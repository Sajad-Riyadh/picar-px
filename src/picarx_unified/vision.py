from __future__ import annotations

import os
import threading
import time

from .config import AppConfig
from .hardware.camera import CameraService, cv2
from .models import Detection, DetectionLabel, SettingsState, VisionSnapshot, utc_now
from .vision_detectors import (
    CascadeDetector,
    DetectorContext,
    HogPersonDetector,
    MotionObjectDetector,
    detection_sort_key,
    non_max_suppression,
    remove_overlapping_motion_detections,
    summarize_labels,
)


class VisionService:
    def __init__(self, config: AppConfig, camera: CameraService) -> None:
        self._config = config
        self._camera = camera
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._settings = SettingsState()
        self._snapshot = VisionSnapshot(summary="Vision loop is starting.")
        self._detectors = (
            CascadeDetector(
                label=DetectionLabel.FACE.value,
                enabled_flag="face_detection_enabled",
                filenames=("haarcascade_frontalface_default.xml",),
                source="haar_face",
                min_size=(40, 40),
                confidence=0.76,
            ),
            CascadeDetector(
                label=DetectionLabel.PERSON.value,
                enabled_flag="person_detection_enabled",
                filenames=("haarcascade_fullbody.xml",),
                source="haar_fullbody",
                min_size=(48, 96),
                confidence=0.68,
            ),
            CascadeDetector(
                label=DetectionLabel.PERSON.value,
                enabled_flag="person_detection_enabled",
                filenames=("haarcascade_upperbody.xml",),
                source="haar_upperbody",
                min_size=(48, 72),
                confidence=0.62,
            ),
            CascadeDetector(
                label=DetectionLabel.CAT.value,
                enabled_flag="cat_detection_enabled",
                filenames=(
                    "haarcascade_frontalcatface_extended.xml",
                    "haarcascade_frontalcatface.xml",
                ),
                source="haar_cat",
                min_size=(48, 48),
                confidence=0.74,
            ),
            HogPersonDetector(enabled=(os.name != "nt" and not config.force_mock_camera)),
            MotionObjectDetector(config.motion_object_min_area),
        )

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

    def set_settings(self, settings: SettingsState) -> None:
        with self._lock:
            self._settings = settings.model_copy(deep=True)

    def get_snapshot(self) -> VisionSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def diagnostics(self) -> dict:
        with self._lock:
            settings = self._settings.model_copy(deep=True)
            snapshot = self._snapshot.model_copy(deep=True)
        return {
            "running": self._running,
            "frame_width": snapshot.frame_width,
            "frame_height": snapshot.frame_height,
            "detections": len(snapshot.detections),
            "detected_labels": list(snapshot.detected_labels),
            "summary": snapshot.summary,
            "analyzed_at": snapshot.analyzed_at,
            "settings": {
                "detection_enabled": settings.detection_enabled,
                "face_detection_enabled": settings.face_detection_enabled,
                "person_detection_enabled": settings.person_detection_enabled,
                "cat_detection_enabled": settings.cat_detection_enabled,
                "object_detection_enabled": settings.object_detection_enabled,
                "detection_overlay_enabled": settings.detection_overlay_enabled,
            },
            "detectors": self._detector_diagnostics(settings),
        }

    def get_frame_jpeg(self) -> bytes | None:
        return self._camera.get_frame_jpeg()

    def _analysis_loop(self) -> None:
        while self._running:
            frame = self._camera.get_frame()
            snapshot = self._analyse_frame(frame)
            with self._lock:
                self._snapshot = snapshot
            time.sleep(max(self._config.vision_loop_seconds, 0.05))

    def _analyse_frame(self, frame) -> VisionSnapshot:
        with self._lock:
            settings = self._settings.model_copy(deep=True)
        if frame is None:
            return VisionSnapshot(summary="No camera frame is available yet.")
        frame_height, frame_width = frame.shape[:2]
        if cv2 is None:
            return VisionSnapshot(
                summary="OpenCV vision support is unavailable.",
                analyzed_at=utc_now(),
                frame_width=frame_width,
                frame_height=frame_height,
            )
        if not settings.detection_enabled:
            return VisionSnapshot(
                summary="Detection is disabled from settings.",
                analyzed_at=utc_now(),
                frame_width=frame_width,
                frame_height=frame_height,
            )
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        context = DetectorContext(
            frame=frame,
            grayscale=grayscale,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        detections: list[Detection] = []
        for detector in self._detectors:
            detections.extend(detector.detect(context, settings))
        detections = remove_overlapping_motion_detections(
            non_max_suppression(detections, iou_threshold=0.42)
        )
        detections.sort(key=detection_sort_key, reverse=True)
        detected_labels, counts = summarize_labels(detections)
        return VisionSnapshot(
            detections=detections,
            detected_labels=detected_labels,
            counts=counts,
            summary=self._build_summary(detections, frame_width, frame_height),
            analyzed_at=utc_now(),
            frame_width=frame_width,
            frame_height=frame_height,
        )

    def _detector_diagnostics(self, settings: SettingsState) -> list[dict]:
        detectors = []
        for detector in self._detectors:
            enabled_flag = getattr(detector, "_enabled_flag", None)
            detectors.append({
                "name": type(detector).__name__,
                "label": getattr(detector, "_label", None),
                "source": getattr(detector, "_source", None),
                "enabled_flag": enabled_flag,
                "enabled": (
                    settings.detection_enabled
                    and (bool(getattr(settings, enabled_flag, True)) if enabled_flag else True)
                ),
                "available": bool(getattr(detector, "available", False)),
            })
        return detectors

    def _build_summary(
        self,
        detections: list[Detection],
        frame_width: int,
        frame_height: int,
    ) -> str:
        if not detections:
            with self._lock:
                settings = self._settings.model_copy(deep=True)
            active_detectors = [
                detector for detector in self._detector_diagnostics(settings)
                if detector["enabled"] and detector["available"]
            ]
            if not settings.detection_enabled:
                return "Detection is disabled from settings."
            if not active_detectors:
                return "Detection is enabled, but no OpenCV detectors are available on this system."
            return "Detection is active, but no face, person, cat, or moving object is currently visible."
        counts = {
            label: sum(1 for detection in detections if detection.label == label)
            for label in {detection.label for detection in detections}
        }
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

        fragments = []
        for label in sorted(counts, key=lambda name: (-counts[name], name)):
            count = counts[label]
            fragments.append(f"{count} {label}{'' if count == 1 else 's'}")
        labels_summary = ", ".join(fragments)
        primary_label = primary.display_label or primary.label.replace("_", " ").title()
        return (
            f"Detected {labels_summary}. "
            f"Primary target: {primary_label} near the {horizontal}-{vertical} part of the frame."
        )
