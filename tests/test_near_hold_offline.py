"""A hold for an answer due one or two rounds ahead gives way to the weak
rounds before it when the money cannot arrive in time for them
(Executor._near_hold_too_late).

Spring Spring CHIMPS (2026-11-07, case 20261107_225718): from round 98 the
bot held every dollar "for the bad answer" of round 100 ($34,560) while the
damage model rated rounds 98 and 99 at 1.18 and 1.04. The plan's Cripple MOAB
sniper waited, round 99 started with $32,973 in the bank and was lost.
Offline: a bare Executor whose checks are replaced by fixed answers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import strategy as S  # noqa: E402


def bare(cash=23_320.0, weak=True, income=9_600.0, margin=1.1):
    """An Executor at round 98 of a CHIMPS game with `cash` in hand; each
    round brings `income`, and rounds 98-99 are rated weak or not."""
    ex = S.Executor.__new__(S.Executor)
    ex.rules = {"lives": 1, "one_life": True}
    ex.noted, ex.held_cash = set(), 0.0
    ex._notes = lambda: ex.noted
    ex.drop_rounds = []
    ex._ramp_due = lambda rnd: None
    ex.weak_now = lambda rnd: weak
    ex.margin_now = lambda rnd: margin
    ex.lives_fell_lately = lambda rnd, rounds=None: False
    ex.income_until = lambda due_round, rnd: income * max(0, due_round - rnd)
    ex.saving_for_threat = ex.firm_hold = False
    ex.cash_seen = cash
    return ex


def test_the_spring_spring_case_holds_nothing_for_round_100():
    ex = bare()
    assert ex._hold_for(100, 34_560.0, 98, "the bad answer", threat_answer=True) is None
    assert not ex.saving_for_threat and ex.held_cash == 0.0
    assert ("near-too-late", "the bad answer", 98) in ex.noted


def test_a_blimp_damage_hold_is_not_released():
    """The blimp check's own holds (blimp damage, a plan's blimp step) are
    for the rounds that make this one weak: they keep their cash, as
    test_threats_offline.test_plan_blimp_step_keeps_its_cash wants."""
    ex = bare()
    assert ex._hold_for(100, 34_560.0, 98, "blimp damage") is False
    assert ex.saving_for_threat


def test_holds_in_full_when_the_answer_comes_before_the_weak_round():
    ex = bare(cash=26_000.0)            # $26,000 + $9,600 this round >= $34,560
    assert ex._hold_for(100, 34_560.0, 98, "the bad answer", threat_answer=True) is False
    assert ex.saving_for_threat


def test_a_safe_round_holds_in_full_as_before():
    ex = bare(weak=False)
    assert ex._hold_for(100, 34_560.0, 98, "the bad answer", threat_answer=True) is False
    assert ex.saving_for_threat


def test_unknown_cash_and_far_rounds_are_left_to_the_older_rules():
    ex = bare()
    del ex.cash_seen
    assert ex._hold_for(100, 34_560.0, 98, "the bad answer", threat_answer=True) is False
    ex = bare()
    assert not ex._near_hold_too_late(100, 34_560.0, 94)    # far: _far_keep decides
    assert not ex._near_hold_too_late(98, 34_560.0, 98)     # the round being played
    assert not ex._near_hold_too_late(100, None, 98)


def test_a_likely_lost_round_holds_nothing_for_a_later_one():
    """Chutes Impoppable (2026-11-11): round 98 rated 0.29, $26,245 held
    for round 100's bad answer though the cash could have paid it."""
    ex = bare(cash=26_245.0, margin=0.29, income=5_000.0)
    assert ex._hold_for(100, 31_200.0, 98, "bad answer", threat_answer=True) is None
    assert not ex.saving_for_threat and ex.held_cash == 0.0
    assert ("lost-first", "bad answer", 98) in ex.noted


def test_likely_lost_needs_one_life_and_a_rating():
    ex = bare(cash=26_245.0, margin=0.29)
    ex.rules = {"lives": 100}
    assert not ex._likely_lost_first(100, 98)
    ex = bare(cash=26_245.0, margin=None)
    assert not ex._likely_lost_first(100, 98)
    ex = bare(cash=26_245.0, margin=0.29)
    assert not ex._likely_lost_first(98, 98)       # the round itself: the playing-hold rule
    assert ex._hold_for(100, 31_200.0, 98, "blimp damage") is False   # blimp holds keep their cash


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
