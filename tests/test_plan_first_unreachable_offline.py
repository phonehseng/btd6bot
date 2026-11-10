"""A plan_first build lets reinforce spend only when its waiting plan step
cannot be paid before a near round the damage model rates a crisis
(Executor.plan_first_yields, Match._plan_lets_reinforce).

Moon Landing CHIMPS (2026-11-09) lost round 59: from round 50 the model
rated it 0.10, the next plan step was the Archmage (w1 5-0-2, $46,925),
which no income could pay before round 60, and with plan_first nothing else
was bought - "idle with $9388: plan step 20 w1 5-0-2 -> wait" during round
59. The broader crisis exception tried on 2026-11-07 (any crisis of the
round being played) was reverted because Alpine Run CHIMPS spent its Glaive
Lord's cash on rounds rated 0.59-0.99 that passed; those cases still wait.

X Factor Half Cash (2026-11-09) lost round 78 the same way, but the bloons
never got deep (74% most rounds): its 72 camo ceramics took all 78 lives at
once. In a mode with lives a weak round rated at the model's floor
(YIELD_FLOOR) lets the step yield without the depth; CHIMPS still needs it.

Fakes in the style of tests/test_one_life_executor_offline.py and
tests/test_reinforce_offline.py.
Run: python tests/test_plan_first_unreachable_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.match import Match  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_one_life_executor_offline import Fixed, bare_executor, tower  # noqa: E402
from test_reinforce_offline import ToyEx, ToyForecast  # noqa: E402

ARCHMAGE = 46_925      # what was left of w1 -> 5-0-2 at round 55, the step Moon Landing waited on
INCOME = 2_000.0       # about what rounds 55-59 pay in CHIMPS


def moon_landing(cash_round=55, weak=(0.10, 59), cost=ARCHMAGE, plan_first=True, income=INCOME):
    """Round `cash_round` of Moon Landing CHIMPS: the plan's next step costs
    `cost`, the damage model's weakest look-ahead round is `weak` (margin,
    round) and every other round is safe."""
    margin, rnd = weak
    w1 = tower("w1", "wizard", [4, 0, 2])
    step = {"do": "upgrade", "id": "w1", "to": "5-0-2"}
    ex = bare_executor("chimps", [w1], forecast=Fixed(3.0, {rnd: margin}),
                       strat={"plan_first": plan_first, "plan": [step]})
    ex.plan, ex.idx = [step], 0
    ex._first_step_cost = lambda st: cost
    if income is not None:
        ex.income_until = lambda due, r: income * max(0, due - r)
    return ex


# -- Executor.plan_first_yields -------------------------------------------------------
def test_the_moon_landing_case_yields():
    for rnd, cash in ((55, 1_151), (58, 6_649), (59, 9_388)):
        ex = moon_landing(rnd)
        assert R.payable_by(ex, ARCHMAGE, cash, max(59, rnd + 1), rnd) is False
        assert ex.plan_first_yields(cash, rnd), rnd
    assert any(n[0] == "plan-first-yields" for n in ex.noted)


def test_a_step_reachable_before_the_weak_round_keeps_the_cash():
    # $9,000 from $1,151 and four rounds of $2,000: paid before round 59
    ex = moon_landing(55, cost=9_000)
    assert R.payable_by(ex, 9_000, 1_151, 59, 55) is True
    assert not ex.plan_first_yields(1_151, 55)
    # affordable now: the plan buys it itself
    assert not moon_landing(55, cost=1_000).plan_first_yields(1_151, 55)


def test_only_a_near_crisis_round_counts():
    # Alpine Run CHIMPS (2026-11-07 08:49): round 54 rated 0.59, the Glaive
    # Lord ($35,100) out of reach - the round passed; the plan keeps its cash
    assert not moon_landing(49, weak=(0.59, 54), cost=35_100).plan_first_yields(7_162, 49)
    # a crisis round further off than YIELD_ROUNDS: income comes in first
    far = 55 + S.Executor.YIELD_ROUNDS + 1
    assert not moon_landing(55, weak=(0.10, far)).plan_first_yields(1_151, 55)
    # no weak round at all
    assert not moon_landing(55, weak=(3.0, 59)).plan_first_yields(1_151, 55)


def test_nothing_changes_without_plan_first_or_an_income_figure():
    assert not moon_landing(55, plan_first=False).plan_first_yields(1_151, 55)
    ex = moon_landing(55)
    ex.income_until = None                                                  # payable_by None: reachable
    assert not ex.plan_first_yields(1_151, 55)
    # the real income figure (CHIMPS round cash) gives the same answer as the fake
    assert moon_landing(55, income=None).plan_first_yields(1_151, 55)
    ex = moon_landing(55)
    ex.idx = 1                                                              # plan done: plan_first is off
    assert not ex.plan_first_yields(1_151, 55)
    assert not moon_landing(55).plan_first_yields(None, 55)


# -- Match's gate ---------------------------------------------------------------------
DEEP = [{"round": 57, "deepest": 0.96}]     # Moon Landing round 57: bloons 96% along the route


def match(ex, depths=DEEP):
    return N(ex=ex, depths=list(depths))


def test_match_lets_reinforce_in_only_when_the_step_yields():
    gate = Match._plan_lets_reinforce
    assert gate(match(moon_landing(58)), 6_649, 58) is True
    assert gate(match(moon_landing(58, cost=8_000)), 6_649, 58) is False
    assert gate(match(moon_landing(58, plan_first=False)), 6_649, 58) is True   # not plan_first: as before
    assert gate(match(N()), 6_649, 58) is True                                  # an executor without it


def test_the_bloons_must_have_got_deep_too():
    """The won Cracked, Hedge, KartsNDarts and Lotus Island CHIMPS games had
    many rounds with the look-ahead rated under 0.5, but never with the
    bloons past 90% of the route: the model's pessimism alone does not let
    the plan's cash go."""
    gate = Match._plan_lets_reinforce
    assert gate(match(moon_landing(58), [{"round": 57, "deepest": 0.84}]), 6_649, 58) is False
    assert gate(match(moon_landing(58), []), 6_649, 58) is False                # no bloon watch
    assert gate(match(moon_landing(58), [{"round": 57, "deepest": None}]), 6_649, 58) is False
    assert gate(match(moon_landing(58), [{"round": 57, "deepest": 0.90}]), 6_649, 58) is True
    # shallow bloons in CHIMPS and an unreachable step: the plan keeps the cash, nothing logged
    ex = moon_landing(58)
    gate(match(ex, [{"round": 57, "deepest": 0.5}]), 6_649, 58)
    assert not any(n[0] == "plan-first-yields" for n in ex.noted)


