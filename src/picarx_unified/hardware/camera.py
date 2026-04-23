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
        with self._frame_ready:
            return None if self._frame is None else self._frame.copy()

    def get_frame_jpeg(self) -> bytes | None:
        with self._frame_ready:
            if self._frame_jpeg is not None:
                return self._frame_jpeg
            frame = None if self._frame is None else self._frame.copy()
        if frame is None:
            return None
        jpeg = self._encode_frame_jpeg(frame)
        if jpeg is None:
            return None
        with self._frame_ready:
            if self._frame_jpeg is None:
                self._frame_jpeg = jpeg
            return self._frame_jpeg

    def stream_generator(self):
        last_sequence = -1
        while True:
            with self._frame_ready:
                self._frame_ready.wait_for(
                    lambda: self._frame_sequence != last_sequence or not self._running
                )
                if not self._running and self._frame_sequence == last_sequence:
                    break
                last_sequence = self._frame_sequence
                jpeg = self._frame_jpeg
            if not jpeg:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    def _capture_loop(self) -> None:
        self._initialise_backend()
        interval = max(1.0 / self._config.camera_fps, 0.03)
        while self._running:
            frame = self._capture_frame()
            if frame is None:
                frame = self._placeholder_frame()
            jpeg = self._encode_frame_jpeg(frame)
            with self._frame_ready:
                self._frame = frame
                self._frame_jpeg = jpeg
                self._frame_at = time.time()
                self._frame_sequence += 1
                self._frame_ready.notify_all()
            time.sleep(interval)

    def _initialise_backend(self) -> None:
        if not self._config.force_mock_camera and Picamera2 is not None:
            try:
                self._picamera = Picamera2()
                sensor_config = self._build_picamera_sensor_config()
                configuration = self._picamera.create_video_configuration(
                    main={
                        "size": (self._config.camera_width, self._config.camera_height),
                        "format": "BGR888",
                    },
                    sensor=sensor_config,
                )
                self._picamera.configure(configuration)
                self._picamera.start()
                time.sleep(2.0)
                self._backend_name = "picamera2"
                logger.info("Camera backend initialized with Picamera2.")
                return
            except Exception:
                logger.exception("Picamera2 initialization failed; falling back to other camera backends.")
                self._picamera = None
        if not self._config.force_mock_camera and cv2 is not None:
            try:
                self._camera = cv2.VideoCapture(self._config.camera_index)
                if self._camera is not None and self._camera.isOpened():
                    self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.camera_width)
                    self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.camera_height)
                    self._backend_name = "opencv"
                    logger.info("Camera backend initialized with OpenCV capture.")
                    return
            except Exception:
                logger.exception("OpenCV camera initialization failed; using mock camera backend.")
        self._backend_name = "mock"
        logger.warning("Camera backend is using mock frames.")

    def _build_picamera_sensor_config(self) -> dict[str, Any] | None:
        sensor_modes = getattr(self._picamera, "sensor_modes", None)
        if not sensor_modes:
            return None
        selected_mode = self._select_sensor_mode(sensor_modes)
        if not selected_mode:
            return None
        output_size = selected_mode.get("size") or selected_mode.get("output_size")
        bit_depth = selected_mode.get("bit_depth")
        if not output_size:
            return None
        sensor_config: dict[str, Any] = {"output_size": tuple(output_size)}
        if bit_depth is not None:
            sensor_config["bit_depth"] = int(bit_depth)
        logger.info("Camera sensor mode selected for full FoV stream: %s", sensor_config)
        return sensor_config

    def _select_sensor_mode(self, sensor_modes: list[dict[str, Any]]) -> dict[str, Any] | None:
        target_ratio = self._config.camera_width / max(self._config.camera_height, 1)
        requested_fps = max(float(self._config.camera_fps), 1.0)
        min_width = self._config.camera_width
        min_height = self._config.camera_height
        candidates: list[tuple[float, int, int, dict[str, Any]]] = []
        fallback_candidates: list[tuple[float, int, int, dict[str, Any]]] = []

        for mode in sensor_modes:
            size = mode.get("size") or mode.get("output_size")
            if not size or len(size) != 2:
                continue
            width, height = int(size[0]), int(size[1])
            if width <= 0 or height <= 0:
                continue
            ratio_delta = abs((width / height) - target_ratio)
            fps = self._mode_max_fps(mode)
            record = (ratio_delta, -width * height, -int(round(fps * 100)), mode)
            if width >= min_width and height >= min_height:
                fallback_candidates.append(record)
                if fps >= requested_fps:
                    candidates.append(record)

        if candidates:
            return sorted(candidates, key=lambda item: (item[0], item[1], item[2]))[0][3]
        if fallback_candidates:
            return sorted(fallback_candidates, key=lambda item: (item[0], item[1], item[2]))[0][3]
        return None

    def _mode_max_fps(self, mode: dict[str, Any]) -> float:
        for key in ("fps", "max_fps", "framerate"):
            value = mode.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        return 0.0

    def _capture_frame(self) -> np.ndarray | None:
        if self._picamera is not None:
            try:
                frame = self._picamera.capture_array()
                # Do not use cvtColor here; passing the array directly 
                # to imencode might correctly use the native layout 
                # (or picamera already matched it).
                return self._apply_color_gains(frame)
            except Exception:
                logger.exception("Picamera2 frame capture failed.")
                return None
        if self._camera is not None:
            try:
                ok, frame = self._camera.read()
            except Exception:
                logger.exception("OpenCV frame capture failed.")
                return None
            if ok:
                return self._apply_color_gains(frame)
        return None

    def _apply_color_gains(self, frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 3 or frame.shape[2] != 3:
            return frame
        with self._lock:
            gains = self._color_gains.copy()
        balanced = frame.astype(np.float32) * gains.reshape(1, 1, 3)
        return np.clip(balanced, 0, 255).astype(np.uint8)

    def _encode_frame_jpeg(self, frame: np.ndarray) -> bytes | None:
        if cv2 is None:
            return None
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._config.jpeg_quality],
        )
        if not ok:
            return None
        return encoded.tobytes()

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
