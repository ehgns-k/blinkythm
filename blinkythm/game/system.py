"""Settings and the setup steps (camera check, timing calibration, finish), drawn like the rest of the game."""
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional

import pygame

from .. import __version__, winenv
from .. import rhythm as R
from . import gfx as G
from .screens import Screen, HomeScreen

ROW_H = 14
LIST_TOP, LIST_BOT = 22, 176


def camera_text(tracker, sim):
    if tracker.error:
        return tracker.error, G.ROSE
    if sim:
        return "Test mode, no camera", G.FOG
    return "Connected, device %d" % tracker.camera_index, G.MINT


# ====================================================================== settings
@dataclass
class Row:
    label: str
    kind: str                                  # "head", "num", "bool", "action"
    get: Optional[Callable] = None
    change: Optional[Callable] = None          # num: change(+1/-1); bool: change(); action: change()
    show: Optional[Callable] = None            # text for the value
    enabled: bool = True
    note: str = ""


class SettingsScreen(Screen):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.rows = self._rows()
        self.sel = next(i for i, r in enumerate(self.rows) if r.kind != "head")
        self.scroll = 0
        self.row_rects = []
        self.buttons = [G.Button("Back", "Esc", lambda: ctx.go(HomeScreen(ctx)), primary=True)]

    # rows ------------------------------------------------------------------
    def _num(self, label, key, lo, hi, step, fmt, scale=1.0, after=None):
        s = self.ctx.settings

        def change(d):
            v = round(getattr(s, key) * scale + d * step)
            v = max(lo, min(hi, v))
            setattr(s, key, v / scale if scale != 1.0 else v)
            if after:
                after()

        return Row(label, "num", get=lambda: getattr(s, key), change=change,
                   show=lambda: fmt % round(getattr(s, key) * scale))

    def _bool(self, label, key, after=None):
        s = self.ctx.settings

        def flip():
            setattr(s, key, not getattr(s, key))
            if after:
                after()

        return Row(label, "bool", get=lambda: getattr(s, key), change=flip)

    def _rows(self):
        c, s = self.ctx, self.ctx.settings

        def volume_changed():
            c.audio.volume = s.volume
            c.audio.prepare(["ui_move", "ui_ok", "stamp"])

        def camera_changed():
            c.tracker.restart(s.camera_index)
            c.tracker.set_game_mode(True)

        def offset(d):
            s.latency_offset = round(s.latency_offset + d * 0.005, 3)

        def autostart():
            winenv.set_autostart(not winenv.is_autostart())

        from .system import SetupCalibScreen, SetupCameraScreen      # noqa: F811 (same module, for clarity)
        return [
            Row("Reminder", "head"),
            self._num("Screen time before checking", "screen_minutes", 1, 180, 1, "%d min"),
            self._num("Remind below", "blink_threshold", 1, 30, 1, "%d blinks/min"),
            self._num("Away after no face for", "away_seconds", 10, 600, 10, "%d s"),
            self._num("Later means", "snooze_minutes", 1, 60, 1, "%d min"),
            self._num("Quiet after a game", "cooldown_minutes", 1, 240, 5, "%d min"),
            self._bool("Quiet during fullscreen apps", "respect_dnd"),
            self._bool("Monitor blinking", "monitoring"),
            Row("Game", "head"),
            self._num("Volume", "volume", 0, 100, 10, "%d%%", scale=100.0, after=volume_changed),
            self._bool("Show where to blink", "show_guide"),
            Row("Input delay", "action", change=offset,
                show=lambda: "%+d ms" % round(s.latency_offset * 1000), note="Enter: measure again"),
            Row("Measure input delay", "action", change=lambda: c.go(SetupCalibScreen(c, standalone=True))),
            Row("Camera", "head"),
            self._num("Camera device", "camera_index", 0, 9, 1, "%d", after=camera_changed),
            Row("Check the camera", "action", change=lambda: c.go(SetupCameraScreen(c, standalone=True))),
            Row("System", "head"),
            Row("Start with Windows", "bool", get=winenv.is_autostart, change=autostart,
                enabled=winenv.IS_WIN, note="" if winenv.IS_WIN else "Windows only"),
            Row("Hide to tray", "action", change=c.close),
            Row("Exit Blinkythm", "action", change=c.app.quit),
        ]

    # input -----------------------------------------------------------------
    def _focusable(self, i):
        return self.rows[i].kind != "head"

    def _step(self, d):
        i = self.sel
        while True:
            i += d
            if i < 0 or i >= len(self.rows):
                return
            if self._focusable(i):
                self.sel = i
                self.ctx.sound("ui_move")
                return

    def _activate(self, row, d=0):
        if not row.enabled:
            return
        if row.kind == "num" and d:
            row.change(d)
        elif row.kind == "bool":
            row.change()
        elif row.kind == "action":
            if row.label == "Input delay":
                if d:
                    row.change(d)
                else:
                    self.rows[self.rows.index(row) + 1].change()
                    return
            else:
                if d:
                    return
                row.change()
        else:
            return
        self.ctx.sound("ui_move" if d else "ui_ok")
        self.ctx.settings.save()

    def key(self, k):
        row = self.rows[self.sel]
        if k == pygame.K_UP:
            self._step(-1)
        elif k in (pygame.K_DOWN, pygame.K_TAB):
            self._step(1)
        elif k == pygame.K_LEFT:
            self._activate(row, -1)
        elif k == pygame.K_RIGHT:
            self._activate(row, 1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(row, 0) if row.kind != "num" else None
        elif k == pygame.K_ESCAPE:
            self.ctx.go(HomeScreen(self.ctx))
        else:
            return False
        return True

    def hover(self, pos):
        for i, r in self.row_rects:
            if r.collidepoint(pos) and i != self.sel:
                self.sel = i
        super().hover(pos)

    def click(self, pos, right=False):
        for i, r in self.row_rects:
            if r.collidepoint(pos):
                self.sel = i
                row = self.rows[i]
                if row.kind == "num" or (row.kind == "action" and row.label == "Input delay"):
                    self._activate(row, -1 if pos[0] < r.right - 44 or right else 1)
                else:
                    self._activate(row, 0)
                return True
        return super().click(pos, right)

    def wheel(self, dy):
        self._step(-1 if dy > 0 else 1)

    # drawing ---------------------------------------------------------------
    def draw(self, s, now):
        s.fill((34, 30, 68))
        self.topbar(s, "Settings")
        visible = (LIST_BOT - LIST_TOP) // ROW_H
        if self.sel < self.scroll + 1:
            self.scroll = max(0, self.sel - 1)
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        self.scroll = max(0, min(self.scroll, len(self.rows) - visible))
        self.row_rects = []
        y = LIST_TOP
        for i in range(self.scroll, min(len(self.rows), self.scroll + visible)):
            row = self.rows[i]
            r = pygame.Rect(8, y, G.BASE_W - 16, ROW_H - 1)
            if row.kind == "head":
                self.g.text(s, row.label, (r.left + 2, y + 2), G.LAMP, "small")
                pygame.draw.line(s, G.DUSK, (r.left + 4 + self.g.width(row.label, "small"), y + 7), (r.right, y + 7))
            else:
                self.row_rects.append((i, r))
                focused = i == self.sel
                if focused:
                    pygame.draw.rect(s, (52, 48, 100), r)
                    pygame.draw.rect(s, G.LAMP, (r.left, r.top, 2, r.height))
                col = G.CREAM if row.enabled else G.HAZE
                self.g.text(s, row.label, (r.left + 8, y + 1), col, "small")
                right = r.right - 6
                if row.kind == "num" or row.label == "Input delay":
                    val = row.show()
                    vr = self.g.text(s, val, (right - 8, y + 1), G.LAMP if focused else G.CREAM, "small", "topright")
                    G.arrow(s, (right - 1, y + 6), 1, G.FOG if focused else G.DUSK)
                    G.arrow(s, (vr.left - 6, y + 6), -1, G.FOG if focused else G.DUSK)
                elif row.kind == "bool":
                    G.toggle(s, (right, y + 2), bool(row.get()) and row.enabled, focused)
                elif row.kind == "action":
                    if focused:
                        G.keycap(self.g, s, "Enter", (right, y + 6), "midright")
                if row.note and (focused or not row.enabled):
                    nx = right - 70 if row.kind != "num" else right - 110
                    self.g.text(s, row.note, (nx, y + 1), G.HAZE, "small", "topright")
            y += ROW_H
        # scroll bar
        if len(self.rows) > visible:
            h = LIST_BOT - LIST_TOP
            bh = max(10, h * visible // len(self.rows))
            by = LIST_TOP + (h - bh) * self.scroll // max(1, len(self.rows) - visible)
            pygame.draw.rect(s, G.DUSK, (G.BASE_W - 5, LIST_TOP, 2, h))
            pygame.draw.rect(s, G.FOG, (G.BASE_W - 5, by, 2, bh))
        msg, col = camera_text(self.ctx.tracker, self.ctx.sim)
        self.g.text(s, "Camera: " + msg[:48], (8, 181), col, "small")
        self.g.text(s, "Blinkythm %s  ·  MIT license" % __version__, (8, 198), G.HAZE, "small")
        self.button_row(s)


# ====================================================================== setup
class SetupState:
    def __init__(self):
        self.offset = None


class SetupScreen(Screen):
    step = 0
    heading = ""

    def __init__(self, ctx, state=None, standalone=False):
        super().__init__(ctx)
        self.state = state or SetupState()
        self.standalone = standalone            # opened from Settings instead of first-run setup

    def back_to_settings(self):
        from .system import SettingsScreen      # noqa: F811
        self.ctx.go(SettingsScreen(self.ctx))

    def frame(self, s, sub):
        s.fill((34, 30, 68))
        title = self.heading if self.standalone else "Setup  %d of 3  ·  %s" % (self.step, self.heading)
        self.topbar(s, title)
        y = 24
        for line in sub:
            for part in self.g.wrap(line, G.BASE_W - 24, "small"):
                self.g.text(s, part, (12, y), G.FOG, "small")
                y += 12
            y += 3
        return y


class SetupCameraScreen(SetupScreen):
    step = 1
    heading = "Camera"

    def __init__(self, ctx, state=None, standalone=False):
        super().__init__(ctx, state, standalone)
        self.face_since = None
        if standalone:
            self.buttons = [G.Button("Done", "Enter", self.back_to_settings, primary=True)]
        else:
            self.buttons = [G.Button("Next", "Enter", self._next, primary=True, enabled=False),
                            G.Button("Later", "Esc", ctx.close)]

    def _next(self):
        self.ctx.go(SetupCalibScreen(self.ctx, self.state))

    def key(self, k):
        if k in (pygame.K_LEFT, pygame.K_RIGHT):
            s = self.ctx.settings
            s.camera_index = max(0, min(9, s.camera_index + (1 if k == pygame.K_RIGHT else -1)))
            s.save()
            self.ctx.tracker.restart(s.camera_index)
            self.ctx.tracker.set_game_mode(True)
            self.ctx.sound("ui_move")
            return True
        if k == pygame.K_ESCAPE:
            self.buttons[-1].press()
            return True
        return super().key(k)

    def update(self, now):
        tr = self.ctx.tracker
        if tr.face_visible and not tr.error:
            if self.face_since is None:
                self.face_since = now
        else:
            self.face_since = None
        if not self.standalone:
            self.buttons[0].enabled = self.face_since is not None and now - self.face_since > 1.0

    def draw(self, s, now):
        y = self.frame(s, ["Blinks are detected with your webcam. Video stays on this computer and is only used to "
                           "measure how open your eyes are. Sit facing the screen in good light."])
        tr = self.ctx.tracker
        closed = tr.eye_closed
        self.g.blit_sprite(s, "owl_me_closed" if closed else "owl_me_open", (64, 172), 4)
        box = G.panel(s, (130, y + 4, 242, 120), (30, 27, 58), G.DUSK, light=(48, 44, 92))
        x0, yy = box.left + 8, box.top + 7
        msg, col = camera_text(tr, self.ctx.sim)
        self.g.text(s, "Camera", (x0, yy), G.FOG, "small")
        for i, part in enumerate(self.g.wrap(msg, 160, "small")[:2]):
            self.g.text(s, part, (x0 + 64, yy + i * 12), col, "small")
        yy += 26
        self.g.text(s, "Device", (x0, yy), G.FOG, "small")
        vr = self.g.text(s, "%d" % self.ctx.settings.camera_index, (x0 + 76, yy), G.CREAM, "small")
        G.arrow(s, (x0 + 68, yy + 5), -1, G.FOG)
        G.arrow(s, (vr.right + 6, yy + 5), 1, G.FOG)
        yy += 15
        face = tr.face_visible and not tr.error
        self.g.text(s, "Face", (x0, yy), G.FOG, "small")
        self.g.text(s, "Found" if face else "Not visible", (x0 + 64, yy), G.MINT if face else G.PEACH, "small")
        yy += 15
        self.g.text(s, "Eyes open", (x0, yy), G.FOG, "small")
        ratio = tr.ear_ratio
        G.bar(s, (x0 + 64, yy + 3, 150, 6), 0 if ratio is None else ratio / 1.1, G.LAMP if not closed else G.PEACH)
        yy += 16
        for part in self.g.wrap("Blink once. The bar should drop and come back.", box.width - 16, "small"):
            self.g.text(s, part, (x0, yy), G.HAZE, "small")
            yy += 12
        if self.ctx.sim:
            self.g.text(s, "Test mode: Space = blink", (x0, yy), G.PEACH, "small")
        self.button_row(s)


class SetupCalibScreen(SetupScreen):
    """Blink along to a steady beat for as long as you like; the offset settles as blinks come in."""
    step = 2
    heading = "Timing"
    LOOP_BEATS = 120                   # the metronome restarts after this many beats
    RING = (192, 100, 38)              # centre x, centre y, radius

    def __init__(self, ctx, state=None, standalone=False):
        super().__init__(ctx, state, standalone)
        self.cal = None
        self.t0 = None
        self.last = None               # (time, error) of the latest blink
        reset = G.Button("Reset", "R", self._reset)
        if standalone:
            self.buttons = [G.Button("Save", "Enter", self._save, primary=True, enabled=False),
                            reset, G.Button("Back", "Esc", self.back_to_settings)]
        else:
            self.buttons = [G.Button("Next", "Enter", self._next, primary=True, enabled=not ctx.audio.ok),
                            reset, G.Button("Back", "Esc", lambda: ctx.go(SetupCameraScreen(ctx, self.state)))]

    def enter(self):
        super().enter()
        self._play()

    def leave(self):
        self.ctx.audio.stop()

    def _play(self):
        n = self.LOOP_BEATS
        ticks = [(k * R.CAL_BEAT, k % 4 == 0) for k in range(n)]
        t0 = self.ctx.audio.play_track(ticks, [], n * R.CAL_BEAT)
        if t0 is None:
            return
        self.t0 = t0
        if self.cal is None:
            self.cal = R.Calibrator(t0)
        else:
            self.cal.t0 = t0

    def _reset(self):
        if self.cal is not None:
            self.cal.reset()
        self.last = None

    def _use(self):
        off, sd, n, ready = self.cal.state() if self.cal else (None, None, 0, False)
        return off if ready else None

    def _next(self):
        off = self._use()
        if off is not None:
            self.state.offset = off
        self.ctx.go(SetupFinishScreen(self.ctx, self.state))

    def _save(self):
        off = self._use()
        if off is not None:
            self.ctx.settings.latency_offset = round(off, 3)
            self.ctx.settings.save()
        self.back_to_settings()

    def key(self, k):
        if k == pygame.K_r:
            self.buttons[1].press()
            return True
        if k == pygame.K_ESCAPE:
            self.buttons[2].press()
            return True
        return super().key(k)

    def blink(self, onset):
        if self.cal is not None:
            e = self.cal.add(onset)
            if e is not None:
                self.last = (time.perf_counter(), e)

    def update(self, now):
        if self.t0 is not None and now - self.t0 >= self.LOOP_BEATS * R.CAL_BEAT:
            self._play()
        ready = self.cal is not None and self.cal.state()[3]
        if self.ctx.audio.ok:
            self.buttons[0].enabled = ready

    def draw(self, s, now):
        y = self.frame(s, ["Blink on every tick. Keep going until the offset stops moving, then press Enter."])
        cx, cy, r = self.RING
        beat = (now - self.t0) / R.CAL_BEAT if self.t0 is not None else 0.0
        phase = beat % 1.0
        pulse = G.beat_pulse(beat) if self.t0 is not None else 0.0
        # ring, drawn as pixels so it stays crisp
        ring_col = G.HAZE if pulse < 0.5 else G.FOG
        for i in range(96):
            a = 2 * math.pi * i / 96
            s.set_at((round(cx + r * math.sin(a)), round(cy - r * math.cos(a))), ring_col)
        # the beat lands at the top
        pygame.draw.polygon(s, G.LAMP, [(cx - 3, cy - r - 7), (cx + 3, cy - r - 7), (cx, cy - r - 3)])
        if pulse > 0.3:
            pygame.draw.circle(s, G.LAMP, (cx, cy - r), round(2 + 3 * pulse), 1)
        # orbiting dot
        if self.t0 is not None:
            a = 2 * math.pi * phase
            pygame.draw.rect(s, G.CREAM, (round(cx + r * math.sin(a)) - 2, round(cy - r * math.cos(a)) - 2, 5, 5))
        # where recent blinks landed: angle = error as a share of the beat
        recent = self.cal.errors[-R.CAL_RECENT:] if self.cal else []
        good = self.cal.used() if self.cal else []
        for k, e in enumerate(recent):
            a = 2 * math.pi * e / R.CAL_BEAT
            rr = r + 7
            col = G.MINT if e in good else G.HAZE
            if k == len(recent) - 1:
                col = G.LAMP
            pygame.draw.rect(s, col, (round(cx + rr * math.sin(a)) - 1, round(cy - rr * math.cos(a)) - 1, 3, 3))
        # the eye in the middle shows what the camera sees
        closed = self.ctx.tracker.eye_closed
        G.eye_icon(s, (cx, cy), closed, G.LAMP if closed else G.FOG)
        if self.last and now - self.last[0] < 0.6:
            ms = round(self.last[1] * 1000)
            self.g.text(s, "%+d ms" % ms, (cx, cy + 9), G.CREAM, "small", "midtop")
        # numbers
        off, sd, n, ready = self.cal.state() if self.cal else (None, None, 0, False)
        box = G.panel(s, (262, y + 8, 112, 84), (30, 27, 58), G.DUSK, light=(48, 44, 92))
        bx, by = box.left + 8, box.top + 6
        self.g.text(s, "Offset", (bx, by), G.FOG, "small")
        self.g.text(s, "-" if off is None else "%+d ms" % round(off * 1000), (box.right - 8, by - 2),
                    G.LAMP if ready else G.CREAM, "bold", "topright")
        self.g.text(s, "Spread", (bx, by + 18), G.FOG, "small")
        self.g.text(s, "-" if sd is None else "%d ms" % round(sd * 1000), (box.right - 8, by + 18), G.CREAM, "small", "topright")
        self.g.text(s, "Blinks", (bx, by + 31), G.FOG, "small")
        self.g.text(s, "%d / %d" % (min(n, R.CAL_MIN_HITS), R.CAL_MIN_HITS) if n < R.CAL_MIN_HITS else "%d" % n,
                    (box.right - 8, by + 31), G.CREAM, "small", "topright")
        if not self.ctx.audio.ok:
            status, col = "No audio device. You can skip this.", G.PEACH
        elif ready:
            status, col = "Steady. Enter to use it.", G.MINT
        elif n >= R.CAL_MIN_HITS:
            status, col = "Still uneven. Keep going.", G.PEACH
        else:
            status, col = "Keep blinking on the tick.", G.FOG
        for i, part in enumerate(self.g.wrap(status, box.width - 16, "small")):
            self.g.text(s, part, (bx, by + 50 + i * 12), col, "small")
        self.g.text(s, "Saved: %+d ms" % round(self.ctx.settings.latency_offset * 1000), (box.left, box.bottom + 4),
                    G.HAZE, "small")
        closed_owl = self.ctx.tracker.eye_closed
        self.g.blit_sprite(s, "owl_me_closed" if closed_owl else "owl_me_open", (60, 160), 3)
        if self.ctx.sim:
            self.g.text(s, "Test mode: Space = blink", (8, 181), G.PEACH, "small")
        self.button_row(s)


class SetupFinishScreen(SetupScreen):
    step = 3
    heading = "Done"

    def __init__(self, ctx, state=None, standalone=False):
        super().__init__(ctx, state, standalone)
        self.monitor_on = True
        self.autostart = winenv.is_autostart()
        self.opts = []
        self.sel = 0
        self.buttons = [G.Button("Finish", "Enter", self._finish, primary=True),
                        G.Button("Back", "Esc", lambda: ctx.go(SetupCalibScreen(ctx, self.state)))]

    def _finish(self):
        s = self.ctx.settings
        if self.state.offset is not None:
            s.latency_offset = self.state.offset
        s.monitoring = self.monitor_on
        s.first_run_done = True
        s.save()
        if winenv.IS_WIN:
            winenv.set_autostart(self.autostart)
        self.ctx.go(HomeScreen(self.ctx))

    def _flip(self, i):
        if i == 0:
            self.monitor_on = not self.monitor_on
        elif winenv.IS_WIN:
            self.autostart = not self.autostart
        self.ctx.sound("ui_move")

    def key(self, k):
        if k in (pygame.K_UP, pygame.K_DOWN):
            self.sel = 1 - self.sel
            self.ctx.sound("ui_move")
        elif k in (pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT):
            self._flip(self.sel)
        elif k == pygame.K_ESCAPE:
            self.buttons[1].press()
        else:
            return super().key(k)
        return True

    def click(self, pos, right=False):
        for i, r in enumerate(self.opts):
            if r.collidepoint(pos):
                self.sel = i
                self._flip(i)
                return True
        return super().click(pos, right)

    def draw(self, s, now):
        st = self.ctx.settings
        y = self.frame(s, ["After %d minutes at the screen with fewer than %d blinks a minute, Blinkythm will suggest "
                           "a short game. It waits in the tray until then. You can change all of this in Settings."
                           % (st.screen_minutes, st.blink_threshold)])
        offset = self.state.offset if self.state.offset is not None else st.latency_offset
        self.g.text(s, "Input delay offset: %+d ms" % round(offset * 1000), (12, y), G.CREAM, "small")
        y += 18
        self.opts = []
        items = [("Monitor blinking", self.monitor_on, True),
                 ("Start Blinkythm with Windows", self.autostart, winenv.IS_WIN)]
        for i, (label, on, enabled) in enumerate(items):
            r = pygame.Rect(8, y, 220, 13)
            self.opts.append(r)
            if i == self.sel:
                pygame.draw.rect(s, (52, 48, 100), r)
                pygame.draw.rect(s, G.LAMP, (r.left, r.top, 2, r.height))
            self.g.text(s, label, (r.left + 8, y + 1), G.CREAM if enabled else G.HAZE, "small")
            G.toggle(s, (r.right - 4, y + 2), on and enabled, i == self.sel)
            y += 15
        self.g.text(s, "Space toggles", (12, y + 2), G.HAZE, "small")
        bob = round(math.sin(now * 2))
        self.g.blit_sprite(s, "owl_me_open", (320, 170 + bob), 3)
        self.button_row(s)
