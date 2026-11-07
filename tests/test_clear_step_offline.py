"""A build can clear a named obstacle at a set point of its plan (`do: clear`).

Removal used to be surplus spending only (Executor.clear_obstacle), when a
tower kind had run out of ground. The Cracked CHIMPS strategy (bloon.games,
2026-11-07) clears the central rock first, for the pond under it, before its
first buccaneer. Offline: the executor with a fake game and a fake obstacle.
Run: python tests/test_clear_step_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import strategy as S             # noqa: E402

ROCK = {"id": "rock-1", "name": "RemoveableRock", "cost": 1000, "frac": (0.5, 0.5), "available": True}
CLEAR = {"do": "clear", "obstacle": "RemoveableRock"}


class Game(F.FakeGame):
    """A fake game that records obstacle removals and can refuse them."""

    def __init__(self, refuse=False):
        super().__init__()
        self.removals, self.refuse = [], refuse

    def remove_obstacle(self, fx, fy, cost, name=""):
        self.removals.append((name, cost))
        return not self.refuse


def executor(game=None, steps=(CLEAR,)):
    plan = {"id": "t", "name": "t", "hero": None, "plan": [dict(s) for s in steps]}
    ex = S.Executor(game or Game(), F.FakeModel(), plan, "hard", F.full_account())
    ex._obstacle_list = [dict(ROCK)]
    return ex


def test_a_clear_step_validates_and_needs_its_obstacle():
    assert not [p for p in S.validate({"id": "t", "plan": [dict(CLEAR)]}) if "clear" in p]
    assert any("clear without obstacle" in p for p in S.validate({"id": "t", "plan": [{"do": "clear"}]}))


def test_a_clear_step_waits_for_the_cash_then_buys_then_is_done():
    ex = executor()
    assert ex.try_step(CLEAR, 999, 6) == "wait"
    assert ex.try_step(CLEAR, 1000, 6) == "bought"
    assert ex.g.removals == [("RemoveableRock", 1000)]
    assert "rock-1" in ex.removed
    assert ex.try_step(CLEAR, 5000, 7) == "done"


def test_a_refused_removal_is_tried_again_then_skipped():
    ex = executor(Game(refuse=True))
    for _ in range(ex.REMOVAL_TRIES):
        assert ex.try_step(CLEAR, 5000, 6) == "wait"
    assert ex.try_step(CLEAR, 5000, 6) == "skip"


def test_an_unknown_obstacle_is_skipped():
    ex = executor()
    assert ex.try_step({"do": "clear", "obstacle": "NoSuchTree"}, 5000, 6) == "skip"


def test_a_clear_step_is_priced_like_its_obstacle():
    ex = executor()
    assert ex._first_step_cost(CLEAR) == 1000
    assert ex._sim_step(CLEAR, {}, 0) == 1000
    ex.removed.append("rock-1")
    assert ex._first_step_cost(CLEAR) == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
