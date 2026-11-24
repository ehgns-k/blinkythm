"""Game window (pygame-ce). Runs its own loop inside the Tk main loop and processes Tk events every frame.

The tray, prompt and settings stay in Tk; only the game is drawn in this window.
"""
import datetime
import queue
import time

import pygame

from .. import stages as S
from ..tracker import SimTracker
from . import gfx as G
from .screens import HomeScreen, PlayScreen

FPS = 60
FADE = 0.16
DOUBLE_BLINK = (0.12, 0.70)          # gap that counts as a double blink (s)
UI_SOUNDS = ["ui_move", "ui_ok", "stamp"]


class GameApp:
    def __init__(self, app, stage=None, from_prompt=False):
        self.app = app
        self.settings = app.settings
        self.monitor = app.monitor
        self.tracker = app.tracker
        self.audio = app.audio
        self.from_prompt = from_prompt
        self.preselect = stage
        self.sim = isinstance(app.tracker, SimTracker)
        self.gfx = None
        self.window = None
        self.base = None
        self.presenter = G.Presenter()
        self.screen = None
        self._next = None
        self._fade_t = None
        self._blinks = queue.Queue()
        self._last_blink = None
        self.running = False
        self.fullscreen = False

    # ------------------------------------------------------------------ lifecycle
    def open(self, headless_size=None):
        pygame.display.init()
        pygame.font.init()
        if headless_size:
            self.window = pygame.display.set_mode(headless_size)
        else:
            desk = pygame.display.get_desktop_sizes()[0]
            self._windowed = G.initial_window_size(*desk)
            self.window = pygame.display.set_mode(self._windowed, pygame.RESIZABLE)
        pygame.display.set_caption("Blinkythm")
        self.gfx = G.Gfx()
        try:
            pygame.display.set_icon(self.gfx.sprite("owl_me_open", 2))
        except pygame.error:
            pass
        self.base = pygame.Surface((G.BASE_W, G.BASE_H))
        self.audio.volume = self.settings.volume
        self.audio.prepare(UI_SOUNDS)
        self.tracker.set_game_mode(True)
        self.tracker.add_listener(self._blinks.put)
        self.running = True
        self.screen = HomeScreen(self)
        self.screen.enter()

    def shutdown(self):
        if self.screen is not None:
            self.screen.leave()
        self.tracker.remove_listener(self._blinks.put)
        self.tracker.set_game_mode(False)
        self.audio.stop()
        pygame.display.quit()
        self.running = False

    def run(self):
        """Open the window and loop until it closes. Tk events are handled with root.update()."""
        import tkinter as tk
        self.open()
        clock = pygame.time.Clock()
        try:
            while self.running:
                self.frame()
                clock.tick(FPS)
                try:
                    self.app.root.update()
                except tk.TclError:       # the app was quit from the tray
                    break
        finally:
            self.shutdown()

    def close(self):
        self.running = False

    # ------------------------------------------------------------------ one frame
    def frame(self, now=None):
        now = time.perf_counter() if now is None else now
        for ev in pygame.event.get():
            self.handle_event(ev)
        while True:
            try:
                onset = self._blinks.get_nowait()
            except queue.Empty:
                break
            self._on_blink(onset)
        if self._next is not None and (self._fade_t is None or now - self._fade_t >= FADE):
            self._swap()
        if self.screen is not None:
            self.screen.update(now)
            self.screen.draw(self.base, now)
        if self._fade_t is not None:
            k = (now - self._fade_t) / FADE
            a = k if self._next is not None else 1 - (k - 1)
            if self._next is None and k >= 2:
                self._fade_t = None
            else:
                G.alpha_fill(self.base, (0, 0, G.BASE_W, G.BASE_H), G.INK, int(255 * max(0, min(1, a))))
        if self.window is not None:
            self.presenter.present(self.window, self.base)
            pygame.display.flip()

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.close()
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif ev.key == pygame.K_SPACE and self.sim:
                self.tracker.press()
            elif self._next is None and self.screen is not None:
                self.screen.key(ev.key)
        elif ev.type == pygame.MOUSEMOTION and self.screen is not None:
            self.screen.hover(self.presenter.to_base(ev.pos))
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.screen is not None and self._next is None:
            self.screen.click(self.presenter.to_base(ev.pos))

    def _on_blink(self, onset):
        if self.screen is None:
            return
        self.screen.blink(onset)
        last = self._last_blink
        self._last_blink = onset
        if last is not None and DOUBLE_BLINK[0] <= onset - last <= DOUBLE_BLINK[1] and self._next is None:
            self._last_blink = None
            self.screen.double_blink()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(self._windowed, pygame.RESIZABLE)

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

    # ------------------------------------------------------------------ helpers
    def sound(self, name):
        self.audio.play_sfx(name)

    def recommended(self):
        return self.preselect or S.next_stage(self.settings.last_stage)

    def open_settings(self):
        self.app.show_main()

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
            self.close()
        else:
            self.go(HomeScreen(self))
