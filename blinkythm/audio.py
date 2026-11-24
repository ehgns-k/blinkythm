"""소리: assets/sounds의 WAV를 읽어 한 판 전체를 미리 합성해 재생하고, 판정 소리는 따로 낸다.

반주와 신호음을 한 버퍼로 미리 섞어 한 번에 재생하므로, 화면 갱신이 늦어도 박자가 흔들리지 않는다.
버퍼 합성(render_*)은 pygame 없이도 동작하므로 시험에서 그대로 쓴다.
"""
import os
import sys
import time
import wave

import numpy as np

SR = 44100

try:
    import pygame
    _HAVE_PYGAME = True
except Exception:       # pragma: no cover
    pygame = None
    _HAVE_PYGAME = False


def assets_dir():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")


def load_wav(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != SR:
            raise ValueError("44.1kHz 16비트 WAV만 지원합니다: %s" % path)
        raw = w.readframes(w.getnframes())
        ch = w.getnchannels()
    y = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        y = y.reshape(-1, ch).mean(axis=1)
    return y


class SampleBank:
    """이름 -> 샘플(numpy). 처음 쓸 때 읽어 둔다."""

    def __init__(self, folder=None):
        self.folder = folder or os.path.join(assets_dir(), "sounds")
        self._cache = {}

    def path(self, name):
        return os.path.join(self.folder, name + ".wav")

    def get(self, name):
        if name not in self._cache:
            try:
                self._cache[name] = load_wav(self.path(name))
            except (OSError, ValueError, EOFError):
                self._cache[name] = np.zeros(1)
        return self._cache[name]


def _mix_into(buf, y, at_sec, gain=1.0):
    i = int(round(at_sec * SR))
    if i < 0:
        y, i = y[-i:], 0
    j = min(len(buf), i + len(y))
    if i < len(buf):
        buf[i:j] += y[: j - i] * gain


def render_stage(stage, bank):
    """한 판의 음원: 4박 세기 -> 반주 루프 반복 + 신호음 -> 마무리 화음."""
    bs = stage.beat_sec
    from .stages import COUNT_IN
    buf = np.zeros(int((stage.total_beats * bs + 1.6) * SR))
    for b in range(COUNT_IN):
        _mix_into(buf, bank.get("count_accent" if b == 0 else "count"), b * bs, 0.8)
    loop = bank.get(stage.loop)
    loop_beats = 8
    b = COUNT_IN
    while b < stage.length:
        # 루프 시작 위치를 매번 박 단위로 다시 계산하므로 반올림 오차가 쌓이지 않는다
        seg = loop[: int(round(min(loop_beats, stage.length - b) * bs * SR))]
        _mix_into(buf, seg, b * bs)
        b += loop_beats
    _mix_into(buf, bank.get("finish"), stage.length * bs, 0.9)
    for c in stage.cues:
        _mix_into(buf, bank.get(c.sound), c.beat * bs)
    peak = float(np.max(np.abs(buf))) if len(buf) else 0.0
    if peak > 0.95:                 # 겹친 소리로 찌그러지지 않게 전체를 살짝 낮춘다
        buf *= 0.95 / peak
    return buf


def render_clicks(ticks, total_sec, bank):
    """보정 마법사용 메트로놈. ticks: [(초, 강박 여부)]"""
    buf = np.zeros(int((total_sec + 0.5) * SR))
    for s, acc in ticks:
        _mix_into(buf, bank.get("count_accent" if acc else "count"), s, 0.8)
    return buf


def to_bytes(y, volume=1.0):
    return (np.clip(y * volume, -1, 1) * 32767).astype("<i2").tobytes()


class Audio:
    def __init__(self, volume=0.7):
        self.volume = volume
        self.ok = False
        self.bank = SampleBank()
        self._sfx = {}
        if not _HAVE_PYGAME:
            return
        try:
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            self.ok = True
        except Exception:
            self.ok = False

    def _sound(self, y, gain=1.0):
        return pygame.mixer.Sound(buffer=to_bytes(y, self.volume * gain))

    def prepare(self, names):
        """판정 중에 바로 낼 효과음을 미리 만든다(현재 음량 반영)."""
        if not self.ok:
            return
        self._sfx = {}
        for n in names:
            self._sfx[n] = self._sound(self.bank.get(n))
            self._sfx[n + "@soft"] = self._sound(self.bank.get(n), 0.45)

    def play_sfx(self, name, soft=False):
        if self.ok:
            snd = self._sfx.get(name + ("@soft" if soft else ""))
            if snd is not None:
                snd.play()

    def play_buffer(self, buf):
        """버퍼 재생을 시작하고 재생 직전 시각을 돌려준다(소리를 낼 수 없으면 None)."""
        if not self.ok:
            return None
        snd = self._sound(buf)
        t0 = time.perf_counter()
        snd.play()
        return t0

    def play_stage(self, stage):
        return self.play_buffer(render_stage(stage, self.bank))

    def play_track(self, ticks, cues, total_sec):
        """보정 마법사용(cues는 쓰지 않음). 재생 직전 시각을 돌려준다."""
        return self.play_buffer(render_clicks(ticks, total_sec, self.bank))

    def play_jingle(self, name):
        if self.ok:
            self._sound(self.bank.get(name)).play()

    def stop(self):
        if self.ok:
            pygame.mixer.stop()
