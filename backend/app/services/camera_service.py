"""
Camera service — capture and processing threads plus a lifecycle manager.

Threading model
---------------
::

    ┌────────────────┐   latest    ┌──────────────────┐   publish    ┌──────────────┐
    │ CaptureThread  │──frame─────▶│ ProcessingThread │──JPEG+stats─▶│ SharedOutput │
    │ (cam.read())   │  (1 slot)   │ (FramePipeline)  │              │  (1 slot)    │
    └────────────────┘             └──────────────────┘              └──────┬───────┘
                                                                            │ read
                                                              WebSocket / MJPEG clients

* The **capture thread** drains the camera as fast as the driver delivers so
  the internal driver buffer never grows (stale-frame latency killer).
* The **processing thread** runs the CV pipeline at ``target_fps``, always on
  the newest frame, and publishes an encoded JPEG.
* Consumers (async WebSocket handlers) only ever read the shared slot — the
  event loop never blocks on OpenCV.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from app.config.settings import Settings, get_settings
from app.services.state import SettingsStore, SharedOutput
from app.utils.logger import get_logger
from app.utils.metrics import RateMeter
from app.vision.pipeline import FramePipeline

log = get_logger("camera")


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or fails mid-stream."""


class _CaptureThread(threading.Thread):
    """Continuously reads frames, keeping only the newest."""

    def __init__(self, cap: cv2.VideoCapture) -> None:
        super().__init__(name="vs-capture", daemon=True)
        self._cap = cap
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._stop = threading.Event()
        self._failures = 0
        self.fps = RateMeter()
        self.error: Optional[str] = None

    def run(self) -> None:
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                self._failures += 1
                if self._failures > 30:
                    self.error = "Camera stopped delivering frames."
                    log.error(self.error)
                    break
                time.sleep(0.02)
                continue
            self._failures = 0
            self.fps.tick()
            with self._lock:
                self._frame = frame

    def latest(self) -> Optional[np.ndarray]:
        """Newest captured frame (or None before first frame)."""
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._stop.set()


class _ProcessingThread(threading.Thread):
    """Runs the vision pipeline at the target FPS and publishes results."""

    def __init__(
        self,
        capture: _CaptureThread,
        store: SettingsStore,
        output: SharedOutput,
        settings: Settings,
        started_at: float,
    ) -> None:
        super().__init__(name="vs-process", daemon=True)
        self._capture = capture
        self._store = store
        self._output = output
        self._settings = settings
        self._stop = threading.Event()
        self._started_at = started_at
        self.frames_total = 0
        self.pipeline: Optional[FramePipeline] = None

    def run(self) -> None:
        # Detectors are built inside this thread — MediaPipe graphs must be
        # created and used on the same thread.
        self.pipeline = FramePipeline(self._settings)
        interval = 1.0 / max(1, self._settings.target_fps)
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self._settings.jpeg_quality]

        while not self._stop.is_set():
            loop_start = time.perf_counter()
            frame = self._capture.latest()
            if frame is None:
                time.sleep(0.01)
                continue

            cfg = self._store.snapshot()
            result = self.pipeline.process(frame, cfg)
            ok, buf = cv2.imencode(".jpg", result.frame, encode_params)
            if ok:
                self.frames_total += 1
                self._output.publish(
                    buf.tobytes(),
                    {
                        "fps": round(result.fps, 1),
                        "capture_fps": round(self._capture.fps.rate, 1),
                        "latency_ms": round(result.latency_ms, 1),
                        "detections": result.detections,
                        "frames_total": self.frames_total,
                        "uptime_s": round(time.time() - self._started_at, 1),
                        "resolution": f"{result.frame.shape[1]}x{result.frame.shape[0]}",
                        "mode": cfg.mode.value,
                        "blur_type": cfg.blur_type.value,
                        "cuda": self.pipeline.cuda_enabled,
                    },
                )

            # FPS cap: sleep off whatever budget this frame did not use.
            elapsed = time.perf_counter() - loop_start
            if (sleep_for := interval - elapsed) > 0:
                time.sleep(sleep_for)

        if self.pipeline is not None:
            self.pipeline.close()

    def stop(self) -> None:
        self._stop.set()


