"""What is worked out from the track follows Erosion's path phases.

Audit of 2026-11-12 (dynamic maps, items 6 and 7):
  - the cursor point Dartlings and helis aim at (Match._park_point) was
    found once per game, so after mapgeom.repaint_track moved the track to
    the next phase's path they aimed at the old one;
  - during a phase's lead-in (PHASE_LEAD rounds before the switch) the track
    is painted for two paths, and _reach_fn spread one path's length over
    both: every tower's blimp reach was halved in rounds 14-18.

Offline: the extracted geometry on a fresh model, no game.
Run: python tests/test_phase_track_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L, mapgeom, match as M, strategy as S   # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

PF = L.get(1920, 1200)["playfield"]


def erosion(rnd):
    geom = mapgeom.load("Erosion")
    if geom is None:
        return None, None
    m = mapgeom.apply(MapModel("Erosion", PF), geom)
    m.refused = {}
    mapgeom.repaint_track(m, geom, rnd)
    return m, geom


def test_park_point_follows_the_repainted_track():
    m, geom = erosion(1)
    if m is None:
        return
    match = M.Match.__new__(M.Match)
    match.m, match._park = m, None
    first = match._park_point()
    cx, cy = m.frac_to_cell(*first)
    assert m.heat[int(cy), int(cx)] > 0
    assert mapgeom.repaint_track(m, geom, 40)       # Path3's phase
    moved = match._park_point()
    cx, cy = m.frac_to_cell(*moved)
    assert moved != first and m.heat[int(round(cy)), int(round(cx))] > 0, (first, moved)


def test_blimp_reach_is_not_halved_in_a_phase_lead_in():
    m, geom = erosion(10)
    if m is None:
        return
    ex = S.Executor(F.FakeGame(), m, {"id": "t", "name": "t", "hero": None, "plan": []},
                    "hard", F.full_account())
    ex._init_threats()
    # a ninja beside Path1 (the only path in round 10), out of reach of
    # Path2, which the lead-in paints from round 14 on
    import cv2
    proj = mapgeom.Projection(PF)
    path1, = mapgeom.path_masks(geom, proj, mapgeom.idle_phase_paths(geom, 10))
    both = mapgeom.path_masks(geom, proj, mapgeom.idle_phase_paths(geom, 15))
    path2 = np.logical_or.reduce(both) & ~path1
    far = cv2.distanceTransform((~path2).astype(np.uint8), cv2.DIST_L2, 5)
    far[~path1] = 0
    y, x = np.unravel_index(int(far.argmax()), far.shape)
    assert far[y, x] > ex._range_cells("ninja") + 2
    ex.g.towers = {"n1": F.Placed("n1", "ninja", *m.cell_to_frac(int(x), int(y)))}
    ex.now_round = 10
    alone = ex._reach_fn()("n1", "ninja")
    assert mapgeom.repaint_track(m, geom, 15)       # Path2 painted as well
    ex.track_changed()
    ex.now_round = 15
    lead_in = ex._reach_fn()("n1", "ninja")
    assert alone > 0 and abs(lead_in - alone) <= 0.1 * alone, (alone, lead_in)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
