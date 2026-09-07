"""Shared synthetic-data builders for hardware-free vision/interaction
tests. Not a test module itself -- pytest won't collect anything here
since the filename doesn't match test_*.py."""
from __future__ import annotations

from typing import Dict, Optional

from aircanvas.vision.tracker import HandResult, LandmarkPoint


def _lm(x: float, y: float, z: float = 0.0) -> LandmarkPoint:
    return LandmarkPoint(x=x, y=y, z=z)


def make_hand(
    extended: Optional[Dict[str, bool]] = None,
    pinch: bool = False,
    handedness: str = "Right",
    score: float = 0.95,
) -> HandResult:
    """Build a synthetic 21-point hand for deterministic unit tests.

    `extended` maps finger names ("thumb", "index", "middle", "ring",
    "pinky") to whether that finger should read as extended by the
    tip-vs-pip-distance-from-wrist heuristic in vision/features.py.
    Any finger not listed defaults to curled (not extended).
    `pinch=True` overrides thumb/index tip placement to sit close
    together, regardless of `extended`.

    Coordinates follow image space (y grows downward); the wrist sits
    near the bottom of the frame and extended fingers point up
    (smaller y), matching a hand held up in front of the camera.
    """
    extended = extended or {}
    landmarks = [None] * 21

    landmarks[0] = _lm(0.50, 0.90)  # wrist
    landmarks[1] = _lm(0.42, 0.85)  # thumb CMC
    landmarks[2] = _lm(0.38, 0.80)  # thumb MCP
    landmarks[3] = _lm(0.35, 0.76)  # thumb IP
    landmarks[4] = (  # thumb tip
        _lm(0.50, 0.56) if pinch else (_lm(0.30, 0.72) if extended.get("thumb") else _lm(0.40, 0.72))
    )

    landmarks[5] = _lm(0.47, 0.75)  # index MCP
    landmarks[6] = _lm(0.47, 0.65)  # index PIP
    landmarks[7] = _lm(0.47, 0.58)  # index DIP
    landmarks[8] = (  # index tip
        _lm(0.50, 0.55) if pinch else (_lm(0.47, 0.45) if extended.get("index") else _lm(0.47, 0.70))
    )

    landmarks[9] = _lm(0.50, 0.75)  # middle MCP
    landmarks[10] = _lm(0.50, 0.65)  # middle PIP
    landmarks[11] = _lm(0.50, 0.58)  # middle DIP
    landmarks[12] = _lm(0.50, 0.45) if extended.get("middle") else _lm(0.50, 0.70)  # middle tip

    landmarks[13] = _lm(0.53, 0.75)  # ring MCP
    landmarks[14] = _lm(0.53, 0.65)  # ring PIP
    landmarks[15] = _lm(0.53, 0.58)  # ring DIP
    landmarks[16] = _lm(0.53, 0.45) if extended.get("ring") else _lm(0.53, 0.70)  # ring tip

    landmarks[17] = _lm(0.56, 0.75)  # pinky MCP
    landmarks[18] = _lm(0.56, 0.66)  # pinky PIP
    landmarks[19] = _lm(0.56, 0.60)  # pinky DIP
    landmarks[20] = _lm(0.56, 0.48) if extended.get("pinky") else _lm(0.56, 0.70)  # pinky tip

    return HandResult(landmarks=landmarks, handedness=handedness, score=score)
