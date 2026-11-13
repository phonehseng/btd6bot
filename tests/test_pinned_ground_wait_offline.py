"""A plan tower waits for its pinned ground on a map that changes by phase.

Erosion's ice melts into water at each 18-round phase's end. In the threat
simulation of erosion_impoppable (2026-11-12) the executor's cash ran ahead
of the plan: buc20, pinned on water that round 18's melt makes, was bought in
round 15 and stood across the map ("nothing legal within 15 cells of its
spot"). Executor._wait_for_pinned_ground sets such a step aside until its
ground is there; when the ground is there, or never comes, nothing changes.

Run: python tests/test_pinned_ground_wait_offline.py"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_achievement_strats_offline as F  # noqa: E402  (the fakes)
from btd6bot import layout as L  # noqa: E402
from btd6bot import mapgeom as G  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = L.get(1920, 1200)["playfield"]


def _model(name):
    """A fresh model of the map from its geometry alone (nothing learned)."""
    geom = G.load(name)
    if geom is None:
        return None
    m = G.apply(MapModel(name, PF), geom)
    m.refused = {}
    return m


def _water_from_round_19(m):
    """A buccaneer cell that is water in round 19 but not in round 15."""
    later = PL.valid_spots(m, "buccaneer", now_round=19, last_round=36)
    before = PL.valid_spots(m, "buccaneer", now_round=15, last_round=18)
    ys, xs = np.nonzero(later & ~before)
    assert len(xs), "the melt of round 18 makes water"
    return m.cell_to_frac(int(xs[0]), int(ys[0]))


def _executor(m, step):
    plan = {"id": "t", "name": "t", "hero": None, "plan": [step]}
    return S.Executor(F.FakeGame(), m, plan, "impoppable", F.full_account())


def test_a_tower_bought_before_its_water_is_set_aside():
    m = _model("Erosion")
    if m is None:
        return
    at = [round(v, 3) for v in _water_from_round_19(m)]
    step = {"do": "place", "id": "buc20", "kind": "buccaneer", "at": at}
    ex = _executor(m, step)
    ex.now_round = 15
    assert ex._wait_for_pinned_ground(step, "plan:0", "buccaneer") is not None
    ex.now_round = 19
    assert ex._wait_for_pinned_ground(step, "plan:0", "buccaneer") is None


def test_a_map_without_phases_never_waits():
    m = _model("Monkey Meadow")
    if m is None:
        return
    step = {"do": "place", "id": "d1", "kind": "dart", "at": [0.5, 0.5]}
    ex = _executor(m, step)
    ex.now_round = 10
    assert ex._wait_for_pinned_ground(step, "plan:0", "dart") is None


def test_a_step_without_a_pin_or_off_the_plan_never_waits():
    m = _model("Erosion")
    if m is None:
        return
    at = [round(v, 3) for v in _water_from_round_19(m)]
    ex = _executor(m, {"do": "place", "id": "buc20", "kind": "buccaneer", "at": at})
    ex.now_round = 15
    assert ex._wait_for_pinned_ground({"do": "place", "id": "buc20", "kind": "buccaneer"}, "plan:0",
                                      "buccaneer") is None
    assert ex._wait_for_pinned_ground({"do": "place", "id": "ans1", "kind": "buccaneer", "at": at}, "ans",
                                      "buccaneer") is None


def test_a_plan_that_buys_each_phase_itself_does_not_rebuild_the_melted_towers():
    """ground_lost forgets the towers on melted ice; it queues their plan
    steps again unless the build says rebuild_lost: false (an optimizer plan
    that buys the next phase's towers itself: erosion_impoppable)."""
    m = _model("Erosion")
    if m is None:
        return
    for rebuild, queued in ((None, True), (False, False)):
        step = {"do": "place", "id": "n1", "kind": "ninja", "at": [0.5, 0.5]}
        plan = {"id": "t", "name": "t", "hero": None, "plan": [step, {"do": "upgrade", "id": "n1", "to": "2-0-0"}]}
        if rebuild is not None:
            plan["rebuild_lost"] = rebuild
        ex = S.Executor(F.FakeGame(), m, plan, "impoppable", F.full_account())
        ex.g.towers["n1"] = type("P", (), {"tid": "n1", "kind": "ninja", "x": 0.5, "y": 0.5, "tiers": [2, 0, 0]})()
        ex.idx = 2
        cx, cy = m.frac_to_cell(0.5, 0.5)
        lost = np.zeros(m.heat.shape, bool)
        lost[cy, cx] = True
        assert ex.ground_lost(lost) == ["n1"]
        assert "n1" not in ex.g.towers
        assert (len(ex.plan) > 2) is queued, (rebuild, ex.plan)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
