"""Lightweight performance metering (FPS + latency) with EMA smoothing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateMeter:
    """Exponentially-smoothed events-per-second meter.

    Call :meth:`tick` once per event (e.g. per processed frame). The reported
    rate is smoothed with an EMA so the UI counter does not flicker.
    """

    alpha: float = 0.15
    _last: float | None = field(default=None, init=False)
    _rate: float = field(default=0.0, init=False)

    def tick(self) -> float:
        """Register one event and return the smoothed rate (Hz)."""
        now = time.perf_counter()
        if self._last is not None:
            dt = now - self._last
            if dt > 0:
                inst = 1.0 / dt
                self._rate = (
                    inst if self._rate == 0.0 else (1 - self.alpha) * self._rate + self.alpha * inst
                )
        self._last = now
        return self._rate

    @property
    def rate(self) -> float:
        """Current smoothed rate in events per second."""
        return self._rate

    def reset(self) -> None:
        """Clear meter state."""
        self._last = None
        self._rate = 0.0


@dataclass
class LatencyMeter:
    """EMA-smoothed duration meter (milliseconds)."""

    alpha: float = 0.2
    _ms: float = field(default=0.0, init=False)

    def observe(self, seconds: float) -> float:
        """Record one duration expressed in seconds; returns smoothed ms."""
        ms = seconds * 1000.0
        self._ms = ms if self._ms == 0.0 else (1 - self.alpha) * self._ms + self.alpha * ms
        return self._ms

    @property
    def ms(self) -> float:
        """Current smoothed latency in milliseconds."""
        return self._ms

    def reset(self) -> None:
        """Clear meter state."""
        self._ms = 0.0
