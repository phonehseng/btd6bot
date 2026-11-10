"""Draw the HUD into an image, offline: no window, no lock, no control files.

    python tools/hud_preview.py out.png [--root DIR | --demo] [--background IMG] [--size 1920x1200]
                                        [--view auto|game|menu] [--at SECONDS] [--hud glass|big]

Reads the bot's files under --root (default: this repo) the way the live HUD
does (hud_data.Collector) - or, with --demo, a made-up bot folder in a
temporary directory (a Bazaar half-cash game at round 61, the planner's
pick between games), so a preview shows every widget whatever the live bot
is doing - and draws them for a screen of --size over
--background (a game frame, stretched to the screen; dark grey without
one). The game's client area is taken to fill the screen, as BTD6 runs
full screen. --at moves the animation clock to that many seconds after the
files were read.

  --hud glass   (the default) the glass HUD (tools/glass_scene.py): each
                widget's picture composited where its window would sit; the
                time each widget took to draw is printed
  --hud big     the old big HUD (tools/hud_scene.py): its shapes painted at
                the window's alpha; with --at, the margins grown and the
                newest log line typed
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hud_data                     # noqa: E402
import hud_scene as S               # noqa: E402
from big_hud import HUD_ALPHA       # noqa: E402

GREY = (40, 44, 52, 255)            # the screen without a --background

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
        base = Image.new("RGBA", size, GREY)
    layer = canvas.img
    layer.putalpha(layer.getchannel("A").point(lambda a: round(a * alpha)))
    return Image.alpha_composite(base, layer).convert("RGB")


def render_glass(pictures, size, background=None):
    """The glass widgets' pictures ({name: glass_scene.Picture}) composited
    over the background where their windows would sit."""
    base = Image.open(background).convert("RGBA").resize(size) if background else Image.new("RGBA", size, GREY)
    for pic in pictures.values():
        base.alpha_composite(pic.image, (max(0, pic.x), max(0, pic.y)),
                             (max(0, -pic.x), max(0, -pic.y)))      # a picture past the top or left edge is cut
    return base.convert("RGB")


def time_glass(scene, snap, now, game_rect, repeat=5):
    """{name: (Picture, best milliseconds of `repeat` builds)}; the first
    build, which fills the glass cache, is timed apart as 'cold'."""
    out = {}
    for name, _key, build in scene.widgets(snap, now, game_rect):
        t0 = time.perf_counter()
        pic = build()
        cold = (time.perf_counter() - t0) * 1000
        best = cold
        for _ in range(repeat):
            t0 = time.perf_counter()
            build()
            best = min(best, (time.perf_counter() - t0) * 1000)
        if pic is not None:
            out[name] = (pic, best, cold)
    return out


def demo_root(root, now, in_game):
    """Write a made-up bot folder under `root` (state, log, journal,
    hud.json, medals) for a preview: a Bazaar half-cash game at round 61,
    or the menus with the planner's pick."""
    root = Path(root)
    logs = root / "logs"
    (logs / "journal").mkdir(parents=True, exist_ok=True)

    def stamp(dt, level, source, msg):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - dt)) + f",000 {level} {source}: {msg}"
    state = "Bazaar half_cash - round 61, $1,789, 100 lives" if in_game else "menus - choosing the next game"
    (logs / "state.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S ") + state + "\n", encoding="utf-8")
    log = [stamp(9, "I", "match", "round 61  cash 1789  lives 100"),
           stamp(6, "I", "reinforce",
                 "reinforce: saving for upgrade sub2 -> 2-0-4 ($3,240) - round 63 goes 0.85 -> 1.42"),
           stamp(3, "I", "strategy", "plan step 14: upgrade sub1 -> 0-2-4")]
    if not in_game:
        log += [stamp(2, "I", "runner", "victory: Bazaar half_cash at round 80"),
                stamp(1, "I", "runner", "NEXT: [HF] Cargo / half_cash with cargo_half_cash: score 9,120/min; "
                                        "p=0.82 (n=3), 11.2 min, learned track, black border: 13 of 14")]
    (logs / "bot.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    journal = [{"t": now - 900, "ev": "game_start", "map": "Bazaar", "mode": "half_cash",
                "strategy": "bazaar_half_cash", "hero": "striker", "end_round": 80},
               {"t": now - 60, "ev": "upgrade", "rnd": 60, "tid": "sub1", "kind": "sub", "cross_before": "0-2-3",
                "cross_after": "0-2-4", "cost": 2700, "why": {"source": "plan", "reason": "plan step 13"}},
               {"t": now - 20, "ev": "upgrade", "rnd": 61, "tid": "dl1", "kind": "dartling", "cross_before": "0-2-2",
                "cross_after": "0-3-2", "cost": 3060,
                "why": {"source": "threat", "reason": "round 63 brings a DDT: camo + lead, 0.85 without it"}}]
    for r, m in ((58, 2.1), (59, 1.8), (60, 1.4)):
        journal.insert(1, {"t": now - 100 + r, "ev": "round", "rnd": r, "cash": 900, "lives": 100, "margin": m})
    if not in_game:
        journal.append({"t": now - 5, "ev": "game_end", "rnd": 80, "outcome": "victory", "round": 80})
    (logs / "journal" / "20261110_120000_Bazaar_half_cash.jsonl").write_text(
        "\n".join(json.dumps(r) for r in journal) + "\n", encoding="utf-8")
    planner = {"phase": "HF", "pick": {"map": "Cargo", "mode": "half_cash", "strategy": "cargo_half_cash", "p": 0.82,
                                       "notes": ["learned track", "black border: 13 of 14", "11.2 min"]},
               "runner_ups": [{"map": "Spillway", "mode": "chimps", "strategy": "s", "p": 0.64},
                              {"map": "Erosion", "mode": "abr", "strategy": "s", "p": 0.51}]}
    hud = {"phase": "menu", "t": now, "planner": planner}
    if in_game:
        hud = {"phase": "game", "t": now, "game": journal[0] | {"ev": None}, "round": 61, "cash": 1789, "lives": 100,
               "margins": [[61, 1.9], [62, 1.6], [63, 0.85], [64, 1.3], [65, 2.4], [66, 1.7], [67, 1.2], [68, 2.8]],
               "weak": 1.5, "crisis": 0.5,
               "towers": [["sub1", "sub", "0-2-4", 0.405, 0.30], ["dl1", "dartling", "0-3-2", 0.75, 0.40]],
               "plan": [{"do": "upgrade", "id": "dl1", "to": "0-4-2"},
                        {"do": "place", "id": "v1", "kind": "village", "at": [0.555, 0.55]},
                        {"do": "upgrade", "id": "v1", "to": "2-0-0"}],
               "sizes": {"sub": [0.008, 0.11], "dartling": [0.01, 0.0], "village": [0.011, 0.105]},
               "planner": planner}
    (logs / "hud.json").write_text(json.dumps(hud), encoding="utf-8")
    # medals: the Beginner maps black, a few more on the way
    maps, tiers, keys = hud_data.game_maps()
    medals = {}
    for i, (name, tier) in enumerate(maps.items()):
        won = len(keys) if tier == tiers[0] else (i * 5) % len(keys)
        medals[name] = {k: True for k in keys[:won]}
    (root / "data" / "accounts").mkdir(parents=True, exist_ok=True)
    (root / "data" / "current_account.txt").write_text("DEMO\n", encoding="utf-8")
    (root / "data" / "accounts" / "DEMO.json").write_text(json.dumps({"medals": medals}), encoding="utf-8")
    (logs / "level.txt").write_text("Lv 152 | 1,204,330 / 2,750,000 XP (44%)", encoding="utf-8")
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--root", default=str(hud_data.ROOT))
    ap.add_argument("--demo", action="store_true", help="draw made-up data instead of the bot's files")
    ap.add_argument("--background")
    ap.add_argument("--size", default="1920x1200")
    ap.add_argument("--view", choices=("auto", "game", "menu"), default="auto")
    ap.add_argument("--at", type=float, default=2.0)
    ap.add_argument("--hud", choices=("glass", "big"), default="glass")
    args = ap.parse_args(argv)
    w, h = (int(v) for v in args.size.lower().split("x"))
    if args.demo:
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            snap = hud_data.Collector(demo_root(tmp, now, args.view != "menu"), clock=lambda: now).poll()
    else:
        snap = hud_data.Collector(args.root).poll()
    if args.view != "auto":
        snap.in_game = args.view == "game"
    if args.hud == "glass":
        import glass_scene as G
        scene = G.GlassScene(w, h)
        timed = time_glass(scene, snap, snap.now + args.at, (0, 0, w, h))
        render_glass({n: t[0] for n, t in timed.items()}, (w, h), args.background).save(args.out)
        area = sum(p.image.width * p.image.height for n, (p, _b, _c) in timed.items() if n != "ghosts")
        print(args.out)
        for name, (pic, best, cold) in timed.items():
            print(f"  {name:9s} {pic.image.width:4d}x{pic.image.height:<4d} at ({pic.x}, {pic.y})  "
                  f"{best:6.2f} ms  (first draw {cold:.1f} ms)")
        print(f"  widgets' windows cover {area / (w * h):.1%} of the screen (ghosts aside)")
        return
    scene = S.Scene(w, h)
    t0 = snap.now
    scene.layers(snap, t0, (0, 0, w, h))            # starts the animation clocks at t0
    shapes = scene.build_all(snap, t0 + args.at, (0, 0, w, h))
    render(shapes, (w, h), args.background).save(args.out)
    print(args.out, f"{len(shapes)} shapes")


if __name__ == "__main__":
    main()
