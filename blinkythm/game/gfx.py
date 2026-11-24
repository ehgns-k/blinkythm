"""Drawing base: everything is drawn on a 384x216 pixel screen, then scaled by a whole number to fit the window.

Text uses a bitmap font (Galmuri) on the same pixel screen, so art and text share one grid.
On high-DPI monitors only the scale changes; the picture stays the same.
"""
import math
import os

import pygame

from ..audio import assets_dir

BASE_W, BASE_H = 384, 216

# Palette: a village at night. Names describe the colour, not its use.
INK = (27, 24, 43)
NIGHT = (39, 37, 74)
DUSK = (61, 57, 112)
HAZE = (107, 104, 164)
FOG = (168, 166, 206)
CREAM = (246, 236, 210)
PAPER = (232, 220, 192)
LAMP = (255, 205, 96)
PEACH = (240, 150, 110)
MINT = (130, 210, 170)
ROSE = (226, 110, 120)
WOOD = (122, 80, 48)

GRADE_COLOR = {"perfect": LAMP, "good": MINT, "ok": PEACH, "miss": FOG}

FONT_FILES = {
    "small": ("Galmuri9.ttf", 12),       # (file, line height)
    "body": ("Galmuri11.ttf", 16),
    "bold": ("Galmuri11-Bold.ttf", 16),
    "title": ("Galmuri14.ttf", 21),
}


