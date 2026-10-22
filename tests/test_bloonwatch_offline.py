"""Offline checks for bloonwatch.BloonWatch on synthetic frames: a bloon-sized
disc moving along a route is seen at its depth; scenery that animates, a
tower placed later, a one-frame flicker and an open upgrade panel are not.
Run: python tests/test_bloonwatch_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import bloonwatch as B  # noqa: E402
from btd6bot.maplearn import GRID  # noqa: E402

PF = (0.0, 0.04, 0.855, 0.96)
W, H = 1920, 1200
SH, SW = GRID[1] * B.WORK_SCALE, GRID[0] * B.WORK_SCALE
CLOSE = (0.84, 0.085)                 # a panel's close button (screen fractions)

# a horizontal route across the middle of the play field: progress = x
PROGRESS = np.full((SH, SW), np.nan, np.float32)
PROGRESS[SH // 2 - 20:SH // 2 + 20, :] = np.linspace(0, 1, SW, dtype=np.float32)[None, :]
ROUTE_Y = PF[1] + 0.5 * (PF[3] - PF[1])


def background(t=0):
    """Sandy map with a strip of 'water' near the top that changes shade."""
    f = np.full((H, W, 3), (150, 190, 210), np.uint8)
    f[200:260, :] = (200, 160 + 30 * (t % 2), 40)       # animated scenery
    return f


def with_bloon(f, fx, r=18, colour=(40, 40, 230)):
    f = f.copy()
    cv2.circle(f, (int(fx * W), int(ROUTE_Y * H)), r, colour, -1)
    return f


def watch():
    w = B.BloonWatch("synthetic", PF, [CLOSE], progress=PROGRESS.copy())
    for i in range(B.EMPTY_FRAMES):
        w.learn_empty(background(i))
    assert w.ready()
    return w


def test_a_moving_bloon_is_seen_at_its_depth():
    w = watch()
    depths = [w.look(with_bloon(background(i), fx), now=i * 0.2)
              for i, fx in enumerate(np.linspace(0.1, 0.7, 21))]
    assert depths[0] == 0.0                          # first sighting: not confirmed yet
    assert all(d > 0 for d in depths[1:])
    # the front edge of the disc, 18 px past its centre
    assert abs(depths[-1] - (0.7 * W + 18) / (PF[2] - PF[0]) / W) < 0.03
    s = w.end_round(5)
    assert s["round"] == 5 and abs(s["deepest"] - depths[-1]) < 0.01


def test_animated_scenery_and_empty_rounds_read_zero():
    w = watch()
    assert all(w.look(background(i), now=i * 0.2) == 0.0 for i in range(10))


def test_a_one_frame_flicker_is_not_a_bloon():
    w = watch()
    assert w.look(with_bloon(background(0), 0.6), now=0.0) == 0.0
    assert w.look(background(1), now=0.2) == 0.0


def test_something_that_stays_put_becomes_scenery():
    w = watch()
    tower = lambda i: with_bloon(background(i), 0.5, r=22, colour=(30, 120, 30))
    early = [w.look(tower(i), now=i * 0.5) for i in range(4)]
    assert max(early) > 0                            # seen while new ...
    late = [w.look(tower(i), now=10 + i * 0.5) for i in range(4)]
    assert max(late) == 0.0                          # ... then part of the map


def test_known_towers_are_masked():
    w = watch()
    tower = N(x=0.5, y=ROUTE_Y)
    depths = [w.look(with_bloon(background(i), 0.5, r=22), now=i * 0.2, towers=[tower]) for i in range(4)]
    assert max(depths) == 0.0


def test_an_open_panel_does_not_count():
    w = watch()
    f = background(0)
    cx, cy = int(CLOSE[0] * W), int(CLOSE[1] * H)
    cv2.rectangle(f, (cx - 40, cy - 40), (cx + 40, cy + 40), (20, 60, 120), -1)
    assert w.look(f, now=0.0) is None


def test_off_without_a_map():
    w = B.BloonWatch(None, PF)
    w.learn_empty(background())
    assert not w.ready() and w.look(background(), now=0.0) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
