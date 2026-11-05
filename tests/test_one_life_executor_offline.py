"""Offline checks for the executor in one-life games (Impoppable, CHIMPS):

* Executor.why() tells the game's journal why a purchase or sale happens;
* income tiers come from towers.py, and CHIMPS never buys them;
* cash is not held for a threat several rounds away while the round being
  played is weak (Chutes Impoppable, 2026-11-04: lost round 96 with
  $16,972 "saving for bad answer");
* reinforcing may outbid a waiting plan step with a purchase that lifts the
  round being played (Bazaar Reverse, 2026-11-05: lost round 51 with the
  cash kept "for plan step a1 0-4-2");
* no tower is sold as useless while the defence is short;
* a village step that buys the discount is not set aside after one click
  without effect (Castle Revenge Impoppable, 2026-11-04).

Fake games and forecasts in the style of tests/test_reinforce_offline.py.
Run: python tests/test_one_life_executor_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_reinforce_offline import ToyEx  # noqa: E402


def tower(tid, kind, tiers, **kw):
    return N(tid=tid, kind=kind, tiers=list(tiers), x=0.5, y=0.5, spent=kw.pop("spent", 0), **kw)


def bare_executor(mode, towers=(), **fields):
    """An Executor with only the fields the checks below read."""
    ex = S.Executor.__new__(S.Executor)
    ex.g = N(towers={p.tid: p for p in towers}, fail_reason=None)
    ex.m = N(frac_to_cell=lambda x, y: (10, 10))
    ex.mode, ex.rules, ex.strat = mode, S.rules(mode), {"plan": []}
    ex.no_income = bool(ex.rules.get("no_income_towers"))
    ex.no_sell = bool(ex.rules.get("no_sell"))
    ex.account, ex.capped, ex.plan, ex.idx, ex.deferred = None, set(), [], 0, []
    ex.failed_spots, ex.noted = set(), set()
    for k, v in fields.items():
        setattr(ex, k, v)
    return ex


class Fixed:
    """A forecast that rates every round `margin` (or by round, `by_round`)."""

    def __init__(self, margin, by_round=None):
        self.m, self.by_round = margin, by_round or {}

    def margin(self, towers, rnd):
        return self.by_round.get(rnd, self.m)

    def worst(self, towers, rounds, iterations=9):
        return min((self.margin(towers, r), r) for r in rounds) if rounds else None


# -- the journal hook -------------------------------------------------------------
def test_why_sets_restores_and_nests():
    ex = bare_executor("impoppable")
    assert getattr(ex.g, "why", None) is None
    with ex.why("plan", "plan step 3", step_idx=3, step={"do": "sell"}):
        assert ex.g.why == {"source": "plan", "reason": "plan step 3", "step_idx": 3, "step": {"do": "sell"}}
        with ex.why("plan_sell", "the plan sells a1"):
            assert ex.g.why["source"] == "plan_sell"       # the innermost block wins
        assert ex.g.why["source"] == "plan"
    assert ex.g.why is None
    # restored even when the block fails
    try:
        with ex.why("surplus"):
            raise RuntimeError
    except RuntimeError:
        pass
    assert ex.g.why is None

    class Refuses:
        __slots__ = ("towers",)
    ex.g = Refuses()
    with ex.why("panic", "lives dropped"):                  # a fake game: nothing recorded, no error
        pass


# -- income tiers -----------------------------------------------------------------
def test_income_tiers_come_from_the_tower_table():
    for entry in [("village", 3, 3), ("alchemist", 3, 3), ("buccaneer", 3, 3), ("engineer", 3, 4),
                  ("druid", 2, 4), ("heli", 2, 4)]:
        assert entry in S.INCOME_UPGRADES, entry
    # Supply Drop is the sniper's middle path (towers.py), tier 4
    assert ("sniper", 2, 4) in S.INCOME_UPGRADES
    # unconfirmed notes ("income?": Bounty Hunter) and discount tiers are not income
    assert not any(k == "village" and p == 3 and t < 3 for k, p, t in S.INCOME_UPGRADES)
    assert not any(k == "dartling" for k, _, _ in S.INCOME_UPGRADES)


def test_tiers_above_income_tiers_are_judged_by_their_own_notes():
    ex = bare_executor("chimps")
    # damage capstones above an income tier stay open in CHIMPS
    for kind, target in [("sniper", [0, 5, 0]), ("heli", [0, 5, 0]), ("alchemist", [0, 0, 5]),
                         ("druid", [0, 5, 0]), ("village", [0, 0, 5])]:
        assert not ex._is_income(kind, target), (kind, target)
        step = {"do": "upgrade", "kind": kind, "to": "-".join(map(str, target))}
        ex._id_kind = {}
        assert ex._step_allowed(step), step
    # the income tiers themselves, crosspathed or not, stay out
    for kind, target in [("sniper", [0, 4, 2]), ("druid", [0, 4, 0]), ("alchemist", [2, 0, 4]),
                         ("village", [0, 0, 3]), ("buccaneer", [0, 0, 5])]:
        assert ex._is_income(kind, target), (kind, target)


def test_chimps_upgrade_choices_never_offer_income_tiers():
    board = [tower("v1", "village", [0, 0, 2]), tower("s1", "sniper", [0, 3, 0]),
             tower("a1", "alchemist", [0, 0, 2]), tower("b1", "buccaneer", [0, 0, 2])]
    chimps = bare_executor("chimps", board)
    offered = [(p.kind, tuple(t)) for p, t, _ in chimps.upgrade_choices(past_plan=True)]
    assert offered, "something else is still offered"
    assert not any(chimps._is_income(kind, list(t)) for kind, t in offered), offered
    # with income the same tiers are fair game
    hard = bare_executor("hard", board)
    assert any(hard._is_income(p.kind, t) for p, t, _ in hard.upgrade_choices(past_plan=True))


# -- a far threat while the round being played is weak ---------------------------------
def chutes(margin):
    """Round 94 of Impoppable with $27,000: the BAD of round 100 is due (one
    life looks six rounds ahead), its answer costs $40,000 and waits."""
    ex = bare_executor("impoppable", [tower("s1", "super", [2, 0, 3])], forecast=Fixed(margin))
    ex.due_threats = lambda rnd: ["bad"]
    ex._ramp_due = lambda rnd: None

    def answer(threat, cash, rnd):
        ex.wait_cost = 3_000          # only the next tier of the answer
        ex.wait_total = 40_000        # the whole answer
        return "wait"
    ex.answer_threat = answer
    ex.saving_for_threat, ex.held_cash = False, 0.0
    return ex


def test_a_weak_round_does_not_hold_all_the_cash_for_a_far_threat():
    ex = chutes(0.25)
    assert ex._threat_round("bad", 94) == 100
    assert ex._threat_tick(27_000, 94) is None              # the plan and reinforcing go on
    assert not ex.saving_for_threat                         # so Match lets reinforce.py spend
    income = ex.income_until(100, 94)
    assert ex.held_cash == max(0.0, 40_000 - income), (ex.held_cash, income)
    if TH.available():
        assert income > 0 and ex.held_cash < 27_000
    # reinforcing spends what is not held: a purchase that lifts round 94
    toy = ToyEx()
    toy.held_cash = ex.held_cash
    status = R.buy_best(toy, toy_forecast(0.25), 27_000, 94, 100)
    assert status == "bought" and toy.bought, status


def test_the_weak_hold_counts_the_whole_answer():
    """The answer's steps are priced in full (_steps_cost), not by their
    next tier: a super monkey 2-0-3 -> 2-0-5 answer costs both tiers."""
    ex = bare_executor("impoppable", [tower("s1", "super", [2, 0, 3])])
    ex._caps = lambda kind, p=None: (5, 5, 5)
    steps = [{"do": "upgrade", "id": "s1", "to": "2-0-5"}]
    fam = S.PRICE_FAMILY.get("impoppable", "hard")
    want = sum(S.T.upgrade_cost("super", 3, t, fam) for t in (4, 5))
    assert ex._steps_cost(steps) == want > 0


def test_an_unknown_answer_cost_holds_all_the_cash_only_in_a_safe_round():
    """Neither the whole answer nor its next tier priced: the cash is held
    while the round being played is safe, and not at all while it is weak
    (a hold of unknown size would starve the round at hand)."""
    def answer(threat, cash, rnd):
        return "wait"                 # waited without pricing anything
    ex = chutes(2.5)
    ex.answer_threat = answer
    assert ex._threat_tick(27_000, 94) is False
    assert ex.saving_for_threat and ex.held_cash == 0.0
    ex = chutes(0.25)
    ex.answer_threat = answer
    assert ex._threat_tick(27_000, 94) is None
    assert not ex.saving_for_threat and ex.held_cash == 0.0


def test_a_safe_round_still_holds_the_cash_for_the_threat():
    ex = chutes(2.5)
    assert ex._threat_tick(27_000, 94) is False
    assert ex.saving_for_threat and ex.held_cash == 0.0


def test_lives_falling_count_as_a_weak_round():
    ex = chutes(2.5)
    ex.note_lives_dropped(94)
    assert ex._threat_tick(27_000, 94) is None and not ex.saving_for_threat


def toy_forecast(now_margin):
    """ToyEx's tower: the round being played rates now_margin plus 0.1 per
    path-1 tier and 0.8 per path-2 tier, the rest of the look-ahead is safe."""
    class Toy:
        def margin(self, towers, rnd):
            extra = sum(0.1 * t.tiers[0] + 0.8 * t.tiers[1] for t in towers)
            return now_margin + extra if rnd in (94, 95) else 3.0

        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: max(0.0, 10 * (1 - self.margin(towers, r) * scale)) for r in rounds}
            return lost if per_round else sum(lost.values())
    return Toy()


# -- a plan step waiting for cash in a crisis ----------------------------------------
class Bazaar:
    """Round 41: the weakest round of the look-ahead by lives (50) does not
    move with any purchase; rounds 41-42 rate now_margin plus 0.1 per path-1
    tier of ToyEx's tower."""

    def __init__(self, now_margin):
        self.now = now_margin

    def margin(self, towers, rnd):
        if rnd == 50:
            return 0.6
        if rnd in (41, 42):
            return self.now + sum(0.1 * t.tiers[0] + 0.8 * t.tiers[1] for t in towers)
        return 3.0

    def leaks(self, towers, rounds, scale, per_round=False):
        lost = {r: 20.0 if r == 50 else max(0.0, 10 * (1 - self.margin(towers, r) * scale))
                for r in rounds}
        return lost if per_round else sum(lost.values())


