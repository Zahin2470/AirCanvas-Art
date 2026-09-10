# AirCanvas — Paint Without Touching Anything

A touchless painting studio: move your index fingertip through the air in
front of your webcam and paint onto a virtual canvas.

**Status: Phase 6 of 8** — save/load projects, PNG export with a shareable
preview card, artwork replay, and crash recovery, on top of Phase 5's
brushes and Living Ink.

## What's here right now

- `main.py` — CLI entry point (now with `--open PATH`)
- `aircanvas/config.py` — runtime configuration, plus app-data paths for
  projects, exports, and crash recovery
- `aircanvas/vision/` — camera, MediaPipe tracker, features, gestures,
  smoothing, calibration (unchanged since Phase 2)
- `aircanvas/interaction/` — intent state machine, `FrameIntent` resolver,
  developer mouse/keyboard input source (unchanged since Phase 3)
- `aircanvas/canvas/stroke.py` — now also records `point_times` (seconds
  since the stroke began) alongside each point, for replay pacing
- `aircanvas/canvas/brush_engine.py` — unchanged rendering, plus a public
  `render_stroke()` used by both `render_full()` and replay
- `aircanvas/canvas/model.py`, `history.py`, `eraser.py`, `brushes.py` —
  unchanged since Phase 3/5
- `aircanvas/canvas/replay.py` — `ReplayController`: reconstructs the
  drawing stroke-by-stroke and point-by-point, with play/pause/seek/speed
- `aircanvas/persistence/project_io.py` — JSON `.aircanvas` save/load
  (never pickle) with atomic writes and clear error messages, plus PNG export
- `aircanvas/persistence/share_card.py` — composites the artwork with a
  title, stroke count, and date into a shareable preview image
- `aircanvas/rendering/particles.py`, `effects.py` — Living Ink (unchanged
  since Phase 5)
- `aircanvas/ui/toolbar.py` — the touchless toolbar (unchanged since Phase 4)
- `aircanvas/app.py` — the pygame app: toolbar, camera preview, canvas,
  replay overlay, status bar, save/export/recovery wiring
- `aircanvas/{rendering/renderer.py,rendering/hud.py,rendering/themes.py,audio,persistence/settings.py}` —
  empty scaffolding for later phases (see Roadmap below)
- `aircanvas/tests/` — 221 unit tests, all hardware/network-free

## A note on MediaPipe versions

