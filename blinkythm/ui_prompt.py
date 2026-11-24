"""화면 모서리에 뜨는 알림 대화상자. 작업 중인 입력을 가로채지 않도록 단축키/기본 버튼 없이 시작한다."""
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
        self.title("눈 깜빡임 알림")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        body = ttk.Frame(self, padding=(12, 12, 12, 8))
        body.pack(fill="both", expand=True)
        tk.Label(body, bitmap="info").grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10))
        ttk.Label(body, text="눈이 건조해질 수 있습니다.", font=bold_font(9)).grid(row=0, column=1, sticky="w")
        msg = ("화면을 본 지 %g분이 지났고, 최근 1분간 눈 깜빡임이 분당 %.0f회입니다.\n"
               "짧은 리듬 게임(약 45초)으로 눈을 쉬어 보시겠어요?") % (round(minutes, 1), rate)
        ttk.Label(body, text=msg, justify="left", wraplength=330).grid(row=1, column=1, sticky="w", pady=(4, 0))

        ttk.Separator(self).pack(fill="x", padx=8)
        btns = ttk.Frame(self, padding=(8, 8, 8, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="지금 하기", width=12, command=self._play).pack(side="right")
        ttk.Button(btns, text="%d분 뒤 다시" % app.settings.snooze_minutes, width=12,
                   command=self._snooze).pack(side="right", padx=(0, 6))
        ttk.Button(btns, text="오늘은 그만", width=12, command=self._today).pack(side="right", padx=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._snooze)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        l, t, r, b = winenv.work_area(app.root)
        self.geometry("%dx%d+%d+%d" % (w, h, r - w - 16, b - h - 16))
        # 타이핑 중 Enter/Space가 버튼을 누르지 않도록 대화상자 자체에 포커스를 둔다
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
