"""Download the official Google MediaPipe pose model, once."""
from pathlib import Path
from urllib.request import urlopen

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def main():
    target = Path(__file__).parent / "models/pose_landmarker_lite.task"
    target.parent.mkdir(exist_ok=True)
    if target.is_file():
        print(f"Already downloaded: {target}")
        return
    temporary = target.with_suffix(".download")
    try:
        with urlopen(URL, timeout=60) as source, temporary.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Downloaded: {target}")


if __name__ == "__main__":
    main()
