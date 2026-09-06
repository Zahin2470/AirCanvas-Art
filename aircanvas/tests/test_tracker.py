from types import SimpleNamespace

import pytest

from aircanvas.vision.tracker import (
    HandResult,
    HandTracker,
    LandmarkPoint,
    ModelUnavailableError,
    ensure_model,
)

# These tests exercise the tracker's data structures, coordinate math,
# and model-caching logic without loading a real MediaPipe model or
# touching a camera — hardware/network-dependent behavior is isolated
# here from the pure logic, per the project's testing rules.


def test_landmark_to_pixel_rounds_to_nearest_int():
    p = LandmarkPoint(x=0.5, y=0.25, z=0.0)
    assert p.to_pixel(width=100, height=200) == (50, 50)


def test_hand_result_pixel_landmarks_and_get():
    points = [LandmarkPoint(x=i / 20, y=i / 20, z=0.0) for i in range(21)]
    hand = HandResult(landmarks=points, handedness="Right", score=0.9)
    pixels = hand.pixel_landmarks(width=200, height=200)
    assert len(pixels) == 21
    assert hand.get(8) is points[8]  # index fingertip — the brush cursor point


def test_to_hand_results_parses_landmarks_and_top_handedness():
    fake_landmark = SimpleNamespace(x=0.1, y=0.2, z=0.3)
    fake_category = SimpleNamespace(category_name="Right", score=0.87)
    fake_result = SimpleNamespace(
        hand_landmarks=[[fake_landmark] * 21],
        handedness=[[fake_category]],
    )

    hands = HandTracker._to_hand_results(fake_result)

    assert len(hands) == 1
    assert hands[0].handedness == "Right"
    assert hands[0].score == pytest.approx(0.87)
    assert len(hands[0].landmarks) == 21
    assert hands[0].landmarks[0] == LandmarkPoint(0.1, 0.2, 0.3)


def test_to_hand_results_handles_no_hands_detected():
    fake_result = SimpleNamespace(hand_landmarks=[], handedness=[])
    assert HandTracker._to_hand_results(fake_result) == []


def test_to_hand_results_handles_two_hands():
    lm = SimpleNamespace(x=0.0, y=0.0, z=0.0)
    left = SimpleNamespace(category_name="Left", score=0.7)
    right = SimpleNamespace(category_name="Right", score=0.9)
    fake_result = SimpleNamespace(
        hand_landmarks=[[lm] * 21, [lm] * 21],
        handedness=[[left], [right]],
    )
    hands = HandTracker._to_hand_results(fake_result)
    assert [h.handedness for h in hands] == ["Left", "Right"]


def test_ensure_model_returns_existing_cached_file(tmp_path):
    model_file = tmp_path / "hand_landmarker.task"
    model_file.write_bytes(b"cache hit test, not a real model")
    result = ensure_model(model_path=model_file)
    assert result == model_file


def test_ensure_model_raises_clear_error_when_download_fails(tmp_path, monkeypatch):
    import aircanvas.vision.tracker as tracker_module

    def boom(*args, **kwargs):
        raise OSError("no network in this test")

    monkeypatch.setattr(tracker_module.urllib.request, "urlretrieve", boom)
    missing_path = tmp_path / "models" / "hand_landmarker.task"

    with pytest.raises(ModelUnavailableError):
        ensure_model(model_path=missing_path)

    assert not missing_path.exists()  # no partial/corrupt file left behind


def test_ensure_model_downloads_when_missing(tmp_path, monkeypatch):
    import aircanvas.vision.tracker as tracker_module

    def fake_urlretrieve(url, dest):
        from pathlib import Path
        Path(dest).write_bytes(b"pretend-model-bytes")

    monkeypatch.setattr(tracker_module.urllib.request, "urlretrieve", fake_urlretrieve)
    target = tmp_path / "models" / "hand_landmarker.task"

    result = ensure_model(model_path=target)

    assert result == target
    assert target.read_bytes() == b"pretend-model-bytes"
