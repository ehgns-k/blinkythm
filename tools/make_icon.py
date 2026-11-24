"""Build the exe icon (assets/blinkythm.ico). Run once before packaging."""
import os
from PIL import Image, ImageDraw


def draw(size):
    s = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((2 * s, 2 * s, 62 * s, 62 * s), fill=(212, 208, 200, 255), outline=(0, 0, 0, 255), width=max(1, int(2 * s)))
    for cx in (21, 43):
        d.ellipse(((cx - 10) * s, 18 * s, (cx + 10) * s, 42 * s), fill="white", outline="black", width=max(1, int(2 * s)))
        d.ellipse(((cx - 4) * s, 24 * s, (cx + 4) * s, 36 * s), fill=(0, 0, 0, 255))
    d.line((24 * s, 50 * s, 40 * s, 50 * s), fill="black", width=max(1, int(3 * s)))
    return img


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    os.makedirs(out, exist_ok=True)
    big = draw(256)
    big.save(os.path.join(out, "blinkythm.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
