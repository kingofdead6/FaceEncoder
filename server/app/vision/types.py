"""Shared datatypes for the vision pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class Mode(str, Enum):
    """Operating mode of the pipeline."""

    FACE = "face"
    HAND = "hand"


class Region(str, Enum):
    """Which side of the mask receives the blur."""

    OUTSIDE = "outside"  # protected region stays sharp, everything else blurred
    INSIDE = "inside"    # protected region is blurred, everything else sharp


class BlurType(str, Enum):
    """Supported blur algorithms."""

    GAUSSIAN = "gaussian"
    BOX = "box"
    BILATERAL = "bilateral"
    MEDIAN = "median"
    PIXELATE = "pixelate"
    MOSAIC = "mosaic"
    MOTION = "motion"
    STRONG = "strong"
    LIGHT = "light"


@dataclass
class Box:
    """Axis-aligned bounding box in pixel coordinates (floats for smoothing)."""

    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> Tuple[float, float]:
        """Box centre point ``(cx, cy)``."""
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def padded(self, px: float, py: float) -> "Box":
        """Return a copy expanded by ``px``/``py`` * size on each axis."""
        dx, dy = self.w * px, self.h * py
        return Box(self.x - dx, self.y - dy, self.w + 2 * dx, self.h + 2 * dy)

    def clamped(self, width: int, height: int) -> "Box":
        """Return a copy clipped to the frame bounds."""
        x = max(0.0, min(self.x, width - 1.0))
        y = max(0.0, min(self.y, height - 1.0))
        w = max(1.0, min(self.w, width - x))
        h = max(1.0, min(self.h, height - y))
        return Box(x, y, w, h)

    def as_int(self) -> Tuple[int, int, int, int]:
        """Integer ``(x, y, w, h)`` tuple for OpenCV drawing calls."""
        return int(self.x), int(self.y), int(self.w), int(self.h)

    @staticmethod
    def union(boxes: List["Box"]) -> Optional["Box"]:
        """Smallest box containing every box in ``boxes`` (None if empty)."""
        if not boxes:
            return None
        x1 = min(b.x for b in boxes)
        y1 = min(b.y for b in boxes)
        x2 = max(b.x + b.w for b in boxes)
        y2 = max(b.y + b.h for b in boxes)
        return Box(x1, y1, x2 - x1, y2 - y1)


@dataclass
class Detection:
    """One detected object (face or hand)."""

    box: Box
    score: float
    label: str = ""
    landmarks: List[Tuple[float, float]] = field(default_factory=list)
