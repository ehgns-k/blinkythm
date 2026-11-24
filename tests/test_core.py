import os, random, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from blinkythm.detector import BlinkDetector
from blinkythm.monitor import UsageMonitor
from blinkythm.config import Settings
from blinkythm import rhythm as R
from blinkythm import stages as S
from blinkythm import audio as A


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


def make_judge(offset=0.0, slack=0.0, key="lighthouse"):
    st = S.make_stage(key)
    return R.Judge(st.notes, t0=100.0, beat_sec=st.beat_sec, offset=offset, slack=slack), st.notes


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
    # 같은 노트에 연속 두 번 -> 두 번째는 다음 노트 창에 닿지 않으므로 stray
    assert j.on_blink(resp[0].time + 0.09 + 0.2) is None


def test_judge_miss_waits_for_late_event():
    j, resp = make_judge()
    n = resp[0]
    assert j.poll(n.time + 0.3) == []           # 창+유예 전에는 놓침 확정 안 함
    out = j.poll(n.time + 0.2 + R.MISS_GRACE + 0.01)
    assert [r.grade for r in out] == [R.MISS]
    assert j.combo == 0


def test_judge_assigns_nearest_when_windows_overlap():
    # 사진관의 '두 명 연달아'는 노트 간격이 1박(536ms)이라 창이 가깝다. 가까운 쪽에 배정되어야 한다
    j, notes = make_judge(key="photo")
    pair = [(a, b) for a, b in zip(notes, notes[1:]) if b.beat - a.beat == 1][0]
    a, b = pair
    assert j.on_blink(b.time - 0.15).note is b
    assert j.on_blink(a.time + 0.05).note is a


def simulate(key, lag=0.130, sigma=0.045, seed=7, fps=30):
    """웹캠 프레임 + 장치 지연 + 사람 편차로 한 판 시뮬레이션."""
    rnd = random.Random(seed)
    st = S.make_stage(key)
    j = R.Judge(st.notes, 0.0, st.beat_sec, offset=lag)
    human = [n.time + 0.03 + rnd.gauss(0, sigma) for n in st.notes]   # 박보다 평균 30ms 늦게 시작
    series = synth_ear(human, fps, st.seconds + 1)
    closes, _ = run_detector(series, cam_lag=lag)
    for o in closes:
        j.on_blink(o)
    j.poll(1e9)
    return st, j.summary(len(st.sections))


def test_full_play_simulation():
    for key in S.ORDER:
        st, s = simulate(key)
        assert s["counts"][R.MISS] <= 2, (key, s)
        assert s["accuracy"] > 70, (key, s)
        assert 0.0 < s["mean_dt"] < 0.08, (key, s)
        assert all(a is not None for a in s["sections"])
        print("sim:", key, {k: s[k] for k in ("counts", "accuracy", "rank")})


def test_stage_charts():
    for key in S.ORDER:
        st = S.make_stage(key)
        assert 25 < st.seconds < 45, (key, st.seconds)
        beats = [n.beat for n in st.notes]
        assert beats == sorted(beats) and [n.idx for n in st.notes] == list(range(len(beats)))
        # 노트 사이가 판정 창 두 개(±200ms)보다 넉넉해야 한 깜빡임이 엉뚱한 노트에 붙지 않는다
        gaps = [(b - a) * st.beat_sec for a, b in zip(beats, beats[1:])]
        assert min(gaps) >= 0.5, (key, min(gaps))
        assert beats[0] >= S.COUNT_IN and beats[-1] < st.length
        assert all(c.beat < st.length for c in st.cues)
        assert all(n.reveal < n.beat for n in st.notes)
        assert (st.length - S.COUNT_IN) % 4 == 0
        assert {n.section for n in st.notes} == set(range(len(st.sections)))


def test_photo_delay_and_owl_intervals():
    st = S.make_stage("photo")
    bells = sorted(c.beat for c in st.cues)
    assert [n.beat for n in st.notes] == [b + S.PHOTO_DELAY for b in bells]
    owls = S.make_stage("owls")
    a = sorted(c.beat for c in owls.cues if c.actor == "owl_a")
    b = sorted(c.beat for c in owls.cues if c.actor == "owl_b")
    for x, y, n in zip(a, b, owls.notes):
        assert abs((n.beat - y) - (y - x)) < 1e-9


SPRITES = ["owl_a_open", "owl_a_closed", "owl_b_open", "owl_b_closed", "owl_me_open", "owl_me_closed",
           "lighthouse_on", "lighthouse_off", "ship_on", "ship_off", "camera_open", "camera_shut",
           "customer_1", "customer_2", "customer_3", "desk_bell"]


def test_assets_present():
    base = A.assets_dir()
    for name in SPRITES:
        assert os.path.isfile(os.path.join(base, "sprites", name + ".png")), name
    bank = A.SampleBank()
    names = {"count", "count_accent", "finish", "dull", "jingle_great", "jingle_good", "jingle_try"}
    for key in S.ORDER:
        st = S.make_stage(key)
        names |= {st.loop, st.hit_sound} | {c.sound for c in st.cues}
    for n in names:
        y = A.load_wav(bank.path(n))
        assert len(y) > 100 and abs(y).max() > 0.05, n


def test_render_stage_track():
    bank = A.SampleBank()
    for key in S.ORDER:
        st = S.make_stage(key)
        buf = A.render_stage(st, bank)
        assert len(buf) >= st.seconds * A.SR
        assert abs(buf).max() <= 0.951
        # 첫 신호음 자리에는 소리가 있어야 한다
        c = st.cues[0]
        i = int(c.beat * st.beat_sec * A.SR)
        assert abs(buf[i:i + 2000]).max() > 0.1


def test_feedback_and_combine():
    _, a = simulate("lighthouse")
    _, b = simulate("owls", sigma=0.12, seed=3)
    m = R.combine([a, b])
    assert m["total"] == a["total"] + b["total"]
    assert len(m["sections"]) == 2
    lines = R.feedback(m, ["등대 신호", "올빼미 합창"])
    assert 1 <= len(lines) <= 3
    empty = R.make_summary({g: (5 if g == R.MISS else 0) for g in R.GRADES}, 5, [], 0, 0, [0.0, 0.0])
    assert "얼굴" in R.feedback(empty, ["가", "나"])[0]
    assert R.rank_of(90) == "훌륭해요" and R.rank_level(10) == 3


def test_next_stage_rotation():
    assert S.next_stage("") == S.ORDER[0]
    assert S.next_stage(S.ORDER[-1]) == S.ORDER[0]
    assert S.next_stage(S.ORDER[0]) == S.ORDER[1]


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
    s = j.summary(3)
    assert abs(R.suggest_offset_shift(s) - 0.06) < 1e-6
    j2, resp2 = make_judge()
    for n in resp2[:12]:
        j2.on_blink(n.time + 0.005)
    assert R.suggest_offset_shift(j2.summary()) is None


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):          # Windows 콘솔(cp1252)에서도 한글 출력이 깨지지 않게
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            try:
                v(); print("PASS", k)
            except AssertionError as e:
                fails += 1; print("FAIL", k, e)
    sys.exit(1 if fails else 0)
