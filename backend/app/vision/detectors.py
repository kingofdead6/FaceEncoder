"""
Face and hand detectors built on the MediaPipe **Tasks** API.

Both detectors implement :class:`BaseDetector`, so the pipeline is agnostic to
the underlying model — a YOLO or OpenCV-DNN detector can be dropped in by
implementing the same two methods.

Model choice
------------
* **Face** — BlazeFace short-range (``blaze_face_short_range.tflite``): built
  for webcam distances, ~200 KB, runs in well under a millisecond on CPU.
* **Hands** — ``hand_landmarker.task``: palm detector + 21-point landmark
  model. Boxes derived from landmark extremes are tighter and more stable
  than raw palm-detector boxes.

Both run in ``RunningMode.VIDEO``, which enables MediaPipe's internal
inter-frame tracking (the landmarker only re-runs its detector when tracking
confidence drops — a large speed win on video).

These models were preferred over YOLOv8-face / OpenCV-DNN ResNet-SSD because
they sustain 30–60 FPS *including* blurring and streaming on a laptop CPU,
with webcam-range accuracy on par with the heavier detectors. Model files are
auto-downloaded on first start by :mod:`app.vision.models`.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

import cv2
import numpy as np

from app.config.settings import Settings
from app.utils.logger import get_logger
from app.vision.models import ensure_model
from app.vision.types import Box, Detection

log = get_logger("detectors")


class BaseDetector(ABC):
    """Minimal interface every detector must implement."""

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        """Return the detections found in a BGR frame."""

    @abstractmethod
    def close(self) -> None:
        """Release model resources."""


class _VideoTimestamper:
    """Strictly-increasing millisecond timestamps required by VIDEO mode."""

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._last = -1

    def next(self) -> int:
        ts = int((time.perf_counter() - self._start) * 1000)
        if ts <= self._last:  # two frames inside the same millisecond
            ts = self._last + 1
        self._last = ts
        return ts


def _to_mp_image(frame_bgr: np.ndarray):
    """Convert a BGR OpenCV frame into a MediaPipe SRGB image (zero surprises)."""
    import mediapipe as mp

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


class FaceDetector(BaseDetector):
    """BlazeFace short-range detector (MediaPipe Tasks ``FaceDetector``)."""

    def __init__(self, settings: Settings) -> None:
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        model_path: Path = ensure_model(
            "blaze_face_short_range.tflite", settings.face_model_url, settings.models_path
        )
        options = vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=settings.face_min_confidence,
        )
        self._detector = vision.FaceDetector.create_from_options(options)
        self._ts = _VideoTimestamper()
        log.info("FaceDetector ready (min_conf=%.2f)", settings.face_min_confidence)

    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        h, w = frame_bgr.shape[:2]
        result = self._detector.detect_for_video(_to_mp_image(frame_bgr), self._ts.next())
        detections: List[Detection] = []
        for det in result.detections or []:
            bb = det.bounding_box  # pixel-space: origin_x/origin_y/width/height
            box = Box(float(bb.origin_x), float(bb.origin_y),
                      float(bb.width), float(bb.height)).clamped(w, h)
            score = float(det.categories[0].score) if det.categories else 1.0
            detections.append(Detection(box=box, score=score, label="face"))
        return detections

    def close(self) -> None:
        self._detector.close()


class HandDetector(BaseDetector):
    """21-landmark hand detector (MediaPipe Tasks ``HandLandmarker``)."""

    def __init__(self, settings: Settings) -> None:
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        model_path: Path = ensure_model(
            "hand_landmarker.task", settings.hand_model_url, settings.models_path
        )
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=settings.hand_max_num,
            min_hand_detection_confidence=settings.hand_min_detection_confidence,
            min_hand_presence_confidence=settings.hand_min_presence_confidence,
            min_tracking_confidence=settings.hand_min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._ts = _VideoTimestamper()
        log.info("HandDetector ready (max=%d)", settings.hand_max_num)

    def detect(self, frame_bgr: np.ndarray) -> List[Detection]:
        h, w = frame_bgr.shape[:2]
        result = self._landmarker.detect_for_video(_to_mp_image(frame_bgr), self._ts.next())
        detections: List[Detection] = []
        hands = result.hand_landmarks or []
        handedness = result.handedness or []
        for i, landmarks in enumerate(hands):
            xs = [p.x * w for p in landmarks]
            ys = [p.y * h for p in landmarks]
            box = Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).clamped(w, h)
            label, score = "hand", 1.0
            if i < len(handedness) and handedness[i]:
                cat = handedness[i][0]
                label, score = cat.category_name.lower(), float(cat.score)
            detections.append(
                Detection(box=box, score=score, label=label, landmarks=list(zip(xs, ys)))
            )
        return detections

    def close(self) -> None:
        self._landmarker.close()
