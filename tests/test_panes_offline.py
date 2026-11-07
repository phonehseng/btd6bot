"""Covered Garden's glass panes: one garden quarter is open each round, the
bottom-left on round 1, then clockwise (top-left, top-right, bottom-right).

The bot must place towers on the open quarter's ground in its round, never
on a shut one, and click (upgrade, sell) a tower under a pane only while
that pane is open. Offline: the map geometry only, no game."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L, mapgeom, placement as PL   # noqa: E402
from btd6bot.maplearn import MapModel                      # noqa: E402

# the quarter open in rounds 1-4 (screen fractions: x < 0.46 is the left half,
# y < 0.49 the top half; data/map_geometry/coveredgarden.json)
OPEN_IN_ROUND = {1: ("left", "bottom"), 2: ("left", "top"), 3: ("right", "top"), 4: ("right", "bottom")}


def model():
    m = MapModel.load("Covered Garden", L.get(1920, 1200)["playfield"])
    m.refused = {}     # what earlier games learned does not matter here
    return m


def test_open_quarter_follows_the_round():
    m = model()
    always = PL.valid_spots(m, "sniper")
    for rnd in range(1, 9):
        extra = PL.valid_spots(m, "sniper", now_round=rnd) & ~always
        ys, xs = np.nonzero(extra)
        assert len(xs) > 20, f"round {rnd}: no pane ground opened"
        fx, fy = m.cell_to_frac(int(xs.mean()), int(ys.mean()))
        side, half = OPEN_IN_ROUND[(rnd - 1) % 4 + 1]
        assert (fx < 0.46) == (side == "left"), (rnd, fx)
        assert (fy < 0.49) == (half == "top"), (rnd, fy)


def test_whole_game_grid_keeps_panes_shut():
    m = model()
    always = PL.valid_spots(m, "sniper")
    for rnd in range(1, 5):
        assert not (always & ~PL.valid_spots(m, "sniper", now_round=rnd)).any(), \
            "ground open all game must stay open in every round"


def test_tower_under_a_pane_is_clicked_only_in_its_rounds():
    m = model()
    top_left = (0.32, 0.28)      # the guides' ninja pocket by the fountain
    rounds = [r for r in range(1, 13) if mapgeom.pane_at(m, *top_left, r)[1]]
    assert rounds == [2, 6, 10], rounds
    assert mapgeom.pane_at(m, 0.05, 0.62, 3) == (None, True), "the left strip is never covered"


def test_maps_without_panes_are_untouched():
    m = MapModel.load("Monkey Meadow", L.get(1920, 1200)["playfield"])
    assert mapgeom.pane_at(m, 0.5, 0.5, 3) == (None, True)


def test_plan_steps_under_a_shut_pane_wait_for_their_round():
    """A build step whose researched spot (`at`) is under a pane is set aside
    while that pane is shut - not moved off the garden, not holding up the
    rest of the plan - and placed and upgraded in the pane's round.
    (The executor runs on tools/simulate_threats' cash game.)"""
    import logging
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import simulate_threats as SIM
    from btd6bot import strategy as S
    logging.getLogger().setLevel(logging.ERROR)
    m = model()
    top_left = [0.32, 0.28]                    # open in rounds 2, 6, 10 ...
    strip = PL.valid_spots(m, "sniper")        # ground open all game
    ys, xs = np.nonzero(strip)
    s_at = [round(float(v), 3) for v in m.cell_to_frac(int(xs[len(xs) // 2]), int(ys[len(ys) // 2]))]
    plan = [{"do": "place", "id": "n1", "kind": "ninja", "role": "dps", "at": top_left},
            {"do": "upgrade", "id": "n1", "to": "1-0-0"},
            {"do": "place", "id": "s1", "kind": "sniper", "role": "dps", "at": s_at}]
    g = SIM.CashGame("medium")
    g.cash = 50000.0
    ex = S.Executor(g, m, {"id": "t", "hero": "quincy", "plan": plan, "modes": ["medium"]},
                    "medium", SIM.full_account())
    for _ in range(6):
        ex.tick(g.cash, 3)                      # the top-right pane is open
    assert "n1" not in g.towers and "s1" in g.towers, sorted(g.towers)
    assert any(d.get("id") == "n1" for d in ex.deferred), ex.deferred
    for _ in range(6):
        ex.tick(g.cash, 6)                      # the top-left pane's round
    assert "n1" in g.towers and g.towers["n1"].tiers[0] == 1, g.towers.get("n1")
    p = g.towers["n1"]
    assert mapgeom.pane_at(m, p.x, p.y, 6)[0] is not None, "placed on the garden ground it was planned for"


def test_own_pane_build_is_not_judged_by_the_all_game_fit():
    """The map-fit table measures ground open all game; Covered Garden's own
    build stands under the panes in their rounds, so the table's fit for its
    towers (mermonkeys and skywardens: 0.35) does not scale its chance down.
    Midnight Mansion's cycling fires are no panes."""
    from btd6bot import mapfit
    from btd6bot import planner as P
    assert P.has_cycling_panes("Covered Garden") and not P.has_cycling_panes("Midnight Mansion")
    assert mapfit.strategy_fit("Covered Garden", ["mermonkey", "skywarden"]) < 0.5
    own = P.StrategySpec(id="t_own", towers={"mermonkey": (4, 4, 2), "skywarden": (2, 2, 0)},
                         modes=frozenset({"medium"}), base_success={"medium": 0.8},
                         maps=frozenset({"Covered Garden"}))
    assert P.map_fit_factor(own, "Covered Garden", "medium") == 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
