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
from typing import Optional, Tuple

APP_NAME = "AirCanvas"
APP_VERSION = "1.2.0"  # v1.0.0 = 8 phases complete; v1.1.0 = shape assist; v1.2.0 = live pointer sensitivity + automatic live shape assist


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


def get_projects_dir() -> Path:
    """Default directory for saved `.aircanvas` project files."""
    return get_app_data_dir() / "projects"


def get_exports_dir() -> Path:
    """Default directory for exported PNGs and share cards."""
    return get_app_data_dir() / "exports"


def get_recovery_path() -> Path:
    """Path to the auto-saved crash-recovery project.

    Written periodically while the app runs (see app.py) and cleared
    on a clean exit, so its presence at the next launch signals the
    previous session ended abnormally.
    """
    return get_app_data_dir() / "recovery.aircanvas"


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

    # -- Virtual canvas (target space the fingertip maps onto; the
    #    real drawable canvas widget arrives in Phase 3) --
    canvas_pixel_width: int = 1600
    canvas_pixel_height: int = 900
    canvas_background_color: Tuple[int, int, int] = (18, 18, 24)

    # -- Brush defaults (see canvas/brush_engine.py, canvas/brushes.py) --
    # "Support at least five sizes" -- diameters in canvas pixels.
    brush_sizes: Tuple[int, ...] = (4, 8, 14, 22, 34)
    default_brush_size_index: int = 2
    # A short curated starting palette; full color-wheel/picker UI is Phase 4.
    brush_palette: Tuple[Tuple[int, int, int], ...] = (
        (240, 240, 245),  # off-white ink
        (255, 87, 87),    # coral red
        (255, 196, 61),   # amber
        (94, 214, 148),   # mint green
        (94, 156, 255),   # sky blue
        (198, 120, 255),  # violet
    )
    default_palette_index: int = 0
    default_brush_type_index: int = 0  # index into canvas.brushes.SELECTABLE_BRUSHES

    # -- Living Ink / particles (see rendering/particles.py, rendering/effects.py) --
    particles_enabled: bool = True
    max_particles: int = 220
    living_ink_base_rate: float = 12.0
    living_ink_velocity_scale: float = 6.0
    living_ink_idle_rate: float = 2.0

    # -- Save/export/recovery (see persistence/project_io.py) --
    recovery_autosave_interval_sec: float = 15.0

    # -- Shape assist (see canvas/shape_assist.py) --
    # Off by default: it's a deliberate, opt-in correction, not a
    # silent one -- see the module docstring on what it can and can't
    # actually tell apart. Once on, detection and the live preview run
    # automatically while drawing -- no extra keypress needed per shape.
    shape_assist_enabled: bool = False
    shape_assist_min_points: int = 8
    shape_assist_min_confidence: float = 0.62
    shape_assist_min_stable_updates: int = 8

    # -- Pointer smoothing (see vision/smoothing.py) --
    smoothing_min_alpha: float = 0.15
    smoothing_max_alpha: float = 0.9
    smoothing_velocity_lower: float = 0.0
    smoothing_velocity_upper: float = 2.0
    smoothing_min_movement_threshold: float = 0.0025

    # -- Coordinate mapping (see vision/calibration.py) --
    canvas_margin: float = 0.08  # symmetric default; calibration overrides per-side
    # Gain around the center of the active region -- 1.0 = raw mapping,
    # lower = a given hand movement produces a smaller cursor movement
    # (easier fine control, at the cost of needing a bigger physical
    # motion to reach the canvas edges). Live-adjustable with , / . --
    # see app.py -- and persisted once tuned.
    pointer_sensitivity: float = 0.55

    # -- Gesture / intent state machine (see interaction/state_machine.py) --
    pinch_threshold: float = 0.35
    gesture_debounce_frames: int = 3
    hand_lost_grace_frames: int = 10
    fist_confirm_frames: int = 20

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
