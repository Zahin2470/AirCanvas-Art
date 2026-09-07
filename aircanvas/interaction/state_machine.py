"""
Temporal debouncing over raw per-frame gestures.

`vision.gestures.classify_gesture` looks at a single frame in
isolation and will occasionally flicker (a frame or two misclassified
mid-transition). This module requires a gesture to persist for
`debounce_frames` consecutive frames before acting on it, and treats
a brief hand disappearance as a transient "hand lost" state rather
than immediately resetting everything -- both are what the master
spec calls for under hysteresis/debounce timing.

State diagram (informal):
    IDLE <-> HAND_DETECTED -> POINTER_ACTIVE -> {DRAWING, ERASING, UI_INTERACTION}
                                   ^                        |
                                   +------------------------+
    (any active state) -- hand missing --> HAND_LOST -- grace expires --> IDLE

FIST is treated as a UI_INTERACTION variant: it requires being held
for `fist_confirm_frames` before `clear_confirmed` fires once, giving
the "deliberate confirmation" the spec asks for before clearing the
canvas. There's no separate confirmation dialog yet -- that's a
Phase 4 UI concern -- so `clear_progress` is exposed for a debug/HUD
overlay to show hold-progress in the meantime.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from aircanvas.vision.gestures import Gesture


class IntentState(Enum):
    IDLE = "idle"
    HAND_DETECTED = "hand_detected"
    POINTER_ACTIVE = "pointer_active"
    DRAWING = "drawing"
    ERASING = "erasing"
    UI_INTERACTION = "ui_interaction"
    HAND_LOST = "hand_lost"


@dataclass
class StateMachineConfig:
    debounce_frames: int = 3  # frames a gesture must persist before it's acted on
    hand_lost_grace_frames: int = 10  # frames of no-hand tolerated before dropping to IDLE
    fist_confirm_frames: int = 20  # frames a fist must be held before CLEAR fires


@dataclass(frozen=True)
class StateUpdate:
    state: IntentState
    clear_confirmed: bool = False  # True on exactly the frame CLEAR should fire
    clear_progress: float = 0.0  # 0..1, for showing fist-hold progress in a HUD


class IntentStateMachine:
    """Advances one frame at a time via `step(gesture)`; `gesture` is
    None when no hand was detected that frame."""

    def __init__(self, config: Optional[StateMachineConfig] = None) -> None:
        self.config = config or StateMachineConfig()
        self.state = IntentState.IDLE
        self._pending_gesture: Optional[Gesture] = None
        self._pending_count = 0
        self._hand_missing_count = 0
        self._fist_hold_count = 0

    def reset(self) -> None:
        config = self.config
        self.__init__(config)

    def step(self, gesture: Optional[Gesture]) -> StateUpdate:
        if gesture is None:
            return self._handle_hand_missing()

        self._hand_missing_count = 0

        if self.state in (IntentState.IDLE, IntentState.HAND_LOST):
            self.state = IntentState.HAND_DETECTED

        # Debounce: require the same gesture to persist before acting on it.
        if gesture == self._pending_gesture:
            self._pending_count += 1
        else:
            self._pending_gesture = gesture
            self._pending_count = 1
        confirmed = self._pending_count >= self.config.debounce_frames

        if gesture != Gesture.FIST:
            self._fist_hold_count = 0

        if not confirmed:
            # Cursor tracking itself is never debounced -- only
            # switching into an action (draw/erase/UI/clear) is.
            if self.state not in (IntentState.DRAWING, IntentState.ERASING, IntentState.UI_INTERACTION):
                self.state = IntentState.POINTER_ACTIVE
            return StateUpdate(state=self.state)

        if gesture == Gesture.PINCH:
            self.state = IntentState.DRAWING
        elif gesture == Gesture.TWO_FINGER:
            self.state = IntentState.ERASING
        elif gesture == Gesture.OPEN_PALM:
            self.state = IntentState.UI_INTERACTION
        elif gesture == Gesture.FIST:
            self._fist_hold_count += 1
            if self._fist_hold_count >= self.config.fist_confirm_frames:
                self._fist_hold_count = 0
                self.state = IntentState.POINTER_ACTIVE
                return StateUpdate(state=self.state, clear_confirmed=True, clear_progress=1.0)
            progress = self._fist_hold_count / self.config.fist_confirm_frames
            self.state = IntentState.UI_INTERACTION
            return StateUpdate(state=self.state, clear_progress=progress)
        else:  # POINTING or NONE: just tracking, no action
            self.state = IntentState.POINTER_ACTIVE

        return StateUpdate(state=self.state)

    def _handle_hand_missing(self) -> StateUpdate:
        self._pending_gesture = None
        self._pending_count = 0
        self._fist_hold_count = 0

        if self.state == IntentState.IDLE:
            return StateUpdate(state=self.state)

        self._hand_missing_count += 1
        if self._hand_missing_count == 1:
            self.state = IntentState.HAND_LOST

        if self._hand_missing_count > self.config.hand_lost_grace_frames:
            self.state = IntentState.IDLE
            self._hand_missing_count = 0

        return StateUpdate(state=self.state)
