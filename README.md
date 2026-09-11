<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:020617,25:312e81,50:4f46e5,75:7c3aed,100:ec4899&height=150&section=header&text=🎨%20AirCanvas&fontSize=64&fontAlignY=38&animation=fadeIn&fontColor=ffffff" width="100%" alt="AirCanvas"/>

<h2>✨ Paint Without Touching Anything</h2>

<p><i>I moved my hand through the air, and the computer turned that movement into beautiful ink.</i></p>

<p><b>No mouse. No touchscreen. No boundaries.</b><br/>
Just your hand, a camera, and a canvas that lives in the air.</p>

</div>

AirCanvas is a touchless digital painting studio. Raise a hand toward your
webcam, move your index fingertip through the air, and paint onto a virtual
canvas — no mouse, no stylus, no touchscreen. Pinch to draw, two fingers to
erase, a fist to clear, all recognized in real time and turned into smooth,
expressive ink with a distinct character of its own.

This isn't a webcam-tracking demo with drawing bolted on. It's a complete,
tested, working application: real hand tracking, a debounced gesture
state machine, six genuinely different brush styles, a bounded particle
system, project save/load, PNG export, a shareable preview card, artwork
replay, four visual themes, procedural sound, and persisted preferences —
built in eight phases, all of which are done.

