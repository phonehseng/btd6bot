"""Spice Islands CHIMPS: the boat sees camo before round 42's camo rainbows.

Why
---
The build (strategies/maps/spiceislands_chimps.yaml) lost live at round 42 on
2026-11-07 (logs/bot.log 14:51:45-14:51:53). Round 42 sends 6 regrow
rainbows and then 5 camo rainbows; camo yellows from them reached the exit.
The Aircraft Carrier had been bought at round 39, the village after it at
round 41, and its Radar Scanner was not affordable before round 42: only the
Night Vision sniper saw camo. The fix moved the village and Radar Scanner
ahead of the Carrier.

The same investigation asked whether the bot's route model misses a lane of
this map (the bloon watch saw bloons at most 61% along the route in a round
that leaked). It does not: the map is one path, and only part of it is on
screen, which is what caps the watch's depth.

Offline checks:
  * at CHIMPS prices and income (test_chimps_builds_offline.plan_timeline)
    the Radar Scanner stands by round 36 - the first camo round after the
    Destroyer that the old order rated under 0.1 - and before the Carrier;
  * the map's route model is one route (data/map_geometry/spiceislands.json
    has one path) whose on-screen stretch ends near 0.83 of its length: a
    bloon at the exit shows as ~83% along the route, not 100%.
Run: python tests/test_spiceislands_camo_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import strategy as S                  # noqa: E402
from btd6bot.dps_model import Track                # noqa: E402
from test_chimps_builds_offline import plan_timeline  # noqa: E402

STRATEGY, MAP, MODE = "spiceislands_chimps", "Spice Islands", "chimps"
RADAR_BY = 36       # rounds 36, 37 (camo greens, whites) and 42 (camo rainbows)


def _stands_from(timeline, tid, what):
    """The round a plan step stands from (affordable by the end of the round before)."""
    for step, _, rnd in timeline:
        if step.get("id") == tid and (step.get("to") or step["do"]) == what:
            return rnd + 1
    raise AssertionError(f"{tid} {what} is not in the plan")


def test_radar_scanner_stands_before_the_carrier_and_round_36():
    timeline = plan_timeline(S.load_all()[STRATEGY], MODE)
    radar = _stands_from(timeline, "v1", "0-2-0")
    carrier = _stands_from(timeline, "b1", "4-2-0")
    assert radar <= RADAR_BY, f"Radar Scanner stands from round {radar}"
    assert radar < carrier, f"Radar Scanner (round {radar}) after the Carrier (round {carrier})"


def test_route_model_is_the_one_path_and_its_exit_is_on_screen_at_83_percent():
    track = Track(MAP)
    assert len(track.paths) == 1, [p["name"] for p in track.paths]
    p = track.paths[0]
    frac = p["dist"] / p["length"]
    seen = frac[p["hittable"]]
    assert 0.10 < seen.min() < 0.20 and 0.78 < seen.max() < 0.88, (seen.min(), seen.max())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
