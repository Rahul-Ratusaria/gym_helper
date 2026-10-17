"""Launch the Gym Helper desktop application."""
import argparse
from pathlib import Path
import sys
from tracker import EXERCISES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", choices=EXERCISES, default="curl")
    parser.add_argument("--side", choices=("auto", "left", "right"), default="auto")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--demo", action="store_true", help="Start a simulated presentation session")
    parser.add_argument("--data-dir", type=Path, help="Override history/preferences directory")
    args = parser.parse_args()
    try:
        from PySide6.QtWidgets import QApplication
        from desktop import GymWindow
    except ImportError as exc:
        parser.exit(1, f"Missing dependency: {exc}\nRun: python -m pip install -r requirements.txt\n")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Gym Helper")
    window = GymWindow(args.data_dir, args.exercise, args.camera, args.side)
    screen = app.primaryScreen().availableGeometry()
    window.resize(min(1440, screen.width()), min(960, screen.height() - 40))
    window.show()
    if args.demo:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, window.start_demo)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
