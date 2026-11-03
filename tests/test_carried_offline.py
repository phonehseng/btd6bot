"""Towers on Geared's gears are followed round (carried.CarriedTowers).

Geared Medium (2026-11-03) lost ac1, ac2, ac3 and sniper3: the gears turned
after a round, the bot clicked the spots where it had placed them, found
empty ground, and "forgot" them. The remembered spots must turn with the
gear: 45 degrees for the big one, 108 for the small one, after every round.
Offline: the real Geared geometry, fake towers.
Run: python tests/test_carried_offline.py"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import mapgeom                    # noqa: E402
from btd6bot.carried import CarriedTowers      # noqa: E402
from btd6bot.game import Placed                # noqa: E402
from btd6bot.layout import LAYOUTS             # noqa: E402

PLAYFIELD = LAYOUTS["16:10"]["playfield"]


def _carrier():
    c = CarriedTowers.for_map("Geared", PLAYFIELD)
    assert c is not None, "Geared has rotating ground"
    return c


def _rotor(c, step):
    return next(r for r in c.rotors if abs(r.step - step) < 1e-6)


def _spot(c, rotor, dx, dz):
    """Screen spot of a tower standing on `rotor` at (dx, dz) from its pivot."""
    x, z = rotor.pivot[0] + dx, rotor.pivot[1] + dz
    fx, fy = c.proj.to_frac([[x, z, rotor.height]])[0]
    return float(fx), float(fy)


def test_geared_has_both_gears():
    c = _carrier()
    assert sorted(round(r.step) for r in c.rotors) == [45, 108]
    assert all(r.first == 2 and r.every == 1 for r in c.rotors)   # after every round from round 1


def test_tower_on_big_gear_turns_45_degrees_per_round():
    c = _carrier()
    big = _rotor(c, 45.0)
    # 60 units out on the side away from the small gear (which sits at -z)
    p = Placed("ac1", "ace", *_spot(c, big, 0.0, 60.0))
    off = Placed("s1", "sniper", 0.02, 0.10)          # far corner: not on a gear
    towers = {"ac1": p, "s1": off}
    moved = c.round_advanced(1, 2, towers)
    assert moved == ["ac1"]
    assert (off.x, off.y) == (0.02, 0.10)
    x, z = c._world(p.x, p.y, big.height)
    ang = math.degrees(math.atan2(x - big.pivot[0], z - big.pivot[1]))
    assert abs(ang - 45.0) < 0.5, ang                 # Unity yaw: +45 turns +z toward +x
    assert abs(math.hypot(x - big.pivot[0], z - big.pivot[1]) - 60.0) < 0.5
    assert big.contains(x, z)                         # still on the (turned) gear


def test_small_gear_wins_where_it_lies_on_the_big_one():
    c = _carrier()
    small = _rotor(c, 108.0)
    p = Placed("sn3", "sniper", *_spot(c, small, 10.0, 0.0))
    c.round_advanced(3, 4, {"sn3": p})
    x, z = c._world(p.x, p.y, small.height)
    ang = math.degrees(math.atan2(x - small.pivot[0], z - small.pivot[1]))
    assert abs(((ang - (90.0 + 108.0)) + 180) % 360 - 180) < 0.5, ang


def test_several_rounds_at_once_and_new_towers():
    c = _carrier()
    big = _rotor(c, 45.0)
    a = Placed("a", "ace", *_spot(c, big, 0.0, 60.0))
    c.round_advanced(4, 6, {"a": a})                 # two rounds: 90 degrees
    x, z = c._world(a.x, a.y, big.height)
    assert abs(math.degrees(math.atan2(x - big.pivot[0], z - big.pivot[1])) - 90.0) < 0.5
    # a tower placed now stands on the turned gear: it is matched there and
    # turns from where it was placed
    b = Placed("b", "ace", *_spot(c, big, 0.0, 60.0))
    c.round_advanced(6, 7, {"a": a, "b": b})
    x, z = c._world(b.x, b.y, big.height)
    assert abs(math.degrees(math.atan2(x - big.pivot[0], z - big.pivot[1])) - 45.0) < 0.5


def test_maps_without_rotating_ground():
    assert CarriedTowers.for_map("Monkey Meadow", PLAYFIELD) is None
    assert CarriedTowers.for_map(None, PLAYFIELD) is None
    # Sanctuary's platforms move along curves: not followed (yet)
    assert CarriedTowers.for_map("Sanctuary", PLAYFIELD) is None
    assert mapgeom.load("Geared") is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK")
