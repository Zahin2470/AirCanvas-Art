# AirCanvas — Paint Without Touching Anything

A touchless painting studio: move your index fingertip through the air in
front of your webcam and paint onto a virtual canvas.

**Status: Phase 2 of 8** — pointer mapping, smoothing, gesture
classification, a debounced intent state machine, and manual
calibration, on top of Phase 1's camera/tracker skeleton. There is
still no paintable canvas yet (that's Phase 3); this phase's
deliverable is a debug preview that proves the *interaction* pipeline
(raw fingertip → smoothed cursor → gesture → drawing/erasing/UI
intent) works end to end.

## What's here right now

- `main.py` — CLI entry point
- `aircanvas/config.py` — runtime configuration (camera, tracking, smoothing,
  mapping, gesture/state-machine settings)
- `aircanvas/vision/camera.py` — webcam capture, with graceful error handling
- `aircanvas/vision/tracker.py` — MediaPipe hand-landmark tracking
- `aircanvas/vision/features.py` — derived per-hand signals (fingertip,
  pinch distance, which fingers are extended)
- `aircanvas/vision/gestures.py` — per-frame gesture classification
  (pointing, pinch, two-finger, open palm, fist)
- `aircanvas/vision/smoothing.py` — velocity-adaptive pointer smoothing
- `aircanvas/vision/calibration.py` — camera-space → canvas-space
  coordinate mapping, plus two-point calibration
- `aircanvas/interaction/state_machine.py` — debounced intent state
  machine (hysteresis, hand-lost grace period, fist-hold-to-clear)
- `aircanvas/interaction/intent.py` — ties the above into one
  per-frame `FrameIntent` for the future canvas/rendering layers
- `aircanvas/app.py` — wires everything into a debug preview window
- `aircanvas/{canvas,rendering,audio,persistence,ui}/` — empty
  scaffolding for later phases (see Roadmap below)
- `aircanvas/tests/` — 80 unit tests, all hardware/network-free

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

A window opens showing your webcam feed with your hand skeleton, a raw
fingertip marker (thin red ring), a smoothed cursor (colored ring, color
matches the current intent state), and status text: current state/gesture,
velocity, and the mapped canvas-cursor coordinates.

**Gestures** (see `aircanvas/vision/gestures.py`):
| Gesture | Pose | Effect |
|---|---|---|
| Pointing | index finger only | move the cursor (no drawing) |
| Pinch | thumb + index together | draw (`DRAWING` state) |
| Two-finger | index + middle | erase (`ERASING` state) |
| Open palm | most/all fingers extended | pause / UI mode |
| Fist | no fingers extended | hold ~2/3 of a second to arm a clear (shown as a hold-progress percentage); release early to cancel |

**Controls:**
- **Q** / **Esc** — quit
- **1** — capture the top-left corner for calibration (point there and press 1)
- **2** — capture the bottom-right corner for calibration
- **C** — reset calibration back to the default margins

Calibration here is a temporary keyboard-driven dev tool — Phase 4's
touchless UI replaces it with a fully hands-only flow.

If the camera fails to open, AirCanvas prints a clear error instead of
crashing — try a different `--camera` index or check that no other app is
using the webcam.

## Running tests

```bash
pip install pytest
pytest aircanvas/tests -v
```

Tests are hardware-free: the camera tests mock `cv2.VideoCapture`, the
tracker tests exercise data structures and model-caching logic without
loading a real model, and the feature/gesture/smoothing/calibration/state-
machine/intent tests all run against synthetic landmark data
(`aircanvas/tests/helpers.py`) rather than a live camera or hand.

## Roadmap

| Phase | Focus |
|---|---|
| 1 ✅ | Skeleton, config, camera, tracker, tests |
| 2 ✅ | Pointer mapping, smoothing, gesture state machine, calibration |
| 3 | Canvas model, stroke representation, basic brush, undo/redo |
| 4 | Touchless tool/color/size controls |
| 5 | Advanced brushes, particles, Living Ink, animation polish |
| 6 | Project save/load, PNG export, replay, share card |
| 7 | Themes, sound, accessibility, performance tuning |
| 8 | Testing, packaging, documentation, demo-ready UX |

The project stays runnable after every phase.
