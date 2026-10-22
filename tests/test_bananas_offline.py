"""Offline checks for the banana collector (Game._banana_blobs, drops_bananas).

Synthetic scenes: a green field around a farm; yellow discs stand in for
bananas. Run: python tests/test_bananas_offline.py
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.game import Game, Placed  # noqa: E402

YELLOW = (40, 220, 250)   # BGR, banana yellow
SIZE = 400                # patch side in pixels (the farm sits in the middle)
CENTRE = (SIZE // 2, SIZE // 2)
WINDOW_AREA = 1920 * 1200


def _field():
    img = np.zeros((SIZE, SIZE, 3), np.uint8)
    img[:] = (60, 140, 60)    # grass
    return img


def _blobs(patch, bg, reach=190, own=40):
    g = Game.__new__(Game)    # only the class constants are needed
    return g._banana_blobs(patch, bg, CENTRE, reach, own, WINDOW_AREA)


def test_new_bananas_are_found():
    bg = _field()
    scene = bg.copy()
    for spot in ((120, 200), (280, 150), (200, 320)):
        cv2.circle(scene, spot, 9, YELLOW, -1)
    found = _blobs(scene, bg)
    assert len(found) == 3, found
    for spot in ((120, 200), (280, 150), (200, 320)):
        assert any(abs(x - spot[0]) <= 2 and abs(y - spot[1]) <= 2 for x, y in found), (spot, found)


def test_yellow_scenery_and_the_farm_itself_are_ignored():
    bg = _field()
    cv2.circle(bg, (100, 100), 12, YELLOW, -1)        # a yellow flower: there from the start
    scene = bg.copy()
    cv2.circle(scene, CENTRE, 15, YELLOW, -1)         # the farm's own bananas (sprite)
    cv2.circle(scene, (395, 395), 9, YELLOW, -1)      # outside the reach
    assert _blobs(scene, bg) == [], _blobs(scene, bg)


def test_only_farms_that_drop_bananas():
    assert Game.drops_bananas(Placed("f", "farm", 0.5, 0.5, [2, 0, 2]))
    assert not Game.drops_bananas(Placed("f", "farm", 0.5, 0.5, [0, 0, 3]))   # Marketplace
    assert not Game.drops_bananas(Placed("f", "farm", 0.5, 0.5, [0, 3, 0]))   # Monkey Bank
    assert not Game.drops_bananas(Placed("t", "tack", 0.5, 0.5, [2, 0, 2]))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
