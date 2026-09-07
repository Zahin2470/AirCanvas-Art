from aircanvas.vision.smoothing import PointSmoother, SmoothingConfig


def test_first_sample_is_returned_unsmoothed():
    smoother = PointSmoother()
    result = smoother.update(0.5, 0.5, dt=1 / 30)
    assert result == (0.5, 0.5)
    assert smoother.velocity == 0.0


def test_second_sample_moves_partway_toward_target():
    config = SmoothingConfig(min_alpha=0.5, max_alpha=0.5)  # fixed alpha, easy to predict
    smoother = PointSmoother(config)
    smoother.update(0.0, 0.0, dt=1 / 30)
    x, y = smoother.update(1.0, 0.0, dt=1 / 30)
    assert x == 0.5  # halfway, since alpha == 0.5
    assert y == 0.0


def test_movement_below_deadband_is_ignored():
    config = SmoothingConfig(min_movement_threshold=0.01, min_alpha=1.0, max_alpha=1.0)
    smoother = PointSmoother(config)
    smoother.update(0.5, 0.5, dt=1 / 30)
    result = smoother.update(0.505, 0.5, dt=1 / 30)  # smaller than the 0.01 deadband
    assert result == (0.5, 0.5)


def test_movement_above_deadband_is_applied():
    config = SmoothingConfig(min_movement_threshold=0.01, min_alpha=1.0, max_alpha=1.0)
    smoother = PointSmoother(config)
    smoother.update(0.5, 0.5, dt=1 / 30)
    result = smoother.update(0.6, 0.5, dt=1 / 30)  # bigger than the deadband, alpha=1.0 -> jumps fully
    assert result == (0.6, 0.5)


def test_faster_movement_tracks_more_closely_than_slower_movement():
    config = SmoothingConfig(min_alpha=0.1, max_alpha=0.9, velocity_lower=0.0, velocity_upper=1.0)

    slow = PointSmoother(config)
    slow.update(0.0, 0.0, dt=1.0)
    slow_result = slow.update(0.05, 0.0, dt=1.0)  # velocity 0.05/s -> near min_alpha

    fast = PointSmoother(config)
    fast.update(0.0, 0.0, dt=1.0)
    fast_result = fast.update(2.0, 0.0, dt=1.0)  # velocity 2.0/s -> saturates at max_alpha

    # Both start at the same point and move toward the same-direction
    # target; the faster one should end up closer to its raw target
    # (as a fraction of distance traveled) because it gets more alpha.
    slow_fraction = slow_result[0] / 0.05
    fast_fraction = fast_result[0] / 2.0
    assert fast_fraction > slow_fraction


def test_velocity_is_computed_from_raw_positions_not_smoothed():
    smoother = PointSmoother(SmoothingConfig(min_alpha=0.1, max_alpha=0.1))
    smoother.update(0.0, 0.0, dt=1.0)
    smoother.update(1.0, 0.0, dt=1.0)
    assert smoother.velocity == 1.0  # raw jump of 1.0 over 1.0s, regardless of how little alpha let through


def test_reset_clears_state_so_next_sample_is_unsmoothed():
    smoother = PointSmoother()
    smoother.update(0.1, 0.1, dt=1 / 30)
    smoother.update(0.9, 0.9, dt=1 / 30)
    smoother.reset()
    result = smoother.update(0.3, 0.3, dt=1 / 30)
    assert result == (0.3, 0.3)
    assert smoother.velocity == 0.0
