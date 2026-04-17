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
        allow_autonomy: bool = False,
        obstacle_stop_cm: float | None = None,
    ) -> DriveRequest:
        source = request.source.lower()
        if emergency_stop:
            raise SafetyViolation("Emergency stop is active. Reset it before driving.")
        autonomy_sources = {"autonomy", "autonomous"}
        if source in {"ai", "assistant", "llm"} or (source in autonomy_sources and not allow_autonomy):
            raise SafetyViolation("AI-originated motor commands are blocked by design.")
        speed_limit = self.config.drive_max_speed
        if source in autonomy_sources:
            speed_limit = min(speed_limit, self.config.autonomous_max_speed)
        speed = int(clamp(request.speed, -speed_limit, speed_limit))
        steering = int(clamp(request.steering, -self.config.steering_limit, self.config.steering_limit))
        minimum_clearance = self.config.obstacle_stop_cm if obstacle_stop_cm is None else obstacle_stop_cm
        if speed > 0 and distance_cm is not None and distance_cm < minimum_clearance:
            raise SafetyViolation(
                f"Forward motion blocked: obstacle detected at {distance_cm:.1f} cm."
            )
        return DriveRequest(speed=speed, steering=steering, source=request.source)

    def sanitize_autonomous_drive(
        self,
        request: DriveRequest,
        *,
        emergency_stop: bool,
        distance_cm: float | None,
        obstacle_stop_cm: float | None = None,
    ) -> DriveRequest:
        safe = self.sanitize_drive(
            request,
            emergency_stop=emergency_stop,
            distance_cm=distance_cm,
            allow_autonomy=True,
            obstacle_stop_cm=obstacle_stop_cm,
        )
        if safe.speed < 0:
            raise SafetyViolation("Autonomous mode is not allowed to reverse.")
        return safe

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
