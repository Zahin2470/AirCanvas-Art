import pygame
import pytest

from aircanvas.canvas.brush_engine import BrushEngine
from aircanvas.canvas.brushes import BrushType
from aircanvas.canvas.stroke import Stroke

BACKGROUND = (10, 10, 12)
INK = (200, 50, 50)


@pytest.fixture
def surface():
    surf = pygame.Surface((300, 300))
    surf.fill(BACKGROUND)
    return surf


def _count_non_background_pixels(surface, rect):
    count = 0
    for x in range(rect[0], rect[0] + rect[2]):
        for y in range(rect[1], rect[1] + rect[3]):
            if surface.get_at((x, y))[:3] != BACKGROUND:
                count += 1
    return count


@pytest.mark.parametrize("brush_type", list(BrushType))
def test_every_brush_type_renders_without_crashing(surface, brush_type):
    engine = BrushEngine()
    stroke = Stroke(points=[(50, 50), (100, 100), (150, 60)], color=INK, size=16, brush_type=brush_type)
    engine.render_full(surface, [stroke], BACKGROUND)  # should not raise
    # Every brush should leave *some* visible mark somewhere near its path.
    assert _count_non_background_pixels(surface, (30, 30, 150, 90)) > 0


def test_neon_glow_bleeds_color_beyond_the_core_radius(surface):
    engine = BrushEngine()
    size = 16
    core_radius = size / 2
    pos = (150, 150)
    glow_stroke = Stroke(points=[pos], color=INK, size=size, brush_type=BrushType.NEON_GLOW)
    engine.render_full(surface, [glow_stroke], BACKGROUND)

    # A point clearly outside the core but inside the halo should be tinted.
    halo_point = (int(pos[0] + core_radius * 1.8), pos[1])
    assert surface.get_at(halo_point)[:3] != BACKGROUND


def test_smooth_ink_does_not_bleed_beyond_its_radius(surface):
    engine = BrushEngine()
    size = 16
    core_radius = size / 2
    pos = (150, 150)
    stroke = Stroke(points=[pos], color=INK, size=size, brush_type=BrushType.SMOOTH_INK)
    engine.render_full(surface, [stroke], BACKGROUND)

    outside_point = (int(pos[0] + core_radius * 1.8), pos[1])
    assert surface.get_at(outside_point)[:3] == BACKGROUND


def test_soft_marker_edge_is_a_partial_blend_not_solid_ink(surface):
    engine = BrushEngine()
    size = 40
    pos = (150, 150)
    stroke = Stroke(points=[pos], color=INK, size=size, opacity=1.0, brush_type=BrushType.SOFT_MARKER)
    engine.render_full(surface, [stroke], BACKGROUND)

    edge_point = (int(pos[0] + size / 2 * 0.9), pos[1])
    edge_color = surface.get_at(edge_point)[:3]
    assert edge_color != BACKGROUND
    assert edge_color != INK  # partially blended, not full-strength ink


def test_particle_brush_has_a_sparser_footprint_than_smooth_ink(surface):
    engine = BrushEngine()
    points = [(50, 150), (250, 150)]
    ink_stroke = Stroke(points=points, color=INK, size=20, brush_type=BrushType.SMOOTH_INK)
    particle_stroke = Stroke(points=points, color=INK, size=20, brush_type=BrushType.PARTICLE)

    ink_surface = pygame.Surface((300, 300))
    ink_surface.fill(BACKGROUND)
    engine.render_full(ink_surface, [ink_stroke], BACKGROUND)

    particle_surface = pygame.Surface((300, 300))
    particle_surface.fill(BACKGROUND)
    engine.render_full(particle_surface, [particle_stroke], BACKGROUND)

    region = (30, 130, 240, 40)
    ink_coverage = _count_non_background_pixels(ink_surface, region)
    particle_coverage = _count_non_background_pixels(particle_surface, region)
    assert particle_coverage < ink_coverage


