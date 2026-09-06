import numpy as np
import pytest

from aircanvas.vision import camera as camera_module
from aircanvas.vision.camera import Camera, CameraError


class FakeCapture:
    """Minimal stand-in for cv2.VideoCapture, hardware-free."""

    def __init__(self, opened=True, frames=None):
        self._opened = opened
        self._frames = frames if frames is not None else [np.zeros((4, 4, 3), dtype=np.uint8)]
        self._i = 0
        self.released = False
        self.props = {}

    def isOpened(self):
        return self._opened

    def set(self, prop, value):
        self.props[prop] = value

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        frame = self._frames[self._i]
        self._i += 1
        return True, frame

    def release(self):
        self.released = True


def test_open_success(monkeypatch):
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: FakeCapture(opened=True))
    cam = Camera(index=0, open_retries=1, retry_delay_sec=0)
    cam.open()
    assert cam.is_opened


def test_open_failure_raises_camera_error_after_retries(monkeypatch):
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: FakeCapture(opened=False))
    cam = Camera(index=0, open_retries=2, retry_delay_sec=0)
    with pytest.raises(CameraError):
        cam.open()


def test_read_returns_none_when_not_opened():
    cam = Camera()
    assert cam.read() is None


def test_read_mirrors_frame_when_configured(monkeypatch):
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    frame[:, 0] = 1  # mark the left column
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: FakeCapture(opened=True, frames=[frame]))
    cam = Camera(index=0, mirror=True, open_retries=1, retry_delay_sec=0)
    cam.open()
    result = cam.read()
    assert result[:, -1].sum() > 0  # marked column moved to the right edge after mirroring


def test_read_does_not_mirror_when_disabled(monkeypatch):
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    frame[:, 0] = 1
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: FakeCapture(opened=True, frames=[frame]))
    cam = Camera(index=0, mirror=False, open_retries=1, retry_delay_sec=0)
    cam.open()
    result = cam.read()
    assert result[:, 0].sum() > 0  # marked column stayed on the left


def test_read_tracks_consecutive_failures(monkeypatch):
    fake = FakeCapture(opened=True, frames=[])
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: fake)
    cam = Camera(index=0, open_retries=1, retry_delay_sec=0)
    cam.open()
    assert cam.read() is None
    assert cam.consecutive_failures == 1
    assert cam.read() is None
    assert cam.consecutive_failures == 2


def test_successful_read_resets_failure_count(monkeypatch):
    frames = [None]  # placeholder, replaced below to control ordering explicitly
    good_frame = np.zeros((2, 2, 3), dtype=np.uint8)
    fake = FakeCapture(opened=True, frames=[])
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: fake)
    cam = Camera(index=0, open_retries=1, retry_delay_sec=0)
    cam.open()
    assert cam.read() is None
    assert cam.consecutive_failures == 1
    fake._frames.append(good_frame)
    assert cam.read() is not None
    assert cam.consecutive_failures == 0


def test_context_manager_releases_camera(monkeypatch):
    fake = FakeCapture(opened=True)
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda idx: fake)
    with Camera(index=0, open_retries=1, retry_delay_sec=0) as cam:
        assert cam.is_opened
    assert fake.released


def test_change_index_reopens_camera(monkeypatch):
    opened_indices = []

    def factory(idx):
        opened_indices.append(idx)
        return FakeCapture(opened=True)

    monkeypatch.setattr(camera_module.cv2, "VideoCapture", factory)
    cam = Camera(index=0, open_retries=1, retry_delay_sec=0)
    cam.open()
    cam.change_index(2)
    assert cam.index == 2
    assert opened_indices == [0, 2]
