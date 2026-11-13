"""A map build's researched spots (`at`) for support steps, as Enchanted
Glade Impoppable lost them (2026-11-12 20:25, loss case
20261112_210026_EnchantedGlade_impoppable, lost at round 98):

  * v2, the MIB village pinned on the top-left island "near ac1", was the
    plan's step before ac1. With no ace standing, the executor placed it
    where it buffed the most towers already standing - by the opening ninja
    at the bottom of the map - and the aces, bomb and sniper meant to stand
    in its range stood across the map from it. A buffer whose `near` towers
    are still to come from the plan now takes its researched spot.
  * b1, the plan's MOAB Eliminator "near v2", was pinned at a cell where a
    bomb reaches 0 of the best 276 track cells. It was placed there, grown
    to 0-4-0 ($6,570) and sold by sell_useless at round 68. A support damage
    tower's researched spot is now held to the reach sell_useless asks.

Offline: the executor with the fake game and model of
tests/test_achievement_strats_offline.py. Run:
python tests/test_pinned_support_spots_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import placement as PL           # noqa: E402
from btd6bot import strategy as S             # noqa: E402

W, H = F.FakeModel.W, F.FakeModel.H


class RightReachModel(F.FakeModel):
    """Track cover grows to the right (the right half is where the track
    is); a search near a tower ranks the cells by it alone."""

    def score_spots(self, rc, seg, occupied, near=None, extra_block=None, **kw):
        cover = np.tile(np.linspace(1.0, 2.0, self.W, dtype=np.float32), (self.H, 1))
        if extra_block is not None:
            cover[extra_block] = 0
        return cover

    def spot_weight(self, seg, covered, only=None):
        return np.ones((self.H, self.W), np.float32)


def executor(plan, towers):
    ex = S.Executor(F.FakeGame(), RightReachModel(), {"id": "t", "name": "t", "hero": None, "plan": plan},
                    "impoppable", F.full_account())
    ex.g.towers = dict(towers)
    return ex


def open_ground(fn):
    """Run fn with every cell legal and no walls on the fake map."""
    original, sight = PL.valid_spots, PL.needs_sight
    PL.valid_spots = lambda *a, **k: np.ones((H, W), bool)
    PL.needs_sight = lambda *a: False
    try:
        return fn()
    finally:
        PL.valid_spots, PL.needs_sight = original, sight


VILLAGE_FIRST = [
    {"do": "place", "id": "n2", "kind": "ninja", "role": "dps"},
    {"do": "place", "id": "v2", "kind": "village", "role": "support", "near": ["ac1"], "near_radius": 7,
     "at": [0.9, 0.5]},
    {"do": "place", "id": "ac1", "kind": "ace", "role": "support", "at": [0.92, 0.4]},
]


def _near(spots, at, cells):
    cx, cy = int(at[0] * W), int(at[1] * H)
    return all((x - cx) ** 2 + (y - cy) ** 2 <= cells ** 2 for x, y, _ in spots)


def test_a_village_bought_before_its_towers_takes_its_researched_spot():
    ex = executor(VILLAGE_FIRST, {"n2": F.Placed("n2", "ninja", 0.05, 0.5)})
    step = VILLAGE_FIRST[1]
    spots = open_ground(lambda: ex._spots_widening("village", step))
    assert spots, "its spot is legal"
    assert _near(spots, step["at"], ex.AT_SEARCH_CELLS), spots


def test_a_village_whose_towers_will_not_come_still_goes_by_the_towers_standing():
    # the ace's step was given up: nothing will stand at the village's spot,
    # so it buffs what stands (Water Park: a lone village buffing nothing)
    ex = executor(VILLAGE_FIRST, {"n2": F.Placed("n2", "ninja", 0.05, 0.5)})
    ex.dead_steps.add(ex._step_key(VILLAGE_FIRST[2]))
    spots = open_ground(lambda: ex._spots_widening("village", VILLAGE_FIRST[1]))
    assert spots and not _near(spots[:1], VILLAGE_FIRST[1]["at"], 20), spots


def test_a_support_damage_tower_is_not_placed_on_a_pinned_spot_out_of_reach():
    step = {"do": "place", "id": "b1", "kind": "bomb", "role": "support", "near": ["v2"], "near_radius": 7,
            "at": [0.1, 0.5]}
    ex = executor([step], {"v2": F.Placed("v2", "village", 0.1, 0.5)})
    reach = np.zeros((H, W), np.float32)
    reach[:, W // 2:] = 100.0              # only the right half reaches the track
    ex._reach_cache = {"bomb": reach}
    at = ex.m.frac_to_cell(*step["at"])
    picked = open_ground(lambda: ex.pick_spots("bomb", step, n=3))
    assert all((x, y) != at for x, y, _ in picked), picked
    assert all(reach[y, x] > 0 for x, y, _ in picked), picked
    spots = open_ground(lambda: ex._spots_widening("bomb", step))
    assert spots and all(x >= W // 2 for x, _, _ in spots), spots


def test_a_pinned_support_spot_in_reach_is_kept():
    step = {"do": "place", "id": "b1", "kind": "bomb", "role": "support", "near": ["v2"], "near_radius": 7,
            "at": [0.7, 0.5]}
    ex = executor([step], {"v2": F.Placed("v2", "village", 0.7, 0.5)})
    reach = np.zeros((H, W), np.float32)
    reach[:, W // 2:] = 100.0
    ex._reach_cache = {"bomb": reach}
    picked = open_ground(lambda: ex.pick_spots("bomb", step, n=3))
    assert picked and picked[0][:2] == ex.m.frac_to_cell(*step["at"]), picked


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