# -- the floor rating in a mode with lives (X Factor Half Cash, 2026-11-09) -------------
APACHE = 21_600        # plan step 30, h1 3-2-0 -> 4-2-0 (Apache Dartship), hard prices
XF_INCOME = 700.0      # about what rounds 74-78 pay in Half Cash, counted at 1/LEAD_MARGIN

# the start of rounds 74-78 in the game: cash, and how far the round before's bloons got
X_FACTOR_ROUNDS = ((74, 4_004, 0.33), (75, 7_108, 0.74), (76, 9_835, 0.81), (77, 11_210, 0.74),
                   (78, 13_810, 0.74))


def x_factor(rnd, weak=(0.06, 78), income=XF_INCOME):
    """Round `rnd` of X Factor Half Cash: the plan waits for the Apache
    Dartship on h1 and the model rates round `weak[1]` at `weak[0]`."""
    margin, wr = weak
    h1 = tower("h1", "heli", [3, 2, 0])
    step = {"do": "upgrade", "id": "h1", "to": "4-2-0"}
    ex = bare_executor("half_cash", [h1], forecast=Fixed(3.0, {wr: margin}),
                       strat={"plan_first": True, "plan": [step]})
    ex.plan, ex.idx = [step], 0
    ex._first_step_cost = lambda st: APACHE
    if income is not None:
        ex.income_until = lambda due, r: income * max(0, due - r)
    return ex


def test_x_factor_floor_rating_yields_without_depth():
    gate = Match._plan_lets_reinforce
    for rnd, cash, depth in X_FACTOR_ROUNDS:
        ex = x_factor(rnd)
        assert R.payable_by(ex, APACHE, cash, max(78, rnd + 1), rnd) is False
        assert ex.plan_first_yields(cash, rnd, deep=False), rnd
        assert gate(match(ex, [{"round": rnd - 1, "deepest": depth}]), cash, rnd) is True, rnd
    assert any(n[0] == "plan-first-yields" for n in ex.noted)
    # the real Half Cash income figure (the round set's cash, halved) agrees at round 74
    assert x_factor(74, income=None).plan_first_yields(4_004, 74, deep=False)
    # no bloon watch at all: the floor rating alone still counts
    assert gate(match(x_factor(77), []), 11_210, 77) is True


