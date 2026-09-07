"""
Per-frame intent resolution: the single integration point that turns
a list of tracked hands into one structured FrameIntent, combining:

    vision.features    -> derived per-hand signals
    vision.gestures     -> per-frame gesture classification
    state_machine        -> temporal debouncing/hysteresis
    vision.smoothing    -> jitter-free pointer position
    vision.calibration  -> camera-space -> canvas-space mapping

The canvas/rendering layers (Phase 3+) only need to look at the
FrameIntent this produces; they don't need to know anything about
hand tracking.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from aircanvas.interaction.state_machine import IntentState, IntentStateMachine, StateMachineConfig
from aircanvas.vision.calibration import Calibrator, CoordinateMapper, MapperConfig
from aircanvas.vision.features import extract_features
from aircanvas.vision.gestures import Gesture, classify_gesture
from aircanvas.vision.smoothing import PointSmoother, SmoothingConfig
from aircanvas.vision.tracker import HandResult

DEFAULT_PINCH_THRESHOLD = 0.35


@dataclass(frozen=True)
class FrameIntent:
    state: IntentState
    gesture: Optional[Gesture]
    raw_pos: Optional[Tuple[float, float]]  # normalized [0,1] fingertip, unsmoothed
    smoothed_pos: Optional[Tuple[float, float]]  # normalized [0,1], after smoothing
    cursor_pos: Optional[Tuple[int, int]]  # mapped to canvas pixel space
    velocity: float
    is_drawing: bool
    is_erasing: bool
    stroke_started: bool
    stroke_ended: bool
    clear_confirmed: bool
    clear_progress: float


class IntentResolver:
    def __init__(
        self,
        canvas_width: int,
        canvas_height: int,
        smoothing_config: Optional[SmoothingConfig] = None,
        mapper_config: Optional[MapperConfig] = None,
        state_config: Optional[StateMachineConfig] = None,
        pinch_threshold: float = DEFAULT_PINCH_THRESHOLD,
    ) -> None:
        self._smoother = PointSmoother(smoothing_config)
        self._mapper = CoordinateMapper(canvas_width, canvas_height, mapper_config)
        self._state_machine = IntentStateMachine(state_config)
        self._pinch_threshold = pinch_threshold
        self._last_time: Optional[float] = None
        self._was_drawing = False

    def resize_canvas(self, width: int, height: int) -> None:
        self._mapper.resize(width, height)

    def apply_calibration(self, calibrator: Calibrator, sensitivity: Optional[float] = None) -> MapperConfig:
        """Recompute and apply the coordinate mapping from a completed
        Calibrator, keeping the current sensitivity unless overridden."""
        new_config = calibrator.to_mapper_config(
            sensitivity=sensitivity if sensitivity is not None else self._mapper.config.sensitivity
        )
        self._mapper.config = new_config
        return new_config

    def reset(self) -> None:
        self._smoother.reset()
        self._state_machine.reset()
        self._last_time = None
        self._was_drawing = False

    def update(self, hands: List[HandResult], now: Optional[float] = None) -> FrameIntent:
        now = now if now is not None else time.monotonic()
        dt = (now - self._last_time) if self._last_time is not None else 1.0 / 30.0
        self._last_time = now

        if not hands:
            update = self._state_machine.step(None)
            self._was_drawing = False
            return FrameIntent(
                state=update.state,
                gesture=None,
                raw_pos=None,
                smoothed_pos=None,
                cursor_pos=None,
                velocity=0.0,
                is_drawing=False,
                is_erasing=False,
                stroke_started=False,
                stroke_ended=False,
                clear_confirmed=update.clear_confirmed,
                clear_progress=update.clear_progress,
            )

        features = extract_features(hands[0])
        gesture = classify_gesture(features, pinch_threshold=self._pinch_threshold)
        update = self._state_machine.step(gesture)

        raw = (features.fingertip.x, features.fingertip.y)
        smoothed = self._smoother.update(raw[0], raw[1], dt)
        cursor = self._mapper.map(*smoothed)

        is_drawing = update.state == IntentState.DRAWING
        is_erasing = update.state == IntentState.ERASING
        stroke_started = is_drawing and not self._was_drawing
        stroke_ended = self._was_drawing and not is_drawing
        self._was_drawing = is_drawing

        return FrameIntent(
            state=update.state,
            gesture=gesture,
            raw_pos=raw,
            smoothed_pos=smoothed,
            cursor_pos=cursor,
            velocity=self._smoother.velocity,
            is_drawing=is_drawing,
            is_erasing=is_erasing,
            stroke_started=stroke_started,
            stroke_ended=stroke_ended,
            clear_confirmed=update.clear_confirmed,
            clear_progress=update.clear_progress,
        )
