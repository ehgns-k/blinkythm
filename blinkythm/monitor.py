"""화면 사용 시간 + 깜빡임 빈도를 보고 게임 프롬프트를 띄울지 결정한다(순수 로직)."""
import threading
from collections import deque

RATE_WINDOW = 60.0
MIN_VISIBLE = 40.0      # 최근 60초 중 얼굴이 이만큼은 보여야 빈도를 신뢰


class UsageMonitor:
    def __init__(self, settings):
        self.s = settings
        self._lock = threading.Lock()
        self._last_t = None
        self._last_seen = None
        self._screen_since = None
        self._visible = deque()     # (t, dt)
        self._blinks = deque()
        self._snooze_until = 0.0
        self.paused = False
        self.suppressed_today = False

    # --- 입력(트래커 스레드) -------------------------------------------------
    def on_frame(self, t, visible):
        with self._lock:
            dt = 0.0 if self._last_t is None else min(max(t - self._last_t, 0.0), 1.0)
            self._last_t = t
            if self.paused:
                return
            if visible:
                self._last_seen = t
                if self._screen_since is None:
                    self._screen_since = t
                self._visible.append((t, dt))
            elif self._last_seen is not None and t - self._last_seen > self.s.away_seconds:
                self._screen_since = None
                self._blinks.clear()
                self._visible.clear()
            self._trim(t)

    def on_blink(self, t):
        with self._lock:
            if not self.paused:
                self._blinks.append(t)

    def _trim(self, t):
        while self._visible and t - self._visible[0][0] > RATE_WINDOW:
            self._visible.popleft()
        while self._blinks and t - self._blinks[0] > RATE_WINDOW:
            self._blinks.popleft()

    # --- 조회 ----------------------------------------------------------------
    def screen_seconds(self, now):
        with self._lock:
            return 0.0 if self._screen_since is None else max(0.0, now - self._screen_since)

    def blink_rate(self, now):
        """최근 1분 기준 분당 깜빡임. 데이터가 부족하면 None."""
        with self._lock:
            self._trim(now)
            vis = sum(dt for _, dt in self._visible)
            if vis < MIN_VISIBLE:
                return None
            return len(self._blinks) / vis * 60.0

    def should_prompt(self, now, dnd=False):
        if self.paused or self.suppressed_today or dnd or now < self._snooze_until:
            return False
        if self.screen_seconds(now) < self.s.screen_minutes * 60.0:
            return False
        rate = self.blink_rate(now)
        return rate is not None and rate < self.s.blink_threshold

    # --- 사용자 응답 ---------------------------------------------------------
    def snooze(self, now, minutes=None):
        self._snooze_until = now + 60.0 * (minutes if minutes is not None else self.s.snooze_minutes)

    def mark_played(self, now):
        with self._lock:
            self._screen_since = now        # 눈을 쉬었으니 사용 시간 초기화
            self._blinks.clear()
            self._visible.clear()
        self._snooze_until = now + 60.0 * self.s.cooldown_minutes
