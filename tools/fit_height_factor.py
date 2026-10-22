"""Measure how the game camera shows raised ground (mapgeom.HEIGHT_FACTOR).

The camera is tilted, so a point raised by h units appears higher on screen
than its ground position. This tool opens a map with raised paths in Sandbox
(free, no towers, infinite lives), sends a few rounds, records where bloons
actually appear, and finds the height factor k for which the map's 3-D path
(data/map_geometry, points [x, z, y]) projected with z + k*y passes closest to
the bloons. Run it with the bot paused, from the main menu:

    python tools/fit_height_factor.py "Luminous Cove"

It prints the best k and the median distance (pixels) for a range of k. The
game is never modified; it is only played in Sandbox and watched.
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import identity, mapgeom  # noqa: E402
from btd6bot import tracklearn as TL  # noqa: E402
from btd6bot.game import Game  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402
from btd6bot.runner import Bot  # noqa: E402


def collect_bloon_pixels(bot, g, rounds=(17, 21, 19), seconds_per_round=25):
    """Screen pixels (x, y) where sent bloons were seen, at full resolution."""
    model = MapModel("height-fit", bot.lay["playfield"])
    tracer = TL.SandboxTracer(model, TL._load("bloons.json")["bloons"])
    TL._wait_still(g)
    tracer.warm_up([g.fresh() for _ in range(10)])
    panel = TL.SandboxPanel(bot)
    TL._fast(bot, g)
    xs, ys = [], []
    for rnd in rounds:
        panel.send_round(bot, rnd)
        tracer.start_round(TL.round_kinds(rnd))
        end = time.time() + seconds_per_round
        while time.time() < end:
            f = g.fresh()
            cells = np.zeros(model.heat.shape, bool)
            for k, c in tracer._detect(f).items():
                if k in tracer.kinds:
                    cells |= c
            cy, cx = np.nonzero(cells)
            # grid cell centres -> screen pixels
            for x, y in zip(cx, cy):
                fx, fy = model.cell_to_frac(x, y)
                xs.append(fx * f.shape[1]); ys.append(fy * f.shape[0])
            time.sleep(0.05)
    return np.array(xs), np.array(ys), g.fresh().shape


def fit(map_name, xs, ys, shape, ks=np.arange(-0.2, 1.21, 0.05)):
    """Median pixel distance from the bloons to the projected path, per k."""
    h, w = shape[:2]
    geom = mapgeom.load(map_name)
    results = []
    for k in ks:
        mapgeom.HEIGHT_FACTOR = float(k)
        proj = mapgeom.Projection((0.0, 0.04, 0.855, 0.96))
        line = np.zeros((h, w), np.uint8)
        for p in geom["paths"]:
            if p["hidden"]:
                continue
            c = proj.to_cells(p["points"])
            px = np.stack([c[:, 0] / 160 * 0.855 * w, (0.04 + c[:, 1] / 108 * 0.92) * h], 1)
            cv2.polylines(line, [px.astype(np.int32)], False, 1, 2)
        dist = cv2.distanceTransform(1 - line, cv2.DIST_L2, 3)
        xi = np.clip(xs.astype(int), 0, w - 1)
        yi = np.clip(ys.astype(int), 0, h - 1)
        results.append((float(np.median(dist[yi, xi])), round(float(k), 2)))
    return sorted(results)


def main(map_name):
    bot = Bot(identity.current_path())
    bot.s.focus()
    bot.to_main_menu()
    diff = TL.sandbox_difficulty(bot.account, map_name)
    if diff is None or not TL._enter_sandbox(bot, map_name, diff):
        print("could not open the Sandbox on", map_name)
        return
    g = Game(bot.s, bot.inp, bot.lay, difficulty=diff, hero=None)
    try:
        xs, ys, shape = collect_bloon_pixels(bot, g)
    finally:
        TL._leave(bot, g)
    print(f"{len(xs)} bloon samples")
    for dist, k in fit(map_name, xs, ys, shape)[:8]:
        print(f"k={k:5.2f}  median distance {dist:.1f} px")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Luminous Cove")
