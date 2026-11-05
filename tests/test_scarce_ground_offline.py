"""Towers that need no track in reach leave the scarce ground near it free.

Cargo Impoppable (2026-11-05, loss case 20261105_075327): only a walkway and
a pier corner of Cargo's land reach the track for a short-range tower. By
round 56 a sniper - global range, it pops bloons from anywhere - had taken
the pier corner, the last cell a dart could use, and every land kind after
it logged "no legal spot reaches the track". Now a global-range tower is
kept off that ground while it is scarce (fewer short-range towers still fit
on it than the plan and its answers need), and a threat answer is not
bought as a land kind with no legal cell in reach of the track, so a kind
that fits (a sub on water) is chosen instead.

Offline: the executor with a fake game, every cell legal, and a reach grid
that puts the track's reach in a band of columns.
Run: python tests/test_scarce_ground_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import placement as PL           # noqa: E402
from btd6bot import strategy as S             # noqa: E402

H, W = F.FakeModel.H, F.FakeModel.W
NINJAS = [{"do": "place", "id": f"n{i}", "kind": "ninja", "role": "dps"} for i in (1, 2, 3)]
SNIPER = {"do": "place", "id": "s1", "kind": "sniper", "role": "dps"}


class RampModel(F.FakeModel):
    """Cover rises to the right (the right columns rank first) and blocked
    cells score nothing, as the real map model's score_spots does."""

    def score_spots(self, rc, seg, occupied, near=None, near_radius=None, placement="land",
                    extra_block=None, covered=None, valid=None):
        cover = np.tile(np.linspace(1.0, 2.0, self.W, dtype=np.float32), (self.H, 1))
        if extra_block is not None:
            cover[extra_block] = 0
        return cover

    def spot_weight(self, seg, covered):
        return np.ones((self.H, self.W), np.float32)


def band(first, last, value=100.0):
    """A reach grid: the track is in reach only in columns first..last."""
    reach = np.zeros((H, W), np.float32)
    reach[:, first:last + 1] = value
    return reach


def executor(ninja_reach, steps=None):
    """An executor whose plan still has three ninja place steps (the
    short-range towers the ground must hold) and then the sniper."""
    plan = {"id": "t", "name": "t", "hero": None, "plan": [dict(s) for s in (steps or NINJAS + [SNIPER])]}
    ex = S.Executor(F.FakeGame(), RampModel(), plan, "medium", F.full_account())
    # the executor opens every plan with a dart, the shortest range here
    ex._reach_cache = {"ninja": ninja_reach, "dart": ninja_reach}
    return ex


def _with_fakes(fn):
    """Run fn with every cell legal, no sight blockers and one world unit
    per cell (a 6-unit footprint then takes ~125 cells packed tight)."""
    saved = PL.valid_spots, PL.needs_sight, PL.units_per_cell
    PL.valid_spots = lambda *a, **k: np.ones((H, W), bool)
    PL.needs_sight = lambda *a: False
    PL.units_per_cell = lambda model: 1.0
    try:
        return fn()
    finally:
        PL.valid_spots, PL.needs_sight, PL.units_per_cell = saved


def test_a_sniper_leaves_scarce_ground_to_the_ninjas():
    # ten columns reach the track: room for ~5 ninjas, the plan and its
    # answers need 3 + SCARCE_ROOM_SPARE
    spots = _with_fakes(lambda: executor(band(90, 99)).pick_spots("sniper", SNIPER, n=3))
    assert spots, "the sniper still gets a spot"
    assert all(cx < 90 for cx, _, _ in spots), spots


def test_ground_that_is_not_scarce_is_left_alone():
    # half the board reaches the track: ~24 ninjas fit, nothing is kept back
    spots = _with_fakes(lambda: executor(band(50, 99)).pick_spots("sniper", SNIPER, n=3))
    assert spots and all(cx >= 90 for cx, _, _ in spots), spots


def test_the_ace_is_not_moved():
    # the Monkey Ace flies round its own spot: it stays near the track
    step = dict(SNIPER, id="a1", kind="ace")
    spots = _with_fakes(lambda: executor(band(90, 99)).pick_spots("ace", step, n=3))
    assert spots and all(cx >= 90 for cx, _, _ in spots), spots


def test_short_range_towers_still_get_the_scarce_ground():
    spots = _with_fakes(lambda: executor(band(90, 99)).pick_spots("ninja", NINJAS[0], n=3))
    assert spots and all(cx >= 90 for cx, _, _ in spots), spots


def test_the_any_legal_cell_fallback_skips_scarce_ground_too():
    # that fallback walks the cells top row first, left to right: the band
    # sits at the left so it would come first
    spots = _with_fakes(lambda: executor(band(0, 9))._any_legal_spot("sniper"))
    assert spots and all(cx > 9 for cx, _, _ in spots), spots


def test_scarce_ground_is_given_when_nothing_else_is_legal():
    def run():
        PL.valid_spots = lambda *a, **k: band(90, 99) > 0     # only the band is legal
        return executor(band(90, 99)).pick_spots("sniper", SNIPER, n=3)
    spots = _with_fakes(run)
    assert spots and all(cx >= 90 for cx, _, _ in spots), spots


def test_an_answer_is_not_a_land_kind_that_reaches_nothing():
    def run():
        ex = executor(np.zeros((H, W), np.float32))
        ex._reach_cache["sub"] = band(0, 99)
        ex._map_has_water = lambda: True
        return ex._answer_kind_ok("ninja"), ex._answer_kind_ok("sub")
    ninja_ok, sub_ok = _with_fakes(run)
    assert not ninja_ok, "no legal cell reaches the track for a ninja"
    assert sub_ok, "a sub still reaches it from the water"


def test_an_answer_kind_that_reaches_the_track_is_still_bought():
    ok = _with_fakes(lambda: executor(band(50, 99))._answer_kind_ok("ninja"))
    assert ok


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
