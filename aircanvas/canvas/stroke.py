"""
Stroke: the unit of drawing, undo/redo, and (in later phases)
serialization and replay.

Holds canvas-pixel-space points plus style, deliberately independent
of how it ends up rendered to pixels (BrushEngine's job) or where the
points came from (a real hand, developer-mode mouse input, or a
loaded/replayed project).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from aircanvas.canvas.brushes import BrushType

Point = Tuple[float, float]


@dataclass
class Stroke:
    points: List[Point] = field(default_factory=list)
    color: Tuple[int, int, int] = (240, 240, 245)
    size: float = 10.0
    opacity: float = 1.0  # 0..1
    brush_type: BrushType = BrushType.SMOOTH_INK
    created_at: float = field(default_factory=time.time)

    def add_point(self, x: float, y: float) -> None:
        self.points.append((x, y))

    @property
    def is_empty(self) -> bool:
        return len(self.points) == 0

    def bounding_box(self) -> Optional[Tuple[float, float, float, float]]:
        """(min_x, min_y, max_x, max_y) padded by the brush radius, or
        None for an empty stroke. Useful later for dirty-region
        rendering or hit-testing; not required for Phase 3's simple
        full-surface redraws."""
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        pad = self.size / 2
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
