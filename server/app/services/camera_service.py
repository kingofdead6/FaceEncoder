"""Browser-frame processing service.

The browser owns camera access. It sends JPEG frames over ``/ws/stream`` and
this service only decodes, processes, and encodes those frames; it never opens
an operating-system video device.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

import cv2
import numpy as np

from app.config.settings import get_settings
from app.services.state import SettingsStore
from app.utils.metrics import RateMeter
from app.vision.pipeline import FramePipeline


class FrameError(ValueError):
    """Raised when a WebSocket payload is not a decodable image frame."""


class CameraManager:
    """Shared manager for client-supplied frame processing only.

    The name is retained so the settings and monitoring routes stay small.
    This class deliberately has no ``VideoCapture`` or camera lifecycle
    methods: camera permissions and device selection belong to the browser.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self.store = SettingsStore()
        self._pipeline: FramePipeline | None = None
        self._started_at = 0.0
        self._frames_total = 0
        self._upload_fps = RateMeter()
        self._last_stats: Dict[str, Any] = {}
        self.ws_clients = 0

    @property
    def running(self) -> bool:
        """Whether at least one browser is currently streaming frames."""
        return self.ws_clients > 0

    def connect(self) -> None:
        self.ws_clients += 1
        if self._started_at == 0.0:
            self._started_at = time.time()

    def disconnect(self) -> None:
        self.ws_clients = max(0, self.ws_clients - 1)

    def process_jpeg(self, jpeg: bytes) -> Tuple[bytes, Dict[str, Any]]:
        """Process one browser-supplied JPEG and return JPEG plus telemetry."""
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            raise FrameError("Received an invalid JPEG frame.")

        if self._pipeline is None:
            self._pipeline = FramePipeline(self._settings)

        cfg = self.store.snapshot()
        result = self._pipeline.process(frame, cfg)
        ok, output = cv2.imencode(
            ".jpg", result.frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._settings.jpeg_quality]
        )
        if not ok:
            raise FrameError("Could not encode the processed frame.")

        self._frames_total += 1
        self._upload_fps.tick()
        self._last_stats = {
            "running": self.running,
            "ws_clients": self.ws_clients,
            "fps": round(result.fps, 1),
            "capture_fps": round(self._upload_fps.rate, 1),
            "latency_ms": round(result.latency_ms, 1),
            "detections": result.detections,
            "frames_total": self._frames_total,
            "uptime_s": round(time.time() - self._started_at, 1),
            "resolution": f"{result.frame.shape[1]}x{result.frame.shape[0]}",
            "mode": cfg.mode.value,
            "blur_type": cfg.blur_type.value,
            "cuda": self._pipeline.cuda_enabled,
        }
        return output.tobytes(), self._last_stats

    def stats(self) -> Dict[str, Any]:
        """Latest processing statistics, suitable for polling."""
        if self._last_stats:
            return {**self._last_stats, "running": self.running, "ws_clients": self.ws_clients}
        cfg = self.store.snapshot()
        return {
            "running": self.running,
            "ws_clients": self.ws_clients,
            "fps": 0.0,
            "capture_fps": 0.0,
            "latency_ms": 0.0,
            "detections": 0,
            "frames_total": 0,
            "uptime_s": 0.0,
            "resolution": "",
            "mode": cfg.mode.value,
            "blur_type": cfg.blur_type.value,
            "cuda": False,
        }

    def close(self) -> None:
        """Release processor resources during application shutdown."""
        if self._pipeline is not None:
            self._pipeline.close()
            self._pipeline = None


manager = CameraManager()
