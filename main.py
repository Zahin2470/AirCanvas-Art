#!/usr/bin/env python3
"""
AirCanvas entry point.

Usage:
    python main.py                  # run with the default camera
    python main.py --camera 1       # use a specific camera index
    python main.py --debug          # verbose logging
    python main.py --mouse          # developer mode: mouse + keyboard, no camera
    python main.py --open art.aircanvas   # load a saved project at startup

In-app: S saves, E exports a PNG + share card, R toggles replay mode.
See README.md for the full control list.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from aircanvas import app
from aircanvas.config import APP_NAME, APP_VERSION, load_config
from aircanvas.utils.logging_setup import setup_logging


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aircanvas", description=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--camera", type=int, default=None, help="Camera index to use (default: 0)")
    parser.add_argument("--debug", action="store_true", help="Verbose logging and diagnostics")
    parser.add_argument(
        "--mouse", action="store_true",
        help="Developer mode: simulate the fingertip with the mouse (left=draw, right=erase, F=hold to clear). "
             "Testing only -- never required for normal use.",
    )
    parser.add_argument("--open", type=str, default=None, metavar="PATH", help="Load a saved .aircanvas project at startup")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    setup_logging(debug=args.debug)

    overrides = {"debug": args.debug}
    if args.camera is not None:
        overrides["camera_index"] = args.camera
    config = load_config(overrides)

    return app.run(config, mouse_mode=args.mouse, open_path=args.open)


if __name__ == "__main__":
    sys.exit(main())
