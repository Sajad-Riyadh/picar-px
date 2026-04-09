from __future__ import annotations

import asyncio
import json
import threading
import time

from .ai import AIService
from .audio import AudioRouter
from .behaviors import PersonGreeterBehavior
from .config import AppConfig
from .hardware.camera import CameraService
from .hardware.picarx_adapter import PicarxAdapter
from .models import AudioTarget, CameraRequest, CameraState, DriveRequest, DriveState, HealthResponse, RobotSession, VoiceMode, utc_now
from .safety import SafetyGuard
from .state import StateStore
from .vision import VisionService


class RobotRuntime:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.store = StateStore(config.state_dir)
        self.guard = SafetyGuard(config)
        self.hardware = PicarxAdapter(config)
        self.camera = CameraService(config)
        self.audio = AudioRouter(config.voice_sample_rate)
        self.ai = AIService(config)
        self.vision = VisionService(self.camera)
        self._ws_lock = threading.Lock()
        self._browser_clients: set[object] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._watchdog_thread: threading.Thread | None = None
        self._last_drive_command_monotonic = 0.0
        self.behaviors = PersonGreeterBehavior(
            config=config,
            hardware=self.hardware,
            guard=self.guard,
            vision=self.vision,
            ai=self.ai,
            audio=self.audio,
            get_audio_state=self.get_audio_state,
            publish_browser_event=self.publish_browser_event,
            on_camera_pose=self.record_camera_pose,
            on_greet=self._record_greeting,
        )

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._running:
            return
        self._loop = loop
        self._running = True
        self.hardware.reset_pose()
        self.store.update(self._refresh_session_metadata)
        self.camera.start()
        self.vision.start()
        self.behaviors.start()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="drive-watchdog", daemon=True)
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._running = False
        self.behaviors.stop()
        self.vision.stop()
        self.camera.stop()
        self.audio.close()
        self.hardware.stop()
        self.store.update(self._refresh_session_metadata)
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)

    def current_session(self) -> RobotSession:
        session = self.store.load()
        self._sync_session_hardware_state(session)
        session.vision = self.vision.get_snapshot()
        session.ai_provider = self.ai.provider_name
        session.browser_connected = self.browser_client_count > 0
        session.updated_at = utc_now()
        return session

    @property
    def browser_client_count(self) -> int:
        with self._ws_lock:
            return len(self._browser_clients)

    def health(self) -> HealthResponse:
        return HealthResponse(
            ok=True,
            hardware_backend=self.hardware.backend_name,
            camera_backend=self.camera.backend_name,
            ai_provider=self.ai.provider_name,
            browser_clients=self.browser_client_count,
        )

    def get_audio_state(self) -> tuple[VoiceMode, AudioTarget]:
        session = self.store.load()
        return session.voice_mode, session.audio_target

    def set_voice_mode(self, mode: VoiceMode) -> RobotSession:
        self.store.update(lambda state: setattr(state, "voice_mode", mode))
        return self._publish_state()

    def set_audio_target(self, target: AudioTarget) -> RobotSession:
        self.store.update(lambda state: setattr(state, "audio_target", target))
        return self._publish_state()

    def record_error(self, message: str | None) -> RobotSession:
        self.store.update(lambda state: setattr(state, "last_error", message))
        return self._publish_state()

    def apply_drive(self, request: DriveRequest) -> RobotSession:
        session = self.store.load()
        distance = self.hardware.get_distance()
        safe = self.guard.sanitize_drive(
            request,
            emergency_stop=session.emergency_stop,
            distance_cm=distance,
        )
        self.hardware.drive(safe.speed, safe.steering)
        self._last_drive_command_monotonic = time.monotonic()
        self.store.update(
            lambda state: self._update_drive_state(
                state,
                speed=safe.speed,
                steering=safe.steering,
                error=None,
            )
        )
        return self._publish_state()

    def stop_drive(self, *, error: str | None = None) -> RobotSession:
        self.hardware.stop()
        self.store.update(lambda state: self._update_drive_state(state, speed=0, steering=0, error=error))
        return self._publish_state()

    def set_camera(self, request: CameraRequest) -> RobotSession:
        safe = self.guard.sanitize_camera(request)
        self.hardware.set_camera(safe.pan, safe.tilt)
        return self.record_camera_pose(safe.pan, safe.tilt)

    def record_camera_pose(self, pan: int, tilt: int) -> RobotSession:
        self.store.update(
            lambda state: self._update_camera_state(
                state,
                pan=pan,
                tilt=tilt,
                error=None,
            )
        )
        return self._publish_state()

    def trigger_emergency_stop(self, reason: str = "Emergency stop requested.") -> RobotSession:
        self.hardware.stop()
        self.store.update(
            lambda state: self._set_emergency_state(
                state,
                emergency_stop=True,
                error=reason,
            )
        )
        return self._publish_state()

    def clear_emergency_stop(self) -> RobotSession:
        self.store.update(
            lambda state: self._set_emergency_state(
                state,
                emergency_stop=False,
                error=None,
            )
        )
        return self._publish_state()

    def answer_vision_question(self, question: str) -> str:
        snapshot = self.vision.get_snapshot()
        frame = self.vision.get_frame_jpeg()
        return self.ai.answer_vision(question, snapshot.summary, frame)

    def handle_ai_turn(self, transcript: str) -> str:
        snapshot = self.vision.get_snapshot()
        session = self.store.load()
        reply = self.ai.generate_reply(transcript, snapshot.summary)
        wav_bytes = self.ai.synthesize(reply)
        self.audio.route_assistant_audio(
            wav_bytes,
            session.audio_target,
            self.publish_browser_event,
            text=reply,
        )
        self.publish_browser_event({"type": "transcript", "text": transcript})
        return reply

    def register_browser_client(self, websocket: object) -> None:
        with self._ws_lock:
            self._browser_clients.add(websocket)
        self.store.update(lambda state: setattr(state, "browser_connected", True))
        self._publish_state()

    def unregister_browser_client(self, websocket: object) -> None:
        with self._ws_lock:
            self._browser_clients.discard(websocket)
            connected = bool(self._browser_clients)
        self.store.update(lambda state: setattr(state, "browser_connected", connected))
        self._publish_state()

    def publish_browser_event(self, payload: dict) -> None:
        if self._loop is None:
            return
        message = json.dumps(payload)
        with self._ws_lock:
            clients = list(self._browser_clients)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        for websocket in clients:
            try:
                if running_loop is self._loop:
                    self._loop.create_task(websocket.send_text(message))
                else:
                    asyncio.run_coroutine_threadsafe(websocket.send_text(message), self._loop)
            except Exception:
                pass

    def _record_greeting(self) -> None:
        self.store.update(lambda state: setattr(state, "last_greeting_at", utc_now()))
        self._publish_state()

    def _watchdog_loop(self) -> None:
        while self._running:
            if self.hardware.snapshot().drive_speed != 0:
                elapsed = time.monotonic() - self._last_drive_command_monotonic
                if elapsed >= self.config.drive_watchdog_seconds:
                    self.stop_drive(error="Drive watchdog timeout triggered.")
            time.sleep(0.2)

    def _refresh_session_metadata(self, state: RobotSession) -> None:
        self._sync_session_hardware_state(state)
        state.ai_provider = self.ai.provider_name
        state.browser_connected = self.browser_client_count > 0
        state.last_error = None

    def _publish_state(self) -> RobotSession:
        session = self.current_session()
        self.publish_browser_event({"type": "state", "state": session.model_dump(mode="json")})
        return session

    def _sync_session_hardware_state(self, state: RobotSession) -> None:
        hardware = self.hardware.snapshot()
        if state.drive.speed != hardware.drive_speed or state.drive.steering != hardware.steering:
            state.drive = DriveState(
                speed=hardware.drive_speed,
                steering=hardware.steering,
                last_command_at=utc_now(),
            )
        if state.camera.pan != hardware.pan or state.camera.tilt != hardware.tilt:
            state.camera = CameraState(
                pan=hardware.pan,
                tilt=hardware.tilt,
                last_command_at=utc_now(),
            )

    def _set_emergency_state(self, state: RobotSession, emergency_stop: bool, error: str | None) -> None:
        state.emergency_stop = emergency_stop
        state.last_error = error
        state.drive = DriveState(speed=0, steering=0, last_command_at=utc_now())

    def _update_drive_state(self, state: RobotSession, speed: int, steering: int, error: str | None) -> None:
        state.drive = DriveState(speed=speed, steering=steering, last_command_at=utc_now())
        state.last_error = error

    def _update_camera_state(self, state: RobotSession, pan: int, tilt: int, error: str | None) -> None:
        state.camera = CameraState(pan=pan, tilt=tilt, last_command_at=utc_now())
        state.last_error = error
