"""Bazaar CHIMPS: a dart in the middle sees both lanes, the third dart keeps round 7.

Why
---
Bazaar sends its rounds down two lanes in turn: odd rounds along the top,
even rounds along the bottom. On 2026-11-13 06:51 bazaar_chimps lost its one
life in round 12 (case 20261113_065333_Bazaar_chimps), an even round of 15
blues, 10 greens and 5 yellows, with three darts, a boomerang and a druid
standing. The same board had held that round the night before (journal
20261112_225338), so the opening was at its limit, not broken - and two of
its five towers hardly saw the lower lane: the left dart (0.115, 0.487) had
26 units of it in sight and range, the boomerang (0.104, 0.428) 24. Both
stood at the left end of the middle strip, above the lane's turn.

The first answer put that dart in the middle of the strip, between the two
canals, where both lanes run straight past. Its first game (11:06 the same
day, case 20261113_110931_Bazaar_chimps) lost round 7 to one red: round 7 is
played by the three darts alone, and with the third dart on the left end
they had held it in every earlier game. The damage model rated the middle
higher for that round, so its rating cannot choose between the two cells;
the games can.

The second answer kept the third dart on the cell that held round 7 and gave
the middle cell to the boomerang. The boomerang never stood there: its
footprint is a unit wider than a dart's, the middle cell is legal only for
the small towers the game has taken on it, and the executor, finding nothing
legal near the pin, placed the boomerang by the lower lane's exit. Round 9,
a top-lane round, was lost at 14:45 (case 20261113_145054_Bazaar_chimps).

The build now keeps the guide's opening on the cells the game took it on -
the boomerang back on the strip's left end - and buys a fourth dart for the
middle cell after the hero (strategies/maps/bazaar_chimps.yaml, "The
boomerang never stood in the middle"). The opening rule allows no searched
opening here (tools/opening_rule), so the middle dart comes after it.

Checked here:
  * the lost boomerang spot sees less than LOST_UNITS of the lower lane;
  * the build's x3 stands on the cell that held round 7 live (ROUND_7_CELL);
  * the build's x4, a dart, sees at least BOTH_UNITS of either lane;
  * every tower the plan places before the hero is legal on the live map
    for its own footprint, with the towers placed before it standing;
  * no round from 6 to 20, played on its own lane on the board the plan has
    bought by then, rates lower than on the board of the 06:51 game, and
    the rounds after the middle dart rate higher.

Run: python tests/test_bazaar_chimps_opening_offline.py (no game)."""
import copy
import logging
import sys
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
import pin_spots  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

BUILD = ROOT / "strategies" / "maps" / "bazaar_chimps.yaml"
# Where the two towers stood in the lost game (its journal's place events).
LOST_SPOTS = {"x3": (0.115, 0.487), "r1": (0.104, 0.428)}
LOWER_LANE = 1          # Track.scenarios index of the lane the even rounds take
LOST_ROUND = 12
LOST_UNITS = 30.0       # the lost spots saw less of the lower lane than this
BOTH_UNITS = 50.0       # the dart in the middle sees at least this much of either lane
# Where the third dart stood in the games whose three darts held round 7
# (journals 20261112_225338 and 20261113_064858, place events).
ROUND_7_CELL = (0.115, 0.487)
OPENING = range(6, 21)  # the rounds replayed: the opening and the first rounds with the middle dart
MIDDLE_DART = "x4"      # the dart on the middle cell; the lost board had none


@lru_cache(maxsize=None)
def _pinner():
    return pin_spots.Pinner("Bazaar", "chimps")


def _build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def _place(d, tid):
    """The place step of tower ``tid`` in build ``d``."""
    return next(st for st in d["plan"] if st["do"] == "place" and st.get("id") == tid)


def _cover(kind, at):
    """Route in sight and range on each lane for ``kind`` standing at ``at``."""
    pin = _pinner()
    return pin.lane_cover(kind, pin.model.frac_to_cell(*at))


def _lost_build():
    """The build as it stood in the lost game: x3 and r1 on their spots of
    that day, no dart in the middle, the boomerang bought before the druid."""
    d = copy.deepcopy(_build())
    for tid, at in LOST_SPOTS.items():
        _place(d, tid)["at"] = list(at)
    boomerang, druid = _place(d, "r1"), _place(d, "d1")
    plan = [st for st in d["plan"] if st is not boomerang and st.get("id") != MIDDLE_DART]
    plan.insert(plan.index(druid), boomerang)
    d["plan"] = plan
    return d


@lru_cache(maxsize=None)
def _margins(lost):
    """{round: margin} of the opening rounds, each on its own lane."""
    _pinner()                # the live learned map, as the spots were searched
    return O.replay_plan(_lost_build() if lost else _build(), OPENING, live_sight=True)


def test_even_rounds_take_the_lower_lane():
    track = _pinner().setup.track
    assert list(track.scenarios_in(LOST_ROUND)) == [LOWER_LANE], track.scenarios_in(LOST_ROUND)


def test_the_lost_boomerang_spot_hardly_saw_the_lower_lane():
    cover = _cover(_place(_build(), "r1")["kind"], LOST_SPOTS["r1"])
    assert cover[LOWER_LANE] < LOST_UNITS, cover


def test_the_third_dart_stands_where_it_held_round_7():
    """Round 7 is the three darts' round; only this cell has held it live."""
    model = _pinner().model
    dart = _place(_build(), "x3")
    assert model.frac_to_cell(*dart["at"]) == model.frac_to_cell(*ROUND_7_CELL), dart["at"]


def test_the_middle_dart_sees_both_lanes():
    dart = _place(_build(), MIDDLE_DART)
    assert dart["kind"] == "dart", dart
    cover = _cover(dart["kind"], dart["at"])
    assert min(cover) >= BOTH_UNITS, (dart["at"], cover)


def test_the_opening_towers_are_legal_for_their_own_footprint():
    """On the live learned map, as the executor judges a pin: a cell the game
    accepted for a small tower is not legal for a wider one."""
    from btd6bot import placement as PL
    model = _pinner().model
    standing = []
    for step in _build()["plan"]:
        if step["do"] != "place":
            continue
        if step["kind"] == "hero":
            break
        cx, cy = (int(round(v)) for v in model.frac_to_cell(*step["at"]))
        legal = PL.valid_spots(model, step["kind"], None, standing)
        assert legal[cy, cx], (step["id"], step["kind"], step["at"])
        standing.append((cx, cy, step["kind"], None))


def test_no_round_rates_worse_and_the_middle_dart_lifts_some():
    new, old = _margins(False), _margins(True)
    worse = {r: (old[r], new[r]) for r in OPENING if new[r] < old[r]}
    assert not worse, worse
    better = [r for r in OPENING if new[r] > old[r]]
    assert better, "the middle dart lifts no round of the opening"


if __name__ == "__main__":
    import inspect
    O.lower_priority()
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as exc:
                fails += 1
                print("FAIL", name, exc)
    sys.exit(1 if fails else 0)
