"""Offline check: a tower no bloon has reached yet is not a dead tower.

Sunset Gulch Impoppable (2026-11-10 15:13, lost at round 40, case
20261110_151838_SunsetGulch_impoppable): the Fast Track start at round 29
bought n1 to 4-0-2 Bloonjitsu at the entrance before the first round was
played, and with Obyn it popped every bloon of rounds 29-38. n2, the 2-0-3
Flash Bomb ninja at the far end of the bridge, read 0 pops twice - a true
zero, its panel is in the recording - and was called dead at round 39. Its
Sticky Bomb step (n2 -> 2-0-4, $6,000 with $5,723 in hand) went to a fresh
ninja a few cells on, $4,832 rebuilt 2-0-3 there, and round 40's MOAB took the
one life.

Executor._shielded keeps such a tower: for SHIELD_ROUNDS rounds after its
placement a pop count of 0 proves a bad spot only when a bloon is known to
have come that far - lives were lost since, or a tower standing as far along
the route (or further) has pops.

The route comes from the game's own geometry for Sunset Gulch; the towers
stand where they stood in that game. Fakes in the style of
tests/test_one_life_executor_offline.py.
Run: python tests/test_shielded_tower_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import mapgeom as G                                    # noqa: E402
from btd6bot import strategy as S                                   # noqa: E402
from btd6bot.layout import LAYOUTS                                  # noqa: E402
from btd6bot.maplearn import MapModel                               # noqa: E402
from test_one_life_executor_offline import bare_executor, tower     # noqa: E402

MAP = "Sunset Gulch"
# where the towers stood (game.log of the case, screen fractions)
N1_SPOT = (0.163, 0.717)        # the entrance ninja, 4-0-2
N2_SPOT = (0.660, 0.453)        # the Flash Bomb ninja at the far end of the bridge
BEND_SPOT = (0.740, 0.800)      # the last bend, where reinforce put its ninjas
START_ROUND, READ_ROUND = 29, 39


def board(n1_pops=30000, bend_pops=None):
    """The round-39 board on the real route: n1 pops, n2 read 0 twice.
    bend_pops: pops of a ninja standing further along than n2 (None: none)."""
    n1 = tower("n1", "ninja", [4, 0, 2], spent=7000, placed_round=START_ROUND, pops=n1_pops)
    n2 = tower("n2", "ninja", [2, 0, 3], spent=4920, placed_round=START_ROUND,
               pops=0, pops_round=READ_ROUND, zero_reads=S.Executor.ZERO_POP_READS)
    n1.x, n1.y = N1_SPOT
    n2.x, n2.y = N2_SPOT
    towers = [n1, n2]
    if bend_pops is not None:
        bend = tower("ninja1", "ninja", [2, 0, 0], spent=1320, placed_round=30, pops=bend_pops)
        bend.x, bend.y = BEND_SPOT
        towers.append(bend)
    ex = bare_executor("impoppable", towers)
    ex.m = G.apply(MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    ex._sole_answer = lambda p: None
    return ex, n2


def test_the_towers_stand_in_route_order():
    """The check below rests on this: n1 before n2 before the bend."""
    ex, n2 = board(bend_pops=0)
    progress = ex.m.progress_full()
    n1, bend = ex.g.towers["n1"], ex.g.towers["ninja1"]
    assert ex._route_position(progress, n1) < ex._route_position(progress, n2) \
        < ex._route_position(progress, bend)


def test_a_tower_behind_a_front_that_holds_is_not_dead():
    ex, n2 = board()
    assert ex._shielded(n2) and not ex._dead(n2)
    # ... and a zero further along is no evidence either (the reinforce ninjas)
    ex, n2 = board(bend_pops=0)
    assert not ex._dead(n2)


def test_pops_further_along_prove_bloons_came_past():
    ex, n2 = board(bend_pops=250)
    assert not ex._shielded(n2) and ex._dead(n2)


def test_lost_lives_prove_bloons_came_past():
    ex, n2 = board()
    ex.drop_rounds = [START_ROUND - 3]          # before n2 stood: says nothing about it
    assert not ex._dead(n2)
    ex.drop_rounds = [READ_ROUND - 2]
    assert ex._dead(n2)


def test_the_benefit_of_the_doubt_ends():
    """Ancient Portal Impoppable (2026-11-05): a ninja on a lane bloons never
    use read 0 from round 6 on - after SHIELD_ROUNDS the old rule judges it."""
    ex, n2 = board()
    n2.pops_round = n2.placed_round + S.Executor.SHIELD_ROUNDS - 1
    assert not ex._dead(n2)
    n2.pops_round = n2.placed_round + S.Executor.SHIELD_ROUNDS
    assert ex._dead(n2)


def test_without_a_route_the_old_rule_stands():
    ex, n2 = board()
    ex.m = type("NoRoute", (), {"frac_to_cell": staticmethod(lambda x, y: (10, 10))})()
    assert ex._dead(n2)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
