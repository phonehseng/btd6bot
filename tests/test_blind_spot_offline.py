"""A damage tower is never offered a spot whose range reaches no track.

Glacial Trail Medium (2026-11-05, loss case 20261105_021907): the map's
learned refusals had eaten the few land cells near the track, so for the
ninjas and the alchemist no legal cell reached any track cell. pick_spots
still handed out the best-scored cells - a ledge 35-47 cells from the track -
and the whole defence stood there while round 15 leaked 100 lives. Now such a
step gets no spot at all (it is set aside, and the dead end is logged by
_any_legal_spot), unless a blocked cell is worth probing. Offline: the
executor with a fake game and a reach grid of zeros.
Run: python tests/test_blind_spot_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import placement as PL           # noqa: E402
from btd6bot import strategy as S             # noqa: E402


class LedgeModel(F.FakeModel):
    """Cover scores rise to the right, so the right half ranks first; the
    tests put the track's reach there or nowhere."""

    def score_spots(self, rc, seg, occupied, near=None, **kw):
        ramp = np.linspace(1.0, 2.0, self.W, dtype=np.float32)
        return np.tile(ramp, (self.H, 1))

    def spot_weight(self, seg, covered):
        return np.ones((self.H, self.W), np.float32)


STEP = {"do": "place", "id": "n1", "kind": "ninja", "role": "dps"}


def executor(reach):
    plan = {"id": "t", "name": "t", "hero": None, "plan": [dict(STEP)]}
    ex = S.Executor(F.FakeGame(), LedgeModel(), plan, "medium", F.full_account())
    ex._reach_cache = {"ninja": reach}
    return ex


def _with_fakes(fn):
    """Run fn with every cell legal and no sight blockers."""
    original, sight = PL.valid_spots, PL.needs_sight
    PL.valid_spots = lambda *a, **k: np.ones((LedgeModel.H, LedgeModel.W), bool)
    PL.needs_sight = lambda *a: False
    try:
        return fn()
    finally:
        PL.valid_spots, PL.needs_sight = original, sight


def test_no_spot_when_no_legal_cell_reaches_the_track():
    reach = np.zeros((LedgeModel.H, LedgeModel.W), np.float32)
    reach[0, 0] = 1e-14          # float noise from the range filter is still "no track"

    def run():
        ex = executor(reach)
        return ex.pick_spots("ninja", STEP, n=3), ex._spots_widening("ninja", STEP)
    spots, widened = _with_fakes(run)
    assert spots == [], spots
    assert widened == [], widened     # the relaxations find nothing either: the step is set aside


def test_spots_in_reach_are_still_offered():
    reach = np.zeros((LedgeModel.H, LedgeModel.W), np.float32)
    reach[:, LedgeModel.W // 2:] = 100.0
    spots = _with_fakes(lambda: executor(reach).pick_spots("ninja", STEP, n=3))
    assert spots, "legal cells reaching the track exist"
    assert all(cx >= LedgeModel.W // 2 for cx, _, _ in spots), spots


def test_global_range_towers_are_untouched():
    reach = np.zeros((LedgeModel.H, LedgeModel.W), np.float32)
    step = dict(STEP, id="s1", kind="sniper")
    spots = _with_fakes(lambda: executor(reach).pick_spots("sniper", step, n=3))
    assert spots, "a sniper hits the track from anywhere"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
