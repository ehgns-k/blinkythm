"""게임 애셋(픽셀 그림 PNG, 효과음/반주 WAV)을 코드로 만든다.

    python tools/make_assets.py

결과는 assets/sprites/*.png, assets/sounds/*.wav에 저장되며 저장소에 함께 올린다.
같은 코드로 다시 만들면 같은 파일이 나온다(난수 시드 고정).
그림은 원래 크기(1배)로 저장하고, 게임에서 정수배로 확대해 쓴다.
"""
import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITE_DIR = os.path.join(ROOT, "assets", "sprites")
SOUND_DIR = os.path.join(ROOT, "assets", "sounds")
SR = 44100

# =========================================================================== 그림
# 글자 하나가 픽셀 하나. '.'은 투명. 글자 -> 색은 팔레트로 정한다.

OWL_OPEN = [
    "..k..........k..",
    ".kbk........kbk.",
    ".kbbkkkkkkkkbbk.",
    ".kbbbbbbbbbbbbk.",
    "kbbwwwwbbwwwwbbk",
    "kbwwwwwwwwwwwwbk",
    "kbwwppwwwwppwwbk",
    "kbwwppwwwwppwwbk",
    "kbbwwwwyywwwwbbk",
    "kbbbbbbyybbbbbbk",
    "kbbllllllllllbbk",
    "kbllllllllllllbk",
    "kbllbllllllbllbk",
    "kblllllbblllllbk",
    "kbllllllllllllbk",
    ".kbllllllllllbk.",
    "..kkkkkkkkkkkk..",
    "....ff....ff....",
]
OWL_CLOSED = OWL_OPEN[:4] + [
    "kbbbbbbbbbbbbbbk",
    "kbbbbbbbbbbbbbbk",
    "kbkkkkbbbbkkkkbk",
    "kbbbbbbbbbbbbbbk",
] + OWL_OPEN[8:]

OWL_PALETTES = {
    "owl_a": {"k": "#2B1D14", "b": "#8B5A2B", "l": "#D9B48A", "w": "#FFFFFF", "p": "#000000", "y": "#E0A020", "f": "#E07020"},
    "owl_b": {"k": "#202020", "b": "#707070", "l": "#C8C8C8", "w": "#FFFFFF", "p": "#000000", "y": "#E0A020", "f": "#E07020"},
    "owl_me": {"k": "#101030", "b": "#3050A0", "l": "#A8C0E8", "w": "#FFFFFF", "p": "#000000", "y": "#F0C030", "f": "#E07020"},
}

LIGHTHOUSE = [
    "......kkkk......",
    ".....kRRRRk.....",
    "....kRRRRRRk....",
    "....kkkkkkkk....",
    "....kLLLLLLk....",
    "....kLLLLLLk....",
    "....kLLLLLLk....",
    "...kkkkkkkkkk...",
    "....kwwwwwwk....",
    "....kwwwwwwk....",
    "....kRRRRRRk....",
    "....kRRRRRRk....",
    "...kwwwwwwwwk...",
    "...kwwwwwwwwk...",
    "...kRRRRRRRRk...",
    "...kRRRRRRRRk...",
    "..kwwwwwwwwwwk..",
    "..kwwwwkkwwwwk..",
    "..kRRRRkkRRRRk..",
    "..kRRRRkkRRRRk..",
    ".kssssssssssssk.",
    "kssssssssssssssk",
]
LIGHTHOUSE_PAL = {"k": "#000000", "R": "#B02020", "w": "#F4F4F4", "s": "#707070"}

