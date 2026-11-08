"""Offline checks for the useless-tower rules on Executor: a damage tower
that pops nothing is sold (two zero pop reads, after a grace period), a
blocked spot that reaches far more track than any legal one is probed once,
and a probe the game accepts is learned for the map.
Run: python tests/test_useless_towers_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.strategy import Executor  # noqa: E402


class FakeGame:
    """Towers by id; select() 'reads' the pop count given in `pops`."""

    def __init__(self, pops):
        self.towers = {tid: SimpleNamespace(tid=tid, kind="sniper", x=0.5, y=0.5, tiers=[0, 0, 0])
                       for tid in pops}
        self.pops = pops
        self.sold = []

    def select(self, p):
        p.pops = self.pops[p.tid]
        return True

    def deselect(self, p):
        pass

    def sell(self, p):
        self.sold.append(p.tid)
        del self.towers[p.tid]
        return True


def _seller(pops):
    ex = Executor.__new__(Executor)
    ex.no_sell = False
    ex.g = FakeGame(pops)
    # a sold tower's spot is remembered in failed_spots (_sell_and_avoid)
    ex.failed_spots = set()
    ex.m = SimpleNamespace(frac_to_cell=lambda x, y: (x * 100, y * 100))
    return ex


def test_a_tower_that_pops_nothing_is_sold():
    ex = _seller({"s1": 0, "s2": 40})
    sold_at = None
    for rnd in range(1, 30):
        if ex.sell_useless(rnd):
            sold_at = rnd
            break
    assert ex.g.sold == ["s1"]
    # never inside the grace period, and only after a second zero read
    assert sold_at > 1 + Executor.POP_GRACE_ROUNDS


def test_no_sale_while_lives_fall_or_in_no_sell_modes():
    ex = _seller({"s1": 0, "s2": 40})
    for rnd in range(1, 30):
        ex.sell_useless(rnd, lives_dropped=True)
    assert ex.g.sold == []
    ex = _seller({"s1": 0, "s2": 40})
    ex.no_sell = True
    for rnd in range(1, 30):
        ex.sell_useless(rnd)
    assert ex.g.sold == []


def test_the_last_tower_is_never_sold():
    ex = _seller({"s1": 0})
    for rnd in range(1, 30):
        ex.sell_useless(rnd)
    assert ex.g.sold == []


def _prober(best_legal, blocked_reach):
    """A 20x20 map: legal ground on the left half reaching `best_legal`
    track cells, one blocked cell at (15, 5) reaching `blocked_reach`."""
    ex = Executor.__new__(Executor)
    reach = np.zeros((20, 20), np.float32)
    reach[:, :10] = best_legal
    reach[5, 15] = blocked_reach
    valid = np.zeros((20, 20), bool)
    valid[:, :10] = True
    ex._reach = lambda kind: reach
    ex.blocked = np.zeros((20, 20), bool)
    ex.failed_spots = set()
    ex.accepted = []
    ex.m = SimpleNamespace(t_cnt=np.zeros((20, 20)), refused_mask=lambda s: np.zeros((20, 20), bool),
                           frac_to_cell=lambda x, y: (x, y),
                           accept=lambda surface, cx, cy: ex.accepted.append((surface, cx, cy)))
    return ex, valid


def test_a_much_better_blocked_spot_is_probed_once():
    ex, valid = _prober(best_legal=100, blocked_reach=150)
    assert ex._probe_spot("tack", valid) == (15, 5, 2e9)
    assert ex._probe_spot("tack", valid) is None    # one probe per kind and game


def test_a_slightly_better_blocked_spot_is_not_probed():
    ex, valid = _prober(best_legal=100, blocked_reach=110)
    assert ex._probe_spot("tack", valid) is None


def test_an_accepted_probe_is_learned():
    ex, valid = _prober(best_legal=100, blocked_reach=150)
    ex._probe_spot("tack", valid)
    ex._learn_probe("tack", SimpleNamespace(x=15, y=5))
    assert ex.accepted == [("land", 15, 5)]
    ex.accepted.clear()
    ex._learn_probe("tack", SimpleNamespace(x=3, y=3))   # an ordinary spot: nothing learned
    assert ex.accepted == []


def _reach_seller(best, here):
    """Two subs that popped bloons, on a 20x20 map where the best legal sub
    spot reaches `best` track cells and the subs' own spot `here`."""
    from btd6bot import placement as PL
    ex = Executor.__new__(Executor)
    ex.no_sell = False
    ex.removed = ()
    ex.failed_spots = set()
    ex._sale_blocked = lambda rnd: None
    ex.g = FakeGame({"sb1": 40, "sb2": 40})
    for p in ex.g.towers.values():
        p.kind, p.x, p.y, p.placed_round, p.pops = "sub", 15, 5, 1, 40
    reach = np.full((20, 20), best, np.float32)
    reach[5, 15] = here
    ex._reach = lambda kind: reach
    ex.m = SimpleNamespace(frac_to_cell=lambda x, y: (x, y))
    saved = PL.valid_spots
    PL.valid_spots = lambda *a, **k: np.ones((20, 20), bool)
    return ex, lambda: setattr(PL, "valid_spots", saved)


def test_no_sale_for_reach_when_no_spot_reaches_the_track_now():
    """Erosion Reverse (2026-11-08): the track was painted for the current
    lane only, far from the water; sb1-sb3 'reached -0 of best 0 track cells'
    and were sold one after another. Nowhere better to go is no reason to sell."""
    ex, undo = _reach_seller(best=0.3, here=0.0)
    try:
        assert not ex.sell_useless(30) and ex.g.sold == []
    finally:
        undo()
    # a bare sub that really stands far from the track while others reach it is still sold
    ex, undo = _reach_seller(best=200.0, here=5.0)
    try:
        assert ex.sell_useless(30) and len(ex.g.sold) == 1
    finally:
        undo()


def test_an_advanced_intel_sub_is_not_sold_for_its_own_reach():
    """A 2-x-x sub shoots what other towers see: its own range says nothing
    (sb3 was 2-0-4 when Erosion Reverse sold it)."""
    ex, undo = _reach_seller(best=200.0, here=5.0)
    try:
        for p in ex.g.towers.values():
            p.tiers = [2, 0, 4]
        assert not ex.sell_useless(30) and ex.g.sold == []
    finally:
        undo()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
