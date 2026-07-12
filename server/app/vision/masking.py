"""
Mask generation and compositing.

A mask is a single-channel ``float32`` image in ``[0, 1]`` where ``1`` marks
the *protected* region (the part the user wants to keep or hide, depending on
the region setting). Feathering the mask with a Gaussian creates the soft
edge between the sharp and blurred areas.
"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np

from app.vision.types import Box, Region


def _odd(value: int) -> int:
    v = max(1, int(value))
    return v if v % 2 == 1 else v + 1


class MaskGenerator:
    """Builds feathered masks from detection boxes."""

    def __init__(self, feather_px: int = 41) -> None:
        self.feather_px = feather_px

    # ------------------------------------------------------------------ #
    # Mask builders                                                      #
    # ------------------------------------------------------------------ #
    def ellipses(self, shape: tuple, boxes: List[Box]) -> np.ndarray:
        """Elliptical mask, one ellipse per box (used for faces).

        Ellipses hug the head shape far better than rectangles, so the
        preserved region does not include big background corners.
        """
        h, w = shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for b in boxes:
            bc = b.clamped(w, h)
            cx, cy = bc.center
            axes = (max(2, int(bc.w / 2)), max(2, int(bc.h / 2)))
            cv2.ellipse(mask, (int(cx), int(cy)), axes, 0, 0, 360, 255, thickness=-1)
        return self._feather(mask)

    def rectangle(self, shape: tuple, box: Box, corner_radius_ratio: float = 0.12) -> np.ndarray:
        """Rounded-rectangle mask (used for the hand region)."""
        h, w = shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        bc = box.clamped(w, h)
        x, y, bw, bh = bc.as_int()
        r = max(1, int(min(bw, bh) * corner_radius_ratio))
        # Rounded rect = two overlapping rects + four corner circles.
        cv2.rectangle(mask, (x + r, y), (x + bw - r, y + bh), 255, -1)
        cv2.rectangle(mask, (x, y + r), (x + bw, y + bh - r), 255, -1)
        for cx, cy in ((x + r, y + r), (x + bw - r, y + r), (x + r, y + bh - r), (x + bw - r, y + bh - r)):
            cv2.circle(mask, (cx, cy), r, 255, -1)
        return self._feather(mask)

    def empty(self, shape: tuple) -> np.ndarray:
        """All-zero mask (no protected region)."""
        h, w = shape[:2]
        return np.zeros((h, w), dtype=np.float32)

    def _feather(self, mask_u8: np.ndarray) -> np.ndarray:
        """Feather a binary uint8 mask into a float32 soft mask."""
        k = _odd(self.feather_px)
        soft = cv2.GaussianBlur(mask_u8, (k, k), 0)
        return soft.astype(np.float32) / 255.0

    # ------------------------------------------------------------------ #
    # Compositing                                                        #
    # ------------------------------------------------------------------ #
    @staticmethod
    def composite(
        frame: np.ndarray,
        blurred: np.ndarray,
        mask: np.ndarray,
        region: Region,
    ) -> np.ndarray:
        """Blend ``frame`` and ``blurred`` through ``mask``.

        * ``Region.OUTSIDE`` — mask==1 stays sharp, the rest is blurred
          (Face Privacy default: faces sharp, background blurred).
        * ``Region.INSIDE``  — mask==1 is blurred, the rest stays sharp
          (classic anonymisation of the detected region).
        """
        m = mask if region == Region.OUTSIDE else 1.0 - mask
        m3 = cv2.merge([m, m, m])
        out = frame.astype(np.float32) * m3 + blurred.astype(np.float32) * (1.0 - m3)
        return out.astype(np.uint8)
