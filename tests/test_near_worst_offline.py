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


if __name__ == "__main__":
    test_the_near_weak_round_is_found()
    print("all tests passed")
