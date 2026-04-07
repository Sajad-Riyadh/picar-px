from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceMode(str, Enum):
    RELAY = "relay"
    AI_REPLY = "ai_reply"
    MUTE = "mute"


class AudioTarget(str, Enum):
    CAR = "car"
    BROWSER = "browser"
    BOTH = "both"


class DriveRequest(BaseModel):
    speed: int = Field(default=0, ge=-100, le=100)
    steering: int = Field(default=0, ge=-45, le=45)
    source: str = Field(default="browser")


class CameraRequest(BaseModel):
    pan: int = Field(default=0, ge=-90, le=90)
    tilt: int = Field(default=0, ge=-90, le=90)


class ModeRequest(BaseModel):
    mode: VoiceMode


class AudioTargetRequest(BaseModel):
    target: AudioTarget


class VisionQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class DriveState(BaseModel):
    speed: int = 0
    steering: int = 0
    last_command_at: str = Field(default_factory=utc_now)


class CameraState(BaseModel):
    pan: int = 0
    tilt: int = 0
    last_command_at: str = Field(default_factory=utc_now)


class Detection(BaseModel):
    label: str
    confidence: float = 0.0
    x: int
    y: int
    width: int
    height: int


class VisionSnapshot(BaseModel):
    detections: list[Detection] = Field(default_factory=list)
    summary: str = "Camera idle."
    analyzed_at: str = Field(default_factory=utc_now)
    frame_width: int = 0
    frame_height: int = 0


class RobotSession(BaseModel):
    voice_mode: VoiceMode = VoiceMode.MUTE
    audio_target: AudioTarget = AudioTarget.CAR
    emergency_stop: bool = False
    browser_connected: bool = False
    drive: DriveState = Field(default_factory=DriveState)
    camera: CameraState = Field(default_factory=CameraState)
    vision: VisionSnapshot = Field(default_factory=VisionSnapshot)
    ai_provider: str = "rule-based"
    last_greeting_at: str | None = None
    last_error: str | None = None
    updated_at: str = Field(default_factory=utc_now)


class HealthResponse(BaseModel):
    ok: bool
    hardware_backend: str
    camera_backend: str
    ai_provider: str
    browser_clients: int
