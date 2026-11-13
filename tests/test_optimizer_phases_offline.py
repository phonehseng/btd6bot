"""The optimizer on maps whose ground changes by phase (Erosion, 2026-11-12).

Erosion runs in six 18-round phases, each on its own path, and each path is
in reach only from ice that melts when its phase ends; the game destroys the
towers on it then (mapgeom.phase_end, lost_ground). The optimizer planned on
the ground that lasts the whole game - 102 land cells, none near the later
paths - and rated 95 of Erosion Impoppable's rounds under 1.0. Now:

* MapSetup.set_round(r) ranks spots on the ground there in round r that
  lasts until r's phase ends, scored on the routes of those rounds;
* each spot carries `until`, the last phase end its ice survives (None for
  ground that lasts the game), and MapSetup.alive() drops a tower after it;
* the Evaluator rates every round with the towers standing in it, and
  replay_plan (the check of a written plan) destroys them at the melt.

Maps without phases are unchanged (set_round does nothing, until is None).

Run: python tests/test_optimizer_phases_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402


def _erosion():
    return O.MapSetup("Erosion", "impoppable")


def test_erosion_phases_end_every_18_rounds():
    s = _erosion()
    assert s.phased
    assert s.phase_ends(6) == [18, 36, 54, 72, 90]
    assert s.phase_ends(40) == [54, 72, 90]


def test_a_map_without_phases_is_planned_as_before():
    s = O.MapSetup("Monkey Meadow", "impoppable")
    assert not s.phased
    before = [sp.cell for sp in s.ranked_spots("dart")]
    s.set_round(50)
    assert [sp.cell for sp in s.ranked_spots("dart")] == before
    assert all(sp.until is None for sp in s.ranked_spots("dart"))


def test_spots_on_the_first_phase_ice_melt_at_its_end():
    """In round 6 the best ninja spots stand on the first phase's ice, which
    goes at round 18; in round 20 the best ones are on the second phase's."""
    s = _erosion()
    s.set_round(6)
    first = s.ranked_spots("ninja")[:5]
    assert first and all(sp.until == 18 for sp in first), [(sp.cell, sp.until) for sp in first]
    s.set_round(20)
    second = s.ranked_spots("ninja")[:5]
    assert second and all(sp.until == 36 for sp in second), [(sp.cell, sp.until) for sp in second]
    assert {sp.cell for sp in first}.isdisjoint({sp.cell for sp in second})


def test_a_tower_counts_only_while_its_ice_lasts():
    s = _erosion()
    s.set_round(6)
    sp = s.ranked_spots("ninja")[0]
    t = O.Tower("n1", "ninja", sp, (2, 0, 2))
    assert s.alive([t], 18) == [t]
    assert s.alive([t], 19) == []
    ev = O.Evaluator(s, "impoppable")
    assert ev.stations(s.alive([t], 19)) == []


def test_lasting_ground_has_no_end():
    """A sub on water that never freezes over lasts the whole game."""
    s = _erosion()
    s.set_round(6)
    subs = [sp for sp in s.ranked_spots("sub") if sp.until is None]
    assert subs, "some water lasts"
    assert s.spot_until(subs[0].cell, "sub", 6) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
