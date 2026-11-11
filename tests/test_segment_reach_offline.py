"""A progress window no legal spot reaches gives way to the whole track.

Firing Range Impoppable (2026-11-11, chimps_ninja_sun, lost in round 6 at
03:18 and again at 15:14 with one life): both bloon paths share the three
lanes along the top and then walk down one side each to their own exit. The
only ground is the field below the barbed wire, more than a ninja's range
from the lanes, so for n1's window [0.0, 0.5] and the starter dart's
[0.05, 0.45] every legal spot scored 0.0. n1 went to 0.136,0.743 and the
starter to 0.168,0.871, both on the left exit lane; the other path's bloons
walked down the right lane untouched. Offline, with the real map model: the
opener must reach track, and the starter must guard the lane n1 does not.
Run: python tests/test_segment_reach_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402

N1_STEP = {"do": "place", "id": "n1", "kind": "ninja", "role": "dps", "segment": [0.0, 0.5]}
STARTER_STEP = {"do": "place", "id": "starter", "kind": "dart", "role": "dps",
                "segment": [0.05, 0.45]}


def executor():
    """An Impoppable executor on the real Firing Range model, its one
    blocked-spot probe per kind already spent (both were refused in the lost
    game); None when the map is not learned on this machine."""
    m = MapModel.load("Firing Range", L.get(1920, 1200)["playfield"])
    if not m.known():
        return None
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "impoppable", F.full_account())
    ex.__dict__["_probed"] = {("ninja", -1, -1), ("dart", -1, -1)}
    return ex


def test_the_opener_is_scored_on_track_it_can_reach():
    ex = executor()
    if ex is None:
        return
    spots = ex.pick_spots("ninja", N1_STEP, n=3)
    assert spots
    # a score counts weighted track cells in range: the lost game's was 0.0
    assert spots[0][2] > 100, ("n1 still ranked by a window out of reach", spots)


def test_the_starter_guards_the_lane_the_opener_does_not():
    ex = executor()
    if ex is None:
        return
    n1 = F.Placed("n1", "ninja", 0.136, 0.743)     # where it stood in the lost game
    n1.tiers = [1, 0, 1]
    ex.g.towers = {"n1": n1}
    spots = ex.pick_spots("dart", STARTER_STEP, n=3)
    assert spots
    fx, _ = ex.m.cell_to_frac(spots[0][0], spots[0][1])
    assert fx > 0.5, ("the starter went to n1's lane again", spots)


def test_a_window_in_reach_is_kept():
    """Monkey Meadow's first half runs through open grass: the window stays."""
    m = MapModel.load("Monkey Meadow", L.get(1920, 1200)["playfield"])
    if not m.known():
        return
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "impoppable", F.full_account())
    rc = min(ex._range_cells("ninja"), 60)
    valid = ex._legal_cells("ninja")
    block = ex._keep_off_scarce("ninja", valid, ex._blocked_for("ninja"))
    seg = ex._segment_in_reach("ninja", (0.0, 0.5), rc, "land", block, ex._covered(), valid)
    assert seg == (0.0, 0.5), seg


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
