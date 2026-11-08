"""Covered Garden: the open pane is read off the screen, not trusted to the
bot's round number - no game needed.

Live game 2026-11-07 20:35-20:39 (coveredgarden_medium): the panes opened
exactly as modelled (one quarter per round, clockwise from bottom-left on
round 1), but from 20:37:21 to 20:38:33 the top-left quarter was open while
the bot still believed round 17 - a tower's side panel covered the HUD's
round counter - and it clicked the shut bottom-left quarter some 40 times.

Fixtures (tests/fixtures/covered_garden_*.jpg) are frames of that game's
recordings (1280x800): a shut quarter shows a white grid, the open one none.
Covers:
  * mapgeom.pane_open_on_screen on every quarter open, with the upgrade
    panel over the right quarters, while a tower is held, at the game's own
    1920x1200 size, with a panel over the left quarters, and unclear frames;
  * the executor judging panes by the screen when its round is stale, and by
    the round when the screen is unclear.
Run: python tests/test_pane_screen_offline.py"""
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import layout as L, mapgeom  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

import simulate_threats as SIM  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)
FIX = ROOT / "tests" / "fixtures"
BL, TL, TR, BR = 0, 1, 2, 3          # cycle order: open in rounds 1, 2, 3, 4 (then again)
# fixture -> the quarter open in it
OPEN = {"covered_garden_open_bl.jpg": BL,
        "covered_garden_open_tl_holding.jpg": TL,     # a mermonkey held over the shut bottom-left
        "covered_garden_open_tr.jpg": TR,
        "covered_garden_open_tr_panel.jpg": TR,       # upgrade panel over the right quarters
        "covered_garden_open_br.jpg": BR,
        "covered_garden_open_br_panel.jpg": BR}


def model():
    m = MapModel("Covered Garden", L.LAYOUTS["16:10"]["playfield"])
    mapgeom.apply(m, mapgeom.load("Covered Garden"))
    return m


def frame(name):
    img = cv2.imread(str(FIX / name))
    assert img is not None, name
    return img


def test_each_quarter_is_read_open():
    m = model()
    for name, index in OPEN.items():
        assert mapgeom.pane_open_on_screen(m, frame(name)) == index, name


def test_game_size_frames_read_the_same():
    m = model()
    for name, index in OPEN.items():
        big = cv2.resize(frame(name), (1920, 1200), interpolation=cv2.INTER_LINEAR)
        assert mapgeom.pane_open_on_screen(m, big) == index, name


def test_a_panel_over_the_left_quarters_still_reads():
    """A tower on the right half opens its panel at the far left (layout
    upg_left); it hides part of the left quarters, never all of them."""
    m = model()
    img = frame("covered_garden_open_tr.jpg")
    h, w = img.shape[:2]
    box = L.LAYOUTS["16:10"]["upg_left"]["box"]
    img[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)] = (40, 70, 110)   # panel brown
    assert mapgeom.pane_open_on_screen(m, img) == TR


def test_unclear_frames_say_nothing():
    m = model()
    # two quarters without grid (the game was switching screens)
    assert mapgeom.pane_open_on_screen(m, frame("covered_garden_unclear.jpg")) is None
    # off the match screen: no grid anywhere
    assert mapgeom.pane_open_on_screen(m, np.zeros((800, 1280, 3), np.uint8)) is None
    assert mapgeom.pane_open_on_screen(m, None) is None
    # maps without panes
    meadow = MapModel("Monkey Meadow", L.LAYOUTS["16:10"]["playfield"])
    mapgeom.apply(meadow, mapgeom.load("Monkey Meadow"))
    assert mapgeom.pane_open_on_screen(meadow, frame("covered_garden_open_tr.jpg")) is None


def test_round_for_open_pane_moves_forward():
    m = model()
    assert mapgeom.round_for_open_pane(m, TL, 17) == 18      # the stale round of 2026-11-07
    assert mapgeom.round_for_open_pane(m, BL, 17) == 17
    assert mapgeom.round_for_open_pane(m, TR, None) == 3
    assert mapgeom.round_for_open_pane(m, None, 17) == 17


class ScreenGame(SIM.CashGame):
    """The simulator's cash game with a screen: fresh() returns `shown`."""
    shown = None

    def fresh(self):
        return self.shown


def executor(plan):
    g = ScreenGame("medium")
    g.cash = 50000.0
    ex = S.Executor(g, model(), {"id": "t", "hero": "quincy", "plan": plan, "modes": ["medium"]},
                    "medium", SIM.full_account())
    ex.now_round = 17                 # the bot believes round 17: bottom-left open
    return g, ex


def test_executor_trusts_the_screen_over_a_stale_round():
    bottom_left = {"do": "place", "id": "sky3", "kind": "skywarden", "role": "dps", "at": [0.281, 0.538]}
    top_left = {"do": "place", "id": "sky1", "kind": "skywarden", "role": "dps", "at": [0.345, 0.249]}
    g, ex = executor([bottom_left, top_left])
    g.shown = frame("covered_garden_open_tl_holding.jpg")        # the screen: top-left open
    assert ex._pane_shut(bottom_left) and not ex._pane_shut(top_left)
    assert ex._pane_round() == 18
    p = SIM.Placed("sky3", "skywarden", 0.281, 0.538)
    assert not ex._reachable(p), "no click on a tower under the shut bottom-left pane"


def test_executor_falls_back_to_the_round_when_the_screen_is_unclear():
    bottom_left = {"do": "place", "id": "sky3", "kind": "skywarden", "role": "dps", "at": [0.281, 0.538]}
    g, ex = executor([bottom_left])
    g.shown = frame("covered_garden_unclear.jpg")
    assert not ex._pane_shut(bottom_left) and ex._pane_round() == 17


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
