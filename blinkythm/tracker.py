"""Webcam -> eye openness (EAR) -> BlinkDetector. Frames stay in memory and are never saved or sent."""
import sys
import threading
import time

from .detector import BlinkDetector

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
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=False,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
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
                period = 1.0 / (GAME_FPS if self.game_mode else MONITOR_FPS)
                if t - last_proc < period * 0.9:
                    continue
                last_proc = t
                if last_t is not None:
                    self.frame_dt = 0.9 * self.frame_dt + 0.1 * (t - last_t)
                last_t = t
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                res = mesh.process(rgb)
                ear = None
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    h, w = rgb.shape[:2]
                    a = _ear(lm, RIGHT_EYE, w, h)
                    b = _ear(lm, LEFT_EYE, w, h)
                    if a is not None and b is not None:
                        ear = (a + b) / 2.0
                self.face_visible = ear is not None
                self.detector.feed(t, ear)
                self.monitor.on_frame(t, ear is not None)
        finally:
            cap.release()
            mesh.close()


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
        self._on_close(now + self._latency)
        self._on_blink(now, 0.12)

    @property
    def eye_closed(self):
        return time.perf_counter() < self._close_until

    @property
    def ear_ratio(self):
        return 0.2 if self.eye_closed else 1.0

    def _run(self):
        while not self._stop.is_set():
            self.monitor.on_frame(time.perf_counter(), True)
            time.sleep(1 / 15)