SHIP = [
    "..........kk............",
    ".........kLLk...........",
    ".........kLLk...........",
    "..........kk............",
    "...........k............",
    "........kkkkkkk.........",
    "........kwwwwwk.........",
    "........kwnwnwk.........",
    "........kwwwwwk.........",
    "..kkkkkkkkkkkkkkkkkkkkk.",
    "..kRRRRRRRRRRRRRRRRRRRk.",
    "...kRRRRRRRRRRRRRRRRRk..",
    "....kHHHHHHHHHHHHHHHk...",
    ".....kkkkkkkkkkkkkkk....",
]
SHIP_PAL = {"k": "#000000", "w": "#F4F4F4", "n": "#203060", "R": "#2050A0", "H": "#183870"}

CAMERA_OPEN = [
    "...kkkk.........",
    "..kssssk........",
    "kkkkkkkkkkkkkkkk",
    "kddddddddddddddk",
    "kddddkkkkkkddddk",
    "kdddknnnnnnkdddk",
    "kddknnwwnnnnkddk",
    "kddknnwnnnnnkddk",
    "kddknnnnnnnnkddk",
    "kddknnnnnnnnkddk",
    "kdddknnnnnnkdddk",
    "kddddkkkkkkddddk",
    "kddddddddddddddk",
    "kkkkkkkkkkkkkkkk",
    ".......kk.......",
    "......k..k......",
    ".....k....k.....",
    "....k......k....",
]
CAMERA_SHUT = CAMERA_OPEN[:5] + [
    "kdddkhhhhhhkdddk",
    "kddkhhhhhhhhkddk",
    "kddkhhhhhhhhkddk",
    "kddkkkkkkkkkkddk",
    "kddkhhhhhhhhkddk",
    "kdddkhhhhhhkdddk",
] + CAMERA_OPEN[11:]
CAMERA_PAL = {"k": "#000000", "s": "#C0C0C0", "d": "#404040", "n": "#102060", "w": "#FFFFFF", "h": "#909090"}

CUSTOMER = [
    "...hhhhhh...",
    "..hhhhhhhh..",
    "..hssssssh..",
    "..skssskss..",
    "..ssssssss..",
    "...smmmms...",
    "....ssss....",
    "..cccccccc..",
    ".cccccccccc.",
    "cccccccccccc",
    "sccccccccccs",
    "sccccccccccs",
    ".cccccccccc.",
    "..pppppppp..",
    "..ppp..ppp..",
    "..ppp..ppp..",
    "..ppp..ppp..",
    "..kkk..kkk..",
]
CUSTOMER_PALETTES = {
    "customer_1": {"h": "#3A2410", "s": "#F0C8A0", "k": "#000000", "m": "#B04040", "c": "#C03030", "p": "#303060"},
    "customer_2": {"h": "#101010", "s": "#E0B088", "k": "#000000", "m": "#B04040", "c": "#30A040", "p": "#504030"},
    "customer_3": {"h": "#C09020", "s": "#F4D0B0", "k": "#000000", "m": "#B04040", "c": "#E0C020", "p": "#303030"},
}

DESK_BELL = [
    "......kk......",
    ".....kyyk.....",
    "...kkyyyykk...",
    "..kyyyyyyyyk..",
    ".kyywyyyyyyyk.",
    ".kyyyyyyyyyyk.",
    "kkkkkkkkkkkkkk",
    "kggggggggggggk",
    "kkkkkkkkkkkkkk",
]
DESK_BELL_PAL = {"k": "#000000", "y": "#D8B030", "w": "#FFF0A0", "g": "#606060"}


def sprite_image(rows, palette):
    from PIL import Image
    w = len(rows[0])
    assert all(len(r) == w for r in rows), "행 길이가 다릅니다"
    img = Image.new("RGBA", (w, len(rows)), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                c = palette[ch]
                px[x, y] = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 255)
    return img


