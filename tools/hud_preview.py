"""Draw the big HUD into an image, offline: no window, no lock, no control files.

    python tools/hud_preview.py out.png [--root DIR] [--background IMG] [--size 1920x1200]
                                        [--view auto|game|menu] [--at SECONDS]

Reads the bot's files under --root (default: this repo) the way the live HUD
does (hud_data.Collector), lays them out with hud_scene.Scene for a screen of
--size and paints the shapes over --background (a game frame, stretched to
the screen; dark grey without one) at the HUD window's own alpha. The game's
client area is taken to fill the screen, as BTD6 runs full screen. --at
moves the animation clock to that many seconds after the files were read,
so a still shows the margins grown and the newest log line typed.

Painting uses Pillow, a developer tool here and not a dependency of the bot
or of the live HUD (which draws the same shapes on a Tk canvas).
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hud_data                     # noqa: E402
import hud_scene as S               # noqa: E402
from big_hud import HUD_ALPHA       # noqa: E402

FONT_FILES = {(S.FONT, False): "segoeui.ttf", (S.FONT, True): "segoeuib.ttf",
              (S.MONO, False): "consola.ttf", (S.MONO, True): "consolab.ttf"}
FONT_DIR = Path(r"C:\Windows\Fonts")
STIPPLE_COVER = {"gray12": 0.125, "gray25": 0.25, "gray50": 0.5, "gray75": 0.75}
# Tk text anchors -> Pillow's (horizontal: left/middle/right, vertical: ascender/middle/descender)
ANCHORS = {"nw": "la", "n": "ma", "ne": "ra", "w": "lm", "center": "mm", "e": "rm", "sw": "ld", "s": "md", "se": "rd"}


def rgba(colour, cover=1.0):
    if not colour:
        return None
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5)) + (round(255 * cover),)


class PilCanvas:
    """The few Tk canvas calls the scene uses, painted with Pillow."""

    def __init__(self, size):
        self.img = Image.new("RGBA", size, (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        self._fonts = {}

    def _font(self, font):
        family, size, weight = font
        key = (family, -size, weight)
        if key not in self._fonts:
            name = FONT_FILES.get((family, weight == "bold"), "segoeui.ttf")
            try:
                self._fonts[key] = ImageFont.truetype(str(FONT_DIR / name), max(1, -size))
            except OSError:
                self._fonts[key] = ImageFont.load_default()
        return self._fonts[key]

    @staticmethod
    def _box(coords):
        x0, y0, x1, y1 = coords
        return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

    def create_rectangle(self, *coords, fill=None, outline="#000000", width=1, stipple=None, **_):
        cover = STIPPLE_COVER.get(stipple, 1.0)
        self.draw.rectangle(self._box(coords), fill=rgba(fill, cover), outline=rgba(outline),
                            width=int(width) if outline else 0)

    def create_oval(self, *coords, fill=None, outline="#000000", width=1, stipple=None, **_):
        cover = STIPPLE_COVER.get(stipple, 1.0)
        self.draw.ellipse(self._box(coords), fill=rgba(fill, cover), outline=rgba(outline),
                          width=int(width) if outline else 0)

    def create_arc(self, *coords, start=0, extent=90, outline="#000000", width=1, **_):
        # Tk counts degrees anticlockwise from 3 o'clock, Pillow clockwise
        self.draw.arc(self._box(coords), -(start + extent), -start, fill=rgba(outline), width=int(width))

    def create_line(self, *coords, fill="#000000", width=1, dash=None, **_):
        pts = list(zip(coords[::2], coords[1::2]))
        if not dash:
            self.draw.line(pts, fill=rgba(fill), width=int(width))
            return
        on, off = dash[0], dash[1] if len(dash) > 1 else dash[0]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = max(1e-6, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
            d = 0.0
            while d < length:
                e = min(length, d + on)
                self.draw.line([(x0 + (x1 - x0) * d / length, y0 + (y1 - y0) * d / length),
                                (x0 + (x1 - x0) * e / length, y0 + (y1 - y0) * e / length)],
                               fill=rgba(fill), width=int(width))
                d = e + off

    def create_polygon(self, *coords, fill=None, outline=None, stipple=None, **_):
        cover = STIPPLE_COVER.get(stipple, 1.0)
        self.draw.polygon(list(zip(coords[::2], coords[1::2])), fill=rgba(fill, cover), outline=rgba(outline))

    def create_text(self, x, y, text="", fill="#ffffff", anchor="center", font=(S.FONT, -12, "normal"), **_):
        if text:
            self.draw.text((x, y), text, fill=rgba(fill), font=self._font(font), anchor=ANCHORS.get(anchor, "la"))


def render(shapes, size, background=None, alpha=HUD_ALPHA):
    """The shapes over the background, the HUD layer at the window's alpha."""
    canvas = PilCanvas(size)
    for s in shapes:
        getattr(canvas, "create_" + s.kind)(*s.coords, **s.opts)
    if background is not None:
        base = Image.open(background).convert("RGBA").resize(size)
    else:
        base = Image.new("RGBA", size, (40, 44, 52, 255))
    layer = canvas.img
    layer.putalpha(layer.getchannel("A").point(lambda a: round(a * alpha)))
    return Image.alpha_composite(base, layer).convert("RGB")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--root", default=str(hud_data.ROOT))
    ap.add_argument("--background")
    ap.add_argument("--size", default="1920x1200")
    ap.add_argument("--view", choices=("auto", "game", "menu"), default="auto")
    ap.add_argument("--at", type=float, default=2.0)
    args = ap.parse_args(argv)
    w, h = (int(v) for v in args.size.lower().split("x"))
    snap = hud_data.Collector(args.root).poll()
    if args.view != "auto":
        snap.in_game = args.view == "game"
    scene = S.Scene(w, h)
    t0 = snap.now
    scene.layers(snap, t0, (0, 0, w, h))            # starts the animation clocks at t0
    shapes = scene.build_all(snap, t0 + args.at, (0, 0, w, h))
    render(shapes, (w, h), args.background).save(args.out)
    print(args.out, f"{len(shapes)} shapes")


if __name__ == "__main__":
    main()
