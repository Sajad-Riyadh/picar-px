from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from typing import Callable

from .ai import AIService
from .audio import AudioRouter
from .config import AppConfig
from .hardware.picarx_adapter import PicarxAdapter
from .models import (
    AudioTarget,
    CameraRequest,
    Detection,
    DetectionLabel,
    DriveRequest,
    GreetingMode,
    SettingsState,
    VoiceMode,
    VisionSnapshot,
)
from .safety import SafetyGuard
from .vision import VisionService


logger = logging.getLogger(__name__)

# Tracking state constants
_TRACK_IDLE = "idle"
_TRACK_ACTIVE = "active"
_TRACK_LOST = "lost"
_TRACK_RECENTERING = "recentering"


class RobotBehaviorController:
    def __init__(
        self,
        config: AppConfig,
        hardware: PicarxAdapter,
        guard: SafetyGuard,
        vision: VisionService,
        ai: AIService,
        audio: AudioRouter,
        get_audio_state: Callable[[], tuple[VoiceMode, AudioTarget]],
        get_settings: Callable[[], SettingsState],
        get_emergency_stop: Callable[[], bool],
        manual_override_active: Callable[[], bool],
        publish_browser_event: Callable[[dict], None],
        on_camera_pose: Callable[[int, int], None],
        on_greet: Callable[[str, str], None],
        on_behavior_action: Callable[[str], None],
        on_autonomy_action: Callable[[str], None],
        apply_autonomous_drive: Callable[[DriveRequest, str], None],
        stop_autonomous_drive: Callable[[str], None],
    ) -> None:
        self._config = config
        self._hardware = hardware
        self._guard = guard
        self._vision = vision
        self._ai = ai
        self._audio = audio
        self._get_audio_state = get_audio_state
        self._get_settings = get_settings
        self._get_emergency_stop = get_emergency_stop
        self._manual_override_active = manual_override_active
        self._publish_browser_event = publish_browser_event
        self._on_camera_pose = on_camera_pose
        self._on_greet = on_greet
        self._on_behavior_action = on_behavior_action
        self._on_autonomy_action = on_autonomy_action
        self._apply_autonomous_drive = apply_autonomous_drive
        self._stop_autonomous_drive = stop_autonomous_drive
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_greet_monotonic = 0.0
        self._last_behavior_action = ""
        self._last_autonomy_action = ""
        self._autonomy_motion_active = False
        # --- Tracking state ---
        # Smoothed error (exponential moving average) in pixels
        self._error_x_smooth: float = 0.0
        self._error_y_smooth: float = 0.0
        # Center of the last tracked detection in frame pixels
        self._tracked_cx: float | None = None
        self._tracked_cy: float | None = None
        # Monotonic timestamp of the last servo move command sent
        self._last_servo_time: float = 0.0
        # Monotonic timestamp when the target was first lost (None = not lost)
        self._lost_since: float | None = None
        # Human-readable tracking phase
        self._tracking_state: str = _TRACK_IDLE

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="behavior-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    @property
    def tracking_state(self) -> str:
        """Current auto-follow phase: idle | active | lost | recentering."""
        return self._tracking_state

    def _loop(self) -> None:
        while self._running:
            snapshot = self._vision.get_snapshot()
            settings = self._get_settings()
            tracking_target = self._select_tracking_target(snapshot)

            if settings.auto_tracking_enabled and not self._manual_override_active():
                if tracking_target is not None:
                    # Target reacquired after loss — log the recovery once
                    if self._lost_since is not None:
                        logger.info(
                            "Auto-follow: target reacquired (%s).",
                            tracking_target.display_label or tracking_target.label,
                        )
                    self._lost_since = None
                    self._tracking_state = _TRACK_ACTIVE
                    self._track_target(
                        tracking_target,
                        snapshot.frame_width,
                        snapshot.frame_height,
                        settings.camera_step_degrees,
                    )
                else:
                    now = time.monotonic()
                    if self._lost_since is None:
                        self._lost_since = now
                        self._tracking_state = _TRACK_LOST
                        logger.info("Auto-follow: target lost. Waiting %.1f s before recentering.",
                                    self._config.tracking_lost_target_timeout)
                        self._record_behavior_action("Auto-follow: target lost.")
                    elif now - self._lost_since >= self._config.tracking_lost_target_timeout:
                        self._tracking_state = _TRACK_RECENTERING
                        self._recenter_camera()
            else:
                # Tracking disabled or manual override — reset state cleanly
                if self._tracking_state != _TRACK_IDLE:
                    self._tracking_state = _TRACK_IDLE
                    self._lost_since = None
                    self._error_x_smooth = 0.0
                    self._error_y_smooth = 0.0
                    self._tracked_cx = None
                    self._tracked_cy = None

            if self._should_greet(snapshot, settings):
                self._greet(settings, snapshot.summary)
                self._last_greet_monotonic = time.monotonic()

            if settings.autonomous_mode_enabled:
                self._handle_autonomy(snapshot, settings)
            elif self._autonomy_motion_active:
                self._ensure_autonomy_stopped("Autonomous mode is disabled.")

            time.sleep(max(self._config.vision_loop_seconds, 0.08))

    def _select_tracking_target(self, snapshot: VisionSnapshot) -> Detection | None:
        """Pick the best detection target using a stable scoring heuristic.

        Priority order: face > person > cat > object.  Within the same label,
        score each candidate by:
          - continuity  — prefer the detection closest to the previously tracked
                          centre (avoids erratic target switching).
          - centre bias — prefer detections near the frame centre.
          - area        — larger detections are more reliable.

        The continuity bonus is double-weighted so that a face already being
        tracked is only replaced if a significantly better candidate exists.
        """
        if not snapshot.detections:
            return None

        frame_w = snapshot.frame_width or 320
        frame_h = snapshot.frame_height or 240
        frame_cx = frame_w / 2
        frame_cy = frame_h / 2
        frame_diag = math.hypot(frame_w, frame_h) or 1.0

        preferred = (
            DetectionLabel.FACE.value,
            DetectionLabel.PERSON.value,
            DetectionLabel.CAT.value,
            DetectionLabel.OBJECT.value,
        )

        def score(d: Detection) -> float:
            cx = d.x + d.width / 2
            cy = d.y + d.height / 2
            # Centre bias: 0 = at edge, 1 = dead-centre
            centre_score = 1.0 - math.hypot(cx - frame_cx, cy - frame_cy) / (frame_diag / 2)
            # Area score: 0 = tiny, 1 = fills frame
            area_score = (d.width * d.height) / (frame_w * frame_h)
            # Continuity bonus: reward staying on the same face
            continuity = 0.0
            if self._tracked_cx is not None and self._tracked_cy is not None:
                dist = math.hypot(cx - self._tracked_cx, cy - self._tracked_cy)
                # Bonus decays linearly from 1 → 0 over one frame-diagonal
                continuity = max(0.0, 1.0 - dist / frame_diag)
            return continuity * 2.0 + centre_score + area_score * 0.5

        for label in preferred:
            candidates = [d for d in snapshot.detections if d.label == label]
            if candidates:
                best = max(candidates, key=score)
                logger.debug(
                    "Auto-follow target selected: %s (score=%.2f, cx=%.0f, cy=%.0f).",
                    best.display_label or best.label,
                    score(best),
                    best.x + best.width / 2,
                    best.y + best.height / 2,
                )
                return best

        return snapshot.detections[0]

    def _select_human_target(self, snapshot: VisionSnapshot) -> Detection | None:
        for detection in snapshot.detections:
            if detection.label in {DetectionLabel.FACE.value, DetectionLabel.PERSON.value}:
                return detection
        return None

    def _should_greet(self, snapshot: VisionSnapshot, settings: SettingsState) -> bool:
        if not settings.greeting_enabled or self._get_emergency_stop():
            return False
        if time.monotonic() - self._last_greet_monotonic < self._config.greet_cooldown_seconds:
            return False
        return self._select_human_target(snapshot) is not None

    def _track_target(
        self,
        detection: Detection,
        frame_width: int,
        frame_height: int,
        step_degrees: int,
    ) -> None:
        """Move the camera to keep *detection* centred in the frame.

        Improvements over the original step-only approach:
        - Exponential moving average (EMA) smooths raw pixel error so that a
          single noisy detection does not jerk the camera.
        - Movement is proportional to the smoothed error magnitude, scaled by
          ``step_degrees`` as the maximum step per update.
        - A deadband suppresses micro-corrections that cause jitter.
        - A minimum interval between servo commands rate-limits the updates so
          the servos are not hammered faster than they can physically move.
        - Servo positions are always clamped by the safety guard.
        """
        if frame_width <= 0 or frame_height <= 0:
            return

        now = time.monotonic()
        min_interval = self._config.tracking_update_interval_ms / 1000.0
        if now - self._last_servo_time < min_interval:
            return

        target_cx = detection.x + detection.width / 2
        target_cy = detection.y + detection.height / 2

        # Update persistent tracked centre for the next target-selection cycle
        self._tracked_cx = target_cx
        self._tracked_cy = target_cy

        frame_cx = frame_width / 2
        frame_cy = frame_height / 2

        raw_err_x = target_cx - frame_cx   # positive → target is right of centre
        raw_err_y = target_cy - frame_cy   # positive → target is below centre

        # EMA smoothing: new = alpha*raw + (1-alpha)*prev
        alpha = max(0.05, min(1.0, self._config.tracking_smoothing))
        self._error_x_smooth = alpha * raw_err_x + (1.0 - alpha) * self._error_x_smooth
        self._error_y_smooth = alpha * raw_err_y + (1.0 - alpha) * self._error_y_smooth

        deadband = self._config.tracking_deadband_px
        snapshot = self._hardware.snapshot()
        pan = snapshot.pan
        tilt = snapshot.tilt
        changed = False

        if abs(self._error_x_smooth) > deadband:
            # Proportional step: max step_degrees at full-frame displacement
            scale = min(abs(self._error_x_smooth) / (frame_width / 2), 1.0)
            move = max(1, round(step_degrees * scale))
            pan += move if self._error_x_smooth > 0 else -move
            changed = True

        if abs(self._error_y_smooth) > deadband:
            scale = min(abs(self._error_y_smooth) / (frame_height / 2), 1.0)
            move = max(1, round(step_degrees * scale))
            # Camera tilt: positive error (below centre) → tilt down (negative tilt)
            tilt += -move if self._error_y_smooth > 0 else move
            changed = True

        if not changed:
            return

        safe = self._guard.sanitize_camera(CameraRequest(pan=pan, tilt=tilt))
        if safe.pan == snapshot.pan and safe.tilt == snapshot.tilt:
            return

        self._hardware.set_camera(safe.pan, safe.tilt)
        self._on_camera_pose(safe.pan, safe.tilt)
        self._last_servo_time = now

        display_name = detection.display_label or detection.label.replace("_", " ").title()
        self._record_behavior_action(f"Auto-follow: tracking {display_name}.")
        logger.debug(
            "Auto-follow: pan=%d tilt=%d err=(%.1f, %.1f) smooth=(%.1f, %.1f).",
            safe.pan, safe.tilt,
            raw_err_x, raw_err_y,
            self._error_x_smooth, self._error_y_smooth,
        )

    def _recenter_camera(self) -> None:
        """Slowly return the camera to centre when the target has been lost.

        Each call nudges pan and tilt one small step toward zero.  When the
        camera reaches centre the tracking state resets to idle.
        """
        snapshot = self._hardware.snapshot()
        pan = snapshot.pan
        tilt = snapshot.tilt

        if pan == 0 and tilt == 0:
            # Already centred — clean up tracking state
            self._tracking_state = _TRACK_IDLE
            self._tracked_cx = None
            self._tracked_cy = None
            self._error_x_smooth = 0.0
            self._error_y_smooth = 0.0
            self._lost_since = None
            logger.info("Auto-follow: camera recentred. Tracking idle.")
            self._record_behavior_action("Auto-follow: camera recentred.")
            return

        now = time.monotonic()
        min_interval = self._config.tracking_update_interval_ms / 1000.0
        if now - self._last_servo_time < min_interval:
            return

        # Nudge toward zero by half the configured step (slower than tracking)
        step = max(1, self._config.tracking_step_degrees // 2)
        new_pan = pan - int(math.copysign(min(step, abs(pan)), pan))
        new_tilt = tilt - int(math.copysign(min(step, abs(tilt)), tilt))

        safe = self._guard.sanitize_camera(CameraRequest(pan=new_pan, tilt=new_tilt))
        if safe.pan == pan and safe.tilt == tilt:
            return

        self._hardware.set_camera(safe.pan, safe.tilt)
        self._on_camera_pose(safe.pan, safe.tilt)
        self._last_servo_time = now
        self._record_behavior_action("Auto-follow: recentering camera.")
        logger.debug("Auto-follow: recentering pan=%d→%d tilt=%d→%d.", pan, safe.pan, tilt, safe.tilt)

    def _greet(self, settings: SettingsState, vision_summary: str) -> None:
        _, target = self._get_audio_state()
        if settings.greeting_mode == GreetingMode.DETECT_ONLY:
            self._on_greet("", "Detection-only mode triggered.")
            return
        greeting = settings.greeting_text
        native_wav: bytes | None = None
        action = "Simple greeting delivered."
        if settings.greeting_mode == GreetingMode.AI_LIVE:
            greeting, native_wav = asyncio.run(
                self._ai.generate_detection_greeting(settings.greeting_text, vision_summary)
            )
            action = "AI live greeting delivered."
        wav_bytes = native_wav or self._ai.synthesize(greeting)
        self._audio.route_assistant_audio(
            wav_bytes,
            target,
            self._publish_browser_event,
            text=greeting,
        )
        self._on_greet(greeting, action)

    def _handle_autonomy(self, snapshot: VisionSnapshot, settings: SettingsState) -> None:
        if self._get_emergency_stop():
            self._ensure_autonomy_stopped("Autonomous mode is paused by emergency stop.")
            return
        if self._manual_override_active():
            self._ensure_autonomy_stopped("Autonomous mode is paused by manual override.")
            return
        primary = self._select_tracking_target(snapshot)
        if primary is not None:
            display_name = (primary.display_label or primary.label).lower()
            self._ensure_autonomy_stopped(f"Autonomous hold on detected {display_name}.")
            return

        speed = min(settings.autonomous_drive_speed, self._config.autonomous_max_speed)
        if speed <= 0:
            self._ensure_autonomy_stopped("Autonomous mode is armed and waiting.")
            return

        request = DriveRequest(speed=speed, steering=0, source="autonomous")
        action = "Autonomous patrol forward at safe speed."
        self._apply_autonomous_drive(request, action)
        self._autonomy_motion_active = speed > 0
        self._record_autonomy_action(action)

    def _ensure_autonomy_stopped(self, action: str) -> None:
        if self._autonomy_motion_active:
            self._stop_autonomous_drive(action)
            self._autonomy_motion_active = False
        self._record_autonomy_action(action)

    def _record_behavior_action(self, action: str) -> None:
        if action == self._last_behavior_action:
            return
        self._last_behavior_action = action
        self._on_behavior_action(action)

    def _record_autonomy_action(self, action: str) -> None:
        if action == self._last_autonomy_action:
            return
        self._last_autonomy_action = action
        self._on_autonomy_action(action)


PersonGreeterBehavior = RobotBehaviorController
