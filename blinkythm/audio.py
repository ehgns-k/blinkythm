"""효과음은 전부 코드로 합성한다(외부 음원 파일 불필요)."""
import os
import numpy as np

SR = 44100
_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

try:
    import pygame
    _HAVE_PYGAME = True
except Exception:       # pragma: no cover
    pygame = None
    _HAVE_PYGAME = False


def _env(n, attack=0.004, decay=6.0):
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def tone(freq, dur, decay=18.0, harm=(1.0, 0.35, 0.15), gain=0.5):
    n = int(SR * dur)
    t = np.arange(n) / SR
    y = sum(a * np.sin(2 * np.pi * freq * (i + 1) * t) for i, a in enumerate(harm))
    return y / sum(harm) * _env(n, decay=decay) * gain


def synth_tick(accent=False):
    return tone(1500 if accent else 1000, 0.05, decay=60, harm=(1.0,), gain=0.45 if accent else 0.28)


def synth_cue():
    return tone(587.0, 0.16, decay=14)               # 듣기 단계: 따라 해야 할 소리


def synth_hit(grade):
    if grade == "perfect":
        return tone(880.0, 0.12, decay=20, gain=0.4)
    if grade == "good":
        return tone(698.0, 0.10, decay=22, gain=0.32)
    if grade == "ok":
        return tone(440.0, 0.09, decay=26, gain=0.25)
    return tone(180.0, 0.12, decay=24, harm=(1.0, 0.6), gain=0.2)


def _to_bytes(y, volume=1.0):
    return (np.clip(y * volume, -1, 1) * 32767).astype("<i2").tobytes()


def _mix_into(buf, y, at_sec):
    i = int(at_sec * SR)
    j = min(len(buf), i + len(y))
    if i < len(buf):
        buf[i:j] += y[: j - i]


class Audio:
    def __init__(self, volume=0.7):
        self.volume = volume
        self.ok = False
        self._ch = None
        self._sounds = {}
        if not _HAVE_PYGAME:
            return
        try:
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            self.ok = True
        except Exception:
            self.ok = False

    def _sound(self, y):
        return pygame.mixer.Sound(buffer=_to_bytes(y, self.volume))

    def prepare_hits(self):
        if self.ok:
            for g in ("perfect", "good", "ok", "miss"):
                self._sounds[g] = self._sound(synth_hit(g))

    def play_hit(self, grade):
        if self.ok and grade in self._sounds:
            self._sounds[grade].play()

    def play_track(self, ticks, cues, total_sec):
        """ticks: [(sec, accent)], cues: [sec]. 전체를 한 번에 합성해 재생하므로 박자가 흔들리지 않는다.
        재생 직전 시각을 돌려준다(없으면 None)."""
        if not self.ok:
            return None
        import time
        buf = np.zeros(int((total_sec + 0.5) * SR), dtype=np.float64)
        for s, acc in ticks:
            _mix_into(buf, synth_tick(acc), s)
        for s in cues:
            _mix_into(buf, synth_cue(), s)
        snd = self._sound(buf)
        t0 = time.perf_counter()
        self._ch = snd.play()
        return t0

    def stop(self):
        if self.ok:
            pygame.mixer.stop()
