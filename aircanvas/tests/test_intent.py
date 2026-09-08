from aircanvas.interaction.intent import IntentResolver
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig
from aircanvas.tests.helpers import make_hand
from aircanvas.vision.calibration import Calibrator, MapperConfig
from aircanvas.vision.smoothing import SmoothingConfig


def _resolver(**state_overrides):
    return IntentResolver(
        canvas_width=1000,
        canvas_height=500,
        # No lag / no margins so cursor math is exact and predictable.
        smoothing_config=SmoothingConfig(min_alpha=1.0, max_alpha=1.0, min_movement_threshold=0.0),
        mapper_config=MapperConfig(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0, sensitivity=1.0),
        state_config=StateMachineConfig(debounce_frames=1, **state_overrides),
    )


def test_no_hand_returns_no_cursor():
    resolver = _resolver()
    result = resolver.update([], now=0.0)
    assert result.cursor_pos is None
    assert result.is_drawing is False


def test_pointing_hand_produces_a_cursor_position_without_drawing():
    resolver = _resolver()
    hand = make_hand(extended={"index": True})
    result = resolver.update([hand], now=0.0)
    assert result.cursor_pos is not None
    assert result.is_drawing is False
    assert result.state == IntentState.POINTER_ACTIVE


def test_pinch_starts_a_stroke_immediately_with_debounce_of_one():
    resolver = _resolver()
    hand = make_hand(pinch=True)
    result = resolver.update([hand], now=0.0)
    assert result.is_drawing is True
    assert result.stroke_started is True


def test_holding_pinch_across_frames_does_not_re_fire_stroke_started():
    resolver = _resolver()
    hand = make_hand(pinch=True)
    resolver.update([hand], now=0.0)
    result = resolver.update([hand], now=1 / 30)
    assert result.is_drawing is True
    assert result.stroke_started is False  # already drawing, not a new stroke


def test_releasing_pinch_ends_the_stroke():
    resolver = _resolver()
    pinch_hand = make_hand(pinch=True)
    point_hand = make_hand(extended={"index": True})
    resolver.update([pinch_hand], now=0.0)
    result = resolver.update([point_hand], now=1 / 30)
    assert result.is_drawing is False
    assert result.stroke_ended is True


def test_two_finger_hand_reports_erasing_not_drawing():
    resolver = _resolver()
    hand = make_hand(extended={"index": True, "middle": True})
    result = resolver.update([hand], now=0.0)
    assert result.is_erasing is True
    assert result.is_drawing is False
    assert result.erase_started is True


def test_holding_two_finger_across_frames_does_not_re_fire_erase_started():
    resolver = _resolver()
    hand = make_hand(extended={"index": True, "middle": True})
    resolver.update([hand], now=0.0)
    result = resolver.update([hand], now=1 / 30)
    assert result.is_erasing is True
    assert result.erase_started is False


def test_releasing_two_finger_ends_the_erase():
    resolver = _resolver()
    two_finger_hand = make_hand(extended={"index": True, "middle": True})
    point_hand = make_hand(extended={"index": True})
    resolver.update([two_finger_hand], now=0.0)
    result = resolver.update([point_hand], now=1 / 30)
    assert result.is_erasing is False
    assert result.erase_ended is True


def test_cursor_position_reflects_coordinate_mapping():
    resolver = _resolver()
    hand = make_hand(extended={"index": True})  # index tip at normalized (0.47, 0.45)
    result = resolver.update([hand], now=0.0)
    assert result.cursor_pos == (470, 225)  # 0.47*1000, 0.45*500 -- no margins/smoothing lag


def test_hand_lost_after_being_seen_reports_no_cursor():
    resolver = _resolver(hand_lost_grace_frames=1)
    hand = make_hand(extended={"index": True})
    resolver.update([hand], now=0.0)
    result = resolver.update([], now=1 / 30)
    assert result.cursor_pos is None
    assert result.state == IntentState.HAND_LOST


def test_apply_calibration_changes_subsequent_cursor_mapping():
    resolver = _resolver()
    calibrator = Calibrator()
    calibrator.set_top_left(0.2, 0.1)
    calibrator.set_bottom_right(0.8, 0.9)
    resolver.apply_calibration(calibrator)

    hand = make_hand(extended={"index": True})  # fingertip at (0.47, 0.45)
    before_margins_result = resolver.update([hand], now=0.0)
    # With the wider active-region margins removed, the same raw point
    # now maps to a different (more central) canvas position than the
    # zero-margin default used in test_cursor_position_reflects_coordinate_mapping.
    assert before_margins_result.cursor_pos != (470, 225)


def test_reset_clears_smoothing_and_state():
    resolver = _resolver()
    resolver.update([make_hand(pinch=True)], now=0.0)
    resolver.reset()
    result = resolver.update([make_hand(extended={"index": True})], now=0.0)
    assert result.state == IntentState.POINTER_ACTIVE
    assert result.stroke_started is False
