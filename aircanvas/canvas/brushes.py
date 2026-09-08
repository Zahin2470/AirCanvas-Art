"""
Brush type catalog.

Phase 3 implements one real brush end to end (SMOOTH_INK) plus the
eraser. The remaining styles are defined here now so the Stroke and
future serialization format are stable, but they currently render
identically to Smooth Ink -- Phase 5 gives each its own distinct
visual character (particles, glow, rainbow gradient, sparks).
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


# Styles brush_engine currently renders with their own logic. Anything
# not in this set falls back to the Smooth Ink stamp-based renderer
# until Phase 5.
IMPLEMENTED_BRUSHES = frozenset({BrushType.SMOOTH_INK, BrushType.ERASER})
