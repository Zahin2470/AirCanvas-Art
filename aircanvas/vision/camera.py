"""
Webcam capture layer.

Isolated from tracking and rendering so it can be unit tested without
a real camera or display (see aircanvas/tests/test_camera.py, which
mocks cv2.VideoCapture). Nothing here ever raises out of `read()` —
a momentarily missing frame is a normal event, not a crash.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger("aircanvas.vision.camera")


class CameraError(RuntimeError):
    """Raised when the webcam cannot be opened after all retries."""


class Camera:
    """Thin, defensive wrapper around cv2.VideoCapture.

    `open()` raises a clear CameraError after exhausting retries, so
    the app can show a friendly setup/error state instead of
    crashing. `read()` never raises — it returns None on any hiccup
    and tracks consecutive failures so callers can tell a single
    dropped frame apart from a camera that has actually disconnected.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        mirror: bool = True,
        open_retries: int = 3,
        retry_delay_sec: float = 0.5,
    ) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.mirror = mirror
        self.open_retries = max(1, open_retries)
        self.retry_delay_sec = retry_delay_sec
        self._cap: Optional["cv2.VideoCapture"] = None
        self._consecutive_failures = 0

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def open(self) -> None:
        """Open the configured camera index, retrying on failure.

        Raises:
            CameraError: if the camera could not be opened after all
                configured retries.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, self.open_retries + 1):
            try:
                cap = cv2.VideoCapture(self.index)
                if cap is not None and cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_FPS, self.fps)
                    self._cap = cap
                    self._consecutive_failures = 0
                    logger.info(
                        "Camera %s opened (%sx%s @ %sfps)",
                        self.index, self.width, self.height, self.fps,
                    )
                    return
                if cap is not None:
                    cap.release()
            except Exception as exc:  # defensive: a driver quirk must never crash the app
                last_error = exc
                logger.warning(
                    "Camera open attempt %s/%s failed: %s", attempt, self.open_retries, exc
                )
            if attempt < self.open_retries:
                time.sleep(self.retry_delay_sec)

        raise CameraError(
            f"Could not open camera index {self.index} after {self.open_retries} attempt(s). "
            "Check that no other application is using the webcam, that camera "
            "permissions are granted, or try a different --camera index."
        ) from last_error

    def change_index(self, new_index: int) -> None:
        """Release the current camera and open a different index."""
        self.release()
        self.index = new_index
        self.open()

    def read(self) -> Optional[np.ndarray]:
        """Return the next BGR frame, or None if one isn't available."""
        if not self.is_opened:
            return None
        try:
            ok, frame = self._cap.read()
        except Exception as exc:
            logger.warning("Camera read failed: %s", exc)
            ok, frame = False, None

        if not ok or frame is None:
            self._consecutive_failures += 1
            return None

        self._consecutive_failures = 0
        if self.mirror:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def list_camera_indices(max_index: int = 5) -> List[int]:
    """Best-effort probe of camera indices 0..max_index-1.

    Intended for a future developer/setup UI that suggests indices to
    try; not guaranteed to be exhaustive or fast on every platform.
    """
    found: List[int] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            found.append(i)
        if cap is not None:
            cap.release()
    return found
