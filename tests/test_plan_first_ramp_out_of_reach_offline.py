"""With one life, a plan_first build's plan stops being its blimp ramp when
the blimp check reads a round far short and the plan's next step cannot be
paid before it; and a blimp round read that far short is not given away to
a round rated lost further on.

Pat's Pond Impoppable (2026-11-13 08:58-09:28, patspond_impoppable; loss case
20261113_093144_PatsPond_impoppable): the first game with backlog 110's fix.
Round 90's camo DDTs were held this time (the sub's Pre-emptive Strike,
bought at rounds 75-76). From round 77 the plan waited for the Super Mines
(spi_carry1 -> 5-0-2), which the bank could not reach before round 91. The
blimp check read rounds 85, 87 and 88 at 0.1-0.3x of its 2.5x one-life bar
and logged "buying blimp damage that can", but under plan_first the ramp
answered "plan" and bought nothing (Executor._answer_ramp). From round 89 it
yielded instead to rounds 98 and 100, rated 0.46 and 0.27 (likely lost):
round 89 was rated 2.04, round 91 1.13 (_ramp_yields_to_lost_round). The
bank grew from $24k at round 79 to $101,163 at round 91, and round 91's
twenty BFBs (blimp check 0.2x; journal: blimp_ratio 0.175) took the life.

Held here on the lost game's own board, which stood unchanged from round
77 to the end (built from the case's journal.jsonl place/upgrade events).

Run: python tests/test_plan_first_ramp_out_of_reach_offline.py"""
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

MAP, MODE, BUILD = "Pat's Pond", "impoppable", "patspond_impoppable"
CASH = {85: 77_530, 87: 84_678, 88: 89_539, 89: 96_561, 91: 101_163}   # the log's "round N  cash" lines
WAITING = ("spi_carry1", "5-0-2")      # "idle with $...: plan step 111 spi_carry1 -> 5-0-2"
BOARD = [
    ("n1", "ninja", "4-0-2", 0.772, 0.368), ("hero", "hero", "0-0-0", 0.777, 0.572),
    ("a1", "alchemist", "3-0-0", 0.804, 0.419), ("b1", "buccaneer", "0-4-2", 0.665, 0.351),
    ("sb1", "sub", "2-0-4", 0.633, 0.683), ("bo1", "bomb", "0-2-4", 0.804, 0.624),
    ("v1", "village", "0-0-0", 0.815, 0.334), ("spi_carry1", "spike", "4-0-2", 0.077, 0.589),
    ("buc502", "buccaneer", "2-0-1", 0.227, 0.743), ("buc503", "buccaneer", "2-0-1", 0.216, 0.854),
    ("sky504", "skywarden", "1-0-0", 0.099, 0.377), ("sky505", "skywarden", "2-0-1", 0.077, 0.675),
    ("sky506", "skywarden", "1-0-0", 0.077, 0.334), ("sky507", "skywarden", "1-0-1", 0.761, 0.658),
    ("sky508", "skywarden", "1-0-1", 0.067, 0.419), ("sky509", "skywarden", "2-0-1", 0.045, 0.717),
    ("sky510", "skywarden", "1-0-0", 0.051, 0.368), ("sky511", "skywarden", "1-0-1", 0.12, 0.334),
    ("dru512", "druid", "1-3-0", 0.035, 0.572), ("boo513", "boomerang", "0-2-3", 0.761, 0.308),
    ("eng514", "engineer", "3-1-0", 0.27, 0.095), ("buc515", "buccaneer", "0-3-1", 0.259, 0.828),
    ("buc516", "buccaneer", "2-0-2", 0.206, 0.368), ("sni517", "sniper", "0-2-2", 0.233, 0.095),
    ("sni518", "sniper", "0-2-2", 0.601, 0.078), ("sni519", "sniper", "0-2-2", 0.644, 0.078),
    ("sni520", "sniper", "0-2-2", 0.687, 0.078), ("s1", "sniper", "4-2-0", 0.729, 0.896),
    ("sni521", "sniper", "0-2-2", 0.184, 0.095), ("sni522", "sniper", "0-2-2", 0.174, 0.146),
    ("sni523", "sniper", "0-2-2", 0.142, 0.112), ("sni524", "sniper", "0-2-2", 0.719, 0.112),
    ("buc525", "buccaneer", "0-3-1", 0.281, 0.726), ("buc526", "buccaneer", "0-3-1", 0.58, 0.734),
    ("sub527", "sub", "2-5-0", 0.238, 0.266), ("mer528", "mermonkey", "0-0-0", 0.591, 0.658),
]


