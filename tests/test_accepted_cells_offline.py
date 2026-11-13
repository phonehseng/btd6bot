"""A cell the game accepted a tower on stays legal for the small towers.

Case 20261112_194415_Ravine_magic_only (2026-11-12 19:31, lost round 60).
Ravine's middle spot (cell 70, 82; screen 0.377, 0.743) is blocked in the map
file, but the game takes a ninja there: a probe found it (Executor.
_probe_spot) and MapModel.accept wrote it down. placement.valid_spots then
threw the cell out again - one allowed cell among blocked ones fails the
footprint check - so the plan could not name the spot and every game had to
find it with a new probe, one per tower kind. On that day the 13 maps with
accepted cells held 32 of them, and 1 was legal.

Checked here on Ravine's game geometry: the accepted cell is legal for a
ninja, not for the bigger wizard, druid and super (the game refused a wizard
and a druid on that very cell), not once it is refused, and not under a
tower that already stands there.

Run: python tests/test_accepted_cells_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from btd6bot import mapgeom as G  # noqa: E402
from btd6bot import placement as P  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

MAP = "Ravine"
SPOT = (0.377, 0.743)       # where ninja1 stood in the lost game (its journal)
SMALL = ("ninja", "dart")
BIGGER = ("wizard", "druid", "super")


def _model():
    """Ravine from the game's geometry alone, nothing learned."""
    m = MapModel(MAP, LAYOUTS["16:10"]["playfield"])
    geom = G.load(MAP)
    assert geom is not None, "no geometry for Ravine"
    G.apply(m, geom)
    return m


def test_the_spot_is_blocked_in_the_map_file():
    m = _model()
    cx, cy = m.frac_to_cell(*SPOT)
    for kind in SMALL + BIGGER:
        assert not P.valid_spots(m, kind)[cy, cx], kind


def test_an_accepted_cell_is_legal_for_small_towers_only():
    m = _model()
    cx, cy = m.frac_to_cell(*SPOT)
    before = {kind: P.valid_spots(m, kind) for kind in SMALL + BIGGER}
    m.accept("land", cx, cy)
    for kind in SMALL:
        assert P.footprint_radius(kind) <= P.SHARED_REFUSAL_RADIUS, kind
        after = P.valid_spots(m, kind)
        assert after[cy, cx], kind
        # nothing else changes: the cell's neighbours stay blocked
        assert int(after.sum()) == int(before[kind].sum()) + 1, kind
    for kind in BIGGER:
        assert P.footprint_radius(kind) > P.SHARED_REFUSAL_RADIUS, kind
        assert (P.valid_spots(m, kind) == before[kind]).all(), kind


def test_a_refusal_or_a_standing_tower_still_rules_the_cell_out():
    m = _model()
    cx, cy = m.frac_to_cell(*SPOT)
    m.accept("land", cx, cy)
    assert not P.valid_spots(m, "ninja", towers=[(cx, cy, "ninja", None)])[cy, cx]
    m.refuse("land", cx, cy)
    assert not P.valid_spots(m, "ninja")[cy, cx]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
