from __future__ import annotations

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

    def _loop(self) -> None:
        while self._running:
            snapshot = self._vision.get_snapshot()
            settings = self._get_settings()
            tracking_target = self._select_tracking_target(snapshot)

            if settings.auto_tracking_enabled and tracking_target is not None and not self._manual_override_active():
                self._track_target(
                    tracking_target,
                    snapshot.frame_width,
                    snapshot.frame_height,
                    settings.camera_step_degrees,
                )

            if self._should_greet(snapshot, settings):
                self._greet(settings, snapshot.summary)
                self._last_greet_monotonic = time.monotonic()

            if settings.autonomous_mode_enabled:
                self._handle_autonomy(snapshot, settings)
            elif self._autonomy_motion_active:
                self._ensure_autonomy_stopped("Autonomous mode is disabled.")

            time.sleep(max(self._config.vision_loop_seconds, 0.08))

    def _select_tracking_target(self, snapshot: VisionSnapshot) -> Detection | None:
        preferred = (
            DetectionLabel.FACE.value,
            DetectionLabel.PERSON.value,
            DetectionLabel.CAT.value,
            DetectionLabel.OBJECT.value,
        )
        for label in preferred:
            for detection in snapshot.detections:
                if detection.label == label:
                    return detection
        return snapshot.detections[0] if snapshot.detections else None

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
        if frame_width <= 0 or frame_height <= 0:
            return
        snapshot = self._hardware.snapshot()
        target_center_x = detection.x + detection.width / 2
        target_center_y = detection.y + detection.height / 2
        frame_center_x = frame_width / 2
        frame_center_y = frame_height / 2
        pan = snapshot.pan
        tilt = snapshot.tilt
        if target_center_x < frame_center_x - self._config.tracking_deadband_px:
            pan -= step_degrees
        elif target_center_x > frame_center_x + self._config.tracking_deadband_px:
            pan += step_degrees
        if target_center_y < frame_center_y - self._config.tracking_deadband_px:
            tilt += step_degrees
        elif target_center_y > frame_center_y + self._config.tracking_deadband_px:
            tilt -= step_degrees
        safe = self._guard.sanitize_camera(CameraRequest(pan=pan, tilt=tilt))
        if safe.pan == snapshot.pan and safe.tilt == snapshot.tilt:
            return
        self._hardware.set_camera(safe.pan, safe.tilt)
        self._on_camera_pose(safe.pan, safe.tilt)
        display_name = detection.display_label or detection.label.replace("_", " ").title()
        self._record_behavior_action(f"Tracking {display_name}.")

    def _greet(self, settings: SettingsState, vision_summary: str) -> None:
        _, target = self._get_audio_state()
        if settings.greeting_mode == GreetingMode.DETECT_ONLY:
            self._on_greet("", "Detection-only mode triggered.")
            return
        greeting = settings.greeting_text
        action = "Simple greeting delivered."
        if settings.greeting_mode == GreetingMode.AI_LIVE:
            greeting = self._ai.generate_detection_greeting(settings.greeting_text, vision_summary)
            action = "AI live greeting delivered."
        wav_bytes = self._ai.synthesize(greeting)
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
