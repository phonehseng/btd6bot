"""Offline checks for the guards that keep clicks off end screens and menus.

Cargo Double HP MOABs (2026-11-03): the game was lost at round 75 while the
bot was buying; it clicked map spots on the DEFEAT screen (whose Continue
button spends Monkey Money) for 35 s, a click hit Home, and stray clicks
then left it on the Legends page for 18 minutes.
Run: python tests/test_screen_guard_offline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import game as G  # noqa: E402
from btd6bot import menus as M  # noqa: E402
from btd6bot.vision import Word  # noqa: E402


class Clicks:
    """Records clicks instead of making them."""

    def __init__(self):
        self.done = []

    def click(self, fx, fy, hold=0.07):
        self.done.append((fx, fy))


def _game(hud_seen):
    """A Game whose Play-button check answers from the list `hud_seen`."""
    g = G.Game.__new__(G.Game)            # no screen or layout needed here
    g.inp = Clicks()
    g.screen_lost = False
    g.SCREEN_RECHECK_S = 0.0
    looks = iter(hud_seen)
    g.in_game = lambda f=None: next(looks)
    return g


def test_no_placement_without_the_hud():
    g = _game([False, False])
    assert g.place("s1", "sniper", 0.3, 0.6) is None
    assert g.fail_reason == "screen" and g.screen_lost
    assert g.inp.done == []                # nothing was clicked


def test_lost_screen_blocks_until_cleared():
    g = _game([False, False])
    assert not g.screen_ok()
    # no further looks are taken (the iterator is empty): the flag answers
    assert not g.select(G.Placed("s1", "sniper", 0.3, 0.6))
    assert g.inp.done == []


def test_one_bad_look_is_not_enough():
    g = _game([False, True])
    assert g.screen_ok() and not g.screen_lost


def _words(*texts):
    return [Word(t, 0.5, 0.1 + 0.05 * i, 0.1, 0.03, 0.9) for i, t in enumerate(texts)]


def _identify(*texts):
    m = M.Menus.__new__(M.Menus)
    m.words = _words(*texts)
    m.in_game = lambda: False
    m.reward_cards = lambda frame=None: []
    return m.identify(read=False)


def test_legends_page_is_named():
    # its text says "defeat the final Boss" and a preview shows "Home"
    assert _identify("LEGENDS", "Rogue Legends", "defeat the final Boss", "Home", "TRY",
                     "GET NOW", "DLC") == "legends"


def test_defeat_card_still_reads_as_defeat():
    assert _identify("DEFEAT", "Round 75", "Bloons Leaked", "Home", "Restart", "Review Map") == "defeat"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
