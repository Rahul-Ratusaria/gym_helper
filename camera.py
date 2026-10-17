"""Background inference with a one-frame mailbox to prevent GUI backlog."""
from pathlib import Path
from threading import Lock
import time

from PySide6.QtCore import QThread, Signal


class CameraWorker(QThread):
    problem = Signal(str)
    ready = Signal()
    ended = Signal()

    def __init__(self, source, model, parent=None):
        super().__init__(parent)
        self.source = source
        self.model = Path(model)
        self.lock = Lock()
        self.latest = None
        self.hold = False

    def take(self):
        with self.lock:
            packet, self.latest = self.latest, None
        return packet

    def pause_video(self, paused):
        with self.lock:
            self.hold = paused

    def run(self):
        cap = None
        try:
            import cv2
            import mediapipe as mp
            if not self.model.is_file():
                raise RuntimeError("Pose model missing. Run python download_model.py, then try again.")
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                raise RuntimeError("Cannot open this source. Check camera permissions, camera index or video format.")
            is_video = isinstance(self.source, str)
            if not is_video:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = fps if 1 <= fps <= 240 else 30
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
                min_pose_detection_confidence=0.6, min_pose_presence_confidence=0.6,
                min_tracking_confidence=0.6)
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as pose:
                self.ready.emit()
                frame_number, last_stamp = 0, -1
                while not self.isInterruptionRequested():
                    with self.lock:
                        held = self.hold
                        pending = self.latest is not None
                    # Preserve every decoded video frame; webcam can drop stale frames.
                    if is_video and (held or pending):
                        self.msleep(10)
                        continue
                    began = time.monotonic()
                    ok, frame = cap.read()
                    if not ok:
                        if is_video:
                            self.ended.emit()
                            break
                        raise RuntimeError("Camera disconnected or stopped delivering frames.")
                    height, width = frame.shape[:2]
                    if width > 960:
                        frame = cv2.resize(frame, (960, round(height * 960 / width)))
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    media_time = frame_number / fps if is_video else began
                    stamp = max(last_stamp + 1, int(media_time * 1000))
                    last_stamp = stamp
                    result = pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                    landmarks = []
                    if result.pose_landmarks:
                        landmarks = [(p.x, p.y, p.z, min(p.visibility, p.presence)) for p in result.pose_landmarks[0]]
                    packet = (rgb, landmarks, media_time, 1 / max(time.monotonic() - began, .001))
                    with self.lock:
                        self.latest = packet
                    frame_number += 1
                    if is_video:
                        self.msleep(max(1, int((1 / fps - (time.monotonic() - began)) * 1000)))
        except Exception as exc:
            self.problem.emit(str(exc))
        finally:
            if cap is not None:
                cap.release()
