from aircanvas.canvas.history import AddStrokeAction, ClearCanvasAction, History
from aircanvas.canvas.stroke import Stroke


def _stroke(*points):
    return Stroke(points=list(points), created_at=0.0)


def test_do_appends_and_enables_undo():
    history = History()
    strokes = []
    history.do(AddStrokeAction(_stroke((0, 0))), strokes)
    assert strokes == [_stroke((0, 0))]
    assert history.can_undo
    assert not history.can_redo


def test_undo_removes_the_last_added_stroke():
    history = History()
    strokes = []
    s1, s2 = _stroke((0, 0)), _stroke((1, 1))
    history.do(AddStrokeAction(s1), strokes)
    history.do(AddStrokeAction(s2), strokes)
    assert history.undo(strokes) is True
    assert strokes == [s1]


def test_redo_restores_the_undone_stroke():
    history = History()
    strokes = []
    s1 = _stroke((0, 0))
    history.do(AddStrokeAction(s1), strokes)
    history.undo(strokes)
    assert history.redo(strokes) is True
    assert strokes == [s1]


def test_new_action_after_undo_invalidates_redo():
    history = History()
    strokes = []
    s1, s2 = _stroke((0, 0)), _stroke((1, 1))
    history.do(AddStrokeAction(s1), strokes)
    history.undo(strokes)
    assert history.can_redo
    history.do(AddStrokeAction(s2), strokes)
    assert not history.can_redo
    assert strokes == [s2]


def test_undo_on_empty_history_is_a_no_op():
    history = History()
    strokes = []
    assert history.undo(strokes) is False
    assert strokes == []


def test_redo_on_empty_redo_stack_is_a_no_op():
    history = History()
    strokes = [_stroke((0, 0))]
    assert history.redo(strokes) is False


def test_clear_canvas_action_can_be_undone_and_redone():
    history = History()
    strokes = [_stroke((0, 0)), _stroke((1, 1))]
    original = list(strokes)
    history.do(ClearCanvasAction(tuple(original)), strokes)
    assert strokes == []
    assert history.undo(strokes) is True
    assert strokes == original
    assert history.redo(strokes) is True
    assert strokes == []


def test_history_clear_resets_both_stacks():
    history = History()
    strokes = []
    history.do(AddStrokeAction(_stroke((0, 0))), strokes)
    history.undo(strokes)
    history.clear()
    assert not history.can_undo
    assert not history.can_redo
