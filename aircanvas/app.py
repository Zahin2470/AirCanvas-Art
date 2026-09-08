"""
Phase 3 application shell.

This is where the real drawing canvas takes over as a pygame window,
replacing the temporary OpenCV debug preview from Phases 1-2. Layout:
a webcam preview panel (hand skeleton + intent overlay, baked in with
the same OpenCV drawing helpers as before) alongside the actual art
canvas, plus a thin status bar.

The interaction pipeline itself (camera -> tracker -> IntentResolver)
is unchanged from Phase 2; this phase's new work is wiring its output
into aircanvas.canvas: starting/extending/ending strokes through
BrushEngine, and recording them in CanvasModel for undo/redo.

Touchless color/size/tool controls are Phase 4 -- for now, palette
and size are cycled with the keyboard, same temporary-dev-tool
pattern as Phase 2's calibration keys.

Developer mode (--mouse, or an automatic fallback if the camera can't
open) drives the exact same brush/canvas code through
interaction.dev_input.DevIntentSource instead of a real hand, so the
whole app is testable without a webcam.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.model import CanvasModel
from aircanvas.config import AppConfig
from aircanvas.interaction.dev_input import DevIntentSource
from aircanvas.interaction.intent import FrameIntent, IntentResolver
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig
from aircanvas.vision.calibration import Calibrator, MapperConfig
from aircanvas.vision.camera import Camera, CameraError
from aircanvas.vision.smoothing import SmoothingConfig
from aircanvas.vision.tracker import HAND_CONNECTIONS, HandResult, HandTracker, ModelUnavailableError

logger = logging.getLogger("aircanvas.app")

WINDOW_TITLE = "AirCanvas — Phase 3"
PREVIEW_PANEL_WIDTH = 320
MARGIN = 14
STATUS_BAR_HEIGHT = 30
PANEL_BG = (10, 10, 13)
STATUS_TEXT_COLOR = (200, 200, 205)

_STATE_COLORS = {
    IntentState.IDLE: (110, 110, 110),
    IntentState.HAND_DETECTED: (190, 190, 190),
    IntentState.POINTER_ACTIVE: (235, 235, 235),
    IntentState.DRAWING: (70, 220, 90),
    IntentState.ERASING: (70, 150, 255),
    IntentState.UI_INTERACTION: (255, 200, 0),
    IntentState.HAND_LOST: (230, 60, 60),
}


def _build_resolver(config: AppConfig) -> IntentResolver:
    smoothing_config = SmoothingConfig(
        min_alpha=config.smoothing_min_alpha,
        max_alpha=config.smoothing_max_alpha,
        velocity_lower=config.smoothing_velocity_lower,
        velocity_upper=config.smoothing_velocity_upper,
        min_movement_threshold=config.smoothing_min_movement_threshold,
    )
    mapper_config = MapperConfig(
        margin_left=config.canvas_margin,
        margin_right=config.canvas_margin,
        margin_top=config.canvas_margin,
        margin_bottom=config.canvas_margin,
        sensitivity=config.pointer_sensitivity,
    )
    state_config = StateMachineConfig(
        debounce_frames=config.gesture_debounce_frames,
        hand_lost_grace_frames=config.hand_lost_grace_frames,
        fist_confirm_frames=config.fist_confirm_frames,
    )
    return IntentResolver(
        canvas_width=config.canvas_pixel_width,
        canvas_height=config.canvas_pixel_height,
        smoothing_config=smoothing_config,
        mapper_config=mapper_config,
        state_config=state_config,
        pinch_threshold=config.pinch_threshold,
    )


def _frame_to_surface(frame_bgr: np.ndarray) -> "pygame.Surface":
    """Convert an OpenCV BGR frame into a pygame Surface for blitting."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    # pygame expects a (width, height, 3) array; OpenCV gives (height, width, 3).
    return pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))


