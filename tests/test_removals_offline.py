"""Removable obstacles: the game's "Remove FOR $N" box is read from a real
frame (Peninsula, 2026-10-23), and buying Peninsula's kelp frees legal ground
for towers. Offline: saved frames and map geometry only."""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L, mapgeom, placement as PL   # noqa: E402
from btd6bot.game import find_removal_box                  # noqa: E402
from btd6bot.maplearn import MapModel                      # noqa: E402
from btd6bot.vision import Vision                          # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def words_of(img):
    return Vision(N(grab=lambda region=None: img)).read(img=img)


def test_the_removal_box_is_read():
    img = cv2.imread(str(FIX / "remove_kelp_box.png"))
    box = find_removal_box(img, words_of(img))
    assert box is not None and box["price"] == 500
    # the green check sits at about (0.26, 0.47), the red X at about (0.14, 0.48)
    cx, cy = box["confirm"]
    assert 0.23 < cx < 0.29 and 0.44 < cy < 0.51, box
    kx, ky = box["cancel"]
    assert 0.11 < kx < 0.17 and 0.45 < ky < 0.52, box


def test_no_box_no_purchase():
    img = cv2.imread(str(FIX / "remove_kelp_none.png"))
    assert find_removal_box(img, words_of(img)) is None


def test_peninsula_kelp_frees_ground():
    m = MapModel.load("Peninsula", L.get(1920, 1200)["playfield"])
    m.refused = {}
    obstacles = {r["name"]: r for r in mapgeom.removables("Peninsula", m.playfield)}
    assert {"RemovableKelpLowerLeft", "RemovableKelpRight", "RemovableKelpMidLeft"} <= set(obstacles)
    before = PL.valid_spots(m, "sniper")
    after = PL.valid_spots(m, "sniper", removed=("RemovableKelpMidLeft",))
    freed = after & ~before
    assert freed.sum() >= 4, freed.sum()
    # the freed cells are around the kelp the bot clicks
    fx, fy = obstacles["RemovableKelpMidLeft"]["frac"]
    cx, cy = m.frac_to_cell(fx, fy)
    ys, xs = freed.nonzero()
    assert ((xs - cx) ** 2 + (ys - cy) ** 2).min() < 10 ** 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
