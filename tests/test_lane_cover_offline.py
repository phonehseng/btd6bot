"""Track already covered counts by how strong the tower covering it is.

Firing Range ABR (2026-11-04, double_hp_sniper_sun, fast track from round
22): the opener dart (0-0-0, $215) stood on the right lane, n1 (2-0-1 ninja)
and Obyn on the left. Cover was 0/1, so the bare dart made the right lane
look defended as well as the left, and n2 went to the left lane too. The
right lane leaked 74 lives in rounds 23-24. Offline, with the real map
model: with that board, the second ninja must go to the right lane.
Run: python tests/test_lane_cover_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402


def board():
    """The towers standing when n2 was placed (positions from game.log)."""
    n1 = F.Placed("n1", "ninja", 0.142, 0.802)
    n1.tiers = [2, 0, 1]
    return {"n1": n1,
            "hero": F.Placed("hero", "hero", 0.136, 0.726),
            "opener": F.Placed("opener", "dart", 0.740, 0.547)}


def test_a_bare_dart_does_not_make_a_lane_defended():
    m = MapModel.load("Firing Range", L.get(1920, 1200)["playfield"])
    if not m.known():
        return                      # map not learned on this machine
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "abr", F.full_account())
    ex.g.towers = board()
    cov = ex._covered()
    dart = m.frac_to_cell(0.740, 0.547)
    ninja = m.frac_to_cell(0.142, 0.802)
    assert cov[ninja[1], ninja[0]] == 1.0
    assert cov[dart[1], dart[0]] < 0.5, cov[dart[1], dart[0]]   # $215 against n1's cash
    ex.__dict__["_probed"] = {("ninja", -1, -1)}   # the blocked-spot probe was refused in that game
    step = {"do": "place", "id": "n2", "kind": "ninja", "role": "dps", "segment": [0.3, 0.9]}
    spots = ex.pick_spots("ninja", step, n=3)
    assert spots
    fx, _ = m.cell_to_frac(spots[0][0], spots[0][1])
    assert fx > 0.5, ("n2 went to the left lane again", spots)


def test_a_pop_record_in_the_guarded_lane_does_not_pull_n2_there():
    """The same board, with the left-lane spot carrying the learned x1.25
    pop bonus (maplearn.spot_factor) that this machine's Firing Range data
    gave it on 2026-11-07: n2 must still go to the right lane, since that
    record was earned in the only lane anyone guarded."""
    from btd6bot import maplearn
    m = MapModel.load("Firing Range", L.get(1920, 1200)["playfield"])
    if not m.known():
        return                      # map not learned on this machine
    m.spot_stats = dict(m.spot_stats or {})
    m.spot_stats[maplearn._spot_key("ninja", 29, 59)] = [3.0, 1]   # 3x the median pops
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "abr", F.full_account())
    ex.g.towers = board()
    ex.__dict__["_probed"] = {("ninja", -1, -1)}
    step = {"do": "place", "id": "n2", "kind": "ninja", "role": "dps", "segment": [0.3, 0.9]}
    spots = ex.pick_spots("ninja", step, n=3)
    assert spots
    fx, _ = m.cell_to_frac(spots[0][0], spots[0][1])
    assert fx > 0.5, ("a pop record pulled n2 to the guarded lane", spots)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
