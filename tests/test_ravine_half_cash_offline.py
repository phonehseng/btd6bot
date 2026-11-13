"""Ravine Half Cash: the map build covers both entrances from the round-22
start, and the general druid build is kept off that medal.

Cases 20261113_122848_Ravine_half_cash and 20261113_135225_Ravine_half_cash
(2026-11-13 12:28 and 13:52, both lost at round 26 within 80 seconds of
Play; hard_ninja_alch_sun lost the same way at 04:29 and 06:41). A Ravine
round runs down one entrance and both of its forks (Path1 on even rounds,
Path2 on odd). obyn_druid_poplust places by track segment and spent the
whole Fast Track start beside the top-right bend, which only Path2 passes:
round 22's whites took 83 lives, and the replay rates every even round at
the model's 0.06 floor. strategies/maps/ravine_half_cash.yaml opens with a
tower beside every fork.

Checked with the executor-faithful replay (simulate_threats.simulate on the
learned map, the account's Fast Track economy), each round's start board
rated by the live forecast, as tests/test_ravine_magic_offline.py does.
"""
from __future__ import annotations

import logging
import math
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O                 # noqa: E402
import simulate_threats as SIM              # noqa: E402
from btd6bot import dps_model as D          # noqa: E402
from btd6bot import placement as P          # noqa: E402
from btd6bot import planner as PL           # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP = "Ravine"
MODE = "half_cash"
BUILD = "ravine_half_cash"
GENERAL = "obyn_druid_poplust"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
FLOOR = 0.1             # a rating at the damage model's floor: nothing reaches the round's bloons
# The rounds the four games were lost in (22, 24, 26), all on Path1, and what
# the map build's start board must rate there (0.90, 2.68, 0.78 measured on
# 2026-11-13; held a little under).
LOST_ROUNDS = (22, 24, 26)
MIN_LOST_ROUND_MARGIN = 0.6
MIN_REACH = 40          # units of track a tower must reach on a fork to count as beside it


@lru_cache(maxsize=None)
def _replay(build):
    """The build replayed on Ravine Half Cash from the Fast Track start:
    (simulate's result, {round: board at the round's start})."""
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(S.load_all()[build], MODE, MAP, real_map=True, learned=True, scenario=scenario, boards=boards)
    return r, boards


@lru_cache(maxsize=None)
def _forecast():
    m = SIM.map_model(MAP, learned=True)
    fc = RoundForecast(MAP, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    return fc


@lru_cache(maxsize=None)
def _margins(build):
    """{round: the live forecast's margin for the board standing at its start}."""
    _, boards = _replay(build)
    fc = _forecast()
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        out[rnd] = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
    return out


def test_start_board_has_a_tower_beside_every_fork():
    """The towers bought with the round-22 cash reach each of the four forks
    (Track routes), sight counted: the lost boards reached Path2's only."""
    fc = _forecast()
    _, boards = _replay(BUILD)
    start = boards[min(boards)]
    reach = [0] * len(fc.track.paths)
    for kind, tiers, fx, fy in start.values():
        if kind == "hero":
            continue
        x, z, _ = fc.track.frac_to_world(fx, fy)
        sight = fc.sight if P.needs_sight(kind) else None
        for i, zone in enumerate(fc.track.zones(x, z, D.profile(kind, tiers).range, sight=sight)):
            if zone and zone.length >= MIN_REACH:
                reach[i] += 1
    assert min(reach) >= 1, list(zip((p["name"] for p in fc.track.paths), reach))


def test_plan_goes_down_where_it_is_pinned():
    """No step is given up in the replay and every tower stands at its `at`."""
    model = SIM.map_model(MAP, learned=True)
    r, _ = _replay(BUILD)
    assert r["gaps"] == [], r["gaps"]
    for st in S.load_all()[BUILD]["plan"]:
        if st.get("do") == "place" and st["kind"] != "hero":
            _, _, fx, fy = r["placed"][st["id"]]
            (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(fx, fy)
            assert math.hypot(px - ax, py - ay) <= S.Executor.AT_SEARCH_CELLS, (st["id"], (fx, fy))


def test_the_lost_rounds_are_covered():
    """Rounds 22, 24 and 26 run down Path1. The general build's replay rates
    them at the floor, as the games went; the map build's does not, and no
    round of its game is left at the floor on the entrance it uses."""
    own, general = _margins(BUILD), _margins(GENERAL)
    for rnd in LOST_ROUNDS:
        assert general[rnd] < FLOOR, (rnd, general[rnd])
        assert own[rnd] >= MIN_LOST_ROUND_MARGIN, (rnd, own[rnd])
    even_at_floor = [r for r, v in general.items() if r % 2 == 0 and v < FLOOR]
    assert len(even_at_floor) >= 20, even_at_floor          # 24 of 30 measured: Path1 is never covered
    assert sum(v < FLOOR for v in own.values()) <= 1, {r: round(v, 2) for r, v in own.items() if v < FLOOR}


def test_general_build_is_kept_off_ravine_half_cash():
    d = S.load_all()[GENERAL]
    assert MAP not in d["planner"]["excluded_maps"]      # its Medium and Hard stay open there
    spec = PL.StrategySpec.from_any({**d["planner"], "id": d["id"], "modes": d["modes"]})   # the runner reads the planner block
    assert MAP in spec.excluded_by_mode.get(MODE, ())
    assert MAP not in spec.excluded_by_mode.get("hard", ())


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
