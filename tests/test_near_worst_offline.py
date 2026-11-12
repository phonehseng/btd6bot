"""plan_first_yields judges the weakest round within its horizon.

Quad Impoppable (2026-11-12 00:13, loss case 20261112_001344): the model
rated round 63's ceramic rush 0.59 and round 70 0.46. The yield looked at
the look-ahead's overall weakest round (70, nine rounds off, past the
four-round horizon) and kept $7,167 for the Ground Zero while round 63
took the life. Executor.near_worst rates only the rounds within reach."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import strategy as S  # noqa: E402

MARGINS = {r: 1.5 for r in range(61, 80)}
MARGINS.update({63: 0.59, 70: 0.46})


class Forecast:
    def worst(self, towers, rounds):
        r = min(rounds, key=lambda x: MARGINS.get(x, 9.0))
        return MARGINS.get(r, 9.0), r


def _ex():
    ex = S.Executor.__new__(S.Executor)
    ex.rules = {"end_round": 100}
    ex.g = SimpleNamespace(towers={})
    ex._forecast = lambda: Forecast()
    ex._board_key = lambda: ()
    return ex


def test_the_near_weak_round_is_found():
    ex = _ex()
    assert ex.lookahead_worst(61)[1] == 70, "the whole look-ahead's weakest is round 70"
    assert ex.near_worst(61, S.Executor.YIELD_ROUNDS) == (0.59, 63)




def test_one_life_floor_next_round_yields_without_depth():
    """Midnight Mansion Impoppable (2026-11-12 00:36): round 63 rated 0.06
    from round 60, shallow bloons, $18,123 held for a $38,400 step."""
    from btd6bot import reinforce as RF
    ex = _ex()
    ex.rules = {"end_round": 100, "one_life": True}
    ex.plan_first = lambda: True
    ex.noted = set()
    ex._notes = lambda: ex.noted
    ex.given_up_credit = lambda: 0
    ex.near_worst = lambda rnd, h: (0.06, 63)
    old_wait, old_pay = RF.waiting_plan_step, RF.payable_by
    RF.waiting_plan_step = lambda e, cash: ({"do": "upgrade", "id": "sn1", "to": "5-2-0"}, 38400)
    RF.payable_by = lambda e, cost, cash, by, rnd: False
    try:
        assert ex.plan_first_yields(18123, 62, deep=False), "the floor round is next: the cash may go"
        assert not ex.plan_first_yields(18123, 60, deep=False), "three rounds off: it waits for the depth"
    finally:
        RF.waiting_plan_step, RF.payable_by = old_wait, old_pay

if __name__ == "__main__":
    test_the_near_weak_round_is_found()
    test_one_life_floor_next_round_yields_without_depth()
    print("all tests passed")
