"""
Living Ink: AirCanvas's signature effect (see the project spec's
"Special Feature" section) -- strokes emit fading motes as they're
drawn, the cursor leaves a light particle trail while just pointing,
and finished strokes get a small settling burst.

Wraps a ParticleSystem with the emission *rules* (when and how many
particles to spawn), kept separate from particle physics so the rules
can be tuned and tested independently of rendering.

Deterministic given a fixed call sequence and a seeded ParticleSystem:
emission timing depends only on elapsed time (`dt`) and stroke
geometry the caller passes in, never on wall-clock time, so the same
sequence of update calls always produces the same particle count.
This is a real-time *decoration* only -- it never touches the baked
Stroke pixels in canvas_surface, so it has no bearing on undo/redo or
replay correctness.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from aircanvas.rendering.particles import ParticleSystem

Color = Tuple[int, int, int]

# A direction change sharper than this (radians) between consecutive
# stroke points triggers a small burst -- "rapid direction change ->
# small particle burst".
DIRECTION_CHANGE_BURST_THRESHOLD = math.radians(60)


class LivingInkEmitter:
    def __init__(
        self,
        particle_system: ParticleSystem,
        base_emit_rate: float = 12.0,  # motes/sec at velocity == 0
        velocity_to_rate_scale: float = 6.0,  # additional motes/sec per unit of velocity
        idle_emit_rate: float = 2.0,  # gentle trail while pointing but not drawing
    ) -> None:
        self.particles = particle_system
        self.base_emit_rate = base_emit_rate
        self.velocity_to_rate_scale = velocity_to_rate_scale
        self.idle_emit_rate = idle_emit_rate
        self._emit_accumulator = 0.0
        self._last_point: Optional[Tuple[float, float]] = None
        self._last_direction: Optional[float] = None

    def reset(self) -> None:
        """Call when a stroke ends or the hand is lost, so a new
        stroke doesn't compare its first direction against a stale
        one from a previous, unrelated stroke."""
        self._emit_accumulator = 0.0
        self._last_point = None
        self._last_direction = None

    def on_stroke_point(self, x: float, y: float, color: Color, size: float, velocity: float, dt: float) -> None:
        """Call once per new point added to an active stroke: emits a
        trickle of motes scaled by fingertip speed, plus a small burst
        on a sharp direction change."""
        rate = self.base_emit_rate + self.velocity_to_rate_scale * velocity
        self._emit_at_rate(x, y, color, size, rate, dt)

        if self._last_point is not None:
            direction = math.atan2(y - self._last_point[1], x - self._last_point[0])
            if self._last_direction is not None:
                if abs(_angle_diff(direction, self._last_direction)) >= DIRECTION_CHANGE_BURST_THRESHOLD:
                    self._burst(x, y, color, size, count=5)
            self._last_direction = direction
        self._last_point = (x, y)

    def on_idle_point(self, x: float, y: float, color: Color, size: float, dt: float) -> None:
        """Call once per frame while pointing but not drawing, for a
        light ambient trail ("the cursor leaves fading motes")."""
        self._emit_at_rate(x, y, color, size, self.idle_emit_rate, dt)

    def on_stroke_start(self, x: float, y: float, color: Color, size: float) -> None:
        """Pinch stroke-start effect."""
        self._burst(x, y, color, size, count=6)
        self._last_point = (x, y)
        self._last_direction = None

    def on_stroke_end(self, x: float, y: float, color: Color, size: float) -> None:
        """Release stroke-end effect -- finished strokes "gently
        settle", so this burst is a bit larger/slower than the start."""
        self._burst(x, y, color, size, count=8, speed=12.0, lifetime=0.9)
        self.reset()

    # -- internals --------------------------------------------------

    def _emit_at_rate(self, x: float, y: float, color: Color, size: float, rate: float, dt: float) -> None:
        self._emit_accumulator += max(rate, 0.0) * dt
        while self._emit_accumulator >= 1.0:
            self._emit_accumulator -= 1.0
            self.particles.spawn(x, y, color, speed=18.0, size=max(2.0, size * 0.18), lifetime=0.5)

    def _burst(self, x: float, y: float, color: Color, size: float, count: int, speed: float = 24.0, lifetime: float = 0.6) -> None:
        for _ in range(count):
            self.particles.spawn(x, y, color, speed=speed, size=max(2.0, size * 0.22), lifetime=lifetime)


def _angle_diff(a: float, b: float) -> float:
    """Smallest signed difference between two angles (radians), in
    the range [-pi, pi]."""
    return (a - b + math.pi) % (2 * math.pi) - math.pi
