"""
Phase 5 application shell.

Adds advanced brushes, particles, and the "Living Ink" signature
effect on top of Phase 4's touchless canvas + toolbar:

  * All six brush types (plus the eraser) are now selectable from the
    toolbar, each with its own distinct look -- see
    canvas/brush_engine.py for how they're rendered.
  * A bounded ParticleSystem + LivingInkEmitter (rendering/particles.py,
    rendering/effects.py) add fading motes that trail the cursor,
    trickle off an active stroke scaled by drawing speed, burst on a
    sharp direction change, and settle when a stroke starts/ends.
    This is a purely decorative overlay drawn on top of everything
    else each frame -- it never touches canvas_surface, so it has no
    effect on undo/redo/replay correctness.

Toolbar-vs-canvas routing, coordinate mapping, and calibration are
unchanged from Phase 4.
"""
from __future__ import annotations

import dataclasses
import logging
import random
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType, SELECTABLE_BRUSHES
from aircanvas.canvas.model import CanvasModel
from aircanvas.config import AppConfig
from aircanvas.interaction.dev_input import DevIntentSource
from aircanvas.interaction.intent import FrameIntent, IntentResolver
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig
from aircanvas.rendering.effects import LivingInkEmitter
from aircanvas.rendering.particles import ParticleSystem
from aircanvas.ui.toolbar import Toolbar, ToolbarResult, Widget
from aircanvas.vision.calibration import Calibrator, MapperConfig
from aircanvas.vision.camera import Camera, CameraError
from aircanvas.vision.smoothing import SmoothingConfig
from aircanvas.vision.tracker import HAND_CONNECTIONS, HandResult, HandTracker, ModelUnavailableError

logger = logging.getLogger("aircanvas.app")

WINDOW_TITLE = "AirCanvas — Phase 5"
PREVIEW_PANEL_WIDTH = 260
TOOLBAR_WIDTH = 176
MARGIN = 14
PADDING = 10
STATUS_BAR_HEIGHT = 30
PANEL_BG = (10, 10, 13)
TOOLBAR_BG = (22, 22, 27)
STATUS_TEXT_COLOR = (200, 200, 205)

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
) -> None:
    if widget_id.startswith("color:"):
        selection.color_index = int(widget_id.split(":", 1)[1])
    elif widget_id.startswith("size:"):
        selection.size_index = int(widget_id.split(":", 1)[1])
    elif widget_id.startswith("brush:"):
        selection.brush_type_index = int(widget_id.split(":", 1)[1])
    elif widget_id == "undo":
        canvas_model.undo()
        brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    elif widget_id == "redo":
        canvas_model.redo()
        brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)


# -- Canvas drawing -----------------------------------------------------------

def _finalize_pending_stroke(intent: FrameIntent, brush_engine: BrushEngine, canvas_model: CanvasModel) -> None:
    """Ends whatever draw/erase stroke is in progress, if the gesture
    that started it just ended -- regardless of where the cursor
    currently is. Always called, every frame, independent of whether
    the cursor is over the canvas, the toolbar, or neither."""
    if intent.stroke_ended or intent.erase_ended:
        finished = brush_engine.end_stroke()
        if finished is not None:
            canvas_model.add_stroke(finished)


