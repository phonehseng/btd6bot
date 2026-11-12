"""A plan_first build's cash may go to a weak round when the bloons got
deep in either of the last two rounds watched, not only the last one.

Bloonarius Prime Impoppable (2026-11-11 23:53, loss case
20261111_235352): round 36's bloons got 95% along the route, round 37's
79%, and round 38 (rated 0.42) began with $1,268 held for plan step
n1 4-0-2; the plan kept it and round 38 took the life."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import match as M  # noqa: E402


def _match(depths, seen):
    m = M.Match.__new__(M.Match)
    m.depths = [{"deepest": d} for d in depths]
    m.ex = SimpleNamespace(plan_first=lambda: True,
                           plan_first_yields=lambda cash, rnd, deep: seen.append(deep) or deep)
    return m


def test_a_deep_round_before_a_quieter_one_still_counts():
    seen = []
    assert _match([0.95, 0.79], seen)._plan_lets_reinforce(1268, 38)
    assert seen == [True]


def test_shallow_rounds_keep_the_cash_with_the_plan():
    seen = []
    assert not _match([0.95, 0.70, 0.79], seen)._plan_lets_reinforce(1268, 38)
    assert seen == [False]


if __name__ == "__main__":
    test_a_deep_round_before_a_quieter_one_still_counts()
    test_shallow_rounds_keep_the_cash_with_the_plan()
    print("all tests passed")
