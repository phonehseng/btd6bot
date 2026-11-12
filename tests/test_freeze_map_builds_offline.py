"""On a map that freezes towers only builds written for it fit.

Glacial Trail Reverse (2026-11-11 23:34, loss case 20261111_233448): with
glacialtrail_medium struck out after three Reverse losses the planner fell
back to military_heli_sniper, a general build, which lost round 25 in 2.5
minutes. General builds won 1 Glacial Trail game of 11."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import planner as P  # noqa: E402


def spec(**kw):
    base = dict(id="x", modes=["reverse", "medium"], towers={"dart": [0, 2, 3]})
    base.update(kw)
    return P.StrategySpec.from_any(base)


def test_general_builds_do_not_fit_glacial_trail():
    assert not P._strategy_fits(spec(), "Glacial Trail", "intermediate", "reverse")
    assert P._strategy_fits(spec(maps=["Glacial Trail"]), "Glacial Trail", "intermediate", "reverse")


def test_other_maps_are_unchanged():
    assert not P._towers_freeze("Monkey Meadow")
    assert P._towers_freeze("Glacial Trail") and P._towers_freeze("Glacial Trail reverse")


if __name__ == "__main__":
    test_general_builds_do_not_fit_glacial_trail()
    test_other_maps_are_unchanged()
    print("all tests passed")
