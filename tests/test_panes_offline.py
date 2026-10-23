"""Covered Garden's glass panes: one garden quarter is open each round, the
bottom-left on round 1, then clockwise (top-left, top-right, bottom-right).

The bot must place towers on the open quarter's ground in its round, never
on a shut one, and click (upgrade, sell) a tower under a pane only while
that pane is open. Offline: the map geometry only, no game."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L, mapgeom, placement as PL   # noqa: E402
from btd6bot.maplearn import MapModel                      # noqa: E402

# the quarter open in rounds 1-4 (screen fractions: x < 0.46 is the left half,
# y < 0.49 the top half; data/map_geometry/coveredgarden.json)
OPEN_IN_ROUND = {1: ("left", "bottom"), 2: ("left", "top"), 3: ("right", "top"), 4: ("right", "bottom")}


def model():
    m = MapModel.load("Covered Garden", L.get(1920, 1200)["playfield"])
    m.refused = {}     # what earlier games learned does not matter here
    return m


def test_open_quarter_follows_the_round():
    m = model()
    always = PL.valid_spots(m, "sniper")
    for rnd in range(1, 9):
        extra = PL.valid_spots(m, "sniper", now_round=rnd) & ~always
        ys, xs = np.nonzero(extra)
        assert len(xs) > 20, f"round {rnd}: no pane ground opened"
        fx, fy = m.cell_to_frac(int(xs.mean()), int(ys.mean()))
        side, half = OPEN_IN_ROUND[(rnd - 1) % 4 + 1]
        assert (fx < 0.46) == (side == "left"), (rnd, fx)
        assert (fy < 0.49) == (half == "top"), (rnd, fy)


def test_whole_game_grid_keeps_panes_shut():
    m = model()
    always = PL.valid_spots(m, "sniper")
    for rnd in range(1, 5):
        assert not (always & ~PL.valid_spots(m, "sniper", now_round=rnd)).any(), \
            "ground open all game must stay open in every round"


def test_tower_under_a_pane_is_clicked_only_in_its_rounds():
    m = model()
    top_left = (0.32, 0.28)      # the guides' ninja pocket by the fountain
    rounds = [r for r in range(1, 13) if mapgeom.pane_at(m, *top_left, r)[1]]
    assert rounds == [2, 6, 10], rounds
    assert mapgeom.pane_at(m, 0.05, 0.62, 3) == (None, True), "the left strip is never covered"


def test_maps_without_panes_are_untouched():
    m = MapModel.load("Monkey Meadow", L.get(1920, 1200)["playfield"])
    assert mapgeom.pane_at(m, 0.5, 0.5, 3) == (None, True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
