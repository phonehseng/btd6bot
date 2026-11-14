"""A village may stand on Geared's gear, beside the towers that ride on it.

Geared ABR, 2026-11-13 09:33 (loss case 20261113_093857_Geared_abr):
military_heli_sniper started at round 22 with two 2-2-0 snipers and a heli,
all on the big gear. Round 27 of ABR is 250 camo bloons in one stream. The
build's camo answer for the heli is a Radar Scanner village "near" it, and
that step was "given up after 0 refused spots": all of Geared's land is gear
ground, and a tower with a range was allowed on moving ground only where it
keeps the track in reach in every position (mapgeom.steady_spots) - no cell
for a village. But a village is worth the towers in its radius, not the
track, and on the same gear it turns with them. The heli never saw a camo
bloon, the three snipers popped a few a second, and all 100 lives went in
ten seconds on a board the damage model rated 1.63.

Now a buffer (village, alchemist) may stand on moving ground that carries a
damage tower, and counts as buffing only the towers riding with it
(mapgeom.carrier_of, Executor._beside_riders, Executor._buffed).
Offline: the real Geared geometry, the towers of the lost game.
Run: python tests/test_buffer_on_gear_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import mapgeom                    # noqa: E402
from btd6bot.game import Placed                # noqa: E402

# the lost game's towers where the bot bought them (screen fractions)
LOST_BOARD = (("s1", "sniper", 0.430, 0.342), ("s2", "sniper", 0.393, 0.351),
              ("h1", "heli", 0.334, 0.359))
CAMO_VILLAGE = {"do": "place", "id": "camo_village", "kind": "village", "role": "support",
                "near": ["hero", "s1", "s2", "h1"], "near_radius": 8}


def _executor(board=LOST_BOARD):
    """An Executor on the real Geared map with `board` standing, or None
    when the map's geometry file is not there."""
    if mapgeom.load("Geared") is None:
        return None
    from test_gear_round_offline import _executor as geared_executor
    ex = geared_executor()[0]
    for tid, kind, fx, fy in board:
        ex.g.towers[tid] = Placed(tid, kind, fx, fy)
    return ex


def test_every_cell_of_geared_rides_on_one_gear_or_none():
    ex = _executor()
    if ex is None:
        return
    carriers = mapgeom.carrier_of(ex.m)
    moving = mapgeom.grids_for(ex.m)["moving"]
    assert carriers.shape == moving.shape
    assert ((carriers > 0) == moving).all()
    assert len(set(np.unique(carriers).tolist()) - {0}) == 2      # the big gear and the small one


def test_the_camo_village_finds_a_spot_beside_the_heli():
    ex = _executor()
    if ex is None:
        return
    spots = ex._spots_widening("village", dict(CAMO_VILLAGE))
    assert spots, "no spot for the village on the gear"
    carriers = mapgeom.carrier_of(ex.m)
    heli = ex.g.towers["h1"]
    hx, hy = ex.m.frac_to_cell(heli.x, heli.y)
    reach = ex._range_cells("village")
    cx, cy = spots[0][0], spots[0][1]
    assert carriers[cy, cx] == carriers[hy, hx] != 0              # on the heli's own gear
    assert (cx - hx) ** 2 + (cy - hy) ** 2 <= reach ** 2          # and the pad in its radius
    assert ex._buffed("village", cx, cy) == len(LOST_BOARD)


def test_a_tower_on_the_other_gear_is_not_counted():
    ex = _executor()
    if ex is None:
        return
    carriers = mapgeom.carrier_of(ex.m)
    heli = ex.g.towers["h1"]
    hx, hy = ex.m.frac_to_cell(heli.x, heli.y)
    other = next(k for k in np.unique(carriers).tolist() if k not in (0, int(carriers[hy, hx])))
    ys, xs = np.nonzero(carriers == other)
    # the cell of the other gear nearest the heli: in a village's radius today, carried off tomorrow
    i = int(np.argmin((xs - hx) ** 2 + (ys - hy) ** 2))
    assert ex._buffed("village", int(xs[i]), int(ys[i])) == 0
    # ... and the village's legal ground leaves out a gear nothing rides on
    legal = ex._legal_cells("village")
    assert legal.any() and not (legal & (carriers == other)).any()


def test_no_village_on_a_gear_without_towers():
    ex = _executor(board=())
    if ex is None:
        return
    assert not ex._legal_cells("village").any()
    assert ex._spots_widening("village", dict(CAMO_VILLAGE)) == []


def test_towers_that_need_the_track_keep_the_old_rule():
    ex = _executor()
    if ex is None:
        return
    assert not ex._legal_cells("dart").any()          # no steady spot on Geared
    assert ex._legal_cells("sniper").any()            # global range: anywhere on the gear


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
