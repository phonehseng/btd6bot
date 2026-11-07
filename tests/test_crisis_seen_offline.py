"""A plan_first build lets reinforce past its plan only in a crisis the bloon
watch has seen (Match._crisis_seen), and such a crisis frees the far-threat
hold for reinforce (reinforce.buy_best release_held).

Two live CHIMPS losses of 2026-11-07 set the line:
  * Alpine Run, round 93: the damage model called many rounds crises, each let
    reinforce buy off-plan snipers, and the plan's Glaive Lord never came. The
    bloons never got past 79% of the route (game.log "bloons got N%").
  * Skates, round 75 (twice): rounds before it reached 90-96% of the route,
    and reinforce had "$0" because round 80's ZOMG hold was subtracted.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from btd6bot import match as M          # noqa: E402
from btd6bot import reinforce as R      # noqa: E402


def match_with_depths(depths):
    """A Match with only the bloon-watch summaries _crisis_seen reads."""
    m = M.Match.__new__(M.Match)
    m.depths = [{"round": r, "deepest": d} for r, d in depths]
    return m


# the last rounds before each loss, as the live game.logs recorded them
ALPINE_90S = [(90, 0.76), (91, 0.76), (92, 0.76)]
SKATES_70S = [(72, 0.70), (73, 0.94), (74, 0.90)]


def test_model_only_crisis_is_not_seen():
    # Alpine Run: rated a crisis, bloons never deep - the plan keeps the cash
    assert not match_with_depths(ALPINE_90S)._crisis_seen(dropped=False, crisis=True)


def test_deep_bloons_make_a_crisis_seen():
    # Skates: rated a crisis and round 73's bloons got 94% along the route
    assert match_with_depths(SKATES_70S)._crisis_seen(dropped=False, crisis=True)


def test_deep_bloons_alone_are_not_a_crisis():
    # a deep round with the round being played rated safe is not a crisis
    assert not match_with_depths(SKATES_70S)._crisis_seen(dropped=False, crisis=False)


def test_only_recent_rounds_count():
    old_deep = [(60, 0.95)] + [(60 + i, 0.5) for i in range(1, M.SEEN_CRISIS_ROUNDS + 1)]
    assert not match_with_depths(old_deep)._crisis_seen(dropped=False, crisis=True)


def test_falling_lives_are_always_seen():
    assert match_with_depths([])._crisis_seen(dropped=True, crisis=False)


def test_no_watch_means_nothing_seen():
    assert not match_with_depths([])._crisis_seen(dropped=False, crisis=True)


def test_seen_crisis_releases_the_far_hold():
    """buy_best subtracts ex.held_cash unless release_held is set."""
    seen_cash = []

    def fake_best(ex, forecast, cash, rnd, end_round, lives):
        seen_cash.append(cash)
        return "wait", None

    class Ex:
        held_cash = 72_894      # Skates: round 80's ZOMG answer
        save_goal = None

    real_best, R.best = R.best, fake_best     # only the cash reaching best() matters
    try:
        assert R.buy_best(Ex(), None, 22_050, 75, 100, lives=1) == "wait"
        assert R.buy_best(Ex(), None, 22_050, 75, 100, lives=1, release_held=True) == "wait"
    finally:
        R.best = real_best
    assert seen_cash == [0, 22_050]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