class CameraManager:
    """Owns the camera lifecycle. One instance per process (see module tail)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = threading.Lock()
        self._cap: Optional[cv2.VideoCapture] = None
        self._capture: Optional[_CaptureThread] = None
        self._processor: Optional[_ProcessingThread] = None
        self._started_at: float = 0.0
        self._camera_index: int = self._settings.camera_index
        self.store = SettingsStore()
        self.output = SharedOutput()
        self.ws_clients = 0

    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        """Whether capture + processing threads are alive."""
        return bool(self._processor is not None and self._processor.is_alive())

    def start(self, camera_index: Optional[int] = None) -> Dict[str, Any]:
        """Open the camera and spin up both threads.

        Raises:
            CameraError: if the device cannot be opened or is already running.
        """
        with self._lock:
            if self.running:
                raise CameraError("Camera is already running.")
            index = self._settings.camera_index if camera_index is None else camera_index

            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                raise CameraError(
                    f"Cannot open camera at index {index}. "
                    "Check that a webcam is connected and not used by another app."
                )
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._settings.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._settings.frame_height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep driver buffering minimal

            self._cap = cap
            self._camera_index = index
            self._started_at = time.time()
            self._capture = _CaptureThread(cap)
            self._processor = _ProcessingThread(
                self._capture, self.store, self.output, self._settings, self._started_at
            )
            self._capture.start()
            self._processor.start()
            log.info("Camera %d started (%s)", index, self.resolution_str())
            return self.status()

    def stop(self) -> Dict[str, Any]:
        """Stop threads and release the device. Safe to call when idle."""
        with self._lock:
            if self._processor is not None:
                self._processor.stop()
                self._processor.join(timeout=3)
            if self._capture is not None:
                self._capture.stop()
                self._capture.join(timeout=3)
            if self._cap is not None:
                self._cap.release()
            self._cap = self._capture = self._processor = None
            self.output.clear()
            log.info("Camera stopped")
            return self.status()

    # ------------------------------------------------------------------ #
    def resolution_str(self) -> str:
        """Actual capture resolution as ``WxH`` (empty when idle)."""
        if self._cap is None:
            return ""
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return f"{w}x{h}"

    def status(self) -> Dict[str, Any]:
        """Lifecycle status for ``GET /api/camera/status``."""
        error = self._capture.error if self._capture else None
        return {
            "running": self.running,
            "camera_index": self._camera_index,
            "capture_resolution": self.resolution_str(),
            "uptime_s": round(time.time() - self._started_at, 1) if self.running else 0,
            "error": error,
        }

    def stats(self) -> Dict[str, Any]:
        """Latest pipeline statistics for ``GET /api/stats``."""
        slot = self.output.snapshot()
        base: Dict[str, Any] = {
            "running": self.running,
            "ws_clients": self.ws_clients,
            **slot.stats,
        }
        if not slot.stats:
            base.update(
                {
                    "fps": 0.0,
                    "capture_fps": 0.0,
                    "latency_ms": 0.0,
                    "detections": 0,
                    "frames_total": 0,
                    "uptime_s": 0.0,
                    "resolution": "",
                    "mode": self.store.snapshot().mode.value,
                    "blur_type": self.store.snapshot().blur_type.value,
                    "cuda": False,
                }
            )
        return base

    def frame_and_seq(self) -> Tuple[Optional[bytes], int]:
        """Latest encoded JPEG and its sequence number (for streamers)."""
        slot = self.output.snapshot()
        return slot.jpeg, slot.seq


#: Process-wide singleton used by every route module.
manager = CameraManager()
