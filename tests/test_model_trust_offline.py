"""The forecast trusts the damage model less once a round it rated safe leaks
(no game needed).

Before: Glacial Trail Apopalypse (2026-11-10 20:08) lost 102 lives in round
24, which the model had rated 8.72; the following rounds still read 3.3-11,
so nothing was reinforced, and round 33 (rated 11.07) took the last 42 lives
with $11,056 in the bank. Now a leak in a round rated m >= 1 scales every
later margin (and every simulated leak's strength) by LEAKED_MARGIN / m.
Run: python tests/test_model_trust_offline.py"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import forecast as F  # noqa: E402
from btd6bot import match as M  # noqa: E402

logging.getLogger("forecast").setLevel(logging.ERROR)
logging.getLogger("match").setLevel(logging.ERROR)


class FixedForecast(F.RoundForecast):
    """A RoundForecast whose model always rates every round `raw` and
    records the strength leaks() asks the simulation for - no map data."""

    def __init__(self, raw):
        super().__init__("Glacial Trail", "apopalypse")
        self.raw = raw
        self.asked_strength = None

    def _ready(self):
        return True

    def _rate(self, towers, rounds, rate):
        return {r: rate(None, r) for r in rounds}

    def margins(self, towers, rounds, iterations=9):
        # the parent's scaling, around a fixed raw rating
        rated = {r: self.raw for r in rounds}
        return rated if self.trust >= 1.0 else {r: m * self.trust for r, m in rated.items()}

    def leaks(self, towers, rounds, strength, per_round=False):
        self.asked_strength = strength * self.trust
        return {r: 0 for r in rounds} if per_round else 0


def test_leak_in_a_safe_round_lowers_trust():
    f = F.RoundForecast("Glacial Trail", "apopalypse")
    assert f.trust == 1.0
    assert f.observe_leak(8.72, 102)
    assert abs(f.trust - F.LEAKED_MARGIN / 8.72) < 1e-9
    # round 33 was rated 11.07 raw: it now reads under 1.5 (weak: reinforce)
    assert 11.07 * f.trust < 1.5


def test_foreseen_or_unrated_leaks_change_nothing():
    f = F.RoundForecast("Ravine", "apopalypse")
    assert not f.observe_leak(None, 61), "the Fast Track opening has no rating"
    assert not f.observe_leak(0.7, 20), "a round rated under 1 was expected to leak"
    assert not f.observe_leak(3.0, 0), "no lives lost"
    assert f.trust == 1.0


def test_trust_only_falls_and_has_a_floor():
    f = F.RoundForecast("Glacial Trail", "apopalypse")
    f.observe_leak(3.0, 10)
    first = f.trust
    # a second leak in a round the bot was told is 1.2 (raw 1.2 / trust)
    assert f.observe_leak(1.2, 5)
    assert f.trust < first
    assert abs(f.trust - F.LEAKED_MARGIN * first / 1.2) < 1e-9
    f.observe_leak(1000.0, 1)
    assert f.trust >= F.TRUST_FLOOR


def test_margins_and_leaks_use_the_trust():
    f = FixedForecast(4.0)
    assert f.margin([], 30) == 4.0
    f.observe_leak(4.0, 30)
    assert abs(f.margin([], 30) - F.LEAKED_MARGIN) < 1e-9
    f.leaks([], [30], 0.5)
    assert abs(f.asked_strength - 0.5 * F.LEAKED_MARGIN / 4.0) < 1e-9


def test_real_margins_are_scaled():
    """RoundForecast.margins itself (not the test double) scales the raw
    ratings the model returns."""
    f = F.RoundForecast("Glacial Trail", "apopalypse")
    f._ready = lambda: True
    f._rate = lambda towers, rounds, rate: {r: 5.0 for r in rounds}
    assert f.margins([], [10, 11]) == {10: 5.0, 11: 5.0}
    f.trust = 0.2
    got = f.margins([], [10, 11])
    assert all(abs(m - 1.0) < 1e-9 for m in got.values())


def test_match_hook_rerates_after_the_leak():
    """Match._distrust_model asks the forecast, then rates the round again."""
    class Shell:
        _margins = {24: 8.72}
        _t_reinforce = 99.0
        forecast = F.RoundForecast("Glacial Trail", "apopalypse")
        rerated = []

        def _forecast_round(self, rnd):
            self.rerated.append(rnd)

    s = Shell()
    M.Match._distrust_model(s, 24, 102)
    assert s.forecast.trust < 1.0
    assert s.rerated == [24]
    assert s._t_reinforce == 0.0
    # a leak the model foresaw leaves everything alone
    s2 = Shell()
    s2.forecast = F.RoundForecast("Glacial Trail", "apopalypse")
    s2.rerated = []
    s2._margins = {24: 0.6}
    M.Match._distrust_model(s2, 24, 10)
    assert s2.forecast.trust == 1.0 and s2.rerated == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} checks pass")
