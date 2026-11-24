"""Reminder popup: a small borderless window in the corner of the screen.

It never takes keyboard focus and only reacts to the mouse, so typing elsewhere cannot press a button.
Buttons stay inactive for the first moment, and no answer counts as "Later".
"""
import time

import pygame

from .. import winenv
from . import gfx as G

W, H = 200, 72
TIMEOUT = 90.0
ARM = 1.2


class PromptWindow:
    def __init__(self, app, minutes, rate, on_play, on_snooze, on_today, gfx):
        self.g = gfx
        self.minutes, self.rate = minutes, rate
        self.on_play, self.on_snooze, self.on_today = on_play, on_snooze, on_today
        desk = pygame.display.get_desktop_sizes()[0]
        main_scale = G.initial_window_size(*desk)[0] // G.BASE_W
        self.scale = max(1, main_scale // 2)
        size = (W * self.scale, H * self.scale)
        left, top, right, bottom = winenv.work_area(desk)
        pos = (right - size[0] - 16, bottom - size[1] - 16)
        self.win = pygame.Window("Blinkythm", size, pos, borderless=True, always_on_top=True, utility=True)
        self.base = pygame.Surface((W, H))
        self.t_open = time.perf_counter()
        self.done = False
        self.hover = None
        snooze = app.settings.snooze_minutes
        self.buttons = [G.Button("Play", "", self._play, primary=True),
                        G.Button("In %d min" % snooze, "", self._snooze),
                        G.Button("Not today", "", self._today)]

    @property
    def armed(self):
        return time.perf_counter() - self.t_open >= ARM

    def _finish(self, cb):
        if self.done:
            return
        self.done = True
        self.win.destroy()
        cb()

    def _play(self):
        self._finish(self.on_play)

    def _snooze(self):
        self._finish(self.on_snooze)

    def _today(self):
        self._finish(self.on_today)

    def owns(self, ev):
        return getattr(ev, "window", None) is self.win

    def handle_event(self, ev):
        if ev.type == pygame.WINDOWCLOSE:
            self._snooze()
        elif ev.type == pygame.MOUSEMOTION:
            p = (ev.pos[0] // self.scale, ev.pos[1] // self.scale)
            self.hover = next((i for i, b in enumerate(self.buttons) if b.rect.collidepoint(p)), None)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.armed:
            p = (ev.pos[0] // self.scale, ev.pos[1] // self.scale)
            for b in self.buttons:
                if b.rect.collidepoint(p):
                    b.press()
                    return

    def frame(self, now=None):
        if self.done:
            return
        now = time.perf_counter() if now is None else now
        if now - self.t_open >= TIMEOUT:
            self._snooze()
            return
        s = self.base
        s.fill(G.INK)
        G.panel(s, (0, 0, W, H), (34, 30, 68), G.LAMP)
        closed = (now - self.t_open) % 3.2 < 0.15
        self.g.blit_sprite(s, "owl_me_closed" if closed else "owl_me_open", (22, 40), 2)
        self.g.text(s, "Time to rest your eyes", (42, 5), G.CREAM, "bold")
        self.g.text(s, "%d min on screen, %d blinks/min" % (round(self.minutes), round(self.rate)),
                    (42, 22), G.FOG, "small")
        armed = self.armed
        x = 8
        for i, b in enumerate(self.buttons):
            b.enabled = armed
            w = self.g.width(b.label, "bold") + 12
            b.draw_plain(self.g, s, (x, 48, w, 17), i == self.hover and armed)
            x += w + 4
        left = max(0, TIMEOUT - (now - self.t_open))
        pygame.draw.line(s, G.DUSK, (2, H - 3), (W - 3, H - 3))
        pygame.draw.line(s, G.HAZE, (2, H - 3), (2 + round((W - 5) * left / TIMEOUT), H - 3))
        self.win.get_surface().blit(pygame.transform.scale_by(s, self.scale), (0, 0))
        self.win.flip()