def _setup(rnd, one_life=True):
    """The executor at the start of round `rnd`: the board standing, the
    plan waiting at the Super Mines step, the log's cash in hand."""
    m = G.apply(SETUP.MapModel(MAP, SETUP.LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SETUP.SIM.CashGame(MODE, "obyn", m)
    g.cash, g.round = CASH[rnd], rnd
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SETUP.SIM.full_account())
    for tid, kind, cross, x, y in BOARD:
        g.towers[tid] = SETUP.SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = next(i for i, st in enumerate(ex.plan)
                  if st.get("id") == WAITING[0] and st.get("to") == WAITING[1])
    ex._init_threats()
    ex.cash_seen = CASH[rnd]
    if not one_life:
        ex.rules = dict(ex.rules, one_life=False)
    return ex


def _ready():
    return D.available() and TH.available()


def _ratio(ex, rnd):
    """(blimp check reading, its bar) for blimp round `rnd`."""
    load = ex.blimp_load(rnd)
    return ex.blimp_ratio(load), ex.ramp_bar(load)


def test_the_board_reads_as_it_did_live():
    """Rounds 87 and 91 read far short in the blimp check, under RAMP_PANIC,
    with the plan waiting for a step it cannot pay before them."""
    if not _ready():
        return
    for rnd in (87, 91):
        ex = _setup(rnd)
        assert ex.plan_first()
        ratio, bar = _ratio(ex, rnd)
        assert ratio < ex.RAMP_PANIC < bar, (rnd, ratio)
        assert ex._plan_step_out_of_reach(ex.plan[ex.idx], CASH[rnd], rnd)
        print(f"round {rnd}: blimp check {ratio:.2f}x of {bar:.1f}x, plan step {ex.plan[ex.idx]} out of reach")


def test_the_plan_gives_its_ramp_turn_away():
    """Round 87: the ramp buys blimp damage where the plan answered "plan"
    and nothing was bought."""
    if not _ready():
        return
    ex = _setup(87)
    ratio, _ = _ratio(ex, 87)
    assert ex._plan_first_gives_up_ramp(87, ratio, CASH[87])
    ex.saving_for_threat = False
    ex._threat_tick(CASH[87], 87)
    assert ex.g.bought, "nothing bought for round 87's blimps"
    print("round 87 bought:", ex.g.bought[:6])


def test_without_the_rule_nothing_was_bought():
    """The live behaviour: with the plan keeping its turn the threat tick
    buys nothing for round 87."""
    if not _ready():
        return
    ex = _setup(87)
    ex._plan_first_gives_up_ramp = lambda *a: False
    ex.saving_for_threat = False
    ex._threat_tick(CASH[87], 87)
    assert not ex.g.bought, ex.g.bought


def test_a_far_short_blimp_round_is_not_given_away():
    """Round 91 (0.2x) does not yield to rounds 98/100 rated lost; a
    reading over RAMP_PANIC still may (test_ramp_yields_to_lost_round)."""
    if not _ready():
        return
    ex = _setup(91)
    ratio, _ = _ratio(ex, 91)
    assert not ex._ramp_yields_to_lost_round(91, 91, ratio)


def test_with_lives_to_spare_the_plan_keeps_its_turn():
    """The rule is for one-life games."""
    if not _ready():
        return
    ex = _setup(87, one_life=False)
    ratio, _ = _ratio(ex, 87)
    assert not ex._plan_first_gives_up_ramp(87, ratio, CASH[87])


def test_over_ramp_ok_the_plan_keeps_its_turn():
    """Sulfur Springs CHIMPS (case 20261113_085155) read round 60 at 2.1x
    of 2.5x with its Archmage out of reach: there the plan keeps the cash.
    So it does from 1x on (RAMP_OK), the readings of the rounds that held
    in the build's next game."""
    if not _ready():
        return
    ex = _setup(87)
    for ratio in (ex.RAMP_OK, 1.6, 2.1):
        assert not ex._plan_first_gives_up_ramp(87, ratio, CASH[87]), ratio


def test_a_reading_just_over_ramp_panic_gives_the_turn_away_too():
    """The build's next game (case 20261113_130204): the ramp's own buys of
    rounds 81-84 lifted rounds 87-91 to 0.4-0.5x, over RAMP_PANIC; the plan
    took its turn back, nothing more was bought and round 91 took the life
    with $57,329 idle. Under RAMP_OK the plan's turn stays given away."""
    if not _ready():
        return
    for rnd in (87, 91):
        ex = _setup(rnd)
        for ratio in (0.44, 0.5, 0.9):
            assert ex.RAMP_PANIC < ratio < ex.RAMP_OK
            assert ex._plan_first_gives_up_ramp(rnd, ratio, CASH[rnd]), (rnd, ratio)


def test_a_given_away_turn_does_not_yield_to_a_lost_round():
    """Round 91 read at 0.5x, rounds 98 and 100 rated lost: yielding would
    leave the cash to a plan step that cannot be paid and to reinforcing,
    which a plan_first build gives no turn - so the blimp check keeps it.
    With the Super Mines in reach (money enough) the old rule decides."""
    if not _ready():
        return
    ex = _setup(91)
    assert not ex._ramp_yields_to_lost_round(91, 91, 0.5)
    ex.saving_for_threat = False

    ex.blimp_ratio = lambda load: 0.5   # the second game's reading of its late blimp rounds
    ex._threat_tick(CASH[91], 91)
    assert ex.g.bought, "nothing bought for round 91's blimps at 0.5x"
    print("round 91 at 0.5x bought:", ex.g.bought[:6])



def test_not_in_chimps():
    """CHIMPS keeps the plan as its ramp: there the blimp check reads the
    guide builds' late boards far short as a rule, and with the rule the
    offline threat simulation left four guide builds a step or two short."""
    if not _ready():
        return
    ex = _setup(87)
    ratio, _ = _ratio(ex, 87)
    ex.mode = "chimps"
    assert not ex._plan_first_gives_up_ramp(87, ratio, CASH[87])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
