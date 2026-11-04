"""Raised ground that blocks line of sight is placeable, and towers on it see
over it - no game needed.

Why: on Sunken Columns the column tops (height 50) are sight blockers typed
as land, with the track running over them at height 51. The bot treated
every sight blocker as solid ground, so no tower could stand on the columns,
and from the sunken pit (height 0) the columns hid the whole track: Easy
Primary Only (loss case 20261104_104816) found "none in reach of the track"
for dart and boomerang and leaked 195 lives on rounds 10-11.

Run: python tests/test_high_ground_sight_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapgeom, placement  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]
MAP = "Sunken Columns"


def _model():
    """A fresh Sunken Columns model with its geometry applied (None without it)."""
    geom = mapgeom.load(MAP)
    return None if geom is None else mapgeom.apply(MapModel(MAP, PF), geom)


def _best_cover(m, cells, kind="dart"):
    """The most track weight a `kind` tower sees from any of `cells`."""
    reach = placement.reach_units(kind) / placement.units_per_cell(m)
    weight = m.track_weight()
    return max((placement.visible_cover(m, x, y, reach, weight) for y, x in cells), default=0.0)


def test_column_tops_are_legal_and_see_the_track():
    m = _model()
    if m is None:
        print(f"skip: no {MAP} geometry")
        return
    land = m.scan["land"] == 1
    high = land & (m.ground_height > 1) & m.sight
    assert high.sum() > 500, f"only {int(high.sum())} legal cells on the column tops"
    ys, xs = np.nonzero(high)
    cover = _best_cover(m, list(zip(ys, xs))[::5])
    assert cover > 0, "no dart on the column tops sees any track"


def test_pit_towers_still_see_less():
    """The columns still hide the track from the pit: the best pit spot sees
    less track than the best column-top spot."""
    m = _model()
    if m is None:
        print(f"skip: no {MAP} geometry")
        return
    land = m.scan["land"] == 1
    pit, high = land & (m.ground_height < 1), land & (m.ground_height > 1)
    ys, xs = np.nonzero(pit)
    pit_best = _best_cover(m, list(zip(ys, xs))[::5])
    ys, xs = np.nonzero(high)
    high_best = _best_cover(m, list(zip(ys, xs))[::5])
    assert pit_best < high_best, f"pit {pit_best} >= column tops {high_best}"


def test_blockers_hide_from_lower_ground_only():
    m = _model()
    if m is None:
        print(f"skip: no {MAP} geometry")
        return
    ys, xs = np.nonzero((m.scan["land"] == 1) & (m.ground_height < 1))
    low = placement.sight_blockers(m, xs[0], ys[0])
    ys, xs = np.nonzero((m.scan["land"] == 1) & (m.ground_height > 1))
    high = placement.sight_blockers(m, xs[0], ys[0])
    assert low.sum() > high.sum(), "a tower on the columns is hidden as much as one in the pit"


if __name__ == "__main__":
    test_column_tops_are_legal_and_see_the_track()
    test_pit_towers_still_see_less()
    test_blockers_hide_from_lower_ground_only()
    print("ok")
