"""첫 실행/재보정 마법사: 카메라 확인 -> 타이밍 보정 -> 완료. 클래식 설치 마법사 형태."""
import time
import tkinter as tk
from tkinter import ttk

from . import rhythm as R
from . import winenv
from .tracker import SimTracker
from .ui_common import C_WHITE, bold_font, center_on


class Wizard(tk.Toplevel):
    def __init__(self, app, on_done):
        super().__init__(app.root)
        self.app = app
        self.on_done = on_done
        self.title("Blinkythm 설정 마법사")
        self.resizable(False, False)
        self.transient(app.root)
        self.offset = None
        self.page = 0
        self._cal_onsets = []
        self._cal_t0 = None
        self._cal_running = False
        self._poll = None
        self._face_since = None

        head = tk.Frame(self, bg=C_WHITE, height=58)
        head.pack(fill="x")
        head.pack_propagate(False)
        self.h_title = tk.Label(head, bg=C_WHITE, font=bold_font(9), anchor="w")
        self.h_title.pack(fill="x", padx=14, pady=(10, 0))
        self.h_sub = tk.Label(head, bg=C_WHITE, anchor="w", justify="left")
        self.h_sub.pack(fill="x", padx=30)
        ttk.Separator(self).pack(fill="x")

        self.body = ttk.Frame(self, padding=(16, 12))
        self.body.pack(fill="both", expand=True)
        self.body.configure(width=500, height=250)
        self.body.pack_propagate(False)

        ttk.Separator(self).pack(fill="x")
        btns = ttk.Frame(self, padding=(10, 8))
        btns.pack(fill="x")
        self.b_cancel = ttk.Button(btns, text="취소", width=10, command=self.cancel)
        self.b_cancel.pack(side="right")
        self.b_next = ttk.Button(btns, text="다음(N) >", width=10, command=self.next)
        self.b_next.pack(side="right", padx=(0, 6))
        self.b_back = ttk.Button(btns, text="< 뒤로(B)", width=10, command=self.back)
        self.b_back.pack(side="right", padx=(0, 2))

        self.pages = [self._page_camera, self._page_calib, self._page_finish]
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.app.tracker.set_game_mode(True)
        self.show(0)
        center_on(self, app.root, 520, 400)
        self.grab_set()

    # ------------------------------------------------------------------ 공통
    def show(self, n):
        self.page = n
        if self._poll:
            self.after_cancel(self._poll)
            self._poll = None
        for w in self.body.winfo_children():
            w.destroy()
        self.pages[n]()
        self.b_back.state(["!disabled" if n > 0 else "disabled"])
        self.b_next.config(text="마침" if n == len(self.pages) - 1 else "다음(N) >")

    def next(self):
        if self.page == len(self.pages) - 1:
            self.finish()
        else:
            self.show(self.page + 1)

    def back(self):
        if self.page > 0 and not self._cal_running:
            self.show(self.page - 1)

    def cancel(self):
        self._cleanup()
        self.destroy()
        self.on_done(False)

    def _cleanup(self):
        if self._poll:
            self.after_cancel(self._poll)
            self._poll = None
        self.app.tracker.remove_listener(self._on_blink)
        self.app.audio.stop()
        self.app.tracker.set_game_mode(False)

    def header(self, title, sub):
        self.h_title.config(text=title)
        self.h_sub.config(text=sub)

    # ------------------------------------------------------------------ 1. 카메라
    def _page_camera(self):
        self.header("카메라 확인", "웹캠으로 눈 깜빡임을 감지합니다.")
        b = self.body
        ttk.Label(b, wraplength=470, justify="left",
                  text="영상은 이 컴퓨터 안에서 눈의 열림 정도를 계산하는 데만 쓰이며, 저장하거나 외부로 전송하지 않습니다.\n"
                       "얼굴이 화면 중앙에 오도록 앉고, 밝은 곳에서 진행하세요.").pack(anchor="w")
        box = ttk.LabelFrame(b, text="카메라", padding=10)
        box.pack(fill="x", pady=12)
        r1 = ttk.Frame(box)
        r1.pack(fill="x")
        ttk.Label(r1, text="장치 번호:").pack(side="left")
        self.cam_var = tk.IntVar(value=self.app.settings.camera_index)
        ttk.Spinbox(r1, from_=0, to=5, width=4, textvariable=self.cam_var).pack(side="left", padx=6)
        ttk.Button(r1, text="다시 연결", command=self._reconnect).pack(side="left")
        self.cam_status = ttk.Label(box, text="")
        self.cam_status.pack(anchor="w", pady=(8, 0))
        self.face_status = ttk.Label(box, text="")
        self.face_status.pack(anchor="w")
        r2 = ttk.Frame(box)
        r2.pack(fill="x", pady=(8, 0))
        ttk.Label(r2, text="눈 뜸 정도:").pack(side="left")
        self.ear_bar = ttk.Progressbar(r2, length=240, maximum=100)
        self.ear_bar.pack(side="left", padx=6)
        ttk.Label(b, text="눈을 한 번 깜빡여 보세요. 막대가 내려갔다 올라오면 정상입니다.").pack(anchor="w")
        self._face_since = None
        self.b_next.state(["disabled"])
        self._poll_camera()

    def _reconnect(self):
        self.app.settings.camera_index = int(self.cam_var.get())
        self.app.tracker.restart(self.app.settings.camera_index)
        self.app.tracker.set_game_mode(True)

    def _poll_camera(self):
        tr = self.app.tracker
        if tr.error:
            self.cam_status.config(text="상태: 오류 - " + tr.error, foreground="#800000", wraplength=440)
        else:
            self.cam_status.config(text="상태: 연결됨", foreground="")
        if tr.face_visible:
            self.face_status.config(text="얼굴: 인식됨")
            self._face_since = self._face_since or time.perf_counter()
        else:
            self.face_status.config(text="얼굴: 보이지 않음")
            self._face_since = None
        r = tr.ear_ratio
        self.ear_bar["value"] = 0 if r is None else min(100, r * 100 / 1.1)
        ok = self._face_since is not None and time.perf_counter() - self._face_since > 1.0
        self.b_next.state(["!disabled" if ok else "disabled"])
        self._poll = self.after(80, self._poll_camera)

    # ------------------------------------------------------------------ 2. 보정
    def _page_calib(self):
        self.header("타이밍 보정", "웹캠과 스피커의 지연을 측정해 판정을 맞춥니다.")
        b = self.body
        ttk.Label(b, wraplength=470, justify="left",
                  text="[시작]을 누르면 일정한 박자의 소리가 12번 납니다. 앞 4번은 듣기만 하고, "
                       "그 뒤로는 소리에 맞춰 눈을 한 번씩 깜빡이세요. 소리를 들은 뒤가 아니라 박자를 예상해서 "
                       "같은 순간에 눈을 감기 시작하는 느낌으로 하면 됩니다.").pack(anchor="w")
        box = ttk.LabelFrame(b, text="측정", padding=10)
        box.pack(fill="x", pady=12)
        self.cal_btn = ttk.Button(box, text="시작(S)", width=10, command=self._cal_start)
        self.cal_btn.pack(anchor="w")
        self.cal_prog = ttk.Progressbar(box, length=300, maximum=R.CAL_TICKS)
        self.cal_prog.pack(anchor="w", pady=8)
        self.cal_text = ttk.Label(box, text="", wraplength=440, justify="left")
        self.cal_text.pack(anchor="w")
        if isinstance(self.app.tracker, SimTracker):
            ttk.Label(b, text="[시험 모드] 스페이스바 = 눈 깜빡임", foreground="#800000").pack(anchor="w")
            self.bind("<space>", lambda e: self.app.tracker.press())
        if self.offset is None:
            self.b_next.state(["disabled"])
        if self.offset is not None:
            self.cal_text.config(text="이전 측정값: %+d ms" % round(self.offset * 1000))

    def _on_blink(self, onset):
        if self._cal_running:
            self._cal_onsets.append(onset)

    def _cal_start(self):
        if not self.app.audio.ok:
            self.cal_text.config(text="소리 장치를 사용할 수 없어 보정할 수 없습니다. 스피커/헤드폰 연결을 확인하세요.")
            return
        self.cal_btn.state(["disabled"])
        self.b_back.state(["disabled"])
        self.b_next.state(["disabled"])
        self._cal_onsets = []
        self.app.audio.volume = self.app.settings.volume
        ticks = [(k * R.CAL_BEAT, k % 4 == 0) for k in range(R.CAL_TICKS)]
        self._cal_t0 = self.app.audio.play_track(ticks, [], R.CAL_TICKS * R.CAL_BEAT)
        self._cal_running = True
        self.app.tracker.add_listener(self._on_blink)
        self.cal_text.config(text="앞 4박은 듣기만 하세요...")
        self._cal_tick()

    def _cal_tick(self):
        if self.page != 1:
            return
        now = time.perf_counter()
        el = now - self._cal_t0
        k = int(el / R.CAL_BEAT)
        self.cal_prog["value"] = min(R.CAL_TICKS, k)
        if k >= R.CAL_SKIP:
            n = len([o for o in self._cal_onsets if o - self._cal_t0 >= R.CAL_SKIP * R.CAL_BEAT - 0.2])
            self.cal_text.config(text="깜빡이세요! 감지된 깜빡임: %d회" % n)
        if el < R.CAL_TICKS * R.CAL_BEAT + 0.7:
            self._poll = self.after(40, self._cal_tick)
        else:
            self._cal_done()

    def _cal_done(self):
        self._cal_running = False
        self.cal_prog["value"] = R.CAL_TICKS
        self.app.tracker.remove_listener(self._on_blink)
        self.cal_btn.state(["!disabled"])
        self.cal_btn.config(text="다시 측정")
        self.b_back.state(["!disabled"])
        out = R.compute_offset(self._cal_onsets, self._cal_t0)
        if out is None:
            self.cal_text.config(text="깜빡임이 너무 적게 감지되었거나 박자가 일정하지 않았습니다. "
                                      "얼굴을 화면 중앙에 두고 조금 더 또렷하게 깜빡이며 다시 측정하세요.")
            self.b_next.state(["disabled"] if self.offset is None else ["!disabled"])
            return
        off, sd, n = out
        self.offset = off
        self.cal_text.config(text="측정 완료: 입력 지연 %+d ms (편차 ±%d ms, %d회 사용)" % (round(off * 1000), round(sd * 1000), n))
        self.b_next.state(["!disabled"])

    # ------------------------------------------------------------------ 3. 완료
    def _page_finish(self):
        self.header("설정 완료", "아래 옵션을 확인하고 [마침]을 누르세요.")
        b = self.body
        s = self.app.settings
        ttk.Label(b, wraplength=470, justify="left",
                  text="화면을 %d분 이상 보았고 최근 1분간 눈 깜빡임이 분당 %d회 미만이면 한 판 해 보라는 알림이 뜹니다. "
                       "조건은 나중에 [설정] 탭에서 바꿀 수 있습니다." % (s.screen_minutes, s.blink_threshold)).pack(anchor="w")
        box = ttk.LabelFrame(b, text="옵션", padding=10)
        box.pack(fill="x", pady=12)
        self.var_monitor = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="마침 후 눈 깜빡임 모니터링을 시작합니다", variable=self.var_monitor).pack(anchor="w")
        self.var_auto = tk.BooleanVar(value=winenv.is_autostart())
        cb = ttk.Checkbutton(box, text="Windows 시작 시 자동으로 실행합니다", variable=self.var_auto)
        cb.pack(anchor="w", pady=(6, 0))
        if not winenv.IS_WIN:
            cb.state(["disabled"])
        if self.offset is not None:
            ttk.Label(b, text="입력 지연 보정값: %+d ms" % round(self.offset * 1000)).pack(anchor="w")
        self.b_next.state(["!disabled"])

    def finish(self):
        s = self.app.settings
        if self.offset is not None:
            s.latency_offset = self.offset
        s.monitoring = bool(self.var_monitor.get())
        s.first_run_done = True
        s.save()
        if winenv.IS_WIN:
            winenv.set_autostart(bool(self.var_auto.get()))
        self._cleanup()
        self.destroy()
        self.on_done(True)
