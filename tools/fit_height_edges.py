"""Fit the camera height factor from map pictures alone (no bloons needed).

Raised and sunken areas (platforms, pools, ledges) are polygons with a
height in the game's map data. Projected with the right height factor k
(screen up-shift = k * height), their outlines lie on the edges visible in a
picture of the map. This tool opens each map in Easy Standard, photographs
the field BEFORE round 1 is started (no bloons are released, nothing is
placed), returns to the menu, and reports for each k how strongly the
projected outlines of raised areas sit on image edges.

    python tools/fit_height_edges.py "Luminous Cove" "Ancient Portal" "Adora's Temple"

Run it with the bot paused. The game files are not modified.
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import identity, mapgeom  # noqa: E402
from btd6bot.game import Game  # noqa: E402
from btd6bot.runner import Bot  # noqa: E402

PLAYFIELD = (0.0, 0.04, 0.855, 0.96)


def photograph(bot, map_name):
    """Open the map in Easy Standard, grab the untouched field, go home."""
    bot.skip_known = None
    if bot.open_map(map_name) is not True:
        return None
    bot.menus.read()
    if not bot.menus.click_word("easy", dy=-0.09, region=(0, 0.3, 1, 0.7)):
        return None
    bot.menus.wait_for("mode_select", timeout=4)
    bot.menus.read()
    if not bot.menus.click_word("standard", dy=-0.08):
        return None
    g = Game(bot.s, bot.inp, bot.lay, difficulty="easy", hero=None)
    end = time.time() + 30
    while time.time() < end and not g.in_game():
        time.sleep(1)
        if bot.menus.identify() == "overwrite":
            bot.menus.click_word("ok", "yes", "overwrite")
        else:
            bot.menus.dismiss_popup()
    time.sleep(3)          # let intro animations settle; round 1 is NOT started
    frame = g.fresh()
    bot.to_main_menu()     # gear -> Home: leaves before any round runs
    return frame


def edge_score(frame, geom, k):
    """Mean edge strength along projected outlines of raised/sunken areas."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    mapgeom.HEIGHT_FACTOR = float(k)
    proj = mapgeom.Projection(PLAYFIELD)
    mask = np.zeros((h, w), np.uint8)
    for a in geom["areas"]:
        for poly in a["polygons"]:
            if len(poly) < 3 or max(abs(p[2]) for p in poly) < 5:
                continue   # flat areas say nothing about the height factor
            c = proj.to_cells(poly)
            px = np.stack([c[:, 0] / 160 * 0.855 * w, (0.04 + c[:, 1] / 108 * 0.92) * h], 1)
            cv2.polylines(mask, [px.astype(np.int32)], True, 1, 1)
    on = mask > 0
    return float(edges[on].mean() / 255.0) if on.any() else 0.0


def main(names):
    bot = Bot(identity.current_path())
    bot.s.focus()
    bot.to_main_menu()
    ks = np.arange(-0.4, 1.41, 0.05)
    total = np.zeros(len(ks))
    for name in names:
        geom = mapgeom.load(name)
        frame = photograph(bot, name)
        if frame is None or geom is None:
            print(name, ": could not photograph")
            continue
        cv2.imwrite(f"logs/heightfit_{mapgeom.map_id_for(name)}.png", cv2.resize(frame, (960, 600)))
        scores = np.array([edge_score(frame, geom, k) for k in ks])
        total += scores / max(scores.max(), 1e-6)
        best = ks[int(scores.argmax())]
        print(f"{name}: best k = {best:.2f}  (score {scores.max():.3f}, k=0 scores {scores[np.argmin(abs(ks))]:.3f})")
    print(f"combined best k = {ks[int(total.argmax())]:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Luminous Cove", "Ancient Portal", "Adora's Temple"])
