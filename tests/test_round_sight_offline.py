"""Sight blockers and obstacles that go during a game stop counting once gone.

Audit of 2026-11-12 (dynamic maps, items 12 and 13):
  - Cargo's centre trucks and Quarry's MOAB-track obstacle go "after round
    39 or at the first MOAB spawn". The spawn trigger has no round, so the
    change stayed a "may" all game: Cargo's CentreTrucksBlocking blocked
    sight to the end;
  - One Two Tree's 23 BlockerPlots open between rounds 3 and 78, and the
    live spot search kept all of them as sight blockers (the model's
    whole-game sight grid is the union of every state).

Offline: the extracted geometry on a fresh model, no game.
Run: python tests/test_round_sight_offline.py"""
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
    geom = mapgeom.load(name)
    if geom is None:
        return None, None
    m = mapgeom.apply(MapModel(name, PF), geom)
    m.refused = {}
    return m, geom


def test_cargo_trucks_are_gone_from_round_40():
    m, geom = model("Cargo")
    if m is None:
        return
    event = next(e for e in geom["mechanics"]["events"]
                 if any(t["type"] == "PreBloonSpawnTrigger" for t in e["triggers"]))
    assert not mapgeom.dynamics(geom, now_round=39).fired[event["id"]][2]
    assert mapgeom.dynamics(geom, now_round=40).fired[event["id"]][2]
    whole = int(m.sight.sum())
    assert int(mapgeom.grids_for(m, now_round=39)["sight"].sum()) == whole == 3168
    assert int(mapgeom.grids_for(m, now_round=40)["sight"].sum()) == 2208


def test_quarry_moab_obstacle_is_gone_from_round_40():
    m, geom = model("Quarry")
    if m is None:
        return
    before = PL.valid_spots(m, "dart", now_round=39)
    after = PL.valid_spots(m, "dart", now_round=40)
    assert after.sum() > before.sum() and not (before & ~after).any()


def test_one_two_tree_opened_plots_stop_blocking_sight():
    m, geom = model("One Two Tree")
    if m is None:
        return
    ex = S.Executor(F.FakeGame(), m, {"id": "t", "name": "t", "hero": None, "plan": []},
                    "hard", F.full_account())
    assert ex._round_sight() is None          # no round read yet: the whole-game grids
    ex.now_round = 80
    blockers, heights = ex._round_sight()
    assert int(m.sight.sum()) == 3575 and int(blockers.sum()) == 2950
    # some dart spot sees more of the track past the opened plots
    weight = (m.heat > 0).astype(np.float32)
    rc = ex._range_cells("dart")
    ys, xs = np.nonzero(PL.valid_spots(m, "dart", now_round=80))
    gain = 0.0
    for x, y in list(zip(xs.tolist(), ys.tolist()))[::7]:
        old = PL.visible_cover(m, x, y, rc, weight)
        new = PL.visible_cover(m, x, y, rc, weight, (blockers, heights))
        assert new >= old
        gain = max(gain, new - old)
    assert gain > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
