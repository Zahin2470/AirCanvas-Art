from aircanvas.vision.features import HandFeatures
from aircanvas.vision.gestures import Gesture, classify_gesture
from aircanvas.vision.tracker import LandmarkPoint

_ORIGIN = LandmarkPoint(0.0, 0.0, 0.0)


def _features(pinch_distance: float, fingers_extended, handedness="Right", score=0.9) -> HandFeatures:
    return HandFeatures(
        fingertip=_ORIGIN,
        pinch_distance=pinch_distance,
        fingers_extended=fingers_extended,
        handedness=handedness,
        score=score,
    )


def test_close_pinch_distance_is_always_pinch_regardless_of_finger_state():
    # Even if the finger-extension heuristic reads all fingers as "up"
    # (e.g. a pinch held high), a small pinch distance wins.
    features = _features(pinch_distance=0.1, fingers_extended=(True, True, True, True, True))
    assert classify_gesture(features) == Gesture.PINCH


def test_no_fingers_extended_and_no_pinch_is_fist():
    features = _features(pinch_distance=1.0, fingers_extended=(False, False, False, False, False))
    assert classify_gesture(features) == Gesture.FIST


def test_index_and_middle_only_is_two_finger():
    features = _features(pinch_distance=1.0, fingers_extended=(False, True, True, False, False))
    assert classify_gesture(features) == Gesture.TWO_FINGER


def test_four_or_more_extended_is_open_palm():
    features = _features(pinch_distance=1.0, fingers_extended=(True, True, True, True, False))
    assert classify_gesture(features) == Gesture.OPEN_PALM


def test_index_only_is_pointing():
    features = _features(pinch_distance=1.0, fingers_extended=(False, True, False, False, False))
    assert classify_gesture(features) == Gesture.POINTING


def test_ambiguous_combination_falls_back_to_none():
    # Ring extended alone doesn't match any named pose.
    features = _features(pinch_distance=1.0, fingers_extended=(False, False, False, True, False))
    assert classify_gesture(features) == Gesture.NONE


def test_pinch_threshold_is_configurable():
    features = _features(pinch_distance=0.5, fingers_extended=(False, True, False, False, False))
    assert classify_gesture(features, pinch_threshold=0.35) == Gesture.POINTING
    assert classify_gesture(features, pinch_threshold=0.6) == Gesture.PINCH
