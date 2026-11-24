"""미니게임 장면 그리기. 그림은 assets/sprites의 PNG를 정수배로 확대해 쓴다.

장면은 매 프레임 캔버스 위쪽 무대 영역(SCENE_TOP~SCENE_BOT)을 다시 그린다.
판정과 박자 계산은 하지 않고, GameWindow가 넘겨 주는 상태(View)만 보고 그린다.
"""
import math
import os
import tkinter as tk
from dataclasses import dataclass, field
from typing import List

from . import rhythm as R
from .audio import assets_dir

STAGE_W = 640
SCENE_TOP, SCENE_BOT = 27, 228
FLASH = 0.16             # 상대가 눈을 감고 있는 시간(초)
STARS = [(34, 48), (96, 70), (150, 40), (232, 58), (290, 88), (348, 44), (402, 76), (452, 52),
         (520, 92), (600, 50), (612, 112), (72, 118), (188, 104), (380, 116)]


class Sprites:
    """PNG를 읽어 확대한 PhotoImage를 보관한다(참조를 잃으면 그림이 사라지므로)."""

    def __init__(self, master):
        self.master = master
        self.folder = os.path.join(assets_dir(), "sprites")
        self._cache = {}

    def get(self, name, scale):
        key = (name, scale)
        if key not in self._cache:
            try:
                img = tk.PhotoImage(master=self.master, file=os.path.join(self.folder, name + ".png"))
                self._cache[key] = img.zoom(scale) if scale > 1 else img
            except tk.TclError:
                self._cache[key] = None
        return self._cache[key]


@dataclass
class View:
    now: float
    beat: float
    player_closed: bool
    hits: List[tuple] = field(default_factory=list)     # (판정 시각, Result)


def active(cues, actor, now, dur=FLASH):
    return any(c.actor == actor and 0 <= now - c.time < dur for c in cues)


def recent_hit(view, within):
    for when, res in reversed(view.hits):
        if view.now - when < within:
            if res.grade != R.MISS:
                return res
        else:
            break
    return None


class Scene:
    popup_pos = (480, 56)

    def __init__(self, sprites, stage):
        self.sp = sprites
        self.stage = stage

    def image(self, c, name, scale, x, y, anchor="s"):
        img = self.sp.get(name, scale)
        if img is not None:
            c.create_image(x, y, image=img, anchor=anchor)
        else:                              # 그림 파일이 없을 때도 게임은 진행되게
            c.create_rectangle(x - 20, y - 40, x + 20, y, outline="#000000")
            c.create_text(x, y - 20, text=name[:6], font=("TkDefaultFont", 7))

    def phase_text(self, beat):
        return None

    def draw(self, c, view):
        raise NotImplementedError


class LighthouseScene(Scene):
    popup_pos = (480, 52)

    def phase_text(self, beat):
        from .stages import COUNT_IN
        rel = beat - COUNT_IN
        if rel < 0:
            return None
        return "등대 신호 보기" if rel % 8 < 4 else "배의 등불로 답하기"

    def draw(self, c, v):
        sky_bot = 162
        c.create_rectangle(0, SCENE_TOP, STAGE_W, sky_bot, fill="#0B1F4A", outline="")
        for x, y in STARS:
            if y < sky_bot - 10:
                c.create_rectangle(x, y, x + 2, y + 2, fill="#D0D0F0", outline="")
        c.create_rectangle(0, sky_bot, STAGE_W, SCENE_BOT, fill="#123A6E", outline="")
        shift = (v.beat * 10) % 40
        for row, y in enumerate(range(sky_bot + 10, SCENE_BOT, 16)):
            for x in range(-40, STAGE_W, 40):
                x0 = x + (shift if row % 2 else -shift)
                c.create_line(x0, y, x0 + 18, y, fill="#2A5A9A", width=2)
        # 바위와 등대
        c.create_polygon(50, SCENE_BOT, 70, 196, 150, 190, 176, SCENE_BOT, fill="#505860", outline="")
        lit = active(self.stage.cues, "lighthouse", v.now, 0.2)
        lamp_y = 196 - 88 + 20
        if lit:
            c.create_polygon(126, lamp_y - 8, 126, lamp_y + 8, 430, lamp_y + 46, 430, lamp_y - 40,
                             fill="#FFE680", outline="", stipple="gray50")
        self.image(c, "lighthouse_on" if lit else "lighthouse_off", 4, 112, 196)
        # 배: 박자에 맞춰 살짝 흔들림
        bob = round(2 * math.sin(v.beat * math.pi))
        sx, sb = 480, 206 + bob
        on = v.player_closed or recent_hit(v, 0.15) is not None
        if recent_hit(v, 0.2) is not None:
            ly = sb - 56 + 6
            c.create_polygon(472, ly - 5, 472, ly + 5, 300, ly + 30, 300, ly - 26,
                             fill="#FFE680", outline="", stipple="gray50")
        self.image(c, "ship_on" if on else "ship_off", 4, sx, sb)


