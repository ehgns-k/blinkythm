"""Minigame scenes. Draws only the stage area (SCENE_TOP..SCENE_BOT); no judging or timing here."""
import math
from dataclasses import dataclass, field
from typing import List

import pygame

from .. import rhythm as R
from . import gfx as G

SCENE_TOP, SCENE_BOT = 16, 168
FLASH = 0.16             # how long the other characters keep their eyes closed (s)


@dataclass
class View:
    now: float
    beat: float
    player_closed: bool
    hits: List[tuple] = field(default_factory=list)     # (time judged, Result)


def active(cues, actor, now, dur=FLASH):
    return any(c.actor == actor and 0 <= now - c.time < dur for c in cues)


def recent_hit(view, within):
    for when, res in reversed(view.hits):
        if view.now - when >= within:
            break
        if res.grade != R.MISS:
            return res
    return None


class Scene:
    popup_pos = (300, 40)
    hint = ""

    def __init__(self, gfx, stage):
        self.g = gfx
        self.stage = stage

    def phase_text(self, beat):
        return None

    def draw(self, surf, v):
        raise NotImplementedError


class LighthouseScene(Scene):
    popup_pos = (292, 92)
    STARS = G.stars(11, (0, SCENE_TOP, G.BASE_W, 86), 34)

    def phase_text(self, beat):
        from ..stages import COUNT_IN
        rel = beat - COUNT_IN
        if rel < 0:
            return None
        return "Watch the lighthouse" if rel % 8 < 4 else "Answer with the lamp"

    def draw(self, s, v):
        sea = 112
        pygame.draw.rect(s, (16, 28, 64), (0, SCENE_TOP, G.BASE_W, sea - SCENE_TOP))
        pygame.draw.rect(s, (22, 40, 84), (0, sea - 18, G.BASE_W, 18))
        G.draw_stars(s, self.STARS, v.now, (200, 204, 236), (70, 80, 130))
        pygame.draw.rect(s, (20, 56, 104), (0, sea, G.BASE_W, SCENE_BOT - sea))
        shift = int(v.beat * 6) % 24
        for row, y in enumerate(range(sea + 6, SCENE_BOT, 10)):
            d = shift if row % 2 else -shift
            for x in range(-24, G.BASE_W + 24, 24):
                pygame.draw.line(s, (44, 88, 150), (x + d, y), (x + d + 7, y))
        pygame.draw.polygon(s, (70, 74, 92), [(34, SCENE_BOT), (46, 152), (68, 146), (104, 148), (124, SCENE_BOT)])
        pygame.draw.polygon(s, (52, 56, 74), [(34, SCENE_BOT), (46, 152), (60, 160), (64, SCENE_BOT)])
        lit = active(self.stage.cues, "lighthouse", v.now, 0.2)
        lamp = (80, 104)
        if lit:
            beam = pygame.Surface((G.BASE_W, G.BASE_H), pygame.SRCALPHA)
            pygame.draw.polygon(beam, (*G.LAMP, 90), [(90, lamp[1] - 6), (90, lamp[1] + 6), (262, lamp[1] + 30), (262, lamp[1] - 26)])
            s.blit(beam, (0, 0))
        self.g.blit_sprite(s, "lighthouse_on" if lit else "lighthouse_off", (80, 154), 3)
        bob = round(1.5 * math.sin(v.beat * math.pi))
        ship = (292, 162 + bob)
        on = v.player_closed or recent_hit(v, 0.15) is not None
        if recent_hit(v, 0.22) is not None:
            beam = pygame.Surface((G.BASE_W, G.BASE_H), pygame.SRCALPHA)
            ly = ship[1] - 37
            pygame.draw.polygon(beam, (*G.LAMP, 80), [(282, ly - 4), (282, ly + 4), (160, ly + 22), (160, ly - 20)])
            s.blit(beam, (0, 0))
        self.g.blit_sprite(s, "ship_on" if on else "ship_off", ship, 3)


