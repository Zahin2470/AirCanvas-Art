"""
Bounded particle system: powers AirCanvas's "Living Ink" signature
effect (see rendering/effects.py) -- fading motes that trail the
cursor and settle out of finished strokes.

Deterministic given an explicit random source: pass a seeded
`random.Random` instance rather than relying on the global `random`
module, so animation-driven visuals can still be unit-tested exactly
(per the project spec: "This should be deterministic enough to
test").

Bounded by design (`max_particles`), per the project's performance
rules -- spawning past the cap silently evicts the oldest particle
rather than growing without limit.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

Color = Tuple[int, int, int]


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Color
    size: float
    age: float = 0.0
    lifetime: float = 0.6  # seconds

    @property
    def alpha(self) -> float:
        """1.0 at birth, fading linearly to 0.0 at end of life."""
        if self.lifetime <= 0:
            return 0.0
        return max(0.0, 1.0 - self.age / self.lifetime)

    @property
    def is_alive(self) -> bool:
        return self.age < self.lifetime


class ParticleSystem:
    def __init__(self, max_particles: int = 220, rng: Optional[random.Random] = None) -> None:
        self.max_particles = max_particles
        self._rng = rng or random.Random()
        self._particles: List[Particle] = []

    @property
    def count(self) -> int:
        return len(self._particles)

    @property
    def particles(self) -> Tuple[Particle, ...]:
        return tuple(self._particles)

    def spawn(
        self,
        x: float,
        y: float,
        color: Color,
        speed: float = 20.0,
        spread: float = math.pi,
        size: float = 3.0,
        lifetime: float = 0.6,
        direction: float = 0.0,
    ) -> Particle:
        """Spawn one particle at (x, y). `direction` is the center
        angle (radians) particles fly off toward; `spread` widens that
        into a random cone (defaults to a full half-circle spread)."""
        angle = direction + self._rng.uniform(-spread / 2, spread / 2)
        speed_jitter = speed * self._rng.uniform(0.5, 1.0)
        particle = Particle(
            x=x, y=y,
            vx=speed_jitter * math.cos(angle), vy=speed_jitter * math.sin(angle),
            color=color, size=size, lifetime=lifetime,
        )
        if len(self._particles) >= self.max_particles:
            self._particles.pop(0)  # drop the oldest -- keep the pool bounded
        self._particles.append(particle)
        return particle

    def update(self, dt: float) -> None:
        for particle in self._particles:
            particle.age += dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
        self._particles = [p for p in self._particles if p.is_alive]

    def clear(self) -> None:
        self._particles.clear()

    def render(self, surface: "pygame.Surface") -> None:
        for particle in self._particles:
            alpha = particle.alpha
            if alpha <= 0.0:
                continue
            radius = max(1, int(round(particle.size * (0.4 + 0.6 * alpha))))  # shrinks slightly as it fades
            stamp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(stamp, (*particle.color, int(255 * alpha)), (radius, radius), radius)
            surface.blit(stamp, (int(particle.x) - radius, int(particle.y) - radius))
