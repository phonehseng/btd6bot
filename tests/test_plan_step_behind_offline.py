"""A one-life plan stalled on a step it cannot pay in time buys the steps
behind it instead of purchases that lift nothing (backlog 75).

Enchanted Glade Impoppable (2026-11-11, chimps_ninja_sun, case
20261111_093749, lost round 98): the Sun Avatar step (s1 -> 3-0-2, $24,000)
was the waiting plan step from about round 40 to the defeat. It could not be
paid before the weak round ahead, so reinforce spent every round's income -
a quarter of its purchases rated "0.06 -> 0.06" - and the fifteen plan steps
behind it were never reached. Mesa Impoppable lost round 78 the same way.

Checked offline, with a game that charges real prices and a toy forecast:
  * reinforce.no_lift: "wait" and a purchase moving the weakest round by less
    than MIN_LIFT count, a real lift and "save" do not;
  * Executor.plan_step_out_of_reach: only a step that costs more than the
    cash and the income before the weakest round;
  * Executor.buy_plan_step_behind buys the first later step the cash pays
    for - skipping a round-gated step, an upgrade of a tower not standing
    and a step too dear - and leaves the stalled step the current one; the
    plan afterwards finishes in its own order;
  * nothing changes in a mode with lives, when income pays the step in
    time, or when no later step is affordable;
  * reinforce.buy_best: a purchase that lifts nothing gives way to the plan
    step behind, a purchase that lifts the round is bought as before.
Run: python tests/test_plan_step_behind_offline.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import reinforce as R         # noqa: E402
from btd6bot import strategy as S          # noqa: E402
from btd6bot import towers as T            # noqa: E402
from btd6bot.game import Placed            # noqa: E402
import simulate_threats as SIM             # noqa: E402

ROUND = 50          # the round being played
WEAK_ROUND = 52     # the weakest round of the look-ahead in the toy forecast
INCOME = 1_500      # dollars a round, as the executor counts income here

# The stalled step first, then what stands behind it in the plan.
PLAN = [{"do": "upgrade", "id": "s1", "to": "3-0-2"},                    # the Sun Avatar: out of reach
        {"do": "upgrade", "id": "a1", "to": "0-2-0", "round": 90},       # waits for its round
        {"do": "upgrade", "id": "b9", "to": "2-0-0"},                    # its tower does not stand
        {"do": "upgrade", "id": "n1", "to": "0-0-5"},                    # stands, but its next tier is too dear
        {"do": "place", "id": "m1", "kind": "bomb", "role": "dps", "segment": [0.5, 1.0]},
        {"do": "upgrade", "id": "n1", "to": "0-0-5"}]
STANDING = [("s1", "super", (2, 0, 2)), ("a1", "ace", (0, 0, 0)), ("n1", "ninja", (0, 0, 4))]


class Weak:
    """A forecast whose weakest look-ahead round is WEAK_ROUND, rated 0.4."""

    def worst(self, towers, rounds, iterations=9):
        return (0.4, WEAK_ROUND)


def executor(mode, cash, income=INCOME):
    """An Executor on a game with real prices (simulate_threats.CashGame),
    the towers of STANDING on the board and PLAN as its plan."""
    g = SIM.CashGame(S.PRICE_FAMILY[mode])
    g.cash = cash
    for tid, kind, tiers in STANDING:
        g.towers[tid] = Placed(tid, kind, 0.3 + 0.05 * len(g.towers), 0.3, list(tiers))
    ex = S.Executor(g, SIM.OpenModel(), {"id": "t", "modes": [mode], "plan": PLAN, "answers": {}}, mode,
                    SIM.full_account())
    ex._threat_tick = lambda cash, rnd: None       # the threat checks are not under test here
    ex.plan = [dict(s) for s in PLAN]               # no opener
    ex.forecast = Weak()
    ex.income_until = lambda due, rnd: income * max(0, due - rnd)
    return g, ex


def bomb_cash(mode="impoppable"):
    """Enough for the bomb, far too little for the Sun Avatar or n1's tier 5."""
    return T.tower_cost("bomb", S.PRICE_FAMILY[mode]) + 500


