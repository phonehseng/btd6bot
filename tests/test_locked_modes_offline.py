"""Modes the game shows locked although our medals unlock them (no game needed).

Lotus Island, 2026-11-03: the map card and the medal sweep both show the
Medium medal (won as a co-op guest), yet Military Only and Reverse were
padlocked on mode select. The planner trusted the medal chain, picked them as
its best safe-mode games, failed to start them, benched them for 2 h and
picked them again - while the bot idled for want of anything else to play.

Covers:
  * note_mode_locked marks the mode, its siblings behind the same medal and
    every mode further down the chain; mode_unlocked then says no;
  * the lock survives a save/load and expires after LOCK_RECHECK_DAYS;
  * a game that starts clears the lock for its mode.
Run: python tests/test_locked_modes_offline.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.account import AccountState  # noqa: E402


def lotus_account():
    a = AccountState()
    a.category_progress = {"beginner": [0, 0]}      # Beginner maps are open
    a.medals["Lotus Island"] = {"easy": True, "medium": True, "hard": True}
    return a


def test_lock_covers_siblings_and_chain():
    a = lotus_account()
    assert a.mode_unlocked("Lotus Island", "military_only")    # the medal chain says yes
    noted = a.note_mode_locked("Lotus Island", "military_only")
    # Reverse needs the same Medium medal, Apopalypse needs Military Only
    assert noted == ["apopalypse", "military_only", "reverse"], noted
    for mode in noted:
        assert not a.mode_unlocked("Lotus Island", mode), mode
    # the Hard chain is untouched
    assert a.mode_unlocked("Lotus Island", "magic_only")


def test_deep_chain():
    a = lotus_account()
    noted = a.note_mode_locked("Lotus Island", "magic_only", now=1000.0)
    # Magic Only and ABR both need Hard; Double HP -> Half Cash and
    # Impoppable -> CHIMPS hang below them
    assert noted == ["abr", "chimps", "double_hp", "half_cash", "impoppable", "magic_only"], noted


def test_persist_expire_and_clear():
    a = lotus_account()
    a.note_mode_locked("Lotus Island", "reverse")
    assert not a.mode_unlocked("Lotus Island", "reverse")
    with tempfile.TemporaryDirectory() as d:
        b = AccountState.load(a.save(Path(d) / "acct.json"))
    assert not b.mode_unlocked("Lotus Island", "reverse")
    later = b.locked_modes["Lotus Island"]["reverse"] + b.LOCK_RECHECK_DAYS * 86400 + 1
    assert not b.seen_locked("Lotus Island", "reverse", now=later)    # offered again
    b.note_mode_started("Lotus Island", "reverse")
    assert "reverse" not in b.locked_modes.get("Lotus Island", {})
    assert b.seen_locked("Lotus Island", "military_only")             # siblings still locked


if __name__ == "__main__":
    test_lock_covers_siblings_and_chain()
    test_deep_chain()
    test_persist_expire_and_clear()
    print("locked modes: OK")
