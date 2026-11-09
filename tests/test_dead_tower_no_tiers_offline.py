"""Offline check: a tower that pops nothing is offered no tier by
upgrade_choices, the list surplus() and reinforce buy from.

Water Park ABR (2026-11-09, won at round 80 with 2 lives left): boomerang1,
placed by surplus at round 22, read 0 pops for 58 rounds. sell_useless kept
it ("keeping boomerang1 ... although not a single pop": the defence was
short, _sale_blocked), which is right - but surplus and reinforce still
offered its tiers, and over 2026-11-05..09 about $388k of tiers went to
towers already logged as dead. A plan upgrade for such a tower already moves
to a fresh one (_redirect_dead_upgrade); spare cash now skips it too.

Fakes in the style of tests/test_surplus_plan_step_offline.py.
Run: python tests/test_dead_tower_no_tiers_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_one_life_executor_offline import bare_executor, tower  # noqa: E402


def board():
    """b1 pops; boomerang1 stood 58 rounds and read 0 pops twice."""
    b1 = tower("b1", "boomerang", [3, 0, 2], spent=3000, placed_round=3, pops=9000)
    dead = tower("boomerang1", "boomerang", [3, 0, 2], spent=1870, placed_round=22,
                 pops=0, pops_round=78, zero_reads=2)
    ex = bare_executor("abr", [b1, dead])
    ex._sole_answer = lambda p: None
    return ex, b1, dead


def offered(ex):
    return {p.tid for p, _, _ in ex.upgrade_choices(past_plan=True)}


def test_a_dead_tower_gets_no_tier():
    ex, b1, dead = board()
    assert ex._dead(dead) and not ex._dead(b1)
    assert offered(ex) == {"b1"}


def test_one_zero_read_or_a_sole_answer_is_not_dead():
    ex, b1, dead = board()
    dead.zero_reads = 1                       # one misread is not proof
    assert offered(ex) == {"b1", "boomerang1"}
    ex, b1, dead = board()
    ex._sole_answer = lambda p: "lead" if p is dead else None
    assert offered(ex) == {"b1", "boomerang1"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
