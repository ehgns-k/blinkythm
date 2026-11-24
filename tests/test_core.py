import os, random, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from blinkythm.detector import BlinkDetector
from blinkythm.monitor import UsageMonitor
from blinkythm.config import Settings
from blinkythm import rhythm as R
from blinkythm import stages as S
from blinkythm import audio as A


def synth_ear(blink_starts, fps, dur, open_ear=0.30, closed=0.10, blink_len=0.15, noise=0.008, seed=1):
    """EAR series for the given true blink starts. Trapezoid: 40 ms closing, 80 ms opening."""
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
    # the 72% threshold is crossed about 40ms*(0.28/0.20), roughly 11 ms after the blink starts
    assert all(-0.01 < e < 0.06 for e in errs), errs
    assert statistics.pstdev(errs) < 0.012


def test_detector_15fps_and_noise_flutter():
    starts = [2 + 2.0 * k for k in range(10)]
    closes, _ = run_detector(synth_ear(starts, 15, 24))
    assert len(closes) == 10
    # a one-frame noise dip is ignored
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
    # visible for 70 s but only 3 blinks -> about 2.6 per minute
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
    # enough blinks: no prompt
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
    for i in range(60 * 15):       # away for 60 s
        t += 1 / 15
        m.on_frame(t, False)
    assert m.screen_seconds(t) == 0
    m.on_frame(t + 1, True)
    assert m.blink_rate(t + 1) is None      # not enough data: no verdict
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
    assert j.on_blink(resp[3].time + 0.35) is None       # outside the window: ignored as a natural blink
    assert len(j.stray) == 1


def test_judge_offset_and_double_blink():
    j, resp = make_judge(offset=0.09)
    # 90 ms of camera delay still gives a perfect after the offset
    assert j.on_blink(resp[0].time + 0.09).grade == R.PERFECT
    # a second blink on the same note does not reach the next note's window, so it is stray
    assert j.on_blink(resp[0].time + 0.09 + 0.2) is None


def test_judge_miss_waits_for_late_event():
    j, resp = make_judge()
    n = resp[0]
    assert j.poll(n.time + 0.3) == []           # no miss before window + grace
    out = j.poll(n.time + 0.2 + R.MISS_GRACE + 0.01)
    assert [r.grade for r in out] == [R.MISS]
    assert j.combo == 0


def test_judge_assigns_nearest_when_windows_overlap():
    # "Back to back" in Blink Studio has notes 1 beat (536 ms) apart; a blink goes to the nearer note
    j, notes = make_judge(key="photo")
    pair = [(a, b) for a, b in zip(notes, notes[1:]) if b.beat - a.beat == 1][0]
    a, b = pair
    assert j.on_blink(b.time - 0.15).note is b
    assert j.on_blink(a.time + 0.05).note is a


def simulate(key, lag=0.130, sigma=0.045, seed=7, fps=30):
    """Simulate one game with webcam frames, device delay and human spread."""
    rnd = random.Random(seed)
    st = S.make_stage(key)
    j = R.Judge(st.notes, 0.0, st.beat_sec, offset=lag)
    human = [n.time + 0.03 + rnd.gauss(0, sigma) for n in st.notes]   # on average 30 ms after the beat
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
        # notes must be further apart than two windows (+/-200 ms) so a blink never lands on the wrong note
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
        # there must be sound where the first cue plays
        c = st.cues[0]
        i = int(c.beat * st.beat_sec * A.SR)
        assert abs(buf[i:i + 2000]).max() > 0.1


def test_feedback_and_combine():
    _, a = simulate("lighthouse")
    _, b = simulate("owls", sigma=0.12, seed=3)
    m = R.combine([a, b])
    assert m["total"] == a["total"] + b["total"]
    assert len(m["sections"]) == 2
    lines = R.feedback(m, ["Lighthouse", "Owl Choir"])
    assert 1 <= len(lines) <= 3
    empty = R.make_summary({g: (5 if g == R.MISS else 0) for g in R.GRADES}, 5, [], 0, 0, [0.0, 0.0])
    assert "face" in R.feedback(empty, ["A", "B"])[0]
    assert R.rank_of(90) == "Superb" and R.rank_level(10) == 3


def test_next_stage_rotation():
    assert S.next_stage("") == S.ORDER[0]
    assert S.next_stage(S.ORDER[-1]) == S.ORDER[0]
    assert S.next_stage(S.ORDER[0]) == S.ORDER[1]


