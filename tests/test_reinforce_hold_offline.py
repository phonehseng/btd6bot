"""Offline checks: while reinforce saves for the one purchase that holds the
weakest round ahead, the plan's own steps leave that cash alone.

Ancient Portal Impoppable (2026-11-05) logged "saving for upgrade ace2 ->
2-4-0 ($19200) - round 98 goes 0.84 -> 1.01" at round 95, and four seconds
later the plan spent $10,760 taking sniper3 to 4-0-2 (+0.05 for round 98).
Round 98 started with $16,190, rated 0.90, and was lost. The save only
stopped surplus(); Executor.tick spent on as before.
Run: python tests/test_reinforce_hold_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as R  # noqa: E402
from btd6bot.match import Match  # noqa: E402
from btd6bot.strategy import Executor  # noqa: E402
from test_reinforce_offline import ToyEx, ToyForecast  # noqa: E402


def test_buy_best_records_what_it_saves_for():
    # ToyForecast: with $1,000 at round 37 only the $2,000 upgrade holds
    # round 40, so reinforce saves for it - and says so on the executor
    ex = ToyEx()
    assert R.buy_best(ex, ToyForecast(), 1000, 37, 80) == "save"
    assert ex.save_goal == (2000, 40)
    # any other answer clears it (here the $2,000 is affordable: bought)
    assert R.buy_best(ex, ToyForecast(), 5000, 37, 80) == "bought"
    assert ex.save_goal is None


def match_with(goal, weak_round=95, crisis_round=None):
    """A Match with only the fields _reinforce_hold reads."""
    m = Match.__new__(Match)
    m.ex = N(save_goal=goal)
    m._weak_round, m._crisis_round = weak_round, crisis_round
    return m


def test_the_hold_lasts_while_the_saving_does():
    m = match_with((19200, 98))
    assert m._reinforce_hold(95, dropped=False) == 19200
    # nothing saved for, or the look-ahead holds again: no hold
    assert match_with(None)._reinforce_hold(95, False) == 0
    assert match_with((19200, 98), weak_round=None)._reinforce_hold(95, False) == 0
    # lives falling, a crisis round being played, or the saved-for round
    # has come: the plan may spend again
    assert m._reinforce_hold(95, dropped=True) == 0
    assert match_with((19200, 98), crisis_round=95)._reinforce_hold(95, False) == 0
    assert match_with((19200, 98), weak_round=98)._reinforce_hold(98, False) == 0


def executor_with_plan(step):
    """An Executor with one plan step whose try_step records the cash it
    was offered (the threat checks and recheck are stubbed out)."""
    ex = Executor.__new__(Executor)
    ex.g = N(fail_reason=None)
    ex.plan, ex.idx, ex.fill, ex.deferred = [step], 0, [], []
    ex.panic_pending, ex.panic_steps, ex.rules = 0, [], {}
    ex._recheck_doubtful = lambda: None
    ex._threat_tick = lambda cash, rnd: None
    ex.offered = []

    def try_step(st, cash, rnd):
        ex.offered.append(cash)
        return "bought" if cash >= 10_760 else "wait"
    ex.try_step = try_step
    ex.why = lambda *a, **k: _Why()
    ex.note_lives_dropped = lambda rnd: None
    return ex


class _Why:
    """Stands in for Executor.why's context manager."""
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def test_the_plan_gets_only_what_the_saving_leaves():
    step = {"do": "upgrade", "id": "sniper3", "to": "4-0-2"}
    ex = executor_with_plan(step)
    # no saving: the $12,000 in hand buys the sniper tiers
    assert ex.tick(12_000, 95) is True and ex.offered[-1] == 12_000
    # reinforce saves $19,200 for ace2: the plan step is offered nothing
    ex.idx = 0
    ex.reinforce_hold = 19_200
    assert ex.tick(12_000, 95) is False and ex.offered[-1] == 0
    # cash past the saving is the plan's again
    assert ex.tick(31_000, 95) is True and ex.offered[-1] == 31_000 - 19_200
    # lives falling: the hold is off
    ex.idx = 0
    assert ex.tick(12_000, 95, lives_dropped=True) is True and ex.offered[-1] == 12_000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
