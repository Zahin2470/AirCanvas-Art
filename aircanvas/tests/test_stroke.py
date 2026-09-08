from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.stroke import Stroke


def test_new_stroke_is_empty_by_default():
    stroke = Stroke()
    assert stroke.is_empty
    assert stroke.bounding_box() is None


def test_add_point_appends_and_clears_empty():
    stroke = Stroke()
    stroke.add_point(1.0, 2.0)
    assert not stroke.is_empty
    assert stroke.points == [(1.0, 2.0)]


def test_bounding_box_pads_by_half_the_brush_size():
    stroke = Stroke(points=[(10.0, 10.0), (20.0, 30.0)], size=8.0)
    box = stroke.bounding_box()
    assert box == (10.0 - 4.0, 10.0 - 4.0, 20.0 + 4.0, 30.0 + 4.0)


def test_defaults_are_sane():
    stroke = Stroke()
    assert 0.0 <= stroke.opacity <= 1.0
    assert stroke.size > 0
    assert stroke.brush_type == BrushType.SMOOTH_INK


def test_created_at_is_set_automatically():
    stroke = Stroke()
    assert stroke.created_at > 0
