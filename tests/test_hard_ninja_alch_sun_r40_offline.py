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
  * in Half Cash, round 63's ceramic rush rates at R63_MARGIN or more with
    the two Druids and the Bomb Shooter standing (Dark Castle lost there,
    2026-11-09), and those Half Cash-only steps stay out of Double HP.
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
# Pond 2.04/1.66, Quad 1.28/1.01, Party Parade 1.45/1.51, Chutes 1.66/2.25,
# Another Brick 2.09/2.54). Bazaar is excluded from this build (no legal
# heliport cell), and Infernal since 2026-11-09 (the game refuses the
# heliport there; see test_infernal_is_excluded); Bazaar, Ship Capture and
# Bloonarius Prime have their own Half Cash builds
# (tests/test_half_cash_map_builds_offline.py).
HALF_CASH_MAPS = ("Cargo", "Pat's Pond", "Quad", "Party Parade", "Chutes", "Another Brick")
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


def test_infernal_is_excluded():
    """The game refused every heliport spot on Infernal in both live games
    that tried one (Military Only 2026-11-04, this build's Half Cash
    2026-11-09: 9 spots each, no heli ever stood). The replay cannot see
    those refusals (8+ in a row are not learned) and places the helis, so
    the build stays off the map: without them it lost round 49."""
    from btd6bot import planner as PL
    from btd6bot.account import AccountState
    strat = S.load_all()[BUILD]
    spec = PL.StrategySpec.from_any(dict(strat, id=BUILD, **(strat.get("planner") or {})))
    assert "Infernal" in spec.excluded_maps
    category = AccountState().map_category("Infernal")
    for mode in strat["modes"]:
        assert not PL._strategy_fits(spec, "Infernal", category, mode), mode


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
        # the round-63 Druids/Bomb and the R59-78 radar/third heli are Half
        # Cash steps (`modes: [half_cash]`)
        assert not {"d1", "d2", "b1", "v2", "h3"} & set(boards[max(boards)]), (map_name, boards[max(boards)])
        m40 = _margin("double_hp", map_name, boards[FIRST_MOAB], FIRST_MOAB)
        assert m40 >= R40_MARGIN, f"{map_name}: round 40 rated {m40:.2f}"


# Late Half Cash: the build lost Dark Path at round 63 and Moon Landing at
# round 76 on 2026-11-08 with a Sun Avatar as its late step. Two Apache
# Dartships replace it (R76 when written: Dark Path 2.02, Moon Landing 4.09;
# 0.40 / 0.61 with the Sun Avatar). Since 2026-11-09 the radar village and
# a third heli 3-2-0 come first in Half Cash, so h2's Dartship stands from
# round 78 rather than 74; round 76 is held by h3 (R76: Dark Path 2.71,
# Moon Landing 4.56).
LATE_ROUND = 76
DARTSHIP_BY = 78
LATE_MARGIN = 1.2
LATE_MAPS = ("Dark Path", "Moon Landing")


def test_half_cash_late_game_has_the_dartships():
    for map_name in LATE_MAPS:
        _, boards = _replay("half_cash", map_name)
        assert boards[DARTSHIP_BY]["h2"][1] == (4, 0, 2), (map_name, boards[DARTSHIP_BY])
        board = boards[LATE_ROUND]
        assert board["h3"][1] == (3, 2, 0), (map_name, board)
        m = _margin("half_cash", map_name, board, LATE_ROUND)
        assert m >= LATE_MARGIN, f"{map_name}: round {LATE_ROUND} rated {m:.2f}"


# Round 63 in Half Cash: three bursts of 40 ceramics and 75 leads. Dark
# Castle lost there on 2026-11-09 holding $19,953 for the first Dartship
# (R63 rated 0.17-0.61 on every map, the Dartship landing at R64-65). Two
# Druids (0-4-2, 0-3-2) and a Bomb Shooter 3-0-2 come before the Dartships
# now (R63 when written: Dark Castle 1.24, X Factor 1.49, Cargo 2.07, Pat's
# Pond 1.85, Quad 1.66, Party Parade 1.56, Chutes 2.02, Dark Path 2.92).
R63 = 63
R63_MARGIN = 1.0
R63_MAPS = ("Dark Castle", "X Factor", "Cargo", "Pat's Pond", "Quad", "Party Parade", "Chutes", "Dark Path")


def test_half_cash_holds_round_63():
    for map_name in R63_MAPS:
        _, boards = _replay("half_cash", map_name)
        board = boards[R63]
        assert board["d1"][1] == (0, 4, 2) and board["b1"][1] == (3, 0, 2), (map_name, board)
        m = _margin("half_cash", map_name, board, R63)
        assert m >= R63_MARGIN, f"{map_name}: round {R63} rated {m:.2f}"


# Half Cash rounds 59-78: Mesa lost R64 (9 MOABs) holding $13,190 and X
# Factor lost R78 (72 camo ceramics) holding $13-17k on 2026-11-09, both
# waiting for the $21,600 Dartship. A Radar Scanner village (v2 0-2-0) and
# a third heli (h3 3-2-0) come first now. Worst round over 59-78, before ->
# when written (each map in its own process; in one process the numbers
# can differ a little, hence the slack below them):
#   Mesa 0.08 -> 0.41 (R59), X Factor 0.06 -> 0.36 (R77), Dark Castle
#   0.07 -> 0.20 (R78), Cargo 0.10 -> 0.68 (R75), Pat's Pond 0.09 -> 0.45
#   (R59), Quad 0.09 -> 0.81 (R61), Party Parade 0.08 -> 0.46 (R77),
#   Chutes 0.10 -> 0.67 (R77). The old worst was round 78 on every map.
LATE_ROUNDS = range(59, 79)
LATE_FLOORS = {"Mesa": 0.35, "X Factor": 0.3, "Dark Castle": 0.15, "Cargo": 0.6,
               "Pat's Pond": 0.4, "Quad": 0.7, "Party Parade": 0.4, "Chutes": 0.6}


def test_half_cash_rounds_59_to_78_floors():
    for map_name, floor in LATE_FLOORS.items():
        _, boards = _replay("half_cash", map_name)
        assert boards[R63]["v2"][1] == (0, 2, 0), (map_name, boards[R63])   # radar by R63
        assert boards[max(LATE_ROUNDS)]["h3"][1] == (3, 2, 0), map_name
        margins = {rnd: _margin("half_cash", map_name, boards[rnd], rnd) for rnd in LATE_ROUNDS}
        worst = min(margins, key=margins.get)
        assert margins[worst] >= floor, f"{map_name}: round {worst} rated {margins[worst]:.2f} (floor {floor})"


def test_hard_and_double_hp_skip_the_half_cash_steps():
    strat = S.load_all()[BUILD]
    hc_ids = {st["id"] for st in strat["plan"] if st.get("modes") == ["half_cash"] and st["do"] == "place"}
    assert {"d1", "d2", "b1", "v2", "h3"} <= hc_ids, hc_ids


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
