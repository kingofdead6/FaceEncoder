"""
Shared, thread-safe application state.

Two objects cross thread boundaries and are therefore centralised here:

* :class:`SettingsStore` — user-tunable pipeline settings, written by REST
  handlers (event-loop thread) and read by the processing thread.
* :class:`SharedOutput` — the latest encoded frame + statistics, written by
  the processing thread and read by every WebSocket / MJPEG client.

Both use a plain ``threading.Lock`` with tiny critical sections; contention is
negligible at these rates.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

from app.vision.types import BlurType, Mode, Region


@dataclass(frozen=True)
class PipelineSettings:
    """Immutable snapshot of the user-controlled pipeline settings."""

    mode: Mode = Mode.FACE
    blur_type: BlurType = BlurType.GAUSSIAN
    strength: int = 55
    region: Region = Region.OUTSIDE
    show_detections: bool = False
    mirror: bool = True

    def as_dict(self) -> Dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "mode": self.mode.value,
            "blur_type": self.blur_type.value,
            "strength": self.strength,
            "region": self.region.value,
            "show_detections": self.show_detections,
            "mirror": self.mirror,
        }


class SettingsStore:
    """Lock-guarded holder of the current :class:`PipelineSettings`."""

    def __init__(self, initial: Optional[PipelineSettings] = None) -> None:
        self._lock = threading.Lock()
        self._settings = initial or PipelineSettings()

    def snapshot(self) -> PipelineSettings:
        """Return the current immutable settings snapshot."""
        with self._lock:
            return self._settings

    def update(self, **changes: Any) -> PipelineSettings:
        """Apply partial changes atomically and return the new snapshot."""
        with self._lock:
            self._settings = replace(self._settings, **changes)
            return self._settings


@dataclass
class _OutputSlot:
    jpeg: Optional[bytes] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    timestamp: float = 0.0


class SharedOutput:
    """Single-slot 'latest frame wins' buffer.

    A queue would add latency (old frames pile up); a single slot means every
    consumer always streams the newest frame — exactly what live video wants.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slot = _OutputSlot()

    def publish(self, jpeg: bytes, stats: Dict[str, Any]) -> None:
        """Store a newly encoded frame (processing thread only)."""
        with self._lock:
            self._slot.jpeg = jpeg
            self._slot.stats = stats
            self._slot.seq += 1
            self._slot.timestamp = time.time()

    def snapshot(self) -> _OutputSlot:
        """Return a shallow copy of the current slot (any consumer)."""
        with self._lock:
            return _OutputSlot(
                jpeg=self._slot.jpeg,
                stats=dict(self._slot.stats),
                seq=self._slot.seq,
                timestamp=self._slot.timestamp,
            )

    def clear(self) -> None:
        """Reset the slot (camera stopped)."""
        with self._lock:
            self._slot = _OutputSlot()
