"""
Phase 8 application shell — the complete, demo-ready AirCanvas.

Everything from Phases 1-7 (tracking, gesture intent, brushes,
particles/Living Ink, save/export/replay, themes/sound/persistence),
plus:

  * H toggles an in-app help overlay -- a compact gesture and keyboard
    cheat-sheet drawn right on the canvas panel, so a first-time user
    (or someone recording a demo) never has to leave the app to learn
    the controls. "Press H for help" is always visible in the status
    bar as a standing hint. While help is open, Esc closes it instead
    of quitting the app -- Q still quits from anywhere.
  * The CLI now lives in aircanvas/cli.py, importable from main.py,
    `python -m aircanvas`, and the `aircanvas` console script
    installed via pyproject.toml, so all three launch paths share one
    implementation.
"""
from __future__ import annotations

import dataclasses
import logging
import random
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

from aircanvas.audio.manager import AudioManager
from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType, SELECTABLE_BRUSHES
from aircanvas.canvas.model import CanvasModel
from aircanvas.canvas.replay import ReplayController
from aircanvas.canvas.shape_assist import ShapeMatch, classify_stroke
from aircanvas.canvas.stroke import Stroke
from aircanvas.config import AppConfig, get_exports_dir, get_projects_dir, get_recovery_path
from aircanvas.interaction.dev_input import DevIntentSource
from aircanvas.interaction.intent import FrameIntent, IntentResolver
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig
from aircanvas.persistence.project_io import ProjectLoadError, export_png, load_project, save_project
from aircanvas.persistence.settings import AppSettings, load_settings, save_settings
from aircanvas.persistence.share_card import build_share_card
from aircanvas.rendering.effects import LivingInkEmitter
from aircanvas.rendering.particles import ParticleSystem
from aircanvas.rendering.themes import Theme, get_theme, next_theme_name
from aircanvas.ui.toolbar import Toolbar, ToolbarResult, Widget
from aircanvas.vision.calibration import Calibrator, MapperConfig
from aircanvas.vision.camera import Camera, CameraError
from aircanvas.vision.smoothing import SmoothingConfig
from aircanvas.vision.tracker import HAND_CONNECTIONS, HandResult, HandTracker, ModelUnavailableError

logger = logging.getLogger("aircanvas.app")

WINDOW_TITLE = "AirCanvas — Paint Without Touching Anything"
PREVIEW_PANEL_WIDTH = 260
TOOLBAR_WIDTH = 176
MARGIN = 14
PADDING = 10
STATUS_BAR_HEIGHT = 30
REPLAY_BAR_HEIGHT = 8
VOLUME_STEP = 0.1

SWATCH_SIZE = 40
SWATCH_GAP = 8
SWATCH_COLUMNS = 3
SIZE_BTN_SIZE = 26
SIZE_BTN_GAP = 6
BRUSH_BTN_WIDTH = 74
BRUSH_BTN_HEIGHT = 26
BRUSH_BTN_GAP = 6
BRUSH_BTN_COLUMNS = 2
UNDO_REDO_HEIGHT = 34
SECTION_GAP = 16

# Short labels for the toolbar's brush-type buttons (toolbar is narrow).
_BRUSH_LABELS = {
    BrushType.SMOOTH_INK: "Ink",
    BrushType.NEON_GLOW: "Glow",
    BrushType.SOFT_MARKER: "Marker",
    BrushType.PARTICLE: "Particle",
    BrushType.RAINBOW_FLOW: "Rainbow",
    BrushType.SPARK: "Spark",
}

_STATE_COLORS = {
    IntentState.IDLE: (110, 110, 110),
    IntentState.HAND_DETECTED: (190, 190, 190),
    IntentState.POINTER_ACTIVE: (235, 235, 235),
    IntentState.DRAWING: (70, 220, 90),
    IntentState.ERASING: (70, 150, 255),
    IntentState.UI_INTERACTION: (255, 200, 0),
    IntentState.HAND_LOST: (230, 60, 60),
}


# -- Layout -----------------------------------------------------------------

