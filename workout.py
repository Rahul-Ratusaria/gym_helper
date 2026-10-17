"""Deterministic workout lifecycle, independent of the UI and camera."""
from dataclasses import dataclass, field


@dataclass
class Workout:
    target: int = 12
    sets: int = 3
    rest_seconds: int = 45
    state: str = "idle"
    set_number: int = 1
    current_reps: int = 0
    total_reps: int = 0
    active_seconds: float = 0
    records: list = field(default_factory=list)
    deadline: float = 0
    last_tick: float = 0
    resume_state: str = "active"
    remaining: float = 0

    def start(self, now):
        self.state, self.deadline, self.last_tick = "countdown", now + 3, now

    def tick(self, now):
        if self.state == "active":
            self.active_seconds += max(0, now - self.last_tick)
        self.last_tick = now
        if self.state in ("countdown", "rest") and now >= self.deadline:
            was_rest = self.state == "rest"
            self.state = "active"
            if was_rest:
                self.set_number += 1
                self.current_reps = 0
            return "new_set" if was_rest else "begin"
        return None

    def record_rep(self, now, angle, duration, side):
        if self.state != "active":
            return False
        self.current_reps += 1
        self.total_reps += 1
        self.records.append({"set": self.set_number, "rep": self.current_reps,
                             "elapsed": round(self.active_seconds, 2), "angle": round(angle, 1),
                             "duration": round(duration, 2) if duration is not None else None,
                             "side": side})
        if self.current_reps >= self.target:
            self.state = "complete" if self.set_number >= self.sets else "rest"
            self.deadline = now + self.rest_seconds
        return True

    def pause(self, now):
        if self.state not in ("active", "rest", "countdown"):
            return
        self.tick(now)
        self.resume_state = self.state
        self.remaining = max(0, self.deadline - now)
        self.state = "paused"

    def resume(self, now):
        if self.state == "paused":
            self.state = self.resume_state
            self.deadline, self.last_tick = now + self.remaining, now

    def skip_rest(self, now):
        if self.state == "rest":
            self.deadline = now
            return self.tick(now)

    def finish(self, now):
        self.tick(now)
        self.state = "complete"
