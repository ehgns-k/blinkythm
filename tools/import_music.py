"""Import the music listed in assets/music/music.json from a folder of source WAV files.

    python tools/import_music.py SOURCE_DIR

For each role in the manifest this
  - reads SOURCE_DIR/<source>,
  - for game songs ("kind": "stage"), finds the exact tempo, the beat grid and the first downbeat,
    and checks that the tempo does not drift between the two halves of the song,
  - evens out loudness (RMS) per kind and keeps the peak below clipping,
  - writes assets/music/<role>.ogg (needs ffmpeg with libvorbis on PATH),
and stores the measured values back in the manifest. To use another song for a role, change its
"source" and run the script again. A role with "bpm_locked": true keeps the tempo written in the manifest.
"""
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
MANIFEST = os.path.join(MUSIC_DIR, "music.json")
SR = 44100
FR = 100.0                                    # onset envelope rate (frames per second)
RMS_TARGET_DB = {"stage": -21.0, "bgm": -21.0, "jingle": -18.0}
STAGE_KEEP_BEATS = 80                         # game songs are trimmed to this many beats after the downbeat


def load(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != SR:
            raise SystemExit("%s: only 44.1 kHz 16-bit WAV is supported" % path)
        ch = w.getnchannels()
        y = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768.0
    y = y.reshape(-1, ch)
    if ch == 1:
        y = np.repeat(y, 2, axis=1)
    return y[:, :2]


def onset_env(mono, low_only=False):
    """Spectral flux at 100 frames per second. low_only keeps the kick-drum range."""
    n, hop = 2048, int(SR / FR)
    frames = 1 + (len(mono) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * np.hanning(n), axis=1))
    if low_only:
        spec = spec[:, : int(150 * n / SR)]
    spec = np.log1p(1000 * spec)
    flux = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
    k = int(FR)                                # remove the slow trend (1 s moving average)
    trend = np.convolve(flux, np.ones(k) / k, mode="same")
    env = np.maximum(0.0, flux - trend)
    return env / (env.max() or 1.0)


def coarse_bpm(env, lo=60, hi=180):
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    best = (None, -1.0)
    for bpm in np.arange(lo, hi, 0.5):
        lag = FR * 60 / bpm
        s = sum(np.interp(k * lag, np.arange(len(ac)), ac) for k in (1, 2, 4))
        if s > best[1]:
            best = (bpm, s)
    return best[0]


def grid_score(env, bpm, phases):
    period = FR * 60 / bpm
    beats = np.arange(0, (len(env) - 1 - period) / period)
    pos = phases[:, None] + beats[None, :] * period
    return np.interp(pos, np.arange(len(env)), env).mean(axis=1)


def fit_grid(env, bpm_guess, span=0.04, step=0.01):
    """Best (bpm, phase in seconds) near bpm_guess, by how strongly onsets line up on the grid."""
    best = (None, None, -1.0)
    for bpm in np.arange(bpm_guess * (1 - span), bpm_guess * (1 + span), step):
        period = FR * 60 / bpm
        phases = np.arange(0, period, 0.25)
        sc = grid_score(env, bpm, phases)
        i = int(np.argmax(sc))
        if sc[i] > best[2]:
            best = (float(bpm), float(phases[i] / FR), float(sc[i]))
    return best


def phase_at(env, bpm):
    period = FR * 60 / bpm
    phases = np.arange(0, period, 0.25)
    return float(phases[int(np.argmax(grid_score(env, bpm, phases)))] / FR)


def analyse_stage(y, target_bpm):
    mono = y.mean(axis=1)
    env = onset_env(mono)
    guess = coarse_bpm(env)
    # pick the octave (x2, /2) closest to the tempo the game was designed for
    guess = min((guess / 2, guess, guess * 2), key=lambda b: abs(b - target_bpm))
    bpm, phase, score = fit_grid(env, guess, span=0.05, step=0.05)
    bpm, phase, score = fit_grid(env, bpm, span=0.004, step=0.005)
    beat = 60.0 / bpm
    # drift: the grid phase measured separately in each half must agree
    half = len(env) // 2
    p1 = phase_at(env[:half], bpm)
    p2 = phase_at(env[half:], bpm)
    shift = ((half / FR + p2 - p1) % beat)
    drift = min(shift, beat - shift)
    # downbeat: the beat of the bar with the strongest kick
    low = onset_env(mono, low_only=True)
    period = FR * beat
    nbeats = int((len(low) - 1 - phase * FR) / period)
    pos = phase * FR + np.arange(nbeats) * period
    kick = np.interp(pos, np.arange(len(low)), low)
    bar_pos = max(range(4), key=lambda j: kick[j::4].mean())
    first_downbeat = phase + bar_pos * beat
    # fine-tune: fold all onsets over the beat and move to the exact peak (within 1/16 beat)
    t = np.arange(len(env)) / FR
    best = (0.0, -1.0)
    for d in np.linspace(-beat / 16, beat / 16, 33):
        ph = ((t - first_downbeat - d) / beat + 0.5) % 1.0 - 0.5
        v = env[np.abs(ph) < 1 / 64].mean()
        if v > best[1]:
            best = (d, v)
    first_downbeat += best[0]
    return {"bpm": round(bpm, 3), "first_downbeat": round(first_downbeat, 4),
            "grid_strength": round(score, 3), "drift_ms": round(drift * 1000, 1)}


def normalise(y, kind):
    rms = float(np.sqrt(np.mean(y ** 2))) or 1e-9
    target = 10 ** (RMS_TARGET_DB[kind] / 20)
    g = target / rms
    peak = float(np.abs(y).max()) * g
    if peak > 0.95:
        g *= 0.95 / peak
    return y * g, round(20 * np.log10(g), 2)


def write_ogg(y, path):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "x.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libvorbis", "-q:a", "5", path], check=True)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    src_dir = argv[1]
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    for role, info in manifest["roles"].items():
        y = load(os.path.join(src_dir, info["source"]))
        kind = info["kind"]
        if kind == "stage":
            if not info.get("bpm_locked"):
                info.update(analyse_stage(y, info["target_bpm"]))
            end = info["first_downbeat"] + STAGE_KEEP_BEATS * 60.0 / info["bpm"]
            y = y[: int(min(len(y), end * SR))]
        y, gain = normalise(y, kind)
        info["gain_db"] = gain
        info["seconds"] = round(len(y) / SR, 2)
        info["file"] = role + ".ogg"
        write_ogg(y, os.path.join(MUSIC_DIR, info["file"]))
        extra = "" if kind != "stage" else "  %.3f BPM, downbeat %.3f s, drift %.1f ms, grid %.2f" % (
            info["bpm"], info["first_downbeat"], info["drift_ms"], info.get("grid_strength", 0))
        print("%-18s <- %-28s %6.1f s%s" % (role, info["source"], info["seconds"], extra))
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
