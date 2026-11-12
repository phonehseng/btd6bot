"""Live placement judges a map's ground by the round being played.

Audit of 2026-11-12 (dynamic maps, items 3-5): the executor passed a round
to the placement grids on Covered Garden only, so
  - One Two Tree's land plots, opened as the game goes, were never used
    (dart cells: 1,869 in round 1, 3,187 by round 80 with the round);
  - Erosion's water from melted ice was never offered to subs (302 cells,
    against 2,865 by round 40);
  - Erosion's buffers asked for ground lasting the whole game (85 village
    cells) while the damage towers stood on the phase's ice;
  - all six of Erosion's phase paths counted as lanes, so open_lanes() said
    two or more lanes were open on every board.

Offline: the extracted map geometry (data/map_geometry) on a fresh model,
no game. Run: python tests/test_round_ground_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L, mapgeom, placement as PL, strategy as S   # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

PF = L.get(1920, 1200)["playfield"]


def model(name):
    """A fresh model of the map from its geometry alone (nothing learned)."""
    geom = mapgeom.load(name)
    if geom is None:
        return None
    m = mapgeom.apply(MapModel(name, PF), geom)
    m.refused = {}
    return m


def executor(m, mode="hard"):
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    return S.Executor(F.FakeGame(), m, plan, mode, F.full_account())


def test_one_two_tree_opened_plots_take_towers():
    m = model("One Two Tree")
    if m is None:
        return
    ex = executor(m)
    ex.now_round = 1
    early = ex._legal_cells("dart")
    ex.now_round = 80
    late = ex._legal_cells("dart")
    assert early.sum() == 1869, early.sum()
    assert late.sum() == 3187, late.sum()
    assert not (early & ~late).any(), "ground open in round 1 stays open"


def test_erosion_subs_get_melted_water():
    m = model("Erosion")
    if m is None:
        return
    ex = executor(m)
    ex.now_round = 1
    assert ex._legal_cells("sub").sum() == 302
    ex.now_round = 40
    assert ex._legal_cells("sub").sum() == 2865


def test_erosion_buffer_reaches_towers_on_phase_ice():
    """A ninja on the round-1 phase's ice, out of a village's reach from
    any cell that lasts the whole game: the village still finds a spot."""
    import cv2
    m = model("Erosion")
    if m is None:
        return
    ex = executor(m)
    ex.now_round, ex.ground_horizon = 1, mapgeom.phase_end(mapgeom.load("Erosion"), 1)
    lasting = PL.valid_spots(m, "village", last_round=80)
    phase = ex._legal_cells("village")
    assert lasting.sum() == 85 and phase.sum() == 3114, (lasting.sum(), phase.sum())
    # the phase cell farthest from every lasting village cell
    far = cv2.distanceTransform((~lasting).astype(np.uint8), cv2.DIST_L2, 5)
    far[~ex._legal_cells("ninja")] = 0
    y, x = np.unravel_index(int(far.argmax()), far.shape)
    assert far[y, x] > 2 * ex._range_cells("village"), "no ice beyond a village's reach"
    fx, fy = m.cell_to_frac(int(x), int(y))
    ex.g.towers = {"n1": F.Placed("n1", "ninja", fx, fy)}
    spots = ex._buff_spots("village")
    assert spots, "no village spot beside the ninja on phase ice"


def test_erosion_counts_only_the_live_phase_path_as_a_lane():
    m = model("Erosion")
    if m is None:
        return
    ex = executor(m)
    ex.now_round = 5
    assert len(ex._lane_grids()["path_masks"]) == 1   # Path1 alone until round 13
    ys, xs = np.nonzero(ex._legal_cells("ninja") & (ex._reach("ninja") > 0))
    fx, fy = m.cell_to_frac(int(xs[0]), int(ys[0]))
    ex.g.towers = {"n1": F.Placed("n1", "ninja", fx, fy)}
    assert ex.open_lanes() == 0, ex.open_lanes()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
