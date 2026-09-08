"""
Stroke-level undo/redo.

Each user action (adding a stroke, clearing the canvas) is recorded
as a small Action object that knows how to apply and revert itself
against a strokes list, rather than storing a full-resolution image
copy per action -- "prefer a command/stroke representation" per the
project spec.

Redo follows the standard invalidation rule: taking any new action
clears whatever was sitting on the redo stack.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Tuple

from aircanvas.canvas.stroke import Stroke


class Action(Protocol):
    def do(self, strokes: List[Stroke]) -> None: ...
    def undo(self, strokes: List[Stroke]) -> None: ...


@dataclass(frozen=True)
class AddStrokeAction:
    """Records one stroke having been added to the canvas."""

    stroke: Stroke

    def do(self, strokes: List[Stroke]) -> None:
        strokes.append(self.stroke)

    def undo(self, strokes: List[Stroke]) -> None:
        strokes.pop()


@dataclass(frozen=True)
class ClearCanvasAction:
    """Records every stroke that existed at the moment the canvas was
    cleared, so a single undo can bring all of them back at once."""

    removed: Tuple[Stroke, ...]

    def do(self, strokes: List[Stroke]) -> None:
        strokes.clear()

    def undo(self, strokes: List[Stroke]) -> None:
        strokes.extend(self.removed)


class History:
    """Generic two-stack undo/redo manager over any Action."""

    def __init__(self) -> None:
        self._undo_stack: List[Action] = []
        self._redo_stack: List[Action] = []

    def do(self, action: Action, strokes: List[Stroke]) -> None:
        action.do(strokes)
        self._undo_stack.append(action)
        self._redo_stack.clear()

    def undo(self, strokes: List[Stroke]) -> bool:
        if not self._undo_stack:
            return False
        action = self._undo_stack.pop()
        action.undo(strokes)
        self._redo_stack.append(action)
        return True

    def redo(self, strokes: List[Stroke]) -> bool:
        if not self._redo_stack:
            return False
        action = self._redo_stack.pop()
        action.do(strokes)
        self._undo_stack.append(action)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