def _continue_canvas_drawing(
    canvas_local_intent: FrameIntent,
    brush_engine: BrushEngine,
    canvas_model: CanvasModel,
    canvas_surface: "pygame.Surface",
    color: Tuple[int, int, int],
    size: float,
    brush_type: BrushType,
) -> None:
    """Handles starting/extending a stroke. Only called when the
    cursor is over the canvas panel; `canvas_local_intent.cursor_pos`
    must already be canvas-local (not window) coordinates."""
    intent = canvas_local_intent
    if intent.is_drawing:
        if intent.stroke_started:
            brush_engine.begin_stroke(canvas_surface, *intent.cursor_pos, color=color, size=size, brush_type=brush_type)
        else:
            brush_engine.extend_stroke(canvas_surface, *intent.cursor_pos)
    elif intent.is_erasing:
        if intent.erase_started:
            brush_engine.begin_stroke(
                canvas_surface, *intent.cursor_pos,
                color=canvas_model.background_color, size=size, opacity=1.0, brush_type=BrushType.ERASER,
            )
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
) -> Optional[ToolbarResult]:
    """Every frame's single dispatch point: ends any finishing
    stroke, then sends the cursor to whichever panel it's over --
    toolbar, canvas, or neither (a no-op, e.g. hovering the preview
    panel or the open-palm "pause" state). Returns the toolbar's
    hover/activation result when the toolbar was the target, for the
    renderer to draw hover/dwell feedback -- None otherwise."""
    _finalize_pending_stroke(intent, brush_engine, canvas_model)

    pos = intent.cursor_pos
    if intent.state == IntentState.UI_INTERACTION or pos is None:
        return None  # open palm = deliberate pause; nothing to route

    if layout.toolbar_rect.collidepoint(pos):
        result = toolbar.update(pos, selecting=intent.is_drawing)
        if result.activated_id:
            _dispatch_toolbar_action(result.activated_id, selection, canvas_model, brush_engine, canvas_surface)
        return result

    if layout.canvas_rect.collidepoint(pos):
        local = (pos[0] - layout.canvas_rect.x, pos[1] - layout.canvas_rect.y)
        local_intent = dataclasses.replace(intent, cursor_pos=local)
        _continue_canvas_drawing(
            local_intent, brush_engine, canvas_model, canvas_surface, selection.color, selection.size, selection.brush_type
        )
    return None


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
    screen: "pygame.Surface", toolbar: Toolbar, hover: Optional[Tuple[Optional[str], float]], font: "pygame.font.Font"
) -> None:
    hovered_id, hover_progress = hover if hover else (None, 0.0)
    for widget in toolbar.widgets:
        is_hovered = widget.id == hovered_id
        if widget.swatch_color is not None:
            pygame.draw.rect(screen, widget.swatch_color, widget.rect, border_radius=6)
            border_color = (255, 255, 255) if widget.is_selected else (90, 90, 96)
            pygame.draw.rect(screen, border_color, widget.rect, width=3 if widget.is_selected else 1, border_radius=6)
        else:
            base = (60, 130, 90) if widget.is_selected else (46, 46, 52)
            pygame.draw.rect(screen, base, widget.rect, border_radius=5)
            pygame.draw.rect(screen, (110, 110, 118), widget.rect, width=1, border_radius=5)
            if widget.label:
                text = font.render(widget.label, True, (225, 225, 230))
                text_rect = text.get_rect(center=widget.rect.center)
                if text_rect.width > widget.rect.width - 4:
                    text = pygame.transform.smoothscale(
                        text, (widget.rect.width - 4, max(1, int(text.get_height() * (widget.rect.width - 4) / text.get_width())))
                    )
                    text_rect = text.get_rect(center=widget.rect.center)
                screen.blit(text, text_rect)

        if is_hovered and hover_progress > 0.0:
            fill_h = max(2, int(widget.rect.height * hover_progress))
            fill_rect = pygame.Rect(widget.rect.x, widget.rect.bottom - fill_h, widget.rect.width, fill_h)
            glow = pygame.Surface((fill_rect.width, fill_rect.height), pygame.SRCALPHA)
            glow.fill((255, 255, 255, 90))
            screen.blit(glow, fill_rect.topleft)
            pygame.draw.rect(screen, (255, 255, 255), widget.rect, width=2, border_radius=5)


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


def run(config: AppConfig, mouse_mode: bool = False) -> int:
    """Run the Phase 5 app. Returns a process exit code."""
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)

    camera: Optional[Camera] = None
    tracker: Optional[HandTracker] = None
    dev_source: Optional[DevIntentSource] = None
    resolver: Optional[IntentResolver] = None
    calibrator = Calibrator()

    if not mouse_mode:
        camera = Camera(
            index=config.camera_index, width=config.camera_width, height=config.camera_height,
            fps=config.camera_fps, mirror=config.mirror,
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

    canvas_model = CanvasModel(
        width=config.canvas_pixel_width, height=config.canvas_pixel_height,
        background_color=config.canvas_background_color,
    )
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    selection = _BrushSelection(config)

    particles = ParticleSystem(max_particles=config.max_particles, rng=random.Random())
    living_ink = LivingInkEmitter(
        particles,
        base_emit_rate=config.living_ink_base_rate,
        velocity_to_rate_scale=config.living_ink_velocity_scale,
        idle_emit_rate=config.living_ink_idle_rate,
    )
    particles_enabled = config.particles_enabled

    clock = pygame.time.Clock()
    warned_stale = False
    running = True
    last_hover: Tuple[Optional[str], float] = (None, 0.0)

    logger.info("AirCanvas Phase 5 running (%s mode). Press Q to quit.", "mouse" if mouse_mode else "camera")

    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_z:
                    canvas_model.undo()
                    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
                elif event.key == pygame.K_x:
                    canvas_model.redo()
                    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
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
                elif event.key == pygame.K_c and resolver is not None:
                    calibrator.reset()

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
                if keys[pygame.K_1] and intent.raw_pos is not None:
                    calibrator.set_top_left(*intent.raw_pos)
                if keys[pygame.K_2] and intent.raw_pos is not None:
                    calibrator.set_bottom_right(*intent.raw_pos)
                    if calibrator.is_complete:
                        resolver.apply_calibration(calibrator, sensitivity=config.pointer_sensitivity)

        selection.sync_widget_selection(toolbar)
        toolbar_result = _route_intent(intent, layout, toolbar, selection, canvas_model, brush_engine, canvas_surface)
        last_hover = (toolbar_result.hovered_id, toolbar_result.hover_progress) if toolbar_result else (None, 0.0)

        if intent.clear_confirmed:
            if canvas_model.clear():
                brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)

        if particles_enabled:
            _update_living_ink(intent, living_ink, selection.color, selection.size, dt)
            particles.update(dt)

        # -- Render --
        screen.fill(PANEL_BG)

        pygame.draw.rect(screen, TOOLBAR_BG, layout.toolbar_rect.inflate(PADDING, PADDING), border_radius=8)
        _draw_toolbar(screen, toolbar, last_hover, widget_font)

        screen.blit(canvas_surface, layout.canvas_rect.topleft)
        pygame.draw.rect(screen, (60, 60, 66), layout.canvas_rect, width=1)

        if layout.preview_rect is not None and frame is not None:
            _draw_camera_overlay(frame, hands, intent, calibrator)
            preview_surface = pygame.transform.smoothscale(
                _frame_to_surface(frame), (layout.preview_rect.width, layout.preview_rect.height)
            )
            screen.blit(preview_surface, layout.preview_rect.topleft)
            pygame.draw.rect(screen, (60, 60, 66), layout.preview_rect, width=1)

        if particles_enabled:
            particles.render(screen)

        if intent.cursor_pos is not None:
            ring_color = _STATE_COLORS.get(intent.state, (255, 255, 255))
            radius = max(int(selection.size / 2), 3) if layout.canvas_rect.collidepoint(intent.cursor_pos) else 6
            pygame.draw.circle(screen, ring_color, intent.cursor_pos, radius, 2)

        pygame.draw.rect(screen, (16, 16, 20), layout.status_rect)
        fps = clock.get_fps()
        status = (
            f"{'MOUSE' if mouse_mode else intent.state.value.upper()}  |  "
            f"{_BRUSH_LABELS.get(selection.brush_type, selection.brush_type.value)} {int(selection.size)}px  |  "
            f"Strokes {canvas_model.stroke_count}  |  "
            f"Undo:{'Y' if canvas_model.can_undo else 'n'} Redo:{'Y' if canvas_model.can_redo else 'n'}  |  "
            f"{'Particles:' + str(particles.count) if particles_enabled else 'Particles off'}  |  FPS {fps:.0f}"
        )
        screen.blit(font.render(status, True, STATUS_TEXT_COLOR), (layout.status_rect.x + 10, layout.status_rect.y + 6))

        pygame.display.flip()

    if tracker is not None:
        tracker.close()
    if camera is not None:
        camera.release()
    pygame.quit()
    return 0