class OwlScene(Scene):
    popup_pos = (440, 52)
    XS = {"owl_a": 200, "owl_b": 320, "owl_me": 440}

    def draw(self, c, v):
        c.create_rectangle(0, SCENE_TOP, STAGE_W, SCENE_BOT, fill="#1A1446", outline="")
        for x, y in STARS:
            c.create_rectangle(x, y, x + 2, y + 2, fill="#C8C8E8", outline="")
        c.create_oval(546, 48, 594, 96, fill="#F0E6B0", outline="")
        c.create_oval(560, 48, 606, 92, fill="#1A1446", outline="")        # 초승달
        c.create_rectangle(40, 186, 610, 196, fill="#5A3A1A", outline="")
        c.create_line(110, 186, 90, 170, fill="#5A3A1A", width=4)
        c.create_line(540, 186, 566, 166, fill="#5A3A1A", width=4)
        for x, y in ((86, 166), (570, 162), (96, 174)):
            c.create_oval(x - 6, y - 4, x + 6, y + 4, fill="#2E6A30", outline="")
        names = {"owl_a": "첫째", "owl_b": "둘째", "owl_me": "나"}
        hit = recent_hit(v, 0.2)
        for actor, x in self.XS.items():
            if actor == "owl_me":
                closed = v.player_closed or recent_hit(v, 0.12) is not None
                singing = hit is not None
            else:
                closed = active(self.stage.cues, actor, v.now)
                singing = active(self.stage.cues, actor, v.now, 0.25)
            self.image(c, "%s_%s" % (actor, "closed" if closed else "open"), 4, x, 188)
            if singing:
                c.create_text(x + 30, 104, text="♪", font=("TkDefaultFont", 14, "bold"), fill="#F0E6B0")
            c.create_text(x, 212, text=names[actor], fill="#C8C8E8", font=("TkDefaultFont", 9))


class PhotoScene(Scene):
    popup_pos = (520, 52)
    SHIRT = {"customer_1": "#C03030", "customer_2": "#30A040", "customer_3": "#E0C020"}

    def draw(self, c, v):
        floor = 196
        c.create_rectangle(0, SCENE_TOP, STAGE_W, floor, fill="#E8DCC0", outline="")
        c.create_rectangle(0, floor, STAGE_W, SCENE_BOT, fill="#A07850", outline="")
        c.create_line(0, floor, STAGE_W, floor, fill="#6A4A30")
        c.create_rectangle(196, 44, 356, floor, fill="#B8D0E0", outline="#8090A0")
        # 책상과 호출 종
        c.create_rectangle(40, 166, 150, 172, fill="#7A5030", outline="")
        c.create_rectangle(48, 172, 54, floor, fill="#7A5030", outline="")
        c.create_rectangle(136, 172, 142, floor, fill="#7A5030", outline="")
        ring = any(0 <= v.now - q.time < 0.15 for q in self.stage.cues)
        dx = round(2 * math.sin(v.now * 90)) if ring else 0
        self.image(c, "desk_bell", 3, 95 + dx, 166)
        if ring:
            c.create_text(95, 128, text="딩", font=("TkDefaultFont", 10, "bold"), fill="#806000")
        # 손님: 종을 친 뒤부터 사진을 찍고 잠시 뒤까지 앞에 서 있다
        judged = {res.note.idx: when for when, res in v.hits}
        waiting = []
        for n in self.stage.notes:
            cue_t = n.time - (n.beat - n.reveal) * self.stage.beat_sec
            if v.now < cue_t:
                continue
            done = judged.get(n.idx)
            if done is not None and v.now - done > 0.35:
                continue
            if done is None and v.now > n.time + 0.6:
                continue
            waiting.append(n)
        for k, n in reversed(list(enumerate(waiting[:3]))):
            self.image(c, n.actor, 4, 276 + 46 * k, floor - 2)
        # 카메라(눈을 감으면 셔터가 닫힘)
        self.image(c, "camera_shut" if v.player_closed else "camera_open", 4, 530, floor + 22)
        # 찍은 사진 줄
        x = 172
        for when, res in v.hits[-6:]:
            col = {"perfect": "#000080", "good": "#008000", "ok": "#808000", "miss": "#800000"}[res.grade]
            c.create_rectangle(x, 202, x + 22, 225, fill="#FFFFFF", outline=col, width=2)
            if res.grade == R.MISS:
                c.create_line(x + 5, 206, x + 17, 216, fill=col)
                c.create_line(x + 17, 206, x + 5, 216, fill=col)
            else:
                c.create_rectangle(x + 4, 205, x + 18, 217, fill=self.SHIRT.get(res.note.actor, "#B8D0E0"), outline="")
            x += 26
        if recent_hit(v, 0.09) is not None:
            c.create_rectangle(0, SCENE_TOP, STAGE_W, SCENE_BOT, fill="#FFFFFF", outline="", stipple="gray50")


SCENES = {"lighthouse": LighthouseScene, "owls": OwlScene, "photo": PhotoScene}


def make_scene(sprites, stage):
    return SCENES[stage.key](sprites, stage)
