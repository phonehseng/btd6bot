"""A damage tower placed by `role: support` (beside the towers it supports)
must still reach the track that sell_useless asks of it.

Cargo Double HP (2026-11-03, double_hp_sniper_sun): a Super Monkey "near v1"
went to a spot whose range reached 0 track cells. sell_useless sold it the
next round, the plan placed it there again, and so on from round 69 to 75,
with $16k-$30k idle each time. Offline: the executor with a fake game whose
best support spots reach no track. Run: python tests/test_support_reach_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import placement as PL           # noqa: E402
from btd6bot import strategy as S             # noqa: E402


class NearVillageModel(F.FakeModel):
    """Only the right half reaches the track. A search near the village
    ranks the left half first; a search by track cover, the right half."""

    def score_spots(self, rc, seg, occupied, near=None, **kw):
        ramp = np.linspace(2.0, 1.0, self.W, dtype=np.float32)
        return np.tile(ramp if near is not None else ramp[::-1], (self.H, 1))

    def spot_weight(self, seg, covered):
        return np.ones((self.H, self.W), np.float32)


def executor():
    plan = {"id": "t", "name": "t", "hero": None,
            "plan": [{"do": "place", "id": "su1", "kind": "super", "role": "support", "near": ["v1"]}]}
    ex = S.Executor(F.FakeGame(), NearVillageModel(), plan, "double_hp", F.full_account())
    reach = np.zeros((NearVillageModel.H, NearVillageModel.W), np.float32)
    reach[:, NearVillageModel.W // 2:] = 100.0
    ex._reach_cache = {"super": reach}
    ex.g.towers = {"v1": F.Placed("v1", "village", 0.05, 0.5)}
    return ex


def test_support_damage_tower_goes_where_it_reaches_the_track():
    original = PL.valid_spots
    PL.valid_spots = lambda *a, **k: np.ones((NearVillageModel.H, NearVillageModel.W), bool)
    try:
        ex = executor()
        step = next(st for st in ex.plan if st.get("id") == "su1")
        assert ex.pick_spots("super", step, n=3) == []   # nothing near v1 reaches the track
        spots = ex._spots_widening("super", step)           # so a later stage places it
    finally:
        PL.valid_spots = original
    assert spots, "a legal spot reaching the track exists"
    assert all(cx >= NearVillageModel.W // 2 for cx, _, _ in spots), spots


def test_support_damage_tower_gets_no_spot_when_no_legal_cell_reaches_the_track():
    # Covered Garden Impoppable (2026-11-11, case 20261111_194816): under the
    # one open pane no legal cell reached the track, the reach floor was
    # therefore unknown, and "placing by role only" stood the Super Monkey
    # where it reached 0 track cells ($13,280 with its upgrades).
    original, sight = PL.valid_spots, PL.needs_sight
    PL.valid_spots = lambda *a, **k: np.ones((NearVillageModel.H, NearVillageModel.W), bool)
    PL.needs_sight = lambda *a: False      # no walls on the fake map
    try:
        ex = executor()
        ex._reach_cache = {"super": np.zeros((NearVillageModel.H, NearVillageModel.W), np.float32)}
        by_role = {"do": "place", "id": "su1", "kind": "super", "role": "support"}
        assert ex.pick_spots("super", by_role, n=3) == []
        # every later stage (wider circle, by role, as a damage tower) too
        assert ex._spots_widening("super", dict(by_role, near=["v1"])) == []
    finally:
        PL.valid_spots, PL.needs_sight = original, sight


def test_a_sold_tower_is_never_bought_back_in_the_same_place():
    # Glacial Trail Medium: a camo-answer Mermonkey sold for reaching no track
    # was placed again on the same spot within the round
    original, sight = PL.valid_spots, PL.needs_sight
    PL.valid_spots = lambda *a, **k: np.ones((NearVillageModel.H, NearVillageModel.W), bool)
    PL.needs_sight = lambda *a: False      # no walls on the fake map
    try:
        ex = executor()
        su = F.Placed("su1", "super", 0.995, 0.5)   # on the best-ranked spot
        ex.g.towers["su1"] = su
        ex._sell_and_avoid(su, rnd=70)
        sold_at = ex.m.frac_to_cell(su.x, su.y)
        spots = ex.pick_spots("super", {"do": "place", "kind": "super", "role": "dps"}, n=10)
    finally:
        PL.valid_spots, PL.needs_sight = original, sight
    assert spots
    assert all((cx - sold_at[0]) ** 2 + (cy - sold_at[1]) ** 2 > S.Executor.SOLD_SPOT_CELLS ** 2
               for cx, cy, _ in spots), spots


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
