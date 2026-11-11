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
        return rated if self.trust == 1.0 else {r: m * self.trust for r, m in rated.items()}

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


def test_clean_weak_rounds_raise_trust_slowly():
    """X Factor Impoppable (2026-11-10): rounds rated 0.09-0.98 all held with
    nothing leaking. Each clean round raises the trust by at most
    TRUST_STEP, up to TRUST_CEILING, so a run of them lifts a 0.46 round
    over 0.9 - reinforce stops starving the plan - but never past the cap."""
    f = F.RoundForecast("X Factor", "impoppable")
    assert f.observe_clean(0.46, 0, depth=0.0)
    assert abs(f.trust - F.TRUST_STEP) < 1e-9, "one round moves it one step"
    for _ in range(20):
        f.observe_clean(0.46 * f.trust, 0, depth=0.1)   # what the bot is told
    assert abs(f.trust - F.TRUST_CEILING) < 1e-9
    assert 0.46 * f.trust > 0.9


def test_clean_rounds_never_lift_past_what_was_held():
    """A round rated 0.9 that held only shows the defence had 1/0.9 of the
    model's strength - the trust stops there, not at the step."""
    f = F.RoundForecast("X Factor", "impoppable")
    assert f.observe_clean(0.9, 0)
    assert abs(f.trust - F.HELD_MARGIN / 0.9) < 1e-9


def test_no_evidence_no_change():
    f = F.RoundForecast("X Factor", "impoppable")
    assert not f.observe_clean(None, 0), "an unrated round says nothing"
    assert not f.observe_clean(1.4, 0), "a round rated safe that held is expected"
    assert not f.observe_clean(0.5, 1), "lives lost: not a clean hold"
    assert not f.observe_clean(0.5, 0, depth=0.9), "bloons came close to the exit"
    assert f.trust == 1.0


def test_a_leak_takes_back_the_raised_trust():
    """Once the defence leaks again - even in a round rated under 1 - the
    extra trust is gone and the model's own rating stands."""
    f = F.RoundForecast("X Factor", "impoppable")
    f.observe_clean(0.5, 0)
    assert f.trust > 1.0
    assert f.observe_leak(0.7, 1)
    assert f.trust == 1.0
    # and a leak in a round told safe under raised trust falls below 1
    f.trust = 2.0
    assert f.observe_leak(1.2, 1)
    assert abs(f.trust - F.LEAKED_MARGIN * 2.0 / 1.2) < 1e-9


def test_real_margins_scale_up_too():
    f = F.RoundForecast("X Factor", "impoppable")
    f._ready = lambda: True
    f._rate = lambda towers, rounds, rate: {r: 0.4 for r in rounds}
    f.trust = 2.0
    assert all(abs(m - 0.8) < 1e-9 for m in f.margins([], [87, 88]).values())


def test_match_hook_trusts_more_after_a_clean_round():
    class Shell:
        _margins = {87: 0.46}
        _round_lost = 0
        depths = [{"deepest": 0.0, "deep_share": 0.0, "looks": 1}]
        forecast = F.RoundForecast("X Factor", "impoppable")

    s = Shell()
    M.Match._trust_model_more(s, 87)
    assert s.forecast.trust > 1.0
    s2 = Shell()
    s2.forecast = F.RoundForecast("X Factor", "impoppable")
    s2._round_lost = 1
    M.Match._trust_model_more(s2, 87)
    assert s2.forecast.trust == 1.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} checks pass")
