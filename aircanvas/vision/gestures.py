"""
Per-frame gesture classification from derived hand features.

Pure and stateless -- classifies exactly what one frame's features
look like, with no memory of previous frames. Temporal smoothing of
noisy per-frame classifications (so a single flickered frame doesn't
change what the app does) is the state machine's job, not this
module's -- see aircanvas/interaction/state_machine.py.
"""
from __future__ import annotations

from enum import Enum

from aircanvas.vision.features import HandFeatures

DEFAULT_PINCH_THRESHOLD = 0.35


class Gesture(Enum):
    NONE = "none"
    POINTING = "pointing"  # index only -- move the brush cursor
    PINCH = "pinch"  # thumb + index together -- draw / select / activate
    TWO_FINGER = "two_finger"  # index + middle -- eraser / tool mode
    OPEN_PALM = "open_palm"  # most/all fingers extended -- pause / UI interaction
    FIST = "fist"  # no fingers extended -- clear (after deliberate confirmation)


def classify_gesture(features: HandFeatures, pinch_threshold: float = DEFAULT_PINCH_THRESHOLD) -> Gesture:
    """Classify one frame's HandFeatures into a single Gesture.

    Checked in priority order: a pinch is recognized regardless of
    which fingers the extension heuristic thinks are up, since a
    pinched thumb and index otherwise tend to read as "curled".
    """
    if features.pinch_distance <= pinch_threshold:
        return Gesture.PINCH

    thumb, index, middle, ring, pinky = features.fingers_extended
    extended = features.extended_count

    if extended == 0:
        return Gesture.FIST
    if index and middle and not ring and not pinky:
        return Gesture.TWO_FINGER
    if extended >= 4:
        return Gesture.OPEN_PALM
    if index and not middle and not ring and not pinky:
        return Gesture.POINTING
    return Gesture.NONE
