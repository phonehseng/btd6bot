"""Luminous Cove CHIMPS: the opening dart sees both alternating lanes.

Why
---
Luminous Cove sends its bloons down one of two mirrored lanes, a different
one each round. Both circle the heart pond; one then leaves by the bottom
left, the other by the bottom right. The guide build's first game
(2026-11-12 16:04, case 20261112_160448_LuminousCove_chimps) had its
opening dart on the right strip at 0.623, 0.845, in reach of the right exit
only. Rounds 6 and 8 left by the left exit: the boat held them alone, round
6 got 99% along the route and round 8 leaked two blues - a lost game on
CHIMPS' one life.

The guide puts the dart "closer to the darker bottom path", the village
"next to the glue, covering the dart". The left strip's top fits both: it
lies between the lower-left pool ring (one lane on its way in) and the
bottom path (the other lane on its way out).

Checked here, on the build as written:
  * the dart has route in range on BOTH lanes, at least MIN_LANE_UNITS on
    the worse one (the lost game's spot: none on one of them);
  * the village has the dart, the druid and the sniper inside its range
    (Jungle Drums for the Crossbow Master; the Radar for the druid's camo
    leads on round 53 and the sniper's camo DDTs on round 90).

The spots' legality, the threat replay and the plan's cost are checked for
every guide build in tests/test_chimps_intermediate_guides_offline.py.

Run: python tests/test_luminouscove_chimps_lanes_offline.py (no game)."""
import logging
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pin_spots  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

BUILD = ROOT / "strategies" / "maps" / "luminouscove_chimps.yaml"
MAP, MODE = "Luminous Cove", "chimps"
# Route a base dart must have in range on its worse lane: a blue bloon
# crosses 30 units in about a second, one dart's reload.
MIN_LANE_UNITS = 30.0
# The spot of the lost game, kept to show the check tells the two apart.
LOST_GAME_DART = (0.623, 0.845)


def _places():
    """{tower id: its `place` step} of the build's plan."""
    build = yaml.safe_load(BUILD.read_text(encoding="utf-8"))
    return {st["id"]: st for st in build["plan"] if st["do"] == "place"}


def _lane_units(at, kind="dart", tiers=(0, 0, 0)):
    """Route in the tower's range on each of the map's lanes, in world
    units (0 for a lane it does not reach), as the damage model sees it."""
    forecast = RoundForecast(MAP, MODE)
    assert forecast._ready(), "no damage model for the map"
    tower = SimpleNamespace(tid="t", kind=kind, tiers=tiers, x=at[0], y=at[1])
    stations = forecast.stations([tower])
    if not stations:
        return [0.0] * len(forecast.track.paths)
    return [0.0 if zone is None else zone.length for zone in stations[0].zones]


def test_the_dart_reaches_both_lanes():
    units = _lane_units(_places()["x1"]["at"])
    assert len(units) == 2, units
    assert min(units) >= MIN_LANE_UNITS, units


def test_the_lost_games_spot_fails_the_same_check():
    assert min(_lane_units(LOST_GAME_DART)) == 0.0


def test_the_village_covers_dart_druid_and_sniper():
    places = _places()
    pin = pin_spots.Pinner(MAP, MODE)
    village_range = pin_spots.buffer_range("village")

    def world(tid):
        return pin.world(pin.model.frac_to_cell(*places[tid]["at"]))

    for tid in ("x1", "d1", "s1"):
        gap = math.dist(world("v1"), world(tid))
        assert gap <= village_range, (tid, round(gap, 1), village_range)


if __name__ == "__main__":
    import inspect
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                print("FAIL", fname, repr(e)[:400])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
