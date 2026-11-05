"""A far threat's answer waits while a nearer round is in danger
(Executor._defer_far_answer).

Lotus Island CHIMPS (2026-11-05): the model rated round 95 at 0.38 from
round 86 on. At round 94 the round-100 BAD answer (s1 -> 5-2-0, $34,560) took
the whole bank, round 95 started with $492 and the game's one life was lost.
Offline: a bare Executor whose checks are replaced by fixed answers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as RF  # noqa: E402
from btd6bot import strategy as S  # noqa: E402


def bare(weak_now=False, worst=(3.0, 99), due=100, strength=True, cost=34560.0, income=28192.0):
    """An Executor that answers the checks _defer_far_answer asks with the
    values given: the round being played weak or not, the weakest round
    ahead (margin, round), the threat's round, the answer's whole cost and
    the income counted on before the threat."""
    ex = S.Executor.__new__(S.Executor)
    ex.strat = {"answers": {"bad": [{"do": "upgrade", "id": "s1", "to": "5-2-0"}]}}
    ex.noted, ex.held_cash = set(), 0.0
    ex._notes = lambda: ex.noted
    ex._strength_threat = lambda threat: strength
    ex._threat_round = lambda threat, rnd: due
    ex.lives_fell_lately = lambda rnd, rounds=None: False
    ex.weak_now = lambda rnd: weak_now
    ex.lookahead_worst = lambda rnd: worst
    ex._step_allowed = lambda st: True
    ex._steps_cost = lambda steps, what="": cost
    ex.income_until = lambda due_round, rnd: income
    return ex


def test_the_lotus_island_case_waits_and_holds_only_what_income_cannot_rebuild():
    ex = bare(weak_now=True)
    assert ex._defer_far_answer("bad", 94)
    assert round(ex.held_cash) == 34560 - 28192


def test_a_weak_round_ahead_of_the_threat_also_makes_it_wait():
    ex = bare(worst=(0.38, 95))
    assert ex._defer_far_answer("bad", 90)


def test_answered_as_before_when_nothing_nearer_is_weak():
    assert not bare(worst=(RF.WEAK_MARGIN + 0.1, 95))._defer_far_answer("bad", 90)
    assert not bare(worst=(0.5, 100))._defer_far_answer("bad", 90)   # the weak round is the threat's own
    assert not bare(worst=None)._defer_far_answer("bad", 90)
    assert not bare(weak_now=True, cost=None)._defer_far_answer("bad", 94)   # unpriced: the usual hold


def test_answered_as_before_once_the_threat_is_near_or_a_gap():
    assert not bare(weak_now=True)._defer_far_answer("bad", 100 - S.Executor.FAR_ROUNDS)
    assert not bare(weak_now=True, strength=False)._defer_far_answer("camo", 94)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
