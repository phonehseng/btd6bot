"""Offline checks for forecast.RoundForecast: the damage model's margin for
the towers standing at a round's start, and when that makes a crisis round.
Run: python tests/test_forecast_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import dps_model as D  # noqa: E402
from btd6bot.forecast import CRISIS_MARGIN, RoundForecast  # noqa: E402

# the Water Park Easy defence lost on 2026-10-22 (from the bot's log, round 28)
WATER_PARK_R28 = [
    N(tid="a1", kind="tack", tiers=(4, 0, 2), x=0.740, y=0.334),
    N(tid="tack1", kind="tack", tiers=(1, 0, 0), x=0.350, y=0.819),
    N(tid="a2", kind="tack", tiers=(1, 0, 2), x=0.601, y=0.905),
    N(tid="b1", kind="tack", tiers=(0, 2, 2), x=0.639, y=0.462),
    N(tid="tack2", kind="tack", tiers=(3, 0, 0), x=0.174, y=0.692),
    N(tid="rv", kind="village", tiers=(0, 2, 0), x=0.521, y=0.606),
    N(tid="nin", kind="ninja", tiers=(3, 0, 2), x=0.751, y=0.283),
    N(tid="hero", kind="hero", tiers=(0, 0, 0), x=0.329, y=0.462),
]


def test_the_lost_water_park_rounds_are_crisis_rounds():
    if not D.available():
        return   # no attack export on this machine
    f = RoundForecast("Water Park", "easy")
    assert not f.is_crisis(f.margin(WATER_PARK_R28, 20))     # held comfortably
    for rnd in (28, 29, 30):                                   # where it collapsed
        assert f.is_crisis(f.margin(WATER_PARK_R28, rnd)), rnd


def test_no_answer_without_towers_map_or_round():
    f = RoundForecast("Water Park", "easy")
    assert f.margin([], 20) is None
    assert f.margin(WATER_PARK_R28[-1:], 20) is None           # the hero alone is not modelled
    assert f.margin(WATER_PARK_R28, None) is None
    assert RoundForecast(None, "easy").margin(WATER_PARK_R28, 20) is None


def test_reverse_games_use_the_map_itself():
    f = RoundForecast("Water Park reverse", "reverse")
    assert (f.map_name, f.reverse) == ("Water Park", True)


def test_a_failure_turns_it_off_quietly():
    f = RoundForecast("No Such Map", "easy")
    assert f.margin(WATER_PARK_R28, 20) is None
    assert f.off


def test_crisis_threshold():
    assert RoundForecast.is_crisis(CRISIS_MARGIN - 0.01)
    assert not RoundForecast.is_crisis(CRISIS_MARGIN)
    assert not RoundForecast.is_crisis(None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
