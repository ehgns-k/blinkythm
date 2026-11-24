"""한 판짜리 리듬 게임 창: 듣기(상대가 눈을 깜빡임) -> 깜빡이기(따라 하기) 4박씩, 8라운드."""
import queue
import time
import tkinter as tk
from tkinter import ttk

from . import rhythm as R
from .tracker import SimTracker
from .ui_common import (C_FACE, C_WHITE, C_INK, C_GRAY, C_LIGHT, C_NAVY, C_GREEN, C_OLIVE, C_RED,
                        bold_font, plain_font, center_on)

STAGE_W, STAGE_H = 640, 300
GRADE_COLOR = {R.PERFECT: C_NAVY, R.GOOD: C_GREEN, R.OK: C_OLIVE, R.MISS: C_RED}
LANE_X0, LANE_X1, LANE_Y0, LANE_Y1 = 20, 620, 226, 268
CLOSE_FLASH = 0.13       # 상대 눈이 감겨 있는 시간


class GameWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Blinkythm - 눈 깜빡임 리듬")
        self.resizable(False, False)
        self.transient(app.root)
        self.mode = "intro"
        self._after = None
        self._blinks = queue.Queue()
        self._listening = False
        self._popup = None            # (text, sub, color, until)
        self._stray_marks = []

        self.stage = tk.Canvas(self, width=STAGE_W, height=STAGE_H, bg=C_WHITE,
                               highlightthickness=1, highlightbackground=C_GRAY)
        self.stage.pack(side="top", padx=8, pady=(8, 4))
        self.panel = ttk.Frame(self)              # 결과 화면용
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self.bar = bar
        self.lbl_score = tk.Label(bar, text="정확도 -", relief="sunken", anchor="w", width=16, bd=1)
        self.lbl_combo = tk.Label(bar, text="콤보 0", relief="sunken", anchor="w", width=10, bd=1)
        self.lbl_cam = tk.Label(bar, text="", relief="sunken", anchor="w", bd=1)
        self.lbl_score.pack(side="left")
        self.lbl_combo.pack(side="left", padx=(2, 0))
        self.lbl_cam.pack(side="left", fill="x", expand=True, padx=(2, 6))
        self.btn_start = ttk.Button(bar, text="시작(S)", command=self.start_game, underline=3)
        self.btn_close = ttk.Button(bar, text="닫기(Esc)", command=self.close)
        self.btn_close.pack(side="right")
        self.btn_start.pack(side="right", padx=(0, 4))

        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Return>", lambda e: self.start_game() if self.mode == "intro" else None)
        self.bind("<s>", lambda e: self.start_game() if self.mode == "intro" else None)
        if isinstance(app.tracker, SimTracker):
            self.bind("<space>", lambda e: app.tracker.press())
        self.protocol("WM_DELETE_WINDOW", self.close)
        center_on(self, app.root)
        self.focus_set()
        app.tracker.set_game_mode(True)
        self._tick()

    # ------------------------------------------------------------------ 수명
    def close(self):
        self._stop_listening()
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        self.app.audio.stop()
        self.app.tracker.set_game_mode(False)
        self.app.game_closed(self)
        self.destroy()

    def _listen(self):
        if not self._listening:
            self.app.tracker.add_listener(self._blinks.put)
            self._listening = True

    def _stop_listening(self):
        if self._listening:
            self.app.tracker.remove_listener(self._blinks.put)
            self._listening = False

    # ------------------------------------------------------------------ 시작
    def start_game(self):
        if self.mode == "playing":
            return
        self.panel.pack_forget()
        self.stage.pack(side="top", padx=8, pady=(8, 4), before=self.bar)
        s = self.app.settings
        self.call, resp = R.build_chart()
        self.judge = R.Judge(resp, 0.0, offset=s.latency_offset,
                             slack=R.frame_slack(self.app.tracker.frame_dt))
        self.app.audio.volume = s.volume
        self.app.audio.prepare_hits()
        ticks = [(b * R.BEAT, b % 4 == 0) for b in range(R.TOTAL_BEATS)]
        cues = [n.beat * R.BEAT for n in self.call]
        t0 = self.app.audio.play_track(ticks, cues, R.TOTAL_BEATS * R.BEAT)
        if t0 is None:                     # 소리를 낼 수 없으면 화면만으로 진행
            t0 = time.perf_counter() + 0.3
        self.t0 = t0
        for n in self.call:
            n.time = t0 + n.beat * R.BEAT
        for n in self.judge.notes:
            n.time = t0 + n.beat * R.BEAT
        while not self._blinks.empty():
            self._blinks.get_nowait()
        self._listen()
        self._popup = None
        self._stray_marks = []
        self.mode = "playing"
        self.btn_start.state(["disabled"])
        self.btn_close.config(text="중단(Esc)")
        self._update_status()

    def _finish(self):
        self.mode = "result"
        self._stop_listening()
        self.app.audio.stop()
        self.app.monitor.mark_played(time.perf_counter())
        self.show_result()

    # ------------------------------------------------------------------ 프레임 루프
    def _tick(self):
        now = time.perf_counter()
        if self.mode == "playing":
            while True:
                try:
                    onset = self._blinks.get_nowait()
                except queue.Empty:
                    break
                res = self.judge.on_blink(onset)
                if res is not None:
                    self._on_result(res, now)
                else:
                    self._stray_marks.append(now)
            for res in self.judge.poll(now):
                self._on_result(res, now, quiet=True)
            if (now - self.t0) / R.BEAT >= R.TOTAL_BEATS:
                self._finish()
            else:
                self._draw(now)
        elif self.mode == "intro":
            self._draw_intro()
        self._update_cam_label()
        self._after = self.after(16, self._tick)

    def _on_result(self, res, now, quiet=False):
        if not quiet:
            self.app.audio.play_hit(res.grade)
        if res.grade == R.MISS:
            self._popup = (R.LABEL[R.MISS], "", C_RED, now + 0.6)
        else:
            ms = int(round(res.dt * 1000))
            if abs(ms) <= 25:
                sub = "딱 맞음"
            else:
                sub = ("느림 +%dms" if ms > 0 else "빠름 %dms") % ms
            self._popup = (R.LABEL[res.grade], sub, GRADE_COLOR[res.grade], now + 0.7)
        self._update_status()

    def _update_status(self):
        done = [m for m in self.judge.matched if m is not None]
        if done:
            acc = sum(R.POINTS[r.grade] for r in done) / (100.0 * len(done)) * 100
            self.lbl_score.config(text="정확도 %d%%" % round(acc))
        else:
            self.lbl_score.config(text="정확도 -")
        self.lbl_combo.config(text="콤보 %d" % self.judge.combo)

    def _update_cam_label(self):
        tr = self.app.tracker
        if tr.error:
            self.lbl_cam.config(text="카메라 오류", fg=C_RED)
        elif tr.face_visible:
            self.lbl_cam.config(text="얼굴 인식됨", fg=C_INK)
        else:
            self.lbl_cam.config(text="얼굴이 보이지 않습니다", fg=C_RED)

    # ------------------------------------------------------------------ 그리기
    def _face(self, cx, cy, closed, label, highlight=False):
        c = self.stage
        c.create_rectangle(cx - 62, cy - 52, cx + 62, cy + 52, fill=C_FACE, outline=C_INK,
                           width=3 if highlight else 1)
        for ex in (cx - 26, cx + 26):
            if closed:
                c.create_line(ex - 15, cy - 6, ex + 15, cy - 6, fill=C_INK, width=3)
            else:
                c.create_oval(ex - 13, cy - 24, ex + 13, cy + 8, fill=C_WHITE, outline=C_INK)
                c.create_oval(ex - 5, cy - 14, ex + 5, cy - 2, fill=C_INK, outline=C_INK)
        c.create_line(cx - 16, cy + 30, cx + 16, cy + 30, fill=C_INK, width=2)
        c.create_text(cx, cy + 68, text=label, font=plain_font(9), fill=C_INK)

    def _draw(self, now):
        c = self.stage
        c.delete("all")
        beat = (now - self.t0) / R.BEAT
        r, phase = R.round_info(beat)
        s = self.app.settings

        # 머리말
        c.create_rectangle(0, 0, STAGE_W, 26, fill=C_LIGHT, outline="")
        c.create_line(0, 26, STAGE_W, 26, fill=C_GRAY)
        if phase == "count":
            head, sub = "준비", "소리를 듣고, 같은 박자로 눈을 깜빡이세요"
        elif phase == "call":
            head, sub = "듣기", "상대가 눈을 감는 박자를 기억하세요"
        elif phase == "resp":
            head, sub = "깜빡이기", "지금! 같은 박자로 눈을 깜빡이세요"
        else:
            head, sub = "끝", ""
        c.create_text(10, 13, anchor="w", font=bold_font(10), text=head, fill=C_NAVY)
        c.create_text(90, 13, anchor="w", font=plain_font(9), text=sub, fill=C_INK)
        if r >= 0:
            c.create_text(STAGE_W - 10, 13, anchor="e", font=plain_font(9),
                          text="라운드 %d / %d" % (r + 1, len(R.PATTERNS)), fill=C_INK)

        # 상대(시범) 눈: 시범 박자에 맞춰 잠깐 감김
        caller_closed = any(0 <= now - n.time < CLOSE_FLASH for n in self.call)
        self._face(170, 142, caller_closed, "상대", highlight=(phase == "call"))
        self._face(470, 142, self.app.tracker.eye_closed, "나", highlight=(phase == "resp"))

        # 판정 표시
        if self._popup and now < self._popup[3]:
            text, subtxt, color, _ = self._popup
            c.create_text(470, 46, text=text, font=bold_font(16), fill=color)
            if subtxt:
                c.create_text(470, 68, text=subtxt, font=plain_font(9), fill=color)

        # 준비 박자 점
        if phase == "count":
            for i in range(R.COUNT_IN):
                x = STAGE_W // 2 - 45 + i * 30
                c.create_oval(x - 7, 204 - 7, x + 7, 204 + 7, outline=C_INK,
                              fill=C_NAVY if beat >= i else C_WHITE)
            c.create_rectangle(LANE_X0, LANE_Y0, LANE_X1, LANE_Y1, outline=C_GRAY)
            return

        # 타임라인: 현재 라운드의 8박
        rr = min(r, len(R.PATTERNS) - 1)
        base = R.COUNT_IN + R.ROUND_BEATS * rr
        px = (LANE_X1 - LANE_X0) / R.ROUND_BEATS

        def bx(b):
            return LANE_X0 + (b - base) * px

        c.create_rectangle(LANE_X0, LANE_Y0, bx(base + 4), LANE_Y1, fill=C_LIGHT, outline=C_GRAY)
        c.create_rectangle(bx(base + 4), LANE_Y0, LANE_X1, LANE_Y1, fill=C_WHITE, outline=C_GRAY)
        for k in range(R.ROUND_BEATS + 1):
            x = LANE_X0 + k * px
            long = k in (0, 4, 8)
            c.create_line(x, LANE_Y0 if long else LANE_Y0 + 10, x, LANE_Y1, fill=C_GRAY)
        c.create_text(LANE_X0 + 4, LANE_Y0 - 9, anchor="w", text="듣기", font=plain_font(8), fill=C_GRAY)
        c.create_text(bx(base + 4) + 4, LANE_Y0 - 9, anchor="w", text="깜빡이기", font=plain_font(8), fill=C_GRAY)

        mid = (LANE_Y0 + LANE_Y1) // 2
        for n in self.call:
            if n.round == rr and now >= n.time:
                x = bx(n.beat)
                c.create_rectangle(x - 7, mid - 7, x + 7, mid + 7, fill=C_NAVY, outline=C_NAVY)
        for i, n in enumerate(self.judge.notes):
            if n.round != rr:
                continue
            x = bx(n.beat)
            m = self.judge.matched[i]
            if m is not None:
                col = GRADE_COLOR[m.grade]
                if m.grade == R.MISS:
                    c.create_line(x - 7, mid - 7, x + 7, mid + 7, fill=col, width=2)
                    c.create_line(x - 7, mid + 7, x + 7, mid - 7, fill=col, width=2)
                else:
                    c.create_rectangle(x - 7, mid - 7, x + 7, mid + 7, fill=col, outline=col)
                    c.create_text(x, LANE_Y1 + 9, text="%+d" % round(m.dt * 1000), font=plain_font(8), fill=col)
            elif s.show_guide:
                c.create_rectangle(x - 7, mid - 7, x + 7, mid + 7, outline=C_GRAY, dash=(2, 2))
        # 재생 위치
        x = max(LANE_X0, min(LANE_X1, bx(beat)))
        c.create_line(x, LANE_Y0 - 4, x, LANE_Y1 + 2, fill=C_INK, width=2)

    def _draw_intro(self):
        c = self.stage
        if getattr(self, "_intro_drawn", False):
            return
        self._intro_drawn = True
        c.delete("all")
        c.create_text(STAGE_W // 2, 40, text="눈 깜빡임 리듬", font=bold_font(16), fill=C_NAVY)
        lines = [
            "1. 먼저 상대가 눈을 감는 박자를 보고 듣습니다. (4박)",
            "2. 이어지는 4박 동안 같은 박자로 눈을 깜빡이세요.",
            "3. 소리가 난 순간이 아니라, 박자에 눈을 감기 시작하는 순간을 맞추면 됩니다.",
            "4. 박자와 상관없는 평소의 깜빡임은 감점되지 않습니다.",
            "",
            "총 8라운드, 약 45초입니다. 화면에서 얼굴이 너무 멀어지지 않게 해 주세요.",
        ]
        for i, t in enumerate(lines):
            c.create_text(60, 90 + i * 26, anchor="w", text=t, font=plain_font(10), fill=C_INK)
        if isinstance(self.app.tracker, SimTracker):
            c.create_text(STAGE_W // 2, 280, text="[시험 모드] 스페이스바 = 눈 깜빡임",
                          font=plain_font(9), fill=C_RED)

    # ------------------------------------------------------------------ 결과
    def show_result(self):
        sm = self.judge.summary()
        self.stage.pack_forget()
        for w in self.panel.winfo_children():
            w.destroy()
        self.panel.pack(side="top", padx=8, pady=(8, 4), before=self.bar)
        p = self.panel
        p.configure(width=STAGE_W, height=STAGE_H + 2)
        p.grid_propagate(False)

        ttk.Label(p, text="결과: %s" % sm["rank"], font=bold_font(14)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        box = ttk.LabelFrame(p, text="판정", padding=8)
        box.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        rows = [(R.PERFECT, "완벽"), (R.GOOD, "좋음"), (R.OK, "아쉬움"), (R.MISS, "놓침")]
        for i, (g, name) in enumerate(rows):
            ttk.Label(box, text=name, width=8).grid(row=i, column=0, sticky="w")
            ttk.Label(box, text="%d / %d" % (sm["counts"][g], sm["total"])).grid(row=i, column=1, sticky="e")
        ttk.Label(box, text="정확도").grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Label(box, text="%.0f%%" % sm["accuracy"], font=bold_font(9)).grid(row=4, column=1, sticky="e", pady=(6, 0))
        ttk.Label(box, text="최고 콤보").grid(row=5, column=0, sticky="w")
        ttk.Label(box, text=str(sm["best_combo"])).grid(row=5, column=1, sticky="e")

        tbox = ttk.LabelFrame(p, text="타이밍 분포 (박자 기준, ms)", padding=8)
        tbox.grid(row=1, column=1, sticky="nsew")
        hist = tk.Canvas(tbox, width=340, height=96, bg=C_WHITE, highlightthickness=1, highlightbackground=C_GRAY)
        hist.pack()
        self._draw_hist(hist, sm["dts"])
        if sm["mean_dt"] is None:
            txt = "입력이 감지되지 않았습니다. 얼굴 위치와 조명을 확인하세요."
        else:
            ms = sm["mean_dt"] * 1000
            side = "늦은 편" if ms > 0 else "빠른 편"
            txt = "평균 %+d ms (%s), 편차 ±%d ms" % (round(ms), side, round((sm["sd"] or 0) * 1000))
        ttk.Label(tbox, text=txt).pack(anchor="w", pady=(4, 0))
        if sm["stray"]:
            ttk.Label(tbox, text="박자와 무관한 깜빡임 %d회 (감점 없음)" % sm["stray"], foreground=C_GRAY).pack(anchor="w")

        shift = R.suggest_offset_shift(sm)
        self._shift = shift
        note = ttk.Frame(p)
        note.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        if shift is not None:
            ttk.Label(note, text="입력이 평균 %+d ms 치우쳐 있습니다. 이 값을 보정에 반영하면 판정이 더 정확해집니다." % round(shift * 1000),
                      wraplength=560, justify="left").pack(side="left", anchor="w")
            ttk.Button(note, text="보정에 반영(A)", command=self._apply_shift, underline=7).pack(side="right")
        else:
            ttk.Label(note, text="화면 사용 시간이 초기화되었습니다. 잠시 먼 곳을 바라보며 눈을 쉬어 주세요.",
                      wraplength=560, justify="left").pack(anchor="w")
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=2)

        self.btn_start.config(text="다시 하기(R)", underline=6)
        self.btn_start.state(["!disabled"])
        self.btn_close.config(text="닫기(Esc)")
        self.mode = "intro"
        self._intro_drawn = True       # 결과 화면에서는 무대를 다시 그리지 않음
        self.bind("<r>", lambda e: self.start_game() if self.mode == "intro" else None)

    def _apply_shift(self):
        if self._shift is None:
            return
        s = self.app.settings
        s.latency_offset += self._shift
        s.save()
        self._shift = None
        self.app.refresh_status()
        for w in self.panel.winfo_children()[-1:]:
            for ch in w.winfo_children():
                ch.destroy()
            ttk.Label(w, text="보정값을 %+d ms로 갱신했습니다." % round(s.latency_offset * 1000)).pack(anchor="w")

    def _draw_hist(self, c, dts):
        W, H = 340, 96
        lo, hi, bins = -0.24, 0.24, 12
        step = (hi - lo) / bins
        counts = [0] * bins
        for d in dts:
            k = int((max(lo, min(hi - 1e-9, d)) - lo) / step)
            counts[k] += 1
        top = max(counts) or 1
        bw = (W - 20) / bins
        for i, n in enumerate(counts):
            x0 = 10 + i * bw
            h = (H - 32) * n / top
            c.create_rectangle(x0 + 1, H - 18 - h, x0 + bw - 1, H - 18, fill=C_NAVY if n else C_WHITE, outline=C_GRAY)
        cx = 10 + (0 - lo) / (hi - lo) * (W - 20)
        c.create_line(cx, 6, cx, H - 14, fill=C_RED)
        c.create_text(10, H - 8, anchor="w", text="빠름", font=plain_font(8))
        c.create_text(W - 10, H - 8, anchor="e", text="느림", font=plain_font(8))
        c.create_text(cx, H - 8, text="0", font=plain_font(8))
