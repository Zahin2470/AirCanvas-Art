"""
End-to-end integration tests: exercise aircanvas.app.run() and its
per-frame helpers the way a real session would, headlessly.

Uses the SDL dummy video/audio drivers so pygame.display/pygame.mixer
initialize deterministically in any environment (this sandbox, CI, a
real machine) without touching real hardware -- set only in this test
module, never in production code.

Each test isolates its app-data directory via AIRCANVAS_HOME (a
tmp_path), so these tests never read or write the real user's
~/.aircanvas, and can't interfere with each other.
"""
from __future__ import annotations

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from aircanvas import app
from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType, SELECTABLE_BRUSHES
from aircanvas.canvas.model import CanvasModel
from aircanvas.config import load_config
from aircanvas.interaction.dev_input import DevIntentSource
from aircanvas.interaction.state_machine import StateMachineConfig
from aircanvas.persistence.project_io import load_project, save_project
from aircanvas.persistence.settings import AppSettings, load_settings, save_settings
from aircanvas.vision.camera import CameraError


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRCANVAS_HOME", str(tmp_path))


def _quit_after_n_event_polls(monkeypatch, n=3):
    """Make pygame.event.get() return a QUIT event on the Nth call, so
    app.run()'s loop exits after a few real frames -- deterministic,
    no sleeping or threads."""
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] >= n:
            return [pygame.event.Event(pygame.QUIT)]
        return []

    monkeypatch.setattr(pygame.event, "get", fake_get)


def _stroke():
    from aircanvas.canvas.stroke import Stroke

    return Stroke(points=[(10.0, 10.0), (20.0, 20.0)], color=(255, 0, 0), size=10.0)


# -- Full app.run() smoke tests ------------------------------------------

def test_app_runs_and_exits_cleanly_in_mouse_mode(monkeypatch):
    _quit_after_n_event_polls(monkeypatch)
    config = load_config({})
    assert app.run(config, mouse_mode=True) == 0


def test_app_falls_back_to_mouse_mode_when_camera_cannot_open(monkeypatch):
    _quit_after_n_event_polls(monkeypatch)

    def fail_to_open(self):
        raise CameraError("no camera in this test")

    monkeypatch.setattr("aircanvas.app.Camera.open", fail_to_open)
    config = load_config({})
    # mouse_mode=False, but Camera.open always raises -> should fall
    # back automatically rather than crash or hang.
    assert app.run(config, mouse_mode=False) == 0


def test_app_loads_an_explicit_project_at_startup(monkeypatch, tmp_path):
    config = load_config({})
    model = CanvasModel(width=config.canvas_pixel_width, height=config.canvas_pixel_height)
    model.add_stroke(_stroke())
    project_path = tmp_path / "art.aircanvas"
    save_project(project_path, model)

    _quit_after_n_event_polls(monkeypatch)
    assert app.run(config, mouse_mode=True, open_path=str(project_path)) == 0


def test_app_recovers_unsaved_work_from_a_previous_session(monkeypatch, tmp_path):
    from aircanvas.config import get_recovery_path

    config = load_config({})
    model = CanvasModel(width=config.canvas_pixel_width, height=config.canvas_pixel_height)
    model.add_stroke(_stroke())
    save_project(get_recovery_path(), model)

    _quit_after_n_event_polls(monkeypatch)
    assert app.run(config, mouse_mode=True) == 0
    # A clean exit clears the recovery file so the next launch doesn't
    # re-offer it.
    assert not get_recovery_path().exists()


# -- Draw / undo / erase through the real routing helpers -----------------

def test_full_draw_undo_erase_cycle_through_real_app_code():
    pygame.display.set_mode((10, 10))
    config = load_config({})
    layout = app.Layout(config, show_preview=False)
    toolbar = app._build_toolbar(layout, config)
    selection = app._BrushSelection(config)
    canvas_model = CanvasModel(
        width=config.canvas_pixel_width, height=config.canvas_pixel_height,
        background_color=config.canvas_background_color,
    )
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    source = DevIntentSource(StateMachineConfig(debounce_frames=1))

    start = (layout.canvas_rect.x + 50, layout.canvas_rect.y + 50)
    end = (layout.canvas_rect.x + 150, layout.canvas_rect.y + 50)
    for i in range(5):
        t = i / 4
        x = int(start[0] + (end[0] - start[0]) * t)
        intent = source.update((x, start[1]), left_button=True, right_button=False, fist_key=False)
        app._route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)
    intent = source.update(end, left_button=False, right_button=False, fist_key=False)
    app._route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)

    assert canvas_model.stroke_count == 1
    drawn_pixel = canvas_surface.get_at((100, 50))[:3]
    assert drawn_pixel != canvas_model.background_color

    canvas_model.undo()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    assert canvas_surface.get_at((100, 50))[:3] == canvas_model.background_color

    canvas_model.redo()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    assert canvas_surface.get_at((100, 50))[:3] == drawn_pixel

    # Erase over the same spot.
    for pos in [(90, 50), (100, 50), (110, 50)]:
        window_pos = (layout.canvas_rect.x + pos[0], layout.canvas_rect.y + pos[1])
        intent = source.update(window_pos, left_button=False, right_button=True, fist_key=False)
        app._route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)
    window_pos = (layout.canvas_rect.x + 110, layout.canvas_rect.y + 50)
    intent = source.update(window_pos, left_button=False, right_button=False, fist_key=False)
    app._route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)
    assert canvas_surface.get_at((100, 50))[:3] == canvas_model.background_color


