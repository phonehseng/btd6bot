"""Geared's gear turns follow the screen, not the bot's lagging round.

Audit of 2026-11-12 (dynamic maps, item 10): the gears turn after every
round, as the HUD round steps on, but the bot reads the new round only
later (a side panel over the counter keeps it one behind, as on Covered
Garden). A tower bought in that gap stands on the turned gear already, and
CarriedTowers turned its remembered spot once more when the round was read;
a round going back after a misread never turned the gears back. The match
now turns the gears when it sees the round end (the Play button is back),
and CarriedTowers counts turns from the round its spots are turned to.
Offline: the real Geared geometry, fake towers.
Run: python tests/test_gear_round_offline.py"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import mapgeom, match as M                 # noqa: E402
from btd6bot.carried import CarriedTowers               # noqa: E402
from btd6bot.game import Placed                         # noqa: E402
from test_carried_offline import PLAYFIELD, _rotor, _spot   # noqa: E402


def _angle(c, rotor, p):
    x, z = c._world(p.x, p.y, rotor.height)
    return math.degrees(math.atan2(x - rotor.pivot[0], z - rotor.pivot[1])) % 360


def _carrier():
    if mapgeom.load("Geared") is None:
        return None
    return CarriedTowers.for_map("Geared", PLAYFIELD)


def test_tower_bought_after_the_round_ended_is_not_turned_again():
    c = _carrier()
    if c is None:
        return
    big = _rotor(c, 45.0)
    a = Placed("a", "ace", *_spot(c, big, 0.0, 60.0))
    c.round_advanced(4, 5, {"a": a})                  # 45 degrees
    c.round_ended(5, {"a": a})                         # round 5 over: the gears turned for 6
    assert abs(_angle(c, big, a) - 90.0) < 0.5
    b = Placed("b", "ace", *_spot(c, big, 0.0, 60.0))  # bought while the bot still reads 5
    towers = {"a": a, "b": b}
    assert c.round_advanced(5, 6, towers) == []        # the bot reads 6: nothing turns again
    assert abs(_angle(c, big, b)) < 0.5 and abs(_angle(c, big, a) - 90.0) < 0.5
    c.round_advanced(6, 7, towers)                     # the next round end turns both
    assert abs(_angle(c, big, b) - 45.0) < 0.5 and abs(_angle(c, big, a) - 135.0) < 0.5


def test_a_round_reset_backwards_turns_the_gears_back():
    c = _carrier()
    if c is None:
        return
    big = _rotor(c, 45.0)
    a = Placed("a", "ace", *_spot(c, big, 0.0, 60.0))
    c.round_advanced(10, 12, {"a": a})                 # a misread jumped two rounds
    assert abs(_angle(c, big, a) - 90.0) < 0.5
    c.round_advanced(12, 11, {"a": a})                 # tracking reset: one round back
    assert abs(_angle(c, big, a) - 45.0) < 0.5


def test_match_turns_the_gears_when_the_play_button_comes_back():
    c = _carrier()
    if c is None:
        return
    big = _rotor(c, 45.0)
    a = Placed("a", "ace", *_spot(c, big, 0.0, 60.0))
    m = M.Match.__new__(M.Match)
    m._carried, m.g, m._played_round = c, SimpleNamespace(towers={"a": a}), None
    c.round_advanced(2, 3, m.g.towers)                 # 45 degrees, round 3 read
    m._in_round = False
    m._follow_round_end(3)                             # before Play: nothing ended
    assert abs(_angle(c, big, a) - 45.0) < 0.5
    m._in_round = True
    m._follow_round_end(3)                             # round 3 running
    m._in_round = False
    m._follow_round_end(3)                             # over, the bot still reads 3
    assert abs(_angle(c, big, a) - 90.0) < 0.5 and c.turned_to == 4
    m._follow_round_end(3)                             # once only
    assert abs(_angle(c, big, a) - 90.0) < 0.5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
