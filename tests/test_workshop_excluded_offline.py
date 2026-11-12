"""chimps_ninja_sun does not play Workshop.

Workshop (Expert): after round 39 the MOAB-class bloons drop down a chute
and ride only the last stretch of the conveyor belt, and the tables beside
the belt block sight. chimps_ninja_sun places its towers by role and track
segment; they do not stand where that stretch is in reach. It lost Workshop
Impoppable four times out of four: round 40 on 2026-11-10 18:11, 2026-11-11
08:31 and 17:32, and round 57 on 2026-11-12 05:21 (loss case
20261112_052113_Workshop_impoppable: blimp check "21 units of track ...
0.0x" at round 40 and 0.2x in rounds 52-57, every round from 50 rated
0.33-0.37, and $12,190 saved for the plan's Sun Avatar meanwhile).

The map's medals came from its own builds (strategies/maps/workshop_*.yaml),
which stand their towers above the belt at the chute's exit and in the exit
pocket. So the general build lists Workshop in planner.excluded_maps and
the planner offers it no Workshop game; an Impoppable map build is backlog
98.

Run: python tests/test_workshop_excluded_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

MAP = "Workshop"


def _spec(sid):
    """The planner's spec of a strategy, as runner.planner_specs builds it."""
    s = S.load_all()[sid]
    return PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))


def test_the_general_impoppable_build_excludes_workshop():
    assert MAP in _spec("chimps_ninja_sun").excluded_maps


def test_workshops_own_builds_still_name_the_map():
    """The exclusion is the general build's alone: the map builds that won
    Workshop's medals keep the map."""
    for sid in ("workshop_medium", "workshop_abr", "workshop_double_hp"):
        spec = _spec(sid)
        assert MAP in spec.maps and MAP not in spec.excluded_maps, sid


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
