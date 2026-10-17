"""Local, transactional SQLite session history. Frames are never stored."""
import csv
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class History:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY, started TEXT NOT NULL, exercise TEXT NOT NULL,
                source TEXT NOT NULL, reps INTEGER NOT NULL, completed_sets INTEGER NOT NULL,
                seconds REAL NOT NULL, payload TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, started, exercise, source, workout, settings):
        completed = sum(1 for s in range(1, workout.sets + 1)
                        if sum(r["set"] == s for r in workout.records) >= workout.target)
        payload = json.dumps({"settings": settings, "repetitions": workout.records})
        with self.connect() as db:
            cursor = db.execute("INSERT INTO sessions (started, exercise, source, reps, completed_sets, seconds, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (started, exercise, source, workout.total_reps, completed,
                                 round(workout.active_seconds, 2), payload))
            return cursor.lastrowid

    def rows(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM sessions ORDER BY id DESC")]

    def export(self, path):
        # All columns are application-generated; no untrusted spreadsheet formulas.
        with Path(path).open("w", newline="", encoding="utf-8-sig") as out:
            fields = ["id", "started", "exercise", "source", "reps", "completed_sets", "seconds"]
            writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows())
