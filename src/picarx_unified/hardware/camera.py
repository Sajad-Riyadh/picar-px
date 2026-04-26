from __future__ import annotations

import logging
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np

from ..config import AppConfig

try:
    import cv2
except Exception:  # pragma: no cover - dependency is optional in dev
    cv2 = None

try:
    from picamera2 import Picamera2
except Exception:  # pragma: no cover - Pi-only dependency
    Picamera2 = None


logger = logging.getLogger(__name__)


class CameraService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)
        self._frame: np.ndarray | None = None
        self._frame_jpeg: bytes | None = None
        self._frame_at = 0.0
        self._frame_sequence = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._backend_name = "none"
        self._camera: Any = None
        self._picamera: Any = None
        self._color_gains = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self._configured_format = str(self._config.camera_format).upper()
        self._configured_size = (self._config.camera_width, self._config.camera_height)
        self._configured_fps = float(self._config.camera_fps)
        self._configured_conversion = "none"
        self._first_frame_logged = False
        self._jpeg_encoder_path = "opencv-imencode"
        self._selected_sensor_mode: dict[str, Any] | None = None
        self._active_scaler_crop: tuple[int, int, int, int] | None = None

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def color_gains(self) -> tuple[float, float, float]:
        with self._lock:
            blue_gain, green_gain, red_gain = self._color_gains.tolist()
        return red_gain, green_gain, blue_gain

    def set_color_gains(self, *, red: float, green: float, blue: float) -> None:
        gains = np.array([
            float(np.clip(blue, 0.5, 1.8)),
            float(np.clip(green, 0.5, 1.8)),
            float(np.clip(red, 0.5, 1.8)),
        ], dtype=np.float32)
        with self._lock:
            self._color_gains = gains

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name="camera-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        with self._frame_ready:
            self._frame_ready.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if self._camera is not None:
            try:
                self._camera.release()
            except Exception:
                pass
            self._camera = None
        if self._picamera is not None:
            try:
                self._picamera.stop()
            except Exception:
                pass
            self._picamera = None

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def get_frame_jpeg(self) -> bytes | None:
        with self._lock:
            return self._frame_jpeg

    def stream_generator(self):
        last_sequence = -1
        while True:
            with self._frame_ready:
                timeout = max(1.0 / self._config.camera_fps, 0.2)
                self._frame_ready.wait_for(
                    lambda: self._frame_sequence != last_sequence or not self._running,
                    timeout=timeout,
                )
                jpeg = self._frame_jpeg
                last_sequence = self._frame_sequence
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

    def _capture_loop(self) -> None:
        self._initialise_backend()
        interval = max(1.0 / self._config.camera_fps, 0.03)
        while self._running:
            frame = self._capture_frame()
            if frame is None:
                frame = self._placeholder_frame()
            jpeg = self._encode_frame_jpeg(frame)
            with self._lock:
                self._frame = frame
                self._frame_jpeg = jpeg
                self._frame_at = time.time()
                self._frame_sequence += 1
                self._frame_ready.notify_all()
            time.sleep(interval)

    def _initialise_backend(self) -> None:
        force_backend = self._config.camera_force_backend.strip().lower()
        allow_picamera2 = force_backend in {"auto", "picamera2"}
        allow_opencv = force_backend in {"auto", "opencv"}
        if force_backend == "mock":
            self._backend_name = "mock"
            self._log_camera_startup()
            return

        if not self._config.force_mock_camera and allow_picamera2 and Picamera2 is not None:
            try:
                self._picamera = Picamera2()
                requested_format = str(self._config.camera_format).upper()
                candidate_formats = [requested_format, "BGR888", "RGB888"]
                self._selected_sensor_mode = self._select_sensor_mode(
                    getattr(self._picamera, "sensor_modes", []),
                )
                sensor = self._build_picamera_sensor_config()
                last_error: Exception | None = None
                configuration = None
                self._configured_format = requested_format
                for fmt in candidate_formats:
                    self._configured_format = fmt
                    try:
                        config_kwargs: dict[str, Any] = {
                            "main": {
                                "size": (self._config.camera_width, self._config.camera_height),
                                "format": fmt,
                            },
                            "controls": {"FrameRate": float(self._config.camera_fps)},
                        }
                        if sensor:
                            config_kwargs["sensor"] = sensor
                        configuration = self._picamera.create_video_configuration(**config_kwargs)
                        break
                    except Exception as exc:
                        last_error = exc
                if configuration is None:
                    raise RuntimeError(f"Unable to configure Picamera2 video stream: {last_error}") from last_error
                self._picamera.configure(configuration)
                self._apply_picamera_controls()
                self._picamera.start()
                time.sleep(2.0)
                self._backend_name = "picamera2"
                self._configured_size = (self._config.camera_width, self._config.camera_height)
                self._configured_fps = float(self._config.camera_fps)
                self._log_camera_startup()
                return
            except Exception:
                logger.exception("Failed to initialise Picamera2 backend.")
                self._picamera = None
        if not self._config.force_mock_camera and allow_opencv and cv2 is not None:
            self._camera = cv2.VideoCapture(self._config.camera_index)
            if self._camera is not None and self._camera.isOpened():
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.camera_width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.camera_height)
                self._backend_name = "opencv"
                self._configured_format = "BGR"
                self._configured_conversion = "none"
                self._log_camera_startup()
                return
        self._backend_name = "mock"
        self._configured_conversion = "none"
        self._log_camera_startup()

    def _capture_frame(self) -> np.ndarray | None:
        if self._picamera is not None:
            try:
                frame = self._picamera.capture_array()
                frame = self._coerce_frame_to_bgr(frame)
                if not self._first_frame_logged:
                    logger.info(
                        "Camera first frame shape=%s dtype=%s conversion=%s",
                        getattr(frame, "shape", None),
                        getattr(frame, "dtype", None),
                        self._configured_conversion,
                    )
                    self._first_frame_logged = True
                return self._apply_color_gains(frame)
            except Exception:
                return None
        if self._camera is not None:
            ok, frame = self._camera.read()
            if ok:
                return self._apply_color_gains(frame)
        return None

    def _encode_frame_jpeg(self, frame: np.ndarray) -> bytes | None:
        encoder_mode = self._config.camera_jpeg_encoder.strip().lower()
        prefer_picamera2 = (
            self._picamera is not None
            and encoder_mode in {"auto", "picamera2", "libcamera"}
        )
        if prefer_picamera2:
            try:
                buffer = BytesIO()
                self._picamera.capture_file(buffer, format="jpeg")
                data = buffer.getvalue()
                if data:
                    self._jpeg_encoder_path = "picamera2-capture_file"
                    return data
            except Exception:
                logger.warning("Picamera2 native JPEG encode failed, falling back to OpenCV.", exc_info=True)
        if cv2 is None:
            return None
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._config.jpeg_quality],
        )
        if not ok:
            return None
        self._jpeg_encoder_path = "opencv-imencode"
        return encoded.tobytes()

    def _coerce_frame_to_bgr(self, frame: np.ndarray) -> np.ndarray:
        if cv2 is None or frame.ndim != 3:
            self._configured_conversion = "none"
            return frame
        channels = frame.shape[2]
        color_fix = self._config.camera_color_fix.strip().lower()
        configured_format = str(self._configured_format).upper()
        if channels == 4:
            if "BGR" in configured_format:
                self._configured_conversion = "BGRA2BGR"
                return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            self._configured_conversion = "RGBA2BGR"
            return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        if channels != 3:
            self._configured_conversion = "none"
            return frame
        if color_fix == "none":
            self._configured_conversion = "none"
            return frame
        if color_fix == "rgb2bgr":
            self._configured_conversion = "RGB2BGR"
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if color_fix == "bgr2rgb":
            self._configured_conversion = "BGR2RGB"
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if "RGB" in configured_format and "BGR" not in configured_format:
            self._configured_conversion = "RGB2BGR"
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        self._configured_conversion = "none"
        return frame

    def _log_camera_startup(self) -> None:
        logger.info(
            "Camera startup backend=%s format=%s size=%s fps=%.2f conversion=%s",
            self._backend_name,
            self._configured_format,
            self._configured_size,
            self._configured_fps,
            self._configured_conversion,
        )

    def _apply_picamera_controls(self) -> None:
        if self._picamera is None:
            return
        controls_payload: dict[str, Any] = {"AwbEnable": bool(self._config.camera_awb_enable)}
        if self._config.camera_full_fov:
            full_crop = self._full_sensor_crop()
            if full_crop is not None:
                controls_payload["ScalerCrop"] = full_crop
                self._active_scaler_crop = full_crop
        awb_mode = self._config.camera_awb_mode.strip().lower()
        if awb_mode and awb_mode != "auto":
            mode_value = self._resolve_awb_mode_value(awb_mode)
            if mode_value is not None:
                controls_payload["AwbMode"] = mode_value
        try:
            self._picamera.set_controls(controls_payload)
        except Exception:
            logger.warning("Unable to apply Picamera2 controls: %s", controls_payload, exc_info=True)

    def _resolve_awb_mode_value(self, awb_mode: str) -> Any:
        try:
            from libcamera import controls as libcamera_controls  # type: ignore
        except Exception:
            return None
        awb_enum = getattr(libcamera_controls, "AwbModeEnum", None)
        if awb_enum is None:
            return None
        candidates = [
            awb_mode,
            awb_mode.title(),
            awb_mode.capitalize(),
            awb_mode.replace("_", ""),
            awb_mode.replace("_", "").title(),
        ]
        for candidate in candidates:
            if hasattr(awb_enum, candidate):
                return getattr(awb_enum, candidate)
        return None

    def _full_sensor_crop(self) -> tuple[int, int, int, int] | None:
        if self._picamera is None:
            return None
        try:
            properties = getattr(self._picamera, "camera_properties", {}) or {}
            crop = properties.get("ScalerCropMaximum")
            if crop and len(crop) == 4:
                return tuple(int(value) for value in crop)
            pixel_array_size = properties.get("PixelArraySize")
            if pixel_array_size and len(pixel_array_size) == 2:
                return (0, 0, int(pixel_array_size[0]), int(pixel_array_size[1]))
        except Exception:
            logger.warning("Unable to resolve full sensor crop rectangle.", exc_info=True)
        return None

    def _select_sensor_mode(self, sensor_modes: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not sensor_modes:
            return None
        requested_w = int(self._config.camera_width)
        requested_h = int(self._config.camera_height)
        requested_fps = float(self._config.camera_fps)
        viable = [
            mode for mode in sensor_modes
            if float(mode.get("fps", 0.0)) >= requested_fps
        ]
        candidates = viable or list(sensor_modes)
        candidates.sort(
            key=lambda mode: (
                abs(int(mode["size"][0]) - requested_w) + abs(int(mode["size"][1]) - requested_h),
                -(int(mode["size"][0]) * int(mode["size"][1])),
            )
        )
        return candidates[0]

    def _build_picamera_sensor_config(self) -> dict[str, Any] | None:
        selected = self._selected_sensor_mode or self._select_sensor_mode(
            getattr(self._picamera, "sensor_modes", []),
        )
        if not selected:
            return None
        payload: dict[str, Any] = {"output_size": tuple(selected["size"])}
        if "bit_depth" in selected:
            payload["bit_depth"] = int(selected["bit_depth"])
        return payload

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            frame_shape = list(self._frame.shape) if self._frame is not None else None
            frame_dtype = str(self._frame.dtype) if self._frame is not None else None
            return {
                "backend": self._backend_name,
                "format": self._configured_format,
                "size": list(self._configured_size),
                "fps": self._configured_fps,
                "conversion": self._configured_conversion,
                "jpeg_encoder": self._jpeg_encoder_path,
                "scaler_crop": list(self._active_scaler_crop) if self._active_scaler_crop else None,
                "frame_shape": frame_shape,
                "frame_dtype": frame_dtype,
                "frame_age_seconds": (time.time() - self._frame_at) if self._frame_at else None,
            }

    def save_stream_debug_frames(self) -> dict[str, Any]:
        frame = self.get_frame()
        jpeg = self.get_frame_jpeg()
        if frame is None:
            return {"ok": False, "error": "No frame available."}
        debug_dir = Path(self._config.state_dir) / "camera-debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(int(time.time() * 1000))
        raw_path = debug_dir / f"stream-raw-{stamp}.npy"
        np.save(raw_path, frame)
        jpeg_path = None
        if jpeg is not None:
            jpeg_path = debug_dir / f"stream-jpeg-{stamp}.jpg"
            jpeg_path.write_bytes(jpeg)
        return {
            "ok": True,
            "raw_frame_path": str(raw_path),
            "jpeg_frame_path": str(jpeg_path) if jpeg_path else None,
            "diagnostics": self.diagnostics(),
        }

    def _apply_color_gains(self, frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 3 or frame.shape[2] != 3:
            return frame
        with self._lock:
            gains = self._color_gains.copy()
        balanced = frame.astype(np.float32) * gains.reshape(1, 1, 3)
        return np.clip(balanced, 0, 255).astype(np.uint8)

    def _placeholder_frame(self) -> np.ndarray:
        frame = np.zeros((self._config.camera_height, self._config.camera_width, 3), dtype=np.uint8)
        if cv2 is not None:
            cv2.putText(
                frame,
                f"Camera backend: {self._backend_name}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )
            cv2.putText(
                frame,
                "No live camera frame available",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )
        return frame
