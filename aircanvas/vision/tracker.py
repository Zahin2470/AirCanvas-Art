"""
Hand landmark tracking, built on MediaPipe's HandLandmarker task.

A note on the MediaPipe API: the master prompt for this project was
written against the older, now-removed `mp.solutions.hands.Hands`
API. Current MediaPipe (0.10.x) replaced it with the Tasks API
(`mediapipe.tasks.python.vision.HandLandmarker`), which loads its
model from a `.task` file instead of shipping one inside the pip
package. This module targets that current API and downloads/caches
the model file on first run (see `ensure_model`) so the rest of the
app never has to think about model management.

Kept independent of pygame/rendering: this module only turns camera
frames into structured landmark data.
"""
from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from mediapipe import Image, ImageFormat
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from aircanvas.config import get_models_dir

logger = logging.getLogger("aircanvas.vision.tracker")

# Google's officially hosted model. Only used when no local copy is
# cached yet; see ensure_model().
DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
DEFAULT_MODEL_FILENAME = "hand_landmarker.task"

# (start, end) landmark index pairs for drawing the 21-point hand
# skeleton, re-exported from MediaPipe so callers (e.g. the Phase 1
# debug overlay in app.py) don't need to import mediapipe directly.
HAND_CONNECTIONS: List[Tuple[int, int]] = [
    (c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS
]

# Landmark indices used elsewhere in the app.
INDEX_FINGERTIP = 8
THUMB_TIP = 4


class ModelUnavailableError(RuntimeError):
    """Raised when the hand-landmark model can't be found or downloaded."""


def ensure_model(model_path: Optional[Path] = None, download_url: str = DEFAULT_MODEL_URL) -> Path:
    """Return a local path to hand_landmarker.task, downloading it into
    the AirCanvas cache directory on first run if it isn't there yet.

    Raises:
        ModelUnavailableError: if no local model exists and it could
            not be downloaded (e.g. no network on first launch).
    """
    path = Path(model_path) if model_path else (get_models_dir() / DEFAULT_MODEL_FILENAME)
    if path.exists() and path.stat().st_size > 0:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading hand-tracking model to %s ...", path)
    tmp_path = path.with_suffix(path.suffix + ".part")
    try:
        urllib.request.urlretrieve(download_url, tmp_path)
        tmp_path.replace(path)
    except Exception as exc:
        raise ModelUnavailableError(
            f"Could not download the hand-tracking model ({download_url}). "
            "Connect to the internet once so AirCanvas can cache it locally, "
            "or set hand_model_path / AIRCANVAS_HAND_MODEL_PATH to a local "
            "hand_landmarker.task file."
        ) from exc
    return path


@dataclass(frozen=True)
class LandmarkPoint:
    """A single hand landmark in normalized [0, 1] image coordinates."""

    x: float
    y: float
    z: float

    def to_pixel(self, width: int, height: int) -> Tuple[int, int]:
        return int(round(self.x * width)), int(round(self.y * height))


@dataclass(frozen=True)
class HandResult:
    """One detected hand: 21 landmarks plus handedness/confidence."""

    landmarks: List[LandmarkPoint] = field(default_factory=list)
    handedness: str = "Unknown"
    score: float = 0.0

    def pixel_landmarks(self, width: int, height: int) -> List[Tuple[int, int]]:
        return [p.to_pixel(width, height) for p in self.landmarks]

    def get(self, index: int) -> LandmarkPoint:
        """Landmark by MediaPipe hand-landmark index (0-20).

        INDEX_FINGERTIP (8) is the point AirCanvas uses as the brush
        cursor; THUMB_TIP (4) is used for pinch detection starting in
        Phase 2.
        """
        return self.landmarks[index]


class HandTracker:
    """Wraps mediapipe's HandLandmarker for synchronous, per-frame use.

    Initialize once and reuse across the whole camera loop — creating
    a new HandLandmarker per frame is expensive and defeats
    MediaPipe's internal tracking optimizations.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        num_hands: int = 1,
        min_hand_detection_confidence: float = 0.6,
        min_hand_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        resolved_model = ensure_model(model_path)
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(resolved_model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._start_time_ms = int(time.time() * 1000)
        self._last_timestamp_ms = -1

    def process(self, frame_bgr: np.ndarray) -> List[HandResult]:
        """Run detection on one BGR frame and return structured results."""
        rgb = frame_bgr[:, :, ::-1]
        mp_image = Image(image_format=ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

        # VIDEO mode requires strictly increasing timestamps; guard
        # against two frames landing in the same millisecond.
        timestamp_ms = int(time.time() * 1000) - self._start_time_ms
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        return self._to_hand_results(result)

    @staticmethod
    def _to_hand_results(result) -> List[HandResult]:
        hands: List[HandResult] = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            points = [LandmarkPoint(p.x, p.y, p.z) for p in landmarks]
            top = handedness[0] if handedness else None
            hands.append(
                HandResult(
                    landmarks=points,
                    handedness=top.category_name if top else "Unknown",
                    score=top.score if top else 0.0,
                )
            )
        return hands

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
