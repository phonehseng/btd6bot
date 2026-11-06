"""Game.is_holding on real frames, without the game.

Cracked Apopalypse (2026-11-06, loss case 20261106_171204): the map's
orange-red ground lies where the red cancel button is drawn while a tower is
held, and the old red-only test said "holding" with nothing on the cursor.
Every placement that worked was logged as a refused click, the tower was
picked up and placed again, and ~30 towers were bought that the bot never
knew about. The two fixtures are frames of that game's recording, 0.25 s
apart: one with a dart monkey on the cursor, one right after it was placed.
Run: python tests/test_holding_offline.py"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L  # noqa: E402
from btd6bot.game import Game  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def make_game():
    """A Game with only what is_holding needs: the layout of the recording's
    1280x800 frames (no screen, no input)."""
    g = Game.__new__(Game)
    g.lay = L.get(1280, 800)
    return g


def frame(name):
    f = cv2.imread(str(FIX / name))
    assert f is not None, f"missing fixture {name}"
    return f


def test_cracked_ground_is_not_a_held_tower():
    g = make_game()
    assert not g.is_holding(frame("cracked_not_holding.jpg")), \
        "Cracked's red ground under the cancel button read as a held tower"


def test_held_tower_is_seen_on_cracked():
    g = make_game()
    assert g.is_holding(frame("cracked_holding.jpg")), "the red cancel button with its X was missed"


if __name__ == "__main__":
    test_cracked_ground_is_not_a_held_tower()
    test_held_tower_is_seen_on_cracked()
    print("OK test_holding_offline")
