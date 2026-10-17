"""Render deterministic idle/demo/compact/guide screenshots without a camera."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from desktop import GymWindow


def main():
    app = QApplication([])
    output = Path(__file__).parent / "artifacts"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        win = GymWindow(temp)
        win.timer.stop()
        win.show()
        app.processEvents()
        win.grab().save(str(output / "studio-idle.png"))
        now = 100.0
        with patch("desktop.time.monotonic", side_effect=lambda: now):
            win.last_ui_tick = now
            win.start_demo()
            now += 3.1
            win._tick()
            for _ in range(730):
                now += 1 / 30
                win._tick()
            app.processEvents()
            win.grab().save(str(output / "studio-demo.png"))
            win.resize(1180, 780)
            app.processEvents()
            print("Compact window:", win.size(), "minimum:", win.minimumSizeHint())
            win.grab().save(str(output / "studio-compact.png"))
            win.finish_session()
            win._page(2)
            win.resize(1440, 960)
            app.processEvents()
            win.grab().save(str(output / "studio-guide.png"))
            win.close()
            app.processEvents()
    print(f"Screenshots saved to {output}")


if __name__ == "__main__":
    main()
