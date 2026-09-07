"""
Pointer smoothing: turns a jittery raw fingertip position into a
stable cursor without adding noticeable lag.

Uses an exponential moving average whose smoothing factor (alpha)
scales with how fast the fingertip is moving: slow movement gets
heavy smoothing (kills jitter while the hand is nearly still), fast
movement gets light smoothing (keeps up with deliberate strokes). A
small deadband ignores movement too tiny to be intentional.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class SmoothingConfig:
    min_alpha: float = 0.15  # heavy smoothing when nearly still
    max_alpha: float = 0.9  # light smoothing during fast movement
    velocity_lower: float = 0.0  # normalized units/sec at which min_alpha applies
    velocity_upper: float = 2.0  # normalized units/sec at which max_alpha applies
    min_movement_threshold: float = 0.0025  # ignore jitter smaller than this (normalized coords)


class PointSmoother:
    """Stateful, per-hand smoothing filter. Create one per tracked hand
    and call `update()` once per frame; `reset()` between strokes or
    when the hand is lost so the next point doesn't lerp in from a
    stale position."""

    def __init__(self, config: Optional[SmoothingConfig] = None) -> None:
        self.config = config or SmoothingConfig()
        self._smoothed: Optional[Tuple[float, float]] = None
        self._last_raw: Optional[Tuple[float, float]] = None
        self.velocity: float = 0.0  # normalized units/sec, exposed for a debug overlay

    def reset(self) -> None:
        self._smoothed = None
        self._last_raw = None
        self.velocity = 0.0

    def update(self, x: float, y: float, dt: float) -> Tuple[float, float]:
        """Feed one new raw (x, y) sample (normalized [0, 1]) and the
        elapsed time in seconds since the previous sample; returns the
        smoothed (x, y)."""
        if self._smoothed is None:
            self._smoothed = (x, y)
            self._last_raw = (x, y)
            self.velocity = 0.0
            return self._smoothed

        dt = max(dt, 1e-6)
        dx = x - self._last_raw[0]
        dy = y - self._last_raw[1]
        self.velocity = math.hypot(dx, dy) / dt
        self._last_raw = (x, y)

        move_dist = math.hypot(x - self._smoothed[0], y - self._smoothed[1])
        if move_dist < self.config.min_movement_threshold:
            return self._smoothed

        alpha = self._velocity_to_alpha(self.velocity)
        sx = self._smoothed[0] + alpha * (x - self._smoothed[0])
        sy = self._smoothed[1] + alpha * (y - self._smoothed[1])
        self._smoothed = (sx, sy)
        return self._smoothed

    def _velocity_to_alpha(self, velocity: float) -> float:
        c = self.config
        if c.velocity_upper <= c.velocity_lower:
            return c.max_alpha
        t = (velocity - c.velocity_lower) / (c.velocity_upper - c.velocity_lower)
        t = min(max(t, 0.0), 1.0)
        return c.min_alpha + t * (c.max_alpha - c.min_alpha)
