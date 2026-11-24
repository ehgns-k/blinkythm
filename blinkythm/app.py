"""메인 창(상태/설정), 트레이, 알림 스케줄러."""
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

from . import APP_NAME, __version__, winenv
from .audio import Audio
from .config import Settings
from .monitor import UsageMonitor
from .tracker import CameraTracker, SimTracker
from .ui_common import setup_style, center_on, fmt_hms, bold_font
from .ui_game import GameWindow
from .ui_prompt import PromptDialog
from .ui_wizard import Wizard


class App:
    def __init__(self, sim=False, demo=False, background=False):
        winenv.enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("Blinkythm - 눈 깜빡임 리듬")
        self.root.resizable(False, False)
        setup_style(self.root)

        self.settings = Settings.load()
        self.sim = sim
        self.demo = demo
        if demo:
            from . import monitor as monitor_mod
            monitor_mod.MIN_VISIBLE = 5.0
            self.settings.screen_minutes = 0.2
            self.settings.blink_threshold = 99.0
            self.settings.cooldown_minutes = 0.3
            self.settings.snooze_minutes = 0.2
            self.settings.first_run_done = True
            self.settings.save = lambda: None      # 시험용 값이 저장되지 않게
        self.monitor = UsageMonitor(self.settings)
        self.tracker = (SimTracker(self.monitor, self.settings.latency_offset) if sim
                        else CameraTracker(self.monitor, self.settings.camera_index))
        self.audio = Audio(self.settings.volume)
        self.game = None
        self.prompt = None
        self.wizard = None
        self.tray = None
        self._ui_q = queue.Queue()

        self._build_menu()
        self._build_body()
        self._setup_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_main)
        center_on(self.root)

        self.tracker.start()
        self.root.after(100, self._pump)
        self.root.after(500, self._tick)
        if not self.settings.first_run_done:
            self.root.after(300, self.open_wizard)
        elif background:
            self.root.after(50, self.hide_main)

    # ------------------------------------------------------------------ 구성
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="지금 한 판 하기(P)", underline=9, command=lambda: self.open_game())
        f.add_command(label="보정 마법사(W)...", underline=7, command=self.open_wizard)
        f.add_separator()
        f.add_command(label="창 숨기기(H)", underline=6, command=self.hide_main)
        f.add_command(label="끝내기(X)", underline=4, command=self.quit)
        m.add_cascade(label="파일(F)", underline=3, menu=f)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Blinkythm 정보(A)...", underline=13, command=self._about)
        m.add_cascade(label="도움말(H)", underline=4, menu=h)
        self.root.config(menu=m)

    def _build_body(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        st = ttk.Frame(nb, padding=10)
        se = ttk.Frame(nb, padding=10)
        nb.add(st, text="상태")
        nb.add(se, text="설정")

        # --- 상태 탭
        cam = ttk.LabelFrame(st, text="카메라", padding=8)
        cam.pack(fill="x")
        self.v_cam = tk.StringVar()
        self.v_face = tk.StringVar()
        for i, (lbl, var) in enumerate((("상태:", self.v_cam), ("얼굴 인식:", self.v_face))):
            ttk.Label(cam, text=lbl, width=12).grid(row=i, column=0, sticky="w")
            ttk.Label(cam, textvariable=var, wraplength=330).grid(row=i, column=1, sticky="w")
        eye = ttk.LabelFrame(st, text="눈 건강 지표", padding=8)
        eye.pack(fill="x", pady=8)
        self.v_screen = tk.StringVar()
        self.v_rate = tk.StringVar()
        self.v_verdict = tk.StringVar()
        ttk.Label(eye, text="화면 사용 시간:", width=16).grid(row=0, column=0, sticky="w")
        ttk.Label(eye, textvariable=self.v_screen).grid(row=0, column=1, sticky="w")
        self.bar_screen = ttk.Progressbar(eye, length=330, maximum=100)
        self.bar_screen.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        ttk.Label(eye, text="분당 눈 깜빡임:", width=16).grid(row=2, column=0, sticky="w")
        ttk.Label(eye, textvariable=self.v_rate).grid(row=2, column=1, sticky="w")
        ttk.Label(eye, textvariable=self.v_verdict, wraplength=330, foreground="#808080").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        row = ttk.Frame(st)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="지금 한 판 하기(P)", underline=9, command=lambda: self.open_game()).pack(side="left")
        ttk.Button(row, text="보정 마법사(W)...", underline=7, command=self.open_wizard).pack(side="left", padx=6)
        self.var_monitor = tk.BooleanVar(value=self.settings.monitoring)
        ttk.Checkbutton(st, text="눈 깜빡임 모니터링 사용", variable=self.var_monitor,
                        command=self._toggle_monitor).pack(anchor="w", pady=(10, 0))

        # --- 설정 탭
        g = ttk.LabelFrame(se, text="알림 조건", padding=8)
        g.pack(fill="x")
        self.sp = {}
        spec = [
            ("screen_minutes", "화면 사용 시간 기준 (분)", 1, 180),
            ("blink_threshold", "분당 깜빡임 기준 (회)", 1, 30),
            ("away_seconds", "자리비움 인식 (초)", 10, 600),
            ("snooze_minutes", "'다시 알림' 간격 (분)", 1, 60),
            ("cooldown_minutes", "한 판 후 알림 중단 (분)", 1, 240),
            ("camera_index", "카메라 장치 번호", 0, 9),
        ]
        for i, (key, label, lo, hi) in enumerate(spec):
            ttk.Label(g, text=label, width=26).grid(row=i, column=0, sticky="w", pady=1)
            v = tk.StringVar(value=str(self._num(getattr(self.settings, key))))
            ttk.Spinbox(g, from_=lo, to=hi, width=7, textvariable=v).grid(row=i, column=1, sticky="w")
            self.sp[key] = (v, lo, hi)
        o = ttk.LabelFrame(se, text="옵션", padding=8)
        o.pack(fill="x", pady=8)
        self.var_dnd = tk.BooleanVar(value=self.settings.respect_dnd)
        self.var_guide = tk.BooleanVar(value=self.settings.show_guide)
        self.var_auto = tk.BooleanVar(value=winenv.is_autostart())
        ttk.Checkbutton(o, text="전체 화면/발표 중에는 알리지 않음", variable=self.var_dnd).pack(anchor="w")
        ttk.Checkbutton(o, text="게임에서 깜빡일 위치 가이드 표시", variable=self.var_guide).pack(anchor="w")
        cb = ttk.Checkbutton(o, text="Windows 시작 시 자동 실행", variable=self.var_auto)
        cb.pack(anchor="w")
        if not winenv.IS_WIN:
            cb.state(["disabled"])
        vr = ttk.Frame(o)
        vr.pack(fill="x", pady=(6, 0))
        ttk.Label(vr, text="소리 크기").pack(side="left")
        self.var_vol = tk.DoubleVar(value=self.settings.volume)
        ttk.Scale(vr, from_=0.0, to=1.0, variable=self.var_vol, length=160).pack(side="left", padx=8)
        row2 = ttk.Frame(se)
        row2.pack(fill="x")
        ttk.Button(row2, text="적용(A)", underline=3, command=self.apply_settings).pack(side="right")
        ttk.Button(row2, text="기본값(D)", underline=4, command=self.reset_defaults).pack(side="right", padx=6)
        self.v_offset = tk.StringVar()
        ttk.Label(se, textvariable=self.v_offset, foreground="#808080").pack(anchor="w", pady=(6, 0))

        # --- 상태 표시줄
        self.v_bar = tk.StringVar()
        tk.Label(self.root, textvariable=self.v_bar, relief="sunken", anchor="w", bd=1).pack(
            side="bottom", fill="x", padx=8, pady=(0, 8))

    @staticmethod
    def _num(x):
        return int(x) if float(x).is_integer() else x

    # ------------------------------------------------------------------ 설정
    def apply_settings(self):
        s = self.settings
        for key, (v, lo, hi) in self.sp.items():
            try:
                val = float(v.get())
            except ValueError:
                messagebox.showwarning("설정", "숫자를 입력하세요.", parent=self.root)
                return
            val = max(lo, min(hi, val))
            setattr(s, key, int(val) if key == "camera_index" else val)
            v.set(str(self._num(getattr(s, key))))
        s.respect_dnd = self.var_dnd.get()
        s.show_guide = self.var_guide.get()
        s.volume = round(self.var_vol.get(), 2)
        if winenv.IS_WIN:
            winenv.set_autostart(self.var_auto.get())
        s.save()
        if not self.sim and s.camera_index != self.tracker.camera_index:
            self.tracker.restart(s.camera_index)
        self.refresh_status()

    def reset_defaults(self):
        d = Settings()
        for key in self.sp:
            self.sp[key][0].set(str(self._num(getattr(d, key))))
        self.var_dnd.set(d.respect_dnd)
        self.var_guide.set(d.show_guide)
        self.var_vol.set(d.volume)

    def _toggle_monitor(self):
        self.settings.monitoring = self.var_monitor.get()
        self.settings.save()
        self.refresh_status()

    # ------------------------------------------------------------------ 창 관리
    def show_main(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_main(self):
        if self.tray:
            self.root.withdraw()
        else:
            self.root.iconify()

    def quit(self):
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.tracker.stop()
        self.audio.stop()
        self.settings.save()
        self.root.destroy()

    def post(self, fn):
        """다른 스레드(트레이)에서 UI 작업을 안전하게 맡긴다."""
        self._ui_q.put(fn)

    def _pump(self):
        while True:
            try:
                self._ui_q.get_nowait()()
            except queue.Empty:
                break
        self.root.after(100, self._pump)

    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            return
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((3, 14, 61, 50), fill="white", outline="black", width=3)
        d.ellipse((22, 20, 42, 44), fill=(0, 0, 128, 255))
        Item = pystray.MenuItem
        menu = pystray.Menu(
            Item("Blinkythm 열기", lambda: self.post(self.show_main), default=True),
            Item("지금 한 판 하기", lambda: self.post(lambda: self.open_game())),
            Item("모니터링 사용", lambda: self.post(self._tray_toggle), checked=lambda i: self.settings.monitoring),
            pystray.Menu.SEPARATOR,
            Item("끝내기", lambda: self.post(self.quit)),
        )
        try:
            self.tray = pystray.Icon(APP_NAME, img, "Blinkythm", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = None

    def _tray_toggle(self):
        self.var_monitor.set(not self.settings.monitoring)
        self._toggle_monitor()

    def _about(self):
        messagebox.showinfo(
            "Blinkythm 정보",
            "Blinkythm %s\n\n웹캠으로 눈 깜빡임 빈도를 살피다가, 화면을 오래 보고 깜빡임이 줄면 "
            "짧은 리듬 게임을 제안합니다.\n영상은 컴퓨터 안에서만 처리되며 저장·전송되지 않습니다.\n\n"
            "게임: 등대 신호, 올빼미 합창, 깜빡 사진관\n"
            "그림과 소리는 모두 이 프로그램을 위해 코드로 만든 것입니다(tools/make_assets.py)." % __version__,
            parent=self.root)

    # ------------------------------------------------------------------ 게임/마법사
    def open_game(self, stage=None):
        if self.game is not None:
            self.game.lift()
            return
        if self.wizard is not None:
            return
        self.game = GameWindow(self, stage)

    def game_closed(self, win):
        if self.game is win:
            self.game = None

    def open_wizard(self):
        if self.wizard is not None or self.game is not None:
            return
        self.show_main()
        self.wizard = Wizard(self, self._wizard_done)

    def _wizard_done(self, ok):
        self.wizard = None
        self.var_monitor.set(self.settings.monitoring)
        self.refresh_status()
        if ok and self.settings.monitoring and not self.demo:
            self.hide_main()

    # ------------------------------------------------------------------ 주기 작업
    def refresh_status(self):
        s = self.settings
        tr = self.tracker
        now = time.perf_counter()
        if tr.error:
            self.v_cam.set("오류 - " + tr.error)
        elif self.sim:
            self.v_cam.set("시험 모드(카메라 없음)")
        else:
            self.v_cam.set("연결됨 (장치 %d)" % tr.camera_index)
        self.v_face.set("예" if tr.face_visible else "아니오")
        sec = self.monitor.screen_seconds(now)
        self.v_screen.set("%s / %d분" % (fmt_hms(sec), s.screen_minutes))
        self.bar_screen["value"] = min(100, sec / (s.screen_minutes * 60) * 100)
        rate = self.monitor.blink_rate(now)
        if rate is None:
            self.v_rate.set("측정 중...")
            self.v_verdict.set("최근 1분 동안 얼굴이 충분히 보이면 계산됩니다.")
        else:
            self.v_rate.set("%.1f 회" % rate)
            self.v_verdict.set("알림 기준: 분당 %g회 미만. 일반 평균은 15~20회이며, 화면에 집중하면 크게 줄 수 있습니다." % s.blink_threshold)
        self.v_offset.set("입력 지연 보정값: %+d ms%s" % (
            round(s.latency_offset * 1000), "" if s.first_run_done else "  (마법사에서 측정하세요)"))
        if not s.monitoring:
            self.v_bar.set("모니터링 중지됨")
        elif self.game is not None:
            self.v_bar.set("게임 중")
        else:
            self.v_bar.set("모니터링 중")

    def _tick(self):
        try:
            if self.root.state() != "withdrawn" and self.root.state() != "iconic":
                self.refresh_status()
            self.monitor.paused = (not self.settings.monitoring) or self.game is not None or self.wizard is not None
            if (self.settings.monitoring and self.prompt is None and self.game is None
                    and self.wizard is None and not self.tracker.error):
                now = time.perf_counter()
                dnd = self.settings.respect_dnd and winenv.is_busy()
                if self.monitor.should_prompt(now, dnd):
                    self._show_prompt(now)
        finally:
            self.root.after(500, self._tick)

    def _show_prompt(self, now):
        minutes = self.monitor.screen_seconds(now) / 60.0
        rate = self.monitor.blink_rate(now) or 0.0

        def done():
            self.prompt = None

        def play():
            done()
            self.open_game()

        def snooze():
            self.monitor.snooze(time.perf_counter())
            done()

        def today():
            self.monitor.suppressed_today = True
            done()

        self.prompt = PromptDialog(self, minutes, rate, play, snooze, today)

    def run(self):
        self.root.mainloop()
