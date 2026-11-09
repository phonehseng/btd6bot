"""A big tower's refusal is learned for its kind, not for every tower.

Tricky Tracks (2026-11-09): the ace's footprint is a 28x18 runway, wider than
the radius-12 circle the placement grid checks. Next to the map's diagonal
tracks the game turned it down again and again, and every refusal was learned
as bad land for every tower. The map file came to hold 1,148 refused cells,
nearly all 9-16 units from the track: ground where a radius-6 ninja fits with
room to spare. They took 26% of the ground the small towers may use.

  * placement.refusal_layer: a small tower's refusal goes into the surface's
    shared layer, a bigger tower's into one of its own ("land@ace");
  * valid_spots: an ace's refusal keeps the next ace off that cell but leaves
    it open to a ninja; a ninja's refusal keeps both off it;
  * the executor learns refusals that way and forgets its own layer under
    a tower that stands (Executor._learn_blocked / _learn_accepted);
  * the layer survives save and load;
  * Tricky Tracks' old refusals are dropped once (maplearn.REFUSAL_RESETS).
Run: python tests/test_refusal_layers_offline.py"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import mapgeom, maplearn  # noqa: E402
from btd6bot import placement as P  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]
MAP = "Tricky Tracks"


def tricky_tracks():
    """Tricky Tracks from its game geometry alone, no learned refusals."""
    model = mapgeom.apply(MapModel(MAP, PF), mapgeom.load(MAP))
    assert P.has_geometry(model)
    return model


def a_cell_both_may_use(model):
    """A cell where both an ace and a ninja may stand."""
    both = P.valid_spots(model, "ace") & P.valid_spots(model, "ninja")
    ys, xs = np.nonzero(both)
    assert len(xs), "no cell takes both an ace and a ninja"
    return int(xs[len(xs) // 2]), int(ys[len(ys) // 2])


def test_layers_by_footprint():
    assert P.refusal_layer("land", "ninja") == "land"
    assert P.refusal_layer("land", "dart") == "land"
    assert P.refusal_layer("land", "ace") == "land@ace"
    assert P.refusal_layer("land", "village") == "land@village"
    assert P.refusal_layer("water", "sub") == "water@sub"


def test_ace_refusal_keeps_only_aces_off():
    m = tricky_tracks()
    cx, cy = a_cell_both_may_use(m)
    m.refuse(P.refusal_layer("land", "ace"), cx, cy)
    assert not P.valid_spots(m, "ace")[cy, cx], "the ace's own refusal was ignored"
    assert P.valid_spots(m, "ninja")[cy, cx], "an ace's refusal took the cell from a ninja"


def test_small_refusal_keeps_everyone_off():
    m = tricky_tracks()
    cx, cy = a_cell_both_may_use(m)
    m.refuse(P.refusal_layer("land", "ninja"), cx, cy)
    assert not P.valid_spots(m, "ninja")[cy, cx]
    assert not P.valid_spots(m, "ace")[cy, cx]


def _executor(model):
    """Just enough of an Executor for _learn_blocked / _learn_accepted."""
    ex = S.Executor.__new__(S.Executor)
    ex.m = model
    ex.g = SimpleNamespace(hero="quincy")
    ex.learned_blocks = 0
    return ex


def test_executor_learns_and_forgets_in_the_tower_layer():
    m = tricky_tracks()
    cx, cy = a_cell_both_may_use(m)
    ex = _executor(m)
    ex._learn_blocked("ace", cx, cy)
    assert m.refused_mask("land@ace")[cy, cx]
    assert not m.refused_mask("land").any(), "an ace's refusal went into the shared layer"
    ex._learn_blocked("ninja", cx + 10, cy)
    assert m.refused_mask("land")[cy, cx + 10]
    fx, fy = m.cell_to_frac(cx, cy)
    ex._learn_accepted("ace", SimpleNamespace(x=fx, y=fy))
    assert not m.refused_mask("land@ace")[cy, cx], "a standing ace did not clear its own refusal"


def test_tower_layer_survives_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        old = maplearn.DATA
        maplearn.DATA = Path(tmp)
        try:
            m = MapModel("unit", PF)
            m.refuse("land@ace", 30, 30)
            m.refuse("land", 60, 60)
            m.save()
            again = MapModel.load("unit", PF)
            assert again.refused_mask("land@ace").sum() == 9
            assert again.refused_mask("land").sum() == 9
        finally:
            maplearn.DATA = old


def test_tricky_tracks_drops_its_old_refusals_once():
    with tempfile.TemporaryDirectory() as tmp:
        old = maplearn.DATA
        maplearn.DATA = Path(tmp)
        try:
            m = MapModel(MAP, PF)
            m.refuse("land", 40, 40)
            m.save()
            loaded = MapModel.load(MAP, PF)
            assert not loaded.refused_mask("land").any(), "Tricky Tracks kept its old refusals"
            loaded.refuse("land", 40, 40)
            loaded.save()
            assert MapModel.load(MAP, PF).refused_mask("land").sum() == 9, "a new refusal was dropped"
        finally:
            maplearn.DATA = old


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