class OwlScene(Scene):
    popup_pos = (264, 56)
    XS = {"owl_a": 116, "owl_b": 192, "owl_me": 268}
    NAMES = {"owl_a": "1st", "owl_b": "2nd", "owl_me": "You"}
    STARS = G.stars(23, (0, SCENE_TOP, G.BASE_W, 110), 40)

    def draw(self, s, v):
        pygame.draw.rect(s, (30, 24, 64), (0, SCENE_TOP, G.BASE_W, SCENE_BOT - SCENE_TOP))
        G.draw_stars(s, self.STARS, v.now, (214, 208, 240), (80, 72, 130))
        pygame.draw.circle(s, (240, 230, 176), (330, 44), 12)
        pygame.draw.circle(s, (30, 24, 64), (336, 40), 11)
        # distant forest
        for x in range(-8, G.BASE_W, 16):
            h = 10 + (x * 7 % 9)
            pygame.draw.polygon(s, (36, 34, 78), [(x, SCENE_BOT), (x + 8, SCENE_BOT - h - 12), (x + 16, SCENE_BOT)])
        pygame.draw.rect(s, (36, 34, 78), (0, SCENE_BOT - 12, G.BASE_W, 12))
        # branch
        pygame.draw.rect(s, (90, 58, 34), (24, 137, 340, 5))
        pygame.draw.line(s, (120, 80, 48), (24, 137), (363, 137))
        pygame.draw.line(s, (90, 58, 34), (60, 137), (48, 126), 2)
        pygame.draw.line(s, (90, 58, 34), (330, 137), (344, 124), 2)
        for x, y in ((46, 124), (52, 122), (346, 122), (340, 121)):
            pygame.draw.rect(s, (60, 120, 80), (x, y, 4, 3))
        hit = recent_hit(v, 0.22)
        for actor, x in self.XS.items():
            bounce = 0
            if actor == "owl_me":
                closed = v.player_closed or recent_hit(v, 0.12) is not None
                singing = hit is not None
            else:
                closed = active(self.stage.cues, actor, v.now)
                singing = active(self.stage.cues, actor, v.now, 0.28)
            if singing:
                bounce = 1
            self.g.blit_sprite(s, "%s_%s" % (actor, "closed" if closed else "open"), (x, 138 - bounce), 3)
            if singing:
                G.music_note(s, (x + 22, 78), (240, 230, 176))
            col = G.LAMP if actor == "owl_me" else G.FOG
            self.g.text(s, self.NAMES[actor], (x, 146), col, "small", "midtop")


class PhotoScene(Scene):
    popup_pos = (318, 82)
    SHIRT = {"customer_1": (192, 48, 48), "customer_2": (48, 160, 64), "customer_3": (224, 192, 32)}

    def draw(self, s, v):
        floor = 140
        pygame.draw.rect(s, (226, 210, 178), (0, SCENE_TOP, G.BASE_W, floor - SCENE_TOP))
        for x in range(0, G.BASE_W, 24):                          # wallpaper stripes
            pygame.draw.line(s, (216, 198, 164), (x, SCENE_TOP), (x, floor - 1))
        pygame.draw.rect(s, (150, 104, 70), (0, floor, G.BASE_W, SCENE_BOT - floor))
        pygame.draw.line(s, (110, 74, 48), (0, floor), (G.BASE_W, floor))
        for x in range(0, G.BASE_W, 32):
            pygame.draw.line(s, (130, 90, 60), (x, floor + 1), (x - 10, SCENE_BOT))
        # backdrop
        pygame.draw.rect(s, (176, 202, 220), (140, 30, 112, floor - 30))
        pygame.draw.line(s, (140, 166, 190), (140, 30), (251, 30))
        pygame.draw.rect(s, (150, 176, 200), (138, 26, 116, 4))
        # desk and bell
        pygame.draw.rect(s, G.WOOD, (20, 116, 80, 5))
        pygame.draw.rect(s, (96, 62, 38), (24, 121, 4, floor - 121))
        pygame.draw.rect(s, (96, 62, 38), (92, 121, 4, floor - 121))
        ring = any(0 <= v.now - q.time < 0.15 for q in self.stage.cues)
        dx = (1 if int(v.now * 40) % 2 else -1) if ring else 0
        self.g.blit_sprite(s, "desk_bell", (60 + dx, 116))
        if ring:
            for a in (-1, 1):
                pygame.draw.line(s, (160, 120, 20), (60 + a * 14, 96), (60 + a * 18, 92))
        # customers stand in front from their bell until shortly after their photo
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
            self.g.blit_sprite(s, n.actor, (178 + 34 * k, floor - 1), 3)
        # camera
        self.g.blit_sprite(s, "camera_shut" if v.player_closed else "camera_open", (322, 164), 3)
        # photos taken
        x = 110
        for when, res in v.hits[-7:]:
            col = G.GRADE_COLOR[res.grade]
            pygame.draw.rect(s, (250, 248, 240), (x, 146, 12, 15))
            pygame.draw.rect(s, col, (x, 146, 12, 15), 1)
            if res.grade == R.MISS:
                pygame.draw.rect(s, (200, 200, 200), (x + 2, 148, 8, 8))
            else:
                pygame.draw.rect(s, (176, 202, 220), (x + 2, 148, 8, 8))
                pygame.draw.rect(s, self.SHIRT.get(res.note.actor, G.HAZE), (x + 4, 152, 4, 4))
                pygame.draw.rect(s, (240, 200, 160), (x + 5, 149, 2, 3))
            x += 15
        if recent_hit(v, 0.09) is not None:
            G.alpha_fill(s, (0, SCENE_TOP, G.BASE_W, SCENE_BOT - SCENE_TOP), (255, 255, 255), 170)


SCENES = {"lighthouse": LighthouseScene, "owls": OwlScene, "photo": PhotoScene}


def make_scene(gfx, stage):
    return SCENES[stage.key](gfx, stage)
