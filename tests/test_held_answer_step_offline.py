"""Cash held for a threat answer is not kept from the plan step that buys it.

Spillway Impoppable (2026-11-12 07:21, loss case 20261112_072317): the plan
waited on b1 0-5-0 ($31,200), which is also the build's BAD answer; the
BAD hold kept $12-20k back from the plan, which logged "idle with $37123:
plan step 29 b1 0-5-0 -> wait" for two rounds before round 98 took the life."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import strategy as S  # noqa: E402


def _ex(plan, answers):
    ex = S.Executor.__new__(S.Executor)
    ex.plan, ex.idx, ex.strat = plan, 0, {"answers": answers}
    return ex


def test_the_answer_step_is_recognised():
    step = {"do": "upgrade", "id": "b1", "to": "0-5-0"}
    ex = _ex([dict(step)], {"bad": [dict(step)], "ddt": [{"do": "upgrade", "id": "b1", "to": "0-5-0"}]})
    assert ex._plan_step_is_held_answer()


def test_other_steps_still_leave_the_held_cash():
    ex = _ex([{"do": "upgrade", "id": "sp1", "to": "2-0-5"}], {"bad": [{"do": "upgrade", "id": "b1", "to": "0-5-0"}]})
    assert not ex._plan_step_is_held_answer()
    assert not _ex([], {"bad": []})._plan_step_is_held_answer()


if __name__ == "__main__":
    test_the_answer_step_is_recognised()
    test_other_steps_still_leave_the_held_cash()
    print("all tests passed")
