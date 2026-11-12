"""A tower placed by role keeps a whole footprint off a later step's exact spot.

Sunset Gulch Impoppable (2026-11-12, loss case 20261112_050436): the build
pins its Super Monkey s1 at [0.163, 0.709]. The one-life opener's tack went
to cell (26, 77) and the free dart to (34, 80) - 4.1 and 4.5 cells from that
spot, just outside the 4 cells that were reserved round every exact spot,
well inside a Super Monkey's footprint. s1 then found "nothing legal within
15 cells of its spot", went by role to the exit, where it popped nothing in
53 rounds ($13,440), and round 88's blimps took the one life.

Executor._reserved_cells now gives each reserved spot the gap of the two
footprints side by side (the game's own radii), never under RESERVED_CELLS.
Offline: a bare Executor on the playfield of the live layout.

Run: python tests/test_reserved_footprint_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import GRID  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]
S1 = {"do": "place", "id": "s1", "kind": "super", "role": "support", "at": [0.163, 0.709]}
OPENER = {"do": "place", "id": "starter", "kind": "tack", "role": "dps"}


class Model:
    """The parts of a MapModel the reservation reads."""
    playfield = PF

    @staticmethod
    def frac_to_cell(x, y):
        return (int((x - PF[0]) / (PF[2] - PF[0]) * GRID[0]),
                int((y - PF[1]) / (PF[3] - PF[1]) * GRID[1]))


class Game:
    hero = "obyn"

    def __init__(self, towers=()):
        self.towers = {tid: object() for tid in towers}


def executor(plan, towers=()):
    ex = S.Executor.__new__(S.Executor)
    ex.m, ex.g, ex.plan, ex.strat = Model(), Game(towers), plan, {"fill": []}
    ex._pose_round = lambda: None       # no moving platforms: `at` stays where it is written
    return ex


def _kept_off(reserved, cell):
    return any((cell[0] - x) ** 2 + (cell[1] - y) ** 2 < gap ** 2 for x, y, gap in reserved)


def test_the_openers_cells_of_the_lost_game_are_now_reserved_for_the_super():
    ex = executor([S1])
    sx, sy = Model.frac_to_cell(*S1["at"])
    tack_cell, dart_cell = Model.frac_to_cell(0.142, 0.700), Model.frac_to_cell(0.184, 0.726)
    for cell in (tack_cell, dart_cell):
        # outside the old flat reservation: that is how the game was lost
        assert (cell[0] - sx) ** 2 + (cell[1] - sy) ** 2 >= S.RESERVED_CELLS ** 2, cell
    assert _kept_off(ex._reserved_cells(OPENER, "tack"), tack_cell)
    assert _kept_off(ex._reserved_cells(dict(OPENER, id="bonus_dart", kind="dart"), "dart"), dart_cell)


def test_the_gap_is_the_two_footprints_side_by_side():
    ex = executor([S1])
    (_, _, gap), = ex._reserved_cells(OPENER, "tack")
    upc = PL.units_per_cell(Model())
    assert abs(gap - (PL.footprint_radius("tack") + PL.footprint_radius("super")) / upc) < 1e-9
    assert gap > S.RESERVED_CELLS
    # a bigger tower placed by role keeps further off than a small one
    (_, _, wide), = ex._reserved_cells(dict(OPENER, kind="village"), "village")
    (_, _, narrow), = ex._reserved_cells(dict(OPENER, kind="dart"), "dart")
    assert wide > narrow >= S.RESERVED_CELLS


def test_a_placed_tower_and_the_step_itself_reserve_nothing():
    assert executor([S1], towers=["s1"])._reserved_cells(OPENER, "tack") == []
    assert executor([S1])._reserved_cells(S1, "super") == []


def test_without_a_kind_the_flat_distance_still_holds():
    (_, _, gap), = executor([S1])._reserved_cells(OPENER)
    assert gap >= S.RESERVED_CELLS


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
