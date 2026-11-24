"""판정, 평가, 타이밍 보정 계산(순수 로직). 채보는 stages.py에 있다."""
import statistics
from dataclasses import dataclass
from typing import Optional

# 판정 등급
PERFECT, GOOD, OK, MISS = "perfect", "good", "ok", "miss"
GRADES = (PERFECT, GOOD, OK, MISS)
POINTS = {PERFECT: 100, GOOD: 75, OK: 40, MISS: 0}
LABEL = {PERFECT: "완벽", GOOD: "좋음", OK: "아쉬움", MISS: "놓침"}

# 판정 창(초, 노트 기준 ±).
# 웹캠은 30fps면 프레임 간격이 33ms이고, 눈 감기 시작을 자발적으로 맞추는 사람의 편차도 크므로
# 키보드 리듬게임보다 훨씬 넓게 잡는다. 느린 카메라는 slack으로 추가 보정한다.
WINDOWS = {PERFECT: 0.070, GOOD: 0.130, OK: 0.200}
# 입력 이벤트는 감기 시작 후 몇 프레임이 지나서 도착하므로, 이 시간이 지나야 "놓침"으로 확정한다.
MISS_GRACE = 0.18


@dataclass
class Cue:
    """박자를 알려 주는 소리/동작. 플레이어는 이것을 보고 들은 뒤 Note 시각에 깜빡인다."""
    beat: float            # 곡 시작 기준 박 위치
    sound: str             # assets/sounds의 파일 이름(확장자 제외)
    actor: str             # 장면에서 움직일 대상
    time: float = 0.0      # 절대 시각(perf_counter)


@dataclass
class Note:
    idx: int
    beat: float            # 곡 시작 기준 박 위치
    section: int = 0       # 평가용 구간 번호
    reveal: float = 0.0    # 이 박이 지나야 가이드에 위치를 보여 준다(신호를 듣기 전에는 숨김)
    actor: str = ""
    time: float = 0.0


@dataclass
class Result:
    note: Note
    grade: str
    dt: Optional[float]    # 입력 - 노트, 초. 양수 = 늦음. 놓침이면 None


def frame_slack(frame_dt):
    """카메라가 30fps보다 느릴 때 판정 창에 더해 줄 여유(초)."""
    return max(0.0, frame_dt - 1 / 30) * 0.5


class Judge:
    def __init__(self, notes, t0, beat_sec, offset=0.0, slack=0.0):
        self.notes = notes
        for n in self.notes:
            n.time = t0 + n.beat * beat_sec
        self.offset = offset
        self.slack = slack
        self.win = {k: v + slack for k, v in WINDOWS.items()}
        self.matched = [None] * len(self.notes)    # Result 또는 None
        self.results = []
        self.stray = []                            # 어떤 노트와도 맞지 않은 깜빡임 시각
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
        """감기 시작 시각(카메라 시계)을 받아 판정. 맞는 노트가 없으면 None."""
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
        """아무 입력도 받지 못하고 지나간 노트를 놓침으로 확정."""
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

    # --- 결과 요약 -----------------------------------------------------------
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
    """메들리: 여러 게임의 요약을 하나로 합친다(구간 대신 게임별 정확도)."""
    counts = {g: sum(s["counts"][g] for s in summaries) for g in GRADES}
    total = sum(s["total"] for s in summaries)
    dts = [d for s in summaries for d in s["dts"]]
    out = make_summary(counts, total, dts, sum(s["stray"] for s in summaries),
                       max((s["best_combo"] for s in summaries), default=0),
                       [s["accuracy"] for s in summaries])
    return out


# 등급(도장) 이름과 기준. 낮은 등급도 꾸짖지 않는 말로 쓴다.
RANKS = [(85, "최고예요"), (65, "잘했어요"), (40, "좋아요"), (0, "푹 쉬었어요")]


def rank_of(acc):
    for lo, name in RANKS:
        if acc >= lo:
            return name
    return RANKS[-1][1]


def rank_level(acc):
    """0(최고)~3. 결과 음악을 고를 때 쓴다."""
    for i, (lo, _) in enumerate(RANKS):
        if acc >= lo:
            return i
    return len(RANKS) - 1


def feedback(summary, names):
    """구간별 정확도를 보고 한두 줄 평을 만든다. names: 구간(또는 게임) 이름."""
    secs = [(a, n) for a, n in zip(summary["sections"], names) if a is not None]
    if summary["total"] and summary["counts"][MISS] == summary["total"]:
        return ["깜빡임이 거의 잡히지 않았습니다. 얼굴 위치와 조명을 확인해 보세요."]
    lines = []
    if summary["no_miss"]:
        lines.append("한 번도 놓치지 않았어요.")
    if len(secs) >= 2:
        best = max(secs)
        worst = min(secs)
        if best[0] - worst[0] >= 15:
            if best[0] >= 65:
                lines.append("'%s' 부분이 특히 좋았어요." % best[1])
            lines.append("'%s' 부분을 조금 더 연습해 보세요." % worst[1])
        elif summary["accuracy"] >= 65:
            lines.append("처음부터 끝까지 고르게 잘 맞혔어요.")
    m = summary["mean_dt"]
    if m is not None and abs(m) >= 0.06:
        lines.append("전체적으로 박자보다 %s 편이에요." % ("늦은" if m > 0 else "빠른"))
    return lines[:3] or ["박자를 미리 세면서 신호를 기다려 보세요."]


def suggest_offset_shift(summary, min_hits=10, min_shift=0.030):
    """평균 오차가 한쪽으로 치우쳐 있으면 보정값 조정량(초)을 제안. 없으면 None."""
    dts = summary["dts"]
    if len(dts) < min_hits or summary["mean_dt"] is None:
        return None
    med = statistics.median(dts)
    return med if abs(med) >= min_shift else None


# --- 보정 -------------------------------------------------------------------
CAL_BPM = 90.0
CAL_BEAT = 60.0 / CAL_BPM
CAL_TICKS = 12
CAL_SKIP = 4                 # 앞 4박은 따라 하기 준비


def compute_offset(onsets, t0):
    """보정용 메트로놈에 맞춰 깜빡인 시각들로 입력 지연을 추정.

    사람은 소리에 '반응'하므로 보통 박보다 늦게 입력된다. 박 주기로 접어(mod) 중앙값을 구한다.
    반환: (offset초, 표준편차, 사용한 개수) 또는 None.
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
