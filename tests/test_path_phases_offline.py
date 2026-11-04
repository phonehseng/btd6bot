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


if __name__ == "__main__":
    test_erosion_phases()
    test_maps_without_phases_keep_every_path()
    test_repaint_moves_the_track()
    print("ok")