def sprites():
    out = {}
    for name, pal in OWL_PALETTES.items():
        out[name + "_open"] = (OWL_OPEN, pal)
        out[name + "_closed"] = (OWL_CLOSED, pal)
    out["lighthouse_on"] = (LIGHTHOUSE, dict(LIGHTHOUSE_PAL, L="#FFE060"))
    out["lighthouse_off"] = (LIGHTHOUSE, dict(LIGHTHOUSE_PAL, L="#404858"))
    out["ship_on"] = (SHIP, dict(SHIP_PAL, L="#FFE060"))
    out["ship_off"] = (SHIP, dict(SHIP_PAL, L="#404858"))
    out["camera_open"] = (CAMERA_OPEN, CAMERA_PAL)
    out["camera_shut"] = (CAMERA_SHUT, CAMERA_PAL)
    for name, pal in CUSTOMER_PALETTES.items():
        out[name] = (CUSTOMER, pal)
    out["desk_bell"] = (DESK_BELL, DESK_BELL_PAL)
    return out


# =========================================================================== 소리
def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def env(n, attack=0.002, decay=8.0):
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def lowpass(x, cutoff):
    """1차 저역 통과. 짧은 소리에만 쓰므로 단순 반복문으로 충분하다."""
    a = 1.0 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


def norm(x, peak):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# --- 타악기 ------------------------------------------------------------------
def kick():
    t = t_axis(0.32)
    f = 45 + 80 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * env(len(t), 0.001, 11)
    y[:60] += np.linspace(0.6, 0, 60)          # 때리는 소리
    return norm(y, 0.9)


def snare(rng):
    n = int(SR * 0.2)
    nz = highpass(rng.standard_normal(n), 1200) * env(n, 0.001, 22)
    tone = np.sin(2 * np.pi * 190 * t_axis(0.2)) * env(n, 0.001, 35)
    return norm(nz * 0.7 + tone * 0.5, 0.8)


def hat(rng):
    n = int(SR * 0.06)
    return norm(highpass(rng.standard_normal(n), 6000) * env(n, 0.0005, 70), 0.5)


def rim():
    t = t_axis(0.05)
    y = (np.sin(2 * np.pi * 1700 * t) + 0.5 * np.sin(2 * np.pi * 2900 * t)) * env(len(t), 0.0005, 90)
    return norm(y, 0.6)


def woodblock(freq):
    t = t_axis(0.08)
    y = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2.76 * t)) * env(len(t), 0.0008, 55)
    return norm(y, 0.8)


# --- 음정 악기 ---------------------------------------------------------------
def bass(note, dur):
    t = t_axis(dur)
    f = midi(note)
    y = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 7))
    y = lowpass(y * env(len(t), 0.004, 2.5), 900)
    rel = min(len(y), int(SR * 0.03))
    y[-rel:] *= np.linspace(1, 0, rel)
    return y


def pluck(note, dur=0.5, bright=1.0):
    t = t_axis(dur)
    f = midi(note)
    y = sum(np.sin(2 * np.pi * f * k * t) * np.exp(-t * (4 + 3 * k)) * bright ** (k - 1) / k for k in range(1, 6))
    return y * env(len(t), 0.002, 1.0)


def pad(notes, dur):
    t = t_axis(dur)
    y = sum(np.sin(2 * np.pi * midi(n) * t) + 0.3 * np.sin(2 * np.pi * midi(n) * 2 * t) for n in notes)
    a = np.minimum(1.0, t / 0.25)
    r = np.minimum(1.0, (dur - t) / 0.3)
    return y * a * np.clip(r, 0, 1) / len(notes)


def bell(freq, dur=0.6, decay=6.0):
    t = t_axis(dur)
    parts = [(1.0, 1.0), (2.76, 0.5), (5.4, 0.25), (8.93, 0.12)]
    y = sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * decay * (1 + r * 0.4)) for r, a in parts)
    return y * env(len(t), 0.0008, 0.0)