This project targets current MediaPipe (0.10.x), which replaced the older
`mp.solutions.hands.Hands` API with the Tasks API
(`mediapipe.tasks.python.vision.HandLandmarker`). One practical
consequence: the hand-landmark model is no longer bundled inside the pip
package — it's a `.task` file that `aircanvas/vision/tracker.py` downloads
once from Google's hosted model and caches under `~/.aircanvas/models/`.
**Your first run needs an internet connection** to fetch that file; every
run after that works offline.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python main.py                 # default camera (index 0)
python main.py --camera 1      # use a different camera index
python main.py --debug         # verbose logging
```

A window opens with three panels: **tools** (color swatches, brush styles
and sizes, undo/redo) on the left, your **webcam feed** in the middle, and
the **art canvas** on the right.

**Brush styles** (see `aircanvas/canvas/brush_engine.py`) — pick one from
the toolbar's brush-type buttons:

| Brush | Look |
|---|---|
| Ink | Smooth Ink — a clean, solid stroke |
| Glow | Neon Glow — a bright core with a soft halo bleeding outward |
| Marker | Soft Marker — wide, translucent, soft-edged |
| Particle | Particle — a scattered, granular cluster instead of a solid line |
| Rainbow | Rainbow Flow — hue cycles smoothly along the stroke's length |
| Spark | Spark — sparse, jittered, high-contrast flecks |

Every brush's look is a deterministic function of the stroke's own stored
points, size, and color — the same stroke always redraws pixel-identically
on undo/redo, which matters once replay arrives in Phase 6.

**Living Ink:** AirCanvas's signature effect. As you draw, faint motes
trail off the stroke (more of them the faster you move), a small burst
fires on a sharp direction change, and a stroke gently "settles" with a
soft burst when it starts and ends. The cursor also leaves a light trail
while just pointing. This is a purely decorative overlay — it never
touches the saved stroke data, so it has no bearing on undo/redo. Toggle
it anytime with **P** if you want a calmer or faster canvas.

**Drawing gestures** (see `aircanvas/vision/gestures.py`):
| Gesture | Pose | Effect |
|---|---|---|
| Pointing | index finger only | move the cursor (no drawing) |
| Pinch | thumb + index together | draw (on canvas) or select (on toolbar) |
| Two-finger | index + middle | erase (same size as the current brush) |
| Open palm | most/all fingers extended | **pause** — cursor moves, nothing else happens |
| Fist | no fingers extended | hold ~2/3 of a second to clear the canvas |

**Using the toolbar:** point at a color, brush style, size, or Undo/Redo,
then hold a pinch over it for about a third of a second (the button fills
up as you hold). Pinching over the canvas draws; pinching over the toolbar
selects.

**Keyboard fallbacks** (not required for normal use):
- **Q** / **Esc** — quit
- **Z** — undo · **X** — redo
- **[** / **]** — smaller / larger brush
- **Tab** — cycle the color palette · **B** — cycle brush style
- **P** — toggle Living Ink particles on/off
- **1** — capture the top-left calibration corner · **2** — bottom-right · **C** — reset calibration

If the camera fails to open, AirCanvas prints a clear message and
**automatically falls back to developer mouse mode** rather than crashing.

### Developer mode (no camera needed)

```bash
python main.py --mouse
```

Tests the entire app — drawing with every brush style, erasing, the
touchless toolbar, Living Ink, undo/redo, clearing — with just a mouse
and keyboard:

- **Left mouse button held** — draw, or select whatever toolbar widget it's held over
- **Right mouse button held** — erase
- **F key held** — hold to clear (same confirmation delay as a fist)

This reuses the exact same `IntentStateMachine`, toolbar, and canvas code a
real hand does — it's a stand-in for the *input*, not a separate code
path. Per the project spec, this is for testing only and is never
required for normal use.

### Save, export, and replay

- **S** — save the current canvas as a `.aircanvas` project (JSON, never
  pickle) to `~/.aircanvas/projects/aircanvas_<timestamp>.aircanvas`
- **E** — export a PNG and a composited share card (artwork + title +
  stroke count + date) to `~/.aircanvas/exports/`
- **R** — toggle Replay mode, which reconstructs the drawing stroke-by-
  stroke (and point-by-point, where timing was recorded) on a separate
  surface — exiting replay resumes editing exactly where you left off,
  untouched. While replaying: **Space** play/pause, **←/→** seek, **↑/↓**
  speed, **Home** restart

```bash
python main.py --open path/to/artwork.aircanvas   # load a saved project at startup
```

**Crash recovery:** AirCanvas autosaves a recovery copy every ~15 seconds
while you work. If the app exits cleanly (Q/Esc/window close), that
recovery file is deleted. If it doesn't — a crash, a force-quit — the
recovery file is still there, and AirCanvas reloads it automatically the
next time you launch, printing how many strokes it recovered.

**Known limitation:** loading a project saved at a different canvas size
than the app's current window keeps the strokes' raw coordinates as-is
rather than remapping them proportionally, so strokes may appear
cropped or offset if the two sizes differ significantly. Fine for the
common case (nothing currently changes the canvas size), worth revisiting
if canvas resizing is ever added.

The fingertip cursor spans the *whole window*, not just the canvas —
that's what lets it reach the toolbar. Every frame, AirCanvas checks where
the cursor is before deciding what a pinch means: over the toolbar, it
selects; over the canvas, it draws; over the middle (webcam) panel or
during an open-palm pause, it does nothing. One known rough edge: if you
drag an in-progress stroke across the toolbar, the stroke pauses (rather
than ending) while you're over the toolbar and could, if you linger,
trigger a button underneath it — this is worth smoothing out in a later
polish pass, but doesn't affect normal use.

## Running tests

```bash
pip install pytest
pytest aircanvas/tests -v
```

Tests are hardware-free: the camera tests mock `cv2.VideoCapture`, the
tracker tests exercise data structures and model-caching logic without
loading a real model, the feature/gesture/smoothing/calibration/state-
machine/intent/dev-input/toolbar/replay tests run against synthetic data
(`aircanvas/tests/helpers.py`), the particle/Living Ink tests use a seeded
`random.Random` for reproducibility, the canvas + brush-style tests
(`stroke`, `history`, `model`, `eraser`, `brush_engine`, `brush_styles`)
run against a real but headless pygame `Surface`, and the project-save and
share-card tests round-trip through real temp files on disk (`tmp_path`).

## Roadmap

| Phase | Focus |
|---|---|
| 1 ✅ | Skeleton, config, camera, tracker, tests |
| 2 ✅ | Pointer mapping, smoothing, gesture state machine, calibration |
| 3 ✅ | Canvas model, stroke representation, basic brush, undo/redo |
| 4 ✅ | Touchless tool/color/size controls |
| 5 ✅ | Advanced brushes, particles, Living Ink, animation polish |
| 6 ✅ | Project save/load, PNG export, replay, share card |
| 3 | Canvas model, stroke representation, basic brush, undo/redo |
| 4 | Touchless tool/color/size controls |
| 5 | Advanced brushes, particles, Living Ink, animation polish |
| 6 | Project save/load, PNG export, replay, share card |
| 7 | Themes, sound, accessibility, performance tuning |
| 8 | Testing, packaging, documentation, demo-ready UX |

The project stays runnable after every phase.
