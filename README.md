# Gym Helper · Movement Studio

A native Python desktop application for webcam exercise tracking, repetition counting and camera-based movement guidance. Rebuilt as a final-year computer vision project with MediaPipe Tasks, OpenCV and PySide6.

## Run

On this computer, double-click **launch.bat**, or run:

```powershell
.\.venv\Scripts\python.exe app.py
```

For a presentation without a camera:

```powershell
.\.venv\Scripts\python.exe app.py --demo
```

The interactive demo uses synthetic landmarks, is visibly labeled, and never saves simulated activity to history. No camera is opened until you choose Webcam and start a session.

## Install on another Windows computer

Use 64-bit Python 3.12 or 3.13. The application was tested with Python 3.13.9, PySide6 6.8.3, MediaPipe 0.10.35 and OpenCV contrib 4.14.0.94 on Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_model.py
.\.venv\Scripts\python.exe app.py
```

Installation and the model download require internet access. Do not copy `.venv` to another computer; recreate it there. PySide6 is pinned to the version verified on this environment. Only one OpenCV distribution is installed, since multiple distributions share the same `cv2` module.

## What is included

- **Workout studio:** dark interface, resizable scrollable panels, camera preview, pose overlay, rep ring, movement-depth indicator, live joint-angle trace and inference FPS.
- **Five exercise profiles:** bicep curl, squat, push-up, shoulder press and lunge. Exercise selection is manual.
- **Movement analysis:** confidence gating, pixel-aspect-correct angles, time-based smoothing, endpoint dwell, minimum repetition duration and cancellation after tracking loss or source discontinuities.
- **Stable side selection:** select anatomical left/right or let Auto choose the clearer side and lock it for that set.
- **Camera-based cues:** upper-arm drift for curls, torso lean for squats/lunges/presses, and shoulder–hip–ankle alignment for push-ups. These cues are independent of rep counting.
- **Workout management:** adjustable reps, sets and rest intervals; three-second preparation; automatic set transitions; pause/resume; skip rest; finish early and save partial sessions.
- **Multiple inputs:** webcam, recorded video and interactive demo. Video timestamps come from frame number/FPS. Video decoding pauses during rest, countdown and manual pauses.
- **Optional speech:** spoken rep counts, rest prompts and occasional form cues using the system speech engine. Availability depends on installed Windows voices.
- **Activity:** local SQLite history, complete-set totals, active duration, per-rep timing, exercise settings and CSV session-summary export.
- **Exercise guide:** setup, movement instructions, counting rules and camera placement for every profile.
- **Adjustable counting endpoints:** tune bent/extended joint angles before a session; restore exercise defaults at any time before starting.

## A workout, step by step

1. Choose your exercise. Follow the camera-placement note and keep one person in view.
2. Set your targets, rest duration and tracked side. For lunges, choose the front leg.
3. Choose Webcam, Video file or Interactive demo. Camera 0 is normally the built-in webcam; try 1 for another camera.
4. Start the session. Begin with the tracked joint extended. Shoulder presses begin overhead to establish the extended endpoint.
5. Reach the bent endpoint, then return to extension. Briefly reach each endpoint; do not bounce through it. Only complete cycles count.
6. The app starts a rest interval after your target reps, then begins the next set. Pause or finish early at any time.
7. Review real sessions in Activity. Select a row to see rep timing and settings, or export all session summaries to CSV.

The preview may be mirrored, but left/right always refer to your body. Only one side is counted; alternating movements are not combined into a single count. Changing exercise, side or targets is disabled during a session. Finish the session before making those changes.

### Shortcuts

| Key | Action |
| --- | --- |
| Space | Pause / resume |
| Escape | Finish current session |
| Ctrl+1 | Train |
| Ctrl+2 | Activity |
| Ctrl+3 | Exercise guide |

Optional launch arguments: `--exercise curl|squat|pushup|press|lunge`, `--side auto|left|right`, `--camera 0`, `--demo`, and `--data-dir PATH`. Saved preferences take precedence for camera/side when present. `cli_app.py` preserves the original minimal OpenCV interface for debugging.

## Counting and feedback limits

| Exercise | Bent endpoint | Extended endpoint | Tracked joint |
| --- | --- | --- | --- |
| Bicep curl | 55° | 155° | Elbow |
| Squat | 100° | 160° | Knee |
| Push-up | 95° | 160° | Elbow |
| Shoulder press | 95° | 160° | Elbow |
| Lunge | 105° | 160° | Front knee |

Defaults are configurable project heuristics, not clinically validated targets. Counting requires an extended → bent → extended cycle, a 0.12-second endpoint dwell, and at least 0.65 seconds for the moving part of the repetition. Incomplete movement is reset after tracking loss, pause, a large input gap, or a cycle lasting over 25 seconds.

Visibility percentages describe landmark detection confidence, not correct technique. Movement depth is the fraction between the two configured joint-angle endpoints, not an anatomical range-of-motion assessment. Counts do not verify whole-body exercise execution. A curl-like elbow motion can be counted under another elbow-based profile if the wrong exercise is selected. Perspective, occlusion, loose clothing, small subjects and lighting affect results. The app does not infer the selected exercise or medically assess movement.

Video is replayed at up to its source FPS, with slower playback when inference cannot keep up. Rep times use source timestamps. Active session time is wall-clock time in active sets and includes time spent repositioning or briefly losing tracking; pauses, countdowns and rests are excluded.

## Local data

Frames are processed in memory and are not recorded or uploaded by application code. Session summaries and per-rep metadata live in `data/workouts.sqlite3`; preferences live in `data/preferences.ini`. MediaPipe and Qt are third-party dependencies and may produce their own runtime logs. Demo sessions are excluded from the database. Exported CSV contains session summaries; per-rep details remain available in the app and SQLite payload.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe verify_ui.py
```

The tests cover angle geometry, synthetic exercise cycles on both sides, low confidence, invalid landmarks, side locking, interrupted/fast/stale reps, form cues, lifecycle timing, persistence, CSV export, GUI navigation, demo exclusion and real MediaPipe inference on a generated blank video. UI verification renders screenshots in `artifacts/` without accessing a camera or modifying real activity.

**Not yet measured:** live webcam rep accuracy, form-cue precision, and hardware-specific latency during real exercise. No accuracy percentage is claimed. See `docs/EVALUATION.md` for a reproducible real-person evaluation plan.

## Project structure

| File | Responsibility |
| --- | --- |
| `app.py` / `launch.bat` | Desktop entry points |
| `desktop.py` | Pages, user actions and session coordination |
| `widgets.py` | Camera canvas, chart, progress ring and visual theme |
| `camera.py` | Background capture and MediaPipe inference |
| `coaching.py` | Confidence, side selection, smoothing and movement cues |
| `tracker.py` | Exercise profiles, joint angles and rep state machine |
| `workout.py` | Countdown, active sets, pause, rest and completion |
| `storage.py` | SQLite persistence and CSV export |
| `demo.py` | Explicitly simulated landmarks |
| `tests/` | Logic, desktop and inference integration tests |

References: [MediaPipe Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python), [Qt for Python](https://doc.qt.io/qtforpython-6/).
