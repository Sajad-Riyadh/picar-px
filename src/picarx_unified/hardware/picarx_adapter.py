from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..config import AppConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HardwareSnapshot:
    drive_speed: int = 0
    steering: int = 0
    pan: int = 0
    tilt: int = 0


class MockPicarx:
    def __init__(self) -> None:
        self.state = HardwareSnapshot()

    def set_dir_servo_angle(self, angle: int) -> None:
        self.state.steering = angle

    def forward(self, speed: int) -> None:
        self.state.drive_speed = abs(speed)

    def backward(self, speed: int) -> None:
        self.state.drive_speed = -abs(speed)

    def stop(self) -> None:
        self.state.drive_speed = 0

    def set_cam_pan_angle(self, angle: int) -> None:
        self.state.pan = angle

    def set_cam_tilt_angle(self, angle: int) -> None:
        self.state.tilt = angle

    def get_distance(self) -> float:
        return 100.0


class PicarxAdapter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._hardware = self._init_hardware()
        self._backend_name = type(self._hardware).__name__
        self._snapshot = HardwareSnapshot()
        # If real hardware was requested but unavailable, retry in background
        if not self._config.use_mock_hardware and self.is_mock:
            threading.Thread(
                target=self._retry_hardware_in_background, daemon=True
            ).start()

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def is_mock(self) -> bool:
        return isinstance(self._hardware, MockPicarx)

    def _init_hardware(self) -> Any:
        if self._config.use_mock_hardware:
            return MockPicarx()
        # lgpio creates notification files in CWD; ensure it's writable
        import os
        try:
            os.chdir(os.path.expanduser("~"))
        except OSError:
            pass
        try:
            from picarx import Picarx

            hw = Picarx()
            logger.info("Picarx hardware initialized on first attempt")
            return hw
        except Exception as exc:
            logger.warning(
                "Initial Picarx init failed: %s — starting with MockPicarx, "
                "will keep retrying in background",
                exc,
            )
            return MockPicarx()

    def _retry_hardware_in_background(self) -> None:
        """Probe readiness in a subprocess to avoid leaking GPIO handles."""
        import os

        max_retries = 60  # 60 × 5 s = up to 5 minutes
        probe_cmd = [
            sys.executable, "-c",
            "from picarx import Picarx; Picarx(); print('READY')",
        ]
        # Ensure subprocess inherits a sane environment (HOME is critical for lgpio)
        probe_env = os.environ.copy()
        probe_env.setdefault("HOME", os.path.expanduser("~"))
        for attempt in range(1, max_retries + 1):
            time.sleep(5)
            try:
                result = subprocess.run(
                    probe_cmd, capture_output=True, text=True, timeout=30,
                    env=probe_env, cwd=probe_env.get("HOME", "/tmp"),
                )
            except subprocess.TimeoutExpired:
                logger.warning("Background Picarx probe %d/%d timed out", attempt, max_retries)
                continue
            if "READY" not in (result.stdout or ""):
                last_line = (result.stderr or "").strip().rsplit("\n", 1)[-1]
                logger.warning(
                    "Background Picarx probe %d/%d: %s", attempt, max_retries, last_line
                )
                continue
            # Probe succeeded — I2C and GPIO confirmed ready
            try:
                from picarx import Picarx

                hw = Picarx()
                with self._lock:
                    self._hardware = hw
                    self._backend_name = type(hw).__name__
                logger.info(
                    "Picarx hardware initialized in background (attempt %d)", attempt
                )
                return
            except Exception as exc:
                logger.error(
                    "Picarx probe succeeded but in-process init failed: %s", exc
                )
                return
        logger.error(
            "All background Picarx init attempts failed — staying with MockPicarx"
        )

    def drive(self, speed: int, steering: int) -> None:
        with self._lock:
            self._hardware.set_dir_servo_angle(int(steering))
            if speed > 0:
                self._hardware.forward(int(abs(speed)))
            elif speed < 0:
                self._hardware.backward(int(abs(speed)))
            else:
                self._hardware.stop()
            self._snapshot.drive_speed = speed
            self._snapshot.steering = steering

    def stop(self) -> None:
        with self._lock:
            self._hardware.stop()
            self._snapshot.drive_speed = 0

    def set_camera(self, pan: int, tilt: int) -> None:
        with self._lock:
            self._hardware.set_cam_pan_angle(int(pan))
            self._hardware.set_cam_tilt_angle(int(tilt))
            self._snapshot.pan = pan
            self._snapshot.tilt = tilt

    def reset_pose(self) -> None:
        self.drive(0, 0)
        self.set_camera(0, 0)

    def get_distance(self) -> float | None:
        try:
            distance = self._hardware.get_distance()
        except Exception:
            return None
        try:
            return float(distance)
        except (TypeError, ValueError):
            return None

    def snapshot(self) -> HardwareSnapshot:
        with self._lock:
            return HardwareSnapshot(
                drive_speed=self._snapshot.drive_speed,
                steering=self._snapshot.steering,
                pan=self._snapshot.pan,
                tilt=self._snapshot.tilt,
            )