def _draw_camera_overlay(frame: np.ndarray, hands, intent: FrameIntent, calibrator: Calibrator) -> None:
    """Bake the hand skeleton + intent readout onto the raw camera
    frame with OpenCV, reusing the same drawing primitives as the
    Phase 1/2 debug preview, before it's converted to a pygame Surface
    for the preview panel. Cheaper than reimplementing this in pygame."""
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
    if intent.smoothed_pos is not None:
        sx, sy = int(intent.smoothed_pos[0] * width), int(intent.smoothed_pos[1] * height)
        cv2.circle(frame, (sx, sy), 9, color, 2, cv2.LINE_AA)

    label = f"{intent.state.value}"
    if intent.clear_progress > 0.0:
        label += f"  clear {intent.clear_progress * 100:.0f}%"
    cv2.putText(frame, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)

    if not calibrator.is_complete:
        remaining = "top-left (1)" if not calibrator.has_top_left else "bottom-right (2)"
        cv2.putText(
            frame, f"Calibrate: {remaining}", (8, height - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1, cv2.LINE_AA,
        )


class Layout:
    """Fixed panel geometry for the Phase 3 window."""

    def __init__(self, config: AppConfig, show_preview: bool) -> None:
        preview_w = PREVIEW_PANEL_WIDTH if show_preview else 0
        preview_h = int(PREVIEW_PANEL_WIDTH * config.camera_height / config.camera_width) if show_preview else 0

        self.canvas_rect = pygame.Rect(
            MARGIN + (preview_w + MARGIN if show_preview else 0),
            MARGIN,
            config.canvas_pixel_width,
            config.canvas_pixel_height,
        )
        self.preview_rect = pygame.Rect(MARGIN, MARGIN, preview_w, preview_h) if show_preview else None

        self.window_width = self.canvas_rect.right + MARGIN
        self.window_height = max(self.canvas_rect.bottom, MARGIN + preview_h) + MARGIN + STATUS_BAR_HEIGHT
        self.status_rect = pygame.Rect(0, self.window_height - STATUS_BAR_HEIGHT, self.window_width, STATUS_BAR_HEIGHT)


def _mouse_to_canvas(layout: "Layout") -> Optional[Tuple[int, int]]:
    mx, my = pygame.mouse.get_pos()
    if not layout.canvas_rect.collidepoint(mx, my):
        return None
    return (mx - layout.canvas_rect.x, my - layout.canvas_rect.y)


def _apply_intent_to_canvas(
    intent: FrameIntent,
    brush_engine: BrushEngine,
    canvas_model: CanvasModel,
    canvas_surface: "pygame.Surface",
    color: Tuple[int, int, int],
    size: float,
) -> None:
    """The one place drawing/erasing actually happens: turns this
    frame's FrameIntent into BrushEngine/CanvasModel calls. Identical
    whether `intent` came from a real hand or DevIntentSource."""
    if intent.is_drawing and intent.cursor_pos is not None:
        if intent.stroke_started:
            brush_engine.begin_stroke(canvas_surface, *intent.cursor_pos, color=color, size=size)
        else:
            brush_engine.extend_stroke(canvas_surface, *intent.cursor_pos)
    elif intent.stroke_ended:
        finished = brush_engine.end_stroke()
        if finished is not None:
            canvas_model.add_stroke(finished)

    if intent.is_erasing and intent.cursor_pos is not None:
        if intent.erase_started:
            brush_engine.begin_stroke(
                canvas_surface, *intent.cursor_pos,
                color=canvas_model.background_color, size=size, opacity=1.0, brush_type=BrushType.ERASER,
            )
        else:
            brush_engine.extend_stroke(canvas_surface, *intent.cursor_pos)
    elif intent.erase_ended:
        finished = brush_engine.end_stroke()
        if finished is not None:
            canvas_model.add_stroke(finished)


class _BrushSelection:
    """Tracks the current size/color presets the keyboard cycles
    through -- a stand-in for Phase 4's touchless color/size UI."""

    def __init__(self, config: AppConfig) -> None:
        self._sizes = list(config.brush_sizes)
        self._colors = list(config.brush_palette)
        self.size_index = min(config.default_brush_size_index, len(self._sizes) - 1)
        self.color_index = min(config.default_palette_index, len(self._colors) - 1)

    @property
    def size(self) -> float:
        return float(self._sizes[self.size_index])

    @property
    def color(self) -> Tuple[int, int, int]:
        return self._colors[self.color_index]

    def cycle_size(self, direction: int) -> None:
        self.size_index = (self.size_index + direction) % len(self._sizes)

    def cycle_color(self) -> None:
        self.color_index = (self.color_index + 1) % len(self._colors)


def run(config: AppConfig, mouse_mode: bool = False) -> int:
    """Run the Phase 3 app. Returns a process exit code."""
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

    if mouse_mode:
        dev_source = DevIntentSource(
            StateMachineConfig(
                debounce_frames=config.gesture_debounce_frames,
                hand_lost_grace_frames=config.hand_lost_grace_frames,
                fist_confirm_frames=config.fist_confirm_frames,
            )
        )
    else:
        resolver = _build_resolver(config)

    layout = Layout(config, show_preview=not mouse_mode)
    screen = pygame.display.set_mode((layout.window_width, layout.window_height))
    font = pygame.font.SysFont("Menlo,Consolas,monospace", 16)

    canvas_model = CanvasModel(
        width=config.canvas_pixel_width, height=config.canvas_pixel_height,
        background_color=config.canvas_background_color,
    )
    canvas_surface = pygame.Surface((canvas_model.width, canvas_model.height))
    brush_engine = BrushEngine()
    brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)
    selection = _BrushSelection(config)

    clock = pygame.time.Clock()
    warned_stale = False
    running = True

    logger.info("AirCanvas Phase 3 running (%s mode). Press Q to quit.", "mouse" if mouse_mode else "camera")

    while running:
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
                elif event.key == pygame.K_c and resolver is not None:
                    calibrator.reset()

        hands: List[HandResult] = []
        frame = None
        if mouse_mode:
            cursor = _mouse_to_canvas(layout)
            buttons = pygame.mouse.get_pressed()
            keys = pygame.key.get_pressed()
            intent = dev_source.update(
                cursor_pos=cursor, left_button=buttons[0], right_button=buttons[2], fist_key=keys[pygame.K_f],
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

        _apply_intent_to_canvas(intent, brush_engine, canvas_model, canvas_surface, selection.color, selection.size)

        if intent.clear_confirmed:
            if canvas_model.clear():
                brush_engine.render_full(canvas_surface, canvas_model.strokes, canvas_model.background_color)

        # -- Render --
        screen.fill(PANEL_BG)
        screen.blit(canvas_surface, layout.canvas_rect.topleft)
        pygame.draw.rect(screen, (60, 60, 66), layout.canvas_rect, width=1)

        if layout.preview_rect is not None and frame is not None:
            _draw_camera_overlay(frame, hands, intent, calibrator)
            preview_surface = pygame.transform.smoothscale(
                _frame_to_surface(frame), (layout.preview_rect.width, layout.preview_rect.height)
            )
            screen.blit(preview_surface, layout.preview_rect.topleft)
            pygame.draw.rect(screen, (60, 60, 66), layout.preview_rect, width=1)

        # Cursor indicator on the canvas panel itself.
        if intent.cursor_pos is not None:
            cx = layout.canvas_rect.x + intent.cursor_pos[0]
            cy = layout.canvas_rect.y + intent.cursor_pos[1]
            ring_color = _STATE_COLORS.get(intent.state, (255, 255, 255))
            pygame.draw.circle(screen, ring_color, (cx, cy), max(int(selection.size / 2), 3), 2)

        pygame.draw.rect(screen, (16, 16, 20), layout.status_rect)
        fps = clock.get_fps()
        status = (
            f"{'MOUSE' if mouse_mode else intent.state.value.upper()}  |  "
            f"Brush {int(selection.size)}px  |  Strokes {canvas_model.stroke_count}  |  "
            f"Undo:{'Y' if canvas_model.can_undo else 'n'} Redo:{'Y' if canvas_model.can_redo else 'n'}  |  "
            f"FPS {fps:.0f}"
        )
        screen.blit(font.render(status, True, STATUS_TEXT_COLOR), (layout.status_rect.x + 10, layout.status_rect.y + 6))

        pygame.display.flip()
        clock.tick(60)

    if tracker is not None:
        tracker.close()
    if camera is not None:
        camera.release()
    pygame.quit()
    return 0
