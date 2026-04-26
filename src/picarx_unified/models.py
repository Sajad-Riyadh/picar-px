from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

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


class GreetingMode(str, Enum):
    SIMPLE = "simple_greeting"
    AI_LIVE = "ai_live_greeting"
    DETECT_ONLY = "detect_only"


class ControlMode(str, Enum):
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"
    EMERGENCY_STOP = "emergency_stop"


class DetectionLabel(str, Enum):
    FACE = "face"
    PERSON = "person"
    CAT = "cat"
    OBJECT = "object"


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


class SettingsState(BaseModel):
    greeting_text: str = Field(default="Hello there. Welcome.", min_length=1, max_length=160)
    greeting_enabled: bool = True
    greeting_mode: GreetingMode = GreetingMode.SIMPLE
    auto_tracking_enabled: bool = True
    detection_enabled: bool = True
    face_detection_enabled: bool = True
    person_detection_enabled: bool = True
    cat_detection_enabled: bool = True
    object_detection_enabled: bool = True
    detection_overlay_enabled: bool = True
    autonomous_mode_enabled: bool = False
    camera_step_degrees: int = Field(default=5, ge=1, le=20)
    camera_red_gain: float = Field(default=1.0, ge=0.5, le=1.8)
    camera_green_gain: float = Field(default=1.0, ge=0.5, le=1.8)
    camera_blue_gain: float = Field(default=1.0, ge=0.5, le=1.8)
    autonomous_drive_speed: int = Field(default=12, ge=0, le=30)
    autonomous_turn_strength: int = Field(default=18, ge=0, le=30)
    autonomous_stop_distance_cm: float = Field(default=26.0, ge=10.0, le=100.0)
    startup_voice_mode: VoiceMode = VoiceMode.MUTE
    startup_audio_target: AudioTarget = AudioTarget.CAR


class SettingsUpdateRequest(BaseModel):
    greeting_text: str | None = Field(default=None, min_length=1, max_length=160)
    greeting_enabled: bool | None = None
    greeting_mode: GreetingMode | None = None
    auto_tracking_enabled: bool | None = None
    detection_enabled: bool | None = None
    face_detection_enabled: bool | None = None
    person_detection_enabled: bool | None = None
    cat_detection_enabled: bool | None = None
    object_detection_enabled: bool | None = None
    detection_overlay_enabled: bool | None = None
    autonomous_mode_enabled: bool | None = None
    camera_step_degrees: int | None = Field(default=None, ge=1, le=20)
    camera_red_gain: float | None = Field(default=None, ge=0.5, le=1.8)
    camera_green_gain: float | None = Field(default=None, ge=0.5, le=1.8)
    camera_blue_gain: float | None = Field(default=None, ge=0.5, le=1.8)
    autonomous_drive_speed: int | None = Field(default=None, ge=0, le=30)
    autonomous_turn_strength: int | None = Field(default=None, ge=0, le=30)
    autonomous_stop_distance_cm: float | None = Field(default=None, ge=10.0, le=100.0)
    startup_voice_mode: VoiceMode | None = None
    startup_audio_target: AudioTarget | None = None


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
    display_label: str | None = None
    confidence: float = 0.0
    source: str = "local"
    x: int
    y: int
    width: int
    height: int


class VisionSnapshot(BaseModel):
    detections: list[Detection] = Field(default_factory=list)
    detected_labels: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    summary: str = "Camera idle."
    analyzed_at: str = Field(default_factory=utc_now)
    frame_width: int = 0
    frame_height: int = 0


class RobotSession(BaseModel):
    voice_mode: VoiceMode = VoiceMode.MUTE
    audio_target: AudioTarget = AudioTarget.CAR
    emergency_stop: bool = False
    browser_connected: bool = False
    control_mode: ControlMode = ControlMode.MANUAL
    autonomous_mode_active: bool = False
    manual_override_active: bool = False
    drive: DriveState = Field(default_factory=DriveState)
    camera: CameraState = Field(default_factory=CameraState)
    vision: VisionSnapshot = Field(default_factory=VisionSnapshot)
    settings: SettingsState = Field(default_factory=SettingsState)
    ai_provider: str = "rule-based"
    person_detected: bool = False
    last_greeting_at: str | None = None
    last_greeting_text: str | None = None
    last_behavior_action: str | None = None
    last_autonomy_action: str | None = None
    last_error: str | None = None
    updated_at: str = Field(default_factory=utc_now)


class HealthResponse(BaseModel):
    ok: bool
    hardware_backend: str
    camera_backend: str
    ai_provider: str
    browser_clients: int
    camera: dict[str, Any] | None = None
