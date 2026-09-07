"""
Derived, per-frame features computed from a single hand's 21 raw
landmarks: the fingertip position AirCanvas paints with, a
scale-invariant pinch distance, and which fingers are extended.

Kept as pure functions/dataclasses (no state) so gesture
classification and the intent state machine that consume these can
be tested deterministically with synthetic landmark sets.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from aircanvas.vision.tracker import HandResult, LandmarkPoint, INDEX_FINGERTIP, THUMB_TIP

# MediaPipe's 21-point hand landmark indices used below.
WRIST = 0
THUMB_MCP = 2
INDEX_PIP = 6
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

# How much farther (as a ratio) a fingertip must be from the wrist
# than its PIP joint to count as "extended". Small margins above 1.0
# guard against borderline/jittery poses flickering between states.
_FINGER_EXTENSION_MARGIN = 1.05
_THUMB_EXTENSION_MARGIN = 1.10


def _distance(a: LandmarkPoint, b: LandmarkPoint) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _is_finger_extended(landmarks, tip: int, pip: int, wrist: LandmarkPoint) -> bool:
    return _distance(landmarks[tip], wrist) > _distance(landmarks[pip], wrist) * _FINGER_EXTENSION_MARGIN


def _is_thumb_extended(landmarks) -> bool:
    # The thumb doesn't fold the same way the other fingers do, so it
    # gets its own heuristic: compare its spread from the pinky-MCP
    # side of the palm instead of distance from the wrist.
    pinky_mcp = landmarks[PINKY_MCP]
    return (
        _distance(landmarks[THUMB_TIP], pinky_mcp)
        > _distance(landmarks[THUMB_MCP], pinky_mcp) * _THUMB_EXTENSION_MARGIN
    )


@dataclass(frozen=True)
class HandFeatures:
    """Derived signals used for gesture classification."""

    fingertip: LandmarkPoint  # index tip -- the brush cursor point
    pinch_distance: float  # thumb-index distance, normalized by hand size
    fingers_extended: Tuple[bool, bool, bool, bool, bool]  # thumb, index, middle, ring, pinky
    handedness: str
    score: float

    @property
    def extended_count(self) -> int:
        return sum(self.fingers_extended)


def extract_features(hand: HandResult) -> HandFeatures:
    """Compute HandFeatures from one HandResult's raw landmarks."""
    lm = hand.landmarks
    wrist = lm[WRIST]

    # Distance from wrist to middle-finger MCP as a hand-size proxy, so
    # pinch distance means roughly the same thing regardless of how
    # close the hand is to the camera.
    scale = _distance(wrist, lm[MIDDLE_MCP]) or 1e-6
    pinch_distance = _distance(lm[THUMB_TIP], lm[INDEX_FINGERTIP]) / scale

    fingers_extended = (
        _is_thumb_extended(lm),
        _is_finger_extended(lm, INDEX_FINGERTIP, INDEX_PIP, wrist),
        _is_finger_extended(lm, MIDDLE_TIP, MIDDLE_PIP, wrist),
        _is_finger_extended(lm, RING_TIP, RING_PIP, wrist),
        _is_finger_extended(lm, PINKY_TIP, PINKY_PIP, wrist),
    )

    return HandFeatures(
        fingertip=lm[INDEX_FINGERTIP],
        pinch_distance=pinch_distance,
        fingers_extended=fingers_extended,
        handedness=hand.handedness,
        score=hand.score,
    )
