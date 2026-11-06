"""A hold for a game-ending blimp round stays whole while the nearer rounds
are weak in the damage model only (Executor._firm_blimp_hold).

Bloonarius Prime Half Cash (2026-11-06, case 20261106_144410): round 40's MOAB
was rated 0.1x from round 34, but each round 34-37 held "only $0-680" of the
$2,430 answer because the round being played was rated weak, and reinforcing
spent the rest. Rounds 34-38 passed with no life lost; round 40 started with
$270 and the MOAB took all 100 lives.
Offline: a bare Executor and Match whose checks are replaced by fixed answers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot import strategy as S  # noqa: E402


def bare(ramp=(40, {"hp": 200}, 0.1), drops=(), rules=None, weak=True, income=1800.0):
    """An Executor at round 34 of a Half Cash game: the blimp check sees
    `ramp` (round, load, ratio), lives fell in `drops`, the round being
    played is rated weak or not."""
    ex = S.Executor.__new__(S.Executor)
    ex.rules = {"lives": 100} if rules is None else rules
    ex.noted, ex.held_cash = set(), 0.0
    ex._notes = lambda: ex.noted
    ex.drop_rounds = list(drops)
    ex._ramp_due = lambda rnd: ramp
    ex.weak_now = lambda rnd: weak
    ex.lives_fell_lately = lambda rnd, rounds=None: bool(drops) and drops[-1] == rnd
    ex.income_until = lambda due_round, rnd: income
    ex.saving_for_threat = ex.firm_hold = False
    return ex


def test_the_bloonarius_prime_case_holds_all_of_the_moab_answer():
    ex = bare()
    assert ex._hold_for(40, 2430.0, 34, "blimp damage") is False
    assert ex.saving_for_threat and ex.firm_hold
    assert ex.held_cash == 0.0           # not the partial "income rebuilds the rest" hold


def test_partial_hold_as_before_when_lives_fell_or_the_blimps_are_not_far_short():
    ex = bare(drops=[33])                # lives fell: the weak rating is real
    assert ex._hold_for(40, 2430.0, 34, "blimp damage") is None
    assert not ex.firm_hold and round(ex.held_cash) == 2430 - 1800
    ex = bare(ramp=(40, {"hp": 200}, S.Executor.RAMP_PANIC + 0.2))
    assert ex._hold_for(40, 2430.0, 34, "blimp damage") is None
    ex = bare(ramp=(39, {"hp": 200}, 0.1))   # the hold is for another round
    assert ex._hold_for(40, 2430.0, 34, "blimp damage") is None


def test_never_firm_in_one_life_or_no_income_modes():
    assert not bare(rules={"lives": 1, "one_life": True})._firm_blimp_hold(40, 34)
    assert not bare(rules={"lives": 100, "income": False})._firm_blimp_hold(40, 34)
    assert not bare()._firm_blimp_hold(34, 34)      # the round being played: nothing to hold for


def test_the_far_moab_threat_is_not_deferred_for_a_model_only_weak_round():
    ex = bare()
    ex._strength_threat = lambda threat: True
    ex._threat_round = lambda threat, rnd: 40
    assert not ex._defer_far_answer("moab", 34)


def test_match_keeps_reinforce_off_a_firm_hold_even_in_a_crisis_round():
    m = M.Match.__new__(M.Match)
    m.ex = bare()
    m.ex.saving_for_threat, m.ex.firm_hold = True, True
    assert m._cash_held(dropped=False, crisis=True)
    assert not m._cash_held(dropped=True, crisis=True)    # lives falling now: spend
    m.ex.firm_hold = False
    assert not m._cash_held(dropped=False, crisis=True)   # an ordinary hold, as before


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
