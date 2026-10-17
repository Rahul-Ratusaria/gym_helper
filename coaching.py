"""Pose confidence gating, smoothing and explicitly heuristic movement cues."""
from dataclasses import dataclass
from math import atan2, degrees, exp, isfinite
from tracker import EXERCISES, RepCounter, joint_angle


@dataclass
class Observation:
    angle: float | None = None
    confidence: float = 0
    side: str = "auto"
    cue: str = "Move into view to begin"
    detail: str = "Keep all required joints inside the camera frame."
    warning: bool = False
    progress: float = 0
    counted: bool = False
    duration: float | None = None


def visible(point, threshold=0.65):
    return (all(isfinite(x) for x in point[:4]) and 0 <= point[0] <= 1
            and 0 <= point[1] <= 1 and point[3] >= threshold)


class Coach:
    def __init__(self, exercise="curl", side="auto", low=None, high=None):
        from dataclasses import replace
        profile = EXERCISES[exercise]
        if low is not None and high is not None:
            if not (20 <= low and high <= 180 and high - low >= 20):
                raise ValueError("Angle endpoints need at least 20 degrees of separation.")
            profile = replace(profile, low=low, high=high)
        self.key = exercise
        self.counter = RepCounter(profile)
        self.requested_side = side
        self.locked_side = None if side == "auto" else side
        self.smoothed = None
        self.last_time = None

    def interrupt(self):
        self.counter.reset_motion()
        self.smoothed = self.last_time = None

    def new_set(self):
        self.counter = RepCounter(self.counter.exercise)
        self.locked_side = None if self.requested_side == "auto" else self.requested_side
        self.interrupt()

    def process(self, landmarks, width, height, timestamp):
        profile = self.counter.exercise
        if not landmarks or len(landmarks) < 33:
            self.interrupt()
            return Observation(side=self.locked_side or "auto")
        if self.locked_side is None:
            candidates = {}
            for side in ("left", "right"):
                points = [landmarks[i] for i in getattr(profile, side)]
                if all(visible(p) for p in points):
                    candidates[side] = min(p[3] for p in points)
            if candidates:
                self.locked_side = max(candidates, key=candidates.get)
        side = self.locked_side
        if side is None:
            self.interrupt()
            return Observation()
        selected = [landmarks[i] for i in getattr(profile, side)]
        confidence = min(p[3] for p in selected)
        if not all(visible(p) for p in selected):
            self.interrupt()
            return Observation(confidence=confidence, side=side,
                               cue="Tracking paused", detail=f"Bring your {side} working joints into view.")
        angle = joint_angle(*[(p[0] * width, p[1] * height) for p in selected])
        if angle is None:
            self.interrupt()
            return Observation(side=side)
        dt = max(0, timestamp - self.last_time) if self.last_time is not None else 1
        # A source discontinuity must never bridge two halves of a repetition.
        if dt > 0.8:
            self.interrupt()
        alpha = 1 - exp(-dt / 0.07)
        self.smoothed = angle if self.smoothed is None else self.smoothed + alpha * (angle - self.smoothed)
        self.last_time = timestamp
        previous = self.counter.reps
        cue = self.counter.update(self.smoothed, timestamp)
        detail = "Complete both endpoints to count a repetition."
        warning = False
        offset = 0 if side == "left" else 1
        shoulder, elbow, hip, ankle = (landmarks[i + offset] for i in (11, 13, 23, 27))
        if all(visible(p) for p in (shoulder, hip)):
            lean = abs(degrees(atan2((shoulder[0] - hip[0]) * width, (hip[1] - shoulder[1]) * height)))
            if self.key in ("squat", "lunge", "press") and lean > (55 if self.key == "squat" else 35):
                cue, detail, warning = "Check your torso position", "Camera estimate: try reducing excessive forward or backward lean.", True
        if self.key == "curl" and all(visible(p) for p in (shoulder, elbow, hip)):
            upper_arm = joint_angle(*[(p[0] * width, p[1] * height) for p in (elbow, shoulder, hip)])
            if upper_arm is not None and upper_arm > 35:
                cue, detail, warning = "Keep your upper arm steady", "Camera estimate: bring your elbow closer to your side.", True
        if self.key == "pushup" and all(visible(p) for p in (shoulder, hip, ankle)):
            alignment = joint_angle(*[(p[0] * width, p[1] * height) for p in (shoulder, hip, ankle)])
            if alignment is not None and alignment < 155:
                cue, detail, warning = "Check your body alignment", "Camera estimate: keep shoulders, hips and ankles in one line.", True
        counted = self.counter.reps > previous
        if counted and not warning:
            cue, detail = "Rep complete. Keep it controlled.", "Both movement endpoints reached."
        progress = max(0, min(1, (profile.high - self.smoothed) / (profile.high - profile.low)))
        return Observation(self.smoothed, confidence, side, cue, detail, warning, progress,
                           counted, self.counter.last_duration if counted else None)
