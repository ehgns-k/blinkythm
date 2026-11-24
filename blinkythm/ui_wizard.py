"""First-run and recalibration wizard: camera check -> timing calibration -> finish. Classic setup wizard layout."""
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
        self.title("Blinkythm Setup")
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
        self.b_cancel = ttk.Button(btns, text="Cancel", width=10, command=self.cancel)
        self.b_cancel.pack(side="right")
        self.b_next = ttk.Button(btns, text="Next >", width=10, command=self.next)
        self.b_next.pack(side="right", padx=(0, 6))
        self.b_back = ttk.Button(btns, text="< Back", width=10, command=self.back)
        self.b_back.pack(side="right", padx=(0, 2))

        self.pages = [self._page_camera, self._page_calib, self._page_finish]
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.app.tracker.set_game_mode(True)
        self.show(0)
        center_on(self, app.root, 520, 400)
        self.grab_set()

    # ------------------------------------------------------------------ shared
    def show(self, n):
        self.page = n
        if self._poll:
            self.after_cancel(self._poll)
            self._poll = None
        for w in self.body.winfo_children():
            w.destroy()
        self.pages[n]()
        self.b_back.state(["!disabled" if n > 0 else "disabled"])
        self.b_next.config(text="Finish" if n == len(self.pages) - 1 else "Next >")

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

    # ------------------------------------------------------------------ 1. camera
    def _page_camera(self):
        self.header("Camera check", "Blinks are detected with your webcam.")
        b = self.body
        ttk.Label(b, wraplength=470, justify="left",
                  text="Video is used only to measure how open your eyes are, on this computer. It is never saved or sent.\n"
                       "Sit with your face in the middle of the picture, in a well-lit place.").pack(anchor="w")
        box = ttk.LabelFrame(b, text="Camera", padding=10)
        box.pack(fill="x", pady=12)
        r1 = ttk.Frame(box)
        r1.pack(fill="x")
        ttk.Label(r1, text="Device:").pack(side="left")
        self.cam_var = tk.IntVar(value=self.app.settings.camera_index)
        ttk.Spinbox(r1, from_=0, to=5, width=4, textvariable=self.cam_var).pack(side="left", padx=6)
        ttk.Button(r1, text="Reconnect", command=self._reconnect).pack(side="left")
        self.cam_status = ttk.Label(box, text="")
        self.cam_status.pack(anchor="w", pady=(8, 0))
        self.face_status = ttk.Label(box, text="")
        self.face_status.pack(anchor="w")
        r2 = ttk.Frame(box)
        r2.pack(fill="x", pady=(8, 0))
        ttk.Label(r2, text="Eye openness:").pack(side="left")
        self.ear_bar = ttk.Progressbar(r2, length=240, maximum=100)
        self.ear_bar.pack(side="left", padx=6)
        ttk.Label(b, text="Blink once. If the bar drops and comes back, detection works.").pack(anchor="w")
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
            self.cam_status.config(text="Status: error - " + tr.error, foreground="#800000", wraplength=440)
        else:
            self.cam_status.config(text="Status: connected", foreground="")
        if tr.face_visible:
            self.face_status.config(text="Face: detected")
            self._face_since = self._face_since or time.perf_counter()
        else:
            self.face_status.config(text="Face: not visible")
            self._face_since = None
        r = tr.ear_ratio
        self.ear_bar["value"] = 0 if r is None else min(100, r * 100 / 1.1)
        ok = self._face_since is not None and time.perf_counter() - self._face_since > 1.0
        self.b_next.state(["!disabled" if ok else "disabled"])
        self._poll = self.after(80, self._poll_camera)

    # ------------------------------------------------------------------ 2. calibration
    def _page_calib(self):
        self.header("Timing calibration", "Measures webcam and speaker delay so judging is fair.")
        b = self.body
        ttk.Label(b, wraplength=470, justify="left",
                  text="Press Start to hear 12 evenly spaced ticks. Listen to the first 4, "
                       "then blink once on each tick. Do not wait for the sound; expect the beat "
                       "and start closing your eyes at the same moment.").pack(anchor="w")
        box = ttk.LabelFrame(b, text="Measurement", padding=10)
        box.pack(fill="x", pady=12)
        self.cal_btn = ttk.Button(box, text="Start", width=10, command=self._cal_start)
        self.cal_btn.pack(anchor="w")
        self.cal_prog = ttk.Progressbar(box, length=300, maximum=R.CAL_TICKS)
        self.cal_prog.pack(anchor="w", pady=8)
        self.cal_text = ttk.Label(box, text="", wraplength=440, justify="left")
        self.cal_text.pack(anchor="w")
        if isinstance(self.app.tracker, SimTracker):
            ttk.Label(b, text="[Test mode] Space = blink", foreground="#800000").pack(anchor="w")
            self.bind("<space>", lambda e: self.app.tracker.press())
        if self.offset is None:
            self.b_next.state(["disabled"])
        if self.offset is not None:
            self.cal_text.config(text="Previous result: %+d ms" % round(self.offset * 1000))

    def _on_blink(self, onset):
        if self._cal_running:
            self._cal_onsets.append(onset)

    def _cal_start(self):
        if not self.app.audio.ok:
            self.cal_text.config(text="No audio device is available, so calibration cannot run. Check your speakers or headphones.")
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
        self.cal_text.config(text="Just listen to the first 4 ticks...")
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
            self.cal_text.config(text="Blink now! Blinks detected: %d" % n)
        if el < R.CAL_TICKS * R.CAL_BEAT + 0.7:
            self._poll = self.after(40, self._cal_tick)
        else:
            self._cal_done()

    def _cal_done(self):
        self._cal_running = False
        self.cal_prog["value"] = R.CAL_TICKS
        self.app.tracker.remove_listener(self._on_blink)
        self.cal_btn.state(["!disabled"])
        self.cal_btn.config(text="Measure again")
        self.b_back.state(["!disabled"])
        out = R.compute_offset(self._cal_onsets, self._cal_t0)
        if out is None:
            self.cal_text.config(text="Too few blinks were detected, or the timing was uneven. "
                                      "Keep your face centred, blink a little more clearly and try again.")
            self.b_next.state(["disabled"] if self.offset is None else ["!disabled"])
            return
        off, sd, n = out
        self.offset = off
        self.cal_text.config(text="Done: input delay %+d ms (spread +/-%d ms, %d blinks used)" % (round(off * 1000), round(sd * 1000), n))
        self.b_next.state(["!disabled"])

    # ------------------------------------------------------------------ 3. finish
    def _page_finish(self):
        self.header("Setup complete", "Check the options below and click Finish.")
        b = self.body
        s = self.app.settings
        ttk.Label(b, wraplength=470, justify="left",
                  text="After %d minutes at the screen with fewer than %d blinks in the last minute, you will be offered a short game. "
                       "You can change these conditions later on the Settings tab." % (s.screen_minutes, s.blink_threshold)).pack(anchor="w")
        box = ttk.LabelFrame(b, text="Options", padding=10)
        box.pack(fill="x", pady=12)
        self.var_monitor = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Start monitoring blinks after Finish", variable=self.var_monitor).pack(anchor="w")
        self.var_auto = tk.BooleanVar(value=winenv.is_autostart())
        cb = ttk.Checkbutton(box, text="Start Blinkythm with Windows", variable=self.var_auto)
        cb.pack(anchor="w", pady=(6, 0))
        if not winenv.IS_WIN:
            cb.state(["disabled"])
        if self.offset is not None:
            ttk.Label(b, text="Input delay offset: %+d ms" % round(self.offset * 1000)).pack(anchor="w")
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
