# AirCanvas — Paint Without Touching Anything

A touchless painting studio: move your index fingertip through the air in
front of your webcam and paint onto a virtual canvas.

**Status: Phase 3 of 8** — a real pygame drawing canvas, stroke-based
brush engine, eraser, and stroke-level undo/redo, on top of Phases 1-2's
tracking and interaction pipeline. The temporary OpenCV debug window is
gone — this is a real (if not yet visually polished) paint app: raise
your hand, pinch to draw, two-finger to erase, hold a fist to clear.

## What's here right now

- `main.py` — CLI entry point
- `aircanvas/config.py` — runtime configuration (camera, tracking, smoothing,
  mapping, gesture/state-machine, brush/palette settings)
- `aircanvas/vision/` — camera, MediaPipe tracker, features, gestures,
  smoothing, calibration (unchanged since Phase 2)
- `aircanvas/interaction/state_machine.py` — debounced intent state machine
- `aircanvas/interaction/intent.py` — per-frame `FrameIntent`, now also
  tracking erase start/end alongside stroke start/end
- `aircanvas/interaction/dev_input.py` — developer mouse/keyboard input
  source (see Developer Mode below)
- `aircanvas/canvas/stroke.py` — the `Stroke` data model
- `aircanvas/canvas/brushes.py` — brush type catalog (one real brush so far)
- `aircanvas/canvas/brush_engine.py` — stamps strokes onto a pygame surface,
  incrementally while drawing and fully on undo/redo/clear
- `aircanvas/canvas/eraser.py` — eraser stroke factory + stamp geometry helper
- `aircanvas/canvas/history.py` — generic undo/redo action stack
- `aircanvas/canvas/model.py` — the canvas document (strokes + undo/redo)
- `aircanvas/app.py` — the real pygame app: canvas panel, camera preview
  panel, status bar, and the main loop wiring everything together
- `aircanvas/{rendering,audio,persistence,ui}/` — empty scaffolding for
  later phases (see Roadmap below)
- `aircanvas/tests/` — 127 unit tests, all hardware/network-free

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

A window opens with two panels: your webcam feed (with hand skeleton and
intent overlay) on the left, and the actual art canvas on the right. Raise
your hand and start painting.

**Gestures** (see `aircanvas/vision/gestures.py`):
| Gesture | Pose | Effect |
|---|---|---|
| Pointing | index finger only | move the cursor (no drawing) |
| Pinch | thumb + index together | draw with the current color/size |
| Two-finger | index + middle | erase (same size as the current brush) |
| Open palm | most/all fingers extended | pause / UI mode |
| Fist | no fingers extended | hold ~2/3 of a second to clear the canvas |

**Keyboard controls** (temporary dev tools — Phase 4 replaces the
brush/color/calibration ones with touchless equivalents):
- **Q** / **Esc** — quit
- **Z** — undo · **X** — redo
- **[** / **]** — smaller / larger brush (5 presets)
- **Tab** — cycle the color palette
- **1** — capture the top-left calibration corner · **2** — bottom-right · **C** — reset calibration

If the camera fails to open, AirCanvas prints a clear message and
**automatically falls back to developer mouse mode** rather than crashing.

### Developer mode (no camera needed)

```bash
python main.py --mouse
```

Lets you test the entire app — drawing, erasing, undo/redo, clearing —
with just a mouse and keyboard, no webcam required:

- **Left mouse button held** — draw
- **Right mouse button held** — erase
- **F key held** — hold to clear (same confirmation delay as a fist)

This reuses the exact same `IntentStateMachine` and brush/canvas code a
real hand does — it's a stand-in for the *input*, not a separate code
path for drawing. Per the project spec, this is for testing only and is
never required for normal use.

## Running tests

```bash
pip install pytest
pytest aircanvas/tests -v
```

Tests are hardware-free: the camera tests mock `cv2.VideoCapture`, the
tracker tests exercise data structures and model-caching logic without
loading a real model, the feature/gesture/smoothing/calibration/state-
machine/intent/dev-input tests run against synthetic data
(`aircanvas/tests/helpers.py`), and the canvas tests (`stroke`, `history`,
`model`, `eraser`, `brush_engine`) run against a real but headless pygame
`Surface` — no window or display needed.

## Roadmap

| Phase | Focus |
|---|---|
| 1 ✅ | Skeleton, config, camera, tracker, tests |
| 2 ✅ | Pointer mapping, smoothing, gesture state machine, calibration |
| 3 ✅ | Canvas model, stroke representation, basic brush, undo/redo |
| 3 | Canvas model, stroke representation, basic brush, undo/redo |
| 4 | Touchless tool/color/size controls |
| 5 | Advanced brushes, particles, Living Ink, animation polish |
| 6 | Project save/load, PNG export, replay, share card |
| 7 | Themes, sound, accessibility, performance tuning |
| 8 | Testing, packaging, documentation, demo-ready UX |

The project stays runnable after every phase.
