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
