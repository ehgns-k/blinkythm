"""Finds blinks in an eye-openness (EAR) time series. Pure logic, no camera or UI."""
from collections import deque

import numpy as np

DEFAULT_OPEN_EAR = 0.28
CLOSE_RATIO = 0.72      # below 72% of normal openness = closing
OPEN_RATIO = 0.85       # above 85% = open again
CONFIRM_FRAMES = 2      # frames below the threshold needed to accept a blink
MIN_OPEN_GAP = 0.08     # minimum gap after the previous blink (s), filters flutter
MIN_BLINK = 0.04
MAX_BLINK = 0.80        # longer closures count as resting the eyes, not blinks
BASELINE_WINDOW = 30.0


class BlinkDetector:
    """Call feed(t, ear) every frame. ear=None means no face.

    on_close(onset_t)           : called as soon as a closing is confirmed (game input).
                                  onset_t is interpolated between frames at the threshold crossing.
    on_blink(onset_t, duration) : called after the eye opens again (statistics). Too short or long is skipped.
    """

    def __init__(self, on_close=None, on_blink=None):
        self.on_close = on_close
        self.on_blink = on_blink
        self.closed = False
        self.baseline = DEFAULT_OPEN_EAR
        self._samples = deque()          # (t, ear) samples while the eye is open
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
            # face lost: drop the blink in progress
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
                        self._armed = False      # treat as flutter and drop it
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
