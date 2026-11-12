"""Offline checks for reinforce.py: when the damage model rates the coming
rounds as weak, the purchase that saves the most lives per dollar (at half
strength) is chosen; nothing is bought when the look-ahead holds or the
cash buys nothing that helps. Uses the real model on Pat's Pond Hard.
Run: python tests/test_reinforce_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402
from btd6bot.strategy import Executor  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = (0.0, 0.04, 0.855, 0.96)


class Ex:
    """The parts of Executor that reinforce.py uses: a few snipers on Pat's
    Pond (spots from the game lost there on 2026-10-22)."""
    mode = "hard"

    def __init__(self, towers):
        self.g = N(towers={t.tid: t for t in towers}, price=lambda kind: T.tower_cost(kind, "hard"))
        self.m = MapModel.load("Pat's Pond", PF)
        self.bought = []

    def upgrade_choices(self, first=None, past_plan=False):
        for p in self.g.towers.values():
            for path in range(3):
                t = list(p.tiers)
                if t[path] >= 5:
                    continue
                t[path] += 1
                if sum(x > 0 for x in t) > 2 or sum(x > 2 for x in t) > 1:
                    continue
                yield p, t, T.upgrade_cost(p.kind, path + 1, t[path], "hard")

    def at_tower_cap(self):
        return False

    def _main_kind(self):
        return "sniper"

    def kind_allowed(self, kind):
        return True

    def pick_spots(self, kind, step, n=1):
        p = next(iter(self.g.towers.values()))
        return [(*self.m.frac_to_cell(p.x + 0.03, p.y), 1.0)]

    why = Executor.why    # the real one: each purchase says why it was made

    def try_step(self, step, cash, rnd):
        self.bought.append(step)
        self.whys = getattr(self, "whys", []) + [self.g.why]
        return "bought"


def weak_board():
    return [N(tid="s1", kind="sniper", tiers=[2, 0, 2], x=0.729, y=0.717),
            N(tid="s2", kind="sniper", tiers=[1, 0, 0], x=0.056, y=0.828),
            N(tid="s3", kind="sniper", tiers=[0, 0, 0], x=0.783, y=0.402)]


def forecast(ex):
    return RoundForecast("Pat's Pond", "hard", ex.m.sight)


def test_a_weak_look_ahead_buys_what_saves_most():
    if not D.available():
        return
    ex = Ex(weak_board())
    status, found = R.best(ex, forecast(ex), 5000, 40, 80)
    assert status == "buy", status
    o, worst, before, after = found
    assert 40 <= worst <= 49 and o.cost <= 5000
    assert after >= before, (o.what, before, after)
    # bought through the executor, and logged as a reinforcement
    assert R.buy_best(ex, forecast(ex), 5000, 40, 80) == "bought" and ex.bought
    assert ex.whys[-1]["source"] == "reinforce" and ex.g.why is None


def test_no_cash_means_wait():
    if not D.available():
        return
    ex = Ex(weak_board())
    assert R.best(ex, forecast(ex), 0, 40, 80) == ("wait", None)


def test_nothing_ahead_means_safe():
    if not D.available():
        return
    ex = Ex(weak_board())
    assert R.best(ex, forecast(ex), 5000, 81, 80) == ("safe", None)     # past the last round


def test_trim_keeps_the_dear_options_too():
    # a crowded board: 30 cheap first tiers and 2 expensive upgrades
    out = [R.Option(f"cheap{i}", 270 + i, {}) for i in range(30)]
    out += [R.Option("t4", 9000, {}), R.Option("t5", 21000, {})]
    kept = R.trim(out)
    assert len(kept) == R.MAX_OPTIONS
    assert {"t4", "t5"} <= {o.what for o in kept}
    assert kept[0].what == "cheap0"
    assert R.trim(out[:5]) == out[:5]      # short lists are kept whole


class ToyForecast:
    """A stand-in damage model: a tower's margin grows 0.1 per path-1 tier
    and 0.8 per path-2 tier, and a round loses 10 lives per missing unit of
    margin, round 40 being 0.1 weaker than the rest. One cheap upgrade ($300,
    +0.1) and one dear one ($2,000, +0.8)."""

    def margin(self, towers, rnd):
        return sum(0.3 + 0.1 * t.tiers[0] + 0.8 * t.tiers[1] for t in towers) - (0.1 if rnd == 40 else 0.0)

    def leaks(self, towers, rounds, scale, per_round=False):
        lost = {r: max(0.0, 10 * (1 - self.margin(towers, r) * scale)) for r in rounds}
        return lost if per_round else sum(lost.values())


class ToyEx(Ex):
    """One tower and its two upgrades (ToyForecast), no room for another."""

    def __init__(self):
        self.g = N(towers={"s1": N(tid="s1", kind="sniper", tiers=[0, 0, 0], x=0.5, y=0.5)})
        self.bought = []

    def upgrade_choices(self, first=None, past_plan=False):
        p = self.g.towers["s1"]
        yield p, [1, 0, 0], 300
        yield p, [0, 1, 0], 2000

    def at_tower_cap(self):
        return True


def test_a_leaking_round_saves_for_the_purchase_that_holds_it():
    # Peninsula Medium (2026-10-27): $1,000 upgrades left round 40 at 0.06.
    # With $1,000 the cheap upgrade only nudges round 40 from 0.2 to 0.3;
    # the $2,000 one holds it (1.0), so the cash is kept for it.
    ex = ToyEx()
    status, found = R.best(ex, ToyForecast(), 1000, 37, 80)
    assert status == "save", status
    assert found[0].cost == 2000 and found[3] >= 1.0
    assert R.buy_best(ex, ToyForecast(), 1000, 37, 80) == "save" and not ex.bought


def test_no_saving_when_the_round_is_too_close_or_too_dear():
    ex = ToyEx()
    # the weakest round is the one being played: no income will come in time
    assert R.save_target(ToyForecast(), ex, 1000, 40, 40) is None
    # $2,000 is more than SAVE_REACH times $500: buy what helps now
    status, found = R.best(ex, ToyForecast(), 500, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)


def test_continuous_sends_save_only_for_what_two_rounds_of_income_pay():
    # Castle Revenge Apopalypse (2026-11-06): saving for a $20,000 step from
    # $7,006 left the board still while blimps piled up. With $1,000 and
    # $300 a round, the $2,000 upgrade is out of reach in two rounds under
    # continuous sends, so the $300 one is bought now; with $600 a round it
    # is in reach and the saving stands. Standard modes are unchanged.
    ex = ToyEx()
    ex.rules = {"continuous": True}
    ex.income_until = lambda due, rnd: 300.0 * (due - rnd)
    status, found = R.best(ex, ToyForecast(), 1000, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    assert R.save_target(ToyForecast(), ex, 1000, 37, 40) is None
    ex.income_until = lambda due, rnd: 600.0 * (due - rnd)
    assert R.save_target(ToyForecast(), ex, 1000, 37, 40)[0].cost == 2000
    # a standard mode keeps the long saving (test_a_leaking_round_saves...)
    assert R.save_target(ToyForecast(), ToyEx(), 1000, 37, 40) is not None


def test_no_saving_when_the_rounds_before_cost_the_lives_left():
    # Cargo Double HP (2026-11-03): saving for round 79 lost round 75.
    # Rounds 37-39 each cost 7 lives at full strength (ToyForecast): with
    # 13 lives left round 38 ends the game, before the $2,000 upgrade can
    # be saved for, so the affordable $300 one is bought now.
    ex = ToyEx()
    status, found = R.best(ex, ToyForecast(), 1000, 37, 80, lives=13)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # with 15 lives the game ends at round 39 (deciding_round looks
    # ENDING_LOOKAHEAD rounds ahead): rounds 37-38 cost only 14, two rounds
    # of income come first, and the $2,000 upgrade that holds round 39 is
    # saved for - the $300 one would still lose 18 lives by then
    status, found = R.best(ex, ToyForecast(), 1000, 37, 80, lives=15)
    assert status == "save" and found[0].cost == 2000 and found[1] == 39, (status, found)
    # with plenty of lives the saving rule is unchanged
    assert R.best(ex, ToyForecast(), 1000, 37, 80, lives=100)[0] == "save"


def test_crisis_falls_back_to_the_biggest_margin_gain():
    # Infernal Double HP (2026-11-03): no purchase saved lives at half
    # strength, so $77,100 sat idle; the one lifting the margin most is
    # bought instead.
    class Saturated(ToyForecast):
        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: 100.0 for r in rounds}       # every round leaks whole
            return lost if per_round else sum(lost.values())
    ex = ToyEx()
    status, found = R.best(ex, Saturated(), 5000, 40, 40, lives=100)
    assert status == "buy" and found[0].cost == 2000, (status, found)


def test_a_big_idle_bank_is_spent_even_when_the_model_sees_no_gain():
    # the model rates every purchase as useless (it misses what it does not
    # simulate): with $10,000+ in a crisis the dearest upgrade is bought;
    # a small bank still waits
    class Blind(ToyForecast):
        def margin(self, towers, rnd):
            return 0.2
        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: 100.0 for r in rounds}
            return lost if per_round else sum(lost.values())
    ex = ToyEx()
    status, found = R.best(ex, Blind(), R.BLIND_SPEND_CASH, 40, 40, lives=100)
    assert status == "buy" and found[0].cost == 2000, (status, found)
    assert R.best(ex, Blind(), 5000, 40, 40, lives=100)[0] == "wait"


def test_a_waiting_plan_step_keeps_the_cash_from_no_gain_purchases():
    # Castle Revenge Impoppable and Haunted Half Cash (2026-11-04): the plan
    # waited for a Sun Avatar while reinforce bought upgrades the model rated
    # "0.52 -> 0.52" - they saved lives in other rounds, never the weakest.
    class Stuck(ToyForecast):
        def margin(self, towers, rnd):
            if rnd == 45:
                return 0.5                       # nothing affordable moves it
            return 1.0 + 0.1 * sum(t.tiers[0] for t in towers)
    ex = ToyEx()
    status, found = R.best(ex, Stuck(), 1000, 40, 80)
    assert status == "buy" and found[0].cost == 300, "without a waiting plan step: bought"
    ex.plan, ex.idx = [{"do": "upgrade", "id": "s1", "to": "3-0-0"}], 0
    ex._first_step_cost = lambda step: 20000
    assert R.waiting_plan_step(ex, 1000) == (ex.plan[0], 20000)
    assert R.best(ex, Stuck(), 1000, 40, 80) == ("wait", None)
    # a plan step the cash already covers makes no claim
    ex._first_step_cost = lambda step: 800
    assert R.waiting_plan_step(ex, 1000) is None
    # a purchase that does lift the weakest round still outbids the plan
    ex._first_step_cost = lambda step: 20000
    assert R.best(ex, ToyForecast(), 500, 37, 80)[0] == "buy"


def test_a_crisis_with_nothing_to_grow_tries_a_new_tower_kind():
    # Spice Islands Impoppable (2026-11-04): every standing tower was at its
    # last tier and no land spot was left, so "0 purchases tried" while
    # $161,626 piled up. Only water spots remain here: a sub (a kind not on
    # the board) fits, and the model rates it as lifting the round.
    class Maxed(ToyEx):
        def __init__(self):
            super().__init__()
            self.g.price = lambda kind: T.tower_cost(kind, "impoppable")
            self.m = N(cell_to_frac=lambda cx, cy: (0.3, 0.3))

        def upgrade_choices(self, first=None, past_plan=False):
            return iter(())

        def at_tower_cap(self):
            return False

        def pick_spots(self, kind, step, n=1):
            return [(10, 10, 1.0)] if kind == "sub" else []

    class LikesSubs(ToyForecast):
        def margin(self, towers, rnd):
            return 0.2 + 0.5 * sum(t.kind == "sub" for t in towers)

        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: 100.0 for r in rounds}
            return lost if per_round else sum(lost.values())
    ex = Maxed()
    assert R.options(ex, 100_000) == []              # the old dead end
    status, found = R.best(ex, LikesSubs(), 100_000, 90, 100, lives=1)
    assert status == "buy" and found[0].what.startswith("another sub"), (status, found)
    assert found[0].step["kind"] == "sub" and found[0].cost == T.tower_cost("sub", "impoppable")
    # a small bank still waits rather than scattering new kinds
    assert R.best(ex, LikesSubs(), 5000, 90, 100, lives=1)[0] == "wait"


def test_a_new_tower_is_rated_at_what_the_bank_grows_it_into():
    ex = N(mode="impoppable", account=None)
    reached = R.grown(ex, "sub", 100_000)
    assert all(sum(x > 0 for x in t) <= 2 and sum(x > 2 for x in t) <= 1 for t in reached)
    assert any(5 in t for t in reached), reached        # $100k buys a tier 5
    assert R.grown(ex, "sub", 0) == {(0, 0, 0)}           # not even the tower itself
    # tower XP: a path locked past tier 2 stops there
    locked = N(mode="impoppable", account=N(upgrades=lambda kind: (2, 2, 2)))
    assert max(max(t) for t in R.grown(locked, "sub", 100_000)) == 2


def test_another_standing_kind_is_rated_grown_too():
    # Bazaar ABR (2026-11-05): "another ninja would move round 63 only 0.12
    # -> 0.12" - rated as a bare $430 tower - while $5,800 bought a 4-0-2
    # Bloonjitsu. Here a bare tower adds nothing and every tier adds 0.8:
    # with $6,000 the grown ninja beats the standing one's $2,000 tier.
    class Growable(ToyEx):
        def __init__(self):
            super().__init__()
            self.g.towers = {"n1": N(tid="n1", kind="ninja", tiers=[0, 0, 0], x=0.5, y=0.5)}
            self.g.price = lambda kind: T.tower_cost(kind, "hard")
            self.m = N(cell_to_frac=lambda cx, cy: (0.3, 0.3))

        def upgrade_choices(self, first=None, past_plan=False):
            p = self.g.towers["n1"]
            yield p, [1, 0, 0], 300
            yield p, [0, 1, 0], 2000

        def at_tower_cap(self):
            return False

        def _main_kind(self):
            return "ninja"

        def pick_spots(self, kind, step, n=1):
            return [(10, 10, 1.0)]

    class PerTier(ToyForecast):
        def margin(self, towers, rnd):
            return 0.2 + 0.8 * sum(sum(t.tiers) for t in towers)

        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: max(0.0, 10 * (1 - self.margin(towers, r) * scale)) for r in rounds}
            return lost if per_round else sum(lost.values())
    ex = Growable()
    bare = [o for o in R.options(ex, 6000) if o.what == "another ninja"]
    assert bare and bare[0].cost == T.tower_cost("ninja", "hard")
    # n1 stands bare, so the growth goes into it before another ninja is
    # bought: Spillway Medium (2026-11-05) bought eleven bare snipers, each
    # rated as the 1-2-0 it would grow into, and grew none of them
    grown = [o for o in R.grow(ex, PerTier(), R.options(ex, 6000), 6000, 45) if "to grow to" in o.what]
    assert grown and grown[0].what.startswith("upgrade n1 ->"), grown
    assert grown[0].step["do"] == "upgrade" and grown[0].step["id"] == "n1"
    assert sum(int(c) for c in grown[0].step["to"].split("-")) == 1, grown[0].step   # one tier at a time
    assert sum(grown[0].towers[0].tiers) > 1 and 0 < grown[0].cost <= 6000, grown    # rated at the target
    assert not [o for o in R.grow(ex, PerTier(), R.options(ex, 6000), 6000, 45) if o.what.startswith("another")]
    status, found = R.best(ex, PerTier(), 6000, 40, 80, lives=100)
    assert status == "buy" and found[0].what.startswith("upgrade n1 ->") and "to grow to" in found[0].what, (status, found)
    # once n1 has what a new ninja is rated at, another one is offered - at its grown price
    ex.g.towers["n1"].tiers = [5, 2, 0]
    grown = [o for o in R.grow(ex, PerTier(), R.options(ex, 6000), 6000, 45) if o.what.startswith("another ninja")]
    assert grown and "to grow to" in grown[0].what, grown
    assert any(grown[0].towers[-1].tiers) and T.tower_cost("ninja", "hard") < grown[0].cost <= 6000, grown
    assert grown[0].step["do"] == "place" and grown[0].step["kind"] == "ninja"
    ex.g.towers["n1"].tiers = [0, 0, 0]
    # when growing adds nothing in the model the bare placement keeps its price
    class Flat(PerTier):
        def margin(self, towers, rnd):
            return 0.2 + 0.5 * len(towers)
    flat = [o for o in R.grow(ex, Flat(), R.options(ex, 6000), 6000, 45) if o.what.startswith("another ninja")]
    assert flat[0].what == "another ninja" and flat[0].cost == T.tower_cost("ninja", "hard"), flat
    # Past the look's time budget a placement stays bare and the model is
    # not asked to rate its growth: on Polyphemus Impoppable (2026-11-05)
    # one look took 28 s and the bot sat on $13,990 through round 98.
    import time

    class Counting(PerTier):
        calls = 0

        def margin(self, towers, rnd):
            Counting.calls += 1
            return super().margin(towers, rnd)
    late = R.grow(ex, Counting(), R.options(ex, 6000), 6000, 45, deadline=time.monotonic() - 1)
    assert Counting.calls == 0, Counting.calls
    assert [o.what for o in late if o.what.startswith("another")] == ["another ninja"], late
    # ... and a look out of time buys nothing from a partial rating: it
    # answers "busy" and the next look (the forecast remembers its ratings)
    # goes on to the purchase an unbounded look would choose
    saved = R.LOOK_BUDGET_S
    R.LOOK_BUDGET_S = -1.0
    try:
        status, found = R.best(ex, PerTier(), 6000, 40, 80, lives=100)
    finally:
        R.LOOK_BUDGET_S = saved
    assert status == "busy" and found is None, (status, found)
    status, found = R.best(ex, PerTier(), 6000, 40, 80, lives=100)
    assert status == "buy" and found[0].cost <= 6000, (status, found)


def test_a_given_up_placement_is_not_offered():
    # Water Park ABR (2026-11-04): "another sniper" had been given up, so
    # every try came back 'skip' - yet it stayed the best-rated purchase
    # and nothing else was bought for three minutes
    class GivenUp(Ex):
        def place_held_back(self, step):
            return step.get("kind") == "sniper"
    board_ = weak_board()
    assert any(o.what == "another sniper" for o in R.options(Ex(board_), 5000))
    offered = [o.what for o in R.options(GivenUp(board_), 5000)]
    assert offered and "another sniper" not in offered, offered


def test_place_held_back_matches_try_place():
    # the executor's own check: the same step key try_place skips on
    from btd6bot.strategy import Executor
    ex = Executor.__new__(Executor)      # only the fields the check reads
    ex.dead_steps, ex.retry_at, ex.hold_fails = set(), {}, {}
    step = {"do": "place", "kind": "sniper", "role": "dps", "segment": [0.2, 1.0]}
    assert not ex.place_held_back(step)
    ex.dead_steps.add(Executor._step_key(dict(step)))
    assert ex.place_held_back(step)
    ex.dead_steps.clear()
    ex.hold_fails["sniper"] = 6
    assert ex.place_held_back(step)


def test_a_plan_step_keeps_the_cash_only_when_reachable_and_better():
    # Ancient Portal Impoppable (2026-11-05): the $27,284 saved toward
    # Perma-Spike went on a Super Monkey tier worth +0.03; Quad ABR: cash was
    # kept for a Glaive Lord no income could pay before the rush. Here the
    # plan waits for the $2,000 upgrade (+0.8 in ToyForecast) while the $300
    # one (+0.1) would eat into the saving. The rounds before 40 hold on
    # their own (Calm): a round in trouble is the next test's case.
    class Calm(ToyForecast):
        def margin(self, towers, rnd):
            return super().margin(towers, rnd) + (0.0 if rnd == 40 else 1.5)

    class Planned(ToyEx):
        income = 500.0                     # per round, counted toward the step

        def __init__(self):
            super().__init__()
            self.plan, self.idx = [{"do": "upgrade", "id": "s1", "to": "0-1-0"}], 0

        def _first_step_cost(self, step):
            return 2000

        def _next_path(self, p, target):
            return (2, 2000)

        def income_until(self, due_round, rnd):
            return self.income * max(0, due_round - rnd)
    ex = Planned()
    # $600 at round 37, round 40 the weakest: three rounds of income make
    # $2,100 - the step is reachable and lifts more, so the cash stays
    assert R.payable_by(ex, 2000, 600, 40, 37) is True
    assert R.danger_round(Calm(), ex, 37) is None
    assert R.best(ex, Calm(), 600, 37, 80) == ("wait", None)
    # no income: the step cannot come before round 40 - the $300 is bought
    ex.income = 0.0
    assert R.payable_by(ex, 2000, 600, 40, 37) is False
    status, found = R.best(ex, Calm(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # reachable, but rated below the purchase (a path-3 tier the model gives
    # nothing for): the $300 upgrade comes first
    ex.income = 500.0
    ex.plan[0]["to"] = "0-0-1"
    ex._next_path = lambda p, target: (3, 2000)
    status, found = R.best(ex, Calm(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # an executor without an income figure cannot tell: the step is assumed reachable
    assert R.payable_by(ToyEx(), 2000, 600, 40, 37) is None


def test_a_plan_step_out_of_reach_before_the_round_in_danger_holds_nothing():
    # Ancient Portal Impoppable (2026-11-05): round 94 was rated 0.45 at its
    # start, Perma-Spike ($36,000) was payable before the weakest round (98)
    # but not before the round at hand, and the pick was vetoed "the cash
    # stays for plan step" with $17,562 in the bank; the round was lost.
    class Planned(ToyEx):
        cost = 2000                       # the waiting step; $500 a round comes in

        def __init__(self):
            super().__init__()
            self.plan, self.idx = [{"do": "upgrade", "id": "s1", "to": "0-1-0"}], 0

        def _first_step_cost(self, step):
            return self.cost

        def _next_path(self, p, target):
            return (2, self.cost)

        def income_until(self, due_round, rnd):
            return 500.0 * max(0, due_round - rnd)
    # round 37 itself is in danger (ToyForecast: 0.3, under CRISIS_MARGIN):
    # the step cannot be paid before it from $600, although three rounds of
    # income would pay it before round 40, the weakest - the $300 that
    # lifts round 37 is bought
    ex = Planned()
    assert R.danger_round(ToyForecast(), ex, 37) == 37
    assert R.payable_by(ex, 2000, 600, 40, 37) is True      # the old rule kept the claim
    assert R.payable_by(ex, 2000, 600, 37, 37) is False     # ... but round 37 cannot wait
    status, found = R.best(ex, ToyForecast(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # lives falling this round make it the round in danger whatever the
    # model says; crisis_now keeps its old answer without a round number
    assert R.danger_round(ToyForecast(), ex, 37, lives_dropped=True) == 37
    assert R.crisis_now(ToyForecast(), ex, None, lives_dropped=True)
    assert R.danger_round(ToyForecast(), ex, None, lives_dropped=True) is None

    # the danger can be the next round: 38 is rated 0.3 while 37 holds, and
    # one round of income ($1,100 in all) does not pay the step before 38
    class NextRound(ToyForecast):
        def margin(self, towers, rnd):
            return super().margin(towers, rnd) + (0.0 if rnd in (38, 40) else 1.5)
    ex = Planned()
    assert R.danger_round(NextRound(), ex, 37) == 38
    status, found = R.best(ex, NextRound(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)

    # A weak-but-holding round is no danger: 37 rated 1.2 (under WEAK_MARGIN,
    # over CRISIS_MARGIN) with round 40 at 0.2. The first version of the rule
    # took crisis_now's WEAK_MARGIN and dropped the claim here, although the
    # step is payable before round 40 and the $300 (+0.1) would leave it
    # short of it - the Perma-Spike-eaten failure 7919935 fixed. Ancient
    # Portal's rounds 85-93 (0.58-0.96 at their start) all held like this.
    class Mild(ToyForecast):
        def margin(self, towers, rnd):
            return super().margin(towers, rnd) + (0.0 if rnd == 40 else 0.9)
    ex = Planned()
    assert R.crisis_now(Mild(), ex, 37) and R.danger_round(Mild(), ex, 37) is None
    assert R.best(ex, Mild(), 600, 37, 80) == ("wait", None)

    # a pick that lifts nothing of the round in trouble (the model rates
    # every board 0.2 but credits path 1 with a life saved somewhere)
    class Flat(ToyForecast):
        def margin(self, towers, rnd):
            return 0.2

        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: (101.0 if r == 45 else 100.0) - 10 * sum(t.tiers[0] for t in towers) for r in rounds}
            return lost if per_round else sum(lost.values())
    # the step is out of reach of round 40 but payable before round 45, the
    # weakest: nothing lifts 40, so the pick is judged by round 45 as before
    # and the step keeps the cash (094f8de) - even with BLIND_SPEND_CASH
    # idle, which must not turn a vetoed pick into a blind spend of the
    # step's saving (the blind fallbacks are for the no-pick case)
    ex = Planned()
    ex.cost = 12_000                   # payable before round 45, not before 40
    assert R.danger_round(Flat(), ex, 40) == 40
    assert R.payable_by(ex, 12_000, R.BLIND_SPEND_CASH, 45, 40) is True
    # (enough lives that no round deciding_round looks at ends the game: the
    # round being played and the next ENDING_LOOKAHEAD cost 100 each)
    spare = 100 * (R.ENDING_LOOKAHEAD + 1) + 50
    assert R.best(ex, Flat(), R.BLIND_SPEND_CASH, 40, 80, lives=spare) == ("wait", None)
    ex.cost = 7_000
    assert R.best(ex, Flat(), 5000, 40, 80, lives=spare) == ("wait", None)
    # with 100 lives round 40 alone ends the game (deciding_round): the step
    # cannot be paid before it, so it holds nothing and the pick, which saves
    # 10 of those lives, is bought (Quiet Street Impoppable, 2026-11-06)
    ex.cost = 12_000
    status, found = R.best(ex, Flat(), R.BLIND_SPEND_CASH, 40, 80, lives=100)
    assert status == "buy" and found[1] == 40 and found[0].cost == 300, (status, found)
    # a step income cannot deliver before the weakest round either holds
    # nothing (Quad ABR, 7919935): the pick is bought, the blind fallbacks
    # still do not run on a vetoed pick
    ex.cost = 12_000
    status, found = R.best(ex, Flat(), 5000, 40, 80, lives=100)
    assert status == "buy" and found[0].cost == 300, (status, found)
    ex.cost = 15_000                   # $10,000 + 5 x $500 falls short of it
    status, found = R.best(ex, Flat(), R.BLIND_SPEND_CASH, 40, 80, lives=100)
    assert status == "buy" and found[0].cost == 300, (status, found)


def test_with_one_life_a_pick_that_lifts_nothing_does_not_eat_the_step():
    """Enchanted Glade Impoppable (2026-11-12, loss case 20261112_055921):
    the judged round was always the next one, so Ground Zero ($19,200)
    could never be paid before it and held no cash; purchases rated
    "0.62 -> 0.62" took the bank round after round until round 95 was lost
    with $20,029 in hand. With one life such a pick does not outbid the
    waiting step; with lives to spare it still does (Quiet Street)."""
    class Planned(ToyEx):
        def __init__(self, rules):
            super().__init__()
            self.rules = rules
            self.plan, self.idx = [{"do": "upgrade", "id": "s1", "to": "0-1-0"}], 0

        def _first_step_cost(self, step):
            return 12_000

        def _next_path(self, p, target):
            return (2, 12_000)

        def income_until(self, due_round, rnd):
            return 500.0 * max(0, due_round - rnd)

    class Flat(ToyForecast):
        def margin(self, towers, rnd):
            return 0.2

        def leaks(self, towers, rounds, scale, per_round=False):
            lost = {r: 100.0 - 10 * sum(t.tiers[0] for t in towers) for r in rounds}
            return lost if per_round else sum(lost.values())
    ex = Planned({"one_life": True})
    assert R.payable_by(ex, 12_000, 5000, 40, 40) is False
    assert R.best(ex, Flat(), 5000, 40, 80, lives=1) == ("wait", None)
    # lives to spare: the lives the pick saves count, it is bought
    status, found = R.best(Planned({}), Flat(), 5000, 40, 80, lives=100)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # one life, and a pick that lifts the round: bought as before
    status, found = R.best(Planned({"one_life": True}), ToyForecast(), 600, 37, 80, lives=1)
    assert status == "buy", (status, found)


def test_a_blocked_path_is_not_grown():
    # High Finance Magic Monkeys Only (2026-11-05): wizard2's paths 1 and 3
    # were capped (four clicks without effect each), yet the grown ladder
    # offered "upgrade wizard2 -> 1-2-0 (to grow to 4-2-0)" thirty times
    # over rounds 49-54, each try "skip" without a click, while $3k grew to
    # $24k. A blocked side path is left out and a blocked main path ends
    # the way, so the ladder's first step is on the open path 2 only.
    ex = N(mode="hard", account=None, path_blocked=lambda p, path: path in (1, 3))
    w = N(tid="wizard2", kind="wizard", tiers=(0, 2, 0))
    ways = R.grown_from(ex, "wizard", (0, 2, 0), 50_000, tower=w)
    firsts = {first for first in ways.values() if first}
    assert firsts == {(0, 3, 0)}, ways
    assert all(t[0] == 0 and t[2] == 0 for t in ways), ways
    # a tower not placed yet has no blocked paths
    assert any(f and f[0] > 0 for f in R.grown_from(ex, "wizard", (0, 2, 0), 50_000).values())


def test_a_plan_tower_is_not_grown_off_its_planned_crosspath():
    # Spring Spring CHIMPS (2026-11-12, case 20261112_155459): the plan
    # wanted sb1 at 0-5-0 (Pre-emptive Strike); reinforce grew it to 2-0-1
    # for a weak round 33 and the middle path was shut for good.
    assert not R.keeps_plan_open((2, 0, 1), (0, 5, 0))     # three paths
    assert not R.keeps_plan_open((3, 0, 0), (0, 5, 0))     # two paths past tier 2
    assert R.keeps_plan_open((2, 2, 0), (0, 5, 0))         # 2-5-0 is still a legal crosspath
    assert R.keeps_plan_open((0, 3, 0), (0, 5, 0))
    assert R.keeps_plan_open((2, 0, 1), None)              # the plan never upgrades it

    class Planned(ToyForecast):
        # the top and bottom paths lift the round most, as 2-0-1 did in the model
        def margin(self, towers, rnd):
            return 0.2 + sum(0.4 * t.tiers[0] + 0.1 * t.tiers[1] + 0.6 * t.tiers[2] for t in towers)
    sub = N(tid="sb1", kind="sub", tiers=(0, 0, 0), x=0.5, y=0.5)
    ex = N(mode="hard", account=None, _planned_cap=lambda p: (0, 5, 0) if p.tid == "sb1" else None)
    o = R.grow_standing(ex, Planned(), [sub], "sub", (2, 0, 2), 0.0, 3000, 33, "hard")
    assert o is not None and o is not R.UNJUDGED, o
    goal = R._tiers(o.goal["to"])
    assert R.keeps_plan_open(goal, (0, 5, 0)) and not (goal[0] and goal[2]), o.goal
    # without a plan for the tower any way may be grown, as before: here
    # the one the game ended with, top and bottom
    free = N(mode="hard", account=None)
    o = R.grow_standing(free, Planned(), [sub], "sub", (2, 0, 2), 0.0, 3000, 33, "hard")
    goal = R._tiers(o.goal["to"])
    assert goal[0] and goal[2], o.goal


def test_path_blocked_reads_the_executor_and_the_game():
    import time
    from btd6bot.strategy import Executor
    ex = Executor.__new__(Executor)      # only the fields the gate reads
    ex.capped, ex.unread_until = set(), {}
    ex.g = N(towers={}, _retry_at={})
    p = N(tid="w2", kind="wizard", tiers=(0, 2, 0))
    assert not any(ex.path_blocked(p, path) for path in (1, 2, 3))
    ex.capped.add(("w2", 1))
    assert ex.path_blocked(p, 1) and not ex.path_blocked(p, 3)
    ex.unread_until[("w2", 3)] = time.time() + 10
    assert ex.path_blocked(p, 3)
    ex.g._retry_at[("w2", 2)] = (time.time() + 30, "noeffect", 1)     # Game.upgrade's hold
    assert ex.path_blocked(p, 2)
    ex.g._retry_at[("w2", 2)] = (time.time() - 1, "noeffect", 1)      # over: tried again
    assert not ex.path_blocked(p, 2)
    # one of each tier 5 on the map: another wizard holds path 3's
    ex.capped.clear()
    ex.unread_until.clear()
    ex.g.towers = {"w1": N(tid="w1", kind="wizard", tiers=(0, 2, 5))}
    assert ex.path_blocked(N(tid="w2", kind="wizard", tiers=(0, 2, 4)), 3)
    assert not ex.path_blocked(N(tid="w2", kind="wizard", tiers=(0, 2, 3)), 3)


def test_look_ahead_covers_the_rounds_left():
    assert R.lookahead_rounds(55, 80) == list(range(55, 65))
    assert R.lookahead_rounds(78, 80) == [78, 79, 80]
    assert R.lookahead_rounds(None, 80) == []


class TwoWeakRounds(ToyForecast):
    """Round 40 rated 0.75 (path-1 tiers lift it 0.4 each) and round 48 rated
    0.5 (path-2 tiers lift it 0.5 each); every other round holds. A round
    loses 100 lives per missing unit of margin."""

    def margin(self, towers, rnd):
        t = towers[0].tiers
        if rnd == 40:
            return 0.75 + 0.4 * t[0]
        if rnd == 48:
            return 0.5 + 0.5 * t[1]
        return 3.0

    def leaks(self, towers, rounds, scale, per_round=False):
        lost = {r: max(0.0, 100 * (1 - self.margin(towers, r) * scale)) for r in rounds}
        return lost if per_round else sum(lost.values())


class TwoCheapPaths(ToyEx):
    """The toy tower with two upgrades at the same price."""

    def upgrade_choices(self, first=None, past_plan=False):
        p = self.g.towers["s1"]
        yield p, [1, 0, 0], 300
        yield p, [0, 1, 0], 300


def test_purchases_are_judged_on_the_round_that_ends_the_game():
    # Quiet Street Impoppable (2026-11-06): at round 39 purchases were judged
    # on round 48, which lost the most lives at half strength, while round
    # 40 alone would end the one-life game. Without a lives count the round
    # losing most still decides (path 2, for round 48) ...
    ex = TwoCheapPaths()
    status, found = R.best(ex, TwoWeakRounds(), 300, 39, 80)
    assert status == "buy" and found[1] == 48, (status, found)
    assert R.deciding_round(TwoWeakRounds(), ex, [40, 48], None) is None
    # ... with one life, round 40 ends the game first: path 1 is bought for it
    assert R.deciding_round(TwoWeakRounds(), ex, [40, 48], 1) == 40
    status, found = R.best(ex, TwoWeakRounds(), 300, 39, 80, lives=1)
    assert status == "buy" and found[1] == 40, (status, found)
    assert found[3] > found[2], found       # round 40 really moves
    # with lives to spare for both leaks, nothing changes
    assert R.deciding_round(TwoWeakRounds(), ex, [40, 48], 500) is None


def test_a_game_ending_round_is_seen_a_few_rounds_ahead():
    # Pat's Pond ABR (2026-11-07): round 57 would end the game, but it was
    # only judged on once it was next, too late to buy and grow its answer.
    # ENDING_LOOKAHEAD rounds ahead (round 37 for round 40) it already
    # decides, although round 48 loses more lives at half strength
    ex = TwoCheapPaths()
    status, found = R.best(ex, TwoWeakRounds(), 300, 40 - R.ENDING_LOOKAHEAD, 80, lives=1)
    assert status == "buy" and found[1] == 40, (status, found)
    assert found[3] > found[2], found       # the purchase lifts round 40 itself


def test_a_camo_round_offers_radar_beside_the_main_tower():
    # Tricky Tracks Medium (2026-11-07, case 20261107_014709): round 51's
    # camo ceramics took all 128 lives; the boomerangs carrying the defence
    # saw no camo, and reinforce never rated the village that would have
    # given them sight (it only offered more of the damage kinds standing).
    if not D.available():
        return

    class Rangs(ToyEx):
        def __init__(self, main_kind="boomerang"):
            self.g = N(towers={
                "b1": N(tid="b1", kind=main_kind, tiers=[4, 0, 2], x=0.5, y=0.5),
                "d1": N(tid="d1", kind="dart", tiers=[0, 2, 0], x=0.2, y=0.2)},
                price=lambda kind: T.tower_cost(kind, "medium"))
            self.m = N(cell_to_frac=lambda cx, cy: (0.52, 0.5))
            self.mode = "medium"
            self.asked = []

        def at_tower_cap(self):
            return False

        def pick_spots(self, kind, step, n=1):
            self.asked.append(step)
            return [(10, 10, 1.0)]

    assert R.camo_round(Rangs(), 51) and not R.camo_round(Rangs(), 1)
    ex = Rangs()
    o = R.radar_option(ex, 5000, 51)
    assert o is not None and o.step["kind"] == "village" and o.step["near"] == ["b1"], o
    assert o.step["role"] == "support" and o.cost == T.tower_cost("village", "medium")
    # no camo in the round, no cash, a main tower that sees camo, or a Radar
    # Scanner already standing: nothing offered
    assert R.radar_option(ex, 5000, 1) is None
    assert R.radar_option(ex, 100, 51) is None
    assert R.radar_option(Rangs("ninja"), 5000, 51) is None
    ex.g.towers["v1"] = N(tid="v1", kind="village", tiers=[0, 2, 0], x=0.5, y=0.6)
    assert R.radar_option(ex, 5000, 51) is None

    # grow() rates it at the Radar Scanner when only the scanner helps, and
    # a bare village already standing is grown instead of another bought
    class NeedsRadar(ToyForecast):
        def margin(self, towers, rnd):
            return 2.0 if any(t.kind == "village" and t.tiers[1] >= 2 for t in towers) else 0.1
    ex = Rangs()
    grown = R.grow(ex, NeedsRadar(), [R.radar_option(ex, 5000, 51)], 5000, 51)
    assert grown[0].towers[-1].tiers[1] >= 2 and "to grow to" in grown[0].what, grown
    ex.g.towers["v1"] = N(tid="v1", kind="village", tiers=[0, 0, 0], x=0.5, y=0.6)
    grown = R.grow(ex, NeedsRadar(), [R.radar_option(ex, 5000, 51)], 5000, 51)
    assert grown[0].step == {"do": "upgrade", "id": "v1", "to": "0-1-0"}, grown


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
