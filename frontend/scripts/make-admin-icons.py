#!/usr/bin/env python3
"""Generate the back-office app icons: the public icons with a gear on them.

Nothing a public visitor sees changes — this only writes public/icons/pwa/admin/, which
only the dev/staging build points at. The mark, the colours and the ground are the
public ones; the gear is the whole difference, which is all it has to be to tell two
tiles apart on a home screen.

The gear is drawn at 4x and downsampled so the teeth survive at 72px, in the dark ink on
the transparent-ground icons and in cream on the maskables (which have a dark ground).
On a maskable it also sits closer to the middle, because a launcher crops the corners.

    python3 frontend/scripts/make-admin-icons.py

Reads frontend/public/icons/pwa/*.png, writes frontend/public/icons/pwa/admin/*.png.
"""
import math
import pathlib

from PIL import Image, ImageDraw

SRC = pathlib.Path(__file__).resolve().parent.parent / "public" / "icons" / "pwa"
DST = SRC / "admin"

INK = (14, 16, 20, 255)       # #0e1014, the mark colour on the light icons
CREAM = (241, 234, 216, 255)  # what the maskables use for the mark
SS = 4                        # supersample factor
TEETH = 8


def gear(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    """A cog: alternating radii around the circle, then a hole punched in the middle."""
    pts = []
    for i in range(TEETH * 4):
        # tooth, tooth, gap, gap — a flat-topped tooth every other pair of steps
        rr = r if i % 4 in (0, 1) else r * 0.78
        a = (i + 0.5) * (2 * math.pi / (TEETH * 4)) - math.pi / 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    draw.polygon(pts, fill=fill)
    draw.ellipse((cx - r * 0.30, cy - r * 0.30, cx + r * 0.30, cy + r * 0.30), fill=(0, 0, 0, 0))


def main() -> None:
    DST.mkdir(exist_ok=True)
    for src in sorted(SRC.glob("*.png")):
        base = Image.open(src).convert("RGBA")
        s = base.size[0]
        maskable = base.getpixel((1, 1))[3] == 255
        # maskable: inside the safe circle a launcher will not crop. otherwise: top-right
        # corner, the one part of the mark's diagonal that is empty.
        cx, cy, r = (0.70, 0.30, 0.105) if maskable else (0.775, 0.225, 0.155)
        fill = CREAM if maskable else INK

        overlay = Image.new("RGBA", (s * SS, s * SS), (0, 0, 0, 0))
        gear(ImageDraw.Draw(overlay), cx * s * SS, cy * s * SS, r * s * SS, fill)
        base.alpha_composite(overlay.resize((s, s), Image.LANCZOS))
        base.save(DST / src.name)
        print(f"  {src.name}")


if __name__ == "__main__":
    main()
