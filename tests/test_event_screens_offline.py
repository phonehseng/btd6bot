"""Offline checks for the collection-event screens (menus.py).

Synthetic frames: the crate-opening screen is face-down blue cards on an
almost black background. Run: python tests/test_event_screens_offline.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import menus as M  # noqa: E402
from btd6bot.vision import Word  # noqa: E402

W, H = 1920, 1200
CARD_BGR = (160, 90, 10)    # the cards' blue (BGR)


def _menus():
    return M.Menus.__new__(M.Menus)   # no screen needed for these helpers


def _cards_screen(xs=(790, 1125)):
    img = np.full((H, W, 3), (24, 20, 20), np.uint8)    # near black
    for x in xs:
        img[520:680, x - 80:x + 80] = CARD_BGR
    return img


def test_cards_found_left_to_right():
    cards = _menus().reward_cards(_cards_screen())
    assert len(cards) == 2, cards
    assert abs(cards[0][0] - 790 / W) < 0.01 and abs(cards[1][0] - 1125 / W) < 0.01


def test_no_cards_on_a_bright_screen():
    img = _cards_screen()
    img[:] = np.maximum(img, 120)          # a normal, bright menu screen
    assert _menus().reward_cards(img) == []


def test_collect_button_beats_the_title():
    """The title "COLLECTION EVENT" contains "collect"; the button wins, also
    when OCR reads its C as G."""
    m = _menus()
    m.words = [Word("COLLeGTIoNEVenT", 0.5, 0.06, 0.4, 0.05, 0.8), Word("COLLEGT", 0.5, 0.63, 0.12, 0.05, 0.89)]
    w = m.find("next", "continue", "collect")
    assert w is not None and w.text == "COLLEGT", w


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
