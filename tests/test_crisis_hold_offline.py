"""Play waits while the damage model expects the coming round to leak and the
bot is still buying (Match._hold_for_crisis). Spillway Medium (2026-11-03)
went into round 40 with $2,329 and lost all 150 lives to its first MOAB.
Offline: a bare Match with a fake forecast and executor."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import match as M   # noqa: E402


class Forecast:
    def __init__(self, margin):
        self.m = margin

    def margin(self, towers, rnd):
        return self.m

    @staticmethod
    def is_crisis(margin):
        return margin < 0.6


class Ex:
    def __init__(self, rules=None):
        self.rules = rules or {}


class G:
    towers = {}


def bare_match(margin, rules=None):
    m = M.Match.__new__(M.Match)
    m.forecast, m.ex, m.g = Forecast(margin), Ex(rules), G()
    m._crisis_hold, m._weak_round, m._t_reinforce = {}, None, 0.0
    m._last_buy = time.time() - 100
    return m


def test_holds_a_round_it_expects_to_leak_and_reinforces_meanwhile():
    m = bare_match(0.48)
    assert m._hold_for_crisis(40, 2329)
    assert m._weak_round == 40            # reinforce.py runs during the hold
    assert m._hold_for_crisis(40, 2329)   # still within the idle allowance


def test_lets_go_once_purchases_stop():
    m = bare_match(0.48)
    assert m._hold_for_crisis(40, 2329)
    m._crisis_hold[40] -= M.CRISIS_HOLD_IDLE_S + 1     # nothing bought for a while
    assert not m._hold_for_crisis(40, 2329)
    assert not m._hold_for_crisis(40, 2329)            # and stays released this round


def test_never_holds_longer_than_the_cap():
    m = bare_match(0.48)
    assert m._hold_for_crisis(40, 2329)
    m._crisis_hold[40] -= M.CRISIS_HOLD_S + 1
    m._last_buy = time.time()                          # even while still buying
    assert not m._hold_for_crisis(40, 2329)


def test_no_hold_when_the_round_holds_or_cash_is_short_or_sends_are_continuous():
    assert not bare_match(1.2)._hold_for_crisis(40, 5000)
    assert not bare_match(0.48)._hold_for_crisis(40, 100)
    assert not bare_match(0.48, {"continuous": True})._hold_for_crisis(40, 5000)


def test_a_crisis_round_lets_reinforce_at_the_cash_the_executor_holds():
    """Ancient Portal Impoppable (2026-11-05): round 94 was rated 0.45 and
    the executor held all $17,562 "for blimp damage before round 94" while
    round 94 was being played; reinforce never ran and the game was lost.
    Outside a crisis the hold stays whole (Spillway ABR 2026-11-04)."""
    m = bare_match(0.48)
    m.ex.saving_for_threat = True
    assert m._cash_held(dropped=False, crisis=False)
    assert not m._cash_held(dropped=False, crisis=True)
    assert not m._cash_held(dropped=True, crisis=False)
    m.ex.saving_for_threat = False
    assert not m._cash_held(dropped=False, crisis=False)
    assert not bare_match(0.48)._cash_held(dropped=False, crisis=False)   # an executor without the flag


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
