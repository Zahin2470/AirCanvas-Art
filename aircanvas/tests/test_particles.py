import random

import pygame
import pytest

from aircanvas.rendering.particles import Particle, ParticleSystem


def test_spawn_increases_count():
    system = ParticleSystem(max_particles=10, rng=random.Random(0))
    system.spawn(0, 0, (255, 0, 0))
    assert system.count == 1


def test_spawn_respects_max_particles_by_dropping_oldest():
    system = ParticleSystem(max_particles=3, rng=random.Random(0))
    first = system.spawn(0, 0, (255, 0, 0))
    system.spawn(1, 1, (255, 0, 0))
    system.spawn(2, 2, (255, 0, 0))
    system.spawn(3, 3, (255, 0, 0))  # should evict `first`
    assert system.count == 3
    assert first not in system.particles


def test_update_ages_particles():
    system = ParticleSystem(rng=random.Random(0))
    p = system.spawn(0, 0, (255, 0, 0))
    system.update(dt=0.1)
    assert p.age == pytest.approx(0.1)


def test_update_moves_particles_by_velocity():
    system = ParticleSystem(rng=random.Random(0))
    p = system.spawn(0, 0, (255, 0, 0), speed=10.0, spread=0.0, direction=0.0)
    system.update(dt=1.0)
    assert p.x == pytest.approx(p.vx * 1.0)
    assert p.y == pytest.approx(p.vy * 1.0)


def test_particle_removed_after_lifetime_elapses():
    system = ParticleSystem(rng=random.Random(0))
    system.spawn(0, 0, (255, 0, 0), lifetime=0.2)
    system.update(dt=0.1)
    assert system.count == 1
    system.update(dt=0.2)  # total age 0.3 > lifetime 0.2
    assert system.count == 0


def test_alpha_decreases_linearly_to_zero_at_end_of_life():
    p = Particle(x=0, y=0, vx=0, vy=0, color=(255, 0, 0), size=3, lifetime=1.0)
    assert p.alpha == pytest.approx(1.0)
    p.age = 0.5
    assert p.alpha == pytest.approx(0.5)
    p.age = 1.0
    assert p.alpha == pytest.approx(0.0)
    assert not p.is_alive


def test_same_seed_produces_identical_velocities():
    a = ParticleSystem(rng=random.Random(42))
    b = ParticleSystem(rng=random.Random(42))
    pa = a.spawn(0, 0, (255, 0, 0), speed=10.0)
    pb = b.spawn(0, 0, (255, 0, 0), speed=10.0)
    assert pa.vx == pytest.approx(pb.vx)
    assert pa.vy == pytest.approx(pb.vy)


def test_zero_spread_and_direction_gives_a_fixed_angle():
    system = ParticleSystem(rng=random.Random(0))
    p = system.spawn(0, 0, (255, 0, 0), speed=10.0, spread=0.0, direction=0.0)
    assert p.vy == pytest.approx(0.0, abs=1e-9)
    assert p.vx > 0


def test_clear_removes_all_particles():
    system = ParticleSystem(rng=random.Random(0))
    system.spawn(0, 0, (255, 0, 0))
    system.spawn(1, 1, (255, 0, 0))
    system.clear()
    assert system.count == 0


def test_render_draws_visible_pixels_onto_a_surface():
    system = ParticleSystem(rng=random.Random(0))
    system.spawn(50, 50, (255, 0, 0), size=10, speed=0.0, spread=0.0)
    surface = pygame.Surface((100, 100))
    surface.fill((0, 0, 0))
    system.render(surface)
    assert surface.get_at((50, 50))[:3] != (0, 0, 0)


def test_dead_particle_is_not_rendered():
    system = ParticleSystem(rng=random.Random(0))
    system.spawn(50, 50, (255, 0, 0), size=10, lifetime=0.1)
    system.update(dt=0.2)  # kills it and removes it from the pool
    surface = pygame.Surface((100, 100))
    surface.fill((0, 0, 0))
    system.render(surface)
    assert surface.get_at((50, 50))[:3] == (0, 0, 0)
