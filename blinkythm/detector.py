"""EAR(눈 뜸 정도) 시계열에서 깜빡임을 찾아내는 순수 로직. 카메라/UI와 무관."""
from collections import deque

import numpy as np

DEFAULT_OPEN_EAR = 0.28
CLOSE_RATIO = 0.72      # 평소 눈 뜸 정도의 72% 아래로 내려가면 "감는 중"
OPEN_RATIO = 0.85       # 85% 위로 올라오면 "다시 뜸"
CONFIRM_FRAMES = 2      # 연속 몇 프레임 아래여야 깜빡임으로 인정하는지
MIN_OPEN_GAP = 0.08     # 직전 깜빡임이 끝난 뒤 최소 간격(초): 떨림 제거
MIN_BLINK = 0.04
MAX_BLINK = 0.80        # 이보다 길게 감으면 깜빡임이 아니라 "눈 감음"으로 취급
BASELINE_WINDOW = 30.0


class BlinkDetector:
    """feed(t, ear)를 프레임마다 호출한다. ear가 None이면 얼굴 없음.

    on_close(onset_t)           : 감기 시작이 확정되는 즉시 호출(게임 입력용).
                                  onset_t는 임계값을 가로지른 시각을 프레임 사이에서 보간한 값.
    on_blink(onset_t, duration) : 눈을 다시 뜬 뒤 호출(통계용). 너무 짧거나 긴 것은 제외.
    """

    def __init__(self, on_close=None, on_blink=None):
        self.on_close = on_close
        self.on_blink = on_blink
        self.closed = False
        self.baseline = DEFAULT_OPEN_EAR
        self._samples = deque()          # (t, ear) 눈을 뜬 상태의 표본
        self._since_base = 0
        self._below = 0
        self._cand_onset = None
        self._armed = True
        self._onset = None
        self._last_reopen = -1e9
        self._prev = None
        self.ear = None

    @property
    def close_thr(self):
        return self.baseline * CLOSE_RATIO

    @property
    def open_thr(self):
        return self.baseline * OPEN_RATIO

    def _update_baseline(self, t, ear):
        self._samples.append((t, ear))
        while self._samples and t - self._samples[0][0] > BASELINE_WINDOW:
            self._samples.popleft()
        self._since_base += 1
        if self._since_base >= 15 and len(self._samples) >= 30:
            self._since_base = 0
            vals = np.fromiter((e for _, e in self._samples), float)
            self.baseline = float(np.percentile(vals, 80))

    def feed(self, t, ear):
        self.ear = ear
        if ear is None:
            # 얼굴을 놓침: 진행 중인 판정은 버린다
            self._below = 0
            self._cand_onset = None
            self._prev = None
            self.closed = False
            self._armed = True
            return
        thr = self.close_thr
        if not self.closed:
            if ear >= thr:
                self._below = 0
                self._cand_onset = None
                self._armed = True
                self._update_baseline(t, ear)
            elif self._armed:
                self._below += 1
                if self._below == 1:
                    if self._prev is not None and self._prev[1] > ear:
                        pt, pe = self._prev
                        frac = (pe - thr) / (pe - ear) if pe > thr else 0.0
                        self._cand_onset = pt + max(0.0, min(1.0, frac)) * (t - pt)
                    else:
                        self._cand_onset = t
                if self._below >= CONFIRM_FRAMES:
                    if self._cand_onset - self._last_reopen < MIN_OPEN_GAP:
                        self._armed = False      # 떨림으로 보고 버림
                        self._below = 0
                    else:
                        self.closed = True
                        self._onset = self._cand_onset
                        if self.on_close:
                            self.on_close(self._onset)
        else:
            if ear > self.open_thr:
                dur = t - self._onset
                self.closed = False
                self._below = 0
                self._last_reopen = t
                if MIN_BLINK <= dur <= MAX_BLINK and self.on_blink:
                    self.on_blink(self._onset, dur)
        self._prev = (t, ear)