def _grid_height(item_count: int, columns: int, item_size: int, gap: int) -> int:
    """Height of a `columns`-wide grid of `item_count` same-size items."""
    rows = -(-item_count // columns)  # ceil div
    return rows * item_size + (rows - 1) * gap


def _toolbar_content_height(config: AppConfig) -> int:
    """Total vertical space the toolbar's widgets need, independent of
    where the toolbar is positioned -- computed once so Layout can
    size the window correctly without a chicken-and-egg rebuild.
    Uses the exact same per-section arithmetic as _build_toolbar, so
    the two can't silently drift apart."""
    height = PADDING
    height += _grid_height(len(config.brush_palette), SWATCH_COLUMNS, SWATCH_SIZE, SWATCH_GAP)
    height += SECTION_GAP + SIZE_BTN_SIZE
    height += SECTION_GAP + _grid_height(len(SELECTABLE_BRUSHES), BRUSH_BTN_COLUMNS, BRUSH_BTN_HEIGHT, BRUSH_BTN_GAP)
    height += SECTION_GAP + UNDO_REDO_HEIGHT
    height += PADDING
    return height


class Layout:
    """Fixed panel geometry: [toolbar] [preview (optional)] [canvas]."""

    def __init__(self, config: AppConfig, show_preview: bool) -> None:
        preview_w = PREVIEW_PANEL_WIDTH if show_preview else 0
        preview_h = int(PREVIEW_PANEL_WIDTH * config.camera_height / config.camera_width) if show_preview else 0

        self.toolbar_rect = pygame.Rect(MARGIN, MARGIN, TOOLBAR_WIDTH, _toolbar_content_height(config))
        self.preview_rect = (
            pygame.Rect(self.toolbar_rect.right + MARGIN, MARGIN, preview_w, preview_h) if show_preview else None
        )
        canvas_x = (self.preview_rect.right if self.preview_rect else self.toolbar_rect.right) + MARGIN
        self.canvas_rect = pygame.Rect(canvas_x, MARGIN, config.canvas_pixel_width, config.canvas_pixel_height)

        self.window_width = self.canvas_rect.right + MARGIN
        self.window_height = (
            max(self.canvas_rect.bottom, self.toolbar_rect.bottom, MARGIN + preview_h) + MARGIN + STATUS_BAR_HEIGHT
        )
        self.status_rect = pygame.Rect(0, self.window_height - STATUS_BAR_HEIGHT, self.window_width, STATUS_BAR_HEIGHT)


def _build_toolbar(layout: Layout, config: AppConfig) -> Toolbar:
    """Lay out color swatches, brush-type buttons, size presets, and
    undo/redo inside layout.toolbar_rect, as absolute-positioned
    Widgets. Mirrors _toolbar_content_height's arithmetic exactly."""
    x0 = layout.toolbar_rect.x + PADDING
    y = layout.toolbar_rect.y + PADDING
    widgets: List[Widget] = []

    for i, color in enumerate(config.brush_palette):
        col, row = i % SWATCH_COLUMNS, i // SWATCH_COLUMNS
        rect = pygame.Rect(
            x0 + col * (SWATCH_SIZE + SWATCH_GAP), y + row * (SWATCH_SIZE + SWATCH_GAP), SWATCH_SIZE, SWATCH_SIZE
        )
        widgets.append(Widget(id=f"color:{i}", rect=rect, swatch_color=color))
    y += _grid_height(len(config.brush_palette), SWATCH_COLUMNS, SWATCH_SIZE, SWATCH_GAP) + SECTION_GAP

    for i, size in enumerate(config.brush_sizes):
        rect = pygame.Rect(x0 + i * (SIZE_BTN_SIZE + SIZE_BTN_GAP), y, SIZE_BTN_SIZE, SIZE_BTN_SIZE)
        widgets.append(Widget(id=f"size:{i}", rect=rect, label=str(size)))
    y += SIZE_BTN_SIZE + SECTION_GAP

    for i, brush_type in enumerate(SELECTABLE_BRUSHES):
        col, row = i % BRUSH_BTN_COLUMNS, i // BRUSH_BTN_COLUMNS
        rect = pygame.Rect(
            x0 + col * (BRUSH_BTN_WIDTH + BRUSH_BTN_GAP), y + row * (BRUSH_BTN_HEIGHT + BRUSH_BTN_GAP),
            BRUSH_BTN_WIDTH, BRUSH_BTN_HEIGHT,
        )
        widgets.append(Widget(id=f"brush:{i}", rect=rect, label=_BRUSH_LABELS[brush_type]))
    y += _grid_height(len(SELECTABLE_BRUSHES), BRUSH_BTN_COLUMNS, BRUSH_BTN_HEIGHT, BRUSH_BTN_GAP) + SECTION_GAP

    inner_width = layout.toolbar_rect.width - 2 * PADDING
    half = (inner_width - 8) // 2
    widgets.append(Widget(id="undo", rect=pygame.Rect(x0, y, half, UNDO_REDO_HEIGHT), label="Undo"))
    widgets.append(Widget(id="redo", rect=pygame.Rect(x0 + half + 8, y, half, UNDO_REDO_HEIGHT), label="Redo"))

    return Toolbar(widgets)


class _BrushSelection:
    """Tracks the current size/color/brush-type the toolbar (or
    keyboard, as a fallback) has selected."""

    def __init__(self, config: AppConfig) -> None:
        self._sizes = list(config.brush_sizes)
        self._colors = list(config.brush_palette)
        self._brush_types = list(SELECTABLE_BRUSHES)
        self.size_index = min(config.default_brush_size_index, len(self._sizes) - 1)
        self.color_index = min(config.default_palette_index, len(self._colors) - 1)
        self.brush_type_index = min(config.default_brush_type_index, len(self._brush_types) - 1)

    @property
    def size(self) -> float:
        return float(self._sizes[self.size_index])

    @property
    def color(self) -> Tuple[int, int, int]:
        return self._colors[self.color_index]

    @property
    def brush_type(self) -> BrushType:
        return self._brush_types[self.brush_type_index]

    def cycle_size(self, direction: int) -> None:
        self.size_index = (self.size_index + direction) % len(self._sizes)

    def cycle_color(self) -> None:
        self.color_index = (self.color_index + 1) % len(self._colors)

    def cycle_brush_type(self) -> None:
        self.brush_type_index = (self.brush_type_index + 1) % len(self._brush_types)

    def sync_widget_selection(self, toolbar: Toolbar) -> None:
        for widget in toolbar.widgets:
            if widget.id.startswith("color:"):
                widget.is_selected = widget.id == f"color:{self.color_index}"
            elif widget.id.startswith("size:"):
                widget.is_selected = widget.id == f"size:{self.size_index}"
            elif widget.id.startswith("brush:"):
                widget.is_selected = widget.id == f"brush:{self.brush_type_index}"


def _dispatch_toolbar_action(
    widget_id: str,
    selection: "_BrushSelection",
    canvas_model: CanvasModel,
    brush_engine: BrushEngine,
    canvas_surface: "pygame.Surface",
    audio: Optional[AudioManager] = None,
) -> None:
    if widget_id.startswith("color:"):
        selection.color_index = int(widget_id.split(":", 1)[1])
        if audio:
            audio.play("color_select")
    elif widget_id.startswith("size:"):
        selection.size_index = int(widget_id.split(":", 1)[1])
        if audio:
            audio.play("size_select")
    elif widget_id.startswith("brush:"):
        selection.brush_type_index = int(widget_id.split(":", 1)[1])
        if audio:
            audio.play("tool_select")
    elif widget_id == "undo":
        canvas_model.undo()
        brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
        if audio:
            audio.play("undo")
    elif widget_id == "redo":
        canvas_model.redo()
        brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
        if audio:
            audio.play("redo")


# -- Canvas drawing -----------------------------------------------------------

def _finalize_pending_stroke(
    intent: FrameIntent,
    brush_engine: BrushEngine,
    canvas_model: CanvasModel,
    canvas_surface: "pygame.Surface",
    shape_assist_enabled: bool = False,
    shape_assist_min_points: int = 8,
) -> Optional[ShapeMatch]:
    """Ends whatever draw/erase stroke is in progress, if the gesture
    that started it just ended -- regardless of where the cursor
    currently is. Always called, every frame, independent of whether
    the cursor is over the canvas, the toolbar, or neither.

    When a DRAWING stroke ends (never an eraser stroke -- "correcting"
    an erase into a shape would make no sense) and shape assist is
    enabled, tries to recognize it via canvas/shape_assist.py. If it
    matches, the rough stroke is replaced with the idealized one
    (same color/size/opacity/brush_type) and the canvas is fully
    re-rendered -- needed because the rough version was already
    painted onto canvas_surface incrementally while it was being
    drawn, so a full render_full is the simplest correct way to
    discard it in favor of the clean version. Returns the ShapeMatch
    when a correction happened, so the caller can show feedback (a
    sound, a particle burst, a status message) -- None otherwise.
    """
    if not (intent.stroke_ended or intent.erase_ended):
        return None

    finished = brush_engine.end_stroke()
    if finished is None:
        return None

    match = None
    if shape_assist_enabled and intent.stroke_ended:
        match = classify_stroke(finished.points, min_points=shape_assist_min_points)

    if match is not None:
        snapped = Stroke(
            points=match.points, color=finished.color, size=finished.size,
            opacity=finished.opacity, brush_type=finished.brush_type, created_at=finished.created_at,
        )
        canvas_model.add_stroke(snapped)
        brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
        return match

    canvas_model.add_stroke(finished)
    return None


def _continue_canvas_drawing(
    canvas_local_intent: FrameIntent,
    brush_engine: BrushEngine,
    canvas_model: CanvasModel,
    canvas_surface: "pygame.Surface",
    color: Tuple[int, int, int],
    size: float,
    brush_type: BrushType,
    audio: Optional[AudioManager] = None,
) -> None:
    """Handles starting/extending a stroke. Only called when the
    cursor is over the canvas panel; `canvas_local_intent.cursor_pos`
    must already be canvas-local (not window) coordinates."""
    intent = canvas_local_intent
    if intent.is_drawing:
        if intent.stroke_started:
            brush_engine.begin_stroke(canvas_surface, *intent.cursor_pos, color=color, size=size, brush_type=brush_type)
            if audio:
                audio.play("brush_activate")
        else:
            brush_engine.extend_stroke(canvas_surface, *intent.cursor_pos)
    elif intent.is_erasing:
        if intent.erase_started:
            brush_engine.begin_stroke(
                canvas_surface, *intent.cursor_pos,
                color=canvas_model.background_color, size=size, opacity=1.0, brush_type=BrushType.ERASER,
            )
            if audio:
                audio.play("erase")
        else:
            brush_engine.extend_stroke(canvas_surface, *intent.cursor_pos)


def _route_intent(
    intent: FrameIntent,
    layout: Layout,
    toolbar: Toolbar,
    selection: _BrushSelection,
    canvas_model: CanvasModel,
    brush_engine: BrushEngine,
    canvas_surface: "pygame.Surface",
    audio: Optional[AudioManager] = None,
    shape_assist_enabled: bool = False,
    shape_assist_min_points: int = 8,
) -> Tuple[Optional[ToolbarResult], Optional[ShapeMatch]]:
    """Every frame's single dispatch point: ends any finishing
    stroke (applying shape assist if enabled), then sends the cursor
    to whichever panel it's over -- toolbar, canvas, or neither (a
    no-op, e.g. hovering the preview panel or the open-palm "pause"
    state).

    Returns (toolbar_result, shape_match): toolbar_result is the
    toolbar's hover/activation result when the toolbar was the
    target, for the renderer to draw hover/dwell feedback (None
    otherwise); shape_match is set on exactly the frame a shape-assist
    correction happened, for the caller to show feedback (a sound, a
    particle burst, a status message).
    """
    shape_match = _finalize_pending_stroke(
        intent, brush_engine, canvas_model, canvas_surface, shape_assist_enabled, shape_assist_min_points
    )

    pos = intent.cursor_pos
    if intent.state == IntentState.UI_INTERACTION or pos is None:
        return None, shape_match  # open palm = deliberate pause; nothing to route

    if layout.toolbar_rect.collidepoint(pos):
        result = toolbar.update(pos, selecting=intent.is_drawing)
        if result.activated_id:
            _dispatch_toolbar_action(result.activated_id, selection, canvas_model, brush_engine, canvas_surface, audio)
        return result, shape_match

    if layout.canvas_rect.collidepoint(pos):
        local = (pos[0] - layout.canvas_rect.x, pos[1] - layout.canvas_rect.y)
        local_intent = dataclasses.replace(intent, cursor_pos=local)
        _continue_canvas_drawing(
            local_intent, brush_engine, canvas_model, canvas_surface,
            selection.color, selection.size, selection.brush_type, audio,
        )
    return None, shape_match


# -- Resolver / camera helpers (unchanged in spirit from Phase 2/3) ---------

def _build_resolver(config: AppConfig, target_width: int, target_height: int) -> IntentResolver:
    smoothing_config = SmoothingConfig(
        min_alpha=config.smoothing_min_alpha,
        max_alpha=config.smoothing_max_alpha,
        velocity_lower=config.smoothing_velocity_lower,
        velocity_upper=config.smoothing_velocity_upper,
        min_movement_threshold=config.smoothing_min_movement_threshold,
    )
    mapper_config = MapperConfig(
        margin_left=config.canvas_margin, margin_right=config.canvas_margin,
        margin_top=config.canvas_margin, margin_bottom=config.canvas_margin,
        sensitivity=config.pointer_sensitivity,
    )
    state_config = StateMachineConfig(
        debounce_frames=config.gesture_debounce_frames,
        hand_lost_grace_frames=config.hand_lost_grace_frames,
        fist_confirm_frames=config.fist_confirm_frames,
    )
    return IntentResolver(
        canvas_width=target_width, canvas_height=target_height,
        smoothing_config=smoothing_config, mapper_config=mapper_config, state_config=state_config,
        pinch_threshold=config.pinch_threshold,
    )


def _frame_to_surface(frame_bgr: np.ndarray) -> "pygame.Surface":
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))


