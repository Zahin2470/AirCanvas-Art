"""
Brush type catalog.

Phase 5 gives every type its own distinct visual character in
canvas/brush_engine.py (Smooth Ink, Neon Glow, Soft Marker, Particle,
Rainbow Flow, Spark), plus the Eraser's background-color reuse of the
Smooth Ink shape.
"""
from __future__ import annotations

from enum import Enum


class BrushType(Enum):
    SMOOTH_INK = "smooth_ink"
    NEON_GLOW = "neon_glow"
    SOFT_MARKER = "soft_marker"
    PARTICLE = "particle"
    RAINBOW_FLOW = "rainbow_flow"
    SPARK = "spark"
    # Not a visual "style" so much as a way of painting -- modeled as
    # a brush type so erasing reuses the same Stroke/history/replay
    # machinery as drawing instead of needing a parallel code path.
    ERASER = "eraser"


# Brush types selectable from the toolbar (everything except the
# eraser, which is triggered by the two-finger gesture instead).
SELECTABLE_BRUSHES = tuple(b for b in BrushType if b != BrushType.ERASER)

# Every brush type now has its own renderer in brush_engine.py.
IMPLEMENTED_BRUSHES = frozenset(BrushType)