def test_a_crisis_buy_outbids_a_waiting_plan_step():
    ex = ToyEx()
    ex.plan, ex.idx = [{"do": "upgrade", "id": "s1", "to": "4-2-0"}], 0
    ex._first_step_cost = lambda step: 20_000
    # round 41 rates 0.3: the $300 upgrade lifts it although round 50 stays at 0.6
    assert R.crisis_now(Bazaar(0.3), ex, 41)
    status, found = R.best(ex, Bazaar(0.3), 1000, 41, 60)
    assert status == "buy" and found[0].cost == 300, (status, found)
    assert found[1] == 50 and found[2] == found[3] == 0.6       # the worst round did not move
    # round 41 safe (1.6): the old rule stands, the cash stays for the plan
    assert not R.crisis_now(Bazaar(1.6), ex, 41)
    assert R.best(ex, Bazaar(1.6), 1000, 41, 60) == ("wait", None)


def test_crisis_lift_counts_the_lowest_round():
    before, after = R.lift(Bazaar(0.3), [tower("s1", "sniper", [0, 0, 0])],
                           [tower("s1", "sniper", [1, 0, 0])], 41, 50, crisis=True)
    assert abs(before - 0.3) < 1e-9 and abs(after - 0.4) < 1e-9
    assert R.lift(Bazaar(0.3), [tower("s1", "sniper", [0, 0, 0])],
                  [tower("s1", "sniper", [1, 0, 0])], 41, 50, crisis=False) == (0.6, 0.6)


