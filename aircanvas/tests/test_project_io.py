import json

import pygame
import pytest

from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.model import CanvasModel
from aircanvas.canvas.stroke import Stroke
from aircanvas.persistence.project_io import (
    ProjectLoadError,
    export_png,
    load_project,
    save_project,
)


def _sample_model() -> CanvasModel:
    model = CanvasModel(width=800, height=600, background_color=(20, 22, 24))
    model.add_stroke(
        Stroke(
            points=[(1.0, 2.0), (3.5, 4.25)],
            point_times=[0.0, 0.033],
            color=(255, 87, 87),
            size=12.0,
            opacity=0.9,
            brush_type=BrushType.NEON_GLOW,
            created_at=1000.0,
        )
    )
    model.add_stroke(
        Stroke(points=[(10.0, 10.0)], color=(0, 255, 0), size=8.0, brush_type=BrushType.SPARK, created_at=1001.0)
    )
    return model


def test_round_trip_preserves_canvas_dimensions_and_background(tmp_path):
    model = _sample_model()
    path = tmp_path / "art.aircanvas"
    save_project(path, model)
    loaded, _ = load_project(path)
    assert (loaded.width, loaded.height) == (800, 600)
    assert loaded.background_color == (20, 22, 24)


def test_round_trip_preserves_stroke_count_and_order(tmp_path):
    model = _sample_model()
    path = tmp_path / "art.aircanvas"
    save_project(path, model)
    loaded, _ = load_project(path)
    assert loaded.stroke_count == 2
    assert loaded.strokes[0].brush_type == BrushType.NEON_GLOW
    assert loaded.strokes[1].brush_type == BrushType.SPARK


def test_round_trip_preserves_stroke_fields_precisely(tmp_path):
    model = _sample_model()
    path = tmp_path / "art.aircanvas"
    save_project(path, model)
    loaded, _ = load_project(path)
    stroke = loaded.strokes[0]
    assert stroke.points == pytest.approx([(1.0, 2.0), (3.5, 4.25)])
    assert stroke.point_times == pytest.approx([0.0, 0.033])
    assert stroke.color == (255, 87, 87)
    assert stroke.size == pytest.approx(12.0)
    assert stroke.opacity == pytest.approx(0.9)
    assert stroke.created_at == pytest.approx(1000.0)


def test_loaded_project_is_undoable_stroke_by_stroke(tmp_path):
    model = _sample_model()
    path = tmp_path / "art.aircanvas"
    save_project(path, model)
    loaded, _ = load_project(path)
    assert loaded.can_undo
    loaded.undo()
    assert loaded.stroke_count == 1
    loaded.undo()
    assert loaded.stroke_count == 0


def test_metadata_round_trips(tmp_path):
    model = _sample_model()
    path = tmp_path / "art.aircanvas"
    save_project(path, model, metadata={"title": "My Sketch"})
    _, metadata = load_project(path)
    assert metadata["title"] == "My Sketch"


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "art.aircanvas"
    save_project(path, _sample_model())
    assert path.exists()


def test_load_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(ProjectLoadError, match="not found"):
        load_project(tmp_path / "nope.aircanvas")


def test_load_invalid_json_raises_clear_error(tmp_path):
    path = tmp_path / "bad.aircanvas"
    path.write_text("{not valid json")
    with pytest.raises(ProjectLoadError, match="not valid JSON"):
        load_project(path)


def test_load_wrong_version_raises_clear_error(tmp_path):
    path = tmp_path / "future.aircanvas"
    path.write_text(json.dumps({"version": 999, "canvas": {"width": 10, "height": 10}, "strokes": []}))
    with pytest.raises(ProjectLoadError, match="version"):
        load_project(path)


def test_load_missing_canvas_section_raises_clear_error(tmp_path):
    path = tmp_path / "bad.aircanvas"
    path.write_text(json.dumps({"version": 1, "strokes": []}))
    with pytest.raises(ProjectLoadError, match="canvas"):
        load_project(path)


def test_load_non_object_json_raises_clear_error(tmp_path):
    path = tmp_path / "bad.aircanvas"
    path.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ProjectLoadError):
        load_project(path)


def test_load_stroke_with_no_points_raises_clear_error(tmp_path):
    path = tmp_path / "bad.aircanvas"
    payload = {
        "version": 1,
        "canvas": {"width": 10, "height": 10},
        "strokes": [{"points": [], "color": "#ffffff", "size": 5}],
    }
    path.write_text(json.dumps(payload))
    with pytest.raises(ProjectLoadError, match="Stroke #0"):
        load_project(path)


def test_load_invalid_color_raises_clear_error(tmp_path):
    path = tmp_path / "bad.aircanvas"
    payload = {
        "version": 1,
        "canvas": {"width": 10, "height": 10},
        "strokes": [{"points": [[0, 0]], "color": "not-a-color", "size": 5}],
    }
    path.write_text(json.dumps(payload))
    with pytest.raises(ProjectLoadError):
        load_project(path)


def test_load_unknown_brush_type_falls_back_to_smooth_ink(tmp_path):
    path = tmp_path / "future_brush.aircanvas"
    payload = {
        "version": 1,
        "canvas": {"width": 10, "height": 10},
        "strokes": [{"points": [[0, 0]], "color": "#ffffff", "size": 5, "brush_type": "holographic_v2"}],
    }
    path.write_text(json.dumps(payload))
    model, _ = load_project(path)
    assert model.strokes[0].brush_type == BrushType.SMOOTH_INK


def test_load_point_times_length_mismatch_is_dropped_not_fatal(tmp_path):
    path = tmp_path / "mismatch.aircanvas"
    payload = {
        "version": 1,
        "canvas": {"width": 10, "height": 10},
        "strokes": [
            {"points": [[0, 0], [1, 1]], "point_times": [0.0], "color": "#ffffff", "size": 5}
        ],
    }
    path.write_text(json.dumps(payload))
    model, _ = load_project(path)
    assert model.strokes[0].point_times == []  # mismatch dropped, not raised


def test_save_is_atomic_no_leftover_tmp_file(tmp_path):
    path = tmp_path / "art.aircanvas"
    save_project(path, _sample_model())
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_export_png_writes_a_readable_image_of_the_right_size(tmp_path):
    surface = pygame.Surface((120, 80))
    surface.fill((255, 0, 0))
    path = tmp_path / "export.png"
    export_png(path, surface)
    assert path.exists()

    loaded = pygame.image.load(str(path))
    assert loaded.get_size() == (120, 80)
    assert loaded.get_at((10, 10))[:3] == (255, 0, 0)
