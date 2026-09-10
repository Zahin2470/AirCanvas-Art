"""
Project save/load: a plain-JSON `.aircanvas` format storing editable
stroke data -- per the project spec, "do not rely on implementation-
specific Python pickles for user projects".

Strokes are the only source of truth here too: exactly what gets
saved is exactly what CanvasModel.strokes already holds, so save/load
round-trips through the same data undo/redo and replay already use.
Loaded strokes go back in through CanvasModel.add_stroke, so a loaded
project is immediately undoable stroke-by-stroke, like anything else.

File format (version 1):
    {
      "version": 1,
      "canvas": {"width": 1600, "height": 900},
      "background": "#121218",
      "saved_at": 1735689600.0,
      "metadata": {"title": "..."},
      "strokes": [
        {
          "points": [[x, y], ...],
          "point_times": [0.0, 0.03, ...],
          "color": "#f0f0f5",
          "size": 10.0,
          "opacity": 1.0,
          "brush_type": "smooth_ink",
          "created_at": 1735689601.2
        },
        ...
      ]
    }
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pygame

from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.model import CanvasModel
from aircanvas.canvas.stroke import Stroke

PROJECT_FORMAT_VERSION = 1
PathLike = Union[str, Path]


class ProjectLoadError(RuntimeError):
    """Raised for any project file that can't be safely loaded: a
    missing file, invalid JSON, an unsupported format version, or
    malformed stroke data. Callers should show this message to the
    user rather than let it crash the app."""


def _color_to_hex(color: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def _hex_to_color(value: str) -> Tuple[int, int, int]:
    text = str(value).lstrip("#")
    if len(text) != 6:
        raise ProjectLoadError(f"Invalid color value: {value!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as exc:
        raise ProjectLoadError(f"Invalid color value: {value!r}") from exc


def _stroke_to_dict(stroke: Stroke) -> Dict[str, Any]:
    return {
        "points": [[round(x, 2), round(y, 2)] for x, y in stroke.points],
        "point_times": [round(t, 4) for t in stroke.point_times],
        "color": _color_to_hex(stroke.color),
        "size": stroke.size,
        "opacity": stroke.opacity,
        "brush_type": stroke.brush_type.value,
        "created_at": stroke.created_at,
    }


def _stroke_from_dict(data: Dict[str, Any], index: int) -> Stroke:
    if not isinstance(data, dict):
        raise ProjectLoadError(f"Stroke #{index} is not an object")
    try:
        points = [(float(p[0]), float(p[1])) for p in data["points"]]
        color = _hex_to_color(data["color"])
        size = float(data["size"])
        opacity = float(data.get("opacity", 1.0))
        created_at = float(data.get("created_at", time.time()))
        point_times = [float(t) for t in data.get("point_times", [])]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ProjectLoadError(f"Stroke #{index} is malformed: {exc}") from exc

    if not points:
        raise ProjectLoadError(f"Stroke #{index} has no points")
    if len(point_times) != len(points):
        point_times = []  # length mismatch -- replay falls back to even spacing

    brush_type_value = data.get("brush_type", BrushType.SMOOTH_INK.value)
    try:
        brush_type = BrushType(brush_type_value)
    except ValueError:
        brush_type = BrushType.SMOOTH_INK  # forward-compat: unknown future brush -> safe fallback

    return Stroke(
        points=points, point_times=point_times, color=color, size=size,
        opacity=opacity, brush_type=brush_type, created_at=created_at,
    )


def project_to_dict(canvas_model: CanvasModel, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "version": PROJECT_FORMAT_VERSION,
        "canvas": {"width": canvas_model.width, "height": canvas_model.height},
        "background": _color_to_hex(canvas_model.background_color),
        "saved_at": time.time(),
        "metadata": metadata or {},
        "strokes": [_stroke_to_dict(s) for s in canvas_model.strokes],
    }


def save_project(path: PathLike, canvas_model: CanvasModel, metadata: Optional[Dict[str, Any]] = None) -> Path:
    """Write `canvas_model` to `path` as JSON.

    Writes to a temporary file in the same directory and renames it
    into place, so a crash or power loss mid-save can't leave a
    half-written, corrupted project file behind.
    """
    path = Path(path)
    payload = project_to_dict(canvas_model, metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(path)
    return path


def load_project(path: PathLike) -> Tuple[CanvasModel, Dict[str, Any]]:
    """Read a `.aircanvas` project file and return (CanvasModel, metadata).

    Raises:
        ProjectLoadError: for a missing file, invalid JSON, an
            unsupported format version, or malformed stroke data --
            always with a clear message, never a raw crash.
    """
    path = Path(path)
    if not path.exists():
        raise ProjectLoadError(f"Project file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ProjectLoadError(f"'{path.name}' is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ProjectLoadError(f"Could not read '{path.name}': {exc}") from exc

    if not isinstance(payload, dict):
        raise ProjectLoadError(f"'{path.name}' does not contain a project object")

    version = payload.get("version")
    if version != PROJECT_FORMAT_VERSION:
        raise ProjectLoadError(
            f"Unsupported project format version {version!r} (expected {PROJECT_FORMAT_VERSION}) "
            f"in '{path.name}' -- it may have been saved by a different version of AirCanvas."
        )

    try:
        canvas_info = payload["canvas"]
        width = int(canvas_info["width"])
        height = int(canvas_info["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectLoadError(f"'{path.name}' has an invalid or missing canvas section: {exc}") from exc

    background = _hex_to_color(payload.get("background", "#121218"))

    strokes_data = payload.get("strokes", [])
    if not isinstance(strokes_data, list):
        raise ProjectLoadError(f"'{path.name}' has an invalid strokes section")

    model = CanvasModel(width=width, height=height, background_color=background)
    for i, stroke_data in enumerate(strokes_data):
        model.add_stroke(_stroke_from_dict(stroke_data, i))

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return model, metadata


def export_png(path: PathLike, canvas_surface: "pygame.Surface") -> Path:
    """Save the current canvas surface as a flat PNG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(canvas_surface, str(path))
    return path
