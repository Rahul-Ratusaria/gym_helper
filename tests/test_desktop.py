"""Offscreen integration checks: no webcam access, no real history changes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from desktop import GymWindow
from demo import demo_pose


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.window = GymWindow(self.temp.name)
        self.window.timer.stop()
        self.now = 100.0
        self.clock = patch("desktop.time.monotonic", side_effect=lambda: self.now)
        self.clock.start()
        self.window.last_ui_tick = self.now

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def start(self, target=2, sets=2):
        self.window.reps_spin.setValue(target)
        self.window.sets_spin.setValue(sets)
        self.window.start_demo()
        self.now += 3.1
        self.window._tick()

    def test_demo_lifecycle_auto_rest_pause_and_no_history(self):
        self.start(target=1)
        for _ in range(180):
            self.now += 1 / 30
            self.window._tick()
            if self.window.workout.state == "rest":
                break
        self.assertEqual(self.window.workout.total_reps, 1)
        self.assertEqual(self.window.workout.state, "rest")
        self.assertFalse(self.window.exercise_combo.isEnabled())
        self.window.toggle_pause()
        remaining = self.window.workout.remaining
        self.now += 100
        self.window._tick()
        self.assertEqual(self.window.workout.state, "paused")
        self.window.toggle_pause()
        self.assertAlmostEqual(self.window.workout.deadline - self.now, remaining)
        self.window.skip_rest()
        self.assertEqual(self.window.workout.set_number, 2)
        self.assertEqual(self.window.coach.counter.reps, 0)
        self.window.finish_session()
        self.assertEqual(self.window.history.rows(), [])
        self.assertTrue(self.window.start_button.isEnabled())

    def test_automatic_completion_keeps_summary(self):
        self.start(target=1, sets=1)
        for _ in range(200):
            self.now += 1 / 30
            self.window._tick()
        self.assertEqual(self.window.workout.state, "complete")
        self.assertEqual(self.window.workout.total_reps, 1)
        self.assertIn("your session", self.window.cue_title.text())
        self.assertFalse(self.window.pause_button.isEnabled())
        self.assertEqual(self.window.history.rows(), [])

    def test_saved_session_is_idempotent_and_visible(self):
        self.start(target=1, sets=1)
        # Inject known landmarks into the actual analysis/save path in an isolated DB.
        self.window.canvas.is_demo = False
        self.window.source_kind = "Video file"
        for frame in range(155):
            t = frame / 30
            self.now += 1 / 30
            self.window.workout.tick(self.now)
            self.window._analyze(demo_pose("curl", t), 1280, 720, t, self.now)
        self.window.finish_session()
        self.assertEqual(len(self.window.history.rows()), 1)
        self.window._page(1)
        self.window.table.selectRow(0)
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertIn("Rep time", self.window.history_detail.toPlainText())

    def test_navigation_guide_and_display_controls(self):
        self.window._page(2)
        self.window.guide_select.setCurrentIndex(4)
        self.window._train_selected()
        self.assertEqual(self.window.exercise_combo.currentData(), "lunge")
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.window.mirror_check.setChecked(False)
        self.assertFalse(self.window.canvas.mirror)
        self.window.skeleton_check.setChecked(False)
        self.assertFalse(self.window.canvas.skeleton)
