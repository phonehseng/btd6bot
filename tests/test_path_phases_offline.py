"""Maps whose bloons change path by round (no game needed).

Erosion's AlternateRoundSplitter hands its six paths 18 rounds each, in
order. Painting all six as track put Easy Primary Only's whole defence
beside paths no bloon takes before round 37, and the game was lost on
round 11. mapgeom.idle_phase_paths / repaint_track paint only the paths of
the round's phase (and the next one, PHASE_LEAD rounds ahead).

Uses the extracted JSON in data/map_geometry (skipped when it is absent)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapgeom  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]


def _names(geom, ids):
    by_id = {p["id"]: p["name"] for p in geom["paths"]}
    return {by_id[i] for i in ids}


def _erosion():
    return mapgeom.load("Erosion")


def test_erosion_phases():
    geom = _erosion()
    if geom is None:
        return
    alternating = {p for s in geom["mechanics"]["splitters"]
                   if s["type"].startswith("AlternateRound") for p in s["paths"]}
    every = _names(geom, alternating)
    # rounds 1-13: only Path1 carries bloons, even with the lead
    assert every - _names(geom, mapgeom.idle_phase_paths(geom, 1)) == {"Path1"}
    assert every - _names(geom, mapgeom.idle_phase_paths(geom, 10)) == {"Path1"}
    # five rounds before the switch the next path is painted as well
    assert every - _names(geom, mapgeom.idle_phase_paths(geom, 15)) == {"Path1", "Path2"}
    assert every - _names(geom, mapgeom.idle_phase_paths(geom, 20)) == {"Path2"}
    # the last phase lasts for good (doesNotLoop)
    assert every - _names(geom, mapgeom.idle_phase_paths(geom, 140)) == {"Path6"}


def test_maps_without_phases_keep_every_path():
    for name in ("Logs", "Sunken Columns"):
        geom = mapgeom.load(name)
        if geom is None:
            continue
        assert mapgeom.idle_phase_paths(geom, 10) == frozenset()


def test_repaint_moves_the_track():
    geom = _erosion()
    if geom is None:
        return
    m = mapgeom.apply(MapModel("Erosion", PF), geom)
    every = int((m.heat > 0).sum())
    lanes_before = m.scan["land"].copy()
    assert mapgeom.repaint_track(m, geom, 10)
    first = m.heat > 0
    assert 0 < first.sum() < every / 2         # one path of six
    assert (m.scan["land"] == lanes_before).all()   # placement grids untouched
    assert not mapgeom.repaint_track(m, geom, 11)   # same phase: nothing to do
    assert mapgeom.repaint_track(m, geom, 40)       # Path3's phase
    assert not ((m.heat > 0) & first).sum() > first.sum() / 2


def test_phase_end():
    geom = _erosion()
    if geom is None:
        return
    assert mapgeom.phase_end(geom, 1) == 18
    assert mapgeom.phase_end(geom, 22) == 36
    assert mapgeom.phase_end(geom, 36) == 36
    assert mapgeom.phase_end(geom, 37) == 54
    assert mapgeom.phase_end(geom, 95) is None      # Path6 lasts for good
    assert mapgeom.phase_end(geom, None) is None
    logs = mapgeom.load("Logs")
    if logs is not None:
        assert mapgeom.phase_end(logs, 22) is None


def _near(mask, cells=8):
    """mask grown by `cells` in the four directions (no scipy here)."""
    out = mask.copy()
    for _ in range(cells):
        n = out.copy()
        n[1:] |= out[:-1]
        n[:-1] |= out[1:]
        n[:, 1:] |= out[:, :-1]
        n[:, :-1] |= out[:, 1:]
        out = n
    return out


def test_phase_ground_reaches_the_live_path():
    """Case 20261106_130851 (Erosion Magic Monkeys Only, Fast Track start
    at round 22): ground lasting the whole game reaches none of Path2, so
    every ninja and wizard step was given up. Ground lasting until the
    phase ends (round 36) does reach it."""
    geom = _erosion()
    if geom is None:
        return
    from btd6bot import placement as PL
    m = mapgeom.apply(MapModel("Erosion", PF), geom)
    mapgeom.repaint_track(m, geom, 22)
    near = _near(m.heat > 0)
    whole = PL.valid_spots(m, "ninja", None, [], last_round=80, now_round=22)
    phase = PL.valid_spots(m, "ninja", None, [], last_round=mapgeom.phase_end(geom, 22), now_round=22)
    assert not (whole & near).any()
    assert (phase & near).sum() > 100


def test_towers_on_melted_ice_are_rebuilt():
    """After round 36 the ice beside Path2 melts with the towers on it:
    they are forgotten and their plan steps queued again."""
    geom = _erosion()
    if geom is None:
        return
    from types import SimpleNamespace
    from btd6bot import placement as PL
    from btd6bot.strategy import Executor
    m = mapgeom.apply(MapModel("Erosion", PF), geom)
    assert mapgeom.lost_ground(m, geom, 22, 30) is None    # nothing melts mid-phase
    lost = mapgeom.lost_ground(m, geom, 36, 37)
    assert lost is not None and lost.any()
    mapgeom.repaint_track(m, geom, 22)
    phase = PL.valid_spots(m, "ninja", None, [], last_round=36, now_round=22)
    rows, cols = (phase & lost & _near(m.heat > 0)).nonzero()
    assert len(rows)
    x0, y0, x1, y1 = m.playfield
    gw, gh = lost.shape[1], lost.shape[0]

    def frac(c, r):
        return x0 + (c + 0.5) / gw * (x1 - x0), y0 + (r + 0.5) / gh * (y1 - y0)

    melt = SimpleNamespace(tid="n1", kind="ninja", x=frac(cols[0], rows[0])[0], y=frac(cols[0], rows[0])[1])
    hero = SimpleNamespace(tid="hero", kind="hero", x=melt.x, y=melt.y)
    plan = [{"do": "place", "id": "n1", "kind": "ninja"}, {"do": "place", "id": "hero", "kind": "hero"},
            {"do": "upgrade", "id": "n1", "to": "2-0-1"}, {"do": "upgrade", "id": "w1", "to": "0-2-2"}]
    ex = SimpleNamespace(g=SimpleNamespace(towers={"n1": melt, "hero": hero}), m=m, plan=plan, idx=3,
                         track_changed=lambda: None)
    assert Executor.ground_lost(ex, lost) == ["n1"]
    assert set(ex.g.towers) == {"hero"}
    assert [s.get("to", s["do"]) for s in ex.plan[3:5]] == ["place", "2-0-1"]
    assert ex.plan[5]["id"] == "w1"


def test_reverse_model_uses_the_map_geometry():
    """Case 20261107_043112 (Erosion Reverse, solo_ace): the Reverse game's
    map model is keyed "Erosion reverse", and mapgeom found no geometry
    under that name, so placement lost the ground lifetimes and left the
    ace 4 legal cells - every ace step was given up on round 1. The reverse
    model must get the same legal ground as the forward one."""
    geom = _erosion()
    if geom is None:
        return
    from btd6bot import placement as PL
    assert mapgeom.map_id_for("Erosion reverse") == mapgeom.map_id_for("Erosion")
    counts = []
    for name, reverse in (("Erosion", False), ("Erosion reverse", True)):
        m = mapgeom.apply(MapModel(name, PF), geom)
        mapgeom.repaint_track(m, geom, 1, reverse=reverse)
        counts.append(int(PL.valid_spots(m, "ace", None, [], last_round=18, now_round=1).sum()))
    assert counts[0] > 1000 and counts[1] == counts[0]


def test_apopalypse_ice_goes_one_hud_round_early():
    """Case 20261109_120839 (Erosion Apopalypse, Fast Track start at round
    15): the ice that melts at round 19 went while the HUD read 18, with
    the next round's bloons already coming. In a continuous mode the map is
    followed one round ahead: at HUD 18 the towers on that ice are
    forgotten (and rebuilt), and ground for new towers lasts until HUD 17's
    phase end only. Other modes keep the HUD round."""
    geom = _erosion()
    if geom is None:
        return
    from types import SimpleNamespace
    from btd6bot import match as M
    seen = []

    def make(rules):
        mt = M.Match.__new__(M.Match)
        mt._phase_geom, mt._reverse = geom, False
        mt.m = mapgeom.apply(MapModel("Erosion", PF), geom)
        mt.ex = SimpleNamespace(rules=rules, ground_horizon=None, track_changed=lambda: None,
                                ground_lost=lambda lost: seen.append(int(lost.sum())))
        return mt

    apop = make({"continuous": True})
    apop._follow_track(15)
    assert apop.ex.ground_horizon == 18 and not seen      # map round 16: ice lasts to 18
    apop._follow_track(17)
    assert not seen
    apop._follow_track(18)                                 # map round 19: the ice is gone
    assert len(seen) == 1 and seen[0] > 0 and apop.ex.ground_horizon == 36
    seen.clear()
    hard = make({})
    hard._follow_track(15)
    hard._follow_track(18)
    assert not seen and hard.ex.ground_horizon == 18
    hard._follow_track(19)
    assert len(seen) == 1


def test_an_early_melt_is_applied_on_the_first_missing_tower():
    """Erosion Easy Primary Only (2026-11-10, Fast Track from round 10): the
    ice that melts for round 19 was gone at HUD 17, and the round-37 ice at
    HUD 35. The first tower on that ice that cannot be selected applies the
    melt at once (every tower there forgotten) and the two-round lead is
    kept, so the next melt is followed at HUD 35 without waiting for misses."""
    geom = _erosion()
    if geom is None:
        return
    from types import SimpleNamespace
    from btd6bot import match as M
    m = mapgeom.apply(MapModel("Erosion", PF), geom)
    lost19 = mapgeom.lost_ground(m, geom, 18, 19)
    rows, cols = lost19.nonzero()
    x0, y0, x1, y1 = m.playfield
    gh, gw = lost19.shape

    def frac(c, r):
        return x0 + (c + 0.5) / gw * (x1 - x0), y0 + (r + 0.5) / gh * (y1 - y0)

    x, y = frac(cols[0], rows[0])
    towers = {"b1": SimpleNamespace(tid="b1", kind="boomerang", x=x, y=y)}
    seen = []

    def ground_lost(lost):
        seen.append(int(lost.sum()))
        for tid, p in list(towers.items()):
            cx, cy = m.frac_to_cell(p.x, p.y)
            if lost[cy, cx]:
                towers.pop(tid)

    mt = M.Match.__new__(M.Match)
    mt._phase_geom, mt._reverse, mt.m = geom, False, m
    mt.g = SimpleNamespace(towers=towers)
    mt.ex = SimpleNamespace(rules={}, ground_horizon=None, track_changed=lambda: None,
                            ground_lost=ground_lost)
    mt._ground_lead = 0
    for r in range(10, 18):
        mt._follow_track(r)
    assert not seen and "b1" in towers
    far = SimpleNamespace(tid="d9", kind="dart", x=0.99, y=0.99)
    assert mt._melt_check(far) is False or not seen   # a tower elsewhere proves nothing
    assert mt._melt_check(towers["b1"]) is True
    assert len(seen) == 1 and "b1" not in towers and mt._ground_lead == 2
    assert mt.ex.ground_horizon == 36
    for r in range(18, 35):
        mt._follow_track(r)
    assert len(seen) == 1
    mt._follow_track(35)                                # trigger round 37: the next melt
    assert len(seen) == 2 and mt.ex.ground_horizon == 54


if __name__ == "__main__":
    test_an_early_melt_is_applied_on_the_first_missing_tower()
    test_apopalypse_ice_goes_one_hud_round_early()
    test_reverse_model_uses_the_map_geometry()
    test_erosion_phases()
    test_maps_without_phases_keep_every_path()
    test_repaint_moves_the_track()
    test_phase_end()
    test_phase_ground_reaches_the_live_path()
    test_towers_on_melted_ice_are_rebuilt()
    print("ok")
