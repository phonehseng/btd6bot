"""Offline checks for the menu guards: real-money buttons are never
clickable, and a page that merely mentions "defeat" is not a defeat screen.
Run: python tests/test_menu_guards_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import menus as M  # noqa: E402
from btd6bot.vision import Word  # noqa: E402


def _words(*texts):
    return [Word(t, 0.5, 0.1 + 0.05 * i, 0.1, 0.03, 0.9) for i, t in enumerate(texts)]


def _screen(*texts):
    m = M.Menus.__new__(M.Menus)
    m.s = None                       # no screen: offline
    m.words = _words(*texts)
    m.in_game = lambda f=None: False
    return m.identify(read=False)


def test_real_money_is_forbidden():
    for text in ("GET NOW", "$9.99", "Get Now $9.99", "DLC", "4,99 EUR"):
        assert M.forbidden(text), text
    for text in ("$1,755", "$17,674", "650", "2,500", "Next", "COLLECT", "Home"):
        assert not M.forbidden(text), text


def test_overwrite_save_is_not_a_purchase():
    # Alpine Run CHIMPS, 2026-11-06 03:26: the box sits over the mode
    # rewards ("$40", "$300") and its OK was refused eighteen times
    box = _words("OVERWRITE SAVE?", "Playing a new game will replace your existing save",
                 "game. Are you sure you want to continue?", "CANCEL", "OK",
                 "HALF CASH", "REWARDS:", "$40", "CHIMPS", "$300")
    assert _screen(*[w.text for w in box]) == "overwrite"
    assert not M.page_forbidden(box)
    # real spending wording on the same page still forbids confirming
    assert M.page_forbidden(box + _words("Buy for 3,000 Monkey Money"))
    assert M.page_forbidden(_words("Are you sure?", "$1,500", "OK"))
    # End Of The Road Apopalypse, 2026-11-06 08:17: the Medium description
    # behind the box ("Monkeys cost normal") is not spending wording either
    medium = _words("On Medium Monkeys cost normal, the Bloons move normal and you have 15o lives.Beating",
                    "OVeRWRITeSAVe?", "Playing a new game will replace your existing save",
                    "game.Are you sure you want to continue?", "CAnceL", "OK", "REWARDS:", "$25")
    assert not M.page_forbidden(medium)
    assert M.page_forbidden(_words("This upgrade will cost 3,000 Monkey Money", "OK"))


def test_defeat_needs_its_buttons():
    # Legends: "work with a cast of Monkey characters to defeat the Bloons"
    assert _screen("Frontier Legends", "to defeat the Bloons", "TRY") != "defeat"
    assert _screen("DEFEAT", "Restart", "Home") == "defeat"


def _popup_click(words):
    """Where dismiss_popup clicks on a screen showing `words` (Word list)."""
    m = M.Menus.__new__(M.Menus)
    m.s = None
    m.words = words
    clicks = []
    m.inp = type("Inp", (), {"click": lambda self, x, y: clicks.append((round(x, 3), round(y, 3)))})()
    sleep, M.time.sleep = M.time.sleep, lambda s: None
    try:
        m.dismiss_popup()
    finally:
        M.time.sleep = sleep
    return clicks


def test_review_map_continue_is_clicked_on_its_icon():
    # Rake Easy, 2026-10-22: clicks on the caption left the game in Review Map for 20 minutes
    corner = [Word("conTinue", 0.925, 0.927, 0.08, 0.03, 0.9)]
    assert _popup_click(corner) == [(0.925, round(0.927 - M.REVIEW_MAP_ICON_ABOVE, 3))]
    middle = [Word("Continue", 0.5, 0.6, 0.08, 0.03, 0.9)]
    assert _popup_click(middle) == [(0.5, 0.6)]     # an ordinary popup: its caption


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
