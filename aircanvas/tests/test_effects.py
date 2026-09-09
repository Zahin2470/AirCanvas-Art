import random

from aircanvas.rendering.effects import LivingInkEmitter
from aircanvas.rendering.particles import ParticleSystem


def _emitter(**kwargs):
    system = ParticleSystem(max_particles=1000, rng=random.Random(0))
    return LivingInkEmitter(system, **kwargs), system


def test_on_stroke_point_emits_particles_proportional_to_rate_and_dt():
    emitter, system = _emitter(base_emit_rate=10.0, velocity_to_rate_scale=0.0)
    emitter.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=1.0)
    assert system.count == 10  # 10 motes/sec * 1.0s


def test_higher_velocity_emits_more_particles():
    slow, slow_system = _emitter(base_emit_rate=5.0, velocity_to_rate_scale=1.0)
    fast, fast_system = _emitter(base_emit_rate=5.0, velocity_to_rate_scale=1.0)
    slow.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=1.0)
    fast.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=20.0, dt=1.0)
    assert fast_system.count > slow_system.count


def test_idle_point_uses_idle_rate_not_base_rate():
    emitter, system = _emitter(base_emit_rate=100.0, idle_emit_rate=2.0)
    emitter.on_idle_point(0, 0, (255, 0, 0), size=10, dt=1.0)
    assert system.count == 2


def test_sharp_direction_change_triggers_a_burst():
    emitter, system = _emitter(base_emit_rate=0.0, velocity_to_rate_scale=0.0)
    emitter.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.on_stroke_point(10, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)  # moving right
    before = system.count
    emitter.on_stroke_point(10, -10, (255, 0, 0), size=10, velocity=0.0, dt=0.0)  # sharp turn
    assert system.count > before


def test_gentle_curve_does_not_trigger_a_burst():
    emitter, system = _emitter(base_emit_rate=0.0, velocity_to_rate_scale=0.0)
    emitter.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.on_stroke_point(10, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    before = system.count
    emitter.on_stroke_point(20, 1, (255, 0, 0), size=10, velocity=0.0, dt=0.0)  # nearly straight
    assert system.count == before


def test_stroke_start_and_end_each_spawn_a_fixed_burst():
    emitter, system = _emitter(base_emit_rate=0.0)
    emitter.on_stroke_start(0, 0, (255, 0, 0), size=10)
    after_start = system.count
    assert after_start > 0
    emitter.on_stroke_end(0, 0, (255, 0, 0), size=10)
    assert system.count > after_start


def test_reset_clears_direction_tracking_so_next_point_does_not_burst():
    emitter, system = _emitter(base_emit_rate=0.0, velocity_to_rate_scale=0.0)
    emitter.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.on_stroke_point(10, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.reset()
    before = system.count
    emitter.on_stroke_point(10, -10, (255, 0, 0), size=10, velocity=0.0, dt=0.0)  # would've been a sharp turn
    assert system.count == before  # no prior direction to compare against


def test_stroke_end_implicitly_resets_direction_tracking():
    emitter, system = _emitter(base_emit_rate=0.0, velocity_to_rate_scale=0.0)
    emitter.on_stroke_point(0, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.on_stroke_point(10, 0, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    emitter.on_stroke_end(10, 0, (255, 0, 0), size=10)
    before = system.count
    emitter.on_stroke_point(10, -10, (255, 0, 0), size=10, velocity=0.0, dt=0.0)
    assert system.count == before
