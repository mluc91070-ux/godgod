"""Render the raster brand assets from the charter mark.

    backend/.venv/Scripts/python scripts/build_brand.py

The geometry matches `frontend/components/Mark.tsx`. Both are drawn from the
same numbers so the tab icon and the in-page logo cannot drift apart; change
one and run this.

Below 24px the mark drops its horizontal segments. The full mark is an ellipse
plus six lines, and at 16 pixels those land on the same three rows and turn to
mush — verified by rendering it. A mark nobody can read in a browser tab is not
more faithful for having kept every stroke.
"""

from __future__ import annotations

import math
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public"

BONE = (242, 242, 242)
GREY = (160, 160, 160)
VOID = (5, 5, 6)
MAGENTA = (255, 44, 240)


def draw_mark(size: int, stroke: float, *, simplified: bool, colour=BONE) -> Image.Image:
    """The charter mark, measured off the reference render.

    Circle r=0.39 of the box, split by a ±5° gap top and bottom where the
    vertical passes; horizontal spokes from 0.17R to 0.84R staying inside the
    circle; diagonals from 0.20R to 1.21R punching through it. That asymmetry
    is what stops it reading as a wheel.

    Supersampled then downscaled: Pillow draws no antialiased lines.
    """
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    r = s * 0.39
    w = max(1, int(stroke * scale))
    gap = 5

    box = [c - r, c - r, c + r, c + r]
    d.arc(box, 90 + gap, 270 - gap, fill=colour, width=w)
    d.arc(box, 270 + gap, 90 - gap, fill=colour, width=w)

    d.line([c, c - r, c, c + r], fill=colour, width=w)

    def spoke(angle: float, start: float, end: float) -> None:
        t = math.radians(angle)
        d.line(
            [
                c + start * math.cos(t), c + start * math.sin(t),
                c + end * math.cos(t), c + end * math.sin(t),
            ],
            fill=colour,
            width=w,
        )

    for angle in (45, 135, 225, 315):
        spoke(angle, r * 0.2, r * 1.21)

    if not simplified:
        spoke(0, r * 0.17, r * 0.84)
        spoke(180, r * 0.17, r * 0.84)

    return img.resize((size, size), Image.LANCZOS)


def write_ico(path: Path, images: list[Image.Image]) -> None:
    """Write the container directly.

    Pillow's ICO writer resizes one source image into every requested size, so
    it cannot hold a simplified small variant next to the full one.
    """
    payloads = []
    for image in images:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        payloads.append(buffer.getvalue())

    offset = 6 + 16 * len(images)
    blob = struct.pack("<HHH", 0, 1, len(images))
    for image, payload in zip(images, payloads, strict=True):
        blob += struct.pack(
            "<BBBBHHII",
            image.width if image.width < 256 else 0,
            image.height if image.height < 256 else 0,
            0, 0, 1, 32, len(payload), offset,
        )
        offset += len(payload)
    path.write_bytes(blob + b"".join(payloads))


def font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    loaded = ImageFont.truetype(str(path), size)
    try:
        loaded.set_variation_by_axes([weight])
    except OSError:
        pass  # static build of the face; the requested weight is already baked in
    return loaded


def build_og(orbitron: Path, exo: Path) -> None:
    card = Image.new("RGBA", (1200, 630), (*VOID, 255))
    glow = Image.new("RGBA", (1200, 630), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    for index, alpha in enumerate((26, 44, 80)):
        pad = index * 9
        draw.ellipse(
            [452 - pad, 72 - pad, 748 + pad, 368 + pad], outline=(*MAGENTA, alpha), width=2
        )
    card = Image.alpha_composite(card, glow)
    card.alpha_composite(draw_mark(280, 11, simplified=False), (460, 80))
    card = card.convert("RGB")

    d = ImageDraw.Draw(card)
    d.text((600, 432), "GODGOD", font=font(orbitron, 72, 700), fill=BONE, anchor="mm")
    d.text(
        (600, 496),
        "T H E   A U T O N O M O U S   M E M E   R E S E A R C H E R",
        font=font(exo, 22, 400),
        fill=GREY,
        anchor="mm",
    )
    d.text(
        (600, 560),
        "it publishes what failed",
        font=font(exo, 26, 300),
        fill=MAGENTA,
        anchor="mm",
    )
    card.save(OUT / "og.png")


def main() -> int:
    write_ico(
        OUT / "favicon.ico",
        [
            draw_mark(16, 1.5, simplified=True),
            draw_mark(24, 2.0, simplified=True),
            draw_mark(32, 2.6, simplified=False),
            draw_mark(48, 3.4, simplified=False),
        ],
    )

    apple = Image.new("RGBA", (180, 180), (*VOID, 255))
    apple.alpha_composite(draw_mark(180, 8.5, simplified=False))
    apple.convert("RGB").save(OUT / "apple-icon.png")

    fonts = ROOT / "assets" / "fonts"
    orbitron, exo = fonts / "Orbitron.ttf", fonts / "Exo2.ttf"
    if orbitron.exists() and exo.exists():
        build_og(orbitron, exo)
        print("og.png rebuilt")
    else:
        print(
            f"og.png left as-is: the charter faces are not in {fonts}. "
            "Rebuilding it with a substitute font would put the wrong wordmark "
            "on every link preview, which is worse than leaving the file alone."
        )

    for name in ("favicon.ico", "apple-icon.png", "icon.svg", "og.png"):
        path = OUT / name
        if path.exists():
            print(f"  {name:<16} {path.stat().st_size:>7} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
