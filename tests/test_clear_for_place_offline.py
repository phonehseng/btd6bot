"""A plan tower with no ground gets the ground under a removable obstacle.

High Finance Impoppable (2026-11-11 08:31, chimps_ninja_sun, loss case
20261111_090319_HighFinance_impoppable): nearly all of the map's land lies
under removable plazas. After the first four towers no kind had a legal cell
left, so the alchemist (round 14) and then both villages, the Sun Avatar, the
Ground Zero aces, the MOAB Eliminator bomb and the exit spikes (round 35)
were given up "after 0 refused spots" - the whole build from round 35 on -
and round 95 was lost with the defence rated 0.35. Obstacles were bought only
by surplus, for "another ninja", from round 50.

Offline: the executor on the map's real geometry with a fake game, the four
towers of that game standing where they stood.
Run: python tests/test_clear_for_place_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L, mapgeom       # noqa: E402
from btd6bot import strategy as S              # noqa: E402
from btd6bot.game import Placed                # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

PF = L.get(1920, 1200)["playfield"]
MAP = "High Finance"
# (id, kind, x, y) as placed in the lost game (game.log, 08:31-08:32)
OPENING = (("n1", "ninja", 0.371, 0.402), ("starter", "dart", 0.371, 0.675),
           ("hero", "hero", 0.489, 0.394), ("n2", "ninja", 0.489, 0.658))


class Game(F.FakeGame):
    """A fake game that records the obstacles it is asked to remove."""

    def __init__(self, refuse=False):
        super().__init__(hero="obyn")
        self.removals, self.refuse = [], refuse

    def remove_obstacle(self, fx, fy, cost, name=""):
        self.removals.append((name, cost))
        return not self.refuse


def executor(refuse=False):
    """chimps_ninja_sun in Impoppable on High Finance's own geometry with the
    lost game's opening on the board; None when the map file is not there."""
    geom = mapgeom.load(MAP)
    if geom is None:
        return None
    model = mapgeom.apply(MapModel(MAP, PF), geom)
    ex = S.Executor(Game(refuse), model, S.load_all()["chimps_ninja_sun"], "impoppable", F.full_account())
    for tid, kind, x, y in OPENING:
        ex.g.towers[tid] = Placed(tid, kind, x, y)
        ex._block(*model.frac_to_cell(x, y), 3)
    return ex


def place_step(ex, tid):
    return next(st for st in ex.plan if st.get("do") == "place" and st.get("id") == tid)


def retry_now(ex):
    """The set-aside steps' pauses are over."""
    ex.retry_at.clear()


def test_the_board_of_the_lost_game_has_no_ground_left():
    ex = executor()
    if ex is None:
        print("skip: no High Finance geometry")
        return
    for kind in ("alchemist", "village", "super", "ace", "bomb"):
        assert int(ex._legal_cells(kind).sum()) == 0, kind


def test_a_plan_tower_waits_for_its_obstacle_and_then_stands_on_its_ground():
    ex = executor()
    if ex is None:
        return
    a1 = place_step(ex, "a1")
    key = ex._step_key(a1)
    # round 14 of the lost game: the tower's price in hand, not the obstacle's too
    assert ex.try_step(a1, ex.g.price("alchemist") + 100, 14) == "skip"
    assert key not in ex.dead_steps, "set aside, not given up"
    assert a1 in ex.deferred and not ex.g.removals
    # the cash is there: the obstacle goes first, the tower at the next look
    retry_now(ex)
    assert ex.try_step(a1, 5000, 16) == "progress"
    assert len(ex.g.removals) == 1 and len(ex.removed) == 1
    assert ex.try_step(a1, 5000, 16) == "bought"
    assert "a1" in ex.g.towers
    # ... where it brews for a tower of the opening. (No obstacle lies by n1,
    # the ninja its step names, so it goes where it buffs the most towers:
    # the plaza beside n2 and the opener.)
    ax, ay = ex.m.frac_to_cell(ex.g.towers["a1"].x, ex.g.towers["a1"].y)
    reach = ex._range_cells("alchemist")
    in_reach = [tid for tid, _, x, y in OPENING if tid != "hero"
                and sum((a - b) ** 2 for a, b in zip(ex.m.frac_to_cell(x, y), (ax, ay))) ** 0.5 <= reach]
    assert in_reach, (ax, ay)


