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
    # Where it collapsed. Water Park's two slides alternate every round
    # (AlternateRoundSplitter, roundsPerPath 0: odd rounds take Path2, even
    # rounds Path1, the rule read off Last Resort's frames). This board is
    # weak on Path1 only: the even rounds 28 and 30 are crisis rounds, and
    # odd round 29 rates 1.7 on Path2. It was a crisis here only while every
    # round was rated on both slides at once (dynamic-map audit 2026-11-12,
    # item 2); against Path1 it still would be.
    for rnd in (28, 30):
        assert f.is_crisis(f.margin(WATER_PARK_R28, rnd)), rnd
    assert not f.is_crisis(f.margin(WATER_PARK_R28, 29))
    path1 = [k for k in range(len(f.track.scenarios))
             if f.track.paths[f.track.scenarios[k][0]]["name"] == "Path1"]
    lots = [D.round_lots("easy", 29, f.track, k) for k in path1]
    assert f.is_crisis(D.lots_margin(f.stations(WATER_PARK_R28), f.track, lots))


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


def test_glacial_trail_towers_count_their_frozen_rounds():
    # towers freeze 2 rounds in 10 there: 80% uptime, by either map name
    assert D.tower_uptime("Glacial Trail") == D.tower_uptime("glacialtrail") == 0.8
    assert D.tower_uptime("Water Park") == 1.0
    if not D.available():
        return
    # the same defence rated with towers off a fifth of the time keeps a
    # fifth less margin (Glacial Trail Medium was lost at round 25 with most
    # boomerangs frozen while the model rated it safe)
    f = RoundForecast("Water Park", "easy")
    always_on = f.margin(WATER_PARK_R28, 20)
    f.track.uptime = 0.8
    frozen = f.margin(WATER_PARK_R28, 20)
    assert abs(frozen / always_on - 0.8) < 0.05, (always_on, frozen)


def test_glacial_trail_freeze_phase_from_the_placement_round():
    # Glacial Trail ABR 2026-11-09: bought in round 22, free in 30, frozen in 31
    assert not D.frozen_in("Glacial Trail", 22, 30)
    assert D.frozen_in("Glacial Trail", 22, 31) and D.frozen_in("glacialtrail", 22, 32)
    assert not D.frozen_in("Glacial Trail", 22, 33)
    assert D.frozen_in("Glacial Trail", 22, 41) and D.frozen_in("Glacial Trail", 15, 25)
    # no freeze elsewhere, nor with a round unknown
    assert not D.frozen_in("Water Park", 22, 31)
    assert not D.frozen_in("Glacial Trail", None, 31) and not D.frozen_in("Glacial Trail", 22, None)


def test_a_defence_bought_in_one_round_is_rated_frozen_together():
    """Glacial Trail ABR 2026-11-09: the whole Fast Track opening was bought
    in round 22 and froze together in round 31, which the average uptime had
    rated 0.81. With placement rounds known, that round is rated with no
    tower awake, the rounds around it at full strength."""
    if not D.available():
        return
    f = RoundForecast("Water Park", "easy")
    full = {r: f.margin(WATER_PARK_R28, r) for r in (20, 21)}
    f.map_name = "Glacial Trail"          # Water Park's track, Glacial Trail's freeze
    f.track.uptime = D.tower_uptime("Glacial Trail")
    # bought in round 12: awake in round 20 (8 rounds on), in ice in 21 and 22
    one_round = [N(**{**t.__dict__, "placed_round": 12}) for t in WATER_PARK_R28]
    assert abs(f.margin(one_round, 20) - full[20]) < 0.05 * full[20]    # all awake: full strength
    assert f.margin(one_round, 21) < CRISIS_MARGIN                         # all in ice
    assert f.leaks(one_round, [21], 1.0) > f.leaks(WATER_PARK_R28, [21], 1.0)
    # bought over two rounds: half the defence still stands in round 21
    staggered = [N(**{**t.__dict__, "placed_round": 12 + i % 2}) for i, t in enumerate(WATER_PARK_R28)]
    assert f.margin(one_round, 21) < f.margin(staggered, 21) <= full[21]
    # a tower without a known placement round: the old average for everyone
    unknown = one_round[:-2] + [WATER_PARK_R28[-2], one_round[-1]]
    assert abs(f.margin(unknown, 20) - 0.8 * full[20]) < 0.08 * full[20]


def test_crisis_threshold():
    assert RoundForecast.is_crisis(CRISIS_MARGIN - 0.01)
    assert not RoundForecast.is_crisis(CRISIS_MARGIN)
    assert not RoundForecast.is_crisis(None)


class Leaky(RoundForecast):
    """A forecast that rates every round `margin` and whose simulation says
    each costs `lost` lives (no map model is loaded)."""

    def __init__(self, lost, margin=0.58):
        super().__init__("Water Park", "hard")
        self.lost, self.m = lost, margin

    def margin(self, towers, rnd):
        return self.m

    def leaks(self, towers, rounds, strength, per_round=False):
        return {r: self.lost for r in rounds} if per_round else self.lost * len(rounds)


def test_a_round_that_would_cost_half_the_lives_is_a_crisis():
    """Pat's Pond ABR: round 54 rated 0.58 with 74 lives left took them all."""
    assert RoundForecast.is_crisis(0.58, lives=74, leak=40)
    assert not RoundForecast.is_crisis(0.58, lives=150, leak=40)      # a dent, not the game
    assert not RoundForecast.is_crisis(1.2, lives=10, leak=100)       # rated to hold: the margin rules
    assert not RoundForecast.is_crisis(0.58, lives=None, leak=40)     # lives unknown: the margin alone
    assert not RoundForecast.is_crisis(0.58, lives=74, leak=None)
    # the leak is only simulated for a round the model expects to leak
    f = Leaky(40)
    assert f.lethal_leak([], 54, 0.58) == 40
    assert f.lethal_leak([], 54, 1.0) is None and f.lethal_leak([], 54, None) is None


def test_danger_round_counts_a_lethal_leak():
    from btd6bot import reinforce as R
    ex = N(g=N(towers={}))
    assert R.danger_round(Leaky(40), ex, 54, lives_dropped=False, lives=74) == 54
    assert R.danger_round(Leaky(40), ex, 54, lives_dropped=False, lives=150) is None
    # a fake forecast without lethal_leak is judged by the margin alone
    fake = N(margin=lambda towers, r: 0.58)
    assert R.danger_round(fake, ex, 54, lives_dropped=False, lives=74) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
