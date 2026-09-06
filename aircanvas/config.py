"""
Central configuration for AirCanvas.

Phase 1 scope is deliberately narrow: camera + hand-tracking + basic
runtime settings. User-facing preference persistence (theme, brush,
color, audio, mirror mode, etc.) arrives in a later phase and will
layer on top of this module rather than replace it — see
`aircanvas/persistence/settings.py` (placeholder for now).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

APP_NAME = "AirCanvas"
APP_VERSION = "0.1.0"  # Phase 1: skeleton, config, camera, tracker, tests


def get_app_data_dir() -> Path:
    """Per-user directory for AirCanvas data (settings, cache, models).

    Never hard-codes a personal path: it always derives from the
    current user's home directory, unless overridden via the
    AIRCANVAS_HOME environment variable (handy for tests and CI).
    """
    override = os.environ.get("AIRCANVAS_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".aircanvas"


def get_models_dir() -> Path:
    """Directory where downloaded ML models (e.g. hand_landmarker.task)
    are cached so they only need to be fetched once per machine."""
    return get_app_data_dir() / "models"


@dataclass(frozen=True)
class AppConfig:
    """Immutable runtime configuration.

    Use `AppConfig()` for defaults, or `load_config(overrides=...)` to
    merge CLI / environment overrides on top of the defaults without
    mutating them in place.
    """

    # -- Camera --
    camera_index: int = 0
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: int = 30
    mirror: bool = True
    camera_open_retries: int = 3
    camera_retry_delay_sec: float = 0.5

    # -- Hand tracking --
    max_num_hands: int = 1
    min_hand_detection_confidence: float = 0.6
    min_hand_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    hand_model_path: Optional[Path] = None  # None => auto-download/cache

    # -- App --
    debug: bool = False


def load_config(overrides: Optional[dict] = None) -> AppConfig:
    """Return an AppConfig with `overrides` applied on top of defaults.

    Unknown keys and None values are ignored defensively — e.g. a
    stale settings file from a future phase, or an unset CLI flag —
    so config loading can never crash the app on a bad or partial
    override dict.
    """
    base = AppConfig()
    if not overrides:
        return base
    known_fields = set(base.__dataclass_fields__)
    clean = {k: v for k, v in overrides.items() if k in known_fields and v is not None}
    return replace(base, **clean)
