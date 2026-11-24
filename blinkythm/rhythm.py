"""Judging, scoring and latency calibration (pure logic). Charts live in stages.py."""
import statistics
from dataclasses import dataclass
from typing import Optional

# Grades
PERFECT, GOOD, OK, MISS = "perfect", "good", "ok", "miss"
GRADES = (PERFECT, GOOD, OK, MISS)
POINTS = {PERFECT: 100, GOOD: 75, OK: 40, MISS: 0}
LABEL = {PERFECT: "Perfect", GOOD: "Good", OK: "Close", MISS: "Miss"}

# Judgement windows (seconds, +/- around the note).
# A 30 fps webcam has 33 ms between frames, and people vary a lot when timing a blink on purpose,
# so the windows are much wider than in a keyboard rhythm game. Slow cameras get extra slack.
WINDOWS = {PERFECT: 0.070, GOOD: 0.130, OK: 0.200}
# Blink events arrive a few frames after the eye starts closing, so a miss is only final after this delay.
MISS_GRACE = 0.18


@dataclass
class Cue:
    """A sound or motion that sets the beat. The player sees or hears it, then blinks at the Note time."""
    beat: float            # position in beats from the start of the track
    sound: str             # file name in assets/sounds, without extension
    actor: str             # what moves in the scene
    time: float = 0.0      # absolute time (perf_counter)


@dataclass
class Note:
    idx: int
    beat: float            # position in beats from the start of the track
    section: int = 0       # section index used for feedback
    reveal: float = 0.0    # beat after which the guide shows this note (hidden until its cue plays)
    actor: str = ""
    time: float = 0.0


@dataclass
class Result:
    note: Note
    grade: str
    dt: Optional[float]    # input minus note, seconds. Positive = late. None for a miss


def frame_slack(frame_dt):
    """Extra window (seconds) for cameras slower than 30 fps."""
    return max(0.0, frame_dt - 1 / 30) * 0.5


class Judge:
    def __init__(self, notes, t0, beat_sec, offset=0.0, slack=0.0):
        self.notes = notes
        for n in self.notes:
            n.time = t0 + n.beat * beat_sec
        self.offset = offset
        self.slack = slack
        self.win = {k: v + slack for k, v in WINDOWS.items()}
        self.matched = [None] * len(self.notes)    # Result or None
        self.results = []
        self.stray = []                            # blink times that matched no note
        self.combo = 0
        self.best_combo = 0

    def grade_of(self, dt):
        a = abs(dt)
        for g in (PERFECT, GOOD, OK):
            if a <= self.win[g]:
                return g
        return MISS

    def _record(self, res):
        self.results.append(res)
        if res.grade == MISS:
            self.combo = 0
        else:
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)

    def on_blink(self, onset):
        """Judge a blink from its onset time (camera clock). Returns None if no note matches."""
        t = onset - self.offset
        best, best_abs = None, None
        for i, n in enumerate(self.notes):
            if self.matched[i] is not None:
                continue
            d = abs(t - n.time)
            if d <= self.win[OK] and (best_abs is None or d < best_abs):
                best, best_abs = i, d
        if best is None:
            self.stray.append(t)
            return None
        n = self.notes[best]
        dt = t - n.time
        res = Result(n, self.grade_of(dt), dt)
        self.matched[best] = res
        self._record(res)
        return res

    def poll(self, now):
        """Mark notes that passed without any input as misses."""
        out = []
        for i, n in enumerate(self.notes):
            if self.matched[i] is None and now > n.time + self.win[OK] + MISS_GRACE:
                res = Result(n, MISS, None)
                self.matched[i] = res
                self._record(res)
                out.append(res)
        return out

    @property
    def finished(self):
        return all(m is not None for m in self.matched)

    def running_accuracy(self):
        done = [m for m in self.matched if m is not None]
        if not done:
            return None
        return sum(POINTS[r.grade] for r in done) / (100.0 * len(done)) * 100

    # --- summary -------------------------------------------------------------
    def summary(self, n_sections=1):
        done = [m for m in self.matched if m is not None]
        counts = {g: sum(1 for r in done if r.grade == g) for g in GRADES}
        total = len(self.notes)
        dts = [r.dt for r in done if r.dt is not None]
        sections = []
        for s in range(n_sections):
            rs = [m for m in done if m.note.section == s]
            ns = sum(1 for n in self.notes if n.section == s)
            sections.append(accuracy_of(rs, ns))
        return make_summary(counts, total, dts, len(self.stray), self.best_combo, sections)


