"""A mode's intro box ("IMPOPPABLE - Impoppable will test your Bloon popping
skills to the max ... OK") can cover the match after it already reads as
in_game; while it is up no hotkey picks a tower up (Cargo and Luminous Cove
Impoppable, 2026-11-05: 6 minutes of failed pick-ups, the game given up).
game.find_intro_box_ok knows the box by its blue panel around the green OK.
Offline: downscaled captures in tests/fixtures (two with the box, two of a
match without it).
Run: python tests/test_intro_box_offline.py"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.game import find_intro_box_ok   # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def test_the_ok_of_an_intro_box_is_found_low_in_its_middle():
    for name in ("intro_box_luminous_cove.jpg", "intro_box_cargo.jpg"):
        spot = find_intro_box_ok(cv2.imread(str(FIX / name)))
        assert spot is not None, name
        assert abs(spot[0] - 0.5) < 0.03 and abs(spot[1] - 0.70) < 0.03, (name, spot)


def test_a_match_without_the_box_gives_nothing_to_click():
    for name in ("match_cargo.jpg", "match_end_of_the_road.jpg"):
        assert find_intro_box_ok(cv2.imread(str(FIX / name))) is None, name


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
