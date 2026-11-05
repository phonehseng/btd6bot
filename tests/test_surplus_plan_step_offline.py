"""Offline checks for the rules from Ancient Portal Impoppable (2026-11-05,
lost at round 94 with $17,562 in the bank while plan step 25, Perma-Spike
for $36,000, had waited since round 63):

* in a one-life mode surplus() leaves a waiting plan step its claim on
  the bank (plan_claim):
  the whole cost when the step has no round, the cost less the income until
  its round when it has one, in a crisis only what income cannot rebuild -
  and then only a purchase that lifts the round being played may spend the
  rest; a step no income can pay before the weak round - the next round in
  a crisis of the round being played - holds nothing;
* _hold_for holds nothing for a round already being played while that round
  is weak (and all of it in a safe round, as before), prices an unpriced
  answer by its next tier, and holds an answer of unknown cost only while
  the round being played is safe; Match's idle line names a hold only when
  the cash is held in full;
* _steps_cost prices the steps it can and _wait_total never leaves
  wait_total None after a "wait";
* a plan upgrade for a tower that has popped nothing (n2 on the walled left
  lane) places a fresh tower of its kind under the step's id instead, in
  no-sell modes too, where sell_useless now reads the pop counts as well.

Fakes in the style of tests/test_one_life_executor_offline.py.
Run: python tests/test_surplus_plan_step_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_one_life_executor_offline import Fixed, bare_executor, tower  # noqa: E402

INCOME = 1500.0          # dollars a round the fakes count on (Executor.income_until stands in)


def portal(margin, cost=36_000, step_round=None, income=INCOME):
    """Round 70 of Impoppable: the plan's next step is sp1 -> 2-0-5 and costs
    `cost`; surplus has a $300 and a $2,000 tier to choose from and records
    what it buys with how much cash."""
    sp1 = tower("sp1", "spike", [2, 0, 4])
    s1 = tower("s1", "sniper", [0, 0, 0], crosspath="0-0-0")
    ex = bare_executor("impoppable", [sp1, s1], forecast=Fixed(margin))
    step = {"do": "upgrade", "id": "sp1", "to": "2-0-5"}
    if step_round:
        step["round"] = step_round
    ex.plan, ex.idx = [step], 0
    ex._first_step_cost = lambda st: cost
    ex._ramp_due = lambda rnd: None
    ex.income_until = lambda due, rnd: income * max(0, due - rnd)
    ex.saving_for_threat, ex.held_cash = False, 0.0
    ex.upgrade_choices = lambda first=None, past_plan=False: iter([(s1, [1, 0, 0], 300), (s1, [0, 1, 0], 2000)])
    ex._main_kind = lambda: None
    ex.bought = []

    def try_step(st, cash, rnd):
        ex.bought.append((st["to"], cash))
        return "bought"
    ex.try_step = try_step
    return ex


# -- the plan step's claim --------------------------------------------------------
def test_a_step_without_a_round_keeps_its_whole_cost():
    ex = portal(3.0)
    keep, idx, step, cost, crisis = ex.plan_claim(20_000, 70)
    assert (keep, idx, cost, crisis) == (36_000, 0, 36_000, False) and step["id"] == "sp1"
    assert ex.surplus(20_000, 70) is False and not ex.bought       # nothing lies above the claim
    # the step bought (or affordable): no claim, surplus spends as before
    ex._first_step_cost = lambda st: 15_000
    assert ex.plan_claim(20_000, 70) is None
    assert ex.surplus(20_000, 70) is True and ex.bought == [("1-0-0", 20_000)]
    # with lives to spare the plan is a guide: no claim on Hard, nor with no income
    hard = portal(3.0)
    hard.rules = S.rules("hard")
    assert hard.plan_claim(20_000, 70) is None
    assert hard.surplus(20_000, 70) is True and hard.bought == [("1-0-0", 20_000)]


def test_with_lives_to_spare_the_step_claims_the_bank_only_while_the_lookahead_is_weak():
    """Workshop Medium (2026-11-05): round 25, $1,957 against the $2,000
    MOAB Press step, round 34 rated 0.08 - reinforce left the cash to the
    step and surplus bought a 3-0-2 boomerang with it instead."""
    ex = portal(3.0, cost=2_000)
    ex.rules = S.rules("medium")
    ex.forecast = Fixed(3.0, {34: 0.08})
    assert ex.plan_claim(1_957, 25) is None          # no match loop reinforcing: a guide, as before
    ex.lookahead_weak = True                          # Match found the look-ahead weak
    keep, idx, step, cost, crisis = ex.plan_claim(1_957, 25)
    assert (keep, cost, crisis) == (2_000, 2_000, False)
    assert ex.surplus(1_957, 25) is False and not ex.bought
    # a step no income can pay before the weak round holds nothing there either
    ex = portal(3.0, cost=200_000)
    ex.rules = S.rules("medium")
    ex.forecast = Fixed(3.0, {34: 0.08})
    ex.lookahead_weak = True
    assert ex.plan_claim(1_957, 25) is None and ex.surplus(1_957, 25) is True


def test_a_step_with_a_round_keeps_what_income_does_not_pay():
    ex = portal(3.0, cost=10_000, step_round=74)         # four rounds of income: $6,000
    keep = ex.plan_claim(8_000, 70)[0]
    assert keep == 4_000, keep
    assert ex.surplus(8_000, 70) is True and ex.bought == [("1-0-0", 4_000)]
    # a step whose round has come keeps all of it (no income before it)
    ex = portal(3.0, cost=10_000, step_round=70)
    assert ex.plan_claim(8_000, 70)[0] == 10_000 and ex.surplus(8_000, 70) is False


def test_an_unpayable_step_holds_nothing():
    """Quad ABR (7919935): a step no income can pay before the weak round is
    no reason to sit on the cash."""
    ex = portal(Fixed(3.0, {75: 0.5}).m, cost=200_000)
    ex.forecast = Fixed(3.0, {75: 0.5})
    assert ex.plan_claim(8_000, 70) is None
    assert ex.surplus(8_000, 70) is True and ex.bought == [("1-0-0", 8_000)]
    assert any(n[0] == "surplus-unpayable" for n in ex.noted)


def test_a_step_unpayable_before_the_next_round_holds_nothing_in_a_crisis():
    """The loss round itself: round 94 rated 0.41, $17,562 in hand, the
    $36,000 step and about $1,000 a round of income. The crisis rule alone
    would keep cost less one round's income - the whole bank - for a step
    no income can pay before round 95; it keeps nothing, and surplus spends
    as before the claim (reinforce's 7919935 rule holds nothing either)."""
    ex = portal(0.41, cost=36_000, income=1_000)
    assert R.payable_by(ex, 36_000, 17_562, 94, 94) is False
    assert ex.plan_claim(17_562, 94) is None
    assert any(n == ("surplus-unpayable", 0, 95) for n in ex.noted)
    assert ex.surplus(17_562, 94) is True and ex.bought == [("1-0-0", 17_562)]
    # the same a round earlier with the weak round next (Quad ABR's shape:
    # round 62, round 63 rated 0.5, a $35,100 Glaive Lord against $15,000)
    ex = portal(3.0, cost=35_100)
    ex.forecast = Fixed(3.0, {63: 0.5})
    assert ex.plan_claim(15_000, 62) is None
    assert ex.surplus(15_000, 62) is True and ex.bought == [("1-0-0", 15_000)]
    # payable by the next round from the cash and one round's income: kept
    ex = portal(0.41, cost=18_000, income=1_000)
    keep, _, _, _, crisis = ex.plan_claim(17_562, 94)
    assert crisis and keep == 17_000, keep


def test_in_a_crisis_only_a_lifting_purchase_spends_the_rest():
    # round 70 rated 0.4: the step keeps cost less one round's income
    ex = portal(0.4, cost=10_000)
    keep, _, _, _, crisis = ex.plan_claim(9_900, 70)
    assert crisis and keep == 10_000 - INCOME, keep
    ex._lifts_now = lambda step, cost, rnd: step["to"] == "0-1-0"
    # $1,400 spare: the $300 tier does not lift round 70, the $2,000 one is too dear
    assert ex.surplus(9_900, 70) is False and not ex.bought
    # with the step's round far off the whole bank is spare, and the lifting tier is bought
    ex = portal(0.4, cost=10_000, step_round=80)
    ex._lifts_now = lambda step, cost, rnd: step["to"] == "0-1-0"
    assert ex.plan_claim(9_900, 70)[0] == 0.0
    assert ex.surplus(9_900, 70) is True and ex.bought == [("0-1-0", 9_900)]


def test_the_claim_is_said_once_per_step():
    ex = portal(3.0)
    ex.surplus(20_000, 70)
    ex.surplus(21_000, 70)
    assert sum(n[0] == "surplus-claim" for n in ex.noted) == 1


class Lifting:
    """Rounds 70-71 rate 0.4 plus 0.8 per path-2 tier; the rest is safe."""

    def margin(self, towers, rnd):
        return 0.4 + sum(0.8 * t.tiers[1] for t in towers) if rnd in (70, 71) else 3.0

    def worst(self, towers, rounds, iterations=9):
        return min((self.margin(towers, r), r) for r in rounds) if rounds else None


def test_lifts_now_rates_the_round_being_played():
    ex = portal(0.4)
    ex.forecast = Lifting()
    ex._next_path = lambda p, target: (2, 2000) if target[1] else (1, 300)
    assert ex._lifts_now({"do": "upgrade", "id": "s1", "to": "0-1-0"}, 2000, 70) is True
    assert ex._lifts_now({"do": "upgrade", "id": "s1", "to": "1-0-0"}, 300, 70) is False
    assert ex._lifts_now({"do": "upgrade", "id": "gone", "to": "1-0-0"}, 300, 70) is False
    ex.forecast = None
    assert ex._lifts_now({"do": "upgrade", "id": "s1", "to": "0-1-0"}, 2000, 70) is False


# -- holds ----------------------------------------------------------------------
def holder(margin):
    ex = portal(margin)
    ex.wait_cost = None
    return ex


def test_nothing_is_held_for_a_round_being_played_while_it_is_weak():
    for due in (94, 93):
        ex = holder(0.25)
        assert ex._hold_for(due, 40_000, 94, "blimp damage") is None
        assert not ex.saving_for_threat and ex.held_cash == 0.0
        assert ("playing-hold", "blimp damage", 94) in ex.noted
    # a safe round holds as before: round 40's MOAB answer is still wanted in
    # round 41 (a strength threat is due through r + 1), and nothing presses
    for due in (40, 41, 42):
        ex = holder(2.5)
        assert ex._hold_for(due, 9_000, 41, "the moab answer") is False and ex.saving_for_threat
    ex = holder(2.5)
    assert ex._hold_for(95, 40_000, 94, "blimp damage") is False and ex.saving_for_threat


def test_the_idle_line_names_a_hold_only_when_the_cash_is_held():
    """The ramp branch of _threat_tick: "saving for blimp damage before
    round 94" was the idle line the loss was diagnosed from; with nothing
    held for the round being played the line must not stand."""
    def ramp_tick(margin):
        ex = holder(margin)
        ex.due_threats = lambda rnd: []
        ex._ramp_due = lambda rnd: (94, {"hp": 124_800}, 0.2)
        ex.ramp_bar = lambda load: 1.4
        ex.waiting = None

        def answer_ramp(R, load, ratio, cash, rnd):
            ex.wait_total = 40_000
            return "wait"
        ex._answer_ramp = answer_ramp
        return ex
    ex = ramp_tick(0.25)
    assert ex._threat_tick(17_562, 94) is None and ex.waiting is None and not ex.saving_for_threat
    ex = ramp_tick(2.5)
    ex._ramp_due = lambda rnd: (96, {"hp": 124_800}, 0.2)
    assert ex._threat_tick(17_562, 94) is False and ex.saving_for_threat
    assert ex.waiting == "saving for blimp damage before round 96"


def test_an_unpriced_answer_is_held_by_its_next_tier():
    ex = holder(2.5)
    ex.wait_cost = 3_000
    assert ex._hold_for(100, None, 94, "the bad answer") is False and ex.saving_for_threat
    ex = holder(0.25)
    ex.wait_cost = 3_000
    assert ex._hold_for(100, None, 94, "the bad answer") is None
    assert ex.held_cash == max(0.0, 3_000 - ex.income_until(100, 94))


def test_an_unknown_cost_is_held_only_while_the_round_is_safe():
    ex = holder(2.5)
    assert ex._hold_for(100, None, 94, "the bad answer") is False and ex.saving_for_threat
    ex = holder(0.25)
    assert ex._hold_for(100, None, 94, "the bad answer") is None
    assert not ex.saving_for_threat and ex.held_cash == 0.0
    assert ex._hold_for(96, None, 94, "the bad answer") is None       # near or far alike


def test_a_gap_answer_has_no_round_and_is_held_as_before():
    ex = holder(0.25)
    ex.due_threats = lambda rnd: ["camo"]
    ex._strength_threat = lambda threat: False

    def answer(threat, cash, rnd):
        ex.wait_cost, ex.wait_total = 3_000, 40_000
        return "wait"
    ex.answer_threat = answer
    assert ex._threat_tick(27_000, 94) is False and ex.saving_for_threat


# -- pricing an answer --------------------------------------------------------------
def test_steps_cost_prices_what_it_can():
    ex = bare_executor("impoppable", [tower("s1", "super", [2, 0, 3])])
    ex._caps = lambda kind, p=None: (5, 5, 5)
    fam = S.PRICE_FAMILY.get("impoppable", "hard")
    want = sum(S.T.upgrade_cost("super", 3, t, fam) for t in (4, 5))
    sale, tier = {"do": "sell", "id": "s1"}, {"do": "upgrade", "id": "s1", "to": "2-0-5"}
    assert ex._steps_cost([sale, tier], "the bad answer") == want
    assert ex._steps_cost([sale], "the bad answer") is None
    assert any(n[0] == "unpriced-steps" for n in ex.noted)
    ex.wait_cost = 3_000
    assert ex._wait_total(None) == "wait" and ex.wait_total == 3_000
    assert ex._wait_total(want) == "wait" and ex.wait_total == want


# -- a dead tower's plan upgrade ------------------------------------------------------
def dead_board(mode):
    """n2 (a ninja on the walled lane) has read 0 pops twice since round 6;
    the plan's next step upgrades it. Placing costs $500 in the fake."""
    n1 = tower("n1", "ninja", [3, 0, 2], pops=5000, placed_round=3)
    n2 = tower("n2", "ninja", [2, 0, 3], spent=5000, placed_round=6, pops=0, pops_round=40, zero_reads=2)
    place = {"do": "place", "id": "n2", "kind": "ninja", "role": "dps", "segment": [0.2, 0.8], "at": [0.21, 0.79]}
    up = {"do": "upgrade", "id": "n2", "to": "2-0-4"}
    ex = bare_executor(mode, [n1, n2], plan=[place, up], idx=1, counter={}, strat={"plan": [place, up]})
    ex._sole_answer = lambda p: None
    ex.capped, ex.panel_price, ex.upgrade_fails, ex.unread_until = {("n2", 2)}, {("n2", 3, 4): 4320}, {}, {}
    ex.g.closed, ex.g._closed_misses = {("n2", 2), ("n1", 1)}, {("n2", 1): 2}
    ex.g.price = lambda kind: 500
    ex.placed = []

    def try_place(step, cash):
        ex.placed.append(dict(step))
        if cash < 500:
            return "wait"
        ex.g.towers[step["id"]] = tower(step["id"], step["kind"], [0, 0, 0])
        return "bought"
    ex._try_place = try_place
    return ex


def test_a_dead_towers_upgrade_places_a_fresh_tower_under_its_id():
    for mode in ("hard", "chimps"):
        ex = dead_board(mode)
        up = ex.plan[1]
        assert ex.try_step(dict(up), 300, 41) == "wait"          # too poor to place yet
        assert "n2" not in ex.g.towers and ex.g.towers["ninja1"].tid == "ninja1"
        assert ex.g.towers["ninja1"].spent == 5000                # the old tower, renamed
        assert ex.redirected["n2"]["segment"] == [0.2, 0.8] and "at" not in ex.redirected["n2"]
        assert ("ninja", 10, 10) in ex.failed_spots               # its spot is avoided
        assert ex.capped == {("ninja1", 2)} and ("ninja1", 3, 4) in ex.panel_price
        # the game's closed paths move with the renamed tower too
        assert ex.g.closed == {("ninja1", 2), ("n1", 1)} and ex.g._closed_misses == {("ninja1", 1): 2}
        # while the stand-in is not placed the step is priced as its placement
        assert ex._first_step_cost(up) == 500
        fam = S.PRICE_FAMILY.get(mode, "hard")
        ex._caps = lambda kind, p=None: (5, 5, 5)
        want = S.T.tower_cost("ninja", fam) + sum(S.T.upgrade_cost("ninja", 1, t, fam) for t in (1, 2)) \
            + sum(S.T.upgrade_cost("ninja", 3, t, fam) for t in (1, 2, 3, 4))
        assert ex._steps_cost([up], "the moab answer") == want
        # the next tick places it, and the id is live again
        assert ex.try_step(dict(up), 1000, 41) == "bought"
        assert ex.g.towers["n2"].tiers == [0, 0, 0] and not ex.redirected
        assert len(ex.placed) == 2 and all(p["id"] == "n2" for p in ex.placed)
        # the fresh tower is not dead: the step goes to the normal upgrade path
        assert ex._redirect_dead_upgrade(dict(up), 1000, 41) is None


def test_the_redirect_keeps_the_callers_journal_reason():
    ex = dead_board("hard")
    up = {"do": "upgrade", "id": "n2", "to": "2-0-4"}
    seen = []
    ex._try_place = lambda step, cash: seen.append(dict(ex.g.why)) or "wait"
    with ex.why("answer", "threat moab due"):
        ex.try_step(dict(up), 300, 41)
    assert seen[-1]["source"] == "answer"                      # not re-labelled as the plan
    ex.g.why = None
    ex.try_step(dict(up), 300, 41)
    assert seen[-1]["source"] == "plan" and seen[-1]["step"]["id"] == "n2"


def test_a_live_tower_and_a_sole_answer_are_not_redirected():
    ex = dead_board("hard")
    ex.g.towers["n2"].pops = 12
    assert ex._redirect_dead_upgrade({"do": "upgrade", "id": "n2", "to": "2-0-4"}, 1000, 41) is None
    ex = dead_board("hard")
    ex._sole_answer = lambda p: "camo"
    assert ex._redirect_dead_upgrade({"do": "upgrade", "id": "n2", "to": "2-0-4"}, 1000, 41) is None
    assert "n2" in ex.g.towers and not getattr(ex, "redirected", None)
    # a step without an id (every tower of a kind) is never redirected
    assert ex._redirect_dead_upgrade({"do": "upgrade", "kind": "ninja", "to": "2-0-4"}, 1000, 41) is None


def test_a_dead_tower_is_renamed_once_and_a_fill_tower_never():
    """Water Park Magic Monkeys Only (2026-11-05, lost round 63): the fill's
    per-tower upgrade steps name each standing tower by its current id, so
    the same dead wizards were renamed again on every pass (130 renames,
    111 placements given up, a "placement" defeat). A tower renamed out of
    its plan id is skipped under its new name, and a dead surplus or fill
    tower - an id no build step waits for - is skipped without a rename or
    a placement."""
    ex = dead_board("hard")
    up = ex.plan[1]
    assert ex.try_step(dict(up), 300, 41) == "wait"           # n2 renamed to ninja1, its stand-in pending
    renamed = ex.g.towers["ninja1"]
    assert renamed.renamed_dead and ex.redirected["n2"]
    # the fill names the dead tower by its new id: skipped, not renamed again
    assert ex.try_step({"do": "upgrade", "id": "ninja1", "to": "2-0-4"}, 5000, 42) == "skip"
    assert ex.g.towers["ninja1"] is renamed and renamed.tid == "ninja1"
    assert set(ex.redirected) == {"n2"} and len(ex.placed) == 1
    # a dead surplus tower (its id is in no build step): skipped outright
    w3 = tower("wizard3", "wizard", [0, 2, 2], spent=1500, placed_round=20, pops=0, pops_round=40, zero_reads=2)
    ex.g.towers["wizard3"] = w3
    assert ex.try_step({"do": "upgrade", "id": "wizard3", "to": "0-2-4"}, 5000, 42) == "skip"
    assert ex.g.towers["wizard3"] is w3 and "wizard3" not in ex.redirected and len(ex.placed) == 1
    # a plan id whose tower pops is still upgraded the normal way
    assert ex._redirect_dead_upgrade({"do": "upgrade", "id": "n1", "to": "4-0-2"}, 5000, 42) is None


def test_chimps_reads_pop_counts_but_sells_nothing():
    d1 = tower("d1", "dart", [2, 0, 0], spent=600, placed_round=30, pops=0)
    t1 = tower("t1", "tack", [2, 0, 0], spent=500, placed_round=30, pops=900)
    ex = bare_executor("chimps", [d1, t1], forecast=Fixed(3.0), removed=[])
    ex._sole_answer = lambda p: None
    selected, sold = [], []
    ex.g.select = lambda p: selected.append(p.tid) or True
    ex.g.deselect = lambda p: None
    ex.g.sell = lambda p: sold.append(p.tid) or True
    assert ex.sell_useless(45) is False and selected == ["d1"] and d1.zero_reads == 1
    d1.zero_reads = 2
    assert ex.sell_useless(48) is False and not sold and ex._dead(d1)
    assert len(selected) == 2                                      # read again, still not sold


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
