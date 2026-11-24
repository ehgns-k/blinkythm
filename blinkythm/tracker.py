"""웹캠 -> 눈 뜸 정도(EAR) -> BlinkDetector. 영상은 메모리에서만 처리하고 저장/전송하지 않는다."""
import sys
import threading
import time

from .detector import BlinkDetector

# MediaPipe FaceMesh 눈 랜드마크 (p1, p2, p3, p4, p5, p6)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)

MONITOR_FPS = 15.0      # 평소(백그라운드) 처리 속도
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
    """UI가 쓰는 공통 인터페이스."""

    def __init__(self, monitor):
        self.monitor = monitor
        self.detector = BlinkDetector(self._on_close, self._on_blink)
        self.game_mode = False
        self.face_visible = False
        self.error = None
        self.frame_dt = 1 / 30           # 최근 프레임 간격(초)
        self._listeners = []
        self._lock = threading.Lock()

    # 감기 시작 이벤트 구독: cb(onset_time)
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
        """0(감김)~1(평소 뜬 상태) 정도로 정규화한 값. 표시용."""
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
            self.error = "필요한 라이브러리를 불러오지 못했습니다: %s" % e
            return
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            self.error = "카메라 %d번을 열 수 없습니다. 다른 프로그램이 사용 중이거나 개인정보 설정에서 차단되었을 수 있습니다." % self.camera_index
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
                t = time.perf_counter()        # 프레임을 받은 시각. 장치 지연은 보정 마법사가 흡수
                if not ok:
                    fails += 1
                    if fails > 60:
                        self.error = "카메라에서 영상을 받지 못했습니다."
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
    """카메라 없이 UI/판정을 시험하기 위한 가짜 트래커. 게임 창에서 스페이스바 = 깜빡임."""

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
        """스페이스 입력: 감기 시작 이벤트를 흉내 낸다."""
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
