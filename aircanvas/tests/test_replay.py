import pygame
import pytest

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.replay import (
    ReplayController,
    build_timeline,
    points_visible_at,
    total_duration,
)
from aircanvas.canvas.stroke import Stroke

BACKGROUND = (10, 10, 12)


def _stroke(points, point_times=None, created_at=0.0):
    return Stroke(points=points, point_times=point_times or [], color=(255, 0, 0), size=10, created_at=created_at)


def test_build_timeline_uses_point_times_for_duration():
    stroke = _stroke([(0, 0), (10, 0), (20, 0)], point_times=[0.0, 0.5, 1.2], created_at=100.0)
    timeline = build_timeline([stroke])
    assert timeline[0].start_time == 0.0
    assert timeline[0].end_time == pytest.approx(1.2)


def test_build_timeline_falls_back_to_even_spacing_without_point_times():
    stroke = _stroke([(0, 0), (10, 0), (20, 0)], created_at=100.0)  # no point_times
    timeline = build_timeline([stroke])
    expected = 2 * (1.0 / 30)  # 2 gaps at the default interval
    assert timeline[0].end_time == pytest.approx(expected)


def test_build_timeline_uses_real_gap_between_strokes():
    s1 = _stroke([(0, 0)], created_at=100.0)
    s2 = _stroke([(10, 10)], created_at=100.5)
    timeline = build_timeline([s1, s2])
    assert timeline[1].start_time == pytest.approx(0.5)


def test_build_timeline_clamps_a_very_long_gap():
    s1 = _stroke([(0, 0)], created_at=100.0)
    s2 = _stroke([(10, 10)], created_at=500.0)  # a 400s "coffee break"
    timeline = build_timeline([s1, s2])
    assert timeline[1].start_time == pytest.approx(2.0)  # clamped to MAX_STROKE_GAP_SECONDS


def test_build_timeline_clamps_a_negative_or_tiny_gap():
    s1 = _stroke([(0, 0)], created_at=100.0)
    s2 = _stroke([(10, 10)], created_at=100.0)  # identical timestamp
    timeline = build_timeline([s1, s2])
    assert timeline[1].start_time == pytest.approx(0.05)  # clamped to MIN_STROKE_GAP_SECONDS


def test_total_duration_of_empty_timeline_is_zero():
    assert total_duration([]) == 0.0


def test_points_visible_before_stroke_starts_is_zero():
    stroke = _stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])
    timeline = build_timeline([stroke])
    assert points_visible_at(stroke, timeline[0], playback_time=-1.0) == 0


def test_points_visible_after_stroke_ends_is_all_of_them():
    stroke = _stroke([(0, 0), (10, 0), (20, 0)], point_times=[0.0, 0.5, 1.0])
    timeline = build_timeline([stroke])
    assert points_visible_at(stroke, timeline[0], playback_time=100.0) == 3


def test_points_visible_partway_through_uses_point_times():
    stroke = _stroke([(0, 0), (10, 0), (20, 0)], point_times=[0.0, 0.5, 1.0])
    timeline = build_timeline([stroke])
    assert points_visible_at(stroke, timeline[0], playback_time=0.6) == 2


def test_points_visible_partway_through_without_timing_uses_fraction():
    stroke = _stroke([(0, 0), (10, 0), (20, 0), (30, 0), (40, 0)])  # no point_times
    timeline = build_timeline([stroke])
    half_time = timeline[0].end_time / 2
    count = points_visible_at(stroke, timeline[0], half_time)
    assert 1 <= count <= 5


# -- ReplayController --------------------------------------------------

def test_controller_starts_paused_at_time_zero():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    assert controller.playback_time == 0.0
    assert controller.is_playing is False


def test_play_sets_playing_true():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.play()
    assert controller.is_playing is True


def test_advance_while_paused_does_nothing():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.advance(0.5)
    assert controller.playback_time == 0.0


def test_advance_while_playing_moves_the_clock():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 2.0])])
    controller.play()
    controller.advance(0.5)
    assert controller.playback_time == pytest.approx(0.5)


def test_speed_multiplies_advance():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 4.0])])
    controller.set_speed(2.0)
    controller.play()
    controller.advance(0.5)
    assert controller.playback_time == pytest.approx(1.0)


def test_playback_stops_and_clamps_at_duration():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.play()
    controller.advance(10.0)  # way past the end
    assert controller.playback_time == pytest.approx(controller.duration)
    assert controller.is_playing is False


def test_restart_resets_to_zero():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.play()
    controller.advance(0.5)
    controller.restart()
    assert controller.playback_time == 0.0


def test_playing_after_finished_restarts_automatically():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.play()
    controller.advance(10.0)
    assert controller.is_finished
    controller.play()
    assert controller.playback_time == 0.0
    assert controller.is_playing is True


def test_toggle_flips_play_state():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 1.0])])
    controller.toggle()
    assert controller.is_playing is True
    controller.toggle()
    assert controller.is_playing is False


def test_seek_sets_fraction_of_duration():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 4.0])])
    controller.seek(0.5)
    assert controller.playback_time == pytest.approx(2.0)


def test_seek_clamps_out_of_range_fractions():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 4.0])])
    controller.seek(2.0)
    assert controller.playback_time == pytest.approx(controller.duration)
    controller.seek(-1.0)
    assert controller.playback_time == 0.0


def test_progress_is_fraction_of_duration():
    controller = ReplayController([_stroke([(0, 0), (10, 0)], point_times=[0.0, 4.0])])
    controller.seek(0.25)
    assert controller.progress == pytest.approx(0.25)


def test_progress_of_empty_replay_is_one():
    controller = ReplayController([])
    assert controller.progress == 1.0


def test_render_draws_only_visible_points():
    controller = ReplayController([_stroke([(50, 50), (150, 50)], point_times=[0.0, 1.0], created_at=0.0)])
    controller.seek(0.0)  # nothing visible yet
    surface = pygame.Surface((300, 300))
    engine = BrushEngine()
    controller.render(surface, engine, BACKGROUND)
    # Right at time 0 the stroke hasn't started, so the canvas is blank.
    assert surface.get_at((100, 50))[:3] == BACKGROUND


def test_render_draws_full_stroke_once_finished():
    controller = ReplayController([_stroke([(50, 50), (150, 50)], point_times=[0.0, 1.0], created_at=0.0)])
    controller.seek(1.0)
    surface = pygame.Surface((300, 300))
    engine = BrushEngine()
    controller.render(surface, engine, BACKGROUND)
    assert surface.get_at((50, 50))[:3] != BACKGROUND
    assert surface.get_at((150, 50))[:3] != BACKGROUND
