"""Logging setup shared across the app."""
from __future__ import annotations

import logging


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure root logging once and return the app's named logger.

    Safe to call more than once (e.g. from tests) — `force=True`
    lets each call replace any handlers a previous call installed.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logger = logging.getLogger("aircanvas")
    logger.setLevel(level)
    return logger