def _draw_camera_overlay(frame: np.ndarray, hands, intent: FrameIntent, calibrator: Calibrator) -> None:
    height, width = frame.shape[:2]
    for hand in hands:
        points = hand.pixel_landmarks(width, height)
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], (0, 220, 255), 2, cv2.LINE_AA)
        for x, y in points:
            cv2.circle(frame, (x, y), 3, (255, 255, 255), -1, cv2.LINE_AA)

    color = _STATE_COLORS.get(intent.state, (255, 255, 255))
    if intent.raw_pos is not None:
        rx, ry = int(intent.raw_pos[0] * width), int(intent.raw_pos[1] * height)
        cv2.circle(frame, (rx, ry), 5, (0, 0, 255), 1, cv2.LINE_AA)

    label = intent.state.value
    if intent.clear_progress > 0.0:
        label += f"  clear {intent.clear_progress * 100:.0f}%"
    cv2.putText(frame, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)

    if not calibrator.is_complete:
        remaining = "top-left (1)" if not calibrator.has_top_left else "bottom-right (2)"
        cv2.putText(
            frame, f"Calibrate: {remaining}", (8, height - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA,
        )


def _mouse_window_pos(layout: Layout) -> Tuple[int, int]:
    mx, my = pygame.mouse.get_pos()
    return (
        max(0, min(mx, layout.window_width - 1)),
        max(0, min(my, layout.window_height - 1)),
    )


# -- Rendering ----------------------------------------------------------------

def _draw_toolbar(
    screen: "pygame.Surface",
    toolbar: Toolbar,
    hover: Optional[Tuple[Optional[str], float]],
    font: "pygame.font.Font",
    theme: Theme,
    effects_enabled: bool = True,
) -> None:
    hovered_id, hover_progress = hover if hover else (None, 0.0)
    for widget in toolbar.widgets:
        is_hovered = widget.id == hovered_id
        if widget.swatch_color is not None:
            pygame.draw.rect(screen, widget.swatch_color, widget.rect, border_radius=6)
            border_color = theme.widget_border_selected if widget.is_selected else theme.widget_border
            pygame.draw.rect(screen, border_color, widget.rect, width=3 if widget.is_selected else 1, border_radius=6)
        else:
            base = theme.widget_selected_bg if widget.is_selected else theme.widget_bg
            pygame.draw.rect(screen, base, widget.rect, border_radius=5)
            pygame.draw.rect(screen, theme.widget_border, widget.rect, width=1, border_radius=5)
            if widget.label:
                text = font.render(widget.label, True, theme.widget_text)
                text_rect = text.get_rect(center=widget.rect.center)
                if text_rect.width > widget.rect.width - 4:
                    text = pygame.transform.smoothscale(
                        text, (widget.rect.width - 4, max(1, int(text.get_height() * (widget.rect.width - 4) / text.get_width())))
                    )
                    text_rect = text.get_rect(center=widget.rect.center)
                screen.blit(text, text_rect)

        if is_hovered and hover_progress > 0.0:
            if effects_enabled:
                fill_h = max(2, int(widget.rect.height * hover_progress))
                fill_rect = pygame.Rect(widget.rect.x, widget.rect.bottom - fill_h, widget.rect.width, fill_h)
                glow = pygame.Surface((fill_rect.width, fill_rect.height), pygame.SRCALPHA)
                glow.fill((*theme.hover_glow, 90))
                screen.blit(glow, fill_rect.topleft)
            pygame.draw.rect(screen, theme.hover_glow, widget.rect, width=2, border_radius=5)


def _update_living_ink(
    intent: FrameIntent, emitter: LivingInkEmitter, color: Tuple[int, int, int], size: float, dt: float
) -> None:
    """Every frame's single Living Ink dispatch point -- a purely
    decorative overlay, see rendering/effects.py's module docstring."""
    pos = intent.cursor_pos
    if pos is None:
        return
    if intent.stroke_started:
        emitter.on_stroke_start(pos[0], pos[1], color, size)
    elif intent.is_drawing:
        emitter.on_stroke_point(pos[0], pos[1], color, size, velocity=intent.velocity, dt=dt)
    elif intent.stroke_ended:
        emitter.on_stroke_end(pos[0], pos[1], color, size)
    elif intent.state == IntentState.POINTER_ACTIVE:
        emitter.on_idle_point(pos[0], pos[1], color, size, dt=dt)


def _load_starting_canvas(config: AppConfig, open_path: Optional[str]) -> CanvasModel:
    """Resolve what canvas to start with, in priority order: an
    explicit --open path, then an unclean-shutdown recovery file, then
    a blank canvas. Never raises -- a bad file falls through to the
    next option with a clear message instead of crashing startup."""
    blank_kwargs = dict(
        width=config.canvas_pixel_width, height=config.canvas_pixel_height,
        background_color=config.canvas_background_color,
    )

    if open_path is not None:
        try:
            model, _ = load_project(open_path)
            model.resize(config.canvas_pixel_width, config.canvas_pixel_height)
            logger.info("Loaded project from %s (%d strokes)", open_path, model.stroke_count)
            return model
        except ProjectLoadError as exc:
            logger.error("Could not open %s: %s", open_path, exc)
            print(f"\nCould not open '{open_path}': {exc}\nStarting with a blank canvas instead.\n")
            return CanvasModel(**blank_kwargs)

    recovery_path = get_recovery_path()
    if recovery_path.exists():
        try:
            model, _ = load_project(recovery_path)
            model.resize(config.canvas_pixel_width, config.canvas_pixel_height)
            logger.info("Recovered unsaved work from a previous session (%d strokes).", model.stroke_count)
            print(f"\nRecovered unsaved work from a previous session ({model.stroke_count} strokes).\n")
            return model
        except ProjectLoadError as exc:
            logger.warning("Recovery file exists but could not be loaded (%s); starting blank.", exc)

    return CanvasModel(**blank_kwargs)


def _save_project_with_timestamp(canvas_model: CanvasModel) -> None:
    path = get_projects_dir() / f"aircanvas_{time.strftime('%Y%m%d_%H%M%S')}.aircanvas"
    try:
        save_project(path, canvas_model, metadata={"stroke_count": canvas_model.stroke_count})
        logger.info("Saved project to %s", path)
        print(f"\nSaved: {path}\n")
    except OSError as exc:
        logger.error("Could not save project: %s", exc)
        print(f"\nCould not save project: {exc}\n")


def _export_png_and_share_card(
    canvas_surface: "pygame.Surface", canvas_model: CanvasModel, audio: Optional[AudioManager] = None
) -> None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    export_dir = get_exports_dir()
    png_path = export_dir / f"aircanvas_{timestamp}.png"
    card_path = export_dir / f"aircanvas_{timestamp}_share.png"
    try:
        export_png(png_path, canvas_surface)
        build_share_card(
            png_path, card_path, title="AirCanvas Artwork",
            stroke_count=canvas_model.stroke_count, created_at=time.time(),
        )
        logger.info("Exported PNG to %s and share card to %s", png_path, card_path)
        print(f"\nExported: {png_path}\nShare card: {card_path}\n")
        if audio:
            audio.play("export_complete")
    except OSError as exc:
        logger.error("Could not export: %s", exc)
        print(f"\nCould not export: {exc}\n")


HELP_LINES = [
    "GESTURES",
    "  Point (index only) - move cursor      Pinch - draw / select toolbar",
    "  Two-finger (index+middle) - erase      Open palm - pause",
    "  Fist, held ~2/3s - clear canvas",
    "",
    "KEYBOARD",
    "  Z undo   X redo   [ ] size   Tab color   B brush style",
    "  S save   E export + share card   R replay   1/2/C calibrate",
    "  T theme   N mute   -/= volume   M mirror   P reduced effects",
    "  K shape assist (off by default)   Q/Esc quit   H toggle this help",
]


def _draw_help_overlay(screen: "pygame.Surface", layout: Layout, font: "pygame.font.Font", theme: Theme) -> None:
    box = layout.canvas_rect.inflate(-40, -40)
    overlay = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
    overlay.fill((*theme.panel_bg, 225))
    screen.blit(overlay, box.topleft)
    pygame.draw.rect(screen, theme.accent_color, box, width=2, border_radius=10)

    y = box.y + 24
    for line in HELP_LINES:
        color = theme.accent_color if line and not line.startswith(" ") else theme.widget_text
        screen.blit(font.render(line, True, color), (box.x + 30, y))
        y += 24


def _draw_replay_overlay(
    screen: "pygame.Surface", layout: Layout, controller: ReplayController, font: "pygame.font.Font", theme: Theme
) -> None:
    bar_rect = pygame.Rect(
        layout.canvas_rect.x, layout.canvas_rect.bottom + 6, layout.canvas_rect.width, REPLAY_BAR_HEIGHT
    )
    pygame.draw.rect(screen, theme.widget_bg, bar_rect, border_radius=4)
    fill_width = max(0, int(bar_rect.width * controller.progress))
    if fill_width > 0:
        fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_width, bar_rect.height)
        pygame.draw.rect(screen, theme.accent_color, fill_rect, border_radius=4)

    state = "Playing" if controller.is_playing else "Paused"
    label = (
        f"REPLAY  |  {state}  |  Speed {controller.speed:.2g}x  |  {controller.progress * 100:.0f}%  |  "
        "Space play/pause \u00b7 \u2190/\u2192 seek \u00b7 \u2191/\u2193 speed \u00b7 Home restart \u00b7 R exit"
    )
    text = font.render(label, True, theme.widget_text)
    label_bg = pygame.Rect(layout.canvas_rect.x, layout.canvas_rect.y, layout.canvas_rect.width, 26)
    overlay = pygame.Surface((label_bg.width, label_bg.height), pygame.SRCALPHA)
    overlay.fill((*theme.panel_bg, 190))
    screen.blit(overlay, label_bg.topleft)
    screen.blit(text, (label_bg.x + 8, label_bg.y + 5))


