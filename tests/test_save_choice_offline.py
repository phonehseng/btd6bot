"""The game's "Choose which save" dialog: two blue cards, "This Device" and
"On the Cloud", each with a USE button. In Peninsula Impoppable on 2026-11-12
(losses/20261112_090153_Peninsula_impoppable, game.log 08:59:24-34) it came
up over the dimmed match, read as a crate's reward cards, and the bot clicked
the USE buttons of both cards. Using the cloud save could load an older save
over the local progress, so the bot must know the dialog, press only This
Device's USE, and press nothing when it is not certain which button that is.

Offline: tests/fixtures/save_choice_peninsula.jpg is the still of that game
(frames/game_008.jpg); the other checks use synthetic OCR words.
Run: python tests/test_save_choice_offline.py"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import menus as M        # noqa: E402
from btd6bot.vision import Vision, Word  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
STILL = FIX / "save_choice_peninsula.jpg"
# where the two USE buttons are on the still (fractions of the window)
THIS_DEVICE_USE = (0.404, 0.619)
CLOUD_USE = (0.595, 0.619)


class FakeInput:
    """Records clicks instead of making them."""
    def __init__(self):
        self.clicks = []

    def click(self, x, y):
        self.clicks.append((x, y))


def _menus(words=()):
    m = M.Menus.__new__(M.Menus)      # no screen: offline
    m.s = None
    m.inp = FakeInput()
    m.words = list(words)
    m.read = lambda scale=0.5: m.words  # handle_save_choice reads afresh
    return m


def _still_words():
    if not hasattr(_still_words, "cache"):
        _still_words.cache = Vision(None).read((0, 0, 1, 1), img=cv2.imread(str(STILL)))
    return _still_words.cache


def _dialog_words(local_x=0.404, cloud_x=0.594, uses=(0.404, 0.594), local_label="THIS DeVICe"):
    """OCR words of the dialog as read on the still, with knobs to break it."""
    words = [Word("oNTHe CLOUD", cloud_x, 0.398, 0.08, 0.03, 0.85)]
    if local_label:
        words.append(Word(local_label, local_x, 0.398, 0.08, 0.03, 0.83))
    words += [Word("use", x, 0.619, 0.03, 0.03, 0.92) for x in uses]
    return words


def _near(p, q, tol=0.02):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def test_the_still_reads_as_the_save_dialog():
    m = _menus(_still_words())
    assert m.identify(read=False) == "save_choice"


def test_the_still_gives_this_devices_use_button():
    button, why = _menus(_still_words()).this_device_button()
    assert button is not None, why
    assert _near((button.x, button.y), THIS_DEVICE_USE), button


def test_the_dialog_is_no_reward_cards():
    """The bug: on the darker frame the bot saw, the blue cards' centres were
    the two USE buttons. With the dialog's words read, no cards."""
    dark = (cv2.imread(str(STILL)).astype(np.float32) * 0.5).astype(np.uint8)
    blind = _menus()                            # how it went: no words consulted
    cards = blind.reward_cards(dark)
    assert len(cards) == 2 and _near(cards[0], THIS_DEVICE_USE, 0.03) and _near(cards[1], CLOUD_USE, 0.03), cards
    assert _menus(_still_words()).reward_cards(dark) == []
    # a USE button alone (title and labels misread) is enough to refuse
    assert _menus([Word("use", 0.4, 0.62, 0.03, 0.03, 0.9)]).reward_cards(dark) == []
    # and so is the match HUD's round counter: crates never open over a match
    assert _menus([Word("ROUnD", 0.783, 0.057, 0.05, 0.03, 0.68)]).reward_cards(dark) == []


def test_handle_save_choice_clicks_only_this_device():
    m = _menus(_still_words())
    assert m.handle_save_choice() is True
    assert len(m.inp.clicks) == 1 and _near(m.inp.clicks[0], THIS_DEVICE_USE), m.inp.clicks


def test_layout_swapped_still_picks_this_device():
    """Nothing assumes This Device is on the left."""
    button, why = _menus(_dialog_words(local_x=0.594, cloud_x=0.404)).this_device_button()
    assert button is not None and abs(button.x - 0.594) < 0.01, (button, why)


def test_unsure_means_no_click():
    cases = {
        "no This Device label": _dialog_words(local_label=None),
        "only the cloud's USE read": _dialog_words(uses=(0.594,)),
        "no USE read": _dialog_words(uses=()),
        "two This Device labels": _dialog_words() + [Word("This Device", 0.6, 0.2, 0.08, 0.03, 0.8)],
        "cards on top of each other": _dialog_words(local_x=0.404, cloud_x=0.42, uses=(0.41,)),
    }
    for name, words in cases.items():
        m = _menus(words)
        button, why = m.this_device_button()
        assert button is None, (name, button)
        assert m.handle_save_choice() is False, name
        assert m.inp.clicks == [], (name, m.inp.clicks)


def test_collection_loop_turns_no_card_under_the_dialog():
    """handle_collection_event, which turned both "cards" in the game, stops
    at the dialog: with no certain This Device button it clicks nothing."""
    m = _menus(_dialog_words(uses=(0.594,)))
    m.identify = lambda read=True: "save_choice"
    assert m.handle_collection_event() is False
    assert m.inp.clicks == []


def test_plain_reward_cards_still_work():
    """A real crate's face-down cards carry no text: still found."""
    img = np.full((1200, 1920, 3), (24, 20, 20), np.uint8)
    for x in (790, 1125):
        img[520:680, x - 80:x + 80] = (160, 90, 10)
    assert len(_menus().reward_cards(img)) == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
