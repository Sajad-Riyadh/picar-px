from __future__ import annotations

import threading
import time
from typing import Callable

from .ai import AIService
from .audio import AudioRouter
from .config import AppConfig
from .hardware.picarx_adapter import PicarxAdapter
from .models import AudioTarget, CameraRequest, Detection, VoiceMode
from .safety import SafetyGuard
from .vision import VisionService


class PersonGreeterBehavior:
    def __init__(
        self,
        config: AppConfig,
        hardware: PicarxAdapter,
        guard: SafetyGuard,
        vision: VisionService,
        ai: AIService,
        audio: AudioRouter,
        get_audio_state: Callable[[], tuple[VoiceMode, AudioTarget]],
        publish_browser_event: Callable[[dict], None],
        on_camera_pose: Callable[[int, int], None],
        on_greet: Callable[[], None],
    ) -> None:
        self._config = config
        self._hardware = hardware
        self._guard = guard
        self._vision = vision
        self._ai = ai
        self._audio = audio
        self._get_audio_state = get_audio_state
        self._publish_browser_event = publish_browser_event
        self._on_camera_pose = on_camera_pose
        self._on_greet = on_greet
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_greet_monotonic = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="person-greeter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while self._running:
            snapshot = self._vision.get_snapshot()
            primary = snapshot.detections[0] if snapshot.detections else None
            if primary is not None:
                self._track_face(primary, snapshot.frame_width, snapshot.frame_height)
                if time.monotonic() - self._last_greet_monotonic >= self._config.greet_cooldown_seconds:
                    self._greet()
                    self._last_greet_monotonic = time.monotonic()
            time.sleep(0.35)

    def _track_face(self, detection: Detection, frame_width: int, frame_height: int) -> None:
        if frame_width <= 0 or frame_height <= 0:
            return
        snapshot = self._hardware.snapshot()
        face_center_x = detection.x + detection.width / 2
        face_center_y = detection.y + detection.height / 2
        frame_center_x = frame_width / 2
        frame_center_y = frame_height / 2
        pan = snapshot.pan
        tilt = snapshot.tilt
        if face_center_x < frame_center_x - self._config.tracking_deadband_px:
            pan -= self._config.tracking_step_degrees
        elif face_center_x > frame_center_x + self._config.tracking_deadband_px:
            pan += self._config.tracking_step_degrees
        if face_center_y < frame_center_y - self._config.tracking_deadband_px:
            tilt += self._config.tracking_step_degrees
        elif face_center_y > frame_center_y + self._config.tracking_deadband_px:
            tilt -= self._config.tracking_step_degrees
        safe = self._guard.sanitize_camera(CameraRequest(pan=pan, tilt=tilt))
        if safe.pan == snapshot.pan and safe.tilt == snapshot.tilt:
            return
        self._hardware.set_camera(safe.pan, safe.tilt)
        self._on_camera_pose(safe.pan, safe.tilt)

    def _greet(self) -> None:
        mode, target = self._get_audio_state()
        if mode == VoiceMode.MUTE:
            return
        greeting = "Hello there. I can see someone in front of me."
        wav_bytes = self._ai.synthesize(greeting)
        self._audio.route_assistant_audio(
            wav_bytes,
            target,
            self._publish_browser_event,
            text=greeting,
        )
        self._on_greet()
