"""
Persisted user preferences: theme, brush/color/size defaults, audio
settings, mirror mode, and particle/performance settings.

Stored as plain JSON at get_app_data_dir()/settings.json -- that path
is derived from the user's home directory (or $AIRCANVAS_HOME), never
hard-coded. A missing or corrupt settings file never crashes startup:
load_settings() falls back to AppSettings() defaults and logs a
warning instead of raising.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from aircanvas.config import get_app_data_dir

logger = logging.getLogger("aircanvas.persistence.settings")

SETTINGS_FORMAT_VERSION = 1


def get_settings_path() -> Path:
    return get_app_data_dir() / "settings.json"


@dataclass
class AppSettings:
    theme: str = "dark"
    brush_type_index: int = 0
    color_index: int = 0
    size_index: int = 2
    mirror: bool = True
    particles_enabled: bool = True
    master_volume: float = 0.7
    sfx_volume: float = 0.8
    muted: bool = False

    def clamped(self) -> "AppSettings":
        """A copy with numeric fields clamped to safe ranges -- used
        right after loading, so a hand-edited or corrupted settings
        file can't smuggle in e.g. a volume of 400."""
        return AppSettings(
            theme=str(self.theme),
            brush_type_index=max(0, int(self.brush_type_index)),
            color_index=max(0, int(self.color_index)),
            size_index=max(0, int(self.size_index)),
            mirror=bool(self.mirror),
            particles_enabled=bool(self.particles_enabled),
            master_volume=min(max(float(self.master_volume), 0.0), 1.0),
            sfx_volume=min(max(float(self.sfx_volume), 0.0), 1.0),
            muted=bool(self.muted),
        )


def save_settings(settings: AppSettings, path: Optional[Path] = None) -> Path:
    """Write `settings` to `path` (default: get_settings_path()) as
    JSON, atomically (temp file + rename)."""
    path = path or get_settings_path()
    payload = {"version": SETTINGS_FORMAT_VERSION, **asdict(settings)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(path)
    return path


def load_settings(path: Optional[Path] = None) -> AppSettings:
    """Read persisted settings, or AppSettings() defaults if the file
    is missing, unreadable, not valid JSON, not an object, or has
    fields of the wrong type. Never raises."""
    path = path or get_settings_path()
    if not path.exists():
        return AppSettings()

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read settings from %s (%s); using defaults.", path, exc)
        return AppSettings()

    if not isinstance(payload, dict):
        logger.warning("Settings file %s is not a JSON object; using defaults.", path)
        return AppSettings()

    known_fields = set(AppSettings.__dataclass_fields__)
    clean = {k: v for k, v in payload.items() if k in known_fields}
    try:
        return AppSettings(**clean).clamped()
    except (TypeError, ValueError) as exc:
        logger.warning("Settings file %s has invalid values (%s); using defaults.", path, exc)
        return AppSettings()
