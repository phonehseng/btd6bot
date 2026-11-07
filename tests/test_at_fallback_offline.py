"""Offline checks that a build's researched spot (`at`) stays the centre of
the search when the game refuses it, and that a set-aside tower's steps keep
their plan order.

Alpine Run CHIMPS (2026-11-07 07:46-07:51, lost at round 40):
  * r3's spot and the one neighbour found legal were refused, and the third
    spot of the same pick-up was the best by role on the whole map: the
    boomerang stood at (0.639, 0.351), across the map from the cluster, and
    the village placed near r1-r3 followed it (Executor._far_from_at);
  * v1's spot was refused, its steps 0-2-0 and 4-2-0 went aside with it, and
    once it stood the 4-2-0 step bought $2,915 of top-path tiers ahead of the
    plan's MOAR Glaives (Executor._waits_for_set_aside_place).

The executor runs on tools/simulate_threats' open field and cash game.
Run: python tests/test_at_fallback_offline.py"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from btd6bot import strategy as S  # noqa: E402

import simulate_threats as SIM  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)


def executor(plan, mode="chimps"):
    """A real Executor on the open field (every cell legal, every cell scored
    alike, so the role ranking alone would start at the top-left corner)."""
    g = SIM.CashGame(S.PRICE_FAMILY.get(mode, "hard"))
    strat = {"id": "t", "hero": "quincy", "plan": plan, "modes": [mode]}
    ex = S.Executor(g, SIM.OpenModel(), strat, mode, SIM.full_account())
    return g, ex


def test_refused_at_falls_back_near_its_spot_not_across_the_map():
    step = {"do": "place", "id": "r3", "kind": "boomerang", "role": "dps", "at": [0.8, 0.8]}
    g, ex = executor([step])
    cx, cy = ex.m.frac_to_cell(0.8, 0.8)
    # the game refused the spot and every cell _at_spots would offer round it
    r = ex.AT_SEARCH_CELLS
    ex.failed_spots |= {("boomerang", cx + dx, cy + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)}
    spots = ex.pick_spots("boomerang", step, n=ex.SPOTS_PER_HOLD)
    assert spots, "a legal cell close to the spot is still offered"
    far = [(x, y) for x, y, _ in spots if (x - cx) ** 2 + (y - cy) ** 2 > ex.AT_FALLBACK_CELLS ** 2]
    assert not far, f"spots offered across the map: {far}"


def test_without_at_the_role_ranking_still_searches_the_whole_map():
    step = {"do": "place", "id": "a1", "kind": "boomerang", "role": "dps"}
    g, ex = executor([step])
    spots = ex.pick_spots("boomerang", step, n=4)
    assert spots and spots[0][:2] == (0, 0), spots     # the open field's first-ranked cell


def test_at_is_dropped_only_when_nothing_near_it_is_left():
    step = {"do": "place", "id": "r3", "kind": "boomerang", "role": "dps", "at": [0.8, 0.8]}
    g, ex = executor([step])
    cx, cy = ex.m.frac_to_cell(0.8, 0.8)
    r = ex.AT_FALLBACK_CELLS + 1
    ex.failed_spots |= {("boomerang", cx + dx, cy + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)}
    assert ex.pick_spots("boomerang", step, n=4) == []
    spots = ex._spots_widening("boomerang", step)
    assert spots, "a damage tower is still placed somewhere, as the last resort"


def test_set_aside_tower_steps_keep_plan_order():
    plan = [
        {"do": "place", "id": "a1", "kind": "boomerang", "role": "dps"},
        {"do": "place", "id": "v1", "kind": "village", "role": "support", "near": ["a1"]},
        {"do": "upgrade", "id": "v1", "to": "0-2-0"},
        {"do": "upgrade", "id": "a1", "to": "2-0-0"},
        {"do": "upgrade", "id": "v1", "to": "2-2-0"},
    ]
    g, ex = executor(plan)
    real_place = g.place
    refusals = {"v1": 1}

    def place(tid, kind, fx, fy, check_valid=True, more_spots=()):
        """The village's first pick-up is refused at every spot offered."""
        if refusals.get(tid):
            refusals[tid] -= 1
            g.refused_spots, g.click_refusals, g.fail_reason = [], 0, "spot"
            return None
        return real_place(tid, kind, fx, fy, check_valid, more_spots)

    g.place = place
    for _ in range(40):
        g.cash = 100000
        ex.tick(g.cash, 30)
    order = [t for _, t in g.bought]
    v1 = [t for t in order if t.startswith("upgrade v1")]
    assert "place v1 (village)" in order and v1, order
    # Radar Scanner's path first, as the plan says, then the top path
    assert v1[:2] == ["upgrade v1 -> 0-1-0", "upgrade v1 -> 0-2-0"], v1
    # and a1's step, which comes before v1 -> 2-2-0 in the plan, before any top-path tier of v1
    first_top = order.index("upgrade v1 -> 1-2-0")
    assert order.index("upgrade a1 -> 2-0-0") < first_top, order


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