def hoot(note, dur=0.28):
    t = t_axis(dur)
    f = midi(note) * (1 + 0.012 * np.sin(2 * np.pi * 7 * t)) * (1 - 0.06 * t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + 0.25 * np.sin(2 * ph)
    a = np.minimum(1.0, t / 0.008)
    return y * a * np.exp(-t * 7)


def horn(note, dur=0.32):
    t = t_axis(dur)
    f = midi(note)
    y = sum(np.sin(2 * np.pi * f * k * t) / k ** 0.8 for k in range(1, 9))
    y = lowpass(y, 1400)
    a = np.minimum(1.0, t / 0.006)
    return y * a * np.exp(-t * 5)


def shutter(rng):
    n = int(SR * 0.12)
    y = np.zeros(n)
    for at, g in ((0, 1.0), (int(SR * 0.045), 0.6)):
        m = int(SR * 0.025)
        burst = highpass(rng.standard_normal(m), 2500) * env(m, 0.0003, 160) * g
        y[at:at + m] += burst
    return y


def dull():
    t = t_axis(0.12)
    y = np.sin(2 * np.pi * 110 * t) * env(len(t), 0.002, 30) + 0.3 * np.sin(2 * np.pi * 70 * t) * env(len(t), 0.002, 20)
    return y


def mix_at(buf, y, sec, gain=1.0):
    i = int(round(sec * SR))
    j = min(len(buf), i + len(y))
    if i < len(buf):
        buf[i:j] += y[: j - i] * gain


def jingle(notes, step, tail=0.6):
    buf = np.zeros(int(SR * (step * len(notes) + tail)))
    for k, n in enumerate(notes):
        if isinstance(n, tuple):
            for m in n:
                mix_at(buf, pluck(m, 0.8), k * step, 0.5)
        else:
            mix_at(buf, pluck(n, 0.5), k * step)
    return buf


# --- 반주 루프(2마디 = 8박) -----------------------------------------------------
def loop_buffer(bpm):
    beat = 60.0 / bpm
    return np.zeros(int(round(8 * beat * SR))), beat


def wrap_mix(buf, y, sec, gain=1.0):
    """루프 끝을 넘는 꼬리는 앞쪽으로 감아 넣어 이음매가 끊기지 않게 한다."""
    i = int(round(sec * SR)) % len(buf)
    y = y * gain
    while len(y):
        j = min(len(buf), i + len(y))
        buf[i:j] += y[: j - i]
        y = y[j - i:]
        i = 0


def loop_lighthouse(rng):
    buf, b = loop_buffer(92)
    k, s, h = kick(), snare(rng), hat(rng)
    for x in (0, 2, 4, 6):
        wrap_mix(buf, k, x * b, 0.55)
    for x in (1, 3, 5, 7):
        wrap_mix(buf, s, x * b, 0.22)
    for x in range(16):
        wrap_mix(buf, h, x * b / 2, 0.18 if x % 2 else 0.1)
    # D단조 | 내림B장조 - C장조
    for at, n, d in ((0, 38, 1.4), (1.5, 38, 0.45), (2, 45, 0.9), (3, 41, 0.9),
                     (4, 34, 1.9), (6, 36, 1.4), (7.5, 36, 0.45)):
        wrap_mix(buf, bass(n, d * b), at * b, 0.5)
    wrap_mix(buf, pad([62, 65, 69], 4 * b), 0, 0.18)
    wrap_mix(buf, pad([58, 62, 65], 2 * b), 4 * b, 0.18)
    wrap_mix(buf, pad([60, 64, 67], 2 * b), 6 * b, 0.18)
    # 파도 소리: 낮은 잡음이 한 루프에 한 번 밀려왔다 빠진다
    n = len(buf)
    sw = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)
    buf += lowpass(rng.standard_normal(n), 500) * sw * 0.35
    return norm(buf, 0.32)


