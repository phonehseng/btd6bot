"""Bazaar CHIMPS: the boomerang sees both lanes, the third dart keeps round 7.

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

The build now keeps the third dart on the cell that held round 7 and gives
the middle cell to the boomerang, which is bought before round 8
(strategies/maps/bazaar_chimps.yaml, "Spots again, 2026-11-13").

Checked here:
  * the lost boomerang spot sees less than LOST_UNITS of the lower lane;
  * the build's x3 stands on the cell that held round 7 live (ROUND_7_CELL);
  * the build's r1 sees at least BOTH_UNITS of either lane;
  * round 12, played on its own lane on the board the plan has bought by
    then, rates higher than on the lost board, and no round from 6 to 14
    rates lower.

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
BOTH_UNITS = 50.0       # the boomerang in the middle sees at least this much of either lane
# Where the third dart stood in the games whose three darts held round 7
# (journals 20261112_225338 and 20261113_064858, place events).
ROUND_7_CELL = (0.115, 0.487)
OPENING = range(6, 15)  # the rounds before the hero is bought


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
    """The build with x3 and r1 back where they stood in the lost game."""
    d = copy.deepcopy(_build())
    for tid, at in LOST_SPOTS.items():
        _place(d, tid)["at"] = list(at)
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


def test_the_boomerang_sees_both_lanes():
    boomerang = _place(_build(), "r1")
    cover = _cover(boomerang["kind"], boomerang["at"])
    assert min(cover) >= BOTH_UNITS, (boomerang["at"], cover)


def test_the_opening_rates_no_worse_and_round_12_better():
    new, old = _margins(False), _margins(True)
    assert new[LOST_ROUND] > old[LOST_ROUND], (new[LOST_ROUND], old[LOST_ROUND])
    worse = {r: (old[r], new[r]) for r in OPENING if new[r] < old[r]}
    assert not worse, worse


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
