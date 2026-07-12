"""Unit tests for the vision building blocks (no camera required)."""

from __future__ import annotations

import numpy as np
import pytest

from app.vision.blur_engine import BLUR_CATALOG, BlurEngine
from app.vision.masking import MaskGenerator
from app.vision.smoothing import MultiBoxSmoother
from app.vision.types import Box, BlurType, Region


@pytest.fixture(scope="module")
def frame() -> np.ndarray:
    """Deterministic 640x480 synthetic frame with visible structure."""
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, size=(480, 640, 3), dtype=np.uint8)
    img[100:300, 200:440] = (30, 180, 240)  # a flat block so blur is observable
    return img


@pytest.fixture(scope="module")
def engine() -> BlurEngine:
    return BlurEngine()


class TestBlurEngine:
    @pytest.mark.parametrize("blur_type", list(BlurType))
    @pytest.mark.parametrize("strength", [1, 50, 100])
    def test_every_algorithm_every_strength(self, engine, frame, blur_type, strength):
        out = engine.apply(frame, blur_type, strength)
        assert out.shape == frame.shape
        assert out.dtype == np.uint8
        # A real blur must change the image (identity output = broken kernel).
        assert not np.array_equal(out, frame)

    def test_strength_is_clamped(self, engine, frame):
        assert engine.apply(frame, BlurType.GAUSSIAN, -5).shape == frame.shape
        assert engine.apply(frame, BlurType.GAUSSIAN, 9999).shape == frame.shape

    def test_stronger_means_blurrier(self, engine, frame):
        """Higher strength must remove more high-frequency energy."""
        lo = engine.apply(frame, BlurType.GAUSSIAN, 10).astype(np.int32)
        hi = engine.apply(frame, BlurType.GAUSSIAN, 90).astype(np.int32)
        var_lo = np.var(np.diff(lo, axis=1))
        var_hi = np.var(np.diff(hi, axis=1))
        assert var_hi < var_lo

    def test_catalog_covers_all_types(self):
        assert {item["id"] for item in BLUR_CATALOG} == set(BlurType)


class TestMasking:
    def test_ellipse_mask_range_and_softness(self, frame):
        gen = MaskGenerator(feather_px=31)
        mask = gen.ellipses(frame.shape, [Box(220, 120, 180, 220)])
        assert mask.shape == frame.shape[:2]
        assert mask.dtype == np.float32
        assert 0.0 <= mask.min() and mask.max() <= 1.0
        # Feathering must create intermediate values (soft edges).
        assert ((mask > 0.05) & (mask < 0.95)).sum() > 500

    def test_composite_outside_keeps_center_sharp(self, frame, engine):
        gen = MaskGenerator(feather_px=31)
        box = Box(220, 120, 180, 220)
        mask = gen.ellipses(frame.shape, [box])
        blurred = engine.apply(frame, BlurType.STRONG, 90)
        out = gen.composite(frame, blurred, mask, Region.OUTSIDE)
        cx, cy = int(box.center[0]), int(box.center[1])
        # Centre of the protected ellipse ≈ original; far corner ≈ blurred.
        assert np.abs(out[cy, cx].astype(int) - frame[cy, cx].astype(int)).max() <= 2
        assert np.abs(out[10, 10].astype(int) - blurred[10, 10].astype(int)).max() <= 2

    def test_composite_inside_inverts(self, frame, engine):
        gen = MaskGenerator(feather_px=31)
        box = Box(220, 120, 180, 220)
        mask = gen.ellipses(frame.shape, [box])
        blurred = engine.apply(frame, BlurType.STRONG, 90)
        out = gen.composite(frame, blurred, mask, Region.INSIDE)
        cx, cy = int(box.center[0]), int(box.center[1])
        assert np.abs(out[cy, cx].astype(int) - blurred[cy, cx].astype(int)).max() <= 2
        assert np.abs(out[10, 10].astype(int) - frame[10, 10].astype(int)).max() <= 2

    def test_empty_mask_blurs_everything_outside_mode(self, frame, engine):
        gen = MaskGenerator()
        mask = gen.empty(frame.shape)
        blurred = engine.apply(frame, BlurType.GAUSSIAN, 60)
        out = gen.composite(frame, blurred, mask, Region.OUTSIDE)
        assert np.array_equal(out, blurred)


class TestSmoothing:
    def test_ema_converges_and_holds(self):
        sm = MultiBoxSmoother(alpha=0.5, hold_frames=3)
        target = Box(100, 100, 50, 50)
        out = []
        for _ in range(12):
            out = sm.update([target])
        b = out[0]
        assert abs(b.x - 100) < 1 and abs(b.w - 50) < 1

        # Detection disappears → the track survives hold_frames updates.
        for i in range(3):
            assert len(sm.update([])) == 1, f"track died too early at miss {i + 1}"
        assert len(sm.update([])) == 0  # then it is reaped

    def test_two_targets_stay_two_tracks(self):
        sm = MultiBoxSmoother(alpha=0.5, hold_frames=2)
        a, b = Box(50, 50, 40, 40), Box(400, 300, 40, 40)
        for _ in range(5):
            boxes = sm.update([a, b])
        assert len(boxes) == 2

    def test_union_box(self):
        u = Box.union([Box(10, 20, 30, 30), Box(100, 90, 20, 40)])
        assert (u.x, u.y) == (10, 20)
        assert (u.x + u.w, u.y + u.h) == (120, 130)
