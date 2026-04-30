from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ[key] = value


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


def _env_optional_path(name: str) -> Path | None:
    raw_value = _env_text(name)
    if not raw_value:
        return None
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


@dataclass(slots=True)
class AppConfig:
    host: str
    port: int
    https_enable: bool
    ssl_certfile: Path | None
    ssl_keyfile: Path | None
    state_dir: Path
    static_dir: Path
    camera_width: int
    camera_height: int
    camera_fps: int
    camera_index: int
    camera_force_backend: str
    camera_format: str
    camera_color_fix: str
    camera_jpeg_encoder: str
    camera_full_fov: bool
    camera_disable_scaler_crop: bool
    camera_awb_enable: bool
    camera_awb_mode: str
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
    vision_loop_seconds: float
    motion_object_min_area: int
    autonomous_max_speed: int
    autonomous_manual_override_seconds: float
    use_mock_hardware: bool
    hardware_init_mode: str
    force_mock_camera: bool
    api_token: str | None
    gemini_api_key: str | None
    gemini_live_model: str
    gemini_native_audio_model: str
    gemini_transcription_model: str

    @property
    def https_enabled(self) -> bool:
        return (
            self.https_enable
            and self.ssl_certfile is not None
            and self.ssl_keyfile is not None
            and self.ssl_certfile.exists()
            and self.ssl_keyfile.exists()
        )

    @classmethod
    def from_env(cls) -> "AppConfig":
        _load_env_file(PROJECT_ROOT / ".env")
        state_dir = _env_path("PICARX_STATE_DIR", PROJECT_ROOT / "state")
        static_dir = _env_path("PICARX_STATIC_DIR", Path(__file__).resolve().parent / "static")
        return cls(
            host=_env_text("PICARX_HOST", "0.0.0.0") or "0.0.0.0",
            port=_env_int("PICARX_PORT", 8080),
            https_enable=_env_flag("PICARX_HTTPS_ENABLE", False),
            ssl_certfile=_env_optional_path("PICARX_SSL_CERTFILE"),
            ssl_keyfile=_env_optional_path("PICARX_SSL_KEYFILE"),
            state_dir=state_dir,
            static_dir=static_dir,
            camera_width=_env_int("PICARX_CAMERA_WIDTH", 640),
            camera_height=_env_int("PICARX_CAMERA_HEIGHT", 480),
            camera_fps=_env_int("PICARX_CAMERA_FPS", 20),
            camera_index=_env_int("PICARX_CAMERA_INDEX", 0),
            camera_force_backend=_env_text("PICARX_CAMERA_FORCE_BACKEND", "auto") or "auto",
            camera_format=_env_text("PICARX_CAMERA_FORMAT", "RGB888") or "RGB888",
            camera_color_fix=_env_text("PICARX_CAMERA_COLOR_FIX", "auto") or "auto",
            camera_jpeg_encoder=_env_text("PICARX_CAMERA_JPEG_ENCODER", "auto") or "auto",
            camera_full_fov=_env_flag("PICARX_CAMERA_FULL_FOV", True),
            camera_disable_scaler_crop=_env_flag("PICARX_CAMERA_DISABLE_SCALER_CROP", True),
            camera_awb_enable=_env_flag("PICARX_CAMERA_AWB_ENABLE", True),
            camera_awb_mode=_env_text("PICARX_CAMERA_AWB_MODE", "auto") or "auto",
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
            vision_loop_seconds=_env_float("PICARX_VISION_LOOP_SECONDS", 0.25),
            motion_object_min_area=_env_int("PICARX_MOTION_OBJECT_MIN_AREA", 2400),
            autonomous_max_speed=_env_int("PICARX_AUTONOMOUS_MAX_SPEED", 20),
            autonomous_manual_override_seconds=_env_float(
                "PICARX_AUTONOMOUS_MANUAL_OVERRIDE_SECONDS",
                2.5,
            ),
            use_mock_hardware=_env_flag("PICARX_USE_MOCK", False),
            hardware_init_mode=_env_text("PICARX_HARDWARE_INIT_MODE", "auto") or "auto",
            force_mock_camera=_env_flag("PICARX_FORCE_MOCK_CAMERA", False),
            api_token=_env_text("PICARX_API_TOKEN"),
            gemini_api_key=_env_text("GEMINI_API_KEY"),
            gemini_live_model=_env_text("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
            or "gemini-3.1-flash-live-preview",
            gemini_native_audio_model=_env_text(
                "GEMINI_NATIVE_AUDIO_MODEL",
                "gemini-2.5-flash-native-audio-preview-12-2025",
            )
            or "gemini-2.5-flash-native-audio-preview-12-2025",
            gemini_transcription_model=_env_text(
                "GEMINI_TRANSCRIPTION_MODEL",
                "gemini-2.5-flash",
            )
            or "gemini-2.5-flash",
        )
