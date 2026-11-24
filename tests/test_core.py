import os, random, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from blinkythm.detector import BlinkDetector
from blinkythm.monitor import UsageMonitor
from blinkythm.config import Settings
from blinkythm import rhythm as R


def synth_ear(blink_starts, fps, dur, open_ear=0.30, closed=0.10, blink_len=0.15, noise=0.008, seed=1):
    """blink_starts(진짜 감기 시작 시각)에 맞춰 EAR 시계열 생성. 감기 40ms/뜨기 80ms 사다리꼴."""
    rnd = random.Random(seed)
    out = []
    n = int(dur * fps)
    for i in range(n):
        t = i / fps
        e = open_ear
        for s in blink_starts:
            x = t - s
            if 0 <= x < 0.04:
                e = open_ear - (open_ear - closed) * x / 0.04
            elif 0.04 <= x < 0.04 + blink_len:
                e = closed
            elif 0.04 + blink_len <= x < 0.04 + blink_len + 0.08:
                e = closed + (open_ear - closed) * (x - 0.04 - blink_len) / 0.08
        out.append((t, e + rnd.gauss(0, noise)))
    return out


def run_detector(series, cam_lag=0.0):
    closes, blinks = [], []
    d = BlinkDetector(lambda o: closes.append(o), lambda o, du: blinks.append((o, du)))
    for t, e in series:
        d.feed(t + cam_lag, e)
    return closes, blinks


def test_detector_accuracy_30fps():
    starts = [2 + 1.7 * k for k in range(15)]
    closes, blinks = run_detector(synth_ear(starts, 30, 32))
    assert len(closes) == 15 and len(blinks) == 15, (len(closes), len(blinks))
    errs = [c - s for c, s in zip(closes, starts)]
    # 임계값(72%) 교차 시점은 감기 시작 후 약 40ms*(0.28/0.20)=약 11ms 부근
    assert all(-0.01 < e < 0.06 for e in errs), errs
    assert statistics.pstdev(errs) < 0.012


def test_detector_15fps_and_noise_flutter():
    starts = [2 + 2.0 * k for k in range(10)]
    closes, _ = run_detector(synth_ear(starts, 15, 24))
    assert len(closes) == 10
    # 한 프레임짜리 노이즈 하락은 무시
    ser = synth_ear([], 30, 10)
    ser = [(t, 0.05 if i == 100 else e) for i, (t, e) in enumerate(ser)]
    closes, _ = run_detector(ser)
    assert closes == []


def test_long_close_not_counted_as_blink():
    closes, blinks = run_detector(synth_ear([3.0], 30, 8, blink_len=1.5))
    assert len(closes) == 1 and blinks == []


def test_face_lost_resets():
    d = BlinkDetector()
    for i in range(60):
        d.feed(i / 30, 0.3)
    d.feed(2.0, None)
    assert d.closed is False


def test_monitor_trigger():
    s = Settings(screen_minutes=1, blink_threshold=12, away_seconds=30)
    m = UsageMonitor(s)
    t = 0.0
    # 70초간 보이지만 깜빡임 3회뿐 -> 분당 약 2.6회
    for i in range(int(70 * 15)):
        t = i / 15
        m.on_frame(t, True)
        if i in (100, 500, 900):
            m.on_blink(t)
    assert m.screen_seconds(t) >= 60
    assert m.blink_rate(t) < 12
    assert m.should_prompt(t)
    assert not m.should_prompt(t, dnd=True)
    m.snooze(t, 5)
    assert not m.should_prompt(t + 100)
    # 깜빡임이 충분하면 알리지 않음
    m2 = UsageMonitor(s)
    for i in range(int(70 * 15)):
        t = i / 15
        m2.on_frame(t, True)
        if i % 60 == 0:
            m2.on_blink(t)
    assert m2.blink_rate(t) > 12 and not m2.should_prompt(t)


def test_monitor_away_reset_and_insufficient_data():
    s = Settings(screen_minutes=1, blink_threshold=12, away_seconds=30)
    m = UsageMonitor(s)
    for i in range(30 * 15):
        m.on_frame(i / 15, True)
    t = 30.0
    for i in range(60 * 15):       # 60초 자리비움
        t += 1 / 15
        m.on_frame(t, False)
    assert m.screen_seconds(t) == 0
    m.on_frame(t + 1, True)
    assert m.blink_rate(t + 1) is None      # 데이터 부족이면 판단 보류
    assert not m.should_prompt(t + 1)


