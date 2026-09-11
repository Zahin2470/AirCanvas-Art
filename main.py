#!/usr/bin/env python3
"""
AirCanvas entry point (repo-root convenience script).

    python main.py [--camera N] [--debug] [--mouse] [--open PATH]

The actual argument parsing and app startup logic lives in
aircanvas/cli.py -- this file, aircanvas/__main__.py (for
`python -m aircanvas`), and the `aircanvas` console script installed
via pyproject.toml all call the same main() so behavior never drifts
between the three ways of launching the app.
"""
import sys

from aircanvas.cli import main

if __name__ == "__main__":
    sys.exit(main())