def test_release_keeps_only_what_income_cannot_rebuild():
    assert R.release(N(), 5000, 50, 40) == 5000                    # unknown income: all held
    ex = N(income_until=lambda due, rnd: 1000.0 * (due - rnd))
    assert R.release(ex, 5000, 43, 40) == 2000
    assert R.release(ex, 5000, 50, 40) == 0.0


# -- sales while the defence is short ------------------------------------------------
def seller(forecast, drops=()):
    """Two towers; d1 has read 0 pops twice since round 30."""
    d1 = tower("d1", "dart", [2, 0, 0], spent=600, placed_round=30, pops=0, pops_round=45, zero_reads=2)
    t1 = tower("t1", "tack", [2, 0, 0], spent=500, placed_round=30, pops=900)
    ex = bare_executor("hard", [d1, t1], forecast=forecast, removed=[])
    ex._sole_answer = lambda p: None
    sold = []
    ex.g.sell = lambda p: sold.append(p.tid) or True
    for r in drops:
        ex.note_lives_dropped(r)
    return ex, sold


def test_no_sale_while_the_look_ahead_is_weak():
    ex, sold = seller(Fixed(3.0, {50: 0.44}))
    assert ex.sell_useless(45) is False and not sold


def test_no_sale_while_lives_fell_lately():
    ex, sold = seller(Fixed(3.0), drops=[43])
    assert ex.sell_useless(45) is False and not sold
    ex, sold = seller(Fixed(3.0), drops=[42])            # three rounds ago: calm again
    assert ex.sell_useless(45) is True and sold == ["d1"]


