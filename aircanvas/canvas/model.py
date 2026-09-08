"""
The canvas document: an ordered list of strokes plus undo/redo.

Holds no pixel data itself -- strokes are the source of truth, so the
same model can back a live pygame surface today and a saved/replayed
project in a later phase without changing anything here.
"""
from __future__ import annotations

from typing import List, Tuple

from aircanvas.canvas.history import AddStrokeAction, ClearCanvasAction, History
from aircanvas.canvas.stroke import Stroke

DEFAULT_BACKGROUND_COLOR: Tuple[int, int, int] = (18, 18, 24)


class CanvasModel:
    def __init__(
        self,
        width: int,
        height: int,
        background_color: Tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR,
    ) -> None:
        self.width = width
        self.height = height
        self.background_color = background_color
        self._strokes: List[Stroke] = []
        self._history = History()

    @property
    def strokes(self) -> Tuple[Stroke, ...]:
        return tuple(self._strokes)

    @property
    def stroke_count(self) -> int:
        return len(self._strokes)

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def add_stroke(self, stroke: Stroke) -> None:
        """Record a completed stroke as one undoable action.

        Empty strokes (e.g. a stroke that started and ended on the
        same frame with no points) are silently ignored -- there's
        nothing meaningful to undo.
        """
        if stroke.is_empty:
            return
        self._history.do(AddStrokeAction(stroke), self._strokes)

    def clear(self) -> bool:
        """Clear all strokes as a single undoable action.

        Returns:
            True if there was anything to clear, False if the canvas
            was already empty (a no-op -- callers can use this to
            skip playing a "cleared" sound, etc.).
        """
        if not self._strokes:
            return False
        self._history.do(ClearCanvasAction(tuple(self._strokes)), self._strokes)
        return True

    def undo(self) -> bool:
        return self._history.undo(self._strokes)

    def redo(self) -> bool:
        return self._history.redo(self._strokes)

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo
