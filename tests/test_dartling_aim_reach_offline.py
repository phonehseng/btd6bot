"""Dartlings fire where the bloons pass every round, from within their darts' reach.

Why
---
Last Resort Deflation, 2026-11-12 (loss case 20261112_164934): solo_dartling
lost round 55 with all 200 lives. A Dartling Gunner fires along the line to
the cursor, and the bot rests the cursor on the densest track point
(match.densest_track_point). On Last Resort the routes take turns on a
4-round cycle, and that point was the top-left bend at 0.126, 0.164, a
cell one round in four passes. The middle Dartling x2 at 0.505, 0.632 stood
174 units from it, beyond its darts' 162: it popped nothing in 13 rounds,
was sold, bought again on the next cell, and popped nothing again.

Checked here, on the live learned Last Resort map:
  * the cursor's resting point lies on track at least half the rounds pass
    (MapModel.round_share), not on the one-round-in-four bend;
  * a Dartling's spot is kept within Executor.DARTLING_AIM_SHARE of its
    darts' reach of that point: the lost game's x2 cell is blocked, the
    cells round the point are not;
  * every other tower is left alone.

Run: python tests/test_dartling_aim_reach_offline.py (no game)."""
import logging
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pin_spots  # noqa: E402
from btd6bot import maplearn as ML  # noqa: E402
from btd6bot import match as M  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

MAP = "Last Resort"
LOST_X2 = (0.505, 0.632)        # the Dartling that popped nothing in 13 rounds
OLD_PARK = (0.126, 0.164)       # where the cursor rested in the lost game


def _model():
    ML.DATA = pin_spots.live_maps_dir()
    return ML.MapModel.load(MAP, LAYOUTS["16:10"]["playfield"])


def _executor(m):
    """Just enough of an Executor for _keep_in_aim_reach."""
    ex = SimpleNamespace(m=m, DARTLING_AIM_SHARE=S.Executor.DARTLING_AIM_SHARE)
    for name in ("_keep_in_aim_reach", "_dart_reach"):
        setattr(ex, name, getattr(S.Executor, name).__get__(ex))
    return ex


def test_cursor_rests_on_track_most_rounds_pass():
    m = _model()
    share = m.round_share()
    assert share is not None, "Last Resort's routes take turns: it must have round shares"
    x, y = m.frac_to_cell(*M.densest_track_point(m))
    ox, oy = m.frac_to_cell(*OLD_PARK)
    assert share[oy, ox] <= 0.25, "the lost game's point was a one-round-in-four cell"
    assert share[y, x] >= 0.5, (M.densest_track_point(m), float(share[y, x]))


def test_dartling_stands_within_its_darts_reach_of_the_point():
    m = _model()
    ex = _executor(m)
    reach = ex._dart_reach("dartling")
    assert reach and 100 < reach < 300, reach
    valid = np.ones(m.heat.shape, bool)
    block = ex._keep_in_aim_reach("dartling", valid, np.zeros(m.heat.shape, bool))
    lx, ly = m.frac_to_cell(*LOST_X2)
    assert block[ly, lx], "the lost game's x2 cell is out of reach of the aim point"
    px, py = m.frac_to_cell(*M.densest_track_point(m))
    assert not block[py, px]
    # every cell left open is within the share of the reach
    ys, xs = np.nonzero(~block)
    upc = PL.units_per_cell(m)
    far = max(math.hypot(x - px, y - py) for x, y in zip(xs, ys)) * upc
    assert far <= reach * S.Executor.DARTLING_AIM_SHARE + upc, (far, reach)


def test_other_towers_are_left_alone():
    m = _model()
    ex = _executor(m)
    valid = np.ones(m.heat.shape, bool)
    block = np.zeros(m.heat.shape, bool)
    for kind in ("sniper", "ninja", "mortar"):
        assert ex._keep_in_aim_reach(kind, valid, block) is block


if __name__ == "__main__":
    import inspect
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", fname, repr(e)[:400])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
