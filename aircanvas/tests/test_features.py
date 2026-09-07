from aircanvas.tests.helpers import make_hand
from aircanvas.vision.features import extract_features
from aircanvas.vision.tracker import INDEX_FINGERTIP


def test_pointing_hand_has_only_index_extended():
    hand = make_hand(extended={"index": True})
    features = extract_features(hand)
    thumb, index, middle, ring, pinky = features.fingers_extended
    assert (thumb, index, middle, ring, pinky) == (False, True, False, False, False)
    assert features.extended_count == 1


def test_open_palm_has_all_fingers_extended():
    hand = make_hand(extended={"thumb": True, "index": True, "middle": True, "ring": True, "pinky": True})
    features = extract_features(hand)
    assert features.extended_count == 5


def test_fist_has_no_fingers_extended():
    hand = make_hand(extended={})
    features = extract_features(hand)
    assert features.extended_count == 0


def test_two_finger_hand_has_index_and_middle_only():
    hand = make_hand(extended={"index": True, "middle": True})
    features = extract_features(hand)
    thumb, index, middle, ring, pinky = features.fingers_extended
    assert (index, middle) == (True, True)
    assert (thumb, ring, pinky) == (False, False, False)


def test_pinch_distance_is_small_when_pinching():
    pinching = extract_features(make_hand(pinch=True))
    not_pinching = extract_features(make_hand(extended={"index": True}))
    assert pinching.pinch_distance < 0.35
    assert not_pinching.pinch_distance > 0.35
    assert pinching.pinch_distance < not_pinching.pinch_distance


def test_fingertip_matches_raw_index_landmark():
    hand = make_hand(extended={"index": True})
    features = extract_features(hand)
    assert features.fingertip == hand.landmarks[INDEX_FINGERTIP]


def test_handedness_and_score_pass_through():
    hand = make_hand(extended={"index": True}, handedness="Left", score=0.72)
    features = extract_features(hand)
    assert features.handedness == "Left"
    assert features.score == 0.72
