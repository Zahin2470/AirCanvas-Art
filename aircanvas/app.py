"""
Phase 2 application shell.

Extends the Phase 1 camera+tracker preview with the full interaction
pipeline: gesture classification, the debounced intent state machine,
pointer smoothing, and coordinate mapping (aircanvas.interaction.intent
.IntentResolver). The overlay now shows raw vs. smoothed fingertip
position, velocity, the current intent state/gesture, the mapped
canvas cursor, and fist-hold progress toward a clear action.

This OpenCV window is still a temporary developer tool. Starting in
Phase 3, the real drawing canvas takes over as a pygame window, and
this becomes an optional --debug overlay layered on top of it.

Calibration in this phase is keyboard-driven (press 1 / 2 to capture
corners) since there's no touchless UI yet to drive it end to end.
Phase 4 replaces this with a fully touchless calibration flow.
"""
from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

from aircanvas.config import AppConfig
from aircanvas.interaction.intent import FrameIntent, IntentResolver
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig
from aircanvas.vision.calibration import Calibrator, MapperConfig
from aircanvas.vision.camera import Camera, CameraError
from aircanvas.vision.smoothing import SmoothingConfig
from aircanvas.vision.tracker import (
    HAND_CONNECTIONS,
    INDEX_FINGERTIP,
    HandResult,
    HandTracker,
    ModelUnavailableError,
)

logger = logging.getLogger("aircanvas.app")

WINDOW_TITLE = "AirCanvas — Phase 2 Preview  (Q quit | 1/2 calibrate corners | C reset calib)"
STALE_FRAME_WARNING_THRESHOLD = 30  # consecutive dropped reads

_STATE_COLORS = {
    IntentState.IDLE: (120, 120, 120),
    IntentState.HAND_DETECTED: (200, 200, 200),
    IntentState.POINTER_ACTIVE: (255, 255, 255),
    IntentState.DRAWING: (60, 220, 60),
    IntentState.ERASING: (60, 140, 255),
    IntentState.UI_INTERACTION: (255, 200, 0),
    IntentState.HAND_LOST: (0, 0, 255),
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


def _draw_hand_skeleton(frame: np.ndarray, hands: List[HandResult]) -> None:
    height, width = frame.shape[:2]
    for hand in hands:
        points = hand.pixel_landmarks(width, height)
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], (0, 220, 255), 2, cv2.LINE_AA)
        for x, y in points:
            cv2.circle(frame, (x, y), 3, (255, 255, 255), -1, cv2.LINE_AA)


def _draw_intent_overlay(frame: np.ndarray, intent: FrameIntent, config: AppConfig) -> None:
    height, width = frame.shape[:2]
    color = _STATE_COLORS.get(intent.state, (255, 255, 255))

    if intent.raw_pos is not None:
        rx, ry = int(intent.raw_pos[0] * width), int(intent.raw_pos[1] * height)
        cv2.circle(frame, (rx, ry), 5, (0, 0, 255), 1, cv2.LINE_AA)  # raw: thin red ring

    if intent.smoothed_pos is not None:
        sx, sy = int(intent.smoothed_pos[0] * width), int(intent.smoothed_pos[1] * height)
        cv2.circle(frame, (sx, sy), 10, color, 2, cv2.LINE_AA)  # smoothed: filled-ish colored ring
        cv2.circle(frame, (sx, sy), 2, color, -1, cv2.LINE_AA)

    lines = [
        f"State: {intent.state.value}   Gesture: {intent.gesture.value if intent.gesture else '-'}",
        f"Velocity: {intent.velocity:.2f}/s   Canvas cursor: {intent.cursor_pos}",
    ]
    if intent.stroke_started:
        lines.append("STROKE START")
    if intent.stroke_ended:
        lines.append("STROKE END")
    if intent.clear_progress > 0.0:
        lines.append(f"Hold fist to clear: {intent.clear_progress * 100:.0f}%")
    if intent.clear_confirmed:
        lines.append("CLEAR CONFIRMED")

    for i, text in enumerate(lines):
        y = height - 20 - (len(lines) - 1 - i) * 22
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)


def _draw_calibration_hint(frame: np.ndarray, calibrator: Calibrator) -> None:
    if calibrator.is_complete:
        return
    remaining = "top-left (press 1)" if not calibrator.has_top_left else "bottom-right (press 2)"
    cv2.putText(
        frame, f"Calibrating: point at {remaining}", (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2, cv2.LINE_AA,
    )


def run(config: AppConfig) -> int:
    """Run the Phase 2 preview loop. Returns a process exit code."""
    camera = Camera(
        index=config.camera_index,
        width=config.camera_width,
        height=config.camera_height,
        fps=config.camera_fps,
        mirror=config.mirror,
        open_retries=config.camera_open_retries,
        retry_delay_sec=config.camera_retry_delay_sec,
    )
    try:
        camera.open()
    except CameraError as exc:
        logger.error(str(exc))
        print(f"\nCamera setup failed: {exc}\n")
        return 1

    try:
        tracker = HandTracker(
            model_path=config.hand_model_path,
            num_hands=config.max_num_hands,
            min_hand_detection_confidence=config.min_hand_detection_confidence,
            min_hand_presence_confidence=config.min_hand_presence_confidence,
            min_tracking_confidence=config.min_tracking_confidence,
        )
    except ModelUnavailableError as exc:
        logger.error(str(exc))
        print(f"\nHand-tracking model unavailable: {exc}\n")
        camera.release()
        return 1

    resolver = _build_resolver(config)
    calibrator = Calibrator()

    logger.info("AirCanvas Phase 2 preview running. Press Q to quit.")
    warned_stale = False
    try:
        while True:
            frame = camera.read()
            if frame is None:
                if camera.consecutive_failures > STALE_FRAME_WARNING_THRESHOLD and not warned_stale:
                    logger.warning("No frames from the camera for a while — is it still connected?")
                    warned_stale = True
                continue
            warned_stale = False

            hands = tracker.process(frame)
            intent = resolver.update(hands)

            _draw_hand_skeleton(frame, hands)
            _draw_intent_overlay(frame, intent, config)
            _draw_calibration_hint(frame, calibrator)

            cv2.imshow(WINDOW_TITLE, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' or Esc
                break
            elif key == ord("c"):
                calibrator.reset()
                logger.info("Calibration reset.")
            elif key in (ord("1"), ord("2")) and intent.raw_pos is not None:
                x, y = intent.raw_pos
                if key == ord("1"):
                    calibrator.set_top_left(x, y)
                    logger.info("Calibration: top-left set at (%.3f, %.3f)", x, y)
                else:
                    calibrator.set_bottom_right(x, y)
                    logger.info("Calibration: bottom-right set at (%.3f, %.3f)", x, y)
                if calibrator.is_complete:
                    new_config = resolver.apply_calibration(calibrator, sensitivity=config.pointer_sensitivity)
                    logger.info("Calibration applied: %s", new_config)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()

    return 0
