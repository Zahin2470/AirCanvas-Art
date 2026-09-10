"""
Share card: a polished preview image combining the artwork with a
title, stroke count, and creation date -- meant to be a shareable
"here's what I made" image, not just the raw canvas PNG.

Built with Pillow (already a project dependency for export-adjacent
work) rather than pygame, since Pillow's text layout doesn't depend
on a bundled font file to produce readable results on any platform --
falling back to its built-in default font when no system font is
found, per the project's rule against hard-coded personal paths.
"""
from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw, ImageFont

PathLike = Union[str, Path]

CARD_BACKGROUND = (16, 16, 20)
TEXT_COLOR = (230, 230, 235)
MUTED_COLOR = (150, 150, 158)
MARK_COLOR = (120, 190, 255)

CARD_PADDING = 40
ART_MAX_WIDTH = 900
HEADER_HEIGHT = 50
FOOTER_HEIGHT = 40


def _load_font(size: int) -> "ImageFont.ImageFont":
    """Try a couple of common system font names before falling back
    to Pillow's bundled default -- no hard-coded personal paths."""
    for name in ("Arial.ttf", "DejaVuSans.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_share_card(
    canvas_png_path: PathLike,
    output_path: PathLike,
    title: str = "Untitled",
    stroke_count: int = 0,
    created_at: Optional[float] = None,
) -> Path:
    """Compose a share card PNG from an already-exported canvas PNG.

    Raises:
        FileNotFoundError: if `canvas_png_path` doesn't exist.
    """
    canvas_png_path = Path(canvas_png_path)
    output_path = Path(output_path)
    if not canvas_png_path.exists():
        raise FileNotFoundError(f"Canvas PNG not found: {canvas_png_path}")

    art = Image.open(canvas_png_path).convert("RGB")
    if art.width > ART_MAX_WIDTH:
        scale = ART_MAX_WIDTH / art.width
        art = art.resize((ART_MAX_WIDTH, max(1, round(art.height * scale))), Image.LANCZOS)

    title_font = _load_font(28)
    meta_font = _load_font(16)
    mark_font = _load_font(14)

    card_width = art.width + CARD_PADDING * 2
    card_height = art.height + CARD_PADDING * 2 + HEADER_HEIGHT + FOOTER_HEIGHT

    card = Image.new("RGB", (card_width, card_height), CARD_BACKGROUND)
    draw = ImageDraw.Draw(card)

    draw.text((CARD_PADDING, CARD_PADDING - 6), title, font=title_font, fill=TEXT_COLOR)

    art_y = CARD_PADDING + HEADER_HEIGHT
    card.paste(art, (CARD_PADDING, art_y))

    timestamp = created_at if created_at is not None else time.time()
    date_str = datetime.datetime.fromtimestamp(timestamp).strftime("%b %d, %Y")
    footer_y = art_y + art.height + 14
    stroke_label = "stroke" if stroke_count == 1 else "strokes"
    draw.text((CARD_PADDING, footer_y), f"{stroke_count} {stroke_label}  \u2022  {date_str}", font=meta_font, fill=MUTED_COLOR)

    mark_text = "AirCanvas"
    mark_box = draw.textbbox((0, 0), mark_text, font=mark_font)
    mark_width = mark_box[2] - mark_box[0]
    draw.text((card_width - CARD_PADDING - mark_width, footer_y + 2), mark_text, font=mark_font, fill=MARK_COLOR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.save(output_path)
    return output_path
