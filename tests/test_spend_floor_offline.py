"""Idle cash under $800 is spent in a crisis whose look-ahead is weak
(Match.spend_floor), by the damage model's own choice only.

Muddy Puddles Impoppable, 2026-11-11 21:35 (case
20261111_213643_MuddyPuddles_impoppable): Play was held before round 7,
rated 0.35, "spending the $506 first" - and the spending never looked at
$506, which was under the $800 floor. The one life went in round 7."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot.match import Match  # noqa: E402


def test_the_floor_drops_only_for_a_weak_crisis():
    assert Match.spend_floor(weak=True, crisis=True) == M.CRISIS_HOLD_MIN_CASH
    # a crisis the model has no weak look-ahead for, or a weak look-ahead
    # without a crisis: the plan's savings stay untouched
    for weak, crisis in ((False, True), (True, False), (False, False)):
        assert Match.spend_floor(weak, crisis) == M.IDLE_SPEND_MIN_CASH


def test_the_lost_games_cash_is_over_the_crisis_floor():
    # the $506 of the lost game is now looked at, and the hold's own
    # minimum is the same sum: what Play waits for can be spent
    assert M.CRISIS_HOLD_MIN_CASH < 506 < M.IDLE_SPEND_MIN_CASH
    assert 506 > Match.spend_floor(weak=True, crisis=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
