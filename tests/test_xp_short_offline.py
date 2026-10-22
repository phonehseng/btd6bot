"""Tower-XP shortfalls remembered per account (no game needed).

Before: "boomerang path 1 tier 5 needs 37500 XP, have 36108" lived in a
module-level dict, so every restart opened the Monkeys menu to read it again
(6-25 s), and the menu was opened before every game even when every needed
upgrade was already unlocked.
Run: python tests/test_xp_short_offline.py"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import xpspend as X  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402

logging.getLogger("xpspend").setLevel(logging.ERROR)


def test_shortfall_covers_its_tier_and_the_ones_above():
    acc = AccountState()
    X.note_short(acc, "boomerang", 1, 5, 37500, 36108)
    assert X.known_short(acc, "boomerang", 1, 5)
    assert not X.known_short(acc, "boomerang", 1, 4), "a lower tier was not shown as too expensive"
    assert not X.known_short(acc, "boomerang", 2, 5), "another path is unknown"
    X.note_short(acc, "bomb", 2, 4, 3000, 2900)
    assert X.known_short(acc, "bomb", 2, 5), "tier 5 needs tier 4 first"


def test_shortfall_expires_and_is_forgotten_after_the_tower_plays():
    acc = AccountState()
    X.note_short(acc, "boomerang", 1, 5, 37500, 36108)
    assert not X.known_short(acc, "boomerang", 1, 5, now=time.time() + X.SHORT_TTL + 1)
    X.forget_short(acc, {"boomerang", "dart"})
    assert not X.known_short(acc, "boomerang", 1, 5)


def test_shortfall_survives_a_restart():
    acc = AccountState()
    X.note_short(acc, "boomerang", 1, 5, 37500, 36108)
    again = AccountState.from_dict(acc.to_dict())
    assert X.known_short(again, "boomerang", 1, 5)


def test_pending_upgrades_skip_owned_and_unaffordable():
    acc = AccountState()
    acc.unlocked_upgrades = {"boomerang": [4, 0, 2], "bomb": [0, 2, 0]}
    X.note_short(acc, "boomerang", 1, 5, 37500, 36108)
    wanted = [("boomerang", 1, 3), ("boomerang", 1, 4), ("boomerang", 1, 5), ("boomerang", 3, 2),
              ("bomb", 2, 1), ("bomb", 2, 3)]
    assert X.pending_upgrades(acc, wanted) == {"bomb": [(2, 3)]}
    X.note_short(acc, "bomb", 2, 3, 1200, 900)
    assert X.pending_upgrades(acc, wanted) == {}


class NoMenu:
    """Fails the test on any attempt to look at or click the game."""
    def identify(self, *a, **k):
        raise AssertionError("the Monkeys menu should not be opened")

    click = read = identify


def test_nothing_to_check_means_no_trip_to_the_menu():
    acc = AccountState()
    acc.unlocked_upgrades = {"boomerang": [4, 0, 2]}
    X.note_short(acc, "boomerang", 1, 5, 37500, 36108)
    spender = X.XpSpender(None, NoMenu(), NoMenu(), acc)
    assert spender.unlock([("boomerang", 1, 4), ("boomerang", 1, 5), ("boomerang", 3, 2)]) == []


def test_strategy_towers():
    strat = {"plan": [{"do": "place", "id": "b1", "kind": "boomerang"}, {"do": "upgrade", "id": "b1", "to": "2-0-0"}],
             "fill": [{"do": "place", "kind": "bomb"}],
             "answers": {"lead": [{"do": "place", "kind": "glue"}]}}
    assert X.strategy_towers(strat) == {"boomerang", "bomb", "glue"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
