"""
Visual themes for the app's UI chrome (panels, toolbar, status bar,
borders, widget states). Deliberately scoped to chrome only -- a
theme never changes canvas_model.background_color, since that's part
of the artwork's own data, not a display preference; switching themes
mid-session never alters anything already drawn.

Four themes per the project spec's Visual Style section: a dark
default, a light mode, a neon mode, and a monochrome mode (the latter
two doubling as higher-contrast options).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    name: str
    panel_bg: Color
    toolbar_bg: Color
    status_bg: Color
    border_color: Color
    widget_bg: Color
    widget_selected_bg: Color
    widget_border: Color
    widget_border_selected: Color
    widget_text: Color
    status_text: Color
    accent_color: Color
    hover_glow: Color


DARK = Theme(
    name="dark",
    panel_bg=(10, 10, 13), toolbar_bg=(22, 22, 27), status_bg=(16, 16, 20), border_color=(60, 60, 66),
    widget_bg=(46, 46, 52), widget_selected_bg=(60, 130, 90), widget_border=(110, 110, 118),
    widget_border_selected=(255, 255, 255), widget_text=(225, 225, 230), status_text=(200, 200, 205),
    accent_color=(90, 190, 255), hover_glow=(255, 255, 255),
)

LIGHT = Theme(
    name="light",
    panel_bg=(238, 238, 242), toolbar_bg=(250, 250, 252), status_bg=(225, 225, 230), border_color=(190, 190, 196),
    widget_bg=(255, 255, 255), widget_selected_bg=(190, 225, 205), widget_border=(200, 200, 206),
    widget_border_selected=(40, 40, 44), widget_text=(30, 30, 34), status_text=(50, 50, 55),
    accent_color=(40, 120, 220), hover_glow=(40, 40, 44),
)

NEON = Theme(
    name="neon",
    panel_bg=(6, 6, 14), toolbar_bg=(14, 10, 26), status_bg=(10, 8, 20), border_color=(120, 40, 200),
    widget_bg=(24, 16, 42), widget_selected_bg=(255, 0, 170), widget_border=(160, 60, 255),
    widget_border_selected=(0, 255, 220), widget_text=(220, 220, 255), status_text=(180, 160, 255),
    accent_color=(0, 255, 220), hover_glow=(255, 0, 200),
)

MONOCHROME = Theme(
    name="monochrome",
    panel_bg=(20, 20, 20), toolbar_bg=(30, 30, 30), status_bg=(15, 15, 15), border_color=(90, 90, 90),
    widget_bg=(50, 50, 50), widget_selected_bg=(160, 160, 160), widget_border=(110, 110, 110),
    widget_border_selected=(255, 255, 255), widget_text=(220, 220, 220), status_text=(190, 190, 190),
    accent_color=(200, 200, 200), hover_glow=(255, 255, 255),
)

THEMES = {t.name: t for t in (DARK, LIGHT, NEON, MONOCHROME)}
THEME_ORDER = ["dark", "light", "neon", "monochrome"]


def get_theme(name: str) -> Theme:
    """Look up a theme by name, falling back to DARK for an unknown
    name (e.g. a stale value from an old settings file) rather than
    raising."""
    return THEMES.get(name, DARK)


def next_theme_name(name: str) -> str:
    """The next theme name after `name` in THEME_ORDER, wrapping
    around -- used by the in-app theme-cycle key."""
    try:
        index = THEME_ORDER.index(name)
    except ValueError:
        index = -1  # unknown current theme -> first theme in the cycle
    return THEME_ORDER[(index + 1) % len(THEME_ORDER)]
