import pygame

from aircanvas.ui.toolbar import Toolbar, Widget


def _toolbar(dwell_frames=3):
    widgets = [
        Widget(id="a", rect=pygame.Rect(0, 0, 10, 10)),
        Widget(id="b", rect=pygame.Rect(20, 0, 10, 10)),
    ]
    return Toolbar(widgets, dwell_frames=dwell_frames)


def test_no_cursor_reports_nothing_hovered():
    toolbar = _toolbar()
    result = toolbar.update(cursor_pos=None, selecting=False)
    assert result.hovered_id is None
    assert result.activated_id is None


def test_cursor_outside_any_widget_reports_nothing_hovered():
    toolbar = _toolbar()
    result = toolbar.update(cursor_pos=(100, 100), selecting=False)
    assert result.hovered_id is None


def test_hovering_without_selecting_reports_hover_but_no_activation():
    toolbar = _toolbar()
    result = toolbar.update(cursor_pos=(5, 5), selecting=False)
    assert result.hovered_id == "a"
    assert result.activated_id is None
    assert result.hover_progress == 0.0


def test_sustained_selecting_activates_after_dwell_frames():
    toolbar = _toolbar(dwell_frames=3)
    r1 = toolbar.update((5, 5), selecting=True)
    r2 = toolbar.update((5, 5), selecting=True)
    r3 = toolbar.update((5, 5), selecting=True)
    assert r1.activated_id is None
    assert r2.activated_id is None
    assert r3.activated_id == "a"
    assert r3.hover_progress == 1.0


def test_dwell_progress_increases_monotonically():
    toolbar = _toolbar(dwell_frames=4)
    progresses = [toolbar.update((5, 5), selecting=True).hover_progress for _ in range(4)]
    assert progresses == sorted(progresses)
    assert progresses[-1] == 1.0


def test_releasing_before_dwell_completes_cancels_progress():
    toolbar = _toolbar(dwell_frames=5)
    toolbar.update((5, 5), selecting=True)
    toolbar.update((5, 5), selecting=True)
    released = toolbar.update((5, 5), selecting=False)
    assert released.activated_id is None
    assert released.hover_progress == 0.0
    resumed = toolbar.update((5, 5), selecting=True)
    assert resumed.hover_progress < 0.5  # dwell counter reset, not carried over


def test_moving_to_a_different_widget_resets_dwell():
    toolbar = _toolbar(dwell_frames=3)
    toolbar.update((5, 5), selecting=True)
    toolbar.update((5, 5), selecting=True)
    moved = toolbar.update((25, 5), selecting=True)  # widget "b" now
    assert moved.hovered_id == "b"
    assert moved.activated_id is None
    assert moved.hover_progress < 1.0


def test_activation_does_not_repeat_fire_while_still_holding():
    toolbar = _toolbar(dwell_frames=2)
    toolbar.update((5, 5), selecting=True)
    first = toolbar.update((5, 5), selecting=True)
    assert first.activated_id == "a"
    second = toolbar.update((5, 5), selecting=True)
    assert second.activated_id is None  # still hovering/holding, but not a fresh activation


def test_widget_by_id_finds_widget():
    toolbar = _toolbar()
    assert toolbar.widget_by_id("a") is not None
    assert toolbar.widget_by_id("missing") is None


def test_widget_at_returns_matching_widget():
    toolbar = _toolbar()
    widget = toolbar.widget_at((5, 5))
    assert widget is not None
    assert widget.id == "a"
