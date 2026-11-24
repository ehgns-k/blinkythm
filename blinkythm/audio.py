"""Sound: renders a whole game from the WAV files in assets/sounds and plays it, plus hit sounds on demand.

The backing loop and cue sounds are mixed into one buffer and played at once, so a slow frame cannot shift the beat.
Rendering (render_*) works without pygame, so the tests use it directly.
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
            raise ValueError("Only 44.1 kHz 16-bit WAV is supported: %s" % path)
        raw = w.readframes(w.getnframes())
        ch = w.getnchannels()
    y = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        y = y.reshape(-1, ch).mean(axis=1)
    return y


class SampleBank:
    """Name -> samples (numpy), loaded on first use."""

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
    """One game's audio: 4-beat count-in -> repeated backing loop + cues -> closing chord."""
    bs = stage.beat_sec
    from .stages import COUNT_IN
    buf = np.zeros(int((stage.total_beats * bs + 1.6) * SR))
    for b in range(COUNT_IN):
        _mix_into(buf, bank.get("count_accent" if b == 0 else "count"), b * bs, 0.8)
    loop = bank.get(stage.loop)
    loop_beats = 8
    b = COUNT_IN
    while b < stage.length:
        # Each loop start is computed from the beat again, so rounding errors do not add up
        seg = loop[: int(round(min(loop_beats, stage.length - b) * bs * SR))]
        _mix_into(buf, seg, b * bs)
        b += loop_beats
    _mix_into(buf, bank.get("finish"), stage.length * bs, 0.9)
    for c in stage.cues:
        _mix_into(buf, bank.get(c.sound), c.beat * bs)
    peak = float(np.max(np.abs(buf))) if len(buf) else 0.0
    if peak > 0.95:                 # lower the whole mix a little if overlapping sounds would clip
        buf *= 0.95 / peak
    return buf


def render_clicks(ticks, total_sec, bank):
    """Metronome for the calibration wizard. ticks: [(seconds, accented)]"""
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
        """Pre-build the sounds played during judging (at the current volume)."""
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
        """Start playing a buffer and return the time just before playback (None if there is no audio)."""
        if not self.ok:
            return None
        snd = self._sound(buf)
        t0 = time.perf_counter()
        snd.play()
        return t0

    def play_stage(self, stage):
        return self.play_buffer(render_stage(stage, self.bank))

    def play_track(self, ticks, cues, total_sec):
        """For the calibration wizard (cues are ignored). Returns the time just before playback."""
        return self.play_buffer(render_clicks(ticks, total_sec, self.bank))

    def play_jingle(self, name):
        if self.ok:
            self._sound(self.bank.get(name)).play()

    def stop(self):
        if self.ok:
            pygame.mixer.stop()
