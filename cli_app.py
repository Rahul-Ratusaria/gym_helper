"""Run a local webcam exercise tracker using MediaPipe Tasks."""
import argparse
from pathlib import Path
import time

from tracker import EXERCISES, RepCounter, joint_angle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", choices=EXERCISES, default="curl")
    parser.add_argument("--side", choices=("left", "right"), default="left")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", type=Path, default=Path(__file__).parent / "models/pose_landmarker_lite.task")
    args = parser.parse_args()
    if not args.model.is_file():
        parser.error("Model missing. Run: python download_model.py")
    import cv2
    import mediapipe as mp

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        cap.release()
        raise SystemExit("Cannot open webcam. Check camera permissions or try --camera 1.")
    counter = RepCounter(EXERCISES[args.exercise])
    side = args.side
    last_ms = -1
    try:
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera stopped delivering frames.")
                now = time.monotonic()
                stamp = max(last_ms + 1, int(now * 1000))
                last_ms = stamp
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                height, width = frame.shape[:2]
                indices = getattr(counter.exercise, side)
                angle = None
                if result.pose_landmarks:
                    landmarks = result.pose_landmarks[0]
                    selected = [landmarks[i] for i in indices]
                    if all(p.visibility >= 0.65 and p.presence >= 0.65 and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in selected):
                        points = [(p.x * width, p.y * height) for p in selected]
                        angle = joint_angle(*points)
                        for a, b in zip(points, points[1:]):
                            cv2.line(frame, tuple(map(int, a)), tuple(map(int, b)), (80, 220, 80), 4)
                        for point in points:
                            cv2.circle(frame, tuple(map(int, point)), 7, (0, 220, 255), -1)
                feedback = counter.update(angle, now)
                rows = [f"{counter.exercise.title} | {side} | Reps: {counter.reps}",
                        f"Angle: {angle:.0f} deg" if angle is not None else "Joint not visible",
                        feedback, "1 Curl  2 Squat  3 Push-up | S Side | R Reset | Q Quit"]
                cv2.rectangle(frame, (0, 0), (width, 140), (25, 25, 25), -1)
                for row, text in enumerate(rows):
                    cv2.putText(frame, text, (12, 28 + row * 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
                cv2.imshow("Gym Helper", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or cv2.getWindowProperty("Gym Helper", cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key in (ord("1"), ord("2"), ord("3")):
                    counter = RepCounter(EXERCISES[{ord("1"): "curl", ord("2"): "squat", ord("3"): "pushup"}[key]])
                elif key == ord("r"):
                    counter = RepCounter(counter.exercise)
                elif key == ord("s"):
                    side = "right" if side == "left" else "left"
                    counter.reset_motion()
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
