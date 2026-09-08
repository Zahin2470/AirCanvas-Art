"""
Eraser support.

Modeled as an ordinary Stroke painted in the canvas's background
color (brush_type=BrushType.ERASER, opacity forced to 1.0 so it fully
covers ink underneath rather than partially blending with it).
Reusing the normal stroke/brush-engine machinery means erasing gets
undo/redo and (in later phases) replay and serialization for free --
and because strokes replay in the order they were created, an eraser
stroke only ever affects ink drawn *before* it, never anything drawn
afterward, so it can't "destroy unrelated canvas content".
"""
from __future__ import annotations

from typing import Tuple

from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.stroke import Stroke


def create_eraser_stroke(x: float, y: float, background_color: Tuple[int, int, int], size: float) -> Stroke:
    """Start a new eraser stroke at (x, y)."""
    return Stroke(points=[(x, y)], color=background_color, size=size, opacity=1.0, brush_type=BrushType.ERASER)


def stamp_covers_point(stamp_center: Tuple[float, float], radius: float, point: Tuple[float, float]) -> bool:
    """Geometry helper: does a circular stamp at `stamp_center` with
    the given `radius` cover `point`? Used by tests, and by any
    future hit-testing that needs to know an eraser's exact footprint
    (e.g. deciding whether a UI element under it should react)."""
    dx = point[0] - stamp_center[0]
    dy = point[1] - stamp_center[1]
    return (dx * dx + dy * dy) <= radius * radius
