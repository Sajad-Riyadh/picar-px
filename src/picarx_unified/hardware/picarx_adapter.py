from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from ..config import AppConfig


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
        self._hardware = self._build_hardware()
        self._backend_name = type(self._hardware).__name__
        self._snapshot = HardwareSnapshot()

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def is_mock(self) -> bool:
        return isinstance(self._hardware, MockPicarx)

    def _build_hardware(self) -> Any:
        if self._config.use_mock_hardware:
            return MockPicarx()
        try:
            from picarx import Picarx

            return Picarx()
        except Exception:
            return MockPicarx()

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
