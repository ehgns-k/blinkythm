"""The main window. It stays alive while the app runs and is hidden to the tray instead of closed.

Every screen (home, games, results, settings, setup) is drawn here on the 384x216 pixel screen.
"""
import datetime
import queue
import time

import pygame

from .. import stages as S
from ..tracker import SimTracker
from . import gfx as G
from .screens import HomeScreen, PlayScreen, InterludeScreen

FADE = 0.16
DOUBLE_BLINK = (0.12, 0.70)          # gap that counts as a double blink (s)
UI_SOUNDS = ["ui_move", "ui_ok", "stamp"]


class MainWindow:
    def __init__(self, app, size=None):
        self.app = app
        self.settings = app.settings
        self.monitor = app.monitor
        self.tracker = app.tracker
        self.audio = app.audio
        self.sim = isinstance(app.tracker, SimTracker)
        self.from_prompt = False
        self.preselect = None
        desk = pygame.display.get_desktop_sizes()[0]
        self._windowed = size or G.initial_window_size(*desk)
        self.win = pygame.Window("Blinkythm", self._windowed, resizable=True, hidden=True)
        self.win.minimum_size = (G.BASE_W, G.BASE_H)
        self.win.get_surface()                     # sets the pixel format used by convert_alpha
        self.gfx = G.Gfx()
        try:
            self.win.set_icon(self.gfx.sprite("owl_me_open", 2))
        except pygame.error:
            pass
        self.base = pygame.Surface((G.BASE_W, G.BASE_H))
        self.presenter = G.Presenter()
        self.screen = HomeScreen(self)
        self._next = None
        self._fade_t = None
        self._blinks = queue.Queue()
        self._last_blink = None
        self.visible = False
        self.fullscreen = False
        self.audio.prepare(UI_SOUNDS)
        self.tracker.add_listener(self._blinks.put)

    # ------------------------------------------------------------------ showing and hiding
    def show(self, screen=None):
        if screen is not None:
            self._set_screen(screen)
        elif not self.visible and not isinstance(self.screen, HomeScreen):
            self._set_screen(HomeScreen(self))
        self.win.show()
        self.win.focus()
        self.visible = True
        self.tracker.set_game_mode(True)

    def hide(self):
        if isinstance(self.screen, (PlayScreen, InterludeScreen)):
            self.audio.stop()
        self._set_screen(HomeScreen(self))
        if self.fullscreen:
            self.toggle_fullscreen()
        self.win.hide()
        self.visible = False
        self.from_prompt = False
        self.preselect = None
        self.tracker.set_game_mode(False)

    def close(self):
        """Close button or Esc on the home screen: back to the tray."""
        self.app.hide_main()

    def destroy(self):
        self.tracker.remove_listener(self._blinks.put)
        self.screen.leave()
        self.win.destroy()

    @property
    def busy(self):
        """True while blinks are deliberate (playing or calibrating), so they stay out of the statistics."""
        from .system import SetupCalibScreen
        return self.visible and isinstance(self.screen, (PlayScreen, InterludeScreen, SetupCalibScreen))

    def open_game(self, stage=None, from_prompt=False):
        self.preselect = stage
        self.from_prompt = from_prompt
        self.show(HomeScreen(self))

    def _set_screen(self, screen):
        self.screen.leave()
        self.screen = screen
        self._next = None
        self._fade_t = None
        self.screen.enter()

    # ------------------------------------------------------------------ one frame
    def frame(self, now=None):
        now = time.perf_counter() if now is None else now
        if not self.visible:
            while not self._blinks.empty():
                self._blinks.get_nowait()
            return
        while True:
            try:
                onset = self._blinks.get_nowait()
            except queue.Empty:
                break
            self._on_blink(onset)
        if self._next is not None and (self._fade_t is None or now - self._fade_t >= FADE):
            self._swap()
        self.screen.update(now)
        self.screen.draw(self.base, now)
        if self._fade_t is not None:
            k = (now - self._fade_t) / FADE
            a = k if self._next is not None else 1 - (k - 1)
            if self._next is None and k >= 2:
                self._fade_t = None
            else:
                G.alpha_fill(self.base, (0, 0, G.BASE_W, G.BASE_H), G.INK, int(255 * max(0, min(1, a))))
        if self.visible:                    # a screen may have hidden the window during update
            self.presenter.present(self.win.get_surface(), self.base)
            self.win.flip()

    def handle_event(self, ev):
        t = ev.type
        if t == pygame.WINDOWCLOSE:
            self.close()
        elif t == pygame.KEYDOWN:
            if ev.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif ev.key == pygame.K_SPACE and self.sim:
                self.tracker.press()
            elif self._next is None:
                self.screen.key(ev.key)
        elif t == pygame.MOUSEMOTION:
            self.screen.hover(self.presenter.to_base(ev.pos))
        elif t == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3) and self._next is None:
            self.screen.click(self.presenter.to_base(ev.pos), ev.button == 3)
        elif t == pygame.MOUSEWHEEL and self._next is None:
            self.screen.wheel(ev.y)

    def _on_blink(self, onset):
        self.screen.blink(onset)
        last = self._last_blink
        self._last_blink = onset
        if last is not None and DOUBLE_BLINK[0] <= onset - last <= DOUBLE_BLINK[1] and self._next is None:
            self._last_blink = None
            self.screen.double_blink()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.win.set_fullscreen(True)
        else:
            self.win.set_windowed()
            self.win.size = self._windowed

    # ------------------------------------------------------------------ screen changes
    def go(self, screen, fade=True):
        self._next = screen
        self._fade_t = time.perf_counter() if fade else None

    def _swap(self):
        self.screen.leave()
        self.screen = self._next
        self._next = None
        self.screen.enter()
        if self._fade_t is not None:
            self._fade_t = time.perf_counter() - FADE     # continue with the fade-in

    def start(self, keys):
        keys = list(keys)
        first = keys.pop(0)
        self.go(PlayScreen(self, first, keys, []))

    # ------------------------------------------------------------------ helpers used by screens
    def sound(self, name):
        self.audio.play_sfx(name)

    def recommended(self):
        return self.preselect or S.next_stage(self.settings.last_stage)

    def open_settings(self):
        from .system import SettingsScreen
        self.go(SettingsScreen(self))

    def daily(self):
        today = datetime.date.today().isoformat()
        d = self.settings.daily or {}
        if d.get("date") != today:
            d = {"date": today, "plays": 0, "rests": 0}
            self.settings.daily = d
        return d

    def record_play(self):
        d = self.daily()
        d["plays"] += 1
        self.settings.stamps += 1
        self.monitor.mark_played(time.perf_counter())
        self.settings.save()

    def record_rest(self):
        self.daily()["rests"] += 1
        self.settings.save()

    def save_record(self, key, acc, last_stage=None):
        recs = dict(self.settings.records or {})
        new = acc > recs.get(key, -1)
        if new:
            recs[key] = round(acc, 1)
        self.settings.records = recs
        if last_stage:
            self.settings.last_stage = last_stage
            self.preselect = None
        self.settings.save()
        return new

    def apply_offset(self, shift):
        s = self.settings
        s.latency_offset += shift
        s.save()
        return "Offset is now %+d ms" % round(s.latency_offset * 1000)

    def after_rest(self):
        if self.from_prompt:
            self.app.hide_main()
        else:
            self.go(HomeScreen(self))
