"""The Apopalypse intro box (2026-10-27, Lost Crevasse): its only button is a
green Play arrow with no text, so the bot sat on it reading "unknown". It is
recognised by its words and its arrow is found by colour. Offline: a saved frame."""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.game import _colour_blob   # noqa: E402
from btd6bot.menus import Menus         # noqa: E402
from btd6bot.runner import Bot          # noqa: E402

IMG = cv2.imread(str(Path(__file__).resolve().parent / "fixtures" / "apopalypse_intro.jpg"))


def test_the_intro_box_is_recognised():
    m = Menus(N(grab=lambda region=None: IMG, width=1920, height=1200, refresh=lambda: None), None)
    assert m.identify() == "mode_intro_play"


def test_the_play_arrow_is_found():
    x, y = _colour_blob(IMG, Bot.INTRO_PLAY_REGION, (40, 120, 120), (85, 255, 255))
    assert 0.47 < x < 0.53 and 0.66 < y < 0.73, (x, y)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
