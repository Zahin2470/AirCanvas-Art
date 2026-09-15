import math
import random

import pytest

from aircanvas.canvas.shape_assist import ShapeKind, classify_stroke, try_snap_stroke
from aircanvas.canvas.stroke import Stroke

RNG = random.Random(42)


def _jitter(points, amount, rng=RNG):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in points]


def _sample_polygon(corners, points_per_edge=8):
    """Sample points walking around a closed polygon's edges, ending
    back near (not exactly at) the start -- like a real hand-drawn
    closed shape."""
    path = []
    ring = corners + [corners[0]]
    for a, b in zip(ring, ring[1:]):
        for i in range(points_per_edge):
            t = i / points_per_edge
            path.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    path.append(ring[-1])
    return path


def _sample_ellipse(cx, cy, rx, ry, n=40):
    return [
        (cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
        for i in range(n + 1)
    ]


def _sample_star(cx, cy, outer_r, inner_r, arms=5, points_per_edge=6):
    corners = []
    for i in range(arms * 2):
        angle = (math.pi / arms) * i - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        corners.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return _sample_polygon(corners, points_per_edge=points_per_edge)


def _sample_line(x0, y0, x1, y1, n=20):
    return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]


# -- Line -----------------------------------------------------------------

def test_straight_line_is_recognized():
    points = _jitter(_sample_line(0, 0, 200, 40), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.LINE
    assert match.points[0] == pytest.approx((0, 0), abs=3)
    assert match.points[-1] == pytest.approx((200, 40), abs=3)


def test_wobbly_open_path_is_not_a_line():
    # A meandering path whose endpoints happen to be far apart but
    # which strays far from the straight line between them.
    points = [(x, 40 * math.sin(x / 15)) for x in range(0, 200, 4)]
    match = classify_stroke(points)
    assert match is None


# -- Rectangle / book -------------------------------------------------------

def test_rectangle_with_square_ish_aspect_is_recognized_as_rectangle():
    corners = [(0, 0), (100, 0), (100, 90), (0, 90)]  # aspect ~1.1 -> below book band
    points = _jitter(_sample_polygon(corners), amount=2.0)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.RECTANGLE
    assert match.points[0] == match.points[-1]  # closed outline


def test_book_aspect_rectangle_is_recognized_as_book():
    corners = [(0, 0), (100, 0), (100, 160), (0, 160)]  # aspect 1.6 -> within book band
    points = _jitter(_sample_polygon(corners), amount=2.0)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.BOOK
    # Book path should include a spine line through the horizontal midpoint.
    xs = [p[0] for p in match.points]
    assert any(abs(x - 50) < 3.0 for x in xs)


def test_very_elongated_rectangle_is_plain_rectangle_not_book():
    corners = [(0, 0), (300, 0), (300, 40), (0, 40)]  # aspect 7.5 -> outside book band
    points = _jitter(_sample_polygon(corners), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.RECTANGLE


# -- Triangle --------------------------------------------------------------

def test_triangle_is_recognized():
    corners = [(0, 100), (50, 0), (100, 100)]
    points = _jitter(_sample_polygon(corners), amount=2.0)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.TRIANGLE
    assert len(match.points) == 4  # 3 corners + closing point


# -- Ellipse / circle --------------------------------------------------------

def test_circle_is_recognized_as_ellipse():
    points = _jitter(_sample_ellipse(50, 50, 40, 40), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.ELLIPSE


def test_wide_ellipse_is_recognized():
    points = _jitter(_sample_ellipse(80, 40, 70, 30), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.ELLIPSE


def test_rectangle_with_a_noise_induced_spurious_vertex_still_classifies_correctly():
    # Regression test: a real noisy hand-drawn rectangle sometimes
    # simplifies to 5 corners instead of 4 (one small bump on an edge
    # survives RDP as a spurious extra vertex). This used to fall
    # through to the ellipse check and get misclassified as an
    # Ellipse; _simplify_to_corners's escalation/pruning fallback
    # should now recover the correct Book/Rectangle classification.
    rng = random.Random(21)
    origin = (250, 250)
    corners = [(0, 0), (180, 0), (180, 130), (0, 130), (0, 0)]
    points = []
    for a, b in zip(corners, corners[1:]):
        for i in range(14):
            t = i / 14
            x = origin[0] + a[0] + (b[0] - a[0]) * t + rng.uniform(-2, 2)
            y = origin[1] + a[1] + (b[1] - a[1]) * t + rng.uniform(-2, 2)
            points.append((x, y))
    match = classify_stroke(points)
    assert match is not None
    assert match.kind in (ShapeKind.RECTANGLE, ShapeKind.BOOK)


def test_ellipse_with_high_initial_corner_count_is_not_forced_into_a_polygon():
    # A smooth curve's first-pass simplification has many corners by
    # nature (it's approximating a curve, not converging on a true
    # small corner count) -- the escalation/pruning fallback must not
    # force this down to a rectangle just because it eventually could.
    points = _jitter(_sample_ellipse(80, 40, 70, 30), amount=1.5, rng=random.Random(42))
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.ELLIPSE
    assert match.confidence > 0.7


# -- Star -------------------------------------------------------------------

def test_five_pointed_star_is_recognized():
    points = _jitter(_sample_star(60, 60, outer_r=50, inner_r=20), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.STAR
    assert "5" in match.label


def test_six_pointed_star_is_recognized():
    points = _jitter(_sample_star(60, 60, outer_r=50, inner_r=22, arms=6), amount=1.5)
    match = classify_stroke(points)
    assert match is not None
    assert match.kind == ShapeKind.STAR


# -- Rejections (freeform ink should stay freeform) ------------------------

def test_too_few_points_is_not_classified():
    match = classify_stroke([(0, 0), (10, 10), (20, 5)])
    assert match is None


def test_tiny_scribble_below_size_threshold_is_not_classified():
    points = _jitter(_sample_polygon([(0, 0), (5, 0), (5, 5), (0, 5)]), amount=0.5)
    match = classify_stroke(points)
    assert match is None


def test_irregular_freeform_scribble_is_not_classified():
    rng = random.Random(7)
    points = [(rng.uniform(0, 200), rng.uniform(0, 200)) for _ in range(30)]
    match = classify_stroke(points)
    assert match is None


def test_open_squiggle_is_not_classified():
    points = [(x, 30 * math.sin(x / 10) + 5 * math.sin(x / 3)) for x in range(0, 150, 3)]
    match = classify_stroke(points)
    assert match is None


# -- try_snap_stroke wrapper -------------------------------------------------

def test_try_snap_stroke_preserves_style_fields():
    from aircanvas.canvas.brushes import BrushType

    corners = [(0, 0), (100, 0), (100, 90), (0, 90)]
    points = _jitter(_sample_polygon(corners), amount=2.0)
    stroke = Stroke(points=points, color=(10, 20, 30), size=17.0, opacity=0.8, brush_type=BrushType.NEON_GLOW)

    snapped = try_snap_stroke(stroke)
    assert snapped is not None
    assert snapped.color == (10, 20, 30)
    assert snapped.size == 17.0
    assert snapped.opacity == 0.8
    assert snapped.brush_type == BrushType.NEON_GLOW
    assert snapped.points != stroke.points  # geometry was actually replaced


def test_try_snap_stroke_returns_none_for_unrecognized_shape():
    rng = random.Random(3)
    points = [(rng.uniform(0, 200), rng.uniform(0, 200)) for _ in range(30)]
    stroke = Stroke(points=points)
    assert try_snap_stroke(stroke) is None


def test_classify_is_deterministic():
    corners = [(0, 0), (100, 0), (100, 90), (0, 90)]
    points = _jitter(_sample_polygon(corners), amount=2.0, rng=random.Random(99))
    first = classify_stroke(points)
    second = classify_stroke(points)
    assert first == second


# -- Confidence scoring -------------------------------------------------

def test_confidence_is_in_valid_range_for_every_shape_kind():
    cases = [
        _jitter(_sample_line(0, 0, 200, 40), amount=1.5),
        _jitter(_sample_polygon([(0, 0), (100, 0), (100, 90), (0, 90)]), amount=2.0),
        _jitter(_sample_polygon([(0, 100), (50, 0), (100, 100)]), amount=2.0),
        _jitter(_sample_ellipse(50, 50, 40, 40), amount=1.5),
        _jitter(_sample_star(60, 60, outer_r=50, inner_r=20), amount=1.5),
    ]
    for points in cases:
        match = classify_stroke(points)
        assert match is not None
        assert 0.0 <= match.confidence <= 1.0


def test_cleaner_rectangle_has_higher_confidence_than_noisier_one():
    corners = [(0, 0), (150, 0), (150, 100), (0, 100)]
    clean = classify_stroke(_jitter(_sample_polygon(corners), amount=0.5, rng=random.Random(1)))
    noisy = classify_stroke(_jitter(_sample_polygon(corners), amount=12.0, rng=random.Random(1)))
    assert clean is not None
    # The noisy version may still classify as a rectangle or may not
    # match at all; either way, if it does match, it should be less
    # confident than the clean version.
    if noisy is not None and noisy.kind == clean.kind:
        assert noisy.confidence < clean.confidence


def test_cleaner_circle_has_higher_confidence_than_slightly_egg_shaped_one():
    clean = classify_stroke(_jitter(_sample_ellipse(50, 50, 40, 40), amount=0.5, rng=random.Random(2)))
    # Not a true ellipse -- one side bulges more than the other.
    lumpy = [
        (50 + (40 + (6 if math.cos(2 * math.pi * i / 40) > 0.3 else 0)) * math.cos(2 * math.pi * i / 40),
         50 + 40 * math.sin(2 * math.pi * i / 40))
        for i in range(41)
    ]
    lumpy_match = classify_stroke(_jitter(lumpy, amount=0.5, rng=random.Random(2)))
    assert clean is not None
    if lumpy_match is not None and lumpy_match.kind == ShapeKind.ELLIPSE:
        assert lumpy_match.confidence < clean.confidence


def test_try_snap_stroke_respects_min_confidence_threshold():
    corners = [(0, 0), (150, 0), (150, 100), (0, 100)]
    points = _jitter(_sample_polygon(corners), amount=0.5, rng=random.Random(1))
    stroke = Stroke(points=points)
    assert try_snap_stroke(stroke, min_confidence=0.0) is not None
    assert try_snap_stroke(stroke, min_confidence=1.1) is None  # impossible threshold -> never snaps


# -- LiveShapeAssistTracker -----------------------------------------------

def test_tracker_confirms_nothing_before_min_stable_updates():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.0, min_stable_updates=5)
    corners = [(0, 0), (100, 0), (100, 90), (0, 90)]
    points = _jitter(_sample_polygon(corners), amount=1.0, rng=random.Random(3))
    for _ in range(4):
        result = tracker.update(points)
    assert result is None  # only 4 updates so far, need 5


def test_tracker_confirms_after_min_stable_updates_of_the_same_kind():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.0, min_stable_updates=5)
    corners = [(0, 0), (100, 0), (100, 90), (0, 90)]
    points = _jitter(_sample_polygon(corners), amount=1.0, rng=random.Random(3))
    result = None
    for _ in range(5):
        result = tracker.update(points)
    assert result is not None
    assert result.kind == ShapeKind.RECTANGLE


def test_tracker_resets_stability_when_the_kind_changes():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.0, min_stable_updates=3)
    rect_points = _jitter(_sample_polygon([(0, 0), (100, 0), (100, 90), (0, 90)]), amount=1.0, rng=random.Random(4))
    triangle_points = _jitter(_sample_polygon([(0, 100), (50, 0), (100, 100)]), amount=1.0, rng=random.Random(4))

    tracker.update(rect_points)
    tracker.update(rect_points)
    switched = tracker.update(triangle_points)  # kind changes -> stability resets
    assert switched is None


def test_tracker_reports_none_when_confidence_drops_below_threshold():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.95, min_stable_updates=2)
    rng = random.Random(9)
    scribble = [(rng.uniform(0, 200), rng.uniform(0, 200)) for _ in range(30)]
    result = tracker.update(scribble)
    assert result is None


def test_tracker_reset_clears_accumulated_stability():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.0, min_stable_updates=3)
    points = _jitter(_sample_polygon([(0, 0), (100, 0), (100, 90), (0, 90)]), amount=1.0, rng=random.Random(5))
    tracker.update(points)
    tracker.update(points)
    tracker.reset()
    result = tracker.update(points)  # only 1 update since reset
    assert result is None
    assert tracker.confirmed is None


def test_tracker_confirmed_property_matches_last_update_result():
    from aircanvas.canvas.shape_assist import LiveShapeAssistTracker

    tracker = LiveShapeAssistTracker(min_confidence=0.0, min_stable_updates=2)
    points = _jitter(_sample_polygon([(0, 0), (100, 0), (100, 90), (0, 90)]), amount=1.0, rng=random.Random(6))
    tracker.update(points)
    result = tracker.update(points)
    assert tracker.confirmed == result
    assert tracker.confirmed is not None
