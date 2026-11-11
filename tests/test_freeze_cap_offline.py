"""General builds are held to a low p on a map that freezes towers.

Glacial Trail Reverse (2026-11-10 19:52): solo_ace, rated p=0.98 by its
record elsewhere and Double Cash, was played over glacialtrail_medium (the
map's own build for Medium and Reverse, which won Medium an hour before)
and lost round 34 when its one-round opening froze together.
Run: python tests/test_freeze_cap_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import planner as PL  # noqa: E402


def test_general_builds_are_capped_on_glacial_trail():
    general = N(maps=None, achievement=None, extends=None)
    own = N(maps=["Glacial Trail"], achievement=None, extends=None)
    assert PL.freeze_cap(0.98, general, "Glacial Trail") == PL.FREEZE_GENERAL_P
    assert PL.freeze_cap(0.98, own, "Glacial Trail") == 0.98
    assert PL.freeze_cap(0.98, general, "Logs") == 0.98, "maps that never freeze keep their p"
    assert PL.freeze_cap(0.1, general, "Glacial Trail") == 0.1, "a lower p is left alone"


if __name__ == "__main__":
    test_general_builds_are_capped_on_glacial_trail()
    print("ok")