def test_the_floor_rule_is_narrow():
    # rated over YIELD_FLOOR: Spillway Half Cash won round 78 rated 0.14 with
    # the same build and the same waiting step; deep bloons still count as before
    assert not x_factor(74, weak=(0.14, 78)).plan_first_yields(9_955, 74, deep=False)
    assert x_factor(74, weak=(0.14, 78)).plan_first_yields(9_955, 74, deep=True)
    # the near-round and reachability tests still apply
    assert not x_factor(70).plan_first_yields(18_345, 70, deep=False)      # round 78 is 8 rounds off
    ex = x_factor(77)
    ex._first_step_cost = lambda st: 11_800                                # $11,210 + a round's income
    assert not ex.plan_first_yields(11_210, 77, deep=False)


def test_dark_castle_rating_just_over_the_old_floor_yields():
    """Dark Castle Half Cash (2026-11-09 13:21, hard_ninja_alch_sun) lost round
    78 rated 0.112: rounds 76-77 began with $4,800 and $6,630 while the plan
    waited for h1 4-2-0 ($21,600), the bloons never past 66% of the route.
    The old 0.10 floor kept that cash for the step; 0.12 lets it go."""
    for rnd, cash in ((76, 4_800), (77, 6_630)):
        ex = x_factor(rnd, weak=(0.112, 78))
        assert ex.plan_first_yields(cash, rnd, deep=False), rnd
        assert Match._plan_lets_reinforce(match(ex, [{"round": rnd - 1, "deepest": 0.66}]), cash, rnd) is True


def test_chimps_floor_rating_still_needs_depth():
    """Cracked CHIMPS (2026-11-07) won with rounds 56 and 59 rated 0.06 from
    round 52 on while $15-26k waited for its $28,080 step: in a one-life
    mode the floor rating alone does not let the plan's cash go."""
    assert not moon_landing(55, weak=(0.06, 59)).plan_first_yields(1_151, 55, deep=False)
    assert moon_landing(55, weak=(0.06, 59)).plan_first_yields(1_151, 55, deep=True)
    shallow = [{"round": 54, "deepest": 0.6}]
    assert Match._plan_lets_reinforce(match(moon_landing(55, weak=(0.06, 59)), shallow), 1_151, 55) is False


# -- end to end: the gate, then reinforce's own choice -----------------------------------
class PlanFirstToy(ToyEx):
    """ToyEx (one sniper, a $300 and a $2,000 upgrade) as a plan_first build
    whose next step is the $2,000 upgrade, with the executor's own
    plan_first rules and look-ahead rating."""
    plan_first = S.Executor.plan_first
    plan_first_yields = S.Executor.plan_first_yields
    # plan_first asks this since 10eddc4 (free `do: ability` steps hold no cash)
    _only_free_steps_left = S.Executor._only_free_steps_left
    lookahead_worst = S.Executor.lookahead_worst
    _rated = S.Executor._rated
    _forecast = S.Executor._forecast
    _board_key = S.Executor._board_key
    _notes = S.Executor._notes
    YIELD_MARGIN, YIELD_ROUNDS = S.Executor.YIELD_MARGIN, S.Executor.YIELD_ROUNDS

    def __init__(self, income):
        super().__init__()
        self.income = income
        self.rules = S.rules("chimps")
        self.forecast = Rated()
        self.plan, self.idx = [{"do": "upgrade", "id": "s1", "to": "0-1-0"}], 0
        self.strat = {"plan_first": True, "plan": self.plan}
        self.noted = set()

    def _first_step_cost(self, step):
        return 2000

    def _next_path(self, p, target):
        return (2, 2000)

    def income_until(self, due_round, rnd):
        return self.income * max(0, due_round - rnd)


class Rated(ToyForecast):
    """ToyForecast with the weakest-round question the executor asks: round
    40 is the weakest (0.2 with the bare sniper)."""

    def worst(self, towers, rounds, iterations=9):
        return min((self.margin(towers, r), r) for r in rounds) if rounds else None


def test_unreachable_step_reinforce_buys_reachable_step_waits():
    # $300 a round: $600 + 3 x $300 cannot pay the $2,000 step before round 40
    ex = PlanFirstToy(income=300.0)
    assert ex.lookahead_worst(37) == (0.2, 40) or ex.lookahead_worst(37)[1] == 40
    assert Match._plan_lets_reinforce(match(ex), 600, 37)
    assert R.buy_best(ex, ex.forecast, 600, 37, 100) == "bought"
    assert ex.bought and ex.bought[-1]["to"] == "1-0-0", ex.bought
    # $500 a round: $2,100 before round 40 - the plan waits as before, and
    # Match never asks reinforce
    ex = PlanFirstToy(income=500.0)
    assert not Match._plan_lets_reinforce(match(ex), 600, 37)
    assert not ex.bought


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
