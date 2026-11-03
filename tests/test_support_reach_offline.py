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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
