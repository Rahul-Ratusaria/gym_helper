import csv
import json
from pathlib import Path
import tempfile
import unittest

from storage import History
from workout import Workout


class WorkoutTests(unittest.TestCase):
    def test_sets_rest_completion_and_excluded_time(self):
        work = Workout(target=1, sets=2, rest_seconds=5)
        work.start(0)
        self.assertFalse(work.record_rep(1, 170, 2, "left"))
        work.tick(3)
        work.tick(5)
        work.record_rep(5, 170, 2, "left")
        self.assertEqual(work.state, "rest")
        self.assertFalse(work.record_rep(6, 170, 2, "left"))
        self.assertIsNone(work.tick(9))
        self.assertEqual(work.tick(10), "new_set")
        work.tick(12)
        work.record_rep(12, 170, 2, "left")
        self.assertEqual(work.state, "complete")
        self.assertEqual(work.total_reps, 2)
        self.assertEqual(work.set_number, 2)
        self.assertEqual(work.active_seconds, 4)

    def test_pause_freezes_active_time_and_rest(self):
        work = Workout(target=1, sets=2, rest_seconds=10)
        work.start(0)
        work.tick(3)
        work.pause(5)
        work.tick(100)
        work.resume(100)
        work.tick(102)
        self.assertEqual(work.active_seconds, 4)
        work.record_rep(102, 170, 2, "left")
        work.pause(104)
        work.resume(200)
        self.assertEqual(work.deadline, 208)
        self.assertEqual(work.tick(208), "new_set")

    def test_history_round_trip_and_csv(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            store = History(Path(temp) / "history.sqlite3")
            work = Workout(target=1, sets=1)
            work.start(0)
            work.tick(3)
            work.tick(6)
            work.record_rep(6, 170, 2.5, "left")
            store.save("2026-10-15T16:00:00+05:30", "curl", "Webcam", work, {"target": 1})
            rows = History(store.path).rows()
            self.assertEqual(rows[0]["completed_sets"], 1)
            self.assertEqual(json.loads(rows[0]["payload"])["repetitions"][0]["duration"], 2.5)
            output = Path(temp) / "export.csv"
            store.export(output)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(exported[0]["reps"], "1")

    def test_skip_rest_starts_next_set(self):
        work = Workout(target=1, sets=2)
        work.start(0)
        work.tick(3)
        work.record_rep(4, 170, 2, "right")
        self.assertEqual(work.skip_rest(5), "new_set")
        self.assertEqual(work.current_reps, 0)
        self.assertEqual(work.set_number, 2)
