"""Turns per-frame gestures into stable, debounced application intent.

`state_machine.py` handles temporal debouncing/hysteresis over raw
per-frame gestures; `intent.py` wraps that together with pointer
smoothing and coordinate mapping into one FrameIntent the canvas and
rendering layers can consume.
"""