def test_calibration_offset():
    rnd = random.Random(3)
    t0 = 50.0
    true_lag = 0.21                    # human reaction + device delay
    beats = [t0 + k * R.CAL_BEAT for k in range(R.CAL_TICKS)]
    onsets = [b + true_lag + rnd.gauss(0, 0.04) for b in beats[R.CAL_SKIP:]]
    off, sd, n = R.compute_offset(onsets, t0)
    assert abs(off - true_lag) < 0.03 and n >= 6
    # erratic blinking fails
    bad = [t0 + 3 + rnd.random() * 5 for _ in range(8)]
    assert R.compute_offset(bad, t0) is None
    # too few blinks fails
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


# --------------------------------------------------------------------- game window (drawn without a display)
def _headless_game():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from blinkythm.tracker import SimTracker
    from blinkythm.game.app import GameApp

    class FakeApp:
        def __init__(self):
            self.settings = Settings()
            self.settings.save = lambda: None
            self.monitor = UsageMonitor(self.settings)
            self.tracker = SimTracker(self.monitor)
            self.audio = A.Audio(0.0)
            self.opened_settings = 0

        def show_main(self):
            self.opened_settings += 1

    fake = FakeApp()
    g = GameApp(fake)
    g.open(headless_size=(768, 432))
    return fake, g


def _frames(g, n=3, dt=0.02):
    import time
    for _ in range(n):
        g.frame(time.perf_counter())
        time.sleep(dt)


def test_window_scale_fits_desktop():
    from blinkythm.game import gfx as G
    assert G.initial_window_size(1920, 1080) == (1536, 864)
    assert G.initial_window_size(3840, 2160) == (3072, 1728)       # 4K: 8x
    assert G.initial_window_size(1366, 768) == (768, 432)
    assert G.fit_scale(1000, 600) == 2 and G.fit_scale(100, 100) == 1


def test_game_screens_render_and_flow():
    import pygame
    from blinkythm.game import screens as SC
    fake, g = _headless_game()
    try:
        _frames(g)
        assert isinstance(g.screen, SC.HomeScreen)
        g.screen.key(pygame.K_g)
        _frames(g, 12)
        assert isinstance(g.screen, SC.SelectScreen)
        g.screen.key(pygame.K_RIGHT)
        g.screen.key(pygame.K_RETURN)
        _frames(g, 12)
        assert isinstance(g.screen, SC.PlayScreen) and g.screen.stage.key == S.ORDER[1]
        ps = g.screen
        # treat it as a blink on the first note
        n = ps.stage.notes[0]
        ps.blink(n.time + 0.01)
        assert ps.judge.matched[0].grade == R.PERFECT
        _frames(g, 2)
        # skip to the end of the track to reach the result
        ps.t0 -= ps.stage.seconds + 1
        _frames(g, 14)
        assert isinstance(g.screen, SC.ResultScreen)
        assert fake.settings.stamps == 1 and g.daily()["plays"] == 1
        assert fake.settings.last_stage == S.ORDER[1]
        g.screen.t_enter -= 2
        _frames(g, 2)
        g.screen.key(pygame.K_RETURN)
        _frames(g, 14)
        assert isinstance(g.screen, SC.RestScreen)
        g.screen.t_enter -= SC.REST_SECONDS + 0.1
        _frames(g, 2)
        assert g.screen.finished and g.daily()["rests"] == 1
    finally:
        g.shutdown()


def test_medley_and_double_blink():
    from blinkythm.game import screens as SC
    fake, g = _headless_game()
    try:
        _frames(g)
        # a double blink on the home screen starts the suggested game
        g._on_blink(10.0)
        g._on_blink(10.3)
        _frames(g, 14)
        assert isinstance(g.screen, SC.PlayScreen)
        g.screen.key(__import__("pygame").K_ESCAPE)
        _frames(g, 14)
        assert isinstance(g.screen, SC.SelectScreen)
        g.start(list(S.ORDER))
        _frames(g, 14)
        for i in range(len(S.ORDER)):
            ps = g.screen
            assert isinstance(ps, SC.PlayScreen) and ps.stage.key == S.ORDER[i]
            ps.t0 -= ps.stage.seconds + 1
            _frames(g, 3)
            if i < len(S.ORDER) - 1:
                assert isinstance(g.screen, SC.InterludeScreen)
                g.screen.t_enter -= SC.INTERLUDE + 0.1
                _frames(g, 3)
        _frames(g, 14)
        assert isinstance(g.screen, SC.ResultScreen) and g.screen.medley
        assert len(g.screen.sm["sections"]) == len(S.ORDER)
    finally:
        g.shutdown()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):          # avoid encoding errors on the Windows console (cp1252)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fails = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            try:
                v(); print("PASS", k)
            except AssertionError as e:
                fails += 1; print("FAIL", k, e)
    sys.exit(1 if fails else 0)
