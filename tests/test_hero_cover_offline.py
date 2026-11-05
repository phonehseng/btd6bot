"""The hero covers its lane only as much as its price is worth.

Party Parade Medium (2026-11-04, solo_bomb, fast track from round 15): the
opener dart (1-0-0) and Quincy stood in the left lane, a1 (0-2-2 bomb) in
the right one. The hero counted as the strongest tower on the board, so the
left lane looked defended and a2, b1 and the village all went right. Bloons
split between both lanes and the left one leaked 90 lives by round 31.
Offline, with the real map model: on that board, a2 must go to the left lane.
Run: python tests/test_hero_cover_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402


def board():
    """The towers standing when a2 was placed (positions from game.log)."""
    opener = F.Placed("opener", "dart", 0.227, 0.240)
    opener.tiers = [1, 0, 0]
    a1 = F.Placed("a1", "bomb", 0.644, 0.564)
    a1.tiers = [0, 2, 2]
    return {"opener": opener, "a1": a1,
            "hero": F.Placed("hero", "hero", 0.222, 0.462)}


def test_the_hero_does_not_make_its_lane_defended():
    m = MapModel.load("Party Parade", L.get(1920, 1200)["playfield"])
    if not m.known():
        return                      # map not learned on this machine
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame("quincy"), m, plan, "medium", F.full_account())
    ex.g.towers = board()
    cov = ex._covered()
    hero = m.frac_to_cell(0.222, 0.462)
    bomb = m.frac_to_cell(0.644, 0.564)
    assert cov[bomb[1], bomb[0]] == 1.0
    assert cov[hero[1], hero[0]] < 0.7, cov[hero[1], hero[0]]   # $540 against a1's cash
    ex.__dict__["_probed"] = {("bomb", -1, -1)}   # no blocked-spot probe in this test
    step = {"do": "place", "id": "a2", "kind": "bomb", "role": "dps", "segment": [0.3, 0.8]}
    spots = ex.pick_spots("bomb", step, n=3)
    assert spots
    fx, _ = m.cell_to_frac(spots[0][0], spots[0][1])
    assert fx < 0.5, ("a2 went to the right lane again", spots)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
