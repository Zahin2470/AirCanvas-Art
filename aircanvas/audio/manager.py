"""
Audio manager: short, procedurally-generated tones for UI feedback
(brush activation, color/tool/size selection, erase, undo/redo,
clear, export complete, replay start), with graceful degradation --
if pygame's mixer can't initialize (no audio device, e.g. this
sandbox or a CI runner), every method becomes a safe no-op instead of
raising.

Tones are synthesized at construction time rather than shipped as
audio assets, so the app has no binary sound files to bundle or
hard-coded paths to load them from. Per the project spec ("do not
make continuous brush audio annoying"), every sound here is a short,
discrete one-shot triggered by a specific event -- nothing loops or
plays continuously while drawing.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pygame

logger = logging.getLogger("aircanvas.audio")

SAMPLE_RATE = 44100


def _tone(freq: float, duration: float, volume: float = 0.5, fade: bool = True, sweep_to: Optional[float] = None) -> np.ndarray:
    """Generate a mono float32 waveform in [-1, 1] for one short tone.
    `sweep_to`, if given, linearly slides the frequency from `freq` to
    that value over the tone's duration (used for undo/redo/clear's
    rising or falling "whoosh")."""
    n = max(1, int(SAMPLE_RATE * duration))
    if sweep_to is not None:
        freqs = np.linspace(freq, sweep_to, n)
        phase = np.cumsum(2 * np.pi * freqs / SAMPLE_RATE)
        wave = np.sin(phase)
    else:
        t = np.linspace(0, duration, n, endpoint=False)
        wave = np.sin(2 * np.pi * freq * t)
    if fade:
        fade_len = max(1, n // 8)
        envelope = np.ones(n)
        envelope[:fade_len] = np.linspace(0, 1, fade_len)
        envelope[-fade_len:] = np.linspace(1, 0, fade_len)
        wave = wave * envelope
    return (wave * volume).astype(np.float32)


def _two_tone(freq_a: float, freq_b: float, duration: float, volume: float = 0.5) -> np.ndarray:
    half = duration / 2
    return np.concatenate([_tone(freq_a, half, volume), _tone(freq_b, half, volume)])


def _default_waveforms() -> Dict[str, np.ndarray]:
    """Event name -> waveform. A plain function (not a constant) so
    retuning a pitch doesn't require touching AudioManager itself."""
    return {
        "brush_activate": _tone(660, 0.05, 0.35),
        "color_select": _tone(880, 0.06, 0.30),
        "tool_select": _tone(740, 0.06, 0.30),
        "size_select": _tone(500, 0.05, 0.30),
        "erase": _tone(220, 0.08, 0.30),
        "undo": _tone(500, 0.07, 0.35, sweep_to=350),
        "redo": _tone(350, 0.07, 0.35, sweep_to=500),
        "clear": _tone(200, 0.15, 0.35, sweep_to=100),
        "export_complete": _two_tone(660, 990, 0.16, 0.40),
        "replay_start": _tone(300, 0.25, 0.35, sweep_to=700),
    }


class AudioManager:
    """Call `play(event_name)` for any built-in event name; unknown
    names are silently ignored. Safe to construct and use even with
    no audio device -- see `available`."""

    def __init__(self, master_volume: float = 0.7, sfx_volume: float = 0.8, muted: bool = False) -> None:
        self.master_volume = max(0.0, min(1.0, master_volume))
        self.sfx_volume = max(0.0, min(1.0, sfx_volume))
        self.muted = muted
        self.available = False
        self._sounds: Dict[str, "pygame.mixer.Sound"] = {}
        self._init_mixer()

    def _init_mixer(self) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
            for name, wave in _default_waveforms().items():
                samples = np.clip(wave * 32767, -32768, 32767).astype(np.int16)
                self._sounds[name] = pygame.sndarray.make_sound(samples)
            self.available = True
        except Exception as exc:  # environment-dependent (no audio device, etc.)
            logger.info("Audio unavailable (%s); running muted.", exc)
            self.available = False
            self._sounds = {}

    def play(self, event_name: str) -> None:
        if not self.available or self.muted:
            return
        sound = self._sounds.get(event_name)
        if sound is None:
            return
        sound.set_volume(self.master_volume * self.sfx_volume)
        sound.play()

    def set_master_volume(self, value: float) -> None:
        self.master_volume = max(0.0, min(1.0, value))

    def set_sfx_volume(self, value: float) -> None:
        self.sfx_volume = max(0.0, min(1.0, value))

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted
