"""hard_ninja_alch_sun holds rounds 37-40 in Half Cash and Double HP.

The general land build is the planner's last-resort pick for open Half Cash
and Double HP medals. Up to 2026-11-08 it lost 16 Half Cash games at rounds
35-40 and two Double HP games at round 40: its only MOAB answer was n2's
Flash Bomb (2-0-3), a short-range, segment-placed ninja that half income
bought at R35-40, and the live forecast rated rounds 37-40 at 0.06-0.9.
The plan now buys two Heli Pilots before round 40 (h1 3-2-0 with IFR camo,
h2 3-0-0 then 3-0-2), the MOAB answers point at them, and the plan owns the
cash (plan_first).

Checked here with the executor-faithful replay (simulate_threats.simulate
on each learned map, Fast Track start and Double Cash income as the account
plays these modes), the board at each round's start rated by the live
forecast (RoundForecast with the learned map's sight grid and heights; the
hero is not counted):
  * on maps the build lost in Half Cash, both helis stand when round 40
    starts and rounds 37 and 40 rate at R37_MARGIN / R40_MARGIN or more (the
    old plan: R40 0.12-0.66, R37 0.06 on most of them);
  * on the maps it lost in Double HP, round 40 rates at R40_MARGIN or more;
  * on the maps it lost late in Half Cash (Dark Path R63, Moon Landing R76,
    2026-11-08, both on the old plan: no plan_first, the cash went to 6-10
    spike factories, darts and aces, n2's Sticky Bomb never bought), the
    plan's late towers stand by round 60 and the lost round rates above
    what the live forecast rated it in the loss.
Run: python tests/test_hard_ninja_alch_sun_r40_offline.py"""
import logging
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

BUILD = "hard_ninja_alch_sun"
FIRST_MOAB = {t: r for r, t in S.THREATS}["moab"]      # round 40
R37 = 37                                               # the black/white/lead/zebra rush that ended 5 games
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
R40_MARGIN = 1.2
R37_MARGIN = 0.9
# Half Cash maps it lost (R40 / R37 when written: Cargo 1.61/2.33, Pat's
# Pond 2.04/1.66, Quad 1.28/1.01, Party Parade 1.45/1.51, Infernal
# 2.02/2.51, Chutes 1.66/2.25). Bazaar, Ship Capture and Bloonarius Prime
# have their own Half Cash builds (tests/test_half_cash_map_builds_offline.py):
# the heliport has no legal cell on Bazaar.
HALF_CASH_MAPS = ("Cargo", "Pat's Pond", "Quad", "Party Parade", "Infernal", "Chutes")
# Half Cash maps it lost late: map -> (round lost, the live forecast's rating
# of that round in the loss). Replayed when written: Dark Path R63 0.44,
# Moon Landing R76 0.56 (the maps it won to round 80 replay at R63 0.26-0.72,
# R76 0.35-0.81: the model rates the late rounds low everywhere).
LATE_LOSSES = {"Dark Path": (63, 0.18), "Moon Landing": (76, 0.40)}
# Double HP maps it lost (R40 when written: Castle Revenge 1.96, Tricky
# Tracks 1.24)
DOUBLE_HP_MAPS = ("Castle Revenge", "Tricky Tracks")


def _replay(mode, map_name):
    """(simulate result, {round: board}) on the economy the account plays."""
    econ = O.economy(mode, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(S.load_all()[BUILD], mode, map_name, real_map=True, learned=True,
                     scenario=scenario, boards=boards)
    return r, boards


def _margin(mode, map_name, board, rnd):
    """The live forecast's rating of `board` for round `rnd` on the map."""
    m = SIM.map_model(map_name, learned=True)
    fc = RoundForecast(map_name, mode, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready(), map_name
    towers = [SimpleNamespace(tid=tid, kind=k, tiers=ti, x=fx, y=fy) for tid, (k, ti, fx, fy) in board.items()]
    st = fc.stations(towers)
    return D.round_margin(st, mode, rnd, fc.track) if st else 0.0


def test_moab_answers_are_the_helis():
    strat = S.load_all()[BUILD]
    assert strat.get("plan_first") is True
    assert {st["id"] for st in strat["answers"]["moab"]} == {"h1", "h2"}


def test_half_cash_holds_rounds_37_and_40():
    for map_name in HALF_CASH_MAPS:
        r, boards = _replay("half_cash", map_name)
        at40 = boards[FIRST_MOAB]
        assert at40["h1"][1] == (3, 2, 0) and at40["h2"][1][0] >= 3, (map_name, at40)
        m40 = _margin("half_cash", map_name, at40, FIRST_MOAB)
        m37 = _margin("half_cash", map_name, boards[R37], R37)
        assert m40 >= R40_MARGIN, f"{map_name}: round 40 rated {m40:.2f}"
        assert m37 >= R37_MARGIN, f"{map_name}: round 37 rated {m37:.2f}"


def test_double_hp_holds_round_40():
    for map_name in DOUBLE_HP_MAPS:
        _, boards = _replay("double_hp", map_name)
        m40 = _margin("double_hp", map_name, boards[FIRST_MOAB], FIRST_MOAB)
        assert m40 >= R40_MARGIN, f"{map_name}: round 40 rated {m40:.2f}"


def test_half_cash_late_losses_hold_better():
    for map_name, (rnd, live) in LATE_LOSSES.items():
        r, boards = _replay("half_cash", map_name)
        at60 = boards[60]
        assert (at60["n1"][1], at60["n2"][1], at60["a1"][1]) == ((4, 0, 2), (2, 0, 4), (4, 2, 0)), (map_name, at60)
        # plan_first: nothing off-plan before the lost round (the $200
        # opener dart the executor puts in front of the plan is listed too)
        assert not [b for b in r["surplus"] if b[0] <= rnd and "opener" not in b[1]], (map_name, r["surplus"])
        m = _margin("half_cash", map_name, boards[rnd], rnd)
        assert m > live, f"{map_name}: round {rnd} rated {m:.2f}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
