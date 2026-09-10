"""
Brush engine: turns a stream of canvas-space points into visible ink
on a pygame surface, with a distinct rendering routine per BrushType.

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

Each brush type's *baked* appearance (what render_full reproduces) is
a pure function of the stroke's own stored data -- point positions,
size, color, and their order -- using position-derived deterministic
jitter (see `_position_rng`) rather than a live random stream, so the
exact same Stroke always redraws pixel-identically on every undo/redo
(and, in a later phase, replay). Both rendering paths walk the same
segment-stamping code, so a live-drawn stroke and its later replay
land on identical stamp positions -- this matters for RAINBOW_FLOW in
particular, whose color depends on cumulative distance along the
stroke.

Some types additionally emit real-time ParticleSystem motes while
actively being drawn (see aircanvas/rendering/effects.py) as a purely
decorative, non-baked flourish layered on top of this deterministic
base -- that lives in app.py, not here, since it needs the live
per-frame velocity/timing this module doesn't track.
"""
from __future__ import annotations

import colorsys
import math
import random
import time
from typing import Dict, Iterable, Optional, Tuple

import pygame

from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.stroke import Point, Stroke

STAMP_SPACING_RATIO = 0.28
SOFT_MARKER_SPACING_RATIO = 0.16  # denser stamps -> smoother, softer edge
SPARK_SPACING_RATIO = 0.9  # sparser stamps -> a spikier, broken line
MIN_STAMP_SPACING_PX = 1.5

RAINBOW_WAVELENGTH_PX = 320.0  # stroke length (px) for one full hue cycle

# "Sustained drawing -> subtle glow accumulation": ink opacity nudges
# up slightly (capped) the further a stroke has traveled.
GLOW_ACCUMULATION_DISTANCE_PX = 3000.0
GLOW_ACCUMULATION_MAX = 0.12


def _position_rng(x: float, y: float, salt: int) -> random.Random:
    """Deterministic pseudo-randomness keyed only by stamp position
    (rounded to damp float noise): the same point jitters the same
    way every time it's rendered, with no external state to track."""
    seed = hash((round(x, 1), round(y, 1), salt))
    return random.Random(seed)


