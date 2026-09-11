"""Enables `python -m aircanvas` as an alternative to `python main.py`."""
import sys

from aircanvas.cli import main

if __name__ == "__main__":
    sys.exit(main())
