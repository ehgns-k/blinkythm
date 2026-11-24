"""Download MediaPipe's Face Landmarker model into assets/models/.

The tracker uses its eyeBlink scores, which catch fast blinks far better than eye landmarks.
Without the file the app still runs and falls back to landmarks. The release build runs this script.

    python tools/get_model.py
"""
import os
import sys
import urllib.request

URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "assets", "models", "face_landmarker.task")


def main():
    if os.path.isfile(DEST) and os.path.getsize(DEST) > 1_000_000:
        print("already present:", DEST)
        return 0
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    tmp = DEST + ".part"
    urllib.request.urlretrieve(URL, tmp)
    if os.path.getsize(tmp) < 1_000_000:
        os.remove(tmp)
        print("download looks wrong (too small)")
        return 1
    os.replace(tmp, DEST)
    print("saved", DEST, os.path.getsize(DEST), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
