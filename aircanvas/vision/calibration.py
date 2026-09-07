"""
Maps normalized [0, 1] camera-space fingertip coordinates to
canvas-pixel coordinates, with configurable margins (the active
region within the camera frame) and sensitivity (movement gain
around the center of that region).

Also provides a simple two-point Calibrator: capture the fingertip
position at the top-left and bottom-right of the area a person
naturally wants to paint in, and derive a MapperConfig from it. In
this phase there's no touchless UI yet to drive calibration end to
end, so the debug preview triggers it with keyboard shortcuts; a
fully touchless calibration flow arrives with the Phase 4 UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class MapperConfig:
    margin_left: float = 0.08
    margin_right: float = 0.08
    margin_top: float = 0.08
    margin_bottom: float = 0.08
    sensitivity: float = 1.0  # >1 amplifies movement around the center, <1 dampens it


class CoordinateMapper:
    """Converts normalized camera-space points into canvas pixel
    coordinates using the active-region margins and sensitivity in
    `config`."""

    def __init__(self, canvas_width: int, canvas_height: int, config: Optional[MapperConfig] = None) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.config = config or MapperConfig()

    def resize(self, width: int, height: int) -> None:
        self.canvas_width = width
        self.canvas_height = height

    def map(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        c = self.config
        x0, x1 = c.margin_left, 1.0 - c.margin_right
        y0, y1 = c.margin_top, 1.0 - c.margin_bottom

        # Position within the active region, as a 0..1 fraction.
        u = (norm_x - x0) / max(x1 - x0, 1e-6)
        v = (norm_y - y0) / max(y1 - y0, 1e-6)

        # Sensitivity scales movement around the center of the region
        # rather than the corner, so it feels like zooming the
        # response, not shifting it.
        u = 0.5 + (u - 0.5) * c.sensitivity
        v = 0.5 + (v - 0.5) * c.sensitivity

        u = min(max(u, 0.0), 1.0)
        v = min(max(v, 0.0), 1.0)
        return int(round(u * self.canvas_width)), int(round(v * self.canvas_height))


class Calibrator:
    """Two-point calibration: record the fingertip position at the
    top-left and bottom-right corners of the area someone wants to
    paint in, then derive the margins that make that area map to the
    full canvas."""

    def __init__(self) -> None:
        self._top_left: Optional[Tuple[float, float]] = None
        self._bottom_right: Optional[Tuple[float, float]] = None

    def set_top_left(self, x: float, y: float) -> None:
        self._top_left = (x, y)

    def set_bottom_right(self, x: float, y: float) -> None:
        self._bottom_right = (x, y)

    @property
    def has_top_left(self) -> bool:
        return self._top_left is not None

    @property
    def has_bottom_right(self) -> bool:
        return self._bottom_right is not None

    @property
    def is_complete(self) -> bool:
        return self.has_top_left and self.has_bottom_right

    def reset(self) -> None:
        self._top_left = None
        self._bottom_right = None

    def to_mapper_config(self, sensitivity: float = 1.0, max_margin: float = 0.45) -> MapperConfig:
        """Derive a MapperConfig from the two captured points.

        Raises:
            ValueError: if calibration hasn't captured both points yet.
        """
        if not self.is_complete:
            raise ValueError("Calibration incomplete: need both a top-left and a bottom-right point")

        x0, y0 = self._top_left
        x1, y1 = self._bottom_right

        # Guard against a person calibrating the two corners in the
        # "wrong" order or slightly overlapping them.
        left = min(x0, x1)
        right = 1.0 - max(x0, x1)
        top = min(y0, y1)
        bottom = 1.0 - max(y0, y1)

        clamp = lambda v: min(max(v, 0.0), max_margin)  # noqa: E731
        return MapperConfig(
            margin_left=clamp(left),
            margin_right=clamp(right),
            margin_top=clamp(top),
            margin_bottom=clamp(bottom),
            sensitivity=sensitivity,
        )
