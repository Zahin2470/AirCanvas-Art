# AirCanvas — Paint Without Touching Anything

A touchless painting studio: move your index fingertip through the air in
front of your webcam and paint onto a virtual canvas.

**Status: Phase 1 of 8** — project skeleton, configuration, camera layer,
hand-landmark tracker, and test suite. There is no paintable canvas yet;
this phase's deliverable is a debug preview that proves the vision
pipeline (camera → hand landmarks → skeleton overlay) works end to end.

## What's here right now

- `main.py` — CLI entry point
- `aircanvas/config.py` — runtime configuration (camera, tracking settings)
- `aircanvas/vision/camera.py` — webcam capture, with graceful error handling
- `aircanvas/vision/tracker.py` — MediaPipe hand-landmark tracking
- `aircanvas/app.py` — wires the above into a debug preview window
- `aircanvas/{interaction,canvas,rendering,audio,persistence,ui}/` —
  empty scaffolding for later phases (see Roadmap below)
- `aircanvas/tests/` — unit tests for config, camera, and tracker logic

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

A window opens showing your webcam feed with your hand skeleton and
fingertip cursor overlaid. Press **Q** or **Esc** to quit.

If the camera fails to open, AirCanvas prints a clear error instead of
crashing — try a different `--camera` index or check that no other app is
using the webcam.

## Running tests

```bash
pip install pytest
pytest aircanvas/tests -v
```

Tests are hardware-free: the camera tests mock `cv2.VideoCapture`, and the
tracker tests exercise the data structures and model-caching logic without
loading a real model or touching a camera.

## Roadmap

| Phase | Focus |
|---|---|
| 1 ✅ | Skeleton, config, camera, tracker, tests |
| 2 | Pointer mapping, smoothing, gesture state machine, calibration |
| 3 | Canvas model, stroke representation, basic brush, undo/redo |
| 4 | Touchless tool/color/size controls |
| 5 | Advanced brushes, particles, Living Ink, animation polish |
| 6 | Project save/load, PNG export, replay, share card |
| 7 | Themes, sound, accessibility, performance tuning |
| 8 | Testing, packaging, documentation, demo-ready UX |

The project stays runnable after every phase.