def fit_scale(w, h):
    return max(1, min(w // BASE_W, h // BASE_H))


def initial_window_size(desktop_w, desktop_h, share=0.8):
    s = max(1, min(int(desktop_w * share) // BASE_W, int(desktop_h * share) // BASE_H))
    return BASE_W * s, BASE_H * s


class Presenter:
    """Scales the base screen into the window, centred, and maps window <-> base coordinates."""

    def __init__(self):
        self.scale = 1
        self.offset = (0, 0)

    def present(self, window, base):
        w, h = window.get_size()
        s = fit_scale(w, h)
        self.scale = s
        ox, oy = (w - BASE_W * s) // 2, (h - BASE_H * s) // 2
        self.offset = (ox, oy)
        window.fill(INK)
        window.blit(pygame.transform.scale(base, (BASE_W * s, BASE_H * s)), (ox, oy))

    def to_base(self, pos):
        x, y = pos
        return (x - self.offset[0]) // self.scale, (y - self.offset[1]) // self.scale


class Gfx:
    def __init__(self):
        root = assets_dir()
        self._font_dir = os.path.join(root, "fonts")
        self._sprite_dir = os.path.join(root, "sprites")
        self._fonts = {}
        self._sprites = {}

    # ------------------------------------------------------------------ text
    def font(self, name):
        if name not in self._fonts:
            fn, _ = FONT_FILES[name]
            try:
                self._fonts[name] = pygame.font.Font(os.path.join(self._font_dir, fn), 12)
            except (OSError, pygame.error):
                self._fonts[name] = pygame.font.Font(None, FONT_FILES[name][1])
        return self._fonts[name]

    def line_height(self, name):
        return FONT_FILES[name][1]

    def render(self, text, color, font="body", scale=1):
        img = self.font(font).render(text, False, color)
        if scale > 1:
            img = pygame.transform.scale_by(img, scale)
        return img

    def text(self, surf, text, pos, color=CREAM, font="body", anchor="topleft", shadow=None, scale=1):
        img = self.render(text, color, font, scale)
        r = img.get_rect(**{anchor: pos})
        if shadow is not None:
            surf.blit(self.render(text, shadow, font, scale), r.move(0, scale))
        surf.blit(img, r)
        return r

    def width(self, text, font="body"):
        return self.font(font).size(text)[0]

    def wrap(self, text, width, font="small"):
        """Break at spaces; break inside a word only when the word alone is too long."""
        lines, cur = [], ""
        for word in text.split(" "):
            cand = word if not cur else cur + " " + word
            if self.width(cand, font) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            for ch in word:
                if self.width(cur + ch, font) > width and cur:
                    lines.append(cur)
                    cur = ""
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    # ------------------------------------------------------------------ sprites
    def sprite(self, name, scale=2):
        key = (name, scale)
        if key not in self._sprites:
            try:
                img = pygame.image.load(os.path.join(self._sprite_dir, name + ".png"))
                try:
                    img = img.convert_alpha()
                except pygame.error:            # no window yet; the plain image works too
                    pass
                self._sprites[key] = pygame.transform.scale_by(img, scale) if scale > 1 else img
            except (OSError, pygame.error, FileNotFoundError):
                img = pygame.Surface((8 * scale, 8 * scale), pygame.SRCALPHA)
                img.fill(ROSE)
                self._sprites[key] = img
        return self._sprites[key]

    def blit_sprite(self, surf, name, midbottom, scale=2):
        img = self.sprite(name, scale)
        surf.blit(img, img.get_rect(midbottom=(round(midbottom[0]), round(midbottom[1]))))


# ---------------------------------------------------------------------- shapes
def panel(surf, rect, fill=NIGHT, edge=DUSK, light=None):
    """Box with a 1 px border and empty corner pixels. With light, draws a highlight under the top edge."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, edge, r.inflate(0, -2))
    pygame.draw.rect(surf, edge, r.inflate(-2, 0))
    pygame.draw.rect(surf, fill, r.inflate(-2, -2))
    if light is not None:
        pygame.draw.line(surf, light, (r.left + 2, r.top + 1), (r.right - 3, r.top + 1))
    return r


def keycap(gfx, surf, label, pos, anchor="midleft", fg=INK, bg=FOG):
    """Keyboard shortcut hint: a small key drawn around the label."""
    img = gfx.render(label, fg, "small")
    w = img.get_width() + 6
    r = pygame.Rect(0, 0, w, 12)
    setattr(r, anchor, pos)
    pygame.draw.rect(surf, bg, r.inflate(0, -2))
    pygame.draw.rect(surf, bg, r.inflate(-2, 0))
    pygame.draw.line(surf, HAZE, (r.left + 1, r.bottom - 1), (r.right - 2, r.bottom - 1))
    surf.blit(img, (r.left + 3, r.top - 1))
    return r


class Button:
    def __init__(self, label, key_label, action, primary=False, enabled=True):
        self.label = label
        self.key_label = key_label
        self.action = action
        self.primary = primary
        self.enabled = enabled
        self.rect = pygame.Rect(0, 0, 0, 0)

    def press(self):
        if self.enabled:
            self.action()
            return True
        return False

    def draw_plain(self, gfx, surf, rect, focused):
        """Button without a key hint (for mouse-only places such as the reminder popup)."""
        self.rect = pygame.Rect(rect)
        r = self.rect
        if not self.enabled:
            fill, edge, fg = NIGHT, DUSK, HAZE
        elif focused:
            fill, edge, fg = LAMP, INK, INK
        elif self.primary:
            fill, edge, fg = CREAM, INK, INK
        else:
            fill, edge, fg = NIGHT, DUSK, CREAM
        panel(surf, r, fill, edge)
        gfx.text(surf, self.label, (r.centerx, r.centery - 1), fg, "bold", "center")

    def measure(self, gfx):
        return gfx.width(self.label, "bold") + gfx.width(self.key_label, "small") + 22

    def draw(self, gfx, surf, rect, focused):
        self.rect = pygame.Rect(rect)
        lift = 0 if focused else 1
        r = self.rect.move(0, lift)
        if not self.enabled:
            panel(surf, r, NIGHT, DUSK)
            gfx.text(surf, self.label, (r.left + 6, r.centery - 1), HAZE, "bold", "midleft")
            keycap(gfx, surf, self.key_label, (r.right - 5, r.centery), "midright", fg=NIGHT, bg=DUSK)
            return
        if self.primary or focused:
            fill, edge, fg = (LAMP, INK, INK) if focused else (CREAM, INK, INK)
        else:
            fill, edge, fg = NIGHT, DUSK, CREAM
        if focused:
            pygame.draw.line(surf, INK, (r.left + 1, r.bottom), (r.right - 2, r.bottom))
        panel(surf, r, fill, edge)
        gfx.text(surf, self.label, (r.left + 6, r.centery - 1), fg, "bold", "midleft")
        keycap(gfx, surf, self.key_label, (r.right - 5, r.centery), "midright",
               fg=INK if fill != NIGHT else NIGHT, bg=FOG if fill == NIGHT else PAPER)


def layout_buttons(gfx, buttons, right, y, gap=4, h=18):
    """Rectangles for buttons laid out in a row, aligned to the right edge."""
    rects = []
    x = right
    for b in reversed(buttons):
        w = b.measure(gfx)
        rects.append(pygame.Rect(x - w, y, w, h))
        x -= w + gap
    return list(reversed(rects))


def bar(surf, rect, frac, color, back=DUSK):
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, back, r)
    w = round(r.width * max(0.0, min(1.0, frac)))
    if w:
        pygame.draw.rect(surf, color, (r.left, r.top, w, r.height))


def eye_icon(surf, center, closed, color=CREAM, pupil=INK):
    """11x7 eye. Closed is a line curving down."""
    x, y = center
    if closed:
        pts = [(x - 5, y), (x - 3, y + 2), (x + 3, y + 2), (x + 5, y)]
        pygame.draw.lines(surf, color, False, pts)
        return
    pygame.draw.polygon(surf, color, [(x - 5, y), (x - 2, y - 3), (x + 2, y - 3), (x + 5, y),
                                      (x + 2, y + 3), (x - 2, y + 3)])
    pygame.draw.rect(surf, pupil, (x - 1, y - 2, 3, 5))


def music_note(surf, pos, color):
    x, y = pos
    pygame.draw.rect(surf, color, (x, y + 4, 3, 2))
    pygame.draw.line(surf, color, (x + 2, y), (x + 2, y + 4))
    pygame.draw.line(surf, color, (x + 3, y), (x + 4, y + 1))


def ease_out_back(t):
    t = max(0.0, min(1.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def beat_pulse(beat):
    """Drops quickly from 1 to 0 after each beat. Used for small hops on the beat."""
    if beat < 0:
        return 0.0
    return math.exp(-(beat % 1.0) * 6)


def stars(seed, area, n):
    """Fixed star positions. The same seed gives the same sky."""
    import random
    rnd = random.Random(seed)
    x0, y0, w, h = area
    return [(x0 + rnd.randrange(w), y0 + rnd.randrange(h), rnd.random()) for _ in range(n)]


def draw_stars(surf, pts, t, color=FOG, dim=HAZE):
    for x, y, ph in pts:
        on = math.sin(t * 1.3 + ph * 6.28) > -0.3
        surf.set_at((x, y), color if on else dim)


def alpha_fill(surf, rect, color, alpha):
    s = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
    s.fill((*color, alpha))
    surf.blit(s, pygame.Rect(rect).topleft)


def toggle(surf, pos, on, focused=False):
    """Pixel on/off switch, 17x9, anchored at its right edge."""
    x, y = pos
    r = pygame.Rect(x - 17, y, 17, 9)
    pygame.draw.rect(surf, MINT if on else DUSK, r.inflate(0, -2))
    pygame.draw.rect(surf, MINT if on else DUSK, r.inflate(-2, 0))
    knob = pygame.Rect(0, 0, 7, 7)
    knob.midleft = (r.left + 1, r.centery) if not on else (r.right - 8, r.centery)
    pygame.draw.rect(surf, CREAM if focused else PAPER, knob)
    return r


def arrow(surf, center, direction, color):
    """Small 3x5 arrow pointing left (-1) or right (1)."""
    x, y = center
    for i in range(3):
        xx = x + i * direction
        pygame.draw.line(surf, color, (xx, y - (2 - i)), (xx, y + (2 - i)))
