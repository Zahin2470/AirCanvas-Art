"""
Touchless toolbar: hover-and-dwell widgets for color, brush size, and
undo/redo.

Matches the project's gesture-driven UI flow (HAND DETECTED ->
POINTING -> PINCH -> SELECTED -> ACTION COMPLETE): pointing at a
widget highlights it, and holding a pinch over it for a short,
deliberate dwell -- not an instant tap -- fires the action. The dwell
requirement is the same hysteresis principle the drawing state
machine uses: it keeps a pinch that's just passing through the
toolbar (e.g. dragging a stroke that happens to cross it) from
accidentally activating a button.

Independent of pygame's event system and of *how* a pinch was
detected (real hand or developer-mode mouse) -- callers just feed it
a cursor position and whether "select" is currently held. Also
independent of rendering: this module only tracks hover/dwell state
and hit-testing; app.py draws the widgets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

Point = Tuple[int, int]

# ~0.3s at 60fps -- deliberate enough that dragging a stroke through
# the toolbar area won't accidentally activate a button.
DEFAULT_DWELL_FRAMES = 18


@dataclass
class Widget:
    id: str
    rect: "pygame.Rect"
    label: str = ""
    swatch_color: Optional[Tuple[int, int, int]] = None  # for color swatches
    is_selected: bool = False  # e.g. the currently active color/size/tool


@dataclass(frozen=True)
class ToolbarResult:
    hovered_id: Optional[str] = None
    activated_id: Optional[str] = None  # set on exactly the frame dwell completes
    hover_progress: float = 0.0  # 0..1 dwell progress on the hovered widget


class Toolbar:
    def __init__(self, widgets: List[Widget], dwell_frames: int = DEFAULT_DWELL_FRAMES) -> None:
        self.widgets = widgets
        self.dwell_frames = max(1, dwell_frames)
        self._hovered_id: Optional[str] = None
        self._dwell_count = 0

    def widget_at(self, pos: Point) -> Optional[Widget]:
        for widget in self.widgets:
            if widget.rect.collidepoint(pos):
                return widget
        return None

    def widget_by_id(self, widget_id: str) -> Optional[Widget]:
        return next((w for w in self.widgets if w.id == widget_id), None)

    def update(self, cursor_pos: Optional[Point], selecting: bool) -> ToolbarResult:
        """Advance one frame. `selecting` is True while the user is
        pinching (or holding the dev-mode select button) with the
        cursor over the toolbar."""
        widget = self.widget_at(cursor_pos) if cursor_pos is not None else None

        if widget is None:
            self._hovered_id = None
            self._dwell_count = 0
            return ToolbarResult()

        if widget.id != self._hovered_id:
            self._hovered_id = widget.id
            self._dwell_count = 0

        if not selecting:
            self._dwell_count = 0
            return ToolbarResult(hovered_id=widget.id, hover_progress=0.0)

        self._dwell_count += 1
        progress = min(self._dwell_count / self.dwell_frames, 1.0)
        if self._dwell_count >= self.dwell_frames:
            self._dwell_count = 0  # so holding still doesn't repeat-fire every frame
            return ToolbarResult(hovered_id=widget.id, activated_id=widget.id, hover_progress=1.0)
        return ToolbarResult(hovered_id=widget.id, hover_progress=progress)
