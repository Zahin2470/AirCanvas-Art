from aircanvas.canvas.model import CanvasModel
from aircanvas.canvas.stroke import Stroke


def _stroke(*points):
    return Stroke(points=list(points))


def test_new_canvas_has_no_strokes_and_nothing_to_undo():
    model = CanvasModel(width=800, height=600)
    assert model.strokes == ()
    assert model.stroke_count == 0
    assert not model.can_undo
    assert not model.can_redo


def test_add_stroke_appends_to_strokes():
    model = CanvasModel(width=800, height=600)
    stroke = _stroke((1, 1), (2, 2))
    model.add_stroke(stroke)
    assert model.strokes == (stroke,)
    assert model.stroke_count == 1
    assert model.can_undo


def test_empty_stroke_is_not_added():
    model = CanvasModel(width=800, height=600)
    model.add_stroke(Stroke())
    assert model.stroke_count == 0
    assert not model.can_undo


def test_undo_removes_last_stroke_redo_restores_it():
    model = CanvasModel(width=800, height=600)
    model.add_stroke(_stroke((0, 0)))
    model.add_stroke(_stroke((1, 1)))
    assert model.undo() is True
    assert model.stroke_count == 1
    assert model.redo() is True
    assert model.stroke_count == 2


def test_new_stroke_after_undo_invalidates_redo():
    model = CanvasModel(width=800, height=600)
    model.add_stroke(_stroke((0, 0)))
    model.undo()
    model.add_stroke(_stroke((1, 1)))
    assert not model.can_redo


def test_clear_removes_all_strokes_as_one_undoable_action():
    model = CanvasModel(width=800, height=600)
    model.add_stroke(_stroke((0, 0)))
    model.add_stroke(_stroke((1, 1)))
    assert model.clear() is True
    assert model.stroke_count == 0
    assert model.undo() is True
    assert model.stroke_count == 2


def test_clear_on_empty_canvas_is_a_no_op():
    model = CanvasModel(width=800, height=600)
    assert model.clear() is False
    assert not model.can_undo


def test_resize_updates_dimensions_without_touching_strokes():
    model = CanvasModel(width=800, height=600)
    model.add_stroke(_stroke((0, 0)))
    model.resize(1024, 768)
    assert (model.width, model.height) == (1024, 768)
    assert model.stroke_count == 1
