"""Camera-independent exercise geometry and repetition state machine."""
from dataclasses import dataclass
from math import acos, degrees, isfinite, sqrt


def joint_angle(a, b, c):
    """Angle ABC in degrees; use pixel coordinates to preserve aspect ratio."""
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    length = sqrt(sum(x*x for x in u) * sum(x*x for x in v))
    if length < 1e-8:
        return None
    return degrees(acos(max(-1, min(1, sum(x*y for x, y in zip(u, v)) / length))))


@dataclass(frozen=True)
class Exercise:
    title: str
    left: tuple
    right: tuple
    low: float
    high: float
    prompt: str
    group: str = "Strength"
    setup: str = "Stand side-on to your camera. Keep your working joints visible."
    steps: tuple = ()


EXERCISES = {
    "curl": Exercise("Bicep curl", (11, 13, 15), (12, 14, 16), 55, 155,
                     "Curl upward with control", "Upper body",
                     "Stand side-on. Keep shoulder, elbow and wrist in frame.",
                     ("Start with your arm extended at your side.", "Bend your elbow while keeping the upper arm close to your torso.", "Return to extension to complete one repetition.")),
    "squat": Exercise("Squat", (23, 25, 27), (24, 26, 28), 100, 160,
                      "Lower with control, then stand", "Lower body",
                      "Place the camera at hip height, side-on. Show your full body.",
                      ("Start standing with your knees extended.", "Bend your hips and knees into a comfortable squat.", "Stand back up to complete one repetition.")),
    "pushup": Exercise("Push-up", (11, 13, 15), (12, 14, 16), 95, 160,
                       "Lower with control", "Upper body",
                       "Place the camera low and side-on. Include shoulders, hips and ankles.",
                       ("Start in a high plank with arms extended.", "Bend your elbows and lower your body together.", "Extend your arms to complete one repetition.")),
    "press": Exercise("Shoulder press", (11, 13, 15), (12, 14, 16), 95, 160,
                      "Lower to your starting position", "Upper body",
                      "Stand side-on. Leave space above your head for both hands.",
                      ("Raise your arms overhead to establish the extended position.", "Lower until your elbows are bent.", "Press overhead again to complete one repetition.")),
    "lunge": Exercise("Lunge", (23, 25, 27), (24, 26, 28), 105, 160,
                      "Lower into the lunge with control", "Lower body",
                      "Stand side-on in a split stance. Select your front leg as the tracked side.",
                      ("Begin with the tracked front knee extended.", "Bend the front knee as you lower into the lunge.", "Return to extension. Complete one side before switching.")),
}


class RepCounter:
    """Require extended -> bent -> extended, with a short endpoint dwell."""
    def __init__(self, exercise, dwell=0.12, min_duration=0.65):
        self.exercise = exercise
        self.dwell = dwell
        self.reps = 0
        self.min_duration = min_duration
        self.last_duration = None
        self.reset_motion()

    def reset_motion(self):
        self.phase = "ready"
        self.candidate = None
        self.since = None
        self.started = None
        self.bending = False

    def update(self, angle, timestamp):
        if angle is None or not isfinite(angle):
            self.reset_motion()
            return "Move into view; counting paused"
        if self.phase == "extended" and angle < self.exercise.high and not self.bending:
            self.started = timestamp
            self.bending = True
        if self.started is not None and timestamp - self.started > 25:
            self.reset_motion()
        endpoint = "extended" if angle >= self.exercise.high else "bent" if angle <= self.exercise.low else None
        if endpoint != self.candidate:
            self.candidate, self.since = endpoint, timestamp
        if endpoint and timestamp - self.since >= self.dwell:
            if endpoint == "extended":
                if self.phase == "bent":
                    duration = timestamp - self.started if self.started is not None else 0
                    if duration >= self.min_duration:
                        self.reps += 1
                        self.last_duration = duration
                self.phase = "extended"
                self.started = None
                self.bending = False
            elif self.phase == "extended":
                self.phase = "bent"
        if self.phase == "ready":
            return "Start with the tracked joint extended"
        if self.phase == "bent":
            return "Return to the starting position"
        return self.exercise.prompt
