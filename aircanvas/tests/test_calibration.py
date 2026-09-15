import pytest

from aircanvas.vision.calibration import Calibrator, CoordinateMapper, MapperConfig


def test_center_point_maps_to_canvas_center_with_no_margins():
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0))
    assert mapper.map(0.5, 0.5) == (500, 250)


def test_corners_map_to_canvas_corners_with_no_margins():
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0))
    assert mapper.map(0.0, 0.0) == (0, 0)
    assert mapper.map(1.0, 1.0) == (1000, 500)


def test_margins_shrink_the_active_region():
    # With a 10% margin on every side, the point 0.1 (the very edge of
    # the active region) should map to the canvas's left edge.
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0.1, margin_right=0.1, margin_top=0.1, margin_bottom=0.1))
    assert mapper.map(0.1, 0.5) == (0, 250)
    assert mapper.map(0.9, 0.5) == (1000, 250)


def test_points_outside_active_region_clamp_to_canvas_edge():
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0.1, margin_right=0.1, margin_top=0.1, margin_bottom=0.1))
    assert mapper.map(0.0, 0.5) == (0, 250)  # would be negative without clamping
    assert mapper.map(1.0, 0.5) == (1000, 250)  # would overshoot without clamping


def test_sensitivity_above_one_amplifies_movement_around_center():
    normal = CoordinateMapper(1000, 500, MapperConfig(sensitivity=1.0, margin_left=0, margin_right=0, margin_top=0, margin_bottom=0))
    amplified = CoordinateMapper(1000, 500, MapperConfig(sensitivity=2.0, margin_left=0, margin_right=0, margin_top=0, margin_bottom=0))
    nx, _ = normal.map(0.6, 0.5)
    ax, _ = amplified.map(0.6, 0.5)
    assert ax > nx  # same input, further from center canvas when amplified


def test_resize_updates_target_canvas_dimensions():
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0))
    mapper.resize(2000, 1000)
    assert mapper.map(0.5, 0.5) == (1000, 500)


def test_calibrator_is_incomplete_until_both_points_set():
    calibrator = Calibrator()
    assert not calibrator.is_complete
    calibrator.set_top_left(0.2, 0.2)
    assert not calibrator.is_complete
    calibrator.set_bottom_right(0.8, 0.8)
    assert calibrator.is_complete


def test_calibrator_raises_if_converted_before_complete():
    calibrator = Calibrator()
    calibrator.set_top_left(0.2, 0.2)
    with pytest.raises(ValueError):
        calibrator.to_mapper_config()


def test_calibrator_derives_margins_from_captured_corners():
    calibrator = Calibrator()
    calibrator.set_top_left(0.2, 0.15)
    calibrator.set_bottom_right(0.85, 0.9)
    config = calibrator.to_mapper_config()
    assert config.margin_left == pytest.approx(0.2)
    assert config.margin_right == pytest.approx(0.15)
    assert config.margin_top == pytest.approx(0.15)
    assert config.margin_bottom == pytest.approx(0.1)


def test_calibrator_handles_corners_captured_in_reversed_order():
    # A person might point at the bottom-right first without realizing
    # the key order matters; min/max should still recover sane margins.
    calibrator = Calibrator()
    calibrator.set_top_left(0.85, 0.9)
    calibrator.set_bottom_right(0.2, 0.15)
    config = calibrator.to_mapper_config()
    assert config.margin_left == pytest.approx(0.2)
    assert config.margin_top == pytest.approx(0.15)


def test_calibrator_clamps_extreme_margins():
    calibrator = Calibrator()
    calibrator.set_top_left(0.49, 0.49)
    calibrator.set_bottom_right(0.51, 0.51)
    config = calibrator.to_mapper_config(max_margin=0.45)
    assert config.margin_left <= 0.45
    assert config.margin_top <= 0.45


def test_calibrator_reset_clears_captured_points():
    calibrator = Calibrator()
    calibrator.set_top_left(0.2, 0.2)
    calibrator.set_bottom_right(0.8, 0.8)
    calibrator.reset()
    assert not calibrator.is_complete
    assert not calibrator.has_top_left
    assert not calibrator.has_bottom_right


def test_set_sensitivity_changes_mapping_without_touching_margins():
    config = MapperConfig(margin_left=0.1, margin_right=0.1, margin_top=0.1, margin_bottom=0.1, sensitivity=1.0)
    mapper = CoordinateMapper(1000, 500, config)
    before = mapper.map(0.7, 0.5)
    mapper.set_sensitivity(0.5)
    after = mapper.map(0.7, 0.5)
    assert after != before
    assert mapper.config.margin_left == 0.1  # margins preserved


def test_lower_sensitivity_dampens_movement_around_center():
    mapper = CoordinateMapper(1000, 500, MapperConfig(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0, sensitivity=1.0))
    full_x, _ = mapper.map(0.6, 0.5)
    mapper.set_sensitivity(0.5)
    damped_x, _ = mapper.map(0.6, 0.5)
    center = 500
    assert abs(damped_x - center) < abs(full_x - center)
