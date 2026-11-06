"""Offline checks for reinforce's goals (backlog 49): a purchase rated by
the crosspath a standing tower grows into is bought as a path, not as one
tier, and an unfinished path stays on offer at the next looks.

Lotus Island CHIMPS (2026-11-05, case 20261105_171203) picked "buccaneer1
-> 1-1-0 (to grow to 4-2-0) ($13555)" for round 95, bought the $295 tier and
nothing more; round 95 came with the buccaneer at 1-1-0.
Run: python tests/test_reinforce_goal_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import towers as T  # noqa: E402

FAMILY = "hard"


class GrowEx:
    """One standing buccaneer and room for more. try_step buys the cheapest
    tier toward the step's crosspath, as Executor.try_step does, and moves
    the tower's tiers, so a path can be followed tier by tier."""
    mode = "hard"

    def __init__(self, tiers=(0, 0, 0)):
        self.g = N(towers={"b1": N(tid="b1", kind="buccaneer", tiers=list(tiers), x=0.5, y=0.5)},
                   price=lambda kind: T.tower_cost(kind, FAMILY))
        self.m = N(cell_to_frac=lambda cx, cy: (0.3, 0.3))
        self.bought = []
        self.fail_after = None      # this many tiers go through, then clicks fail

    def upgrade_choices(self, first=None, past_plan=False):
        for p in self.g.towers.values():
            for path in range(3):
                t = list(p.tiers)
                if t[path] >= 5:
                    continue
                t[path] += 1
                if sum(x > 0 for x in t) > 2 or sum(x > 2 for x in t) > 1:
                    continue
                yield p, t, T.upgrade_cost(p.kind, path + 1, t[path], FAMILY)

    def at_tower_cap(self):
        return False

    def _main_kind(self):
        return "buccaneer"

    def kind_allowed(self, kind):
        return True

    def pick_spots(self, kind, step, n=1):
        return [(10, 10, 1.0)]

    def try_step(self, step, cash, rnd):
        p = self.g.towers[step["id"]]
        target = R._tiers(step["to"])
        cost = R._next_tier_cost(p.kind, tuple(p.tiers), target, FAMILY)
        if cost is None:
            return "done"
        if cash < cost or (self.fail_after is not None and len(self.bought) >= self.fail_after):
            return "wait"
        path = min((i for i in range(3) if p.tiers[i] < target[i]),
                   key=lambda i: T.upgrade_cost(p.kind, i + 1, p.tiers[i] + 1, FAMILY))
        p.tiers[path] += 1
        self.bought.append(tuple(p.tiers))
        return "progress" if R._next_tier_cost(p.kind, tuple(p.tiers), target, FAMILY) else "bought"


class PerTier:
    """A stand-in damage model: a bare tower adds nothing, each tier 0.15,
    so only a grown tower lifts the weak round, and each round loses 10
    lives per missing unit of margin."""

    def margin(self, towers, rnd):
        return 0.2 + 0.15 * sum(sum(t.tiers) for t in towers)

    def leaks(self, towers, rounds, scale, per_round=False):
        lost = {r: max(0.0, 10 * (1 - self.margin(towers, r) * scale)) for r in rounds}
        return lost if per_round else sum(lost.values())


def test_a_grown_path_is_bought_whole_while_the_cash_lasts():
    ex = GrowEx()
    status, found = R.best(ex, PerTier(), 8000, 90, 100, lives=1)
    assert status == "buy" and found[0].goal and found[0].goal["id"] == "b1", (status, found)
    goal = R._tiers(found[0].goal["to"])
    assert R.buy_best(ex, PerTier(), 8000, 90, 100, lives=1) == "bought"
    # more than the first tier went in, and never more than the $8,000 rated on
    assert len(ex.bought) > 1, ex.bought
    spent = T.total_cost("buccaneer", tuple(ex.g.towers["b1"].tiers), FAMILY) - T.total_cost("buccaneer", (0, 0, 0), FAMILY)
    assert spent <= 8000, spent
    if tuple(ex.g.towers["b1"].tiers) == goal:
        assert getattr(ex, "reinforce_goal", None) is None      # finished: no goal left
    else:
        assert ex.reinforce_goal["step"]["to"] == found[0].goal["to"]


def test_an_unfinished_goal_stays_on_offer():
    ex = GrowEx()
    ex.fail_after = 1                          # only the first tier goes through now
    assert R.buy_best(ex, PerTier(), 8000, 90, 100, lives=1) == "bought"
    assert len(ex.bought) == 1
    goal = ex.reinforce_goal
    assert goal and goal["step"]["id"] == "b1" and goal["round"] >= 90, goal
    # the next look offers the rest of the path, costed at what is left to pay
    ex.fail_after = None
    o = R.goal_option(ex, 8000, goal["round"])
    target = R._tiers(goal["step"]["to"])
    left = T.total_cost("buccaneer", target, FAMILY) - T.total_cost("buccaneer", tuple(ex.g.towers["b1"].tiers), FAMILY)
    assert o is not None and o.goal == goal["step"] and o.cost == left, o
    assert tuple(o.towers[0].tiers) == target                 # rated at the finished crosspath
    # and buying it carries the path on (a model where only b1 reaches the
    # track, so no new tower competes with the goal)
    class OnlyB1(PerTier):
        def margin(self, towers, rnd):
            return 0.2 + 0.15 * sum(sum(t.tiers) for t in towers if t.tid == "b1")
    assert R.buy_best(ex, OnlyB1(), 8000, goal["round"], 100, lives=1) == "bought" and len(ex.bought) > 2
    assert tuple(ex.g.towers["b1"].tiers) == target or ex.reinforce_goal["step"] == goal["step"]


def test_a_goal_is_dropped_when_it_no_longer_holds():
    ex = GrowEx(tiers=(1, 1, 0))
    ex.reinforce_goal = {"step": {"do": "upgrade", "id": "b1", "to": "4-2-0"}, "round": 95}
    assert R.goal_option(ex, 0, 93) is None and ex.reinforce_goal     # no cash yet: kept
    assert R.goal_option(ex, 5000, 96) is None and ex.reinforce_goal is None   # its round passed
    ex.reinforce_goal = {"step": {"do": "upgrade", "id": "b1", "to": "4-2-0"}, "round": 95}
    ex.income_until = lambda due, rnd: 100                         # income cannot pay the rest in time
    assert R.goal_option(ex, 500, 93) is None and ex.reinforce_goal is None
    del ex.income_until
    ex.reinforce_goal = {"step": {"do": "upgrade", "id": "b1", "to": "4-2-0"}, "round": 95}
    ex.g.towers["b1"].tiers = [1, 1, 1]                               # went another way
    assert R.goal_option(ex, 5000, 93) is None and ex.reinforce_goal is None
    ex.reinforce_goal = {"step": {"do": "upgrade", "id": "b1", "to": "4-2-0"}, "round": 95}
    del ex.g.towers["b1"]                                             # sold or gone
    assert R.goal_option(ex, 5000, 93) is None and ex.reinforce_goal is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