def test_no_lift():
    option = N(what="upgrade x", cost=100)
    assert R.no_lift("wait", None)
    assert R.no_lift("buy", (option, WEAK_ROUND, 0.06, 0.06))
    assert R.no_lift("buy", (option, WEAK_ROUND, None, None))
    assert not R.no_lift("buy", (option, WEAK_ROUND, 0.40, 0.40 + R.MIN_LIFT))
    assert not R.no_lift("save", (option, WEAK_ROUND, 0.4, 1.1))
    assert not R.no_lift("safe", None)


def test_out_of_reach_is_about_cash_and_income():
    g, ex = executor("impoppable", bomb_cash())
    step, cost, due = ex.plan_step_out_of_reach(g.cash, ROUND)
    assert step["id"] == "s1" and due == WEAK_ROUND and cost > g.cash + 2 * INCOME
    # income that pays the step before the weak round: it keeps its turn
    g, ex = executor("impoppable", bomb_cash(), income=50_000)
    assert ex.plan_step_out_of_reach(g.cash, ROUND) is None
    # the cash pays it now: nothing waits
    g, ex = executor("impoppable", 100_000)
    assert ex.plan_step_out_of_reach(g.cash, ROUND) is None


def test_the_first_affordable_step_behind_is_bought():
    g, ex = executor("impoppable", bomb_cash())
    assert ex.buy_plan_step_behind(g.cash, ROUND)
    assert "m1" in g.towers                                   # the bomb, plan step 4
    assert g.towers["a1"].tiers == [0, 0, 0]                  # round-gated: left alone
    assert "b9" not in g.towers and g.towers["n1"].tiers == [0, 0, 4]
    assert ex.idx == 0                                        # the Sun Avatar is still the plan's step
    # nothing behind is affordable any more
    assert not ex.buy_plan_step_behind(g.cash, ROUND)
    # with the cash the plan goes on in its order and meets the bomb as done
    g.cash = 500_000
    while ex.idx < len(ex.plan):
        assert ex.tick(g.cash, 95)
    assert g.towers["s1"].tiers == [3, 0, 2] and g.towers["n1"].tiers == [0, 0, 5]
    assert g.towers["a1"].tiers == [0, 2, 0]
    assert sum(1 for p in g.towers.values() if p.kind == "bomb") == 1


def test_only_with_one_life_and_a_step_out_of_reach():
    # a mode with lives keeps its spending as it was
    g, ex = executor("hard", bomb_cash("hard"))
    assert not ex.buy_plan_step_behind(g.cash, ROUND) and "m1" not in g.towers
    # income brings the Sun Avatar in time: the cash is its own
    g, ex = executor("impoppable", bomb_cash(), income=50_000)
    assert not ex.buy_plan_step_behind(g.cash, ROUND) and "m1" not in g.towers


def test_buy_best_prefers_the_plan_to_a_purchase_that_lifts_nothing():
    junk = R.Option("upgrade a1 -> 1-0-0", 700, {"do": "upgrade", "id": "a1", "to": "1-0-0"}, [])
    real_best = R.best
    try:
        # the model's pick moves nothing: the plan's bomb comes instead
        g, ex = executor("impoppable", bomb_cash())
        R.best = lambda *a, **k: ("buy", (junk, WEAK_ROUND, 0.40, 0.40))
        assert R.buy_best(ex, ex.forecast, g.cash, ROUND, 100) == "bought"
        assert "m1" in g.towers and g.towers["a1"].tiers == [0, 0, 0]
        # nothing to buy at all: the idle cash goes to the plan too
        g, ex = executor("impoppable", bomb_cash())
        R.best = lambda *a, **k: ("wait", None)
        assert R.buy_best(ex, ex.forecast, g.cash, ROUND, 100) == "bought" and "m1" in g.towers
        # the pick lifts the weak round: it is bought as before
        g, ex = executor("impoppable", bomb_cash())
        R.best = lambda *a, **k: ("buy", (junk, WEAK_ROUND, 0.40, 0.55))
        assert R.buy_best(ex, ex.forecast, g.cash, ROUND, 100) == "bought"
        assert "m1" not in g.towers and g.towers["a1"].tiers == [1, 0, 0]
        # the look is saving for a purchase that holds the round: left alone
        g, ex = executor("impoppable", bomb_cash())
        R.best = lambda *a, **k: ("save", (junk, WEAK_ROUND, 0.40, 1.10))
        assert R.buy_best(ex, ex.forecast, g.cash, ROUND, 100) == "save" and "m1" not in g.towers
    finally:
        R.best = real_best


if __name__ == "__main__":
    import inspect
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
    print("ok")
