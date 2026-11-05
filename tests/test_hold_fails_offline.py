"""A tower whose hotkey will not pick it up is given up for the game after
Executor.HOLD_BAN failed pick-ups - but only failures made while the hotkeys
are known to work count (Executor._note_hold_failure). Cargo Impoppable
(2026-11-05): the mode's intro box covered the match at the start, the ninja
failed six pick-ups behind it and was banned for the game, so the build's
core tower and the two buffers placed "near" it were never bought.
Offline: an Executor stub with only the fields the check reads.
Run: python tests/test_hold_fails_offline.py"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.strategy import Executor   # noqa: E402

logging.getLogger("strategy").setLevel(logging.CRITICAL)

STEP = {"do": "place", "id": "n1", "kind": "ninja", "role": "dps", "segment": [0.2, 1.0]}


def stub(placed=0):
    """An Executor with `placed` towers already bought this game."""
    ex = Executor.__new__(Executor)
    ex.dead_steps, ex.retry_at, ex.hold_fails = set(), {}, {}
    ex.blind_hold_fails, ex.purchased = 0, placed
    return ex


def test_failures_before_any_tower_stands_blame_no_kind():
    # the Cargo case: six pick-ups fail behind the intro box, nothing placed yet
    ex = stub()
    for _ in range(Executor.HOLD_BAN + 2):
        ex._note_hold_failure("ninja")
    assert not ex.place_held_back(STEP)
    assert ex.hold_fails == {} and ex.blind_hold_fails == Executor.HOLD_BAN + 2


def test_failures_while_other_towers_are_placed_ban_the_kind():
    # the hotkeys work (a tower stands), yet this kind never picks up
    ex = stub(placed=1)
    for n in range(1, Executor.HOLD_BAN + 1):
        ex._note_hold_failure("ninja")
        assert ex.place_held_back(STEP) == (n >= Executor.HOLD_BAN), n
    assert not ex.place_held_back(dict(STEP, kind="dart", id="d1"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
