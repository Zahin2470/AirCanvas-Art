import os

# The dummy SDL audio driver lets pygame.mixer initialize deterministically
# in any environment (this sandbox, CI, a real machine) without touching
# real audio hardware -- set only for this test module, never in production
# code, so real users still get real audio.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pytest

from aircanvas.audio.manager import AudioManager, _default_waveforms, _tone, _two_tone


def test_tone_has_the_requested_sample_count():
    wave = _tone(440, 0.1)
    assert len(wave) == pytest.approx(4410, abs=2)


def test_tone_stays_within_unit_amplitude():
    wave = _tone(440, 0.2, volume=1.0)
    assert wave.max() <= 1.0
    assert wave.min() >= -1.0


def test_tone_volume_scales_amplitude():
    loud = _tone(440, 0.1, volume=1.0, fade=False)
    quiet = _tone(440, 0.1, volume=0.2, fade=False)
    assert np.abs(loud).max() > np.abs(quiet).max()


def test_faded_tone_starts_and_ends_near_zero():
    wave = _tone(440, 0.2, volume=1.0, fade=True)
    assert abs(wave[0]) < 0.05
    assert abs(wave[-1]) < 0.05


def test_sweep_changes_frequency_over_the_tone():
    # A sweep from low to high should have a shorter period (faster
    # oscillation) near the end than near the start.
    wave = _tone(200, 0.3, volume=1.0, fade=False, sweep_to=2000)
    early = wave[:1000]
    late = wave[-1000:]
    early_zero_crossings = np.sum(np.diff(np.sign(early)) != 0)
    late_zero_crossings = np.sum(np.diff(np.sign(late)) != 0)
    assert late_zero_crossings > early_zero_crossings


def test_two_tone_is_twice_the_duration_of_each_half():
    half = _tone(440, 0.1)
    combined = _two_tone(440, 660, 0.2)
    assert len(combined) == pytest.approx(len(half) * 2, abs=4)


def test_default_waveforms_cover_all_expected_events():
    waveforms = _default_waveforms()
    expected = {
        "brush_activate", "color_select", "tool_select", "size_select", "erase",
        "undo", "redo", "clear", "export_complete", "replay_start",
    }
    assert set(waveforms.keys()) == expected


def test_default_waveforms_are_all_non_empty():
    for name, wave in _default_waveforms().items():
        assert len(wave) > 0, name


# -- AudioManager -------------------------------------------------------

def test_manager_constructs_without_raising():
    AudioManager()  # should not raise regardless of audio availability


def test_play_never_raises_even_for_unknown_event():
    manager = AudioManager()
    manager.play("not_a_real_event")  # should not raise


def test_play_never_raises_when_muted():
    manager = AudioManager(muted=True)
    manager.play("brush_activate")  # should not raise


def test_unavailable_manager_is_a_safe_no_op(monkeypatch):
    import pygame

    def boom(*args, **kwargs):
        raise RuntimeError("no audio device")

    monkeypatch.setattr(pygame.mixer, "init", boom)
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    manager = AudioManager()
    assert manager.available is False
    manager.play("brush_activate")  # should not raise


def test_volume_setters_clamp_to_unit_range():
    manager = AudioManager()
    manager.set_master_volume(5.0)
    assert manager.master_volume == 1.0
    manager.set_master_volume(-5.0)
    assert manager.master_volume == 0.0
    manager.set_sfx_volume(2.0)
    assert manager.sfx_volume == 1.0


def test_toggle_mute_flips_state_and_returns_new_state():
    manager = AudioManager(muted=False)
    assert manager.toggle_mute() is True
    assert manager.muted is True
    assert manager.toggle_mute() is False
    assert manager.muted is False


def test_constructor_clamps_initial_volumes():
    manager = AudioManager(master_volume=3.0, sfx_volume=-1.0)
    assert manager.master_volume == 1.0
    assert manager.sfx_volume == 0.0


def test_adapts_to_a_mixer_already_initialized_in_stereo():
    # pygame.init() (called once at real app startup) can initialize
    # the mixer in stereo before AudioManager ever runs -- this was a
    # real bug found during Phase 8 smoke testing: sound generation
    # silently failed (caught as "unavailable") on the channel-count
    # mismatch. Regression test: force a stereo mixer first, then
    # confirm AudioManager still comes up available and can play.
    import pygame

    pygame.mixer.quit()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    try:
        manager = AudioManager()
        assert manager.available is True
        manager.play("brush_activate")  # should not raise
    finally:
        pygame.mixer.quit()
