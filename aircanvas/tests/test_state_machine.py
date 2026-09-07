from aircanvas.interaction.state_machine import IntentState, IntentStateMachine, StateMachineConfig
from aircanvas.vision.gestures import Gesture


def test_starts_idle():
    sm = IntentStateMachine()
    assert sm.state == IntentState.IDLE


def test_pointer_tracking_activates_immediately_no_debounce_needed():
    # Cursor movement shouldn't lag just because a hand appeared --
    # only switching into an action (draw/erase/UI/clear) is debounced.
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=5))
    update = sm.step(Gesture.POINTING)
    assert update.state == IntentState.POINTER_ACTIVE


def test_single_frame_glitch_does_not_trigger_drawing():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=3))
    sm.step(Gesture.POINTING)
    sm.step(Gesture.POINTING)
    update = sm.step(Gesture.PINCH)  # one glitchy frame -- not enough to confirm
    assert update.state != IntentState.DRAWING


def test_sustained_pinch_enters_drawing_once_debounced():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=3))
    update = None
    for _ in range(3):
        update = sm.step(Gesture.PINCH)
    assert update.state == IntentState.DRAWING


def test_sustained_two_finger_enters_erasing():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=2))
    sm.step(Gesture.TWO_FINGER)
    update = sm.step(Gesture.TWO_FINGER)
    assert update.state == IntentState.ERASING


def test_sustained_open_palm_enters_ui_interaction():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1))
    update = sm.step(Gesture.OPEN_PALM)
    assert update.state == IntentState.UI_INTERACTION


def test_hand_missing_enters_hand_lost_then_idle_after_grace_expires():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1, hand_lost_grace_frames=2))
    sm.step(Gesture.POINTING)  # get out of IDLE first
    assert sm.step(None).state == IntentState.HAND_LOST
    assert sm.step(None).state == IntentState.HAND_LOST
    assert sm.step(None).state == IntentState.IDLE


def test_brief_hand_loss_within_grace_recovers_without_dropping_to_idle():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1, hand_lost_grace_frames=5))
    sm.step(Gesture.POINTING)
    sm.step(None)
    update = sm.step(Gesture.POINTING)
    assert update.state != IntentState.IDLE


def test_no_hand_while_already_idle_stays_idle():
    sm = IntentStateMachine()
    update = sm.step(None)
    assert update.state == IntentState.IDLE


def test_fist_requires_sustained_hold_before_clear_fires_exactly_once():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1, fist_confirm_frames=5))
    confirmed_flags = [sm.step(Gesture.FIST).clear_confirmed for _ in range(5)]
    assert confirmed_flags.count(True) == 1
    assert confirmed_flags[-1] is True


def test_fist_progress_increases_monotonically_to_one():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1, fist_confirm_frames=4))
    progresses = [sm.step(Gesture.FIST).clear_progress for _ in range(4)]
    assert progresses == sorted(progresses)
    assert progresses[-1] == 1.0


def test_releasing_fist_before_confirmation_cancels_the_hold():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1, fist_confirm_frames=10))
    sm.step(Gesture.FIST)
    sm.step(Gesture.FIST)
    released = sm.step(Gesture.POINTING)
    assert released.clear_confirmed is False

    resumed = sm.step(Gesture.FIST)
    assert resumed.clear_progress < 0.5  # hold count reset, not carried over


def test_reset_returns_to_initial_idle_state():
    sm = IntentStateMachine(StateMachineConfig(debounce_frames=1))
    sm.step(Gesture.PINCH)
    sm.reset()
    assert sm.state == IntentState.IDLE