def _hue_shift_color(base_color: Tuple[int, int, int], distance_along_stroke: float) -> Tuple[int, int, int]:
    hue = (distance_along_stroke / RAINBOW_WAVELENGTH_PX) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _lighten(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(int(c + (255 - c) * amount) for c in color)


class BrushEngine:
    """Owns the in-progress stroke, if any. Stateless with respect to
    finished strokes -- those live in CanvasModel."""

    def __init__(self) -> None:
        self._active: Optional[Stroke] = None
        self._active_distance: float = 0.0
        self._active_start_time: float = 0.0

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
        now: Optional[float] = None,
    ) -> Stroke:
        """Start a new stroke at (x, y) and paint its first stamp
        immediately, so even a stroke that never gets a second point
        (a tap) leaves a visible mark.

        `now` (seconds, e.g. from time.monotonic()) lets callers pin
        down the stroke's start time for deterministic tests; real
        drawing can leave it as None to use the wall clock. This time
        is only used to derive `point_times` for replay pacing -- it
        has no effect on the stroke's baked appearance.
        """
        stroke = Stroke(points=[(x, y)], point_times=[0.0], color=color, size=size, opacity=opacity, brush_type=brush_type)
        self._active = stroke
        self._active_distance = 0.0
        self._active_start_time = now if now is not None else time.monotonic()
        self._place_stamp(surface, (x, y), stroke, distance_along=0.0)
        return stroke

    def extend_stroke(self, surface: "pygame.Surface", x: float, y: float, now: Optional[float] = None) -> None:
        """Add a new raw point to the in-progress stroke and paint
        only the new segment. Safe to call with no active stroke (a
        no-op) so callers don't need to guard every call site."""
        if self._active is None:
            return
        now = now if now is not None else time.monotonic()
        elapsed = max(0.0, now - self._active_start_time)
        prev = self._active.points[-1]
        self._active.add_point(x, y, t=elapsed)
        self._active_distance = self._stamp_segment(surface, prev, (x, y), self._active, self._active_distance)

    def end_stroke(self) -> Optional[Stroke]:
        """Finish the in-progress stroke and return it for the caller
        to hand to CanvasModel.add_stroke -- or None if there wasn't
        one, or it never received a point."""
        stroke = self._active
        self._active = None
        self._active_distance = 0.0
        if stroke is None or stroke.is_empty:
            return None
        return stroke

    def cancel_stroke(self) -> None:
        """Discard the in-progress stroke without returning it (e.g.
        the hand was lost mid-draw)."""
        self._active = None
        self._active_distance = 0.0

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
            self.render_stroke(surface, stroke)

    def render_stroke(self, surface: "pygame.Surface", stroke: Stroke) -> None:
        """Render one (possibly partial) stroke onto `surface` without
        touching anything else already there. Public entry point used
        by render_full above and by canvas/replay.py, which renders
        strokes one at a time with a truncated point list."""
        self._render_complete_stroke(surface, stroke)

    def _render_complete_stroke(self, surface: "pygame.Surface", stroke: Stroke) -> None:
        if not stroke.points:
            return
        self._place_stamp(surface, stroke.points[0], stroke, distance_along=0.0)
        if len(stroke.points) == 1:
            return
        distance = 0.0
        for start, end in zip(stroke.points, stroke.points[1:]):
            distance = self._stamp_segment(surface, start, end, stroke, distance)

    # -- Segment/stamp placement --------------------------------------

    def _stamp_segment(
        self, surface: "pygame.Surface", start: Point, end: Point, stroke: Stroke, distance_so_far: float
    ) -> float:
        spacing = self._spacing_for(stroke)
        x0, y0 = start
        x1, y1 = end
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len <= 0:
            return distance_so_far
        steps = max(int(seg_len / spacing), 1)
        # Start at 1: the segment's start point was already stamped as
        # the previous segment's end (or the stroke's first point).
        for i in range(1, steps + 1):
            t = i / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            distance_so_far += seg_len / steps
            self._place_stamp(surface, (x, y), stroke, distance_along=distance_so_far)
        return distance_so_far

    def _spacing_for(self, stroke: Stroke) -> float:
        if stroke.brush_type == BrushType.SOFT_MARKER:
            ratio = SOFT_MARKER_SPACING_RATIO
        elif stroke.brush_type == BrushType.SPARK:
            ratio = SPARK_SPACING_RATIO
        else:
            ratio = STAMP_SPACING_RATIO
        return max(stroke.size * ratio, MIN_STAMP_SPACING_PX)

    def _place_stamp(self, surface: "pygame.Surface", pos: Point, stroke: Stroke, distance_along: float) -> None:
        method_name = _BRUSH_RENDER_METHODS.get(stroke.brush_type, "_stamp_smooth_ink")
        getattr(self, method_name)(surface, pos, stroke, distance_along)

    # -- Per-brush-type stamps (see _BRUSH_RENDERERS below) -------------

    def _stamp_smooth_ink(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        opacity = _with_glow_accumulation(stroke.opacity, distance_along)
        _draw_circle(surface, pos, stroke.size / 2, stroke.color, opacity)

    def _stamp_neon_glow(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        core_radius = stroke.size / 2
        halo_radius = core_radius * 2.4
        opacity = _with_glow_accumulation(stroke.opacity, distance_along)
        # Two low-alpha rings underneath approximate a soft glow
        # cheaply (no real blur) -- see Visual Style's "restrained
        # bloom-like effects" guidance.
        _draw_circle(surface, pos, halo_radius, stroke.color, opacity * 0.16)
        _draw_circle(surface, pos, halo_radius * 0.65, stroke.color, opacity * 0.28)
        core_color = _lighten(stroke.color, 0.35)  # bright, slightly-hot core
        _draw_circle(surface, pos, core_radius, core_color, opacity)

    def _stamp_soft_marker(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        radius = stroke.size / 2
        rings = 4
        for i in range(rings, 0, -1):
            r = radius * (i / rings)
            alpha = stroke.opacity * 0.55 * (1.0 - (i - 1) / rings)
            _draw_circle(surface, pos, r, stroke.color, alpha)

    def _stamp_particle(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        # Baked appearance: a small scattered cluster instead of one
        # solid disc -- deterministic per position (_position_rng), so
        # replay reproduces the exact same scatter every time.
        radius = stroke.size / 2
        rng = _position_rng(pos[0], pos[1], salt=1)
        count = max(2, int(radius / 2))
        for _ in range(count):
            angle = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(0, radius)
            speck_pos = (pos[0] + dist * math.cos(angle), pos[1] + dist * math.sin(angle))
            speck_size = max(1.0, radius * rng.uniform(0.15, 0.35))
            _draw_circle(surface, speck_pos, speck_size, stroke.color, stroke.opacity * rng.uniform(0.6, 1.0))

    def _stamp_rainbow_flow(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        color = _hue_shift_color(stroke.color, distance_along)
        _draw_circle(surface, pos, stroke.size / 2, color, stroke.opacity)

    def _stamp_spark(self, surface, pos: Point, stroke: Stroke, distance_along: float) -> None:
        rng = _position_rng(pos[0], pos[1], salt=2)
        radius = max(1.0, stroke.size * rng.uniform(0.25, 0.45))
        color = _lighten(stroke.color, 0.4)
        jitter = stroke.size * 0.3
        jittered_pos = (pos[0] + rng.uniform(-jitter, jitter), pos[1] + rng.uniform(-jitter, jitter))
        _draw_circle(surface, jittered_pos, radius, color, stroke.opacity)


def _with_glow_accumulation(base_opacity: float, distance_along: float) -> float:
    boost = min(distance_along / GLOW_ACCUMULATION_DISTANCE_PX, 1.0) * GLOW_ACCUMULATION_MAX
    return min(base_opacity + boost, 1.0)


def _draw_circle(surface: "pygame.Surface", pos: Point, radius: float, color: Tuple[int, int, int], opacity: float) -> None:
    radius = max(int(round(radius)), 1)
    x, y = int(round(pos[0])), int(round(pos[1]))
    opacity = max(0.0, min(1.0, opacity))
    if opacity <= 0.0:
        return
    if opacity >= 0.999:
        pygame.draw.circle(surface, color, (x, y), radius)
        return
    stamp_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    alpha = int(round(opacity * 255))
    pygame.draw.circle(stamp_surface, (*color, alpha), (radius, radius), radius)
    surface.blit(stamp_surface, (x - radius, y - radius))


_BRUSH_RENDER_METHODS: Dict[BrushType, str] = {
    BrushType.SMOOTH_INK: "_stamp_smooth_ink",
    BrushType.ERASER: "_stamp_smooth_ink",  # same shape, background color (see eraser.py)
    BrushType.NEON_GLOW: "_stamp_neon_glow",
    BrushType.SOFT_MARKER: "_stamp_soft_marker",
    BrushType.PARTICLE: "_stamp_particle",
    BrushType.RAINBOW_FLOW: "_stamp_rainbow_flow",
    BrushType.SPARK: "_stamp_spark",
}
