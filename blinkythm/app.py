"""Main window (status/settings), tray icon and prompt scheduler."""
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

from . import APP_NAME, __version__, winenv
from .audio import Audio
from .config import Settings
from .monitor import UsageMonitor
from .tracker import CameraTracker, SimTracker
from .ui_common import setup_style, center_on, fmt_hms
from .ui_prompt import PromptDialog
from .ui_wizard import Wizard


class App:
    def __init__(self, sim=False, demo=False, background=False):
        winenv.enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("Blinkythm")
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
            self.settings.save = lambda: None      # keep demo values out of the saved settings
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

    # ------------------------------------------------------------------ layout
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Play now", underline=0, command=lambda: self.open_game())
        f.add_command(label="Calibration wizard...", underline=12, command=self.open_wizard)
        f.add_separator()
        f.add_command(label="Hide window", underline=0, command=self.hide_main)
        f.add_command(label="Exit", underline=1, command=self.quit)
        m.add_cascade(label="File", underline=0, menu=f)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="About Blinkythm...", underline=0, command=self._about)
        m.add_cascade(label="Help", underline=0, menu=h)
        self.root.config(menu=m)

    def _build_body(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        st = ttk.Frame(nb, padding=10)
        se = ttk.Frame(nb, padding=10)
        nb.add(st, text="Status")
        nb.add(se, text="Settings")

        # --- status tab
        cam = ttk.LabelFrame(st, text="Camera", padding=8)
        cam.pack(fill="x")
        self.v_cam = tk.StringVar()
        self.v_face = tk.StringVar()
        for i, (lbl, var) in enumerate((("Status:", self.v_cam), ("Face:", self.v_face))):
            ttk.Label(cam, text=lbl, width=12).grid(row=i, column=0, sticky="w")
            ttk.Label(cam, textvariable=var, wraplength=330).grid(row=i, column=1, sticky="w")
        eye = ttk.LabelFrame(st, text="Eye health", padding=8)
        eye.pack(fill="x", pady=8)
        self.v_screen = tk.StringVar()
        self.v_rate = tk.StringVar()
        self.v_verdict = tk.StringVar()
        ttk.Label(eye, text="Screen time:", width=16).grid(row=0, column=0, sticky="w")
        ttk.Label(eye, textvariable=self.v_screen).grid(row=0, column=1, sticky="w")
        self.bar_screen = ttk.Progressbar(eye, length=330, maximum=100)
        self.bar_screen.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        ttk.Label(eye, text="Blinks per minute:", width=16).grid(row=2, column=0, sticky="w")
        ttk.Label(eye, textvariable=self.v_rate).grid(row=2, column=1, sticky="w")
        ttk.Label(eye, textvariable=self.v_verdict, wraplength=330, foreground="#808080").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        row = ttk.Frame(st)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Play now", underline=0, command=lambda: self.open_game()).pack(side="left")
        ttk.Button(row, text="Calibration wizard...", underline=12, command=self.open_wizard).pack(side="left", padx=6)
        self.var_monitor = tk.BooleanVar(value=self.settings.monitoring)
        ttk.Checkbutton(st, text="Monitor blinking", variable=self.var_monitor,
                        command=self._toggle_monitor).pack(anchor="w", pady=(10, 0))

        # --- settings tab
        g = ttk.LabelFrame(se, text="Prompt conditions", padding=8)
        g.pack(fill="x")
        self.sp = {}
        spec = [
            ("screen_minutes", "Screen time before checking (min)", 1, 180),
            ("blink_threshold", "Blinks per minute below (count)", 1, 30),
            ("away_seconds", "Away after no face for (s)", 10, 600),
            ("snooze_minutes", "Snooze length (min)", 1, 60),
            ("cooldown_minutes", "Quiet time after a game (min)", 1, 240),
            ("camera_index", "Camera device number", 0, 9),
        ]
        for i, (key, label, lo, hi) in enumerate(spec):
            ttk.Label(g, text=label, width=26).grid(row=i, column=0, sticky="w", pady=1)
            v = tk.StringVar(value=str(self._num(getattr(self.settings, key))))
            ttk.Spinbox(g, from_=lo, to=hi, width=7, textvariable=v).grid(row=i, column=1, sticky="w")
            self.sp[key] = (v, lo, hi)
        o = ttk.LabelFrame(se, text="Options", padding=8)
        o.pack(fill="x", pady=8)
        self.var_dnd = tk.BooleanVar(value=self.settings.respect_dnd)
        self.var_guide = tk.BooleanVar(value=self.settings.show_guide)
        self.var_auto = tk.BooleanVar(value=winenv.is_autostart())
        ttk.Checkbutton(o, text="Stay quiet during fullscreen apps and presentations", variable=self.var_dnd).pack(anchor="w")
        ttk.Checkbutton(o, text="Show where to blink in games", variable=self.var_guide).pack(anchor="w")
        cb = ttk.Checkbutton(o, text="Start with Windows", variable=self.var_auto)
        cb.pack(anchor="w")
        if not winenv.IS_WIN:
            cb.state(["disabled"])
        vr = ttk.Frame(o)
        vr.pack(fill="x", pady=(6, 0))
        ttk.Label(vr, text="Volume").pack(side="left")
        self.var_vol = tk.DoubleVar(value=self.settings.volume)
        ttk.Scale(vr, from_=0.0, to=1.0, variable=self.var_vol, length=160).pack(side="left", padx=8)
        row2 = ttk.Frame(se)
        row2.pack(fill="x")
        ttk.Button(row2, text="Apply", underline=0, command=self.apply_settings).pack(side="right")
        ttk.Button(row2, text="Defaults", underline=0, command=self.reset_defaults).pack(side="right", padx=6)
        self.v_offset = tk.StringVar()
        ttk.Label(se, textvariable=self.v_offset, foreground="#808080").pack(anchor="w", pady=(6, 0))

        # --- status bar
        self.v_bar = tk.StringVar()
        tk.Label(self.root, textvariable=self.v_bar, relief="sunken", anchor="w", bd=1).pack(
            side="bottom", fill="x", padx=8, pady=(0, 8))

    @staticmethod
    def _num(x):
        return int(x) if float(x).is_integer() else x

    # ------------------------------------------------------------------ settings
    def apply_settings(self):
        s = self.settings
        for key, (v, lo, hi) in self.sp.items():
            try:
                val = float(v.get())
            except ValueError:
                messagebox.showwarning("Settings", "Please enter a number.", parent=self.root)
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

    # ------------------------------------------------------------------ windows
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
        if self.game is not None:
            self.game.close()
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
        """Queue UI work from another thread (the tray) to run on the Tk thread."""
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
            Item("Open Blinkythm", lambda: self.post(self.show_main), default=True),
            Item("Play now", lambda: self.post(lambda: self.open_game())),
            Item("Monitor blinking", lambda: self.post(self._tray_toggle), checked=lambda i: self.settings.monitoring),
            pystray.Menu.SEPARATOR,
            Item("Exit", lambda: self.post(self.quit)),
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
            "About Blinkythm",
            "Blinkythm %s\n\nWatches how often you blink through the webcam. After a long stretch at the screen "
            "with too few blinks, it suggests a short rhythm game.\nVideo is processed on this computer only and is never saved or sent.\n\n"
            "Games: Lighthouse, Owl Choir, Blink Studio\n"
            "All art and sound were generated for this program (tools/make_assets.py)." % __version__,
            parent=self.root)

    # ------------------------------------------------------------------ game and wizard
    def open_game(self, stage=None, from_prompt=False):
        """Open the game window (pygame-ce). Tk events keep running inside it until it closes."""
        if self.game is not None or self.wizard is not None:
            return
        from .game.app import GameApp
        self.game = GameApp(self, stage, from_prompt)
        self.refresh_status()
        try:
            self.game.run()
        finally:
            self.game = None
            try:
                self.refresh_status()
            except tk.TclError:
                pass

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

    # ------------------------------------------------------------------ periodic work
    def refresh_status(self):
        s = self.settings
        tr = self.tracker
        now = time.perf_counter()
        if tr.error:
            self.v_cam.set("Error - " + tr.error)
        elif self.sim:
            self.v_cam.set("Test mode (no camera)")
        else:
            self.v_cam.set("Connected (device %d)" % tr.camera_index)
        self.v_face.set("Yes" if tr.face_visible else "No")
        sec = self.monitor.screen_seconds(now)
        self.v_screen.set("%s / %d min" % (fmt_hms(sec), s.screen_minutes))
        self.bar_screen["value"] = min(100, sec / (s.screen_minutes * 60) * 100)
        rate = self.monitor.blink_rate(now)
        if rate is None:
            self.v_rate.set("Measuring...")
            self.v_verdict.set("Shown once your face has been visible for most of the last minute.")
        else:
            self.v_rate.set("%.1f" % rate)
            self.v_verdict.set("Prompt below %g per minute. People often blink much less while focused on a screen." % s.blink_threshold)
        self.v_offset.set("Input delay offset: %+d ms%s" % (
            round(s.latency_offset * 1000), "" if s.first_run_done else "  (measure it in the wizard)"))
        if not s.monitoring:
            self.v_bar.set("Monitoring off")
        elif self.game is not None:
            self.v_bar.set("In a game")
        else:
            self.v_bar.set("Monitoring")

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
            self.root.after(10, lambda: self.open_game(from_prompt=True))

        def snooze():
            self.monitor.snooze(time.perf_counter())
            done()

        def today():
            self.monitor.suppressed_today = True
            done()

        self.prompt = PromptDialog(self, minutes, rate, play, snooze, today)

    def run(self):
        self.root.mainloop()
