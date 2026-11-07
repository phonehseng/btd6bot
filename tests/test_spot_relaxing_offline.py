"""Offline checks for Executor._spots_widening: a place step that finds no
spot is relaxed in stages (near radius, near, segment, role) before it can
be given up. Run: python tests/test_spot_relaxing_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.strategy import Executor  # noqa: E402


def _executor(finds, standing=("s1", "v1", "a1")):
    """An Executor whose spot finder only succeeds when finds(step) is True;
    `standing` are the tower ids already placed."""
    ex = Executor.__new__(Executor)
    ex.SPOTS_PER_HOLD = 4
    ex.seen = []
    ex.g = SimpleNamespace(towers={tid: object() for tid in standing})
    ex.pick_spots = lambda kind, step, n=1: (ex.seen.append(dict(step)) or
                                              ([(10, 10, 1.0)] if finds(step) else []))
    ex._any_legal_spot = lambda kind: []
    ex._buff_spots = lambda kind, step=None: [(5, 5, 2.0)] if ex.buff_ok else []
    ex.buff_ok = False
    return ex


def test_segment_is_dropped_when_nothing_covers_it():
    ex = _executor(lambda st: "segment" not in st)
    step = {"do": "place", "kind": "ninja", "role": "dps", "segment": [0.0, 0.5]}
    assert ex._spots_widening("ninja", step) == [(10, 10, 1.0)]
    assert "segment" in ex.seen[0] and "segment" not in ex.seen[-1]


def test_near_widens_before_it_is_dropped():
    ex = _executor(lambda st: st.get("near_radius", 0) > 10)
    step = {"do": "place", "kind": "village", "role": "support", "near": ["s1"], "near_radius": 8}
    assert ex._spots_widening("village", step)
    assert ex.seen[-1]["near_radius"] == 8 * Executor.NEAR_WIDENING[0]


def test_support_step_falls_back_to_a_damage_spot():
    ex = _executor(lambda st: st.get("role") == "dps" and "near" not in st)
    step = {"do": "place", "kind": "sniper", "role": "support", "near": ["v1"], "near_radius": 10}
    assert ex._spots_widening("sniper", step)
    assert ex.seen[-1]["role"] == "dps"


def test_gives_up_only_after_every_stage():
    ex = _executor(lambda st: False)
    step = {"do": "place", "kind": "ninja", "role": "support", "near": ["a1"], "segment": [0, 0.5]}
    assert ex._spots_widening("ninja", step) == []
    assert len(ex.seen) >= 5      # original + 2 radii + no near + no segment + as dps


def test_buffer_without_its_towers_goes_next_to_damage_towers():
    # Water Park: the village's snipers were never placed and it stood alone
    ex = _executor(lambda st: True, standing=())
    ex.buff_ok = True
    step = {"do": "place", "kind": "village", "role": "support", "near": ["s1"]}
    assert ex._spots_widening("village", step) == [(5, 5, 2.0)]
    assert ex.seen == []          # no spot chosen by role alone was even looked at


def test_buffer_never_relaxes_into_a_role_only_spot():
    ex = _executor(lambda st: "near" not in st)   # only a role-only search would succeed
    step = {"do": "place", "kind": "village", "role": "support", "near": ["s1"], "near_radius": 8}
    assert ex._spots_widening("village", step) == []
    assert all("near" in st for st in ex.seen)


def _buff_executor(damage_at):
    """An Executor on an open 40x40 grid with damage towers at the cells in
    `damage_at`, for the real _buff_spots (see _buff_spots_on_open_ground)."""
    import numpy as np
    ex = Executor.__new__(Executor)
    ex.SPOTS_PER_HOLD = 4
    ex.blocked = np.zeros((40, 40), bool)
    ex.failed_spots = set()
    ex.land_only = False
    ex.removed = []
    ex._pane_round = lambda: 10
    ex._range_cells = lambda kind: 5
    ex.m = SimpleNamespace(frac_to_cell=lambda fx, fy: (fx * 40, fy * 40))
    towers = {f"s{i}": SimpleNamespace(kind="sniper", x=cx / 40, y=cy / 40)
              for i, (cx, cy) in enumerate(damage_at)}
    ex.g = SimpleNamespace(towers=towers, hero=None)
    return ex


def _buff_spots_on_open_ground(ex, kind, step):
    """ex._buff_spots with placement.valid_spots saying every cell is legal
    (restored afterwards, so other tests see the real one)."""
    import numpy as np
    from btd6bot import placement as PL
    real = PL.valid_spots
    PL.valid_spots = lambda *a, **k: np.ones((40, 40), bool)
    try:
        return ex._buff_spots(kind, step)
    finally:
        PL.valid_spots = real


def test_buffer_keeps_its_researched_spot_when_it_buffs_something():
    # Castle Revenge Hard: alchemists with an `at` spot and no `near`
    ex = _buff_executor([(10, 10), (30, 30), (31, 31)])
    step = {"do": "place", "kind": "alchemist", "role": "support", "at": [12 / 40, 10 / 40]}
    spots = _buff_spots_on_open_ground(ex, "alchemist", step)
    assert spots[0][:2] == (12, 10)
    assert len(spots) > 1         # the best buffing spots still follow as fallbacks


def test_researched_spot_that_buffs_nothing_is_skipped():
    ex = _buff_executor([(30, 30), (31, 31)])
    step = {"do": "place", "kind": "village", "role": "support", "at": [5 / 40, 5 / 40]}
    spots = _buff_spots_on_open_ground(ex, "village", step)
    assert spots and all((x - 5) ** 2 + (y - 5) ** 2 > 25 for x, y, _ in spots)


def test_refused_researched_spot_moves_to_its_neighbours():
    # Lotus Island CHIMPS (2026-11-05): b3's spot by the bay was refused and
    # the next spot offered in the same pick-up was the best by role, at the
    # far end of the map. Now the cells round the `at` come first.
    ex = _buff_executor([(10, 10), (30, 30), (31, 31), (32, 30)])
    ex.failed_spots = {("alchemist", 12, 10)}          # the game refused the exact spot
    step = {"do": "place", "kind": "alchemist", "role": "support", "at": [12 / 40, 10 / 40]}
    spots = _buff_spots_on_open_ground(ex, "alchemist", step)
    near = [(x, y) for x, y, _ in spots if (x - 12) ** 2 + (y - 10) ** 2 <= Executor.AT_SEARCH_CELLS ** 2]
    assert spots[0][:2] in near and (12, 10) not in near
    assert len(near) >= 2, "the next try in the same pick-up stays by the researched spot too"


def test_at_neighbours_are_nearest_first_and_spaced():
    import numpy as np
    ex = _buff_executor([])
    ex.failed_spots = {("buccaneer", 20, 20)}
    step = {"do": "place", "kind": "buccaneer", "at": [20 / 40, 20 / 40]}
    spots = ex._at_spots(step, np.ones((40, 40), bool), 4)
    dist = [(x - 20) ** 2 + (y - 20) ** 2 for x, y, _ in spots]
    assert len(spots) == 4 and dist == sorted(dist) and 0 < dist[0] <= max(dist) <= Executor.AT_SEARCH_CELLS ** 2
    gap = Executor.AT_SPOT_GAP_CELLS ** 2
    assert all((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 >= gap for i, a in enumerate(spots) for b in spots[:i])


def test_buffer_goes_where_it_buffs_most_before_widening_near():
    # Alpine Run CHIMPS (2026-11-07): the widened `near` circle round the
    # average of r1-r3 (r3 pushed across the map) put the village between
    # the groups, buffing nothing; the most-buffing spot comes first now
    ex = _executor(lambda st: st.get("near_radius", 0) > 10)
    ex.buff_ok = True
    step = {"do": "place", "kind": "village", "role": "support", "near": ["s1"], "near_radius": 8}
    assert ex._spots_widening("village", step) == [(5, 5, 2.0)]
    assert len(ex.seen) == 1      # only the build's own search, no widened circle


def test_refused_at_neighbourhood_widens_before_spots_by_role():
    # Alpine Run CHIMPS (2026-11-07): r3's spot and its one legal neighbour
    # were refused, and the next spot was the best by role, across the map
    import numpy as np
    ex = _buff_executor([])
    valid = np.zeros((40, 40), bool)
    valid[20, 30] = True                       # the only legal cell nearby, 10 cells off
    valid[2, 2] = True                         # and one far away
    step = {"do": "place", "kind": "boomerang", "at": [20 / 40, 20 / 40]}
    assert ex._at_spots(step, valid, 4) == []  # nothing within AT_SEARCH_CELLS
    wide = ex._at_spots(step, valid, 4, radius=Executor.AT_WIDE_CELLS)
    assert [c[:2] for c in wide] == [(30, 20)], "the wider ring finds the near cell, not the far one"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
