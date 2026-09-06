"""AirCanvas — a touchless painting studio.

This package is being built phase by phase per the project's
development plan (see README.md at the repo root for current status
and what's coming next). Phase 1 provides: configuration, the camera
layer, and the hand-landmark tracker, wired together behind a minimal
debug preview in `app.py`.
"""
from aircanvas.config import APP_NAME, APP_VERSION  # noqa: F401

__all__ = ["APP_NAME", "APP_VERSION"]
