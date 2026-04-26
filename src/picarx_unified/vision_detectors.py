from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from typing import Iterable

import numpy as np

from .hardware.camera import cv2
from .models import Detection, DetectionLabel, SettingsState


CASCADE_SEARCH_DIRS = (
    "/usr/share/opencv4/haarcascades",
    "/usr/share/opencv/haarcascades",
    "/usr/local/share/opencv4/haarcascades",
    "/usr/local/share/OpenCV/haarcascades",
)

LABEL_PRIORITIES = {
    DetectionLabel.FACE.value: 110,
    DetectionLabel.PERSON.value: 100,
    DetectionLabel.CAT.value: 90,
    DetectionLabel.OBJECT.value: 60,
}

LABEL_DISPLAY_NAMES = {
    DetectionLabel.FACE.value: "Face",
    DetectionLabel.PERSON.value: "Person",
    DetectionLabel.CAT.value: "Cat",
    DetectionLabel.OBJECT.value: "Object",
}


def cascade_path(filename: str) -> str | None:
    if cv2 is None:
        return None
    if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
        candidate = os.path.join(cv2.data.haarcascades, filename)
        if os.path.isfile(candidate):
            return candidate
    for search_dir in CASCADE_SEARCH_DIRS:
        candidate = os.path.join(search_dir, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def is_detection_enabled(settings: SettingsState, flag_name: str) -> bool:
    return settings.detection_enabled and bool(getattr(settings, flag_name, False))


def make_detection(
    *,
    label: str,
    x: int,
    y: int,
    width: int,
    height: int,
    confidence: float,
    source: str,
) -> Detection:
    return Detection(
        label=label,
        display_label=LABEL_DISPLAY_NAMES.get(label, label.replace("_", " ").title()),
        confidence=max(0.0, min(float(confidence), 1.0)),
        source=source,
        x=max(0, int(x)),
        y=max(0, int(y)),
        width=max(1, int(width)),
        height=max(1, int(height)),
    )


def detection_area(detection: Detection) -> int:
    return detection.width * detection.height


def detection_sort_key(detection: Detection) -> tuple[int, int, float]:
    return (
        LABEL_PRIORITIES.get(detection.label, 0),
        detection_area(detection),
        detection.confidence,
    )


def intersection_over_union(left: Detection, right: Detection) -> float:
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    union = detection_area(left) + detection_area(right) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def non_max_suppression(
    detections: Iterable[Detection],
    *,
    iou_threshold: float = 0.4,
) -> list[Detection]:
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.label, []).append(detection)

    selected: list[Detection] = []
    for label, candidates in grouped.items():
        del label
        ordered = sorted(candidates, key=detection_sort_key, reverse=True)
        kept: list[Detection] = []
        for candidate in ordered:
            if any(intersection_over_union(candidate, existing) >= iou_threshold for existing in kept):
                continue
            kept.append(candidate)
        selected.extend(kept)
    return sorted(selected, key=detection_sort_key, reverse=True)


def remove_overlapping_motion_detections(
    detections: Iterable[Detection],
    *,
    overlap_threshold: float = 0.2,
) -> list[Detection]:
    detections = list(detections)
    static_targets = [item for item in detections if item.label != DetectionLabel.OBJECT.value]
    filtered: list[Detection] = []
    for detection in detections:
        if detection.label != DetectionLabel.OBJECT.value:
            filtered.append(detection)
            continue
        if any(intersection_over_union(detection, target) >= overlap_threshold for target in static_targets):
            continue
        filtered.append(detection)
    return filtered


def summarize_labels(detections: Iterable[Detection]) -> tuple[list[str], dict[str, int]]:
    counts = Counter(detection.label for detection in detections)
    ordered_labels = sorted(counts, key=lambda label: (-LABEL_PRIORITIES.get(label, 0), label))
    return ordered_labels, dict(counts)


@dataclass(slots=True)
class DetectorContext:
    frame: np.ndarray
    grayscale: np.ndarray
    frame_width: int
    frame_height: int