def test_touchless_toolbar_dwell_selects_brush_and_size():
    pygame.display.set_mode((10, 10))
    config = load_config({})
    layout = app.Layout(config, show_preview=False)
    toolbar = app._build_toolbar(layout, config)
    selection = app._BrushSelection(config)
    canvas_model = CanvasModel(width=config.canvas_pixel_width, height=config.canvas_pixel_height)
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    source = DevIntentSource(StateMachineConfig(debounce_frames=1))

    neon_index = SELECTABLE_BRUSHES.index(BrushType.NEON_GLOW)
    widget = toolbar.widget_by_id(f"brush:{neon_index}")
    cx, cy = widget.rect.center
    for _ in range(25):
        intent = source.update((cx, cy), left_button=True, right_button=False, fist_key=False)
        app._route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)

    assert selection.brush_type == BrushType.NEON_GLOW


def test_shape_assist_snaps_a_rough_rectangle_drawn_through_real_app_code():
    pygame.display.set_mode((10, 10))
    config = load_config({})
    layout = app.Layout(config, show_preview=False)
    toolbar = app._build_toolbar(layout, config)
    selection = app._BrushSelection(config)
    canvas_model = CanvasModel(
        width=config.canvas_pixel_width, height=config.canvas_pixel_height,
        background_color=config.canvas_background_color,
    )
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    source = DevIntentSource(StateMachineConfig(debounce_frames=1))

    # Walk a rough, slightly-jittered rectangle outline, drawn as one
    # continuous pinch-held stroke -- the same shape as a real hand's
    # imperfect attempt at a rectangle.
    rng = random.Random(11)
    origin = (layout.canvas_rect.x + 100, layout.canvas_rect.y + 100)
    corners = [(0, 0), (200, 0), (200, 150), (0, 150), (0, 0)]
    rough_points = []
    for a, b in zip(corners, corners[1:]):
        for i in range(10):
            t = i / 10
            x = origin[0] + a[0] + (b[0] - a[0]) * t + rng.uniform(-2, 2)
            y = origin[1] + a[1] + (b[1] - a[1]) * t + rng.uniform(-2, 2)
            rough_points.append((x, y))

    shape_match = None
    for point in rough_points:
        intent = source.update(point, left_button=True, right_button=False, fist_key=False)
        _, match = app._route_intent(
            intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface,
            shape_assist_enabled=True, shape_assist_min_points=8,
        )
        shape_match = shape_match or match
    intent = source.update(rough_points[-1], left_button=False, right_button=False, fist_key=False)
    _, match = app._route_intent(
        intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface,
        shape_assist_enabled=True, shape_assist_min_points=8,
    )
    shape_match = shape_match or match

    assert shape_match is not None
    assert canvas_model.stroke_count == 1
    snapped_stroke = canvas_model.strokes[0]
    # The idealized rectangle has exactly 5 points (4 corners + close);
    # the rough hand-drawn version had ~40.
    assert len(snapped_stroke.points) < len(rough_points) / 2


def test_shape_assist_off_by_default_leaves_rough_strokes_alone():
    pygame.display.set_mode((10, 10))
    config = load_config({})
    assert config.shape_assist_enabled is False


# -- Settings persistence across a simulated relaunch ----------------------

def test_settings_persist_across_a_simulated_relaunch(tmp_path):
    written = AppSettings(theme="light", brush_type_index=3, muted=True, master_volume=0.3)
    settings_path = tmp_path / "settings.json"
    save_settings(written, settings_path)

    reloaded = load_settings(settings_path)
    assert reloaded == written


def test_corrupted_settings_file_does_not_crash_a_relaunch(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json at all")
    reloaded = load_settings(settings_path)
    assert reloaded == AppSettings()  # falls back to defaults, doesn't raise


# -- Save/export round trip ------------------------------------------------

def test_save_then_reload_preserves_strokes(tmp_path):
    config = load_config({})
    model = CanvasModel(width=config.canvas_pixel_width, height=config.canvas_pixel_height)
    model.add_stroke(_stroke())
    model.add_stroke(_stroke())

    path = tmp_path / "art.aircanvas"
    save_project(path, model)
    reloaded, _ = load_project(path)

    assert reloaded.stroke_count == 2
    assert reloaded.strokes[0].points == model.strokes[0].points