**269 tests. Zero hardware dependencies to run them. Runs with or without
a webcam** (see [Developer mode](#developer-mode-no-camera-needed)).


## Features

- **Real-time hand tracking** — MediaPipe's `HandLandmarker`, initialized once, reused every frame
- **Stabilized air-pointer control** — velocity-adaptive smoothing, deadband jitter filtering, resolution-independent coordinate mapping with configurable margins/sensitivity, and manual calibration
- **A debounced gesture state machine** — pointing, pinch, two-finger, open-palm, and fist gestures, hysteresis-protected so a single misread frame never starts an accidental stroke
- **Touchless color, brush-style, and size selection** — a toolbar you operate with the same "point, then pinch to confirm" language as drawing
- **Six distinct brush styles** — Smooth Ink, Neon Glow, Soft Marker, Particle, Rainbow Flow, Spark
- **Stroke-level undo/redo** — one undo = one stroke or one clear, standard redo invalidation
- **A real eraser** — modeled as a stroke painted in the background color, so it gets undo/redo and replay for free, and never destroys ink drawn after it
- **Living Ink** — a bounded, deterministic particle system: fading motes trail your cursor and your strokes, burst on a sharp turn, and settle when a stroke starts or ends
- **Project save/load** — plain JSON (`.aircanvas`), never pickle, atomic writes, corruption-safe loading
- **PNG export + a shareable preview card** — artwork, title, stroke count, and date composited together
- **Artwork replay** — watch a drawing reconstruct itself stroke-by-stroke and point-by-point, with play/pause/seek/speed
- **Crash recovery** — autosaves periodically, reloads automatically if the last session didn't exit cleanly
- **Four visual themes** — Dark, Light, Neon, Monochrome
- **Procedural sound feedback** — short synthesized tones, no bundled audio files, silently disabled with no audio device
- **Persisted preferences** — theme, brush, color, size, mirror mode, particle/performance setting, and audio all reload automatically next launch
- **An in-app help overlay** (**H**) — a cheat-sheet you never have to leave the app to read
- **A developer mode** — draw, erase, and touch every toolbar control with just a mouse and keyboard, no webcam required, and an automatic fallback into it if your camera can't open

## The core loop

```
Camera → Hand Landmarks → Stabilized Pointer → Gesture Intent → Brush Engine → Particles/Canvas → Artwork
```

Each arrow is a real module boundary, not just a comment — see
[Tracking vs. smoothing vs. gesture intent vs. brush rendering](#tracking-vs-smoothing-vs-gesture-intent-vs-brush-rendering)
for what each stage actually owns.

## Gesture map

| Gesture | Pose | Effect |
|---|---|---|
| Pointing | index finger only | move the cursor (no drawing) |
| Pinch | thumb + index together | draw (on canvas) or select (on toolbar) |
| Two-finger | index + middle | erase, same size as the current brush |
| Open palm | most/all fingers extended | **pause** — cursor moves, nothing else happens |
| Fist | no fingers extended | hold ~2/3 of a second to clear the canvas |

Full keyboard reference (all optional utility actions — see
[Engineering notes](#tracking-vs-smoothing-vs-gesture-intent-vs-brush-rendering) on why these stay
keyboard-driven):

| Key | Action |
|---|---|
| **Q** / **Esc** | quit (Esc closes the help overlay first, if it's open) |
| **H** | toggle the in-app help overlay |
| **Z** / **X** | undo / redo |
| **[** / **]** | smaller / larger brush |
| **Tab** | cycle color · **B** cycle brush style |
| **1** / **2** / **C** | calibrate top-left / bottom-right / reset |
| **S** | save project · **E** export PNG + share card |
| **R** | toggle replay mode |
| **Space** / **Home** / **←→** / **↑↓** | (in replay) play-pause / restart / seek / speed |
| **T** | cycle theme |
| **N** | mute · **-** / **=** volume down/up |
| **M** | toggle camera mirror |
| **P** | toggle Living Ink + toolbar hover-glow (reduced effects) |

## Installation

```bash
python3 -m venv .venv   #macOS/Linux
pip install -r requirements.txt
```

Or install it as a package (adds an `aircanvas` command and enables
`python -m aircanvas`):

```bash
pip install -e .
```

### A note on MediaPipe versions

This project targets current MediaPipe (0.10.x), which replaced the older
`mp.solutions.hands.Hands` API with the Tasks API
(`mediapipe.tasks.python.vision.HandLandmarker`). One practical
consequence: the hand-landmark model is no longer bundled inside the pip
package — it's a `.task` file that `aircanvas/vision/tracker.py` downloads
once from Google's hosted model and caches under `~/.aircanvas/models/`.
**Your first run needs an internet connection** to fetch that file; every
run after that works offline.

## Running

```bash
python main.py                 # default camera (index 0)
python main.py --camera 1      # use a different camera index
python main.py --debug         # verbose logging
python main.py --open art.aircanvas   # load a saved project at startup
python -m aircanvas             # same thing, if installed as a package
aircanvas                       # same thing, via the console script
```

A window opens with three panels: **tools** (color swatches, brush styles
and sizes, undo/redo) on the left, your **webcam feed** in the middle, and
the **art canvas** on the right. Raise your hand and start painting — press
**H** at any time for an in-app reminder of every control.

**Using the toolbar:** point at a color, brush style, size, or Undo/Redo,
then hold a pinch over it for about a third of a second (the button fills
up as you hold — the same "point, then pinch to confirm" language as
drawing). Pinching over the canvas draws; pinching over the toolbar
selects. The fingertip cursor spans the whole window, not just the canvas,
which is what lets it reach the toolbar at all.

If the camera fails to open, AirCanvas prints a clear message and
**automatically falls back to developer mouse mode** rather than crashing.

*Known rough edge:* dragging an in-progress stroke across the toolbar
pauses it (rather than ending it) while you're over the toolbar, and if
you linger there it could trigger whatever button is underneath. Doesn't
affect normal use — worth smoothing out in a future polish pass.

## Developer mode (no camera needed)

```bash
python main.py --mouse
```

Tests the entire app — drawing with every brush style, erasing, the
touchless toolbar, Living Ink, undo/redo, save/export, replay — with just
a mouse and keyboard:

- **Left mouse button held** — draw, or select whatever toolbar widget it's held over
- **Right mouse button held** — erase
- **F key held** — hold to clear (same confirmation delay as a fist)

This reuses the exact same `IntentStateMachine`, toolbar, and canvas code
a real hand does (`aircanvas/interaction/dev_input.py`) — it's a stand-in
for the *input*, not a separate code path. Per the project spec, this is
for testing only and is never required for normal use.

## Calibration

Point at the top-left corner of the area you want to paint in and press
**1**; point at the bottom-right and press **2**. AirCanvas remaps that
region to the full active canvas area. Press **C** to reset to the
default margins. This is a keyboard-triggered action (not gesture-driven)
by design — see the note in
[Tracking vs. smoothing vs. gesture intent vs. brush rendering](#tracking-vs-smoothing-vs-gesture-intent-vs-brush-rendering)
on why utility actions like this stay on the keyboard rather than
competing with the drawing gesture vocabulary.

## Brush styles

Pick one from the toolbar's brush-type buttons (or cycle with **B**):

| Brush | Look |
|---|---|
| Ink | Smooth Ink — a clean, solid stroke |
| Glow | Neon Glow — a bright core with a soft halo bleeding outward |
| Marker | Soft Marker — wide, translucent, soft-edged |
| Particle | Particle — a scattered, granular cluster instead of a solid line |
| Rainbow | Rainbow Flow — hue cycles smoothly along the stroke's length |
| Spark | Spark — sparse, jittered, high-contrast flecks |

Every brush's look is a **deterministic** function of the stroke's own
stored points, size, and color (`aircanvas/canvas/brush_engine.py`) — any
jitter (Particle, Spark) is derived from the stamp's own position, and
Rainbow Flow's hue comes from cumulative distance walked along the
stroke, never from live randomness or wall-clock time. That's what makes
`undo → redo` pixel-identical regardless of brush style, and it's what
makes replay trustworthy: a saved stroke always redraws exactly the way
it looked when drawn.

## Living Ink

AirCanvas's signature effect (`aircanvas/rendering/particles.py` +
`effects.py`). As you draw, faint motes trail off the stroke — more of
them the faster you move — a small burst fires on a sharp direction
change, and a stroke gently "settles" with a soft burst when it starts
and ends. The cursor also leaves a light trail while just pointing.

This is a purely decorative, real-time overlay: it never touches the
saved stroke data, so it has zero bearing on undo/redo or replay
correctness — only the deterministic brush rendering above does. Toggle
it (along with the toolbar's hover-glow) anytime with **P**.

## Themes, sound, and persistence

- **T** cycles theme: Dark (default) → Light → Neon → Monochrome → Dark.
  Themes recolor the toolbar, panels, status bar, and borders — never the
  canvas background, since that's part of the artwork's own data, not a
  display preference
- **N** mutes/unmutes · **-** / **=** adjust volume
- **M** toggles the camera mirror
- **P** toggles Living Ink particles *and* the toolbar's hover-glow
  effect together — a combined "reduced effects" switch for lower-end
  machines, or anyone who'd rather the UI stay calmer. It only ever
  changes presentation, never how a stroke bakes onto the canvas, so it
  can't affect redraw or replay fidelity

Every one of these — plus your current brush, color, size, and mirror
setting — saves to `~/.aircanvas/settings.json` on exit and reloads
automatically next launch. A missing or corrupted settings file just
falls back to defaults rather than crashing startup.

**Sound** (`aircanvas/audio/manager.py`) is a handful of short,
procedurally-generated tones — no bundled audio files — confirming brush
activation, color/tool/size selection, erase, undo/redo, clear, export,
and replay start. Nothing loops or plays continuously while you draw. If
your machine has no usable audio device, `AudioManager` detects that at
startup and every sound call becomes a silent no-op; nothing else about
the app is affected.

## Save, export, and replay

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
rather than remapping them proportionally, so strokes may appear cropped
or offset if the two sizes differ significantly. Fine for the common
case (nothing currently changes the canvas size); worth revisiting if
canvas resizing is ever added.

## Project file format

Plain JSON, never a Python pickle, so a `.aircanvas` file is inspectable
and hand-editable:

```json
{
  "version": 1,
  "canvas": {"width": 1600, "height": 900},
  "background": "#121218",
  "saved_at": 1735689600.0,
  "metadata": {"title": "..."},
  "strokes": [
    {
      "points": [[x, y], ...],
      "point_times": [0.0, 0.033, ...],
      "color": "#f05757",
      "size": 14.0,
      "opacity": 1.0,
      "brush_type": "neon_glow",
      "created_at": 1735689601.2
    }
  ]
}
```

Strokes are the single source of truth (`aircanvas/canvas/stroke.py`) —
the same list backs live drawing, undo/redo, PNG export, replay, and
saved projects, so there's no separate "export format" to keep in sync.
`point_times` (seconds elapsed since the stroke began) drives replay
pacing; a project saved before this field existed, or with a
length-mismatched array, just falls back to assuming evenly-spaced
points rather than failing to load. Loading a project also replays its
strokes through the normal undo history, so a reopened artwork is
immediately undoable stroke-by-stroke, exactly like one you just drew.

## Troubleshooting

**Camera won't open / "Could not open camera index 0"**
Check that no other app (Zoom, another browser tab, etc.) is holding the
webcam, that AirCanvas has camera permission in your OS's privacy
settings, and try `--camera 1` (or higher) if you have more than one
camera. AirCanvas will automatically drop into developer mouse mode
rather than crash — you can keep working while you sort out the camera.

**"Hand-tracking model unavailable" on first launch**
The hand-landmark model downloads from Google on first run (see
[A note on MediaPipe versions](#a-note-on-mediapipe-versions)) — you need
internet access once. After that first successful download it's cached
under `~/.aircanvas/models/` and works offline.

**No sound**
`AudioManager` silently disables itself if it can't find a usable audio
device — this is intentional graceful degradation, not a bug, and
nothing else about the app is affected. Check `N` isn't toggled to mute,
and that your system volume isn't at zero.

**Low FPS / stuttering**
Press **P** to disable Living Ink particles and the toolbar's hover-glow
— that's the app's "reduced effects" lever. Also try a smaller
`camera_width`/`camera_height` in `aircanvas/config.py` if your webcam's
default resolution is unusually high.

**Hand tracked, but the cursor feels laggy or jittery**
Jittery: your camera may be low light or low resolution, which makes
MediaPipe's landmarks noisier — try better lighting. Laggy: the
smoothing is tuned to trade a little lag for stability at low speed;
`smoothing_max_alpha` in `aircanvas/config.py` controls how quickly it
catches up during fast motion.

**Drawing feels offset from where my finger actually is**
Recalibrate: point at the top-left of your intended painting area and
press **1**, then the bottom-right and press **2** (see
[Calibration](#calibration)).

**A saved project won't load ("... is not valid JSON" / "invalid or missing canvas section" / "Unsupported project format version")**
The file is corrupted, hand-edited incorrectly, or was saved by an
incompatible version. `project_io.load_project` always raises a clear
`ProjectLoadError` describing exactly what's wrong rather than crashing —
check the message for the specific issue.

## Running tests

```bash
pip install pytest
pytest aircanvas/tests -v
```

269 tests, all hardware/network-free:

- camera tests mock `cv2.VideoCapture`
- tracker tests exercise data structures and model-caching logic without loading a real model
- feature/gesture/smoothing/calibration/state-machine/intent/dev-input/toolbar/replay/theme/settings tests run against synthetic data or real temp files (`tmp_path`)
- particle/Living-Ink/audio tests use a seeded `random.Random` (and, for audio, the SDL dummy driver) for reproducibility
- canvas + brush-style tests run against a real but headless pygame `Surface`
- `test_integration.py` runs the actual `aircanvas.app.run()` loop headlessly (SDL dummy video/audio drivers, an isolated `AIRCANVAS_HOME` per test) to verify the whole app boots, falls back to mouse mode, loads projects, recovers from a simulated crash, and exits cleanly — end to end, not just its parts in isolation

No window, display, camera, or microphone needed anywhere in the suite.

## Project structure

```
aircanvas/
├── main.py                    # CLI entry point (thin shim over aircanvas/cli.py)
├── pyproject.toml             # packaging: pip install -e ., `aircanvas` console script
├── requirements.txt
├── README.md
└── aircanvas/                 # the actual package
    ├── __main__.py            # enables `python -m aircanvas`
    ├── cli.py                 # argument parsing + main()
    ├── app.py                 # the pygame app: layout, routing, main loop
    ├── config.py              # runtime configuration + app-data paths
    ├── vision/                # camera → landmarks → features → gesture (per-frame, stateless-ish)
    │   ├── camera.py          # webcam capture, graceful failure handling
    │   ├── tracker.py         # MediaPipe HandLandmarker wrapper
    │   ├── features.py        # fingertip/pinch-distance/finger-extension signals
    │   ├── gestures.py        # one frame's features -> one Gesture label
    │   ├── smoothing.py       # velocity-adaptive EMA + jitter deadband
    │   └── calibration.py     # camera-space -> canvas-space mapping
    ├── interaction/           # gesture -> stable, debounced application intent
    │   ├── state_machine.py   # hysteresis/debounce over raw per-frame gestures
    │   ├── intent.py          # IntentResolver: ties vision + state machine + smoothing together
    │   └── dev_input.py       # mouse/keyboard stand-in for a real hand (testing only)
    ├── canvas/                # the document: strokes, brushes, undo/redo, replay
    │   ├── stroke.py          # Stroke: points, point_times, color, size, opacity, brush_type
    │   ├── brushes.py         # BrushType catalog
    │   ├── brush_engine.py    # stamps strokes onto a pygame surface, per-brush-type + deterministic
    │   ├── eraser.py          # eraser stroke factory + stamp geometry
    │   ├── history.py         # generic undo/redo action stack
    │   ├── model.py           # CanvasModel: strokes + undo/redo, no pixel data
    │   └── replay.py          # ReplayController: reconstructs drawing over time
    ├── rendering/             # decorative/presentational layers (never touch stroke data)
    │   ├── particles.py       # bounded, deterministic particle system
    │   ├── effects.py         # LivingInkEmitter: the emission rules
    │   └── themes.py          # dark/light/neon/monochrome UI chrome
    ├── audio/
    │   └── manager.py         # procedurally-generated UI tones, graceful degradation
    ├── persistence/
    │   ├── project_io.py      # JSON .aircanvas save/load + PNG export
    │   ├── share_card.py      # composited preview image
    │   └── settings.py        # persisted user preferences
    ├── ui/
    │   └── toolbar.py         # touchless hover + pinch-dwell widget system
    ├── utils/
    │   └── logging_setup.py
    └── tests/                 # 269 tests -- see "Running tests" above
```

## Tracking vs. smoothing vs. gesture intent vs. brush rendering

Four layers that are easy to conflate but deliberately kept independent
(`aircanvas/vision/`, `aircanvas/interaction/`, `aircanvas/canvas/`):

- **Tracking** (`vision/tracker.py`) answers "where are the hand's 21
  landmarks, this frame?" — raw, jittery, camera-space coordinates. It
  knows nothing about gestures or drawing.
- **Smoothing** (`vision/smoothing.py`) answers "where is the fingertip
  *really*, once you filter out jitter?" — a velocity-adaptive filter
  that trades a little lag for stability at low speed and catches up
  fast during deliberate motion. It knows nothing about what the
  smoothed point will be used *for*.
- **Gesture intent** (`vision/gestures.py` + `interaction/state_machine.py`)
  answers "what does the user want to happen?" — classifying a pose
  into a `Gesture` each frame, then debouncing that into a stable
  `IntentState` (`POINTER_ACTIVE`, `DRAWING`, `ERASING`, ...) so a single
  misread frame can never start an accidental stroke. It knows about
  hysteresis and timing, not about pixels.
- **Brush rendering** (`canvas/brush_engine.py`) answers "given a
  confirmed stroke of points, what does it look like?" — a pure,
  deterministic function of stored stroke data (position, size, color,
  brush type), with zero awareness that a hand, a camera, or a gesture
  state machine exists upstream of it at all.

This separation is why the whole interaction pipeline is unit-testable
without a camera (synthetic landmarks in, assertions on classified
gestures out) and why [developer mode](#developer-mode-no-camera-needed)
works at all: mouse input can stand in for tracking+smoothing+gesture
intent and feed the *exact same* brush rendering a real hand does,
because brush rendering was never coupled to where its input came from.

## Development history

Built in eight phases, keeping the project runnable after every one:

| Phase | Focus |
|---|---|
| 1 ✅ | Skeleton, config, camera, tracker, tests |
| 2 ✅ | Pointer mapping, smoothing, gesture state machine, calibration |
| 3 ✅ | Canvas model, stroke representation, basic brush, undo/redo |
| 4 ✅ | Touchless tool/color/size controls |
| 5 ✅ | Advanced brushes, particles, Living Ink, animation polish |
| 6 ✅ | Project save/load, PNG export, replay, share card |
| 7 ✅ | Themes, sound, accessibility, performance tuning |
| 8 ✅ | Testing, packaging, documentation, demo-ready UX |

Known, deliberately-scoped rough edges (not oversights — each is called
out inline above where it's relevant): dragging a stroke across the
toolbar mid-draw can pause into an accidental button trigger; loading a
project saved at a different canvas size doesn't remap coordinates;
calibration and a handful of utility actions (save/export/theme/replay
controls) are keyboard-driven rather than gesture-driven, by design, so
they never compete with the drawing gesture vocabulary.
