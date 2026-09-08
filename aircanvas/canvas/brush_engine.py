"""
Brush engine: turns a stream of canvas-space points into visible ink
on a pygame surface.

Deliberately independent of hand tracking -- it only knows about
canvas-pixel points, colors, sizes, and pygame surfaces, so it works
identically whether points come from a real hand, developer-mode
mouse input, or (in a later phase) stroke replay.

Two rendering paths, for performance (see the project's Engineering
Rules: "do not regenerate the entire canvas texture for every tiny
state change"):

  * `begin_stroke` / `extend_stroke` paint incrementally, stamping
    only the newly added segment onto a persistent canvas surface
    each frame while a stroke is in progress -- O(new ink), not
    O(whole stroke), per frame.
  * `render_full` redraws every stroke from scratch. Used only for
    infrequent, whole-canvas changes: undo, redo, clear, resize, or
    loading a project.

Strokes are rendered as circular "stamps" placed at a fixed spacing
along the path between points, rather than one stamp per raw input
point. That keeps fast strokes solid (many stamps along a long
segment) and slow strokes clean (stamps naturally overlap) without a
special case for either.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Tuple

import pygame

from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.stroke import Point, Stroke

# Stamps are spaced at this fraction of the brush size: small enough
# to read as a continuous line, large enough not to waste time
# stamping redundant, fully-overlapping circles.
STAMP_SPACING_RATIO = 0.28
MIN_STAMP_SPACING_PX = 1.5


class BrushEngine:
    """Owns the in-progress stroke, if any. Stateless with respect to
    finished strokes -- those live in CanvasModel."""

    def __init__(self) -> None:
        self._active: Optional[Stroke] = None

    @property
    def active_stroke(self) -> Optional[Stroke]:
        return self._active

    @property
    def is_drawing(self) -> bool:
        return self._active is not None

    # -- Incremental drawing (called during an active stroke) -------

    def begin_stroke(
        self,
        surface: "pygame.Surface",
        x: float,
        y: float,
        color: Tuple[int, int, int],
        size: float,
        opacity: float = 1.0,
        brush_type: BrushType = BrushType.SMOOTH_INK,
    ) -> Stroke:
        """Start a new stroke at (x, y) and paint its first stamp
        immediately, so even a stroke that never gets a second point
        (a tap) leaves a visible dot."""
        stroke = Stroke(points=[(x, y)], color=color, size=size, opacity=opacity, brush_type=brush_type)
        self._active = stroke
        self._stamp(surface, (x, y), size, color, opacity)
        return stroke

    def extend_stroke(self, surface: "pygame.Surface", x: float, y: float) -> None:
        """Add a new raw point to the in-progress stroke and paint
        only the new segment. Safe to call with no active stroke (a
        no-op) so callers don't need to guard every call site."""
        if self._active is None:
            return
        prev = self._active.points[-1]
        self._active.add_point(x, y)
        self._stamp_segment(surface, prev, (x, y), self._active.size, self._active.color, self._active.opacity)

    def end_stroke(self) -> Optional[Stroke]:
        """Finish the in-progress stroke and return it for the caller
        to hand to CanvasModel.add_stroke -- or None if there wasn't
        one, or it never received a point."""
        stroke = self._active
        self._active = None
        if stroke is None or stroke.is_empty:
            return None
        return stroke

    def cancel_stroke(self) -> None:
        """Discard the in-progress stroke without returning it (e.g.
        the hand was lost mid-draw)."""
        self._active = None

    # -- Full redraw (undo/redo/clear/resize/load) -------------------

    def render_full(
        self,
        surface: "pygame.Surface",
        strokes: Iterable[Stroke],
        background_color: Tuple[int, int, int],
    ) -> None:
        """Redraw the entire canvas from scratch given the full list
        of strokes, in order. Infrequent by design -- see module
        docstring."""
        surface.fill(background_color)
        for stroke in strokes:
            self._render_complete_stroke(surface, stroke)

    def _render_complete_stroke(self, surface: "pygame.Surface", stroke: Stroke) -> None:
        if not stroke.points:
            return
        if len(stroke.points) == 1:
            self._stamp(surface, stroke.points[0], stroke.size, stroke.color, stroke.opacity)
            return
        for start, end in zip(stroke.points, stroke.points[1:]):
            self._stamp_segment(surface, start, end, stroke.size, stroke.color, stroke.opacity)

    # -- Low-level stamping ------------------------------------------

    def _stamp_segment(
        self,
        surface: "pygame.Surface",
        start: Point,
        end: Point,
        size: float,
        color: Tuple[int, int, int],
        opacity: float,
    ) -> None:
        spacing = max(size * STAMP_SPACING_RATIO, MIN_STAMP_SPACING_PX)
        x0, y0 = start
        x1, y1 = end
        distance = math.hypot(x1 - x0, y1 - y0)
        if distance <= 0:
            self._stamp(surface, end, size, color, opacity)
            return
        steps = max(int(distance / spacing), 1)
        # Start at 1, not 0: the segment's start point was already
        # stamped as the previous segment's end (or the stroke's
        # first point), so this avoids double-stamping it.
        for i in range(1, steps + 1):
            t = i / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            self._stamp(surface, (x, y), size, color, opacity)

    def _stamp(
        self,
        surface: "pygame.Surface",
        pos: Point,
        size: float,
        color: Tuple[int, int, int],
        opacity: float,
    ) -> None:
        radius = max(int(round(size / 2)), 1)
        x, y = int(round(pos[0])), int(round(pos[1]))
        if opacity >= 0.999:
            pygame.draw.circle(surface, color, (x, y), radius)
            return
        # Semi-transparent stamp: draw onto a small per-pixel-alpha
        # surface, then blit it, rather than drawing straight onto a
        # non-alpha surface with a blend mode that would darken the
        # whole surface instead of just this circle.
        stamp_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        alpha = max(0, min(255, int(round(opacity * 255))))
        pygame.draw.circle(stamp_surface, (*color, alpha), (radius, radius), radius)
        surface.blit(stamp_surface, (x - radius, y - radius))
