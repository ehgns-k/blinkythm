"""Webcam -> eye openness -> BlinkDetector. Frames stay in memory and are never saved or sent.

The preferred signal is MediaPipe Face Landmarker's eyeBlink scores (a model trained for this),
read from assets/models/face_landmarker.task. Without that file the tracker falls back to the eye
aspect ratio (EAR) from FaceMesh landmarks, which reacts less to fast blinks.
"""
import os
import sys
import threading
import time

from .detector import BlinkDetector

MODEL_FILE = "face_landmarker.task"
OPEN_LEVEL_SCORES = 0.95        # typical openness (1 - blink score) with eyes open

# MediaPipe FaceMesh eye landmarks (p1, p2, p3, p4, p5, p6)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)

MONITOR_FPS = 15.0      # processing rate in the background
GAME_FPS = 30.0


def _ear(lm, idx, w, h):
    def p(i):
        return lm[i].x * w, lm[i].y * h

    def d(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    p1, p2, p3, p4, p5, p6 = (p(i) for i in idx)
    horiz = d(p1, p4)
    return (d(p2, p6) + d(p3, p5)) / (2.0 * horiz) if horiz > 1e-6 else None


class BaseTracker:
    """Interface the UI uses."""

    def __init__(self, monitor):
        self.monitor = monitor
        self.detector = BlinkDetector(self._on_close, self._on_blink)
        self.game_mode = False
        self.face_visible = False
        self.error = None
        self.frame_dt = 1 / 30           # recent frame interval (s)
        self.source = ""                 # "blink scores" or "landmarks", shown on the camera screen
        self._listeners = []
        self._lock = threading.Lock()

    # Subscribe to eye-closing events: cb(onset_time)
    def add_listener(self, cb):
        with self._lock:
            self._listeners.append(cb)

    def remove_listener(self, cb):
        with self._lock:
            if cb in self._listeners:
                self._listeners.remove(cb)

    def _on_close(self, onset):
        with self._lock:
            ls = list(self._listeners)
        for cb in ls:
            cb(onset)

    def _on_blink(self, onset, dur):
        self.monitor.on_blink(onset)

    @property
    def eye_closed(self):
        return self.detector.closed

    @property
    def ear_ratio(self):
        """Openness from 0 (closed) to about 1 (normally open). For display only."""
        e = self.detector.ear
        if e is None:
            return None
        return max(0.0, min(1.2, e / max(self.detector.baseline, 1e-6)))

    def set_game_mode(self, on):
        self.game_mode = on

    def set_sensitivity(self, level):
        self.detector.set_sensitivity(level)

    @property
    def fps(self):
        return 1.0 / max(self.frame_dt, 1e-3)

    def start(self): ...
    def stop(self): ...
    def restart(self, camera_index=None): ...


class CameraTracker(BaseTracker):
    def __init__(self, monitor, camera_index=0):
        super().__init__(monitor)
        self.camera_index = camera_index
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(target=self._run, name="tracker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def restart(self, camera_index=None):
        self.stop()
        if camera_index is not None:
            self.camera_index = camera_index
        self.start()

    def _landmarker(self, mp):
        """Face Landmarker in video mode, or None if the model file is missing or fails to load."""
        from .audio import assets_dir
        path = os.path.join(assets_dir(), "models", MODEL_FILE)
        if not os.path.isfile(path):
            return None
        try:
            from mediapipe.tasks import python as mpt
            from mediapipe.tasks.python import vision
            opts = vision.FaceLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=path),
                running_mode=vision.RunningMode.VIDEO, num_faces=1,
                output_face_blendshapes=True,
                min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5)
            return vision.FaceLandmarker.create_from_options(opts)
        except Exception:
            return None

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
        except Exception as e:
            self.error = "Could not load a required library: %s" % e
            return
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            self.error = "Cannot open camera %d. Another app may be using it, or privacy settings may block it." % self.camera_index
            return
        # MJPG lets most webcams deliver 30 fps at this size over USB; a 1-frame buffer keeps latency low.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        landmarker = self._landmarker(mp)
        mesh = None
        if landmarker is not None:
            self.source = "blink scores"
            self.detector.reset_baseline(OPEN_LEVEL_SCORES)
        else:
            self.source = "landmarks"
            mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)
        t_start = time.perf_counter()
        last_ms = -1
        last_proc = 0.0
        last_t = None
        fails = 0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                t = time.perf_counter()        # time the frame arrived; device delay is covered by calibration
                if not ok:
                    fails += 1
                    if fails > 60:
                        self.error = "No video from the camera."
                        break
                    time.sleep(0.02)
                    continue
                fails = 0
                # In the background a lower rate is enough; in games and setup every frame counts.
                if not self.game_mode and t - last_proc < 1.0 / MONITOR_FPS - 0.01:
                    continue
                last_proc = t
                if last_t is not None:
                    self.frame_dt = 0.9 * self.frame_dt + 0.1 * (t - last_t)
                last_t = t
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                openness = None
                if landmarker is not None:
                    ms = max(last_ms + 1, int((t - t_start) * 1000))
                    last_ms = ms
                    res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
                    if res.face_blendshapes:
                        sc = {c.category_name: c.score for c in res.face_blendshapes[0]}
                        blink = (sc.get("eyeBlinkLeft", 0.0) + sc.get("eyeBlinkRight", 0.0)) / 2.0
                        openness = 1.0 - blink
                else:
                    rgb.flags.writeable = False
                    res = mesh.process(rgb)
                    if res.multi_face_landmarks:
                        lm = res.multi_face_landmarks[0].landmark
                        h, w = rgb.shape[:2]
                        a = _ear(lm, RIGHT_EYE, w, h)
                        b = _ear(lm, LEFT_EYE, w, h)
                        if a is not None and b is not None:
                            openness = (a + b) / 2.0
                self.face_visible = openness is not None
                self.detector.feed(t, openness)
                self.monitor.on_frame(t, openness is not None)
        finally:
            cap.release()
            if mesh is not None:
                mesh.close()
            if landmarker is not None:
                landmarker.close()


class SimTracker(BaseTracker):
    """Fake tracker for testing the UI and judging without a camera. Space in the game window = blink."""

    def __init__(self, monitor, latency_offset=0.0):
        super().__init__(monitor)
        self.face_visible = True
        self._latency = latency_offset
        self._stop = threading.Event()
        self._thread = None
        self._close_until = 0.0

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def restart(self, camera_index=None):
        pass

    def press(self):
        """Space key: simulate the start of a blink."""
        now = time.perf_counter()
        self._close_until = now + 0.12
        self.detector.count += 1
        self.detector.marks.append(now)
        self._on_close(now + self._latency)
        self._on_blink(now, 0.12)

    @property
    def eye_closed(self):
        return time.perf_counter() < self._close_until

    @property
    def ear_ratio(self):
        return 0.2 if self.eye_closed else 1.0

    def _run(self):
        self.source = "test mode"
        while not self._stop.is_set():
            t = time.perf_counter()
            self.monitor.on_frame(t, True)
            self.detector.baseline = 1.0
            self.detector._remember(t, 0.2 if self.eye_closed else 1.0)
            time.sleep(1 / 30)
