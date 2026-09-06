"""
Phase 1 application shell.

Wires the camera and hand tracker together into a minimal, runnable
preview so the vision pipeline can be sanity-checked end to end.

This OpenCV preview window is a temporary developer tool. Starting in
Phase 3, the real drawing canvas takes over as a pygame window, and
this overlay becomes an optional --debug view layered on top of it
rather than the whole app.
"""
from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

from aircanvas.config import AppConfig
from aircanvas.vision.camera import Camera, CameraError
from aircanvas.vision.tracker import (
    HAND_CONNECTIONS,
    INDEX_FINGERTIP,
    HandResult,
    HandTracker,
    ModelUnavailableError,
)

logger = logging.getLogger("aircanvas.app")

WINDOW_TITLE = "AirCanvas — Phase 1 Preview (press Q to quit)"
STALE_FRAME_WARNING_THRESHOLD = 30  # consecutive dropped reads


def _draw_debug_overlay(frame: np.ndarray, hands: List[HandResult]) -> None:
    """Draw the hand skeleton, fingertip cursor, and status text.

    A temporary Phase 1 visualization — the polished cursor/HUD design
    from the master prompt arrives with the real renderer in later
    phases.
    """
    height, width = frame.shape[:2]

    for hand in hands:
        points = hand.pixel_landmarks(width, height)
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], (0, 220, 255), 2, cv2.LINE_AA)
        for x, y in points:
            cv2.circle(frame, (x, y), 4, (255, 255, 255), -1, cv2.LINE_AA)

        fingertip = points[INDEX_FINGERTIP]
        cv2.circle(frame, fingertip, 10, (0, 140, 255), 2, cv2.LINE_AA)

        label = f"{hand.handedness} {hand.score:.2f}"
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    status = "HAND DETECTED" if hands else "NO HAND"
    cv2.putText(frame, status, (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)


def run(config: AppConfig) -> int:
    """Run the Phase 1 preview loop. Returns a process exit code."""
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

    logger.info("AirCanvas Phase 1 preview running. Press Q to quit.")
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
            _draw_debug_overlay(frame, hands)

            cv2.imshow(WINDOW_TITLE, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):  # 'q' or Esc
                break
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()

    return 0
