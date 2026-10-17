"""Integration with actual MediaPipe on a generated blank video, never a webcam."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from camera import CameraWorker


class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_inference_video_finishes_and_releases_file(self):
        import cv2
        import numpy as np
        model = Path(__file__).resolve().parents[1] / "models/pose_landmarker_lite.task"
        if not model.is_file():
            self.skipTest("Download model with python download_model.py to run inference integration test")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            source = Path(temp) / "blank.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 20, (320, 180))
            self.assertTrue(writer.isOpened())
            for _ in range(6):
                writer.write(np.zeros((180, 320, 3), dtype=np.uint8))
            writer.release()
            worker = CameraWorker(str(source), model)
            errors, ended, packets = [], [], []
            worker.problem.connect(errors.append)
            worker.ended.connect(lambda: ended.append(True))
            worker.start()
            deadline = time.monotonic() + 20
            try:
                while worker.isRunning() and time.monotonic() < deadline:
                    packet = worker.take()
                    if packet:
                        packets.append(packet)
                    QTest.qWait(10)
            finally:
                worker.requestInterruption()
                self.assertTrue(worker.wait(10000), "Inference thread did not stop")
            self.app.processEvents()
            self.assertEqual(errors, [])
            self.assertEqual(len(packets), 6)
            self.assertTrue(ended)
            self.assertTrue(all(not p[1] for p in packets))
            self.assertEqual([p[2] for p in packets], sorted(p[2] for p in packets))
            source.unlink()  # Windows requires the capture handle to have been released.

    def test_missing_model_returns_actionable_error(self):
        worker = CameraWorker(0, Path(__file__).parent / "missing-model.task")
        errors = []
        worker.problem.connect(errors.append)
        worker.start()
        deadline = time.monotonic() + 10
        while worker.isRunning() and time.monotonic() < deadline:
            QTest.qWait(10)
        worker.requestInterruption()
        self.assertTrue(worker.wait(10000))
        self.app.processEvents()
        self.assertTrue(errors)
        self.assertIn("download_model.py", errors[0])
