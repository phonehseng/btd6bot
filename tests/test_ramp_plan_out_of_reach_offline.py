"""With one life, a plan step that cannot be paid before a blimp round the
blimp check reads short gives its turn to blimp damage at once.

Party Parade Impoppable (2026-11-10 21:29-21:49, chimps_ninja_sun; loss case
20261110_214932_PartyParade_impoppable): at round 70 the blimp check read
round 75's seven BFBs (11,700 blimp HP) at 1.3x of the 2.5x one-life bar.
The plan waited for the Sun Avatar (s1 -> 3-0-2, $24,000) with $5,157 in
hand - reinforce itself logged "cannot be paid before round 79" - and the
ramp answered "plan" in rounds 70-72, because the plan keeps its turn until
two rounds before the blimps. Reinforce spent that cash on Super Monkey
tiers rated "0.63 -> 0.63" for rounds 76-79, and round 75 took the one life.

Offline on Party Parade's geometry with the round-70 board of the log's
purchase lines (tools/rate_board.py board_from_log, stop 21:47:29).
Run: python tests/test_ramp_plan_out_of_reach_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from btd6bot import dps_model as D                      # noqa: E402
from btd6bot import mapgeom as G                        # noqa: E402
from btd6bot import strategy as S                       # noqa: E402
from btd6bot import threats as TH                       # noqa: E402
import test_reinforce_budget_offline as SETUP           # noqa: E402  (MapModel, LAYOUTS, SIM)

MAP, MODE, BUILD = "Party Parade", "impoppable", "chimps_ninja_sun"
RND, BLIMP_ROUND, CASH = 70, 75, 5_157
LIVE_RATIO = 1.3                       # "the defence deals about 1.3x that in reach"
BOARD_70 = [
    ("n1", "ninja", "4-0-2", 0.644, 0.564), ("hero", "hero", "0-0-0", 0.216, 0.436),
    ("n2", "ninja", "2-0-4", 0.206, 0.521), ("a1", "alchemist", "3-2-0", 0.761, 0.632),
    ("ninja1", "ninja", "4-0-1", 0.612, 0.198), ("ninja2", "ninja", "4-0-2", 0.243, 0.836),
    ("ninja3", "ninja", "0-0-0", 0.644, 0.181), ("ninja5", "ninja", "4-0-2", 0.628, 0.402),
    ("ans_blimps_ace", "ace", "4-2-0", 0.329, 0.564), ("ace1", "ace", "4-1-0", 0.532, 0.547),
    ("ans_blimps_bomb", "bomb", "0-4-2", 0.238, 0.198), ("v1", "village", "2-0-2", 0.633, 0.487),
    ("ninja6", "ninja", "0-0-0", 0.665, 0.24), ("ninja7", "ninja", "3-0-0", 0.211, 0.768),
    ("ace3", "ace", "2-3-0", 0.542, 0.436), ("bomb1", "bomb", "2-0-2", 0.612, 0.138),
    ("bomb2", "bomb", "3-0-2", 0.216, 0.589), ("s1", "super", "2-0-2", 0.644, 0.785),
    ("bomb3", "bomb", "0-2-2", 0.206, 0.828), ("ace4", "ace", "2-3-0", 0.329, 0.428),
    ("ace5", "ace", "2-3-0", 0.131, 0.802), ("ans_blimps_super", "super", "1-2-0", 0.195, 0.155),
    ("super1", "super", "2-2-0", 0.692, 0.164), ("ace6", "ace", "4-1-0", 0.035, 0.828),
    ("ace7", "ace", "0-0-0", 0.168, 0.896), ("ninja8", "ninja", "0-0-0", 0.254, 0.598),
    ("ninja9", "ninja", "0-0-0", 0.094, 0.513), ("ace8", "ace", "2-3-0", 0.067, 0.334),
]


def _setup(cash=CASH):
    """The round-70 executor: the board standing, the plan waiting at the
    Sun Avatar step (s1 -> 3-0-2), `cash` in hand."""
    m = G.apply(SETUP.MapModel(MAP, SETUP.LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SETUP.SIM.CashGame(MODE, "obyn", m)
    g.cash, g.round = cash, RND
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SETUP.SIM.full_account())
    for tid, kind, cross, x, y in BOARD_70:
        g.towers[tid] = SETUP.SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = next(i for i, st in enumerate(ex.plan) if st.get("do") == "upgrade" and st.get("id") == "s1")
    ex._init_threats()
    ex.cash_seen = cash
    return ex


def _ramp(ex):
    """What the blimp ramp answers for round 75 on ex's board."""
    load = ex.blimp_load(BLIMP_ROUND)
    return ex._answer_ramp(BLIMP_ROUND, load, ex.blimp_ratio(load), ex.g.cash, RND)


def test_the_board_reads_short_as_it_did_live():
    """The rebuilt board reads round 75 close to the live 1.3x, under the bar."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    load = ex.blimp_load(BLIMP_ROUND)
    ratio = ex.blimp_ratio(load)
    assert abs(ratio - LIVE_RATIO) < 0.2 and ratio < ex.ramp_bar(load), (ratio, ex.ramp_bar(load))


def test_an_unreachable_plan_step_gives_its_turn_to_blimp_damage():
    """Five rounds before the BFBs, with the Sun Avatar out of reach, the
    ramp buys blimp damage instead of answering "plan"."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    income = sum(TH.round_cash(ex.round_set, r) * ex.income_mult for r in range(RND, BLIMP_ROUND))
    assert ex._first_step_cost(ex.plan[ex.idx]) > CASH + income      # the Sun Avatar, out of reach
    answer = _ramp(ex)
    assert answer == "bought", answer
    assert ex.g.bought, "nothing bought"
    print(f"round {RND}: the ramp bought {ex.g.bought[0][1]} for round {BLIMP_ROUND}")


def test_a_step_income_can_pay_before_the_blimps_keeps_its_turn():
    """With the Sun Avatar payable before round 75 from cash and income
    (but not yet from cash alone), the plan keeps its turn as before."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    step_cost = ex._first_step_cost(ex.plan[ex.idx])
    income = sum(TH.round_cash(ex.round_set, r) * ex.income_mult for r in range(RND, BLIMP_ROUND))
    ex = _setup(cash=step_cost - income / 2)          # short now, paid half-way through the income
    answer = _ramp(ex)
    assert answer in ("plan", "plan_hold"), answer
    assert not ex.g.bought


def test_with_lives_to_lose_the_plan_keeps_its_turn():
    """The rule is for one-life modes: elsewhere the plan still gets its
    turn until the round before the blimps."""
    if not D.available() or not TH.available():
        return
    ex = _setup()
    ex.rules = {**ex.rules, "one_life": False, "lives": 100}
    assert _ramp(ex) == "plan"
    assert not ex.g.bought


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
