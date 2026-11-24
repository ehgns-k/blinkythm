"""게임 창: 게임 선택 -> 한 판(또는 메들리) -> 결과."""
import queue
import time
import tkinter as tk
from tkinter import ttk

from . import rhythm as R
from . import stages as S
from .tracker import SimTracker
from .ui_common import (C_WHITE, C_INK, C_GRAY, C_LIGHT, C_NAVY, C_GREEN, C_OLIVE, C_RED,
                        bold_font, plain_font, center_on)
from .ui_scenes import STAGE_W, SCENE_BOT, Sprites, View, make_scene

STAGE_H = 320
GRADE_COLOR = {R.PERFECT: C_NAVY, R.GOOD: C_GREEN, R.OK: C_OLIVE, R.MISS: C_RED}
LANE_X0, LANE_X1, LANE_Y0, LANE_Y1 = 56, 624, 254, 292
INTERLUDE = 3.5          # 메들리에서 다음 게임까지 쉬는 시간(초)
JINGLES = ["jingle_great", "jingle_good", "jingle_try", "jingle_try"]


class GameWindow(tk.Toplevel):
    def __init__(self, app, preselect=None):
        super().__init__(app.root)
        self.app = app
        self.title("Blinkythm - 눈 깜빡임 리듬")
        self.resizable(False, False)
        self.transient(app.root)
        self.mode = "select"
        self._after = None
        self._blinks = queue.Queue()
        self._listening = False
        self._popup = None            # (text, sub, color, until)
        self.sprites = Sprites(self)
        self.stage = None
        self.judge = None
        self.hits = []
        self.queue = []
        self.played = []              # [(Stage, summary)]
        self.choice = preselect or S.next_stage(app.settings.last_stage)

        self.stage_canvas = tk.Canvas(self, width=STAGE_W, height=STAGE_H, bg=C_WHITE,
                                      highlightthickness=1, highlightbackground=C_GRAY)
        self.panel = ttk.Frame(self, width=STAGE_W + 2, height=STAGE_H + 2)
        self.panel.pack_propagate(False)
        self.panel.grid_propagate(False)
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self.bar = bar
        self.lbl_score = tk.Label(bar, text="정확도 -", relief="sunken", anchor="w", width=14, bd=1)
        self.lbl_combo = tk.Label(bar, text="콤보 0", relief="sunken", anchor="w", width=9, bd=1)
        self.lbl_cam = tk.Label(bar, text="", relief="sunken", anchor="w", bd=1)
        self.lbl_score.pack(side="left")
        self.lbl_combo.pack(side="left", padx=(2, 0))
        self.lbl_cam.pack(side="left", fill="x", expand=True, padx=(2, 6))
        self.btn_close = ttk.Button(bar, text="닫기(Esc)", command=self.on_escape)
        self.btn_close.pack(side="right")
        self.btn_select = ttk.Button(bar, text="게임 선택(G)", command=self.show_select, underline=6)
        self.btn_select.pack(side="right", padx=(0, 4))
        self.btn_start = ttk.Button(bar, text="시작(S)", command=self.start_selected, underline=3)
        self.btn_start.pack(side="right", padx=(0, 4))

        self.bind("<Escape>", lambda e: self.on_escape())
        self.bind("<Return>", lambda e: self.start_selected())
        self.bind("<s>", lambda e: self.start_selected())
        self.bind("<r>", lambda e: self.start_selected() if self.mode == "result" else None)
        self.bind("<g>", lambda e: self.show_select() if self.mode == "result" else None)
        if isinstance(app.tracker, SimTracker):
            self.bind("<space>", lambda e: app.tracker.press())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_select()
        center_on(self, app.root)
        self.focus_set()
        app.tracker.set_game_mode(True)
        self._tick()

    # ------------------------------------------------------------------ 수명
    def on_escape(self):
        if self.mode in ("playing", "interlude"):
            self._abort()
        else:
            self.close()

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

    def _abort(self):
        self._stop_listening()
        self.app.audio.stop()
        self.queue = []
        self.show_select()

    def _show_canvas(self):
        self.panel.pack_forget()
        self.stage_canvas.pack(side="top", padx=8, pady=(8, 4), before=self.bar)

    def _show_panel(self):
        self.stage_canvas.pack_forget()
        for w in self.panel.winfo_children():
            w.destroy()
        self.panel.pack(side="top", padx=8, pady=(8, 4), before=self.bar)
        return self.panel

    # ------------------------------------------------------------------ 게임 선택
    def show_select(self):
        self.mode = "select"
        p = self._show_panel()
        ttk.Label(p, text="게임을 고르세요", font=bold_font(11)).pack(anchor="w", pady=(0, 6))
        tv = ttk.Treeview(p, columns=("style", "len", "best"), height=4, selectmode="browse")
        tv.heading("#0", text="게임")
        tv.heading("style", text="방식")
        tv.heading("len", text="길이")
        tv.heading("best", text="최고 기록")
        tv.column("#0", width=200)
        tv.column("style", width=110)
        tv.column("len", width=80, anchor="e")
        tv.column("best", width=200)
        rec = self.app.settings.records or {}
        total = 0.0
        for key in S.ORDER:
            st = S.make_stage(key)
            total += st.seconds
            tv.insert("", "end", iid=key, text=st.title,
                      values=(st.style, "%d초" % round(st.seconds), self._record_text(rec.get(key))))
        tv.insert("", "end", iid=S.MEDLEY, text="메들리 (세 게임 연속)",
                  values=("모두", "%d초" % round(total + INTERLUDE * (len(S.ORDER) - 1)),
                          self._record_text(rec.get(S.MEDLEY))))
        tv.pack(fill="x")
        tv.selection_set(self.choice)
        tv.focus(self.choice)
        tv.bind("<<TreeviewSelect>>", lambda e: self._on_choose(tv))
        tv.bind("<Double-1>", lambda e: self.start_selected())
        box = ttk.LabelFrame(p, text="하는 방법", padding=8)
        box.pack(fill="both", expand=True, pady=(8, 0))
        self.howto = ttk.Label(box, justify="left", wraplength=590)
        self.howto.pack(anchor="nw")
        foot = ttk.Label(p, foreground=C_GRAY,
                         text="판정은 눈을 감기 시작하는 순간이 기준이며, 박자와 무관한 깜빡임은 감점되지 않습니다.")
        foot.pack(anchor="w", pady=(6, 0))
        if isinstance(self.app.tracker, SimTracker):
            ttk.Label(p, text="[시험 모드] 스페이스바 = 눈 깜빡임", foreground=C_RED).pack(anchor="w")
        self._on_choose(tv)
        self.btn_start.config(text="시작(S)", underline=3)
        self.btn_start.state(["!disabled"])
        self.btn_select.state(["disabled"])
        self.btn_close.config(text="닫기(Esc)")
        tv.focus_set()

    @staticmethod
    def _record_text(acc):
        if acc is None:
            return "-"
        return "%d%% (%s)" % (round(acc), R.rank_of(acc))

    def _on_choose(self, tv):
        sel = tv.selection()
        if sel:
            self.choice = sel[0]
        if self.choice == S.MEDLEY:
            lines = ["세 게임을 쉬지 않고 이어서 합니다. 게임 사이에 %g초씩 쉬는 시간이 있습니다." % INTERLUDE,
                     "결과는 게임별 정확도와 전체 판정으로 보여 줍니다."]
        else:
            lines = S.make_stage(self.choice).howto
        self.howto.config(text="\n".join("%d. %s" % (i + 1, t) for i, t in enumerate(lines)))

    # ------------------------------------------------------------------ 시작
    def start_selected(self):
        if self.mode not in ("select", "result"):
            return
        keys = list(S.ORDER) if self.choice == S.MEDLEY else [self.choice]
        self.queue = keys
        self.played = []
        self.app.audio.volume = self.app.settings.volume
        self._start_next()

    def _start_next(self):
        key = self.queue.pop(0)
        st = S.make_stage(key)
        s = self.app.settings
        self.stage = st
        self.scene = make_scene(self.sprites, st)
        self.judge = R.Judge(st.notes, 0.0, st.beat_sec, offset=s.latency_offset,
                             slack=R.frame_slack(self.app.tracker.frame_dt))
        self.app.audio.prepare([st.hit_sound, "dull"])
        t0 = self.app.audio.play_stage(st)
        if t0 is None:                     # 소리를 낼 수 없으면 화면만으로 진행
            t0 = time.perf_counter() + 0.3
        self.t0 = t0
        for c in st.cues:
            c.time = t0 + c.beat * st.beat_sec
        for n in st.notes:
            n.time = t0 + n.beat * st.beat_sec
        while not self._blinks.empty():
            self._blinks.get_nowait()
        self._listen()
        self._popup = None
        self.hits = []
        self.mode = "playing"
        self._show_canvas()
        self.btn_start.state(["disabled"])
        self.btn_select.state(["disabled"])
        self.btn_close.config(text="중단(Esc)")
        self.focus_set()
        self._update_status()

    def _finish_stage(self, now):
        self.judge.poll(float("inf"))
        sm = self.judge.summary(len(self.stage.sections))
        self.played.append((self.stage, sm))
        self.app.monitor.mark_played(time.perf_counter())
        if self.queue:
            self.mode = "interlude"
            self._interlude_end = now + INTERLUDE
            self._next_stage_preview = S.make_stage(self.queue[0])
            self.app.audio.play_jingle(JINGLES[R.rank_level(sm["accuracy"])])
            return
        self.mode = "result"
        self._stop_listening()
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
            for res in self.judge.poll(now):
                self._on_result(res, now, quiet=True)
            if now - self.t0 >= self.stage.seconds:
                self._finish_stage(now)
            else:
                self._draw(now)
        elif self.mode == "interlude":
            while not self._blinks.empty():
                self._blinks.get_nowait()
            if now >= self._interlude_end:
                self._start_next()
            else:
                self._draw_interlude(now)
        self._update_cam_label()
        self._after = self.after(16, self._tick)

    def _on_result(self, res, now, quiet=False):
        self.hits.append((now, res))
        if not quiet:
            if res.grade == R.OK:
                self.app.audio.play_sfx(self.stage.hit_sound, soft=True)
                self.app.audio.play_sfx("dull")
            else:
                self.app.audio.play_sfx(self.stage.hit_sound)
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
        acc = self.judge.running_accuracy() if self.judge else None
        self.lbl_score.config(text="정확도 -" if acc is None else "정확도 %d%%" % round(acc))
        self.lbl_combo.config(text="콤보 %d" % (self.judge.combo if self.judge else 0))

    def _update_cam_label(self):
        tr = self.app.tracker
        if tr.error:
            self.lbl_cam.config(text="카메라 오류", fg=C_RED)
        elif tr.face_visible:
            self.lbl_cam.config(text="얼굴 인식됨", fg=C_INK)
        else:
            self.lbl_cam.config(text="얼굴이 보이지 않습니다", fg=C_RED)

    # ------------------------------------------------------------------ 그리기
    def _draw(self, now):
        c = self.stage_canvas
        c.delete("all")
        st = self.stage
        beat = (now - self.t0) / st.beat_sec
        view = View(now, beat, self.app.tracker.eye_closed, self.hits)
        self.scene.draw(c, view)

        # 머리말
        c.create_rectangle(0, 0, STAGE_W, 26, fill=C_LIGHT, outline="")
        c.create_line(0, 26, STAGE_W, 26, fill=C_GRAY)
        c.create_text(10, 13, anchor="w", font=bold_font(10), text=st.title, fill=C_NAVY)
        if beat < S.COUNT_IN:
            sub = "준비 - %d" % (S.COUNT_IN - int(beat)) if beat >= 0 else "준비"
        elif beat >= st.length:
            sub = "끝"
        else:
            sub = self.scene.phase_text(beat) or st.section_at(beat)
        c.create_text(120, 13, anchor="w", font=plain_font(9), text=sub, fill=C_INK)
        done = sum(1 for m in self.judge.matched if m is not None)
        c.create_text(STAGE_W - 10, 13, anchor="e", font=plain_font(9),
                      text="%d / %d" % (done, len(st.notes)), fill=C_INK)

        # 판정 표시
        if self._popup and now < self._popup[3]:
            text, subtxt, color, _ = self._popup
            x, y = self.scene.popup_pos
            w = 70
            c.create_rectangle(x - w, y - 16, x + w, y + (30 if subtxt else 14), fill=C_WHITE, outline=color)
            c.create_text(x, y - 1, text=text, font=bold_font(13), fill=color)
            if subtxt:
                c.create_text(x, y + 19, text=subtxt, font=plain_font(8), fill=color)

        self._draw_lane(c, now, beat)

    def _draw_lane(self, c, now, beat):
        st = self.stage
        c.create_rectangle(0, SCENE_BOT, STAGE_W, STAGE_H, fill=C_WHITE, outline="")
        c.create_line(0, SCENE_BOT, STAGE_W, SCENE_BOT, fill=C_GRAY)
        if beat < S.COUNT_IN:
            for i in range(S.COUNT_IN):
                x = STAGE_W // 2 - 45 + i * 30
                c.create_oval(x - 7, 273 - 7, x + 7, 273 + 7, outline=C_INK,
                              fill=C_NAVY if beat >= i else C_WHITE)
            return
        page = max(0, int((beat - S.COUNT_IN) // S.PAGE_BEATS))
        base = S.COUNT_IN + S.PAGE_BEATS * page
        px = (LANE_X1 - LANE_X0) / S.PAGE_BEATS

        def bx(b):
            return LANE_X0 + (b - base) * px

        def on_page(b):
            return base - 1e-6 <= b <= base + S.PAGE_BEATS + 1e-6

        mid = (LANE_Y0 + LANE_Y1) // 2
        c.create_rectangle(LANE_X0, LANE_Y0, LANE_X1, mid, fill=C_LIGHT, outline=C_GRAY)
        c.create_rectangle(LANE_X0, mid, LANE_X1, LANE_Y1, fill=C_WHITE, outline=C_GRAY)
        for k in range(S.PAGE_BEATS + 1):
            x = LANE_X0 + k * px
            c.create_line(x, LANE_Y0 if k % 4 == 0 else mid - 4, x, LANE_Y1, fill=C_GRAY)
        c.create_text(LANE_X0 - 6, (LANE_Y0 + mid) // 2, anchor="e", text="신호", font=plain_font(8), fill=C_GRAY)
        c.create_text(LANE_X0 - 6, (mid + LANE_Y1) // 2, anchor="e", text="나", font=plain_font(8), fill=C_GRAY)
        cy = (LANE_Y0 + mid) // 2
        for q in st.cues:
            if on_page(q.beat) and now >= q.time:
                x = bx(q.beat)
                c.create_rectangle(x - 4, cy - 4, x + 4, cy + 4, fill=C_GRAY, outline=C_GRAY)
        ny = (mid + LANE_Y1) // 2
        show_guide = self.app.settings.show_guide
        for i, n in enumerate(st.notes):
            if not on_page(n.beat):
                continue
            x = bx(n.beat)
            m = self.judge.matched[i]
            if m is not None:
                col = GRADE_COLOR[m.grade]
                if m.grade == R.MISS:
                    c.create_line(x - 6, ny - 6, x + 6, ny + 6, fill=col, width=2)
                    c.create_line(x - 6, ny + 6, x + 6, ny - 6, fill=col, width=2)
                else:
                    c.create_rectangle(x - 6, ny - 6, x + 6, ny + 6, fill=col, outline=col)
                    c.create_text(x, LANE_Y1 + 8, text="%+d" % round(m.dt * 1000), font=plain_font(7), fill=col)
            elif show_guide and beat >= n.reveal:
                c.create_rectangle(x - 6, ny - 6, x + 6, ny + 6, outline=C_INK, dash=(2, 2))
        x = max(LANE_X0, min(LANE_X1, bx(beat)))
        c.create_line(x, LANE_Y0 - 3, x, LANE_Y1 + 2, fill=C_INK, width=2)

    def _draw_interlude(self, now):
        c = self.stage_canvas
        c.delete("all")
        last_stage, sm = self.played[-1]
        nxt = self._next_stage_preview
        c.create_rectangle(0, 0, STAGE_W, 26, fill=C_LIGHT, outline="")
        c.create_line(0, 26, STAGE_W, 26, fill=C_GRAY)
        c.create_text(10, 13, anchor="w", font=bold_font(10), text="메들리 %d / %d" % (len(self.played), len(self.played) + len(self.queue)), fill=C_NAVY)
        c.create_text(STAGE_W // 2, 70, text="%s: %d%% (%s)" % (last_stage.title, round(sm["accuracy"]), sm["rank"]),
                      font=bold_font(12), fill=C_INK)
        c.create_text(STAGE_W // 2, 130, text="다음 게임: %s" % nxt.title, font=bold_font(14), fill=C_NAVY)
        for i, t in enumerate(nxt.howto[:2]):
            c.create_text(STAGE_W // 2, 170 + i * 22, text=t, font=plain_font(9), fill=C_INK)
        left = max(0, self._interlude_end - now)
        c.create_text(STAGE_W // 2, 250, text="%d초 뒤 시작" % (int(left) + 1), font=plain_font(10), fill=C_GRAY)

    # ------------------------------------------------------------------ 결과
    def show_result(self):
        s = self.app.settings
        medley = len(self.played) > 1
        if medley:
            sm = R.combine([x[1] for x in self.played])
            key, names = S.MEDLEY, [x[0].title for x in self.played]
            title = "메들리"
        else:
            st, sm = self.played[0]
            key, names, title = st.key, st.sections, st.title
            s.last_stage = st.key
        records = dict(s.records or {})
        new_best = sm["accuracy"] > records.get(key, -1)
        if new_best:
            records[key] = round(sm["accuracy"], 1)
        s.records = records
        s.save()
        self.app.audio.play_jingle(JINGLES[R.rank_level(sm["accuracy"])])

        p = self._show_panel()
        head = ttk.Frame(p)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(head, text="%s 결과: %s" % (title, sm["rank"]), font=bold_font(13)).pack(side="left")
        if new_best:
            ttk.Label(head, text="최고 기록", foreground=C_NAVY, font=bold_font(9)).pack(side="right")

        box = ttk.LabelFrame(p, text="판정", padding=(8, 4))
        box.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        for i, g in enumerate(R.GRADES):
            ttk.Label(box, text=R.LABEL[g], width=8).grid(row=i, column=0, sticky="w")
            ttk.Label(box, text="%d / %d" % (sm["counts"][g], sm["total"])).grid(row=i, column=1, sticky="e")
        ttk.Label(box, text="정확도").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Label(box, text="%.0f%%" % sm["accuracy"], font=bold_font(9)).grid(row=4, column=1, sticky="e", pady=(4, 0))
        ttk.Label(box, text="최고 콤보").grid(row=5, column=0, sticky="w")
        ttk.Label(box, text=str(sm["best_combo"])).grid(row=5, column=1, sticky="e")

        sec = ttk.LabelFrame(p, text="게임별 정확도" if medley else "구간별 정확도", padding=(8, 4))
        sec.grid(row=1, column=1, sticky="nsew")
        for i, (name, acc) in enumerate(zip(names, sm["sections"])):
            ttk.Label(sec, text=name, width=14).grid(row=i, column=0, sticky="w")
            pb = ttk.Progressbar(sec, length=200, maximum=100, value=acc or 0)
            pb.grid(row=i, column=1, padx=6, pady=1)
            ttk.Label(sec, text="-" if acc is None else "%d%%" % round(acc), width=5).grid(row=i, column=2, sticky="e")
        ttk.Label(sec, text="\n".join(R.feedback(sm, names)), wraplength=380, justify="left").grid(
            row=len(names), column=0, columnspan=3, sticky="w", pady=(4, 0))

        tbox = ttk.LabelFrame(p, text="타이밍 분포 (박자 기준, ms)", padding=(8, 4))
        tbox.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        hist = tk.Canvas(tbox, width=300, height=64, bg=C_WHITE, highlightthickness=1, highlightbackground=C_GRAY)
        hist.grid(row=0, column=0, rowspan=3, sticky="w")
        self._draw_hist(hist, sm["dts"])
        if sm["mean_dt"] is None:
            txt = "입력이 감지되지 않았습니다. 얼굴 위치와 조명을 확인하세요."
        else:
            ms = sm["mean_dt"] * 1000
            txt = "평균 %+d ms (%s), 편차 ±%d ms" % (round(ms), "늦은 편" if ms > 0 else "빠른 편",
                                                round((sm["sd"] or 0) * 1000))
        ttk.Label(tbox, text=txt, wraplength=290).grid(row=0, column=1, sticky="w", padx=(10, 0))
        if sm["stray"]:
            ttk.Label(tbox, text="박자와 무관한 깜빡임 %d회 (감점 없음)" % sm["stray"],
                      foreground=C_GRAY).grid(row=1, column=1, sticky="w", padx=(10, 0))
        self._shift = R.suggest_offset_shift(sm)
        self._shift_row = ttk.Frame(tbox)
        self._shift_row.grid(row=2, column=1, sticky="w", padx=(10, 0))
        if self._shift is not None:
            ttk.Label(self._shift_row, text="입력이 평균 %+d ms 치우침" % round(self._shift * 1000)).pack(side="left")
            ttk.Button(self._shift_row, text="보정에 반영(A)", underline=7, command=self._apply_shift).pack(side="left", padx=6)
            self.bind("<a>", lambda e: self._apply_shift())
        else:
            ttk.Label(self._shift_row, text="잠시 먼 곳을 바라보며 눈을 쉬어 주세요.", foreground=C_GRAY).pack(side="left")
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=3)

        self.btn_start.config(text="다시 하기(R)", underline=6)
        self.btn_start.state(["!disabled"])
        self.btn_select.state(["!disabled"])
        self.btn_close.config(text="닫기(Esc)")
        self.choice = key
        self.app.refresh_status()

    def _apply_shift(self):
        if self._shift is None:
            return
        s = self.app.settings
        s.latency_offset += self._shift
        s.save()
        self._shift = None
        self.app.refresh_status()
        for ch in self._shift_row.winfo_children():
            ch.destroy()
        ttk.Label(self._shift_row, text="보정값을 %+d ms로 갱신했습니다." % round(s.latency_offset * 1000)).pack(side="left")

    def _draw_hist(self, c, dts):
        W, H = 300, 64
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
            h = (H - 26) * n / top
            c.create_rectangle(x0 + 1, H - 16 - h, x0 + bw - 1, H - 16, fill=C_NAVY if n else C_WHITE, outline=C_GRAY)
        cx = 10 + (0 - lo) / (hi - lo) * (W - 20)
        c.create_line(cx, 4, cx, H - 12, fill=C_RED)
        c.create_text(10, H - 7, anchor="w", text="빠름", font=plain_font(7))
        c.create_text(W - 10, H - 7, anchor="e", text="느림", font=plain_font(7))
        c.create_text(cx, H - 7, text="0", font=plain_font(7))
