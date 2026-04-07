from __future__ import annotations

import threading
import time

from .hardware.camera import CameraService, cv2
from .models import Detection, VisionSnapshot, utc_now


class VisionService:
    def __init__(self, camera: CameraService) -> None:
        self._camera = camera
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._snapshot = VisionSnapshot(summary="Vision loop is starting.")
        self._face_cascade = None
        if cv2 is not None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(cascade_path)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._analysis_loop, name="vision-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_snapshot(self) -> VisionSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def get_frame_jpeg(self) -> bytes | None:
        return self._camera.get_frame_jpeg()

    def _analysis_loop(self) -> None:
        while self._running:
            frame = self._camera.get_frame()
            snapshot = self._analyse_frame(frame)
            with self._lock:
                self._snapshot = snapshot
            time.sleep(0.25)

    def _analyse_frame(self, frame) -> VisionSnapshot:
        if frame is None:
            return VisionSnapshot(summary="No camera frame is available yet.")
        frame_height, frame_width = frame.shape[:2]
        if cv2 is None or self._face_cascade is None or self._face_cascade.empty():
            return VisionSnapshot(
                summary="OpenCV face detection is unavailable.",
                analyzed_at=utc_now(),
                frame_width=frame_width,
                frame_height=frame_height,
            )
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            grayscale,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40),
        )
        detections = [
            Detection(
                label="person_face",
                confidence=0.65,
                x=int(x),
                y=int(y),
                width=int(w),
                height=int(h),
            )
            for (x, y, w, h) in faces
        ]
        detections.sort(key=lambda item: item.width * item.height, reverse=True)
        summary = self._build_summary(detections, frame_width, frame_height)
        return VisionSnapshot(
            detections=detections,
            summary=summary,
            analyzed_at=utc_now(),
            frame_width=frame_width,
            frame_height=frame_height,
        )

    def _build_summary(
        self,
        detections: list[Detection],
        frame_width: int,
        frame_height: int,
    ) -> str:
        if not detections:
            return "No person-like face is currently detected."
        primary = detections[0]
        center_x = primary.x + primary.width / 2
        center_y = primary.y + primary.height / 2
        horizontal = "center"
        vertical = "center"
        if center_x < frame_width * 0.4:
            horizontal = "left"
        elif center_x > frame_width * 0.6:
            horizontal = "right"
        if center_y < frame_height * 0.4:
            vertical = "upper"
        elif center_y > frame_height * 0.6:
            vertical = "lower"
        count = len(detections)
        return (
            f"Detected {count} face(s). "
            f"The primary face is near the {horizontal}-{vertical} part of the frame."
        )