def test_a_sale_goes_ahead_when_the_defence_holds():
    ex, sold = seller(Fixed(3.0))
    assert ex.sell_useless(45) is True and sold == ["d1"]


# -- clicks without effect --------------------------------------------------------
def test_the_discount_village_is_not_set_aside_after_one_click():
    step = {"do": "upgrade", "id": "v1", "to": "2-0-2"}
    ex = bare_executor("impoppable", [tower("v1", "village", [1, 0, 1])], plan=[step])
    ex.g.fail_reason = "noeffect"
    for tick in range(1, 6):                     # never, however often: it buys Monkey Commerce
        ex.tick_no = tick
        assert ex._set_aside_blocked(step) is False
    assert ex.idx == 0 and not ex.deferred
    # with income and more lives the old rule stands: set aside at once
    hard = bare_executor("hard", [tower("v1", "village", [1, 0, 1])], plan=[dict(step)])
    hard.g.fail_reason = "noeffect"
    assert hard._set_aside_blocked(hard.plan[0]) is True and hard.deferred


def test_other_one_life_upgrades_get_three_clicks():
    step = {"do": "upgrade", "id": "n1", "to": "2-0-4"}
    ex = bare_executor("impoppable", [tower("n1", "ninja", [2, 0, 3])], plan=[step])
    ex.g.fail_reason = "noeffect"
    ex.tick_no = 1
    assert ex._set_aside_blocked(step) is False
    assert ex._set_aside_blocked(step) is False             # the same tick counts once
    ex.tick_no = 2
    assert ex._set_aside_blocked(step) is False
    ex.tick_no = 3
    assert ex._set_aside_blocked(step) is True and ex.deferred == [step]


def test_held_retries_are_not_counted_as_clicks():
    # Game.upgrade answers "noeffect" without clicking while it holds a retry
    # back: only its own count of real clicks may close the path
    ex = bare_executor("impoppable", [tower("v1", "village", [1, 0, 1])])
    ex.upgrade_fails = {}
    ex.g.fail_reason = "noeffect"
    ex.g._retry_at = {("v1", 3): (0.0, "noeffect", 1)}
    for _ in range(6):
        ex._upgrade_failed(ex.g.towers["v1"], 3, 766)
    assert ("v1", 3) not in ex.capped and ex.upgrade_fails[("v1", 3)] == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