def run(config: AppConfig, mouse_mode: bool = False, open_path: Optional[str] = None) -> int:
    """Run the Phase 7 app. Returns a process exit code."""
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)

    settings = load_settings()

    camera: Optional[Camera] = None
    tracker: Optional[HandTracker] = None
    dev_source: Optional[DevIntentSource] = None
    resolver: Optional[IntentResolver] = None
    calibrator = Calibrator()

    if not mouse_mode:
        camera = Camera(
            index=config.camera_index, width=config.camera_width, height=config.camera_height,
            fps=config.camera_fps, mirror=settings.mirror,
            open_retries=config.camera_open_retries, retry_delay_sec=config.camera_retry_delay_sec,
        )
        try:
            camera.open()
        except CameraError as exc:
            logger.warning("Camera unavailable (%s) -- falling back to developer mouse mode.", exc)
            print(f"\nCamera setup failed: {exc}\nFalling back to developer mouse mode (see README).\n")
            camera = None
            mouse_mode = True

    if not mouse_mode:
        try:
            tracker = HandTracker(
                model_path=config.hand_model_path, num_hands=config.max_num_hands,
                min_hand_detection_confidence=config.min_hand_detection_confidence,
                min_hand_presence_confidence=config.min_hand_presence_confidence,
                min_tracking_confidence=config.min_tracking_confidence,
            )
        except ModelUnavailableError as exc:
            logger.warning("Hand-tracking model unavailable (%s) -- falling back to developer mouse mode.", exc)
            print(f"\nHand-tracking model unavailable: {exc}\nFalling back to developer mouse mode.\n")
            if camera is not None:
                camera.release()
            camera = None
            mouse_mode = True

    state_config = StateMachineConfig(
        debounce_frames=config.gesture_debounce_frames,
        hand_lost_grace_frames=config.hand_lost_grace_frames,
        fist_confirm_frames=config.fist_confirm_frames,
    )
    if mouse_mode:
        dev_source = DevIntentSource(state_config)

    layout = Layout(config, show_preview=not mouse_mode)
    toolbar = _build_toolbar(layout, config)

    if not mouse_mode:
        resolver = _build_resolver(config, layout.window_width, layout.window_height)

    screen = pygame.display.set_mode((layout.window_width, layout.window_height))
    font = pygame.font.SysFont("Menlo,Consolas,monospace", 16)
    widget_font = pygame.font.SysFont("Menlo,Consolas,monospace", 12)

    canvas_model = _load_starting_canvas(config, open_path)
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)

    selection = _BrushSelection(config)
    selection.color_index = min(settings.color_index, len(config.brush_palette) - 1)
    selection.size_index = min(settings.size_index, len(config.brush_sizes) - 1)
    selection.brush_type_index = min(settings.brush_type_index, len(SELECTABLE_BRUSHES) - 1)

    theme = get_theme(settings.theme)
    audio = AudioManager(master_volume=settings.master_volume, sfx_volume=settings.sfx_volume, muted=settings.muted)

    particles = ParticleSystem(max_particles=config.max_particles, rng=random.Random())
    living_ink = LivingInkEmitter(
        particles,
        base_emit_rate=config.living_ink_base_rate,
        velocity_to_rate_scale=config.living_ink_velocity_scale,
        idle_emit_rate=config.living_ink_idle_rate,
    )
    particles_enabled = settings.particles_enabled
    shape_assist_enabled = settings.shape_assist_enabled
    shape_toast_label: Optional[str] = None
    shape_toast_timer = 0.0

    replay_mode = False
    help_visible = False
    replay_controller: Optional[ReplayController] = None
    replay_surface = pygame.Surface((canvas_model.width, canvas_model.height))

    recovery_timer = 0.0

    clock = pygame.time.Clock()
    warned_stale = False
    running = True
    last_hover: Tuple[Optional[str], float] = (None, 0.0)

    logger.info("AirCanvas running (%s mode). Press Q to quit, H for help.", "mouse" if mouse_mode else "camera")

    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    help_visible = not help_visible
                elif help_visible:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        help_visible = False
                    # Help is a read-only overlay -- every other key is
                    # ignored while it's open, so nothing fires twice.
                elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_r:
                    if replay_mode:
                        replay_mode = False
                    else:
                        replay_controller = ReplayController(list(canvas_model.strokes))
                        replay_controller.play()
                        replay_mode = True
                        audio.play("replay_start")
                elif replay_mode:
                    if event.key == pygame.K_SPACE:
                        replay_controller.toggle()
                    elif event.key in (pygame.K_HOME, pygame.K_BACKSPACE):
                        replay_controller.restart()
                        replay_controller.play()
                    elif event.key == pygame.K_LEFT:
                        replay_controller.seek_relative(-0.05)
                    elif event.key == pygame.K_RIGHT:
                        replay_controller.seek_relative(0.05)
                    elif event.key == pygame.K_UP:
                        replay_controller.set_speed(replay_controller.speed * 2)
                    elif event.key == pygame.K_DOWN:
                        replay_controller.set_speed(replay_controller.speed / 2)
                elif event.key == pygame.K_z:
                    canvas_model.undo()
                    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
                    audio.play("undo")
                elif event.key == pygame.K_x:
                    canvas_model.redo()
                    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
                    audio.play("redo")
                elif event.key == pygame.K_LEFTBRACKET:
                    selection.cycle_size(-1)
                elif event.key == pygame.K_RIGHTBRACKET:
                    selection.cycle_size(1)
                elif event.key == pygame.K_TAB:
                    selection.cycle_color()
                elif event.key == pygame.K_b:
                    selection.cycle_brush_type()
                elif event.key == pygame.K_p:
                    particles_enabled = not particles_enabled
                    if not particles_enabled:
                        particles.clear()
                elif event.key == pygame.K_k:
                    shape_assist_enabled = not shape_assist_enabled
                    shape_toast_label = f"Shape assist {'on' if shape_assist_enabled else 'off'}"
                    shape_toast_timer = 1.2
                elif event.key == pygame.K_c and resolver is not None:
                    calibrator.reset()
                elif event.key == pygame.K_s:
                    _save_project_with_timestamp(canvas_model)
                elif event.key == pygame.K_e:
                    _export_png_and_share_card(canvas_surface, canvas_model, audio)
                elif event.key == pygame.K_t:
                    theme = get_theme(next_theme_name(theme.name))
                elif event.key == pygame.K_m and camera is not None:
                    camera.mirror = not camera.mirror
                elif event.key == pygame.K_n:
                    audio.toggle_mute()
                elif event.key == pygame.K_EQUALS:
                    audio.set_master_volume(audio.master_volume + VOLUME_STEP)
                elif event.key == pygame.K_MINUS:
                    audio.set_master_volume(audio.master_volume - VOLUME_STEP)

        hands: List[HandResult] = []
        frame = None
        if mouse_mode:
            window_pos = _mouse_window_pos(layout)
            buttons = pygame.mouse.get_pressed()
            keys = pygame.key.get_pressed()
            intent = dev_source.update(
                cursor_pos=window_pos, left_button=buttons[0], right_button=buttons[2], fist_key=keys[pygame.K_f],
            )
        else:
            frame = camera.read()
            if frame is None:
                if camera.consecutive_failures > 30 and not warned_stale:
                    logger.warning("No frames from the camera for a while -- is it still connected?")
                    warned_stale = True
                intent = resolver.update([])
            else:
                warned_stale = False
                hands = tracker.process(frame)
                intent = resolver.update(hands)

                keys = pygame.key.get_pressed()
                if not replay_mode:
                    if keys[pygame.K_1] and intent.raw_pos is not None:
                        calibrator.set_top_left(*intent.raw_pos)
                    if keys[pygame.K_2] and intent.raw_pos is not None:
                        calibrator.set_bottom_right(*intent.raw_pos)
                        if calibrator.is_complete:
                            resolver.apply_calibration(calibrator, sensitivity=config.pointer_sensitivity)

        if replay_mode:
            replay_controller.advance(dt)
            replay_controller.render(replay_surface, brush_engine, canvas_model.background_color)
            last_hover = (None, 0.0)
        elif help_visible:
            last_hover = (None, 0.0)
        else:
            selection.sync_widget_selection(toolbar)
            toolbar_result, shape_match = _route_intent(
                intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface, audio,
                shape_assist_enabled, config.shape_assist_min_points,
            )
            last_hover = (toolbar_result.hovered_id, toolbar_result.hover_progress) if toolbar_result else (None, 0.0)

            if shape_match is not None:
                audio.play("shape_snap")
                cx = sum(p[0] for p in shape_match.points) / len(shape_match.points)
                cy = sum(p[1] for p in shape_match.points) / len(shape_match.points)
                if particles_enabled:
                    living_ink.burst_at(
                        layout.canvas_rect.x + cx, layout.canvas_rect.y + cy, selection.color, selection.size
                    )
                shape_toast_label = f"\u2728 Snapped to {shape_match.label}"
                shape_toast_timer = 1.6

            if shape_toast_timer > 0.0:
                shape_toast_timer -= dt
                if shape_toast_timer <= 0.0:
                    shape_toast_label = None

            if intent.clear_confirmed:
                if canvas_model.clear():
                    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
                    audio.play("clear")

            if particles_enabled:
                _update_living_ink(intent, living_ink, selection.color, selection.size, dt)
                particles.update(dt)

            recovery_timer += dt
            if recovery_timer >= config.recovery_autosave_interval_sec:
                recovery_timer = 0.0
                try:
                    save_project(get_recovery_path(), canvas_model)
                except OSError as exc:
                    logger.warning("Recovery autosave failed: %s", exc)

        # -- Render --
        screen.fill(theme.panel_bg)

        pygame.draw.rect(screen, theme.toolbar_bg, layout.toolbar_rect.inflate(PADDING, PADDING), border_radius=8)
        _draw_toolbar(screen, toolbar, last_hover, widget_font, theme, effects_enabled=particles_enabled)

        screen.blit(replay_surface if replay_mode else canvas_surface, layout.canvas_rect.topleft)
        pygame.draw.rect(screen, theme.border_color, layout.canvas_rect, width=1)

        if layout.preview_rect is not None and frame is not None:
            _draw_camera_overlay(frame, hands, intent, calibrator)
            preview_surface = pygame.transform.smoothscale(
                _frame_to_surface(frame), (layout.preview_rect.width, layout.preview_rect.height)
            )
            screen.blit(preview_surface, layout.preview_rect.topleft)
            pygame.draw.rect(screen, theme.border_color, layout.preview_rect, width=1)

        if replay_mode:
            _draw_replay_overlay(screen, layout, replay_controller, widget_font, theme)
        else:
            if particles_enabled:
                particles.render(screen)
            if intent.cursor_pos is not None:
                ring_color = _STATE_COLORS.get(intent.state, (255, 255, 255))
                radius = max(int(selection.size / 2), 3) if layout.canvas_rect.collidepoint(intent.cursor_pos) else 6
                pygame.draw.circle(screen, ring_color, intent.cursor_pos, radius, 2)

        if help_visible:
            _draw_help_overlay(screen, layout, widget_font, theme)

        pygame.draw.rect(screen, theme.status_bg, layout.status_rect)
        fps = clock.get_fps()
        if help_visible:
            status = "HELP  |  Press H or Esc to close"
        elif replay_mode:
            status = f"REPLAY MODE  |  Press R to return to drawing  |  FPS {fps:.0f}"
        elif shape_toast_label is not None:
            status = shape_toast_label
        else:
            mute_label = "muted" if audio.muted else f"{int(audio.master_volume * 100)}%"
            status = (
                f"{'MOUSE' if mouse_mode else intent.state.value.upper()}  |  "
                f"{_BRUSH_LABELS.get(selection.brush_type, selection.brush_type.value)} {int(selection.size)}px  |  "
                f"Strokes {canvas_model.stroke_count}  |  "
                f"Undo:{'Y' if canvas_model.can_undo else 'n'} Redo:{'Y' if canvas_model.can_redo else 'n'}  |  "
                f"{'Particles:' + str(particles.count) if particles_enabled else 'Particles off'}  |  "
                f"{'Shape assist:on' if shape_assist_enabled else 'Shape assist:off'}  |  "
                f"{theme.name.capitalize()}  |  Vol {mute_label}  |  Press H for help  |  FPS {fps:.0f}"
            )
        screen.blit(font.render(status, True, theme.status_text), (layout.status_rect.x + 10, layout.status_rect.y + 6))

        pygame.display.flip()

    if tracker is not None:
        tracker.close()
    if camera is not None:
        camera.release()
    recovery_path = get_recovery_path()
    if recovery_path.exists():
        try:
            recovery_path.unlink()  # clean exit -- no need to offer recovery next launch
        except OSError:
            pass

    save_settings(AppSettings(
        theme=theme.name,
        brush_type_index=selection.brush_type_index,
        color_index=selection.color_index,
        size_index=selection.size_index,
        mirror=camera.mirror if camera is not None else settings.mirror,
        particles_enabled=particles_enabled,
        master_volume=audio.master_volume,
        sfx_volume=audio.sfx_volume,
        muted=audio.muted,
        shape_assist_enabled=shape_assist_enabled,
    ))

    pygame.quit()
    return 0
