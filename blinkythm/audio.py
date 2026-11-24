"""Sound: games, background music, jingles and effects.

A game is rendered into one stereo buffer before it starts: its song from assets/music, aligned so
that beat 0 of the chart falls on the song's first downbeat, plus the count-in and every cue sound.
It is played in one go, so a slow frame cannot shift the beat. Menu screens stream their music with
pygame's music player. Rendering (render_*) works without a sound device, so the tests use it directly.
"""
import json
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


def music_dir():
    return os.path.join(assets_dir(), "music")


_manifest = None


def music_manifest():
    """Role -> info from assets/music/music.json (file, bpm and downbeat for game songs)."""
    global _manifest
    if _manifest is None:
        try:
            with open(os.path.join(music_dir(), "music.json"), encoding="utf-8") as f:
                _manifest = json.load(f)["roles"]
        except (OSError, ValueError, KeyError):
            _manifest = {}
    return _manifest


def load_wav(path):
    """16-bit 44.1 kHz WAV -> float array of shape (n, 2)."""
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != SR:
            raise ValueError("Only 44.1 kHz 16-bit WAV is supported: %s" % path)
        raw = w.readframes(w.getnframes())
        ch = w.getnchannels()
    y = np.frombuffer(raw, dtype="<i2").astype(np.float64).reshape(-1, ch) / 32768.0
    if ch == 1:
        y = np.repeat(y, 2, axis=1)
    return y[:, :2]


def load_ogg(path):
    """Decode an OGG file with pygame's mixer -> float array of shape (n, 2)."""
    if not _HAVE_PYGAME:
        raise OSError("pygame is needed to decode %s" % path)
    if not pygame.mixer.get_init():
        pygame.mixer.init(SR, -16, 2, 512)
    a = pygame.sndarray.array(pygame.mixer.Sound(path)).astype(np.float64) / 32768.0
    if a.ndim == 1:
        a = np.repeat(a[:, None], 2, axis=1)
    return a[:, :2]


class SampleBank:
    """Effects by name (assets/sounds/*.wav) and music by role (assets/music/*.ogg), loaded on first use."""

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
                self._cache[name] = np.zeros((1, 2))
        return self._cache[name]

    def music(self, role):
        key = "music:" + role
        if key not in self._cache:
            info = music_manifest().get(role)
            try:
                self._cache[key] = load_ogg(os.path.join(music_dir(), info["file"]))
            except Exception:
                self._cache[key] = np.zeros((1, 2))
        return self._cache[key]


def _mix_into(buf, y, at_sec, gain=1.0):
    i = int(round(at_sec * SR))
    if i < 0:
        y, i = y[-i:], 0
    j = min(len(buf), i + len(y))
    if i < len(buf):
        buf[i:j] += y[: j - i] * gain


def render_stage(stage, bank):
    """One game's audio: the song from its first downbeat, the 4-beat count-in and the cues.
    Chart beat b sounds at b * beat_sec seconds into the buffer."""
    bs = stage.beat_sec
    from .stages import COUNT_IN
    total = stage.total_beats * bs
    buf = np.zeros((int((total + 0.2) * SR), 2))
    info = music_manifest().get(stage.song, {})
    song = bank.music(stage.song) if info else np.zeros((1, 2))
    start = int(round(info.get("first_downbeat", 0.0) * SR))
    seg = song[start: start + len(buf)].copy()
    if len(seg):
        fade_in = min(len(seg), int(0.03 * SR))
        seg[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
        # fade out over the tail after the last bar
        a = int(stage.length * bs * SR)
        if a < len(seg):
            seg[a:] *= np.linspace(1, 0, len(seg) - a)[:, None]
        buf[: len(seg)] += seg
    for b in range(COUNT_IN):
        _mix_into(buf, bank.get("count_accent" if b == 0 else "count"), b * bs, 0.7)
    for c in stage.cues:
        _mix_into(buf, bank.get(c.sound), c.beat * bs)
    peak = float(np.max(np.abs(buf))) if len(buf) else 0.0
    if peak > 0.95:                 # lower the whole mix a little if overlapping sounds would clip
        buf *= 0.95 / peak
    return buf


def render_clicks(ticks, total_sec, bank):
    """Metronome for calibration. ticks: [(seconds, accented)]"""
    buf = np.zeros((int((total_sec + 0.5) * SR), 2))
    for s, acc in ticks:
        _mix_into(buf, bank.get("count_accent" if acc else "count"), s, 0.8)
    return buf


def to_bytes(y, volume=1.0):
    """Float samples (n, 2) -> interleaved 16-bit stereo bytes."""
    return np.ascontiguousarray(np.clip(y * volume, -1, 1) * 32767).astype("<i2").tobytes()


class Audio:
    def __init__(self, volume=0.7):
        self.volume = volume
        self.ok = False
        self.bank = SampleBank()
        self._sfx = {}
        self._music_role = None
        self._loop = None
        if not _HAVE_PYGAME:
            return
        try:
            pygame.mixer.pre_init(SR, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(1)       # channel 0 is kept for looping tracks
            self.ok = True
        except Exception:
            self.ok = False

    def _sound(self, y, gain=1.0):
        return pygame.mixer.Sound(buffer=to_bytes(y, self.volume * gain))

    def set_volume(self, v):
        self.volume = v
        if self.ok:
            pygame.mixer.music.set_volume(v)

    def prepare(self, names):
        """Pre-build the sounds played during judging (at the current volume)."""
        if not self.ok:
            return
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

    def play_loop(self, buf):
        """Loop a buffer without gaps until stop() (calibration metronome).
        Returns the time just before playback, or None without audio."""
        if not self.ok:
            return None
        snd = self._sound(buf)
        self._loop = snd                     # keep a reference while it plays
        ch = pygame.mixer.Channel(0)
        t0 = time.perf_counter()
        ch.play(snd, loops=-1)
        return t0

    def play_stage(self, stage):
        self.music(None, fade_ms=0)
        return self.play_buffer(render_stage(stage, self.bank))

    def play_track(self, ticks, cues, total_sec):
        """Metronome buffer played once. Returns the time just before playback."""
        return self.play_buffer(render_clicks(ticks, total_sec, self.bank))

    def play_jingle(self, role):
        """A short piece from assets/music played once over everything else. Returns its length (s)."""
        if not self.ok or role not in music_manifest():
            return 0.0
        y = self.bank.music(role)
        self._sound(y).play()
        return len(y) / SR

    def music(self, role, fade_ms=500):
        """Loop a role's music in the background; None fades it out. Same role again keeps playing."""
        if not self.ok or role == self._music_role:
            return
        self._music_role = role
        info = music_manifest().get(role) if role else None
        if not info:
            pygame.mixer.music.fadeout(fade_ms) if fade_ms else pygame.mixer.music.stop()
            return
        try:
            pygame.mixer.music.load(os.path.join(music_dir(), info["file"]))
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play(-1, fade_ms=fade_ms)
        except pygame.error:
            self._music_role = None

    def stop(self):
        """Stop effects, games and the metronome (background music keeps its own state)."""
        if self.ok:
            pygame.mixer.stop()
