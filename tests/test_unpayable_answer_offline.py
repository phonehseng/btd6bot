"""A threat answer the income cannot pay in time must not hold the cash.

Midnight Mansion Primary Only (case 20261104_195037): every cheap camo
answer (desperado, dart, ice) was given up for lack of a legal spot, so the
next option on the list was Boomerang 5-0-2 at $27,625. The executor
"saved" for it from round 24 with $4,248 in hand while camo leaked, and the
game was lost at round 40. Now such an answer returns 'defer': the plan and
reinforcing go on, and the answer is tried again on the next tick.
Run: python tests/test_unpayable_answer_offline.py (no game needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import strategy as S   # noqa: E402


def executor(cash, option_cost):
    """An Executor with just what _answer_gap reads; every step 'waits' for cash."""
    ex = S.Executor.__new__(S.Executor)
    ex.latched, ex.noted, ex.strat = {}, set(), {}
    ex.cash_seen = cash
    ex.round_set, ex.income_mult = "standard", 1.0
    ex._options = lambda threat, sig: [{"cost": option_cost, "desc": "upgrade b1 to 5-0-2",
                                        "steps": [{"do": "upgrade", "id": "b1", "to": "5-0-2"}]}]
    ex._plan_cost_to_cover = lambda *a, **k: None
    ex.try_step = lambda st, cash, rnd: "wait"
    return ex


def test_an_answer_out_of_reach_does_not_hold_the_cash():
    ex = executor(4248, 27625)
    assert ex._answer_gap("camo", None, 4248, 24) == "defer"


def test_an_answer_the_income_can_pay_is_still_saved_for():
    ex = executor(4248, 4800)
    assert ex._answer_gap("camo", None, 4248, 24) == "wait"
    assert "saving $4800" in ex.wait_note


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
