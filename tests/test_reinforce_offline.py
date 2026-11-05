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


def test_no_saving_when_the_rounds_before_cost_the_lives_left():
    # Cargo Double HP (2026-11-03): saving for round 79 lost round 75.
    # Rounds 37-39 each cost 7 lives at full strength (ToyForecast): with
    # 15 lives left the game would end before the $2,000 upgrade arrives,
    # so the affordable $300 one is bought now.
    ex = ToyEx()
    status, found = R.best(ex, ToyForecast(), 1000, 37, 80, lives=15)
    assert status == "buy" and found[0].cost == 300, (status, found)
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
    # one (+0.1) would eat into the saving.
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
    assert R.best(ex, ToyForecast(), 600, 37, 80) == ("wait", None)
    # no income: the step cannot come before round 40 - the $300 is bought
    ex.income = 0.0
    assert R.payable_by(ex, 2000, 600, 40, 37) is False
    status, found = R.best(ex, ToyForecast(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # reachable, but rated below the purchase (a path-3 tier the model gives
    # nothing for): the $300 upgrade comes first
    ex.income = 500.0
    ex.plan[0]["to"] = "0-0-1"
    ex._next_path = lambda p, target: (3, 2000)
    status, found = R.best(ex, ToyForecast(), 600, 37, 80)
    assert status == "buy" and found[0].cost == 300, (status, found)
    # an executor without an income figure cannot tell: the step is assumed reachable
    assert R.payable_by(ToyEx(), 2000, 600, 40, 37) is None


def test_look_ahead_covers_the_rounds_left():
    assert R.lookahead_rounds(55, 80) == list(range(55, 65))
    assert R.lookahead_rounds(78, 80) == [78, 79, 80]
    assert R.lookahead_rounds(None, 80) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