def make_judge(offset=0.0, slack=0.0):
    _, resp = R.build_chart()
    return R.Judge(resp, t0=100.0, offset=offset, slack=slack), resp


def test_judge_grades_and_signs():
    j, resp = make_judge()
    n0 = resp[0].time
    assert j.on_blink(n0 + 0.02).grade == R.PERFECT
    assert j.on_blink(resp[1].time - 0.10).grade == R.GOOD
    r = j.on_blink(resp[2].time + 0.18)
    assert r.grade == R.OK and r.dt > 0
    assert j.on_blink(resp[3].time + 0.35) is None       # 창 밖: 자연 깜빡임으로 무시
    assert len(j.stray) == 1


def test_judge_offset_and_double_blink():
    j, resp = make_judge(offset=0.09)
    # 카메라 지연 90ms가 있는 입력도 보정 후 완벽
    assert j.on_blink(resp[0].time + 0.09).grade == R.PERFECT
    # 같은 노트에 연속 두 번 -> 두 번째는 다음 노트 창(1박=625ms)에 안 닿으므로 stray
    assert j.on_blink(resp[0].time + 0.09 + 0.2) is None


def test_judge_miss_waits_for_late_event():
    j, resp = make_judge()
    n = resp[0]
    assert j.poll(n.time + 0.3) == []           # 창+유예 전에는 놓침 확정 안 함
    out = j.poll(n.time + 0.2 + R.MISS_GRACE + 0.01)
    assert [r.grade for r in out] == [R.MISS]
    assert j.combo == 0


def test_judge_assigns_nearest_when_windows_overlap():
    j, resp = make_judge()
    # 0.5박 간격 노트가 있는 라운드(인덱스 14: [0.5,2,3]은 1.5박 간격)에서도 가까운 쪽에 배정
    a, b = resp[0], resp[1]
    mid = (a.time + b.time) / 2
    r = j.on_blink(a.time + 0.05)
    assert r.note is a


def test_full_play_simulation():
    """30fps 카메라 + 130ms 장치 지연 + 사람 편차(σ45ms)로 한 판 시뮬레이션."""
    rnd = random.Random(7)
    _, resp = R.build_chart()
    t0 = 0.0
    lag = 0.130
    j = R.Judge(resp, t0, offset=lag)
    human = [n.time + 0.03 + rnd.gauss(0, 0.045) for n in resp]       # 박보다 평균 30ms 늦게 시작
    # 카메라 시계에서는 lag만큼 늦게 보임
    series = synth_ear(human, 30, R.TOTAL_BEATS * R.BEAT + 1)
    closes, _ = run_detector(series, cam_lag=lag)
    for o in closes:
        j.on_blink(o)
    j.poll(1e9)
    s = j.summary()
    assert s["counts"][R.MISS] <= 2, s
    assert s["accuracy"] > 70, s
    assert 0.0 < s["mean_dt"] < 0.08, s
    print("sim:", {k: s[k] for k in ("counts", "accuracy", "mean_dt", "sd", "rank")})


def test_calibration_offset():
    rnd = random.Random(3)
    t0 = 50.0
    true_lag = 0.21                    # 사람 반응 + 장치 지연
    beats = [t0 + k * R.CAL_BEAT for k in range(R.CAL_TICKS)]
    onsets = [b + true_lag + rnd.gauss(0, 0.04) for b in beats[R.CAL_SKIP:]]
    off, sd, n = R.compute_offset(onsets, t0)
    assert abs(off - true_lag) < 0.03 and n >= 6
    # 엉망으로 깜빡이면 실패 처리
    bad = [t0 + 3 + rnd.random() * 5 for _ in range(8)]
    assert R.compute_offset(bad, t0) is None
    # 너무 적으면 실패
    assert R.compute_offset(onsets[:3], t0) is None


def test_suggest_shift():
    j, resp = make_judge()
    for n in resp[:12]:
        j.on_blink(n.time + 0.06)
    s = j.summary()
    assert abs(R.suggest_offset_shift(s) - 0.06) < 1e-6
    j2, resp2 = make_judge()
    for n in resp2[:12]:
        j2.on_blink(n.time + 0.005)
    assert R.suggest_offset_shift(j2.summary()) is None


if __name__ == "__main__":
    fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            try:
                v(); print("PASS", k)
            except AssertionError as e:
                fails += 1; print("FAIL", k, e)
    sys.exit(1 if fails else 0)
