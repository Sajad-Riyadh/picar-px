from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .models import CameraRequest, DriveRequest


class SafetyViolation(RuntimeError):
    """Raised when a command exceeds configured safety constraints."""


def clamp(value: int | float, minimum: int | float, maximum: int | float) -> int | float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class SafetyGuard:
    config: AppConfig

    def sanitize_drive(
        self,
        request: DriveRequest,
        *,
        emergency_stop: bool,
        distance_cm: float | None,
    ) -> DriveRequest:
        source = request.source.lower()
        if emergency_stop:
            raise SafetyViolation("Emergency stop is active. Reset it before driving.")
        if source in {"ai", "assistant", "autonomy", "llm"}:
            raise SafetyViolation("AI-originated motor commands are blocked by design.")
        speed = int(clamp(request.speed, -self.config.drive_max_speed, self.config.drive_max_speed))
        steering = int(clamp(request.steering, -self.config.steering_limit, self.config.steering_limit))
        if speed > 0 and distance_cm is not None and distance_cm < self.config.obstacle_stop_cm:
            raise SafetyViolation(
                f"Forward motion blocked: obstacle detected at {distance_cm:.1f} cm."
            )
        return DriveRequest(speed=speed, steering=steering, source=request.source)

    def sanitize_camera(self, request: CameraRequest) -> CameraRequest:
        pan = int(clamp(request.pan, -self.config.camera_pan_limit, self.config.camera_pan_limit))
        tilt = int(
            clamp(
                request.tilt,
                self.config.camera_tilt_down_limit,
                self.config.camera_tilt_up_limit,
            )
        )
        return CameraRequest(pan=pan, tilt=tilt)