def test_steps_with_no_ground_wait_behind_one_obstacle_and_none_is_given_up():
    """Round 35 of the lost game: thirteen placements given up in one second."""
    ex = executor()
    if ex is None:
        return
    ids = ("v1", "s1", "v2", "ac1", "b1")
    for tid in ids:
        assert ex.try_step(place_step(ex, tid), ex.g.price(place_step(ex, tid)["kind"]) + 100, 35) == "skip", tid
    assert not ex.dead_steps and not ex.g.removals
    assert [st["id"] for st in ex.deferred] == list(ids)
    # one step chose an obstacle; the others wait behind it without a search
    assert sum(1 for _, r in ex.clear_wait.values() if r is not None) == 1
    # with the cash in hand the plaza is bought once and the towers follow
    retry_now(ex)
    assert ex.try_step(place_step(ex, "v1"), 20000, 36) == "progress"
    assert ex.try_step(place_step(ex, "v1"), 20000, 36) == "bought"
    assert ex.try_step(place_step(ex, "s1"), 20000, 36) in ("bought", "progress")


def test_a_refused_removal_is_left_alone_after_its_tries():
    ex = executor(refuse=True)
    if ex is None:
        return
    a1 = place_step(ex, "a1")
    seen = []
    for _ in range(40):
        retry_now(ex)
        seen.append(ex.try_step(a1, 50000, 20))
        if ex._step_key(a1) in ex.dead_steps:
            break
    assert ex._step_key(a1) in ex.dead_steps, "every obstacle refused: the step is given up in the end"
    assert "progress" not in seen and not ex.removed


def test_fill_and_answer_steps_are_given_up_as_before_and_come_back_with_the_ground():
    ex = executor()
    if ex is None:
        return
    answer = {"do": "place", "id": "ans_blimps_ace", "kind": "ace", "role": "dps",
              "segment": [0.0, 0.7], "lane": "blimp"}
    assert ex.try_step(dict(answer), 20000, 35) == "skip"
    assert ex._step_key(answer) in ex.dead_steps and not ex.g.removals
    # surplus buys a plaza for the build's main tower: the answer may be asked again
    assert ex.clear_obstacle(20000, "ninja")
    assert ex._step_key(answer) not in ex.dead_steps
    assert ex.try_step(dict(answer), 20000, 50) == "bought"


def test_a_given_up_plan_tower_comes_back_with_the_upgrades_the_plan_passed():
    """The replay of the lost game: v1 (no obstacle helped a village at
    round 39) came back a round later as a bare 0-0-0 village, because the
    plan had already skipped `v1 -> 2-0-2`."""
    ex = executor()
    if ex is None:
        return
    v1 = place_step(ex, "v1")
    ex.dead_steps.add(ex._step_key(v1))            # given up without a refused spot
    ex.idx = len(ex.plan)                          # the plan has gone past all of it
    ex.removed.append(ex._obstacles()[0]["id"])
    ex._ground_cleared()
    assert ex._step_key(v1) not in ex.dead_steps
    assert ex.deferred[0] is v1
    ups = [st for st in ex.plan if st.get("do") == "upgrade" and st.get("id") == "v1"]
    assert ups and ex.deferred[1:] == ups, ex.deferred


def test_a_build_that_may_not_remove_obstacles_gives_the_step_up():
    ex = executor()
    if ex is None:
        return
    ex.no_removals = True
    a1 = place_step(ex, "a1")
    assert ex.try_step(a1, 5000, 16) == "skip"
    assert ex._step_key(a1) in ex.dead_steps and not ex.g.removals


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
