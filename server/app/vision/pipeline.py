"""
Frame processing pipeline.

One :class:`FramePipeline` instance lives inside the processing thread and
turns raw camera frames into the final composited output:

    frame ──▶ detect ──▶ smooth ──▶ mask ──▶ blur ──▶ composite ──▶ overlay

The pipeline reads an immutable *snapshot* of the user settings at the top of
every frame, so REST updates from the frontend apply between frames without
any locking inside the hot loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from app.config.settings import Settings
from app.services.state import PipelineSettings
from app.utils.logger import get_logger
from app.utils.metrics import LatencyMeter, RateMeter
from app.vision.blur_engine import BlurEngine
from app.vision.detectors import BaseDetector, FaceDetector, HandDetector
from app.vision.masking import MaskGenerator
from app.vision.smoothing import MultiBoxSmoother
from app.vision.types import Box, Mode, Region

log = get_logger("pipeline")

_ACCENT = (238, 211, 34)  # BGR — matches the frontend cyan accent


@dataclass
class FrameResult:
    """Output of one pipeline pass."""

    frame: np.ndarray
    detections: int
    latency_ms: float
    fps: float


class FramePipeline:
    """Stateful per-thread processor (detectors are not thread-safe)."""

    def __init__(
        self,
        settings: Settings,
        face_detector: Optional[BaseDetector] = None,
        hand_detector: Optional[BaseDetector] = None,
    ) -> None:
        """
        Args:
            settings: application settings.
            face_detector / hand_detector: optional pre-built detectors —
                used for dependency injection in tests and for swapping in
                alternative models (YOLO, OpenCV-DNN) without touching the
                pipeline. When ``None`` the MediaPipe defaults are built
                lazily inside the processing thread.
        """
        self._settings = settings
        self._face_detector = face_detector
        self._hand_detector = hand_detector
        self._blur = BlurEngine()
        self._masks = MaskGenerator(feather_px=settings.mask_feather_px)
        self._face_smoother = MultiBoxSmoother(
            alpha=settings.smooth_alpha, hold_frames=settings.smooth_hold_frames
        )
        self._hand_smoother = MultiBoxSmoother(
            alpha=settings.smooth_alpha, hold_frames=settings.smooth_hold_frames
        )
        self._fps = RateMeter()
        self._latency = LatencyMeter()
        self._last_mode: Optional[Mode] = None

    # ------------------------------------------------------------------ #
    # Lazy detector construction (inside the processing thread)          #
    # ------------------------------------------------------------------ #
    def _faces(self) -> BaseDetector:
        if self._face_detector is None:
            self._face_detector = FaceDetector(self._settings)
        return self._face_detector

    def _hands(self) -> BaseDetector:
        if self._hand_detector is None:
            self._hand_detector = HandDetector(self._settings)
        return self._hand_detector

    @property
    def cuda_enabled(self) -> bool:
        """Whether the blur engine found a CUDA device."""
        return self._blur.cuda_enabled

    # ------------------------------------------------------------------ #
    # Main entry                                                         #
    # ------------------------------------------------------------------ #
    def process(self, frame: np.ndarray, cfg: PipelineSettings) -> FrameResult:
        """Run the full pipeline on one BGR frame and return the result."""
        t0 = time.perf_counter()
        s = self._settings

        # Downscale for processing — massive latency win, negligible quality cost.
        if frame.shape[1] > s.process_width:
            scale = s.process_width / frame.shape[1]
            frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if cfg.mirror:
            frame = cv2.flip(frame, 1)

        # Reset trackers when the mode flips so stale boxes never leak across.
        if cfg.mode != self._last_mode:
            self._face_smoother.reset()
            self._hand_smoother.reset()
            self._last_mode = cfg.mode

        if cfg.mode == Mode.FACE:
            out, n = self._face_mode(frame, cfg)
        else:
            out, n = self._hand_mode(frame, cfg)

        latency = self._latency.observe(time.perf_counter() - t0)
        fps = self._fps.tick()
        return FrameResult(frame=out, detections=n, latency_ms=latency, fps=fps)

    # ------------------------------------------------------------------ #
    # Mode 1 — Face Privacy                                              #
    # ------------------------------------------------------------------ #
    def _face_mode(self, frame: np.ndarray, cfg: PipelineSettings) -> tuple:
        s = self._settings
        raw = self._faces().detect(frame)
        padded = [d.box.padded(s.face_pad_x, s.face_pad_y) for d in raw]
        boxes = self._face_smoother.update(padded)

        if boxes:
            mask = self._masks.ellipses(frame.shape, boxes)
        else:
            mask = self._masks.empty(frame.shape)

        blurred = self._blur.apply(frame, cfg.blur_type, cfg.strength)
        out = self._masks.composite(frame, blurred, mask, cfg.region)

        if not boxes:
            out = self._banner(out, "No faces detected - step into frame")
        if cfg.show_detections:
            self._draw_boxes(out, boxes, "FACE")
        return out, len(boxes)

    # ------------------------------------------------------------------ #
    # Mode 2 — Hand Privacy                                              #
    # ------------------------------------------------------------------ #
    def _hand_mode(self, frame: np.ndarray, cfg: PipelineSettings) -> tuple:
        s = self._settings
        raw = self._hands().detect(frame)
        padded = [d.box.padded(s.hand_pad, s.hand_pad) for d in raw]
        boxes = self._hand_smoother.update(padded)

        region_box: Optional[Box] = None
        if len(boxes) >= 2:
            # Smallest rectangle containing both (all) hands.
            region_box = Box.union(boxes)
        elif len(boxes) == 1:
            # One hand: expand the rectangle around it.
            region_box = boxes[0].padded(s.single_hand_expand, s.single_hand_expand)

        h, w = frame.shape[:2]
        if region_box is not None:
            mask = self._masks.rectangle(frame.shape, region_box.clamped(w, h))
        else:
            mask = self._masks.empty(frame.shape)

        blurred = self._blur.apply(frame, cfg.blur_type, cfg.strength)
        out = self._masks.composite(frame, blurred, mask, cfg.region)

        if region_box is None:
            # Empty mask + OUTSIDE region blurs everything (privacy-safe),
            # + INSIDE leaves the frame sharp — both get an explanatory banner.
            out = self._banner(out, "No hands detected - show your hands to the camera")
        if cfg.show_detections:
            self._draw_boxes(out, boxes, "HAND")
            if region_box is not None:
                x, y, bw, bh = region_box.clamped(w, h).as_int()
                cv2.rectangle(out, (x, y), (x + bw, y + bh), _ACCENT, 2)
        return out, len(boxes)

    # ------------------------------------------------------------------ #
    # Overlays                                                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _banner(frame: np.ndarray, text: str) -> np.ndarray:
        """Translucent centre banner with an informative message."""
        h, w = frame.shape[:2]
        overlay = frame.copy()
        bh = 46
        y0 = h // 2 - bh // 2
        cv2.rectangle(overlay, (0, y0), (w, y0 + bh), (12, 12, 18), -1)
        frame = cv2.addWeighted(overlay, 0.62, frame, 0.38, 0)
        size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)[0]
        cv2.putText(
            frame,
            text,
            ((w - size[0]) // 2, y0 + bh // 2 + size[1] // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (235, 235, 240),
            2,
            cv2.LINE_AA,
        )
        return frame

    @staticmethod
    def _draw_boxes(frame: np.ndarray, boxes: List[Box], tag: str) -> None:
        """Debug overlay: viewfinder-style corner brackets per detection."""
        for b in boxes:
            x, y, w, h = b.clamped(frame.shape[1], frame.shape[0]).as_int()
            c = max(10, min(w, h) // 5)
            for (px, py, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
                cv2.line(frame, (px, py), (px + dx * c, py), _ACCENT, 2)
                cv2.line(frame, (px, py), (px, py + dy * c), _ACCENT, 2)
            cv2.putText(frame, tag, (x, max(14, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _ACCENT, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """Release detector resources."""
        for det in (self._face_detector, self._hand_detector):
            if det is not None:
                det.close()
