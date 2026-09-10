"""
Artwork replay: reconstructs a finished canvas stroke-by-stroke (and,
where per-point timing was recorded, point-by-point) so the *process*
of drawing can be watched back, not just the final PNG.

Reads stroke data only -- it never touches how strokes were rendered
live, so replay works identically for a project just drawn and one
loaded from disk (see persistence/project_io.py) a week later.

Timing model: each stroke's own pacing comes from `point_times` when
available (see canvas/stroke.py), falling back to assuming evenly-
spaced points when it isn't. The *gap* between one stroke ending and
the next starting uses the real difference between their `created_at`
timestamps, clamped to a sane range -- long enough to read as a
pause, short enough that a real coffee-break mid-drawing doesn't
stall playback for actual minutes.

Known limitation: a project loaded from an older save with no
point_times recorded replays with assumed-even pacing rather than the
original rhythm -- still watchable, just not perfectly faithful.
Worth flagging rather than hiding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.stroke import Stroke

DEFAULT_POINT_INTERVAL_SECONDS = 1.0 / 30  # assumed spacing when a stroke has no point_times
MIN_STROKE_GAP_SECONDS = 0.05
MAX_STROKE_GAP_SECONDS = 2.0


def _stroke_duration(stroke: Stroke) -> float:
    if stroke.point_times and len(stroke.point_times) == len(stroke.points):
        return max(stroke.point_times[-1], 0.0)
    return max(len(stroke.points) - 1, 0) * DEFAULT_POINT_INTERVAL_SECONDS


@dataclass(frozen=True)
class TimelineEntry:
    stroke_index: int
    start_time: float  # seconds from the start of the whole replay
    end_time: float


def build_timeline(strokes: List[Stroke]) -> List[TimelineEntry]:
    """Lay strokes out along a single replay timeline, using each
    stroke's real recorded duration and the real (clamped) gap to the
    next stroke's start time."""
    timeline: List[TimelineEntry] = []
    t = 0.0
    previous_created_at = None
    for i, stroke in enumerate(strokes):
        if previous_created_at is not None:
            gap = stroke.created_at - previous_created_at
            gap = max(MIN_STROKE_GAP_SECONDS, min(gap, MAX_STROKE_GAP_SECONDS))
            t += gap
        duration = _stroke_duration(stroke)
        timeline.append(TimelineEntry(stroke_index=i, start_time=t, end_time=t + duration))
        t += duration
        previous_created_at = stroke.created_at
    return timeline


def total_duration(timeline: List[TimelineEntry]) -> float:
    return timeline[-1].end_time if timeline else 0.0


def points_visible_at(stroke: Stroke, entry: TimelineEntry, playback_time: float) -> int:
    """How many of `stroke`'s points should be visible if the replay
    clock reads `playback_time` (seconds from the start of the whole
    replay). 0 before the stroke starts, len(points) once it's done."""
    if not stroke.points or playback_time <= entry.start_time:
        return 0
    if playback_time >= entry.end_time:
        return len(stroke.points)

    local_t = playback_time - entry.start_time
    if stroke.point_times and len(stroke.point_times) == len(stroke.points):
        count = 0
        for pt in stroke.point_times:
            if pt <= local_t:
                count += 1
            else:
                break
        return max(count, 1)

    duration = max(entry.end_time - entry.start_time, 1e-6)
    fraction = local_t / duration
    return max(1, int(round(fraction * len(stroke.points))))


class ReplayController:
    """Owns replay playback state -- current time, play/pause, speed --
    and knows how to render whatever should currently be visible."""

    def __init__(self, strokes: List[Stroke]) -> None:
        self.strokes: List[Stroke] = []
        self.timeline: List[TimelineEntry] = []
        self.duration: float = 0.0
        self.set_strokes(strokes)
        self.playback_time = 0.0
        self.speed = 1.0
        self.is_playing = False

    def set_strokes(self, strokes: List[Stroke]) -> None:
        self.strokes = list(strokes)
        self.timeline = build_timeline(self.strokes)
        self.duration = total_duration(self.timeline)

    @property
    def progress(self) -> float:
        if self.duration <= 0:
            return 1.0
        return min(self.playback_time / self.duration, 1.0)

    @property
    def is_finished(self) -> bool:
        return self.playback_time >= self.duration

    def play(self) -> None:
        if self.is_finished:
            self.restart()
        self.is_playing = True

    def pause(self) -> None:
        self.is_playing = False

    def toggle(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def restart(self) -> None:
        self.playback_time = 0.0

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.1, min(speed, 8.0))

    def seek(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        self.playback_time = fraction * self.duration

    def seek_relative(self, delta_fraction: float) -> None:
        self.seek(self.progress + delta_fraction)

    def advance(self, dt: float) -> None:
        """Step playback forward by `dt` real seconds (multiplied by
        `speed` internally). No-op while paused."""
        if not self.is_playing:
            return
        self.playback_time += dt * self.speed
        if self.playback_time >= self.duration:
            self.playback_time = self.duration
            self.is_playing = False

    def visible_strokes(self) -> List[Tuple[Stroke, int]]:
        """(stroke, point_count) pairs for everything that should
        currently be at least partly drawn."""
        result = []
        for stroke, entry in zip(self.strokes, self.timeline):
            count = points_visible_at(stroke, entry, self.playback_time)
            if count > 0:
                result.append((stroke, count))
        return result

    def render(self, surface, brush_engine: BrushEngine, background_color: Tuple[int, int, int]) -> None:
        """Draw the current playback frame onto `surface` from scratch."""
        surface.fill(background_color)
        for stroke, count in self.visible_strokes():
            if count >= len(stroke.points):
                brush_engine.render_stroke(surface, stroke)
            else:
                partial = Stroke(
                    points=stroke.points[:count],
                    point_times=stroke.point_times[:count],
                    color=stroke.color,
                    size=stroke.size,
                    opacity=stroke.opacity,
                    brush_type=stroke.brush_type,
                    created_at=stroke.created_at,
                )
                brush_engine.render_stroke(surface, partial)
