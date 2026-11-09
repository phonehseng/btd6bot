"""Forgetting learned refusals that real placements contradict (no game needed).

Backlog item 15 (2026-11-03): before strategy.refusals_are_trusted, runs of
clicks the game ignored were learned as bad ground, and nothing ever took a
refusal back - Spice Islands had 55% of its legal land marked refused.
  * MapModel.unrefuse clears the square under a tower that now stands there;
  * forget_contradicted_refusals drops refusals inside every spot_stats
    bucket where a tower of that surface really stood, and nothing else;
  * the clean-up runs once per map on load and is remembered after a save.
Run: python tests/test_refusal_cleanup_offline.py"""
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import maplearn  # noqa: E402
from btd6bot.maplearn import SPOT_BUCKET, MapModel  # noqa: E402

PF = (0.0, 0.0, 1.0, 1.0)


def test_unrefuse_clears_square():
    m = MapModel("unit", PF)
    m.refuse("land", 20, 20)              # 3x3 refused around (20, 20)
    assert m.refused_mask("land").sum() == 9
    assert m.unrefuse("land", 21, 21) == 4  # overlap of the two 3x3 squares
    assert m.refused_mask("land").sum() == 5
    assert m.unrefuse("water", 21, 21) == 0  # no water layer: nothing to do
    print("ok unrefuse clears only the tower's square")


def test_cleanup_uses_tower_surface():
    m = MapModel("unit", PF)
    m.refuse("land", 41, 41)              # inside bucket (10, 10)
    m.refuse("land", 81, 81)              # bucket (20, 20): no tower ever stood there
    m.refuse("water", 41, 41)
    m.spot_stats = {"sniper|10|10": [1.0, 1]}   # a land tower stood in bucket (10, 10)
    cleared = m.forget_contradicted_refusals()
    lo, hi = 10 * SPOT_BUCKET, 11 * SPOT_BUCKET
    assert cleared == 9, cleared
    assert not m.refused_mask("land")[lo:hi, lo:hi].any()
    assert m.refused_mask("land")[80:83, 80:83].all(), "uncontradicted refusal must stay"
    assert m.refused_mask("water").sum() == 9, "a land tower says nothing about water"
    print("ok clean-up drops only contradicted refusals, per surface")


def test_cleanup_runs_once_per_map():
    with tempfile.TemporaryDirectory() as tmp:
        old = maplearn.DATA
        maplearn.DATA = Path(tmp)
        try:
            m = MapModel("unit", PF)
            m.refuse("land", 41, 41)
            m.spot_stats = {"sniper|10|10": [1.0, 1]}
            m.save()
            # an old file: written before the clean-up existed
            loaded = MapModel.load("unit", PF)
            assert loaded.refusal_cleanup == maplearn.REFUSAL_CLEANUP
            assert not loaded.refused_mask("land").any()
            # after a save, a new refusal in the same bucket is kept on load
            loaded.refuse("land", 41, 41)
            loaded.save()
            again = MapModel.load("unit", PF)
            assert again.refused_mask("land").sum() == 9
        finally:
            maplearn.DATA = old
    print("ok clean-up runs once per map and is remembered")


def test_listed_map_drops_its_refusals_once():
    """REFUSAL_RESETS (Mesa, 2026-11-09): every refusal learned on a listed
    map is dropped on the first load, then new ones are kept; maps not
    listed keep theirs."""
    with tempfile.TemporaryDirectory() as tmp:
        old = maplearn.DATA
        maplearn.DATA = Path(tmp)
        try:
            for name in ("Mesa", "Monkey Meadow"):
                m = MapModel(name, PF)
                m.refuse("land", 41, 41)
                m.refuse("land", 81, 81)
                m.save()
            mesa = MapModel.load("Mesa", PF)
            assert not mesa.refused_mask("land").any(), "Mesa's old refusals must go"
            assert mesa.refusal_reset == maplearn.REFUSAL_RESETS["mesa"]
            mesa.refuse("land", 41, 41)       # learned after the fix
            mesa.save()
            assert MapModel.load("Mesa", PF).refused_mask("land").sum() == 9, \
                "a refusal learned after the reset must stay"
            meadow = MapModel.load("Monkey Meadow", PF)
            assert meadow.refused_mask("land").sum() == 18, "an unlisted map keeps its refusals"
        finally:
            maplearn.DATA = old
    print("ok a listed map drops its refusals once")


if __name__ == "__main__":
    test_unrefuse_clears_square()
    test_cleanup_uses_tower_surface()
    test_cleanup_runs_once_per_map()
    test_listed_map_drops_its_refusals_once()
    print("ALL OK")
