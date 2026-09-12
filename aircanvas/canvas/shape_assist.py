"""
Shape assist: recognizes a few geometric primitives and aspect-ratio
templates in a freshly-completed stroke, and offers a clean
replacement for it.

Scope, stated plainly (this matters more than usual here): this is
pure geometry, not object recognition. It can tell a closed
four-cornered shape from a five-pointed star, because those really
are different shapes. It cannot tell a book from a rectangle, because
a book drawn as a rectangle *is* a rectangle -- there is no shape-only
signal that distinguishes them. "Book" here means "a closed
four-cornered shape whose aspect ratio falls in a book-like band",
not "AirCanvas recognized a book". See BOOK_ASPECT_RATIO_RANGE below;
widen or narrow it to taste.

Used only when explicitly enabled (shape assist defaults to off) --
see app.py's K key and persistence/settings.py. Only ever replaces the
stroke's *points*; color, size, opacity, and brush_type carry over
unchanged, so a shape drawn with Neon Glow snaps to a clean Neon Glow
shape, not a plain one.

Deterministic and stateless: classify_stroke is a pure function of the
points it's given, with no hidden state and no randomness, so the
same rough sketch always classifies the same way.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from aircanvas.canvas.stroke import Point, Stroke

# -- Tunable thresholds ------------------------------------------------
# All ratios, so they scale with the stroke's own size rather than a
# fixed pixel count -- a tiny sketch and a huge one classify the same
# way as long as their proportions match.

MIN_POINTS = 8
MIN_BOUNDING_DIAGONAL = 20.0  # ignore near-single-point taps entirely

CLOSURE_RATIO = 0.28          # start-to-end distance / bbox diagonal, below which a path counts as "closed"
LINE_STRAIGHTNESS_RATIO = 0.08  # max perpendicular deviation / path length, below which an open path counts as "straight"

CORNER_EPSILON_RATIO = 0.045  # RDP simplification tolerance / bbox diagonal
CORNER_MERGE_RATIO = 0.12     # distance below which two simplified corners / the closing corner are merged as "the same point"

CIRCULARITY_MAX_CV = 0.22     # max coefficient of variation of centroid-distance for an "ellipse"

STAR_ANGLE_BINS = 36
STAR_MIN_PEAKS = 4
STAR_MAX_PEAKS = 7
STAR_PROMINENCE_RATIO = 0.22  # min (peak - adjacent valley) / mean radius to count as a real point of a star

BOOK_ASPECT_RATIO_RANGE = (1.15, 1.9)  # long side / short side -- see module docstring

ELLIPSE_RENDER_POINTS = 48
STAR_RENDER_POINTS_PER_ARM = 1  # a 5-armed star is rendered as 10 vertices (outer, inner) x 5


class ShapeKind(Enum):
    LINE = "line"
    TRIANGLE = "triangle"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    STAR = "star"
    BOOK = "book"


DISPLAY_NAMES = {
    ShapeKind.LINE: "Line",
    ShapeKind.TRIANGLE: "Triangle",
    ShapeKind.RECTANGLE: "Rectangle",
    ShapeKind.ELLIPSE: "Ellipse",
    ShapeKind.STAR: "Star",
    ShapeKind.BOOK: "Book",
}


@dataclass(frozen=True)
class ShapeMatch:
    kind: ShapeKind
    points: List[Point]  # the idealized replacement path
    label: str           # human-readable, for a status-bar toast


# -- Basic geometry helpers ---------------------------------------------

def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _bounding_box(points: List[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _centroid(points: List[Point]) -> Point:
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _path_length(points: List[Point]) -> float:
    return sum(_distance(a, b) for a, b in zip(points, points[1:]))


def _point_line_distance(point: Point, start: Point, end: Point) -> float:
    if start == end:
        return _distance(point, start)
    x0, y0 = point
    x1, y1 = start
    x2, y2 = end
    numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def _rdp(points: List[Point], epsilon: float) -> List[Point]:
    """Ramer-Douglas-Peucker polyline simplification."""
    if len(points) < 3:
        return list(points)
    start, end = points[0], points[-1]
    max_dist, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _point_line_distance(points[i], start, end)
        if d > max_dist:
            max_dist, index = d, i
    if max_dist > epsilon:
        left = _rdp(points[: index + 1], epsilon)
        right = _rdp(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def _merge_close_points(points: List[Point], min_distance: float) -> List[Point]:
    """Drop consecutive points closer together than `min_distance` --
    used to collapse a near-duplicate closing vertex after RDP."""
    if not points:
        return points
    merged = [points[0]]
    for p in points[1:]:
        if _distance(p, merged[-1]) >= min_distance:
            merged.append(p)
    if len(merged) > 1 and _distance(merged[0], merged[-1]) < min_distance:
        merged.pop()
    return merged


# -- Classification -------------------------------------------------------

def classify_stroke(
    points: List[Point],
    min_points: int = MIN_POINTS,
) -> Optional[ShapeMatch]:
    """Try to recognize `points` as one of the supported shapes.
    Returns None (leave the stroke as freeform ink) when nothing
    matches confidently -- this is the common case for real
    freeform drawing, by design."""
    if len(points) < min_points:
        return None

    x0, y0, x1, y1 = _bounding_box(points)
    width, height = x1 - x0, y1 - y0
    diagonal = math.hypot(width, height)
    if diagonal < MIN_BOUNDING_DIAGONAL:
        return None

    closure = _distance(points[0], points[-1]) / diagonal
    is_closed = closure <= CLOSURE_RATIO

    if not is_closed:
        return _classify_open_path(points, diagonal)
    return _classify_closed_path(points, (x0, y0, x1, y1), diagonal)


def _classify_open_path(points: List[Point], diagonal: float) -> Optional[ShapeMatch]:
    start, end = points[0], points[-1]
    straight_length = _distance(start, end)
    if straight_length <= 0:
        return None
    max_deviation = max(_point_line_distance(p, start, end) for p in points)
    if (max_deviation / straight_length) <= LINE_STRAIGHTNESS_RATIO:
        return ShapeMatch(kind=ShapeKind.LINE, points=[start, end], label=DISPLAY_NAMES[ShapeKind.LINE])
    return None  # an open, non-straight path is just freeform ink


def _classify_closed_path(
    points: List[Point], bbox: Tuple[float, float, float, float], diagonal: float
) -> Optional[ShapeMatch]:
    star = _try_star(points, bbox, diagonal)
    if star is not None:
        return star

    epsilon = diagonal * CORNER_EPSILON_RATIO
    simplified = _rdp(points, epsilon)
    simplified = _merge_close_points(simplified, diagonal * CORNER_MERGE_RATIO)
    corners = len(simplified) - 1 if len(simplified) > 1 and simplified[0] == simplified[-1] else len(simplified)

    if corners == 3:
        triangle = simplified[:3]
        return ShapeMatch(kind=ShapeKind.TRIANGLE, points=triangle + [triangle[0]], label=DISPLAY_NAMES[ShapeKind.TRIANGLE])

    if corners == 4:
        return _rectangle_or_book(bbox)

    return _try_ellipse(points, bbox)


def _rectangle_or_book(bbox: Tuple[float, float, float, float]) -> ShapeMatch:
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    long_side, short_side = max(width, height), max(min(width, height), 1e-6)
    aspect_ratio = long_side / short_side

    outline = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    if BOOK_ASPECT_RATIO_RANGE[0] <= aspect_ratio <= BOOK_ASPECT_RATIO_RANGE[1]:
        mid_top = ((x0 + x1) / 2, y0)
        mid_bottom = ((x0 + x1) / 2, y1)
        # Trace the outline, then the spine down and back up -- still
        # one continuous path, so it's still one Stroke.
        book_path = outline + [mid_top, mid_bottom, mid_top]
        return ShapeMatch(kind=ShapeKind.BOOK, points=book_path, label=DISPLAY_NAMES[ShapeKind.BOOK])
    return ShapeMatch(kind=ShapeKind.RECTANGLE, points=outline, label=DISPLAY_NAMES[ShapeKind.RECTANGLE])


def _try_ellipse(points: List[Point], bbox: Tuple[float, float, float, float]) -> Optional[ShapeMatch]:
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = max((x1 - x0) / 2, 1e-6), max((y1 - y0) / 2, 1e-6)

    # Normalize each point by the bounding box's half-extents before
    # measuring "roundness": a true ellipse of any aspect ratio maps
    # to a perfect unit circle under this transform, so the check
    # works the same for a circle and a very flat ellipse alike,
    # rather than only recognizing near-circular shapes.
    normalized_radii = [math.hypot((x - cx) / rx, (y - cy) / ry) for x, y in points]
    mean_radius = sum(normalized_radii) / len(normalized_radii)
    if mean_radius <= 0:
        return None
    variance = sum((r - mean_radius) ** 2 for r in normalized_radii) / len(normalized_radii)
    coefficient_of_variation = math.sqrt(variance) / mean_radius
    if coefficient_of_variation > CIRCULARITY_MAX_CV:
        return None  # not round enough, and not a clean polygon either -- leave it freeform

    ellipse = [
        (cx + rx * math.cos(2 * math.pi * i / ELLIPSE_RENDER_POINTS), cy + ry * math.sin(2 * math.pi * i / ELLIPSE_RENDER_POINTS))
        for i in range(ELLIPSE_RENDER_POINTS + 1)
    ]
    return ShapeMatch(kind=ShapeKind.ELLIPSE, points=ellipse, label=DISPLAY_NAMES[ShapeKind.ELLIPSE])


def _try_star(points: List[Point], bbox: Tuple[float, float, float, float], diagonal: float) -> Optional[ShapeMatch]:
    """Look for a star's signature: several pronounced alternating
    near/far peaks in distance-from-centroid as you walk the path,
    rather than corner-counting (a star's RDP corner count is noisy
    and easy to confuse with an odd polygon)."""
    centroid = _centroid(points)

    # Resample onto a fixed angular grid (max radius seen per bin) so
    # unevenly-spaced hand-drawn points don't bias the peak search.
    bins = [0.0] * STAR_ANGLE_BINS
    for x, y in points:
        angle = math.atan2(y - centroid[1], x - centroid[0]) % (2 * math.pi)
        b = min(int(angle / (2 * math.pi) * STAR_ANGLE_BINS), STAR_ANGLE_BINS - 1)
        r = math.hypot(x - centroid[0], y - centroid[1])
        bins[b] = max(bins[b], r)

    filled_count = sum(1 for b in bins if b > 0)
    if filled_count < STAR_ANGLE_BINS * 0.6:
        return None  # too little of the sweep around the centroid was sampled at all

    # A handful of empty bins is normal -- hand-drawn points aren't
    # evenly spaced by angle, especially near a star's sharp inner
    # corners. Fill any gaps from the nearest sampled bin (walking
    # forward, wrapping around) rather than treating them as "radius
    # zero", which would otherwise look like a spurious deep valley.
    for i in range(STAR_ANGLE_BINS):
        if bins[i] <= 0:
            for offset in range(1, STAR_ANGLE_BINS):
                candidate = bins[(i + offset) % STAR_ANGLE_BINS]
                if candidate > 0:
                    bins[i] = candidate
                    break

    mean_radius = sum(bins) / len(bins)
    peaks = []
    for i in range(STAR_ANGLE_BINS):
        prev_b, next_b = bins[i - 1], bins[(i + 1) % STAR_ANGLE_BINS]
        if bins[i] >= prev_b and bins[i] >= next_b:
            prominence = bins[i] - (prev_b + next_b) / 2
            if prominence / mean_radius >= STAR_PROMINENCE_RATIO:
                peaks.append(i)
    # Collapse adjacent bins that both cleared the bar into one peak.
    collapsed = []
    for p in peaks:
        if collapsed and (p - collapsed[-1]) <= 1:
            continue
        collapsed.append(p)
    if collapsed and (STAR_ANGLE_BINS - collapsed[-1] + collapsed[0]) <= 1:
        collapsed.pop()  # first/last peak wrapped around and touch

    if not (STAR_MIN_PEAKS <= len(collapsed) <= STAR_MAX_PEAKS):
        return None

    arms = len(collapsed)
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    outer_r = max((x1 - x0) / 2, (y1 - y0) / 2, 1.0)
    inner_r = outer_r * 0.45
    star_points = []
    for i in range(arms * 2):
        angle = (math.pi / arms) * i - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        star_points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    star_points.append(star_points[0])
    return ShapeMatch(kind=ShapeKind.STAR, points=star_points, label=f"{arms}-point Star")


def try_snap_stroke(stroke: Stroke, min_points: int = MIN_POINTS) -> Optional[Stroke]:
    """If `stroke` matches a supported shape, return a new Stroke with
    the same style (color/size/opacity/brush_type) but idealized
    points. Returns None if nothing matched -- callers should keep
    the original stroke in that case."""
    match = classify_stroke(stroke.points, min_points=min_points)
    if match is None:
        return None
    return Stroke(
        points=match.points,
        color=stroke.color,
        size=stroke.size,
        opacity=stroke.opacity,
        brush_type=stroke.brush_type,
        created_at=stroke.created_at,
    )