def accuracy_of(results, total):
    if not total:
        return None
    return sum(POINTS[r.grade] for r in results) / (100.0 * total) * 100


def make_summary(counts, total, dts, stray, best_combo, sections=()):
    acc = sum(POINTS[g] * counts[g] for g in GRADES) / (100.0 * total) * 100 if total else 0.0
    return {
        "counts": counts, "accuracy": acc, "total": total,
        "mean_dt": statistics.fmean(dts) if dts else None,
        "sd": statistics.pstdev(dts) if len(dts) > 1 else None,
        "dts": list(dts), "stray": stray, "best_combo": best_combo,
        "sections": list(sections), "rank": rank_of(acc),
        "no_miss": total > 0 and counts[MISS] == 0,
    }


def combine(summaries):
    """Medley: merge several summaries (per-game accuracy instead of sections)."""
    counts = {g: sum(s["counts"][g] for s in summaries) for g in GRADES}
    total = sum(s["total"] for s in summaries)
    dts = [d for s in summaries for d in s["dts"]]
    out = make_summary(counts, total, dts, sum(s["stray"] for s in summaries),
                       max((s["best_combo"] for s in summaries), default=0),
                       [s["accuracy"] for s in summaries])
    return out


# Stamp names and thresholds. Even the lowest one is not a scolding.
RANKS = [(85, "Superb"), (65, "Nice"), (40, "Good"), (0, "Rested")]


def rank_of(acc):
    for lo, name in RANKS:
        if acc >= lo:
            return name
    return RANKS[-1][1]


def rank_level(acc):
    """0 (best) to 3. Picks the result jingle."""
    for i, (lo, _) in enumerate(RANKS):
        if acc >= lo:
            return i
    return len(RANKS) - 1


def feedback(summary, names):
    """One or two lines of feedback from section accuracy. names: section (or game) names."""
    secs = [(a, n) for a, n in zip(summary["sections"], names) if a is not None]
    if summary["total"] and summary["counts"][MISS] == summary["total"]:
        return ["Hardly any blinks were detected. Check your face position and lighting."]
    lines = []
    if summary["no_miss"]:
        lines.append("No misses at all.")
    if len(secs) >= 2:
        best = max(secs)
        worst = min(secs)
        if best[0] - worst[0] >= 15:
            if best[0] >= 65:
                lines.append("\"%s\" went especially well." % best[1])
            lines.append("Try \"%s\" a few more times." % worst[1])
        elif summary["accuracy"] >= 65:
            lines.append("Even timing from start to finish.")
    m = summary["mean_dt"]
    if m is not None and abs(m) >= 0.06:
        lines.append("Overall you blinked a little %s." % ("late" if m > 0 else "early"))
    return lines[:3] or ["Count the beats in your head while you wait for the cue."]


def suggest_offset_shift(summary, min_hits=10, min_shift=0.030):
    """Suggest a calibration change (seconds) if the timing leans to one side, else None."""
    dts = summary["dts"]
    if len(dts) < min_hits or summary["mean_dt"] is None:
        return None
    med = statistics.median(dts)
    return med if abs(med) >= min_shift else None


# --- calibration -------------------------------------------------------------
CAL_BPM = 90.0
CAL_BEAT = 60.0 / CAL_BPM
CAL_TICKS = 12
CAL_SKIP = 4                 # the first 4 ticks are for listening


def compute_offset(onsets, t0):
    """Estimate input delay from blinks timed to the calibration metronome.

    People react to sound, so input usually lands after the beat. Fold by the beat period and take the median.
    Returns (offset seconds, standard deviation, samples used) or None.
    """
    lo = -0.20
    ds = []
    for o in onsets:
        rel = o - t0 - CAL_SKIP * CAL_BEAT
        if rel < -0.2:
            continue
        ds.append(((rel - lo) % CAL_BEAT) + lo)
    if len(ds) < 5:
        return None
    med = statistics.median(ds)
    good = [d for d in ds if abs(d - med) <= 0.12]
    if len(good) < 5:
        return None
    sd = statistics.pstdev(good)
    if sd > 0.09:
        return None
    return statistics.median(good), sd, len(good)