def loop_owls(rng):
    buf, b = loop_buffer(100)
    k, h, r = kick(), hat(rng), rim()
    for x in (0, 2.5, 4, 6.5):
        wrap_mix(buf, k, x * b, 0.45)
    for x in (1, 3, 5, 7):
        wrap_mix(buf, r, x * b, 0.25)
    for x in range(8):                         # 셋잇단 느낌으로 민 뒷박
        wrap_mix(buf, h, x * b, 0.12)
        wrap_mix(buf, h, (x + 2 / 3) * b, 0.08)
    # A단조 | F장조 - G장조
    for at, n, d in ((0, 45, 3.8), (4, 41, 1.9), (6, 43, 1.9)):
        wrap_mix(buf, bass(n, d * b), at * b, 0.45)
    arp = [69, 72, 76, 72, 69, 72, 76, 79, 65, 69, 72, 69, 67, 71, 74, 71]
    for x, n in enumerate(arp):
        wrap_mix(buf, pluck(n + 12, 0.4, 0.6), x * b / 2, 0.12)
    return norm(buf, 0.3)


def loop_photo(rng):
    buf, b = loop_buffer(112)
    k, s, h = kick(), snare(rng), hat(rng)
    for x in range(8):
        wrap_mix(buf, k, x * b, 0.5)
        wrap_mix(buf, h, (x + 0.5) * b, 0.2)
    for x in (1, 3, 5, 7):
        wrap_mix(buf, s, x * b, 0.35)
    # C장조 | F장조 - G장조, 옥타브를 오가는 베이스
    roots = [36] * 8 + [41] * 4 + [43] * 4
    for x, n in enumerate(roots):
        wrap_mix(buf, bass(n + (12 if x % 2 else 0), 0.45 * b), x * b / 2, 0.4)
    chords = [[60, 64, 67]] * 4 + [[60, 65, 69]] * 2 + [[59, 62, 67]] * 2
    for x, ch in enumerate(chords):
        for n in ch:
            wrap_mix(buf, pluck(n, 0.25, 0.8), (x + 0.5) * b, 0.07)
    return norm(buf, 0.32)


def sounds():
    rng = np.random.default_rng(20261124)
    out = {
        "count": norm(woodblock(1200), 0.7),
        "count_accent": norm(woodblock(1600), 0.8),
        "horn": norm(horn(50), 0.75),                     # 등대: 낮은 뱃고동
        "ship_bell": norm(bell(1318, 0.5, 7), 0.75),      # 배: 높은 종
        "hoot_a": norm(hoot(67), 0.7),                    # 올빼미 G4
        "hoot_b": norm(hoot(71), 0.7),                    # B4
        "hoot_me": norm(hoot(74), 0.75),                  # D5
        "desk_bell": norm(bell(2093, 0.7, 5), 0.7),       # 사진관 호출 종
        "shutter": norm(shutter(rng), 0.8),
        "dull": norm(dull(), 0.6),
        "finish": norm(jingle([(60, 64, 67, 72)], 0.1, 1.4), 0.6),
        "jingle_great": norm(jingle([72, 76, 79, (72, 76, 79, 84)], 0.11), 0.6),
        "jingle_good": norm(jingle([67, 72, (67, 72, 76)], 0.13), 0.6),
        "jingle_try": norm(jingle([67, 64, (60, 63, 67)], 0.16), 0.5),
        "loop_lighthouse": loop_lighthouse(rng),
        "loop_owls": loop_owls(rng),
        "loop_photo": loop_photo(rng),
    }
    return out


def write_wav(path, y):
    data = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def main():
    os.makedirs(SPRITE_DIR, exist_ok=True)
    os.makedirs(SOUND_DIR, exist_ok=True)
    for name, (rows, pal) in sprites().items():
        sprite_image(rows, pal).save(os.path.join(SPRITE_DIR, name + ".png"), optimize=True)
    for name, y in sounds().items():
        write_wav(os.path.join(SOUND_DIR, name + ".wav"), y)
    print("sprites:", len(os.listdir(SPRITE_DIR)), "sounds:", len(os.listdir(SOUND_DIR)))


if __name__ == "__main__":
    sys.exit(main())
