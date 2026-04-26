from __future__ import annotations

import logging
import threading
import time
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
        self._frame: np.ndarray | None = None
        self._frame_at = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._backend_name = "none"
        self._camera: Any = None
        self._picamera: Any = None
        self._color_gains = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self._configured_format = "unknown"
        self._configured_size = (self._config.camera_width, self._config.camera_height)
        self._configured_fps = float(self._config.camera_fps)
        self._configured_conversion = "none"
        self._first_frame_logged = False

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
        frame = self.get_frame()
        if frame is None or cv2 is None:
            return None
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._config.jpeg_quality],
        )
        if not ok:
            return None
        return encoded.tobytes()

    def stream_generator(self):
        while True:
            jpeg = self.get_frame_jpeg()
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            time.sleep(max(1.0 / self._config.camera_fps, 0.05))

    def _capture_loop(self) -> None:
        self._initialise_backend()
        interval = max(1.0 / self._config.camera_fps, 0.03)
        while self._running:
            frame = self._capture_frame()
            if frame is None:
                frame = self._placeholder_frame()
            with self._lock:
                self._frame = frame
                self._frame_at = time.time()
            time.sleep(interval)

    def _initialise_backend(self) -> None:
        if not self._config.force_mock_camera and Picamera2 is not None:
            try:
                self._picamera = Picamera2()
                self._picam_format = "BGR888"
                try:
                    configuration = self._picamera.create_video_configuration(
                        main={
                            "size": (self._config.camera_width, self._config.camera_height),
                            "format": self._picam_format,
                        },
                        controls={"FrameRate": float(self._config.camera_fps)},
                    )
                except Exception:
                    self._picam_format = "RGB888"
                    configuration = self._picamera.create_video_configuration(
                        main={
                            "size": (self._config.camera_width, self._config.camera_height),
                            "format": self._picam_format,
                        },
                        controls={"FrameRate": float(self._config.camera_fps)},
                    )
                self._picamera.configure(configuration)
                self._picamera.start()
                import logging
                logging.getLogger(__name__).info(
                    "picamera2 started: format=%s size=%dx%d fps=%d",
                    self._picam_format,
                    self._config.camera_width,
                    self._config.camera_height,
                    self._config.camera_fps,
                )
                time.sleep(2.0)
                self._backend_name = "picamera2"
                return
            except Exception:
                self._picamera = None
        if not self._config.force_mock_camera and cv2 is not None:
            self._camera = cv2.VideoCapture(self._config.camera_index)
            if self._camera is not None and self._camera.isOpened():
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.camera_width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.camera_height)
                self._backend_name = "opencv"
                return
        self._backend_name = "mock"

    def _capture_frame(self) -> np.ndarray | None:
        if self._picamera is not None:
            try:
                frame = self._picamera.capture_array()
                if not getattr(self, "_logged_first_frame", False):
                    import logging
                    logging.getLogger(__name__).info(
                        "first frame: shape=%s dtype=%s format=%s",
                        frame.shape, frame.dtype, self._picam_format,
                    )
                    self._logged_first_frame = True
                n_ch = frame.shape[2] if frame.ndim == 3 else 0
                if self._picam_format == "BGR888" and n_ch == 3:
                    pass
                elif self._picam_format == "RGB888" and n_ch == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif n_ch == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                return self._apply_color_gains(frame)
            except Exception:
                return None
        if self._camera is not None:
            ok, frame = self._camera.read()
            if ok:
                return self._apply_color_gains(frame)
        return None

    def _picamera_conversion_for_frame(self, frame: np.ndarray) -> tuple[int | None, str]:
        if frame.ndim != 3:
            return None, "none"
        channels = frame.shape[2]
        if channels == 4:
            return cv2.COLOR_RGBA2BGR if cv2 is not None else None, "RGBA2BGR"
        if self._configured_format == "RGB888" and channels == 3:
            return cv2.COLOR_RGB2BGR if cv2 is not None else None, "RGB2BGR"
        return None, "none"

    def _log_camera_startup(self) -> None:
        logger.info(
            "Camera startup backend=%s format=%s size=%s fps=%.2f conversion=%s",
            self._backend_name,
            self._configured_format,
            self._configured_size,
            self._configured_fps,
            self._configured_conversion,
        )

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
