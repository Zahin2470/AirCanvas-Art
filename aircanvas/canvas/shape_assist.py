"""
Shape assist: recognizes a few geometric primitives and aspect-ratio
templates -- live, while a stroke is still being drawn -- and offers
a clean replacement for it.

Scope, stated plainly (this matters more than usual here): this is
pure geometry, not object recognition. It can tell a closed
four-cornered shape from a five-pointed star, because those really
are different shapes. It cannot tell a book from a rectangle, because
a book drawn as a rectangle *is* a rectangle -- there is no shape-only
signal that distinguishes them. "Book" here means "a closed
four-cornered shape whose aspect ratio falls in a book-like band",
not "AirCanvas recognized a book". See BOOK_ASPECT_RATIO_RANGE below;
widen or narrow it to taste.

Two layers, kept separate on purpose:

  * `classify_stroke` is a pure, stateless function: given a point
    list, it returns the best-matching ShapeMatch (with a confidence
    score) or None. Same input always gives the same output -- no
    hidden state, no randomness, no notion of "while drawing" vs.
    "finished".
  * `LiveShapeAssistTracker` adds temporal stability on top: call
    `update()` once per new point while a stroke is being drawn, and
    it only reports a "confirmed" match once the same shape kind has
    classified confidently for several consecutive updates in a row.
    This is what keeps the live preview from flickering between
    guesses as an in-progress stroke's shape becomes clearer.

Used only when explicitly enabled (shape assist defaults to off, see
app.py's K key and persistence/settings.py). Only ever replaces the
stroke's *points*; color, size, opacity, and brush_type carry over
unchanged, so a shape drawn with Neon Glow snaps to a clean Neon Glow
shape, not a plain one. The result is a normal Stroke -- there is no
separate "shape object" -- so it undoes, redoes, saves, and replays
exactly like anything else drawn.
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
CORNER_EPSILON_MULTIPLIERS = (1.0, 1.6, 2.2)  # progressively more aggressive simplification passes
CORNER_ESCALATION_MAX_STARTING_CORNERS = 6    # a first pass rougher than this looks like a smooth curve, not a noisy polygon -- don't force it toward 4


def _polygon_vertex_significance(poly: List[Point], i: int) -> float:
    """How much vertex `i` actually bends the polygon: its distance
    from the straight line between its two neighbors. A low value
    means "this vertex barely changes the shape" -- a candidate for
    pruning as simplification noise rather than a real corner."""
    n = len(poly)
    return _point_line_distance(poly[i], poly[(i - 1) % n], poly[(i + 1) % n])


def _simplify_to_corners(points: List[Point], diagonal: float) -> Tuple[List[Point], int]:
    """Real hand-drawn noise occasionally makes RDP keep one spurious
    extra vertex on an otherwise-clean edge (a small bump that just
    clears the tolerance), pushing a true 4-corner rectangle to a
    5-corner simplification and knocking it out of the exact
    corner-count check below. Rather than accept a single epsilon's
    result no matter what, try a few increasingly aggressive passes
    and use the first one that lands on a plausible small corner
    count (3 or 4).

    If none do -- the spurious vertex was locally significant enough
    to survive even a much larger epsilon, which does happen -- fall
    back to directly pruning the single weakest remaining vertex
    (smallest contribution to the polygon's shape) one at a time,
    stopping the moment every remaining vertex looks like a real
    corner (clears the same tolerance the last epsilon pass used).
    That safety check is what stops this from forcing a genuinely
    5-or-6-sided freeform shape down into a rectangle it isn't.
    """
    first_result = None
    for multiplier in CORNER_EPSILON_MULTIPLIERS:
        epsilon = diagonal * CORNER_EPSILON_RATIO * multiplier
        simplified = _rdp(points, epsilon)
        simplified = _merge_close_points(simplified, diagonal * CORNER_MERGE_RATIO)
        corners = len(simplified) - 1 if len(simplified) > 1 and simplified[0] == simplified[-1] else len(simplified)
        if first_result is None:
            first_result = (simplified, corners)
            if corners > CORNER_ESCALATION_MAX_STARTING_CORNERS:
                return first_result  # looks like a smooth curve, not a noisy near-miss polygon -- leave it for the ellipse check instead
        if corners in (3, 4):
            return simplified, corners

    simplified, _corners = first_result
    poly = simplified[:-1] if len(simplified) > 1 and simplified[0] == simplified[-1] else list(simplified)
    weak_threshold = diagonal * CORNER_EPSILON_RATIO * CORNER_EPSILON_MULTIPLIERS[-1]
    while len(poly) > 4:
        significances = [_polygon_vertex_significance(poly, i) for i in range(len(poly))]
        weakest_index = min(range(len(poly)), key=lambda i: significances[i])
        if significances[weakest_index] > weak_threshold:
            break  # every remaining vertex looks like a real corner -- don't force it further
        poly.pop(weakest_index)

    return poly + [poly[0]], len(poly)

CIRCULARITY_MAX_CV = 0.22     # max coefficient of variation of centroid-distance for an "ellipse"

STAR_ANGLE_BINS = 36
STAR_MIN_PEAKS = 4
STAR_MAX_PEAKS = 7
STAR_PROMINENCE_RATIO = 0.22  # min (peak - adjacent valley) / mean radius to count as a real point of a star

BOOK_ASPECT_RATIO_RANGE = (1.15, 1.9)  # long side / short side -- see module docstring

ELLIPSE_RENDER_POINTS = 48

# Defaults for the live tracker -- also exposed as AppConfig fields
# (shape_assist_min_confidence, shape_assist_min_stable_updates) so
# they're tunable without editing this file.
DEFAULT_MIN_CONFIDENCE = 0.62
DEFAULT_MIN_STABLE_UPDATES = 8


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class ShapeMatch:
    kind: ShapeKind
    points: List[Point]     # the idealized replacement path
    label: str              # human-readable, for a status-bar toast
    confidence: float = 1.0  # 0..1, how confidently this stroke matches `kind`


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


def _closure_confidence(closure: float) -> float:
    return _clamp01(1.0 - closure / CLOSURE_RATIO)


# -- Classification -------------------------------------------------------

def classify_stroke(
    points: List[Point],
    min_points: int = MIN_POINTS,
) -> Optional[ShapeMatch]:
    """Try to recognize `points` as one of the supported shapes.
    Returns None (leave the stroke as freeform ink) when nothing
    matches at all -- this is the common case for real freeform
    drawing, by design. Callers that want to *act* on the result
    (auto-convert, show a preview) should additionally check
    `.confidence` against their own threshold -- a low-confidence
    match is still returned so a caller can decide for itself, rather
    than this function silently deciding what counts as "enough"."""
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
    return _classify_closed_path(points, (x0, y0, x1, y1), diagonal, closure)


def _classify_open_path(points: List[Point], diagonal: float) -> Optional[ShapeMatch]:
    start, end = points[0], points[-1]
    straight_length = _distance(start, end)
    if straight_length <= 0:
        return None
    max_deviation = max(_point_line_distance(p, start, end) for p in points)
    ratio = max_deviation / straight_length
    if ratio <= LINE_STRAIGHTNESS_RATIO:
        confidence = _clamp01(1.0 - ratio / LINE_STRAIGHTNESS_RATIO)
        return ShapeMatch(kind=ShapeKind.LINE, points=[start, end], label=DISPLAY_NAMES[ShapeKind.LINE], confidence=confidence)
    return None  # an open, non-straight path is just freeform ink


def _classify_closed_path(
    points: List[Point], bbox: Tuple[float, float, float, float], diagonal: float, closure: float
) -> Optional[ShapeMatch]:
    star = _try_star(points, bbox, closure)
    if star is not None:
        return star

    simplified, corners = _simplify_to_corners(points, diagonal)

    closure_conf = _closure_confidence(closure)

    if corners == 3:
        triangle = simplified[:3]
        confidence = _clamp01(0.5 + 0.5 * closure_conf)
        return ShapeMatch(kind=ShapeKind.TRIANGLE, points=triangle + [triangle[0]], label=DISPLAY_NAMES[ShapeKind.TRIANGLE], confidence=confidence)

    if corners == 4:
        return _rectangle_or_book(bbox, closure_conf)

    return _try_ellipse(points, bbox, closure_conf)


def _rectangle_or_book(bbox: Tuple[float, float, float, float], closure_conf: float) -> ShapeMatch:
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    long_side, short_side = max(width, height), max(min(width, height), 1e-6)
    aspect_ratio = long_side / short_side

    outline = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    band_low, band_high = BOOK_ASPECT_RATIO_RANGE
    if band_low <= aspect_ratio <= band_high:
        band_center = (band_low + band_high) / 2
        band_half_width = (band_high - band_low) / 2
        aspect_conf = _clamp01(1.0 - abs(aspect_ratio - band_center) / band_half_width)
        confidence = _clamp01(0.4 * closure_conf + 0.3 + 0.3 * aspect_conf)
        mid_top = ((x0 + x1) / 2, y0)
        mid_bottom = ((x0 + x1) / 2, y1)
        # Trace the outline, then the spine down and back up -- still
        # one continuous path, so it's still one Stroke.
        book_path = outline + [mid_top, mid_bottom, mid_top]
        return ShapeMatch(kind=ShapeKind.BOOK, points=book_path, label=DISPLAY_NAMES[ShapeKind.BOOK], confidence=confidence)

    confidence = _clamp01(0.5 + 0.5 * closure_conf)
    return ShapeMatch(kind=ShapeKind.RECTANGLE, points=outline, label=DISPLAY_NAMES[ShapeKind.RECTANGLE], confidence=confidence)


def _try_ellipse(points: List[Point], bbox: Tuple[float, float, float, float], closure_conf: float) -> Optional[ShapeMatch]:
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

    fit_conf = _clamp01(1.0 - coefficient_of_variation / CIRCULARITY_MAX_CV)
    confidence = _clamp01(0.6 * fit_conf + 0.4 * closure_conf)

    ellipse = [
        (cx + rx * math.cos(2 * math.pi * i / ELLIPSE_RENDER_POINTS), cy + ry * math.sin(2 * math.pi * i / ELLIPSE_RENDER_POINTS))
        for i in range(ELLIPSE_RENDER_POINTS + 1)
    ]
    return ShapeMatch(kind=ShapeKind.ELLIPSE, points=ellipse, label=DISPLAY_NAMES[ShapeKind.ELLIPSE], confidence=confidence)


def _try_star(points: List[Point], bbox: Tuple[float, float, float, float], closure: float) -> Optional[ShapeMatch]:
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
    prominences = []
    for i in range(STAR_ANGLE_BINS):
        prev_b, next_b = bins[i - 1], bins[(i + 1) % STAR_ANGLE_BINS]
        if bins[i] >= prev_b and bins[i] >= next_b:
            prominence = bins[i] - (prev_b + next_b) / 2
            ratio = prominence / mean_radius
            if ratio >= STAR_PROMINENCE_RATIO:
                peaks.append(i)
                prominences.append(ratio)
    # Collapse adjacent bins that both cleared the bar into one peak.
    collapsed, collapsed_prominences = [], []
    for p, prom in zip(peaks, prominences):
        if collapsed and (p - collapsed[-1]) <= 1:
            continue
        collapsed.append(p)
        collapsed_prominences.append(prom)
    if collapsed and (STAR_ANGLE_BINS - collapsed[-1] + collapsed[0]) <= 1:
        collapsed.pop()  # first/last peak wrapped around and touch
        collapsed_prominences.pop()

    if not (STAR_MIN_PEAKS <= len(collapsed) <= STAR_MAX_PEAKS):
        return None

    arms = len(collapsed)
    avg_prominence_ratio = sum(collapsed_prominences) / len(collapsed_prominences)
    prominence_conf = _clamp01(avg_prominence_ratio / (STAR_PROMINENCE_RATIO * 2))
    arms_conf = 1.0 if arms == 5 else 0.85 if arms in (4, 6) else 0.7
    closure_conf = _closure_confidence(closure)
    confidence = _clamp01(0.45 * prominence_conf + 0.35 * arms_conf + 0.2 * closure_conf)

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
    return ShapeMatch(kind=ShapeKind.STAR, points=star_points, label=f"{arms}-point Star", confidence=confidence)


def try_snap_stroke(stroke: Stroke, min_points: int = MIN_POINTS, min_confidence: float = 0.0) -> Optional[Stroke]:
    """If `stroke` matches a supported shape at >= `min_confidence`,
    return a new Stroke with the same style (color/size/opacity/
    brush_type) but idealized points. Returns None if nothing matched
    confidently enough -- callers should keep the original stroke in
    that case."""
    match = classify_stroke(stroke.points, min_points=min_points)
    if match is None or match.confidence < min_confidence:
        return None
    return Stroke(
        points=match.points,
        color=stroke.color,
        size=stroke.size,
        opacity=stroke.opacity,
        brush_type=stroke.brush_type,
        created_at=stroke.created_at,
    )


class LiveShapeAssistTracker:
    """Adds temporal stability to `classify_stroke` for use while a
    stroke is still being drawn: call `update()` once per new point,
    and it only reports a match once the same ShapeKind has cleared
    `min_confidence` for `min_stable_updates` consecutive calls in a
    row. This is what stops the live preview from flickering between
    guesses while an in-progress stroke's shape is still ambiguous.

    Stateful and mutable by design (unlike `classify_stroke`) -- create
    one per in-progress stroke and call `reset()` when a new one
    begins (or the previous one ends), so stability from an unrelated
    earlier stroke never carries over.
    """

    def __init__(self, min_confidence: float = DEFAULT_MIN_CONFIDENCE, min_stable_updates: int = DEFAULT_MIN_STABLE_UPDATES, min_points: int = MIN_POINTS) -> None:
        self.min_confidence = min_confidence
        self.min_stable_updates = max(1, min_stable_updates)
        self.min_points = min_points
        self._last_kind: Optional[ShapeKind] = None
        self._stable_count = 0
        self._confirmed: Optional[ShapeMatch] = None

    def reset(self) -> None:
        self._last_kind = None
        self._stable_count = 0
        self._confirmed = None

    @property
    def confirmed(self) -> Optional[ShapeMatch]:
        return self._confirmed

    def update(self, points: List[Point]) -> Optional[ShapeMatch]:
        """Feed the in-progress stroke's current point list. Returns
        the currently-confirmed ShapeMatch, or None if nothing has
        been stable and confident for long enough yet."""
        match = classify_stroke(points, min_points=self.min_points)

        if match is None or match.confidence < self.min_confidence:
            self._last_kind = None
            self._stable_count = 0
            self._confirmed = None
            return None

        if match.kind == self._last_kind:
            self._stable_count += 1
        else:
            self._last_kind = match.kind
            self._stable_count = 1

        if self._stable_count >= self.min_stable_updates:
            self._confirmed = match
        else:
            self._confirmed = None
        return self._confirmed
