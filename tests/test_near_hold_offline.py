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


def bare(cash=23_320.0, weak=True, income=9_600.0):
    """An Executor at round 98 of a CHIMPS game with `cash` in hand; each
    round brings `income`, and rounds 98-99 are rated weak or not."""
    ex = S.Executor.__new__(S.Executor)
    ex.rules = {"lives": 1, "one_life": True}
    ex.noted, ex.held_cash = set(), 0.0
    ex._notes = lambda: ex.noted
    ex.drop_rounds = []
    ex._ramp_due = lambda rnd: None
    ex.weak_now = lambda rnd: weak
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


def rated(ex, playing, due):
    """Make the damage model rate the round being played at `playing` and
    the round the cash is held for at `due`."""
    ex._rated = lambda what, rnd, rate: (playing, due)
    return ex


def test_the_chutes_case_holds_nothing_while_round_98_would_end_the_game():
    """Chutes Impoppable (2026-11-11, case 20261111_041712): $26,389 in hand
    at round 98, rated 0.29 and the weakest round left; the $31,200 BAD
    answer was payable after the round's income, so the cash was held in
    full and the round was lost."""
    ex = rated(bare(cash=26_389.0), 0.29, 0.5)
    assert ex._hold_for(100, 31_200.0, 98, "the bad answer", threat_answer=True) is None
    assert not ex.saving_for_threat and ex.held_cash == 0.0
    assert ("lost-round-hold", "the bad answer", 98) in ex.noted


def test_a_far_hold_still_keeps_what_income_cannot_rebuild():
    """Three rounds before the answer's round the far-round rule decides as
    before: it already frees most of the cash ($31,200 - 3 x $3,700 kept)."""
    ex = rated(bare(cash=25_355.0, income=3_700.0), 0.29, 0.5)
    assert ex._hold_for(100, 31_200.0, 97, "the bad answer", threat_answer=True) is None
    assert ex.held_cash == 31_200.0 - 3 * 3_700.0


def test_a_later_round_the_model_fears_more_keeps_its_hold():
    """Spillway Impoppable (2026-11-11 04:18): rounds 34-39 were rated
    0.39-0.99 and all held; round 40's MOAB, rated 0.67, ended the game.
    At round 38 (0.81) the hold for round 40's answer must stand."""
    ex = rated(bare(cash=5_000.0, income=1_500.0), 0.81, 0.67)
    assert not ex._lost_as_it_stands(38, 40)
    assert ex._hold_for(40, 6_000.0, 38, "the moab answer", threat_answer=True) is False
    assert ex.saving_for_threat


def test_a_round_rated_to_hold_keeps_the_older_rules():
    ex = rated(bare(cash=26_389.0), 1.2, 1.3)       # weak (under 1.5) but not lost
    assert ex._hold_for(100, 31_200.0, 98, "the bad answer", threat_answer=True) is False


def test_lives_to_spare_and_unrated_rounds_keep_the_older_rules():
    """With lives left a leak costs lives, not the game: the hold stands.
    So it does when the model cannot rate one of the two rounds."""
    ex = rated(bare(cash=26_389.0), 0.29, 0.5)
    ex.rules = {"lives": 100}
    assert not ex._lost_as_it_stands(98, 100)
    assert ex._hold_for(100, 31_200.0, 98, "the bad answer", threat_answer=True) is False
    ex = rated(bare(cash=26_389.0), 0.29, None)
    assert not ex._lost_as_it_stands(98, 100)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