def test_particle_brush_is_deterministic_across_renders():
    engine = BrushEngine()
    stroke = Stroke(points=[(50, 150), (250, 150)], color=INK, size=20, brush_type=BrushType.PARTICLE)

    surface_a = pygame.Surface((300, 300))
    surface_a.fill(BACKGROUND)
    engine.render_full(surface_a, [stroke], BACKGROUND)

    surface_b = pygame.Surface((300, 300))
    surface_b.fill(BACKGROUND)
    engine.render_full(surface_b, [stroke], BACKGROUND)

    assert pygame.image.tostring(surface_a, "RGB") == pygame.image.tostring(surface_b, "RGB")


def test_spark_brush_has_a_sparser_footprint_than_smooth_ink(surface):
    engine = BrushEngine()
    points = [(50, 150), (250, 150)]
    ink_stroke = Stroke(points=points, color=INK, size=14, brush_type=BrushType.SMOOTH_INK)
    spark_stroke = Stroke(points=points, color=INK, size=14, brush_type=BrushType.SPARK)

    ink_surface = pygame.Surface((300, 300))
    ink_surface.fill(BACKGROUND)
    engine.render_full(ink_surface, [ink_stroke], BACKGROUND)

    spark_surface = pygame.Surface((300, 300))
    spark_surface.fill(BACKGROUND)
    engine.render_full(spark_surface, [spark_stroke], BACKGROUND)

    region = (30, 130, 240, 40)
    ink_coverage = _count_non_background_pixels(ink_surface, region)
    spark_coverage = _count_non_background_pixels(spark_surface, region)
    assert spark_coverage < ink_coverage


def test_rainbow_flow_color_changes_along_a_long_stroke(surface):
    engine = BrushEngine()
    stroke = Stroke(points=[(0, 150), (299, 150)], color=INK, size=10, brush_type=BrushType.RAINBOW_FLOW)
    engine.render_full(surface, [stroke], BACKGROUND)

    start_color = surface.get_at((5, 150))[:3]
    end_color = surface.get_at((294, 150))[:3]
    assert start_color != end_color


def test_eraser_still_paints_solid_background_color(surface):
    engine = BrushEngine()
    ink = Stroke(points=[(150, 150)], color=INK, size=30, brush_type=BrushType.SMOOTH_INK)
    engine.render_full(surface, [ink], BACKGROUND)
    assert surface.get_at((150, 150))[:3] == INK

    eraser = Stroke(points=[(150, 150)], color=BACKGROUND, size=30, opacity=1.0, brush_type=BrushType.ERASER)
    engine.render_full(surface, [ink, eraser], BACKGROUND)
    assert surface.get_at((150, 150))[:3] == BACKGROUND


def test_sustained_drawing_increases_opacity_slightly():
    # Same point spacing in both strokes (so local stamp overlap is
    # identical) -- only the cumulative distance at the sampled point
    # differs, isolating glow accumulation from stamp-density effects.
    engine = BrushEngine()
    short_points = [(x, 150) for x in range(50, 60, 5)]  # ends at distance ~5
    long_points = [(x, 150) for x in range(50, 3050, 5)]  # ends at distance ~2995

    short_stroke = Stroke(points=short_points, color=INK, size=10, opacity=0.5, brush_type=BrushType.SMOOTH_INK)
    long_stroke = Stroke(points=long_points, color=INK, size=10, opacity=0.5, brush_type=BrushType.SMOOTH_INK)

    short_surface = pygame.Surface((3100, 300))
    short_surface.fill(BACKGROUND)
    engine.render_full(short_surface, [short_stroke], BACKGROUND)

    long_surface = pygame.Surface((3100, 300))
    long_surface.fill(BACKGROUND)
    engine.render_full(long_surface, [long_stroke], BACKGROUND)

    def blend_strength(pixel):
        # Rough proxy for opacity: how far the rendered pixel moved
        # from the background toward the ink color.
        return abs(pixel[0] - BACKGROUND[0])

    short_pixel = short_surface.get_at((55, 150))[:3]
    long_pixel = long_surface.get_at((3045, 150))[:3]
    assert blend_strength(long_pixel) > blend_strength(short_pixel)
