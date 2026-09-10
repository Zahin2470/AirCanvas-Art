import pytest
from PIL import Image

from aircanvas.persistence.share_card import build_share_card


def _make_sample_png(path, width=200, height=150, color=(200, 50, 50)):
    img = Image.new("RGB", (width, height), color)
    img.save(path)
    return path


def test_build_share_card_creates_output_file(tmp_path):
    canvas_png = _make_sample_png(tmp_path / "canvas.png")
    output = tmp_path / "share.png"
    result = build_share_card(canvas_png, output, title="My Art", stroke_count=5)
    assert result == output
    assert output.exists()


def test_share_card_is_larger_than_the_source_art_for_padding_and_text(tmp_path):
    canvas_png = _make_sample_png(tmp_path / "canvas.png", width=200, height=150)
    output = tmp_path / "share.png"
    build_share_card(canvas_png, output)
    card = Image.open(output)
    assert card.width > 200
    assert card.height > 150


def test_share_card_contains_the_source_art_pixels(tmp_path):
    canvas_png = _make_sample_png(tmp_path / "canvas.png", width=100, height=80, color=(10, 200, 10))
    output = tmp_path / "share.png"
    build_share_card(canvas_png, output)
    card = Image.open(output).convert("RGB")
    # The art is pasted at (CARD_PADDING, CARD_PADDING + HEADER_HEIGHT);
    # sample a pixel well inside that region.
    pixel = card.getpixel((60, 110))
    assert pixel == (10, 200, 10)


def test_wide_art_is_downscaled_to_max_width(tmp_path):
    canvas_png = _make_sample_png(tmp_path / "wide.png", width=2000, height=1000)
    output = tmp_path / "share.png"
    build_share_card(canvas_png, output)
    card = Image.open(output)
    # Card width = scaled art width + 2*padding; scaled art width should be <= ART_MAX_WIDTH.
    from aircanvas.persistence.share_card import ART_MAX_WIDTH, CARD_PADDING
    assert card.width <= ART_MAX_WIDTH + CARD_PADDING * 2


def test_missing_source_png_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_share_card(tmp_path / "nope.png", tmp_path / "out.png")


def test_output_parent_directories_are_created(tmp_path):
    canvas_png = _make_sample_png(tmp_path / "canvas.png")
    output = tmp_path / "nested" / "dir" / "share.png"
    build_share_card(canvas_png, output)
    assert output.exists()


def test_singular_stroke_label_for_count_one(tmp_path):
    # Not asserting on rendered pixels (font-dependent) -- just that
    # it doesn't crash with the singular/plural boundary value.
    canvas_png = _make_sample_png(tmp_path / "canvas.png")
    output = tmp_path / "share.png"
    build_share_card(canvas_png, output, stroke_count=1)
    assert output.exists()