class CascadeDetector:
    def __init__(
        self,
        *,
        label: str,
        enabled_flag: str,
        filenames: tuple[str, ...],
        source: str,
        min_size: tuple[int, int],
        scale_factor: float = 1.1,
        min_neighbors: int = 5,
        confidence: float = 0.7,
    ) -> None:
        self._label = label
        self._enabled_flag = enabled_flag
        self._scale_factor = scale_factor
        self._min_neighbors = min_neighbors
        self._min_size = min_size
        self._confidence = confidence
        self._source = source
        self._classifier = None
        if cv2 is None:
            return
        for filename in filenames:
            path = cascade_path(filename)
            if not path:
                continue
            classifier = cv2.CascadeClassifier(path)
            if not classifier.empty():
                self._classifier = classifier
                break

    @property
    def available(self) -> bool:
        return self._classifier is not None

    def detect(self, context: DetectorContext, settings: SettingsState) -> list[Detection]:
        if not self.available or not is_detection_enabled(settings, self._enabled_flag):
            return []
        rects = self._classifier.detectMultiScale(
            context.grayscale,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            minSize=self._min_size,
        )
        return [
            make_detection(
                label=self._label,
                x=int(x),
                y=int(y),
                width=int(width),
                height=int(height),
                confidence=self._confidence,
                source=self._source,
            )
            for (x, y, width, height) in rects
        ]


class HogPersonDetector:
    def __init__(self, *, enabled: bool = True) -> None:
        self._label = DetectionLabel.PERSON.value
        self._enabled_flag = "person_detection_enabled"
        self._source = "hog_person"
        self._hog = None
        if cv2 is None or not enabled:
            return
        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception:
            hog = None
        self._hog = hog

    @property
    def available(self) -> bool:
        return self._hog is not None

    def detect(self, context: DetectorContext, settings: SettingsState) -> list[Detection]:
        if not self.available or not is_detection_enabled(settings, self._enabled_flag):
            return []
        scale = 0.75 if context.frame_width >= 480 else 1.0
        frame = context.frame
        if scale != 1.0:
            frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        boxes, weights = self._hog.detectMultiScale(
            frame,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        detections: list[Detection] = []
        for (x, y, width, height), weight in zip(boxes, weights):
            confidence = min(float(weight[0] if np.ndim(weight) else weight) / 2.5, 0.88)
            if scale != 1.0:
                x = int(round(x / scale))
                y = int(round(y / scale))
                width = int(round(width / scale))
                height = int(round(height / scale))
            detections.append(
                make_detection(
                    label=DetectionLabel.PERSON.value,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    confidence=max(0.45, confidence),
                    source=self._source,
                )
            )
        return detections


class MotionObjectDetector:
    def __init__(self, min_area: int) -> None:
        self._label = DetectionLabel.OBJECT.value
        self._enabled_flag = "object_detection_enabled"
        self._source = "motion_object"
        self._min_area = max(400, int(min_area))
        self._subtractor = None
        if cv2 is None:
            return
        try:
            self._subtractor = cv2.createBackgroundSubtractorMOG2(
                history=180,
                varThreshold=32,
                detectShadows=False,
            )
        except Exception:
            self._subtractor = None

    @property
    def available(self) -> bool:
        return self._subtractor is not None

    def detect(self, context: DetectorContext, settings: SettingsState) -> list[Detection]:
        if not self.available or not is_detection_enabled(settings, self._enabled_flag):
            return []
        mask = self._subtractor.apply(context.grayscale)
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = context.frame_width * context.frame_height
        detections: list[Detection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self._min_area or area > frame_area * 0.45:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            if width < 30 or height < 30:
                continue
            detections.append(
                make_detection(
                    label=DetectionLabel.OBJECT.value,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    confidence=min(0.8, 0.35 + (area / max(frame_area, 1))),
                    source=self._source,
                )
            )
        return detections
