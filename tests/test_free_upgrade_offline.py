"""An upgrade button that says "Free" is a tier to buy, not a closed path
(no game needed).

Haunted CHIMPS (2026-11-13 00:39, lost at round 96): the build's glue was
placed beside the village just after its Primary Mentoring (4-2-0), which
gives primary monkeys their tier-1 upgrades for nothing. The glue's panel
(logs/closed_misread.png of that game) showed "Free" on Glue Soak and on
Stickier Glue and "$700" on Glue Splatter. The OCR reads the word as "FRee";
price_row took it for no price, three such reads closed the top path for the
game, and plan step "g1 to 5-2-0" - The Bloon Solver, about $30,000 of the
build's blimp damage - was set aside and never bought.

Run: python tests/test_free_upgrade_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import towers as T  # noqa: E402
from btd6bot.game import Placed, price_row  # noqa: E402
from test_purchase_proof_offline import path_clicks, scripted, upgrade_game  # noqa: E402

FREE = ("free", 0)
BLANK = (None, None)


def glue_price(path, tier):
    """The price table's cost of a glue tier on Hard (CHIMPS prices)."""
    return T.upgrade_cost("glue", path, tier, "hard")


def haunted_panel():
    """The glue's panel as the game showed it at 0-1-0 beside the village."""
    return [FREE, ("cash", 700), FREE]


def test_the_word_free_is_read_as_a_free_tier():
    for text in ("FRee", "Free", "FREE", " free "):
        assert price_row(text) == FREE, text
    # nothing else becomes free: a $0 read is still no price (a PATH CLOSED
    # box read as $0, High Finance 2026-11-05), and words stay words
    for text in ("$0", "0", "PATH CLOSED", "", "owned", "Freeze"):
        assert price_row(text) == BLANK, text
    assert price_row("$700") == ("cash", 700)
    print("ok 'FRee' reads as a free tier, $0 and words do not")


def test_free_tier_is_bought_and_the_path_stays_open():
    g = upgrade_game([], cash=634)
    after = [("cash", glue_price(1, 2)), ("cash", 700), FREE]   # Corrosive Glue is next
    g.path_costs = scripted([haunted_panel(), after])
    p = Placed("g1", "glue", 0.27, 0.658, tiers=[0, 1, 0])
    assert g.upgrade(p, 1) is True, g.fail_reason
    assert p.tiers == [1, 1, 0] and ("g1", 1) not in g.closed
    assert len(path_clicks(g, p)) == 1 and not g.inp.keys, "one click, no hotkey"
    assert p.spent == 0 and g.last_price == 0, "a free tier costs nothing"
    print("ok Glue Soak is bought from its 'Free' button; the path to the Bloon Solver stays open")


def test_free_panel_is_the_towers_own_and_corrects_no_tier():
    g = upgrade_game(haunted_panel())
    p = Placed("g1", "glue", 0.27, 0.658, tiers=[0, 1, 0])
    assert g._panel_owner(p, haunted_panel()) is None
    assert g._resync_tiers(p, haunted_panel()) is False and p.tiers == [0, 1, 0]
    assert g._path_closed(p, 1, haunted_panel()) is False and not g.closed
    print("ok a 'Free' button names no tier by price and closes no path")


def test_button_still_free_presses_no_hotkey_on_a_guess():
    """After the click the button may still say "Free": the click missed, or
    the next tier is free too. With the pips unread nothing proves "same", so
    no hotkey is pressed (it could take a second tier unseen) and the path is
    tried again later, not closed."""
    g = upgrade_game(haunted_panel())
    p = Placed("g1", "glue", 0.27, 0.658, tiers=[0, 1, 0])
    assert g.upgrade(p, 1) is False and g.fail_reason == "noeffect"
    assert not g.inp.keys and p.tiers == [0, 1, 0] and ("g1", 1) not in g.closed
    print("ok a button that stays 'Free' with unread pips: no hotkey, no tier counted")


def test_button_still_free_with_unmoved_pips_is_a_missed_click():
    g = upgrade_game(haunted_panel())
    g.path_pips = lambda p, path, f=None: 0        # no pip lit before or after
    p = Placed("g1", "glue", 0.27, 0.658, tiers=[0, 1, 0])
    g.upgrade(p, 1)
    assert g.inp.keys == [T.UPGRADE_HOTKEYS[0]], "the click did not register: the hotkey tries once"
    assert p.tiers == [0, 1, 0]
    print("ok pips that did not move prove a missed click on a 'Free' button")


if __name__ == "__main__":
    test_the_word_free_is_read_as_a_free_tier()
    test_free_tier_is_bought_and_the_path_stays_open()
    test_free_panel_is_the_towers_own_and_corrects_no_tier()
    test_button_still_free_presses_no_hotkey_on_a_guess()
    test_button_still_free_with_unmoved_pips_is_a_missed_click()
    print("ALL OK")
