from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_text(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _env_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    candidate = Path(raw_value).expanduser() if raw_value else default.expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


@dataclass(slots=True)
class AppConfig:
    host: str
    port: int
    state_dir: Path
    static_dir: Path
    camera_width: int
    camera_height: int
    camera_fps: int
    camera_index: int
    jpeg_quality: int
    voice_sample_rate: int
    voice_chunk_samples: int
    voice_capture_max_seconds: float
    drive_max_speed: int
    steering_limit: int
    camera_pan_limit: int
    camera_tilt_up_limit: int
    camera_tilt_down_limit: int
    obstacle_stop_cm: float
    drive_watchdog_seconds: float
    greet_cooldown_seconds: float
    tracking_step_degrees: int
    tracking_deadband_px: int
    use_mock_hardware: bool
    force_mock_camera: bool
    api_token: str | None
    openai_api_key: str | None
    openai_text_model: str
    openai_vision_model: str
    openai_stt_model: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        state_dir = _env_path("PICARX_STATE_DIR", PROJECT_ROOT / "state")
        static_dir = _env_path("PICARX_STATIC_DIR", Path(__file__).resolve().parent / "static")
        return cls(
            host=_env_text("PICARX_HOST", "0.0.0.0") or "0.0.0.0",
            port=_env_int("PICARX_PORT", 8080),
            state_dir=state_dir,
            static_dir=static_dir,
            camera_width=_env_int("PICARX_CAMERA_WIDTH", 640),
            camera_height=_env_int("PICARX_CAMERA_HEIGHT", 480),
            camera_fps=_env_int("PICARX_CAMERA_FPS", 20),
            camera_index=_env_int("PICARX_CAMERA_INDEX", 0),
            jpeg_quality=_env_int("PICARX_JPEG_QUALITY", 80),
            voice_sample_rate=_env_int("PICARX_VOICE_SAMPLE_RATE", 16000),
            voice_chunk_samples=_env_int("PICARX_VOICE_CHUNK_SAMPLES", 2048),
            voice_capture_max_seconds=_env_float("PICARX_VOICE_CAPTURE_MAX_SECONDS", 20.0),
            drive_max_speed=_env_int("PICARX_MAX_SPEED", 50),
            steering_limit=_env_int("PICARX_STEERING_LIMIT", 30),
            camera_pan_limit=_env_int("PICARX_PAN_LIMIT", 70),
            camera_tilt_up_limit=_env_int("PICARX_TILT_UP_LIMIT", 35),
            camera_tilt_down_limit=_env_int("PICARX_TILT_DOWN_LIMIT", -35),
            obstacle_stop_cm=_env_float("PICARX_OBSTACLE_STOP_CM", 18.0),
            drive_watchdog_seconds=_env_float("PICARX_DRIVE_WATCHDOG_SECONDS", 0.9),
            greet_cooldown_seconds=_env_float("PICARX_GREET_COOLDOWN_SECONDS", 20.0),
            tracking_step_degrees=_env_int("PICARX_TRACKING_STEP_DEGREES", 5),
            tracking_deadband_px=_env_int("PICARX_TRACKING_DEADBAND_PX", 36),
            use_mock_hardware=_env_flag("PICARX_USE_MOCK", False),
            force_mock_camera=_env_flag("PICARX_FORCE_MOCK_CAMERA", False),
            api_token=_env_text("PICARX_API_TOKEN"),
            openai_api_key=_env_text("OPENAI_API_KEY"),
            openai_text_model=_env_text("OPENAI_TEXT_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
            openai_vision_model=_env_text("OPENAI_VISION_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
            openai_stt_model=_env_text("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe") or "gpt-4o-mini-transcribe",
        )
