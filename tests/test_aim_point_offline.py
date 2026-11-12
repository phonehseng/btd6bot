"""Fixed aim points for Mortar and Dartling (docs/model_fix_plan.md item 14,
bot side): Executor._aim gives a Mortar its reticle, or locks a Dartling, on
the densest track point - the cursor-park point - behind the switches
Executor.MORTAR_AIM and DARTLING_LOCK, which stay off until the flow is
checked in game (see their comment in strategy.py).

Offline: fakes only, no game. Run: python tests/test_aim_point_offline.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import match as M  # noqa: E402
from btd6bot import strategy as S  # noqa: E402


class FakeMap:
    """A 60x40 grid with one horizontal lane and a short crossing lane: the
    densest point is where they meet."""
    def __init__(self):
        self.heat = np.zeros((40, 60), np.float32)
        self.heat[20, :] = 1
        self.heat[10:31, 30] = 1

    def cell_to_frac(self, x, y):
        return (x / 60.0, y / 40.0)


class FakeGame:
    def __init__(self, target_ok=True, point_ok=True):
        self.calls = []
        self.target_ok, self.point_ok = target_ok, point_ok

    def target(self, p, mode):
        self.calls.append(("target", p.tid, mode))
        return self.target_ok

    def set_target_point(self, p, fx, fy):
        self.calls.append(("point", p.tid, round(fx, 3), round(fy, 3)))
        return self.point_ok


def executor(g):
    ex = N(g=g, m=FakeMap(), plan=[], fill=[], MORTAR_AIM=S.Executor.MORTAR_AIM,
           DARTLING_LOCK=S.Executor.DARTLING_LOCK, HELI_PURSUIT_TIER=S.Executor.HELI_PURSUIT_TIER)
    for name in ("_aim", "_aim_fixed", "_aim_point", "_explicit_target"):
        setattr(ex, name, getattr(S.Executor, name).__get__(ex))
    return ex


def test_switches_are_off_until_checked_in_game():
    assert S.Executor.MORTAR_AIM is False and S.Executor.DARTLING_LOCK is False
    g = FakeGame()
    ex = executor(g)
    mortar = N(tid="m1", kind="mortar", tiers=(0, 0, 0))
    ex._aim(mortar)
    assert g.calls == [] and not hasattr(mortar, "aim")


POINT = M.densest_track_point(FakeMap())
PX, PY = round(POINT[0], 3), round(POINT[1], 3)


def test_the_aim_point_is_the_densest_track_point():
    """On the crossing lane, within reach of the junction - not out on the
    single lane."""
    x, y = POINT
    assert x == 30 / 60.0 and abs(y - 0.5) <= 7 / 40.0, POINT


def test_mortar_gets_its_reticle_once():
    g = FakeGame()
    ex = executor(g)
    ex.MORTAR_AIM = True
    mortar = N(tid="m1", kind="mortar", tiers=(0, 0, 0))
    ex._aim(mortar)
    assert g.calls == [("point", "m1", PX, PY)] and mortar.aim == "point"
    ex._aim(mortar)                                  # an upgrade later: not again
    assert len(g.calls) == 1


def test_dartling_is_locked_then_pointed():
    g = FakeGame()
    ex = executor(g)
    ex.DARTLING_LOCK = True
    dart = N(tid="d1", kind="dartling", tiers=(0, 0, 0))
    ex._aim(dart)
    assert g.calls == [("target", "d1", "lock"), ("point", "d1", PX, PY)] and dart.aim == "point"


def test_a_failed_aim_is_not_retried_and_the_cursor_still_parks():
    g = FakeGame(target_ok=False)
    ex = executor(g)
    ex.DARTLING_LOCK = True
    dart = N(tid="d1", kind="dartling", tiers=(0, 0, 0))
    ex._aim(dart)
    assert dart.aim == "failed point" and g.calls == [("target", "d1", "lock")]
    ex._aim(dart)
    assert len(g.calls) == 1
    # Match._park_cursor keeps parking for a dartling that is not on a point
    parked = []
    match = M.Match.__new__(M.Match)
    match.m, match._park, match._t_park = FakeMap(), None, -1e9
    match.g = N(towers={"d1": dart}, inp=N(move=lambda x, y, fast=False: parked.append((x, y))))
    match._park_cursor(0.0)
    assert parked == [POINT]
    dart.aim = "point"
    parked.clear()
    match._t_park = -1e9
    match._park_cursor(10.0)
    assert parked == []                              # locked on its point: the cursor is free


def test_a_plan_that_sets_targeting_itself_keeps_it():
    g = FakeGame()
    ex = executor(g)
    ex.MORTAR_AIM = True
    ex.plan = [{"do": "target", "id": "m1", "mode": "first"}]
    ex._aim(N(tid="m1", kind="mortar", tiers=(0, 0, 0)))
    assert g.calls == []


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, repr(e)[:400])
    sys.exit(1 if failed else 0)
