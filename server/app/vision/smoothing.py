"""
Temporal smoothing of detection boxes.

Raw per-frame detections jitter by a few pixels and occasionally drop out for
a frame or two during fast motion. ``MultiBoxSmoother`` fixes both problems:

* **EMA smoothing** — each tracked box is an exponential moving average of the
  raw boxes assigned to it, which removes jitter while staying responsive.
* **Hold on miss** — when a track receives no detection this frame it survives
  for ``hold_frames`` frames at its last position, bridging detector misses so
  the mask never flickers.

Assignment uses greedy nearest-centre matching, which is ideal at the small
object counts a webcam scene produces (a Hungarian solver would be overkill).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Dict, List

from app.vision.types import Box

_ids = count(1)


@dataclass
class _Track:
    box: Box
    missed: int = 0
    track_id: int = field(default_factory=lambda: next(_ids))


class MultiBoxSmoother:
    """Smooths a variable-size set of boxes across frames."""

    def __init__(self, alpha: float = 0.45, hold_frames: int = 8, match_dist: float = 160.0) -> None:
        """
        Args:
            alpha: EMA coefficient — 1.0 means no smoothing, small values lag.
            hold_frames: how many frames a lost track is kept alive.
            match_dist: max centre distance (px) for a detection→track match.
        """
        self.alpha = alpha
        self.hold_frames = hold_frames
        self.match_dist = match_dist
        self._tracks: Dict[int, _Track] = {}

    def update(self, boxes: List[Box]) -> List[Box]:
        """Feed the raw boxes for this frame; get the stabilised set back."""
        unmatched = list(boxes)

        # 1) Match each existing track to its nearest raw detection.
        for track in self._tracks.values():
            best, best_d = None, self.match_dist
            tcx, tcy = track.box.center
            for cand in unmatched:
                ccx, ccy = cand.center
                d = ((tcx - ccx) ** 2 + (tcy - ccy) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = cand, d
            if best is not None:
                unmatched.remove(best)
                a = self.alpha
                b = track.box
                track.box = Box(
                    x=(1 - a) * b.x + a * best.x,
                    y=(1 - a) * b.y + a * best.y,
                    w=(1 - a) * b.w + a * best.w,
                    h=(1 - a) * b.h + a * best.h,
                )
                track.missed = 0
            else:
                track.missed += 1

        # 2) Spawn tracks for detections that matched nothing.
        for cand in unmatched:
            t = _Track(box=cand)
            self._tracks[t.track_id] = t

        # 3) Reap tracks that have been missing too long.
        dead = [tid for tid, t in self._tracks.items() if t.missed > self.hold_frames]
        for tid in dead:
            del self._tracks[tid]

        return [t.box for t in self._tracks.values()]

    def reset(self) -> None:
        """Drop all tracks (called when the mode changes or camera restarts)."""
        self._tracks.clear()
