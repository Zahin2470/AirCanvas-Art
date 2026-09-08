import pygame
import pytest

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.eraser import create_eraser_stroke
from aircanvas.canvas.stroke import Stroke

BACKGROUND = (18, 18, 24)
INK = (255, 0, 0)


@pytest.fixture
def surface():
    # pygame.Surface works headlessly -- no display/video driver
    # needed, only pygame.display.set_mode would require one.
    surf = pygame.Surface((200, 200))
    surf.fill(BACKGROUND)
    return surf


def test_begin_stroke_paints_a_dot_immediately(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 100, 100, color=INK, size=20)
    assert surface.get_at((100, 100))[:3] == INK
    assert engine.is_drawing


def test_extend_stroke_paints_the_new_segment(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 20, 100, color=INK, size=10)
    engine.extend_stroke(surface, 180, 100)
    # A point along the segment, far from either endpoint, should have
    # been stamped too -- proving the segment was filled in, not just
    # the two endpoints.
    assert surface.get_at((100, 100))[:3] == INK


def test_extend_stroke_with_no_active_stroke_is_a_safe_no_op(surface):
    engine = BrushEngine()
    engine.extend_stroke(surface, 50, 50)  # should not raise
    assert not engine.is_drawing


def test_end_stroke_returns_the_completed_stroke(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 10, 10, color=INK, size=8)
    engine.extend_stroke(surface, 20, 20)
    stroke = engine.end_stroke()
    assert stroke is not None
    assert stroke.points == [(10, 10), (20, 20)]
    assert not engine.is_drawing


def test_end_stroke_with_nothing_active_returns_none(surface):
    engine = BrushEngine()
    assert engine.end_stroke() is None


def test_cancel_stroke_discards_without_returning(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 10, 10, color=INK, size=8)
    engine.cancel_stroke()
    assert not engine.is_drawing
    assert engine.end_stroke() is None


def test_single_point_stroke_still_paints_a_visible_dot(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 100, 100, color=INK, size=16)
    stroke = engine.end_stroke()
    assert stroke.points == [(100, 100)]
    assert surface.get_at((100, 100))[:3] == INK


def test_render_full_redraws_all_strokes_in_order(surface):
    engine = BrushEngine()
    strokes = [
        Stroke(points=[(50, 50)], color=(255, 0, 0), size=10),
        Stroke(points=[(150, 150)], color=(0, 255, 0), size=10),
    ]
    engine.render_full(surface, strokes, background_color=BACKGROUND)
    assert surface.get_at((50, 50))[:3] == (255, 0, 0)
    assert surface.get_at((150, 150))[:3] == (0, 255, 0)


def test_render_full_clears_ink_not_present_in_the_given_strokes(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 100, 100, color=INK, size=20)
    engine.end_stroke()
    assert surface.get_at((100, 100))[:3] == INK

    # Simulate an undo: re-render with an empty stroke list.
    engine.render_full(surface, [], background_color=BACKGROUND)
    assert surface.get_at((100, 100))[:3] == BACKGROUND


def test_eraser_stroke_paints_with_background_color(surface):
    engine = BrushEngine()
    engine.begin_stroke(surface, 60, 60, color=INK, size=20)
    engine.end_stroke()
    assert surface.get_at((60, 60))[:3] == INK

    eraser_stroke = create_eraser_stroke(60, 60, background_color=BACKGROUND, size=30)
    engine.render_full(surface, [eraser_stroke], background_color=BACKGROUND)
    assert surface.get_at((60, 60))[:3] == BACKGROUND


def test_eraser_only_affects_ink_drawn_before_it_in_stroke_order(surface):
    engine = BrushEngine()
    earlier_ink = Stroke(points=[(60, 60)], color=INK, size=20)
    eraser = create_eraser_stroke(60, 60, background_color=BACKGROUND, size=40)
    later_ink = Stroke(points=[(60, 60)], color=(0, 0, 255), size=10)

    engine.render_full(surface, [earlier_ink, eraser, later_ink], background_color=BACKGROUND)

    # The later stroke was painted after the eraser, so it's still visible.
    assert surface.get_at((60, 60))[:3] == (0, 0, 255)
