"""A blimp answer stands where the blimps pass.

Workshop ABR (case 20261109_044354, double_hp_sniper_sun): the round-37
blimp check placed its new MOAB answer, ans_blimps_bomb, at x 0.019 - the
entrance of the belt. Workshop's MOAB-class bloons never come there: from
round 40 they drop down the chute at x ~0.57 and ride only the rest of the
belt (a MoabOnlySplitter in the map file), so the bomb never hit a MOAB and
round 40 was lost with 100 lives. The spot was scored on the whole track
(role dps, segment 0.0-0.7). Now a blimp answer scores only the blimps' own
route (mapgeom.blimp_track), read from the map's splitters.
Run: python tests/test_blimp_lane_offline.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import mapgeom as G              # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402

PLAYFIELD = L.get(1920, 1200)["playfield"]


def _geom(map_id):
    path = ROOT / "data" / "map_geometry" / f"{map_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_workshop_blimp_route_is_past_the_chute():
    """The blimps' route is the belt after the chute (x 0.55-0.85), and the
    entrance where the case's bomb stood is not on it."""
    geom = _geom("workshop")
    if geom is None:
        return                      # geometry not extracted on this machine
    proj = G.Projection(PLAYFIELD)
    lane = G.blimp_track(geom, proj)
    assert lane is not None, "Workshop's MOAB route was not found"
    x0, _, x1, _ = PLAYFIELD
    cols = lane.any(axis=0).nonzero()[0]
    left = x0 + cols.min() / lane.shape[1] * (x1 - x0)
    assert left > 0.45, ("the blimp route reaches the entrance", left)
    heat, _, _ = G.paint_paths(geom, proj)
    assert lane.sum() < (heat > 0).sum() * 0.6, "the blimp route is not a part of the track"


def test_maps_without_a_moab_route_give_none():
    """Where blimps share the track with everything else, nothing changes."""
    for map_id in ("logs", "cubism", "spillway"):
        geom = _geom(map_id)
        if geom is None:
            continue
        assert G.blimp_track(geom, G.Projection(PLAYFIELD)) is None, map_id


def test_blimp_needs_are_recognised():
    ex = S.Executor
    assert ex._is_blimp_need("blimps")
    assert ex._is_blimp_need("moab")
    assert ex._is_blimp_need("ddt")
    assert ex._is_blimp_need("camo+blimp")
    assert not ex._is_blimp_need("camo")
    assert not ex._is_blimp_need("camo+lead")


def test_workshop_bomb_answer_goes_onto_the_blimp_route():
    """The case's answer step, picked on the real map model: the bomb must
    stand within reach of the blimps' route, right of the chute."""
    m = MapModel.load("Workshop", PLAYFIELD)
    if not m.known() or _geom("workshop") is None:
        return                      # map not learned on this machine
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "abr", F.full_account())
    ex.g.towers = {}
    ex.__dict__["_probed"] = {("bomb", -1, -1)}
    opt = ex._new_tower_option("blimps", "bomb", 1000, (0, 3, 0))
    step = opt["steps"][0]
    assert step.get("lane") == "blimp", step
    spots = ex.pick_spots("bomb", step, n=3)
    assert spots, "no spot for the blimp answer"
    fx, _ = m.cell_to_frac(spots[0][0], spots[0][1])
    assert fx > 0.45, ("the blimp answer went to the entrance again", fx, spots)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
