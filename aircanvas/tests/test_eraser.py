from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.eraser import create_eraser_stroke, stamp_covers_point


def test_create_eraser_stroke_uses_background_color_and_full_opacity():
    stroke = create_eraser_stroke(10.0, 20.0, background_color=(18, 18, 24), size=30.0)
    assert stroke.color == (18, 18, 24)
    assert stroke.opacity == 1.0
    assert stroke.brush_type == BrushType.ERASER
    assert stroke.points == [(10.0, 20.0)]


def test_stamp_covers_point_inside_radius():
    assert stamp_covers_point((50.0, 50.0), radius=10.0, point=(55.0, 50.0)) is True


def test_stamp_covers_point_outside_radius():
    assert stamp_covers_point((50.0, 50.0), radius=10.0, point=(70.0, 50.0)) is False


def test_stamp_covers_point_exactly_on_boundary():
    # Point exactly `radius` away should count as covered (<=, not <).
    assert stamp_covers_point((0.0, 0.0), radius=5.0, point=(5.0, 0.0)) is True


def test_stamp_covers_point_at_center():
    assert stamp_covers_point((10.0, 10.0), radius=1.0, point=(10.0, 10.0)) is True
