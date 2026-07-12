"""
Blur engine.

Implements nine blur algorithms behind a single ``apply()`` call. Every
algorithm maps a normalised ``strength`` (1..100) onto its own natural
parameter space (kernel size, block size, sigma, ...), so the UI slider feels
consistent across algorithms.

GPU note: if the installed OpenCV build exposes a CUDA device, Gaussian-family
blurs are routed through ``cv2.cuda`` filters; otherwise the engine falls back
to the (heavily optimised, SIMD) CPU implementations transparently.
"""

from __future__ import annotations

from typing import Callable, Dict

import cv2
import numpy as np

from app.utils.logger import get_logger
from app.vision.types import BlurType

log = get_logger("blur")


def _odd(value: int, minimum: int = 3, maximum: int = 255) -> int:
    """Clamp ``value`` to ``[minimum, maximum]`` and force it odd."""
    v = max(minimum, min(int(value), maximum))
    return v if v % 2 == 1 else v + 1


class BlurEngine:
    """Applies a configurable blur to full frames.

    The engine is stateless per-call apart from a cached CUDA availability
    probe, so a single instance can safely be shared by the pipeline.
    """

    def __init__(self) -> None:
        self._cuda = self._probe_cuda()
        self._dispatch: Dict[BlurType, Callable[[np.ndarray, int], np.ndarray]] = {
            BlurType.GAUSSIAN: self._gaussian,
            BlurType.BOX: self._box,
            BlurType.BILATERAL: self._bilateral,
            BlurType.MEDIAN: self._median,
            BlurType.PIXELATE: self._pixelate,
            BlurType.MOSAIC: self._mosaic,
            BlurType.MOTION: self._motion,
            BlurType.STRONG: self._strong,
            BlurType.LIGHT: self._light,
        }
        log.info("BlurEngine ready (CUDA=%s)", self._cuda)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    @property
    def cuda_enabled(self) -> bool:
        """Whether the CUDA fast path is active."""
        return self._cuda

    def apply(self, frame: np.ndarray, blur_type: BlurType, strength: int) -> np.ndarray:
        """Blur ``frame`` (BGR uint8) with ``blur_type`` at ``strength`` (1..100)."""
        strength = int(max(1, min(strength, 100)))
        fn = self._dispatch.get(blur_type, self._gaussian)
        try:
            return fn(frame, strength)
        except cv2.error as exc:  # pragma: no cover - defensive
            log.error("Blur '%s' failed (%s); falling back to Gaussian", blur_type, exc)
            return self._gaussian(frame, strength)

    # ------------------------------------------------------------------ #
    # CUDA                                                               #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _probe_cuda() -> bool:
        """Detect a usable CUDA device on the installed OpenCV build."""
        try:
            return bool(cv2.cuda.getCudaEnabledDeviceCount() > 0)
        except (AttributeError, cv2.error):
            return False

    def _gaussian_gpu(self, frame: np.ndarray, ksize: int) -> np.ndarray:
        """Gaussian blur on the GPU (BGR uint8 in/out)."""
        gpu = cv2.cuda_GpuMat()
        gpu.upload(frame)
        # CUDA Gaussian filters cap kernels at 31x31 — chain passes if needed.
        remaining = ksize
        while remaining > 1:
            k = _odd(min(remaining, 31))
            filt = cv2.cuda.createGaussianFilter(cv2.CV_8UC3, cv2.CV_8UC3, (k, k), 0)
            gpu = filt.apply(gpu)
            remaining -= 30
        return gpu.download()

    # ------------------------------------------------------------------ #
    # Algorithms                                                          #
    # ------------------------------------------------------------------ #
    def _gaussian(self, frame: np.ndarray, s: int) -> np.ndarray:
        """Classic Gaussian blur; kernel grows linearly with strength."""
        k = _odd(3 + s)  # 3..103
        if self._cuda:
            try:
                return self._gaussian_gpu(frame, k)
            except cv2.error:  # pragma: no cover
                pass
        return cv2.GaussianBlur(frame, (k, k), 0)

    @staticmethod
    def _box(frame: np.ndarray, s: int) -> np.ndarray:
        """Uniform (box) average blur."""
        k = max(3, 3 + s)
        return cv2.blur(frame, (k, k))

    @staticmethod
    def _bilateral(frame: np.ndarray, s: int) -> np.ndarray:
        """Edge-preserving bilateral filter (smooths textures, keeps edges).

        Bilateral filtering is O(d^2) per pixel, so it runs on a half-resolution
        copy and is upscaled back — visually indistinguishable for a blur.
        """
        small = cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        sigma = 20 + s * 1.6
        out = cv2.bilateralFilter(small, d=9, sigmaColor=sigma, sigmaSpace=sigma)
        return cv2.resize(out, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)

    @staticmethod
    def _median(frame: np.ndarray, s: int) -> np.ndarray:
        """Median blur (great at destroying fine detail / text)."""
        k = _odd(3 + s // 3, maximum=31)  # medians beyond ~31 are very slow
        return cv2.medianBlur(frame, k)

    @staticmethod
    def _pixelate(frame: np.ndarray, s: int) -> np.ndarray:
        """Fine pixelation: downsample then nearest-neighbour upsample."""
        h, w = frame.shape[:2]
        block = max(2, s // 5)  # 2..20 px blocks
        small = cv2.resize(
            frame, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_LINEAR
        )
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

    @staticmethod
    def _mosaic(frame: np.ndarray, s: int) -> np.ndarray:
        """Coarse mosaic: large averaged tiles with visible grid lines."""
        h, w = frame.shape[:2]
        block = max(8, int(s * 0.6))  # 8..60 px tiles
        small = cv2.resize(
            frame, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA
        )
        out = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        # Subtle darkened grid to give the classic mosaic look.
        out[::block, :] = (out[::block, :] * 0.82).astype(np.uint8)
        out[:, ::block] = (out[:, ::block] * 0.82).astype(np.uint8)
        return out

    @staticmethod
    def _motion(frame: np.ndarray, s: int) -> np.ndarray:
        """Directional motion blur using a rotated line PSF."""
        k = _odd(5 + s // 2, maximum=99)
        kernel = np.zeros((k, k), dtype=np.float32)
        kernel[k // 2, :] = 1.0
        # 25° streak reads more like camera motion than a pure horizontal.
        rot = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), 25, 1.0)
        kernel = cv2.warpAffine(kernel, rot, (k, k))
        kernel /= max(kernel.sum(), 1e-6)
        return cv2.filter2D(frame, -1, kernel)

    def _strong(self, frame: np.ndarray, s: int) -> np.ndarray:
        """Maximum anonymisation: aggressive downscale + wide Gaussian."""
        h, w = frame.shape[:2]
        factor = 8 + s // 10  # 8..18x downscale
        small = cv2.resize(
            frame, (max(1, w // factor), max(1, h // factor)), interpolation=cv2.INTER_AREA
        )
        small = cv2.GaussianBlur(small, (_odd(9), _odd(9)), 0)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _light(self, frame: np.ndarray, s: int) -> np.ndarray:
        """Gentle softening blur (frosted-glass feel)."""
        k = _odd(3 + s // 8, maximum=17)  # 3..15
        return cv2.GaussianBlur(frame, (k, k), 0)


#: Human-readable catalogue served to the frontend by ``GET /api/settings/blur-types``.
BLUR_CATALOG = [
    {"id": BlurType.GAUSSIAN, "label": "Gaussian", "desc": "Smooth optical defocus — the all-round default."},
    {"id": BlurType.BOX, "label": "Box", "desc": "Uniform average blur, slightly boxy highlights."},
    {"id": BlurType.BILATERAL, "label": "Bilateral", "desc": "Smooths detail while preserving strong edges."},
    {"id": BlurType.MEDIAN, "label": "Median", "desc": "Excellent at destroying fine detail and text."},
    {"id": BlurType.PIXELATE, "label": "Pixelate", "desc": "Fine retro pixel blocks."},
    {"id": BlurType.MOSAIC, "label": "Mosaic", "desc": "Coarse censor tiles with a visible grid."},
    {"id": BlurType.MOTION, "label": "Motion", "desc": "Directional streaking, like camera movement."},
    {"id": BlurType.STRONG, "label": "Strong", "desc": "Maximum anonymisation — nothing survives."},
    {"id": BlurType.LIGHT, "label": "Light", "desc": "Subtle frosted-glass softening."},
]
