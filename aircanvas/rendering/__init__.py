"""
Rendering support beyond the canvas itself.

Phase 7 status: particles.py, effects.py (Living Ink, since Phase 5),
and themes.py (dark/light/neon/monochrome UI chrome) are implemented.
hud.py and typography.py aren't built as separate modules -- app.py
still owns the status bar and panel chrome directly, now driven by
the active Theme instead of hardcoded colors.
"""
