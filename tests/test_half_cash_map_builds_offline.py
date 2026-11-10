"""Bazaar, Ship Capture and Bloonarius Prime Half Cash: the map builds hold
where the general build lost.

On 2026-11-06/08 the general land build hard_ninja_alch_sun (the planner's
last-resort pick for open Half Cash medals) lost Bazaar at rounds 35 and 37,
Ship Capture at rounds 36 and 37 and Bloonarius Prime at rounds 26 and 40.
Its 2026-11-08 heli rework (tests/test_hard_ninja_alch_sun_r40_offline.py)
does not reach Bazaar (no cell fits the heliport), leaves Ship Capture under
1 at rounds 34-39 and Bloonarius Prime under 0.5 at rounds 22-25. Each map
got its own Half Cash build from the spots of its other map builds:
  * strategies/maps/bazaar_half_cash.yaml (Night Vision snipers, Advanced
    Intel subs in the canal; from bazaar_medium / bazaar_deflation)
  * strategies/maps/shipcapture_half_cash.yaml (shipcapture_deflation bought
    in order, the MOAB Mauler / Assassin in the plan)
  * strategies/maps/bloonariusprime_half_cash.yaml (Pursuit helis and
    snipers from bloonariusprime_military_only, camo and lead in the setup)
  * strategies/maps/enchantedglade_half_cash.yaml (2026-11-09: the general
    build lost round 31 there; Pursuit helis with Razor Rotors and IFR, top-
    left snipers, a bottom-centre ninja, all from the map's other builds)

Checked here with the executor-faithful replay (simulate_threats.simulate on
each learned map, Fast Track start and Double Cash income as the account
plays Half Cash), the board at each round's start rated by the live forecast
(RoundForecast with the learned map's sight grid and heights; no hero):
  * every plan tower stands on its `at` spot;
  * every round from 22 to 80 rates at the map's MIN_MARGIN or more and the
    rounds the general build lost at its LOST_MARGIN or more;
  * the map build rates its weakest round above the general build's.
Run: python tests/test_half_cash_map_builds_offline.py"""
import logging
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O                 # noqa: E402
import simulate_threats as SIM              # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MODE, GENERAL = "half_cash", "hard_ninja_alch_sun"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)

# map -> (build, MIN_MARGIN over rounds 22-80, rounds the general build lost
# or rated lowest, LOST_MARGIN for them). When written:
#   Bazaar: worst R36 0.84; R35 1.09, R37 1.06, R40 2.04 (general: worst
#     0.06; R37 0.43, R40 0.12). Worst R34 0.75 since 2026-11-09 (below).
#   Ship Capture: worst R79 0.86; R34 1.04, R36 1.15, R37 1.46, R40 1.59
#     (general: worst 0.06; R34 0.32, R36 0.75, R37 0.92, R40 1.14).
#     PARKED 2026-11-09 (base_success 0.05): the first live game lost R39.
#     The replay over-rates this map (see the build's header), so these
#     numbers only guard the replay, not the live game. Since 2026-11-09
#     the replay rates R34 0.44, R36 1.01, R37 0.85, R40 0.90: frags and
#     Shrapnel Shot no longer count hits on the bloon their carrier struck
#     (tests/test_thrown_off_pieces_offline.py), which brings the replay
#     closer to the live loss.
#   Bloonarius Prime: worst R30 0.46 (Razor Rotors stands from R30); R22
#     2.04, R25 2.28, R26 1.89, R40 2.99 (general: worst 0.06; R22 0.43,
#     R25 0.41, R26 0.76, R40 2.33)
#   Enchanted Glade (2026-11-09, after the general build lost R31 live with
#     the opening rated 0.06): worst R67/R78 0.81; R26 1.59, R27 1.19, R28
#     7.91, R31 2.38 (general: worst R28 0.64; R27 0.82, R31 0.92)
CASES = {
    "Bazaar": ("bazaar_half_cash", 0.7, (35, 37, 40), 1.0),
    "Ship Capture": ("shipcapture_half_cash", 0.4, (34, 36, 37, 40), 0.4),
    "Bloonarius Prime": ("bloonariusprime_half_cash", 0.4, (22, 25, 26, 40), 1.5),
    "Enchanted Glade": ("enchantedglade_half_cash", 0.7, (26, 27, 28, 31), 1.0),
}


def _replay(strat, map_name):
    """(simulate result, {round: board}) on the Half Cash economy the account plays."""
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(strat, MODE, map_name, real_map=True, learned=True, scenario=scenario, boards=boards)
    return r, boards


def _margins(map_name, boards):
    """{round: the live forecast's rating of the board at that round's start}."""
    m = SIM.map_model(map_name, learned=True)
    fc = RoundForecast(map_name, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready(), map_name
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=tid, kind=k, tiers=ti, x=fx, y=fy) for tid, (k, ti, fx, fy) in board.items()]
        st = fc.stations(towers)
        out[rnd] = D.round_margin(st, MODE, rnd, fc.track) if st else 0.0
    return out


def _check_map(map_name):
    build, min_margin, lost_rounds, lost_margin = CASES[map_name]
    strat = S.load_all()[build]
    assert strat.get("plan_first") is True and strat["modes"] == [MODE], build
    r, boards = _replay(strat, map_name)
    assert r["gaps"] == [], (map_name, r["gaps"])
    model = SIM.map_model(map_name, learned=True)
    for st in strat["plan"]:
        if st.get("do") == "place" and st["kind"] != "hero":
            _, _, fx, fy = r["placed"][st["id"]]
            (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(fx, fy)
            assert math.hypot(px - ax, py - ay) <= S.Executor.AT_SEARCH_CELLS, (map_name, st["id"], (fx, fy))
    own = _margins(map_name, boards)
    worst = min(own, key=own.get)
    assert own[worst] >= min_margin, f"{map_name}: round {worst} rated {own[worst]:.2f}"
    for rnd in lost_rounds:
        assert own[rnd] >= lost_margin, f"{map_name}: round {rnd} rated {own[rnd]:.2f}"
    _, general_boards = _replay(S.load_all()[GENERAL], map_name)
    general = _margins(map_name, general_boards)
    assert own[worst] > min(general.values()), map_name


def test_bazaar_half_cash():
    _check_map("Bazaar")


def test_shipcapture_half_cash():
    _check_map("Ship Capture")


def test_bloonariusprime_half_cash():
    _check_map("Bloonarius Prime")


def test_enchantedglade_half_cash():
    _check_map("Enchanted Glade")


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
