"""
Canvas document model: strokes, brushes, undo/redo.

Deliberately holds no pixel data as the source of truth -- strokes
are ("keep stroke data independent from final pixel output"), so the
same model can back a live pygame surface today and saved-project /
replay reconstruction in a later phase without changes here.

Phase 3 status: model.py, stroke.py, brushes.py, brush_engine.py,
eraser.py, and history.py are implemented with one real brush
(Smooth Ink). replay.py (Phase 6) isn't built yet.
"""
