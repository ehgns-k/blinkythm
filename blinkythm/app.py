"""The app: one pygame-ce loop that runs the main window, the reminder popup, the tray icon and the
prompt scheduler. The main window is hidden to the tray instead of closed."""
import os
import queue
import time

from . import APP_NAME, winenv
from .audio import Audio
from .config import Settings
from .monitor import UsageMonitor
from .tracker import CameraTracker, SimTracker

TICK = 0.5                 # how often the prompt conditions are checked (s)
FPS_SHOWN = 60
FPS_HIDDEN = 15


class App:
    def __init__(self, sim=False, demo=False, background=False, window_size=None, tray=True):
        winenv.enable_dpi_awareness()
        # Showing the reminder must not take focus away from what the user is typing in.
        os.environ.setdefault("SDL_WINDOW_NO_ACTIVATION_WHEN_SHOWN", "1")
        import pygame
        self.pg = pygame
        pygame.display.init()
        pygame.font.init()

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
        self.tracker.set_sensitivity(self.settings.blink_sensitivity)
        self.audio = Audio(self.settings.volume)

        from .game.window import MainWindow
        self.window = MainWindow(self, window_size)
        self.prompt = None
        self.tray = None
        self.running = True
        self._ui_q = queue.Queue()
        self._next_tick = 0.0
        if tray:
            self._setup_tray()

        self.tracker.start()
        if not self.settings.first_run_done:
            from .game.system import SetupCameraScreen
            self.window.show(SetupCameraScreen(self.window))
        elif not background:
            self.window.show()

    # ------------------------------------------------------------------ main loop
    def run(self):
        clock = self.pg.time.Clock()
        try:
            while self.running:
                self.step()
                busy = self.window.visible or self.prompt is not None
                clock.tick(FPS_SHOWN if busy else FPS_HIDDEN)
        finally:
            self.shutdown()

    def step(self, now=None):
        now = time.perf_counter() if now is None else now
        while True:
            try:
                self._ui_q.get_nowait()()
            except queue.Empty:
                break
        for ev in self.pg.event.get():
            if self.prompt is not None and self.prompt.owns(ev):
                self.prompt.handle_event(ev)
            elif ev.type == self.pg.QUIT:
                if self.tray is None:
                    self.quit()
            else:
                self.window.handle_event(ev)
        if now >= self._next_tick:
            self._next_tick = now + TICK
            self._tick(now)
        if self.running:
            self.window.frame(now)
            if self.prompt is not None:
                self.prompt.frame(now)

    def post(self, fn):
        """Queue work from another thread (the tray) to run on the main loop."""
        self._ui_q.put(fn)

    def quit(self):
        self.running = False

    def shutdown(self):
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.tracker.stop()
        self.audio.stop()
        self.settings.save()
        self._close_prompt()
        self.window.destroy()
        self.pg.display.quit()

    # ------------------------------------------------------------------ windows
    def show_main(self, screen=None):
        self._close_prompt()
        self.window.show(screen)

    def hide_main(self):
        if self.tray is None and not self.sim:
            self.window.win.minimize()      # no tray to come back from
            return
        self.window.hide()

    def open_game(self, stage=None, from_prompt=False):
        self._close_prompt()
        self.window.open_game(stage, from_prompt)

    def _close_prompt(self):
        if self.prompt is not None and not self.prompt.done:
            self.prompt.done = True
            self.prompt.win.destroy()
        self.prompt = None

    # ------------------------------------------------------------------ tray
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
            Item("Play now", lambda: self.post(self.open_game)),
            Item("Settings", lambda: self.post(self._open_settings)),
            Item("Monitor blinking", lambda: self.post(self._tray_toggle), checked=lambda i: self.settings.monitoring),
            pystray.Menu.SEPARATOR,
            Item("Exit", lambda: self.post(self.quit)),
        )
        try:
            self.tray = pystray.Icon(APP_NAME, img, "Blinkythm", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = None

    def _open_settings(self):
        from .game.system import SettingsScreen
        self.show_main(SettingsScreen(self.window))

    def _tray_toggle(self):
        self.settings.monitoring = not self.settings.monitoring
        self.settings.save()

    # ------------------------------------------------------------------ prompt scheduling
    def _tick(self, now):
        self.monitor.paused = (not self.settings.monitoring) or self.window.busy
        if (self.settings.monitoring and self.prompt is None and not self.window.visible
                and not self.tracker.error):
            dnd = self.settings.respect_dnd and winenv.is_busy()
            if self.monitor.should_prompt(now, dnd):
                self._show_prompt(now)
        if self.prompt is not None and self.prompt.done:
            self.prompt = None

    def _show_prompt(self, now):
        from .game.prompt import PromptWindow
        minutes = self.monitor.screen_seconds(now) / 60.0
        rate = self.monitor.blink_rate(now) or 0.0

        def play():
            self.prompt = None
            self.open_game(from_prompt=True)

        def snooze():
            self.prompt = None
            self.monitor.snooze(time.perf_counter())

        def today():
            self.prompt = None
            self.monitor.suppressed_today = True

        self.prompt = PromptWindow(self, minutes, rate, play, snooze, today, self.window.gfx)
