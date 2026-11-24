"""채보, 판정, 타이밍 보정 계산(순수 로직)."""
import statistics
from dataclasses import dataclass
from typing import Optional

BPM = 96.0
BEAT = 60.0 / BPM
COUNT_IN = 4
ROUND_BEATS = 8              # 듣기 4박 + 깜빡이기 4박
TAIL_BEATS = 2

# 4박 안에서의 박 위치(0 = 첫 박, 1.5 = 둘째 박 뒷박 반)
PATTERNS = [
    [0, 2],
    [0, 1, 2],
    [1, 2, 3],
    [0, 1.5, 3],
    [0, 2, 3],
    [0, 1, 2.5],
    [0.5, 2, 3],
    [0, 1.5, 2.5, 3.5],
]
TOTAL_BEATS = COUNT_IN + ROUND_BEATS * len(PATTERNS) + TAIL_BEATS

# 판정 등급
PERFECT, GOOD, OK, MISS = "perfect", "good", "ok", "miss"
POINTS = {PERFECT: 100, GOOD: 75, OK: 40, MISS: 0}
LABEL = {PERFECT: "완벽", GOOD: "좋음", OK: "아쉬움", MISS: "놓침"}

# 판정 창(초, 노트 기준 ±).
# 웹캠은 30fps면 프레임 간격이 33ms이고, 눈 감기 시작을 자발적으로 맞추는 사람의 편차도 크므로
# 키보드 리듬게임보다 훨씬 넓게 잡는다. 느린 카메라는 slack으로 추가 보정한다.
WINDOWS = {PERFECT: 0.070, GOOD: 0.130, OK: 0.200}
# 입력 이벤트는 감기 시작 후 몇 프레임이 지나서 도착하므로, 이 시간이 지나야 "놓침"으로 확정한다.
MISS_GRACE = 0.18


@dataclass
class Note:
    idx: int
    round: int
    beat: float            # 곡 시작 기준 박 위치
    phase: str             # "call" | "resp"
    time: float = 0.0      # 절대 시각(perf_counter)


@dataclass
class Result:
    note: Note
    grade: str
    dt: Optional[float]    # 입력 - 노트, 초. 양수 = 늦음. 놓침이면 None


def build_chart():
    call, resp = [], []
    for r, pat in enumerate(PATTERNS):
        start = COUNT_IN + ROUND_BEATS * r
        for p in pat:
            call.append(Note(len(call), r, start + p, "call"))
            resp.append(Note(len(resp), r, start + 4 + p, "resp"))
    return call, resp


def round_info(beat):
    """현재 박 위치 -> (라운드 번호 또는 -1, 단계). 단계: count/call/resp/end"""
    if beat < COUNT_IN:
        return -1, "count"
    if beat >= COUNT_IN + ROUND_BEATS * len(PATTERNS):
        return len(PATTERNS) - 1, "end"
    rel = beat - COUNT_IN
    r = int(rel // ROUND_BEATS)
    return r, ("call" if rel % ROUND_BEATS < 4 else "resp")


def frame_slack(frame_dt):
    """카메라가 30fps보다 느릴 때 판정 창에 더해 줄 여유(초)."""
    return max(0.0, frame_dt - 1 / 30) * 0.5


class Judge:
    def __init__(self, resp_notes, t0, offset=0.0, slack=0.0):
        self.notes = resp_notes
        for n in self.notes:
            n.time = t0 + n.beat * BEAT
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

    # --- 결과 요약 -----------------------------------------------------------
    def summary(self):
        done = [m for m in self.matched if m is not None]
        counts = {g: sum(1 for r in done if r.grade == g) for g in POINTS}
        total = len(self.notes)
        acc = sum(POINTS[r.grade] for r in done) / (100.0 * total) * 100 if total else 0.0
        dts = [r.dt for r in done if r.dt is not None]
        mean = statistics.fmean(dts) if dts else None
        sd = statistics.pstdev(dts) if len(dts) > 1 else None
        return {
            "counts": counts, "accuracy": acc, "mean_dt": mean, "sd": sd,
            "dts": dts, "stray": len(self.stray), "best_combo": self.best_combo,
            "rank": rank_of(acc), "total": total,
        }


def rank_of(acc):
    if acc >= 85:
        return "훌륭해요"
    if acc >= 65:
        return "좋아요"
    if acc >= 40:
        return "보통이에요"
    return "다시 도전해요"


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
