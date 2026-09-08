"""
Developer input source: a mouse (plus a couple of keys) standing in
for a real tracked hand, so the whole drawing pipeline can be tested
without a webcam. Only active via --mouse, or as an automatic
fallback if the camera can't be opened -- never required for normal
use (per the project spec's Developer Mode section).

Reuses IntentStateMachine directly, so mouse input gets the exact
same debounce/hysteresis/fist-hold-to-clear behavior a real hand
does. It skips vision.features/gestures/smoothing/calibration
entirely, though: the raw per-frame gesture comes straight from which
mouse button or key is held, and the cursor position is reported
as-is (mouse input has no jitter to smooth, and the caller is
expected to already be in canvas-pixel space).

Controls:
    Left mouse button held   -> PINCH       (draw)
    Right mouse button held  -> TWO_FINGER  (erase)
    F key held                -> FIST        (hold to clear)
    (nothing held)            -> POINTING    (move cursor only)
"""
from __future__ import annotations

from typing import Optional, Tuple

from aircanvas.interaction.intent import FrameIntent
from aircanvas.interaction.state_machine import IntentState, IntentStateMachine, StateMachineConfig
from aircanvas.vision.gestures import Gesture


class DevIntentSource:
    def __init__(self, state_config: Optional[StateMachineConfig] = None) -> None:
        self._state_machine = IntentStateMachine(state_config)
        self._was_drawing = False
        self._was_erasing = False

    def reset(self) -> None:
        self._state_machine.reset()
        self._was_drawing = False
        self._was_erasing = False

    def update(
        self,
        cursor_pos: Optional[Tuple[int, int]],
        left_button: bool,
        right_button: bool,
        fist_key: bool,
    ) -> FrameIntent:
        """Advance one frame. `cursor_pos` is None when the mouse is
        outside the drawable area (treated like a lost hand)."""
        if cursor_pos is None:
            update = self._state_machine.step(None)
            self._was_drawing = False
            self._was_erasing = False
            return FrameIntent(
                state=update.state, gesture=None, raw_pos=None, smoothed_pos=None,
                cursor_pos=None, velocity=0.0, is_drawing=False, is_erasing=False,
                stroke_started=False, stroke_ended=False, erase_started=False, erase_ended=False,
                clear_confirmed=update.clear_confirmed, clear_progress=update.clear_progress,
            )

        if fist_key:
            gesture = Gesture.FIST
        elif left_button:
            gesture = Gesture.PINCH
        elif right_button:
            gesture = Gesture.TWO_FINGER
        else:
            gesture = Gesture.POINTING

        update = self._state_machine.step(gesture)
        is_drawing = update.state == IntentState.DRAWING
        is_erasing = update.state == IntentState.ERASING
        stroke_started = is_drawing and not self._was_drawing
        stroke_ended = self._was_drawing and not is_drawing
        erase_started = is_erasing and not self._was_erasing
        erase_ended = self._was_erasing and not is_erasing
        self._was_drawing = is_drawing
        self._was_erasing = is_erasing

        return FrameIntent(
            state=update.state, gesture=gesture, raw_pos=cursor_pos, smoothed_pos=cursor_pos,
            cursor_pos=cursor_pos, velocity=0.0, is_drawing=is_drawing, is_erasing=is_erasing,
            stroke_started=stroke_started, stroke_ended=stroke_ended,
            erase_started=erase_started, erase_ended=erase_ended,
            clear_confirmed=update.clear_confirmed, clear_progress=update.clear_progress,
        )
