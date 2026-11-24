"""게임 창의 화면들: 홈, 게임 고르기, 플레이, 쉬는 시간(메들리), 결과, 먼 곳 보기."""
import math
import time

import pygame

from .. import rhythm as R
from .. import stages as S
from . import gfx as G
from .scenes import SCENE_BOT, View, make_scene

LANE_X0, LANE_X1, LANE_Y0, LANE_Y1 = 40, 372, 176, 206
REST_SECONDS = 20
INTERLUDE = 3.5
STAMP_SLOTS = 10
JINGLES = ["jingle_great", "jingle_good", "jingle_try", "jingle_try"]


def fmt_minutes(sec):
    m = int(sec // 60)
    return "%d시간 %02d분" % (m // 60, m % 60) if m >= 60 else "%d분" % m


class Screen:
    title = ""
    accepts_double_blink = False

    def __init__(self, ctx):
        self.ctx = ctx
        self.g = ctx.gfx
        self.buttons = []
        self.focus = 0
        self.t_enter = time.perf_counter()

    # 수명
    def enter(self):
        self.t_enter = time.perf_counter()

    def leave(self):
        pass

    def update(self, now):
        pass

    # 입력
    def key(self, k):
        if not self.buttons:
            return False
        if k in (pygame.K_LEFT, pygame.K_UP):
            self._move(-1)
        elif k in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_TAB):
            self._move(1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.ctx.sound("ui_ok")
            self.buttons[self.focus].action()
        else:
            return False
        return True

    def _move(self, d):
        self.focus = (self.focus + d) % len(self.buttons)
        self.ctx.sound("ui_move")

    def hover(self, pos):
        for i, b in enumerate(self.buttons):
            if b.rect.collidepoint(pos) and i != self.focus:
                self.focus = i
                self.ctx.sound("ui_move")

    def click(self, pos):
        for b in self.buttons:
            if b.rect.collidepoint(pos):
                self.ctx.sound("ui_ok")
                b.action()
                return True
        return False

    def blink(self, onset):
        pass

    def double_blink(self):
        if self.accepts_double_blink and self.buttons:
            self.ctx.sound("ui_ok")
            self.buttons[0].action()

    # 그리기
    def draw(self, s, now):
        raise NotImplementedError

    def topbar(self, s, title, right=None, beat=None):
        pygame.draw.rect(s, G.INK, (0, 0, G.BASE_W, 16))
        pygame.draw.line(s, G.DUSK, (0, 16), (G.BASE_W, 16))
        self.g.text(s, title, (6, 2), G.CREAM, "bold")
        x = G.BASE_W - 6
        tr = self.ctx.tracker
        if tr.error:
            r = self.g.text(s, "카메라 오류", (x, 3), G.ROSE, "small", "topright")
        elif not tr.face_visible:
            r = self.g.text(s, "얼굴이 안 보여요", (x, 3), G.PEACH, "small", "topright")
        else:
            G.eye_icon(s, (x - 6, 8), tr.eye_closed, G.CREAM)
            r = pygame.Rect(x - 12, 3, 12, 10)
        if right:
            self.g.text(s, right, (r.left - 8, 3), G.FOG, "small", "topright")
        if beat is not None and beat >= 0:
            p = G.beat_pulse(beat)
            c = G.LAMP if p > 0.4 else G.DUSK
            pygame.draw.rect(s, c, (r.left - 4 - (self.g.width(right, "small") + 8 if right else 0) - 6, 6, 4, 4))

    def button_row(self, s, y=194):
        rects = G.layout_buttons(self.g, self.buttons, G.BASE_W - 8, y)
        for i, (b, r) in enumerate(zip(self.buttons, rects)):
            b.draw(self.g, s, r, i == self.focus)


# ====================================================================== 홈
class HomeScreen(Screen):
    accepts_double_blink = True
    STARS = G.stars(5, (0, 0, G.BASE_W, 120), 60)
    HOUSES = [(108, 18, 16), (130, 14, 22), (150, 20, 14), (176, 12, 12)]

    def __init__(self, ctx):
        super().__init__(ctx)
        self.pick = ctx.recommended()
        self.pick_title = S.make_stage(self.pick).title
        self.buttons = [
            G.Button("시작", "Enter", lambda: ctx.start([self.pick]), primary=True),
            G.Button("게임 고르기", "G", lambda: ctx.go(SelectScreen(ctx))),
            G.Button("설정", "S", ctx.open_settings),
            G.Button("닫기", "Esc", ctx.close),
        ]

    def key(self, k):
        if k == pygame.K_g:
            self.ctx.go(SelectScreen(self.ctx))
        elif k == pygame.K_s:
            self.ctx.open_settings()
        elif k == pygame.K_ESCAPE:
            self.ctx.close()
        else:
            return super().key(k)
        return True

    def draw(self, s, now):
        t = now - self.t_enter
        s.fill((34, 30, 68))
        G.draw_stars(s, self.STARS, now)
        pygame.draw.circle(s, (240, 230, 176), (352, 30), 9)
        pygame.draw.circle(s, (34, 30, 68), (356, 27), 8)
        # 언덕과 마을
        pts = [(0, 140)] + [(x, 132 - int(10 * math.sin(x / 40.0))) for x in range(0, G.BASE_W + 1, 8)] + [(G.BASE_W, 140)]
        pygame.draw.polygon(s, (48, 44, 92), pts + [(G.BASE_W, 216), (0, 216)])
        for i, (x, w, h) in enumerate(self.HOUSES):
            base = 136 - int(10 * math.sin(x / 40.0))
            pygame.draw.rect(s, (30, 27, 58), (x, base - h, w, h))
            pygame.draw.polygon(s, (30, 27, 58), [(x - 2, base - h), (x + w // 2, base - h - 7), (x + w + 2, base - h)])
            lit = math.sin(now * 0.7 + i * 1.9) > -0.6       # 창문이 가끔 깜빡인다
            pygame.draw.rect(s, G.LAMP if lit else (60, 54, 96), (x + w // 2 - 2, base - h + 5, 4, 4))
        pygame.draw.rect(s, (40, 36, 80), (0, 150, G.BASE_W, 66))
        pygame.draw.line(s, (56, 52, 104), (0, 150), (G.BASE_W, 150))
        # 제목
        bob = round(math.sin(t * 2) * 1)
        self.g.text(s, "Blinkythm", (14, 12 + bob), G.LAMP, "bold", shadow=(150, 96, 40), scale=3)
        self.g.text(s, "눈을 깜빡여 박자를 맞추는 작은 리듬 게임", (16, 62), G.FOG, "small")
        # 마스코트: 내 눈을 따라 깜빡이고, 가끔 혼자 깜빡인다
        closed = self.ctx.tracker.eye_closed or (t % 3.4) < 0.14
        pygame.draw.rect(s, G.WOOD, (52, 146, 40, 6))
        pygame.draw.rect(s, (96, 62, 38), (58, 152, 4, 30))
        pygame.draw.rect(s, (96, 62, 38), (82, 152, 4, 30))
        self.g.blit_sprite(s, "owl_me_closed" if closed else "owl_me_open", (72, 147), scale=4)
        # 오늘의 눈
        box = G.panel(s, (196, 74, 176, 102), (30, 27, 58), G.DUSK, light=(48, 44, 92))
        self.g.text(s, "오늘의 눈", (box.left + 8, box.top + 5), G.CREAM, "bold")
        mon, st = self.ctx.monitor, self.ctx.settings
        now_p = time.perf_counter()
        rate = mon.blink_rate(now_p)
        y = box.top + 25
        self.g.text(s, "화면 본 시간", (box.left + 8, y), G.FOG, "small")
        self.g.text(s, fmt_minutes(mon.screen_seconds(now_p)), (box.right - 8, y), G.CREAM, "small", "topright")
        y += 15
        self.g.text(s, "분당 깜빡임", (box.left + 8, y), G.FOG, "small")
        if rate is None:
            self.g.text(s, "재는 중", (box.right - 8, y), G.HAZE, "small", "topright")
        else:
            col = G.MINT if rate >= st.blink_threshold else G.PEACH
            self.g.text(s, "%d회" % round(rate), (box.right - 8, y), col, "small", "topright")
            bx = pygame.Rect(box.left + 70, y + 4, 64, 4)
            G.bar(s, bx, rate / 30.0, col)
            tx = bx.left + round(bx.width * st.blink_threshold / 30.0)
            pygame.draw.line(s, G.CREAM, (tx, bx.top - 2), (tx, bx.bottom + 1))
        y += 15
        daily = self.ctx.daily()
        self.g.text(s, "오늘 쉰 횟수", (box.left + 8, y), G.FOG, "small")
        self.g.text(s, "%d번" % daily["rests"], (box.right - 8, y), G.CREAM, "small", "topright")
        y += 18
        stamps = self.ctx.settings.stamps
        filled = stamps % STAMP_SLOTS if stamps % STAMP_SLOTS or not stamps else STAMP_SLOTS
        for i in range(STAMP_SLOTS):
            cx = box.left + 14 + i * 16
            if i < filled:
                pygame.draw.circle(s, G.ROSE, (cx, y + 6), 6)
                pygame.draw.circle(s, (250, 170, 170), (cx, y + 6), 4, 1)
            else:
                pygame.draw.circle(s, G.DUSK, (cx, y + 6), 6, 1)
        cards = stamps // STAMP_SLOTS
        y += 16
        self.g.text(s, "오늘의 게임", (box.left + 8, y), G.FOG, "small")
        self.g.text(s, self.pick_title, (box.right - 8, y), G.LAMP, "small", "topright")
        if cards:
            self.g.text(s, "도장판 %d장 채움" % cards, (box.right - 8, box.top + 6), G.HAZE, "small", "topright")
        self.g.text(s, "눈을 두 번 깜빡여도 시작해요", (G.BASE_W - 8, 181), G.HAZE, "small", "topright")
        self.button_row(s)


# ====================================================================== 게임 고르기
class SelectScreen(Screen):
    accepts_double_blink = True
    TILE_BG = {"lighthouse": ((16, 28, 64), (20, 56, 104)), "owls": ((30, 24, 64), (36, 34, 78)),
               "photo": ((226, 210, 178), (150, 104, 70))}
    HERO = {"lighthouse": "lighthouse_on", "owls": "owl_me_open", "photo": "camera_open"}

    def __init__(self, ctx):
        super().__init__(ctx)
        self.stages = [S.make_stage(k) for k in S.ORDER]
        pick = ctx.recommended()
        self.sel = S.ORDER.index(pick) if pick in S.ORDER else 0
        self.tiles = []
        self.buttons = [
            G.Button("시작", "Enter", self._start, primary=True),
            G.Button("메들리", "M", lambda: ctx.start(list(S.ORDER))),
            G.Button("뒤로", "Esc", lambda: ctx.go(HomeScreen(ctx))),
        ]

    def _start(self):
        self.ctx.start([S.ORDER[self.sel]])

    def key(self, k):
        if k in (pygame.K_LEFT, pygame.K_RIGHT):
            self.sel = (self.sel + (1 if k == pygame.K_RIGHT else -1)) % len(self.stages)
            self.ctx.sound("ui_move")
        elif k == pygame.K_m:
            self.ctx.start(list(S.ORDER))
        elif k == pygame.K_ESCAPE:
            self.ctx.go(HomeScreen(self.ctx))
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.ctx.sound("ui_ok")
            self.buttons[self.focus].action()
        elif k in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
            self._move(1 if k != pygame.K_UP else -1)
        else:
            return False
        return True

    def hover(self, pos):
        for i, r in enumerate(self.tiles):
            if r.collidepoint(pos) and i != self.sel:
                self.sel = i
                self.ctx.sound("ui_move")
        super().hover(pos)

    def click(self, pos):
        for i, r in enumerate(self.tiles):
            if r.collidepoint(pos):
                self.sel = i
                self.ctx.sound("ui_ok")
                self._start()
                return True
        return super().click(pos)

    def draw(self, s, now):
        s.fill((34, 30, 68))
        self.topbar(s, "게임 고르기")
        rec = self.ctx.settings.records or {}
        self.tiles = []
        t = now - self.t_enter
        for i, st in enumerate(self.stages):
            x = 12 + i * 124
            focused = i == self.sel
            lift = -2 if focused else 0
            r = pygame.Rect(x, 26 + lift, 112, 112)
            self.tiles.append(r)
            if focused:
                pygame.draw.rect(s, G.INK, r.move(0, 3))
            G.panel(s, r, (30, 27, 58), G.LAMP if focused else G.DUSK)
            top, bottom = self.TILE_BG[st.key]
            art = pygame.Rect(r.left + 3, r.top + 3, r.width - 6, 62)
            pygame.draw.rect(s, top, art)
            pygame.draw.rect(s, bottom, (art.left, art.bottom - 14, art.width, 14))
            hop = round(abs(math.sin(t * 3)) * 2) if focused else 0
            self.g.blit_sprite(s, self.HERO[st.key], (art.centerx, art.bottom - 3 - hop))
            self.g.text(s, st.title, (r.left + 8, art.bottom + 5), G.CREAM, "bold")
            self.g.text(s, "%s · %d초" % (st.style, round(st.seconds)), (r.left + 8, art.bottom + 22), G.FOG, "small")
            best = rec.get(st.key)
            if best is not None:
                self.g.text(s, "최고 %d%%" % round(best), (r.right - 7, art.bottom + 22), G.LAMP, "small", "topright")
        st = self.stages[self.sel]
        y = 146
        for line in st.howto[:2]:
            for part in self.g.wrap(line, 360, "small"):
                if y > 178:
                    break
                self.g.text(s, part, (14, y), G.CREAM, "small")
                y += 12
        self.button_row(s)


# ====================================================================== 플레이
class PlayScreen(Screen):
    title = "플레이"

    def __init__(self, ctx, key, queue, played):
        super().__init__(ctx)
        self.key_name = key
        self.queue = queue
        self.played = played
        self.stage = S.make_stage(key)
        self.scene = make_scene(self.g, self.stage)
        self.hits = []
        self.popup = None
        self.done = False

    def enter(self):
        super().enter()
        st, c = self.stage, self.ctx
        self.judge = R.Judge(st.notes, 0.0, st.beat_sec, offset=c.settings.latency_offset,
                             slack=R.frame_slack(c.tracker.frame_dt))
        c.audio.prepare([st.hit_sound, "dull"])
        t0 = c.audio.play_stage(st)
        if t0 is None:
            t0 = time.perf_counter() + 0.3
        self.t0 = t0
        for q in st.cues:
            q.time = t0 + q.beat * st.beat_sec
        for n in st.notes:
            n.time = t0 + n.beat * st.beat_sec

    def leave(self):
        if not self.done:
            self.ctx.audio.stop()

    def key(self, k):
        if k == pygame.K_ESCAPE:
            self.ctx.audio.stop()
            self.ctx.go(SelectScreen(self.ctx))
            return True
        return False

    def blink(self, onset):
        res = self.judge.on_blink(onset)
        if res is not None:
            self._result(res, time.perf_counter(), quiet=False)

    def _result(self, res, now, quiet):
        self.hits.append((now, res))
        a = self.ctx.audio
        if not quiet:
            if res.grade == R.OK:
                a.play_sfx(self.stage.hit_sound, soft=True)
                a.play_sfx("dull")
            else:
                a.play_sfx(self.stage.hit_sound)
        if res.grade == R.MISS:
            self.popup = (R.LABEL[R.MISS], "", now)
        else:
            ms = int(round(res.dt * 1000))
            sub = "딱 맞아요" if abs(ms) <= 25 else ("%dms 늦게" % ms if ms > 0 else "%dms 일찍" % -ms)
            self.popup = (R.LABEL[res.grade], sub, now)

    def update(self, now):
        if self.done:
            return
        for res in self.judge.poll(now):
            self._result(res, now, quiet=True)
        if now - self.t0 >= self.stage.seconds:
            self.done = True
            self.judge.poll(float("inf"))
            sm = self.judge.summary(len(self.stage.sections))
            self.played.append((self.stage, sm))
            self.ctx.record_play()
            if self.queue:
                self.ctx.go(InterludeScreen(self.ctx, self.queue, self.played), fade=False)
            else:
                self.ctx.go(ResultScreen(self.ctx, self.played))

    def draw(self, s, now):
        st = self.stage
        beat = (now - self.t0) / st.beat_sec
        view = View(now, beat, self.ctx.tracker.eye_closed, self.hits)
        self.scene.draw(s, view)
        # 머리줄
        if beat < S.COUNT_IN:
            sub = "준비"
        elif beat >= st.length:
            sub = "끝"
        else:
            sub = self.scene.phase_text(beat) or st.section_at(beat)
        done = sum(1 for m in self.judge.matched if m is not None)
        self.topbar(s, st.title, "%d / %d" % (done, len(st.notes)), beat)
        self.g.text(s, sub, (self.g.width(st.title, "bold") + 16, 3), G.FOG, "small")
        # 세기
        if 0 <= beat < S.COUNT_IN:
            n = S.COUNT_IN - int(beat)
            k = G.ease_out_back((beat % 1.0) * 3)
            img = self.g.render(str(n), G.CREAM, "bold", 4)
            img = pygame.transform.scale_by(img, 0.6 + 0.4 * k) if k < 1 else img
            r = img.get_rect(center=(G.BASE_W // 2, 60))
            sh = self.g.render(str(n), G.INK, "bold", 4)
            if k >= 1:
                s.blit(sh, r.move(0, 3))
            s.blit(img, r)
        # 판정 말풍선
        if self.popup and now - self.popup[2] < 0.7:
            text, sub, t = self.popup
            grade = next((g for g, lb in R.LABEL.items() if lb == text), R.MISS)
            col = G.GRADE_COLOR[grade]
            x, y = self.scene.popup_pos
            rise = round(4 * (1 - G.ease_out((now - t) / 0.25)))
            w = max(self.g.width(text, "bold"), self.g.width(sub, "small")) + 14
            h = 30 if sub else 19
            r = pygame.Rect(0, 0, w, h)
            r.center = (x, y + rise)
            G.panel(s, r, G.INK, col)
            self.g.text(s, text, (r.centerx, r.top + 2), col, "bold", "midtop")
            if sub:
                self.g.text(s, sub, (r.centerx, r.top + 17), G.FOG, "small", "midtop")
        self._lane(s, now, beat)

    def _lane(self, s, now, beat):
        st = self.stage
        pygame.draw.rect(s, G.INK, (0, SCENE_BOT, G.BASE_W, G.BASE_H - SCENE_BOT))
        pygame.draw.line(s, G.DUSK, (0, SCENE_BOT), (G.BASE_W, SCENE_BOT))
        if beat < S.COUNT_IN:
            for i in range(S.COUNT_IN):
                x = G.BASE_W // 2 - 27 + i * 18
                on = beat >= i
                pygame.draw.rect(s, G.LAMP if on else G.DUSK, (x - 4, 187, 8, 8))
            self.g.text(s, "소리를 들으며 박자를 세어 보세요", (G.BASE_W // 2, 199), G.FOG, "small", "midtop")
            return
        page = max(0, int((beat - S.COUNT_IN) // S.PAGE_BEATS))
        base = S.COUNT_IN + S.PAGE_BEATS * page
        px = (LANE_X1 - LANE_X0) / S.PAGE_BEATS

        def bx(b):
            return round(LANE_X0 + (b - base) * px)

        def on_page(b):
            return base - 1e-6 <= b <= base + S.PAGE_BEATS + 1e-6

        mid = (LANE_Y0 + LANE_Y1) // 2
        pygame.draw.rect(s, (36, 33, 66), (LANE_X0, LANE_Y0, LANE_X1 - LANE_X0, mid - LANE_Y0))
        pygame.draw.rect(s, (44, 41, 82), (LANE_X0, mid, LANE_X1 - LANE_X0, LANE_Y1 - mid))
        for k in range(S.PAGE_BEATS + 1):
            x = round(LANE_X0 + k * px)
            pygame.draw.line(s, G.HAZE if k % 4 == 0 else G.DUSK, (x, LANE_Y0), (x, LANE_Y1 - 1))
        self.g.text(s, "신호", (LANE_X0 - 6, (LANE_Y0 + mid) // 2), G.HAZE, "small", "midright")
        self.g.text(s, "나", (LANE_X0 - 6, (mid + LANE_Y1) // 2), G.LAMP, "small", "midright")
        cy = (LANE_Y0 + mid) // 2
        for q in st.cues:
            if on_page(q.beat) and now >= q.time:
                x = bx(q.beat)
                pygame.draw.rect(s, G.FOG, (x - 2, cy - 2, 5, 5))
        ny = (mid + LANE_Y1) // 2
        guide = self.ctx.settings.show_guide
        for i, n in enumerate(st.notes):
            if not on_page(n.beat):
                continue
            x = bx(n.beat)
            m = self.judge.matched[i]
            if m is not None:
                col = G.GRADE_COLOR[m.grade]
                if m.grade == R.MISS:
                    pygame.draw.line(s, col, (x - 3, ny - 3), (x + 3, ny + 3))
                    pygame.draw.line(s, col, (x - 3, ny + 3), (x + 3, ny - 3))
                else:
                    pygame.draw.rect(s, col, (x - 3, ny - 3, 7, 7))
            elif guide and beat >= n.reveal:
                for dx, dy in ((-3, -3), (3, -3), (-3, 3), (3, 3)):
                    pygame.draw.rect(s, G.CREAM, (x + dx - (dx > 0), ny + dy - (dy > 0), 2, 2))
        x = max(LANE_X0, min(LANE_X1, bx(beat)))
        pygame.draw.line(s, G.CREAM, (x, LANE_Y0 - 2), (x, LANE_Y1 + 1))
        pygame.draw.rect(s, G.CREAM, (x - 1, LANE_Y0 - 3, 3, 2))


# ====================================================================== 메들리 쉬는 시간
class InterludeScreen(Screen):
    def __init__(self, ctx, queue, played):
        super().__init__(ctx)
        self.queue = queue
        self.played = played
        self.next = S.make_stage(queue[0])

    def enter(self):
        super().enter()
        stage, sm = self.played[-1]
        self.ctx.audio.play_jingle(JINGLES[R.rank_level(sm["accuracy"])])

    def key(self, k):
        if k == pygame.K_ESCAPE:
            self.ctx.go(SelectScreen(self.ctx))
            return True
        return False

    def update(self, now):
        if now - self.t_enter >= INTERLUDE:
            key = self.queue.pop(0)
            self.ctx.go(PlayScreen(self.ctx, key, self.queue, self.played), fade=False)

    def draw(self, s, now):
        s.fill((34, 30, 68))
        total = len(self.played) + len(self.queue)
        self.topbar(s, "메들리 %d / %d" % (len(self.played), total))
        stage, sm = self.played[-1]
        self.g.text(s, "%s  %d%%" % (stage.title, round(sm["accuracy"])), (G.BASE_W // 2, 40), G.FOG, "body", "midtop")
        self.g.text(s, R.rank_of(sm["accuracy"]), (G.BASE_W // 2, 58), G.ROSE, "bold", "midtop")
        self.g.text(s, "다음", (G.BASE_W // 2, 92), G.HAZE, "small", "midtop")
        self.g.text(s, self.next.title, (G.BASE_W // 2, 104), G.LAMP, "bold", "midtop", shadow=(150, 96, 40), scale=3)
        y = 154
        for part in self.g.wrap(self.next.howto[1], 340, "small"):
            self.g.text(s, part, (G.BASE_W // 2, y), G.CREAM, "small", "midtop")
            y += 12
        left = max(0.0, INTERLUDE - (now - self.t_enter))
        G.bar(s, (92, 196, 200, 3), 1 - left / INTERLUDE, G.LAMP)


# ====================================================================== 결과
class ResultScreen(Screen):
    accepts_double_blink = True

    def __init__(self, ctx, played):
        super().__init__(ctx)
        self.played = played
        self.medley = len(played) > 1
        if self.medley:
            self.sm = R.combine([x[1] for x in played])
            self.key_name, self.names, self.name = S.MEDLEY, [x[0].title for x in played], "메들리"
        else:
            st, self.sm = played[0]
            self.key_name, self.names, self.name = st.key, st.sections, st.title
        self.new_best = ctx.save_record(self.key_name, self.sm["accuracy"], None if self.medley else played[0][0].key)
        self.feedback = R.feedback(self.sm, self.names)
        self.shift = R.suggest_offset_shift(self.sm)
        self.shift_msg = None
        replay = [x[0].key for x in played]
        self.buttons = [
            G.Button("눈 쉬러 가기", "Enter", lambda: ctx.go(RestScreen(ctx)), primary=True),
            G.Button("다시", "R", lambda: ctx.start(list(replay))),
            G.Button("고르기", "G", lambda: ctx.go(SelectScreen(ctx))),
        ]
        self.stamped = False

    def key(self, k):
        if k == pygame.K_r:
            self.buttons[1].action()
        elif k == pygame.K_g:
            self.buttons[2].action()
        elif k == pygame.K_a and self.shift is not None:
            self.shift_msg = self.ctx.apply_offset(self.shift)
            self.shift = None
        elif k == pygame.K_ESCAPE:
            self.ctx.go(HomeScreen(self.ctx))
        else:
            return super().key(k)
        return True

    def update(self, now):
        if not self.stamped and now - self.t_enter > 0.45:
            self.stamped = True
            self.ctx.sound("stamp")
            self.ctx.audio.play_jingle(JINGLES[R.rank_level(self.sm["accuracy"])])

    def draw(self, s, now):
        sm = self.sm
        s.fill((34, 30, 68))
        self.topbar(s, "%s 결과" % self.name)
        t = now - self.t_enter
        # 왼쪽: 도장, 정확도, 판정 수
        left = G.panel(s, (8, 22, 136, 166), (30, 27, 58), G.DUSK, light=(48, 44, 92))
        cx, cy = left.centerx, 68
        if t > 0.45:
            k = G.ease_out_back((t - 0.45) / 0.25)
            r = max(1, round(36 * (1.6 - 0.6 * k)))
            pygame.draw.circle(s, G.ROSE, (cx, cy), r, 2)
            pygame.draw.circle(s, G.ROSE, (cx, cy), max(1, r - 4), 1)
            if k >= 0.9:
                self.g.text(s, sm["rank"], (cx, cy), G.ROSE, "bold", "center")
        if self.new_best and t > 0.9:
            self.g.text(s, "새 기록", (left.right - 6, left.top + 4), G.LAMP, "small", "topright")
        self.g.text(s, "%d%%" % round(sm["accuracy"]), (cx, 106), G.CREAM, "bold", "midtop", shadow=G.INK, scale=3)
        y = 158
        for i, g in enumerate(R.GRADES):
            x = left.left + 10 + (i % 2) * 64
            yy = y + (i // 2) * 14
            pygame.draw.rect(s, G.GRADE_COLOR[g], (x, yy + 4, 5, 5))
            self.g.text(s, "%s %d" % (R.LABEL[g], sm["counts"][g]), (x + 9, yy), G.CREAM, "small")
        # 오른쪽: 구간, 한 줄 평, 타이밍
        right = G.panel(s, (150, 22, 226, 166), (30, 27, 58), G.DUSK, light=(48, 44, 92))
        self.g.text(s, "게임별" if self.medley else "구간별", (right.left + 8, right.top + 5), G.FOG, "small")
        y = right.top + 20
        for name, acc in zip(self.names, sm["sections"]):
            self.g.text(s, name, (right.left + 8, y), G.CREAM, "small")
            frac = 0 if acc is None else acc / 100
            shown = frac * G.ease_out((t - 0.2) / 0.6)
            G.bar(s, (right.left + 90, y + 4, 92, 5), shown, G.MINT if frac >= 0.65 else G.PEACH)
            self.g.text(s, "-" if acc is None else "%d%%" % round(acc), (right.right - 8, y), G.CREAM, "small", "topright")
            y += 13
        y += 4
        for line in self.feedback[:2]:
            for part in self.g.wrap(line, right.width - 16, "small")[:2]:
                self.g.text(s, part, (right.left + 8, y), G.LAMP, "small")
                y += 12
        # 타이밍 분포
        hy = right.bottom - 40
        self._hist(s, pygame.Rect(right.left + 8, hy, 96, 24), sm["dts"])
        if sm["mean_dt"] is None:
            msg = "깜빡임이 잡히지 않았어요"
        else:
            ms = sm["mean_dt"] * 1000
            msg = "평균 %d ms %s" % (abs(round(ms)), "늦게" if ms > 0 else "일찍")
        self.g.text(s, msg, (right.left + 112, hy), G.CREAM, "small")
        if self.shift is not None:
            keycap(self.g, s, "A", (right.left + 112, hy + 19))
            self.g.text(s, "보정에 반영", (right.left + 126, hy + 14), G.FOG, "small")
        elif self.shift_msg:
            self.g.text(s, self.shift_msg, (right.left + 112, hy + 14), G.MINT, "small")
        elif sm["stray"]:
            self.g.text(s, "박자 밖 깜빡임 %d번" % sm["stray"], (right.left + 112, hy + 14), G.HAZE, "small")
        self.button_row(s)

    def _hist(self, s, r, dts):
        lo, hi, bins = -0.24, 0.24, 12
        counts = [0] * bins
        for d in dts:
            counts[int((max(lo, min(hi - 1e-9, d)) - lo) / ((hi - lo) / bins))] += 1
        top = max(counts) or 1
        bw = r.width // bins
        for i, n in enumerate(counts):
            h = round((r.height - 2) * n / top)
            col = G.MINT if 4 <= i < 8 else G.HAZE
            if h:
                pygame.draw.rect(s, col, (r.left + i * bw, r.bottom - h, bw - 1, h))
        pygame.draw.line(s, G.DUSK, (r.left, r.bottom), (r.right, r.bottom))
        cx = r.left + r.width // 2
        pygame.draw.line(s, G.ROSE, (cx, r.top), (cx, r.bottom))


def keycap(gfx, s, label, pos):
    return G.keycap(gfx, s, label, pos, "midleft")


# ====================================================================== 먼 곳 보기
class RestScreen(Screen):
    CLOUDS = [(30, 40, 26), (150, 30, 34), (260, 50, 22), (340, 34, 28)]

    def __init__(self, ctx):
        super().__init__(ctx)
        self.finished = False
        self.t_done = None
        self.buttons = [G.Button("건너뛰기", "Esc", self._skip)]

    def _skip(self):
        if self.finished:
            self.ctx.after_rest()
        else:
            self._finish(counted=False)

    def _finish(self, counted):
        self.finished = True
        self.t_done = time.perf_counter()
        if counted:
            self.ctx.record_rest()
            self.ctx.audio.play_jingle("jingle_good")
        if self.ctx.from_prompt:
            self.buttons = [G.Button("닫기", "Enter", self.ctx.after_rest, primary=True)]
        else:
            self.buttons = [G.Button("홈으로", "Enter", self.ctx.after_rest, primary=True)]
        self.focus = 0

    def key(self, k):
        if k == pygame.K_ESCAPE:
            self._skip()
            return True
        return super().key(k)

    def update(self, now):
        if not self.finished and now - self.t_enter >= REST_SECONDS:
            self._finish(counted=True)
        if self.finished and self.ctx.from_prompt and now - self.t_done > 4.0:
            self.ctx.after_rest()

    def draw(self, s, now):
        t = now - self.t_enter
        # 창밖 풍경: 낮게 깔린 노을과 먼 산
        sky = [(250, 214, 170), (240, 180, 150), (200, 150, 160)]
        for i, c in enumerate(sky):
            pygame.draw.rect(s, c, (0, i * 40, G.BASE_W, 40))
        pygame.draw.rect(s, sky[-1], (0, 120, G.BASE_W, 96))
        pygame.draw.circle(s, (255, 236, 200), (300, 96), 16)
        for x, y, w in self.CLOUDS:
            xx = (x + t * 4) % (G.BASE_W + 60) - 30
            pygame.draw.rect(s, (255, 236, 220), (xx, y, w, 4))
            pygame.draw.rect(s, (255, 236, 220), (xx + 5, y - 3, w - 10, 3))
        layers = (((214, 160, 170), 18, 140, 30.0), ((176, 128, 150), 14, 154, 22.0), ((136, 98, 126), 10, 168, 16.0))
        for layer, (col, amp, base_y, f) in enumerate(layers):
            pts = [(0, 216)] + [(x, base_y - int(amp * abs(math.sin(x / f + layer)))) for x in range(0, G.BASE_W + 1, 6)] + [(G.BASE_W, 216)]
            pygame.draw.polygon(s, col, pts)
        # 창틀
        frame = (96, 62, 38)
        pygame.draw.rect(s, frame, (0, 0, G.BASE_W, 16))
        pygame.draw.rect(s, frame, (0, 0, 14, G.BASE_H))
        pygame.draw.rect(s, frame, (G.BASE_W - 14, 0, 14, G.BASE_H))
        pygame.draw.rect(s, frame, (0, 172, G.BASE_W, 44))
        pygame.draw.line(s, (130, 88, 56), (14, 172), (G.BASE_W - 15, 172))
        # 졸린 올빼미
        sway = round(math.sin(t * 1.2))
        self.g.blit_sprite(s, "owl_me_closed", (44 + sway, 172), scale=2)
        if self.finished:
            self.g.text(s, "잘 쉬었어요", (G.BASE_W // 2, 40), (70, 44, 60), "bold", "midtop", scale=3)
            if self.ctx.from_prompt:
                self.g.text(s, "잠시 뒤 창이 닫혀요", (G.BASE_W // 2, 88), (90, 60, 70), "small", "midtop")
        else:
            left = max(0, REST_SECONDS - t)
            self.g.text(s, "먼 곳을 바라보며 눈을 쉬어요", (G.BASE_W // 2, 26), (70, 44, 60), "bold", "midtop")
            self.g.text(s, "%d" % math.ceil(left), (G.BASE_W // 2, 46), (70, 44, 60), "bold", "midtop", scale=4)
            G.bar(s, (G.BASE_W // 2 - 60, 104, 120, 3), 1 - left / REST_SECONDS, (70, 44, 60), (226, 176, 164))
        self.button_row(s, 186)
