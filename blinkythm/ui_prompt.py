"""Prompt dialog in the screen corner. It starts without a default button so typing is not captured."""
import tkinter as tk
from tkinter import ttk

from . import winenv
from .ui_common import bold_font

TIMEOUT_MS = 90_000
ARM_MS = 1200


class PromptDialog(tk.Toplevel):
    def __init__(self, app, minutes, rate, on_play, on_snooze, on_today):
        super().__init__(app.root)
        self.app = app
        self._on_play, self._on_snooze, self._on_today = on_play, on_snooze, on_today
        self._done = False
        self._armed = False
        self.title("Blink reminder")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        body = ttk.Frame(self, padding=(12, 12, 12, 8))
        body.pack(fill="both", expand=True)
        tk.Label(body, bitmap="info").grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10))
        ttk.Label(body, text="Your eyes may be getting dry.", font=bold_font(9)).grid(row=0, column=1, sticky="w")
        msg = ("You have been looking at the screen for %g minutes and blinked %.0f times in the last minute.\n"
               "Rest your eyes with a short rhythm game (about 35 seconds)?") % (round(minutes, 1), rate)
        ttk.Label(body, text=msg, justify="left", wraplength=330).grid(row=1, column=1, sticky="w", pady=(4, 0))

        ttk.Separator(self).pack(fill="x", padx=8)
        btns = ttk.Frame(self, padding=(8, 8, 8, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Play now", width=12, command=self._play).pack(side="right")
        ttk.Button(btns, text="In %d min" % app.settings.snooze_minutes, width=12,
                   command=self._snooze).pack(side="right", padx=(0, 6))
        ttk.Button(btns, text="Not today", width=12, command=self._today).pack(side="right", padx=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._snooze)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        l, t, r, b = winenv.work_area(app.root)
        self.geometry("%dx%d+%d+%d" % (w, h, r - w - 16, b - h - 16))
        # Focus the dialog itself so Enter or Space typed elsewhere does not press a button
        self.focus_set()
        self._timeout = self.after(TIMEOUT_MS, self._snooze)
        self.after(ARM_MS, self._arm)

    def _arm(self):
        self._armed = True

    def _finish(self, cb):
        if self._done:
            return
        self._done = True
        try:
            self.after_cancel(self._timeout)
        except Exception:
            pass
        self.destroy()
        cb()

    def _play(self):
        if self._armed:
            self._finish(self._on_play)

    def _snooze(self):
        self._finish(self._on_snooze)

    def _today(self):
        if self._armed:
            self._finish(self._on_today)
