"""Ravine Double HP MOABs: the map build has area damage on both stretches
of the A fork that a tower can reach.

Case 20261112_222133_Ravine_double_hp (2026-11-12 22:10, lost round 64):
hard_ninja_alch_sun held rounds 22-63 without losing a life and lost all 100
within ten seconds of round 64 (nine MOABs, three fortified, down Path1's
forks). They were popped at the top of the A fork (Path1-split2) and two
fortified ceramics got out (defeat screen: ceramic -228); only single-target
ninjas and a 0-0-0 dart stood on that fork. strategies/maps/
ravine_double_hp.yaml keeps the general build's order on the spots that game
stood on and adds a Recursive Cluster bomb beside A and one in the middle.

Checked with the executor-faithful replay (simulate_threats.simulate on the
learned map, the account's Fast Track + Double Cash economy), each round's
start board rated by the live forecast, as tests/test_ravine_magic_offline.py
does. The model rates a blimp round on the blimp alone (docs/backlog.md 109),
so the replay cannot show the bombs' worth on round 64 itself; what is held
here is where they stand, when they are bought, and that the build as a
whole rates no worse than the general one.
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
MODE = "double_hp"
BUILD = "ravine_double_hp"
GENERAL = "hard_ninja_alch_sun"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
A_FORK = "Path1+Path1-split2"
CLUSTER = (2, 0, 4)             # Recursive Cluster
# Units of the A fork each bomb must reach from its `at` (measured 2026-11-12:
# bA 67-183 = 116, bM 218-237 = 19; no legal cell reaches units 190-210).
MIN_UPPER_REACH = 90
MIN_TAIL_REACH = 12
# The build's worst round on 2026-11-12 was 0.44 (R78, R80) against the
# general build's 0.32 (R80); held a little under today's number.
MIN_MARGIN = 0.35


@lru_cache(maxsize=None)
def _forecast():
    m = SIM.map_model(MAP, learned=True)
    fc = RoundForecast(MAP, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    return fc


@lru_cache(maxsize=None)
def _replay(build):
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(S.load_all()[build], MODE, MAP, real_map=True, learned=True, scenario=scenario, boards=boards)
    return r, boards


@lru_cache(maxsize=None)
def _margins(build):
    _, boards = _replay(build)
    fc = _forecast()
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        out[rnd] = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
    return out


def _a_fork_zone(step, tiers):
    """The stretch of the A fork a plan tower reaches from its `at`."""
    fc = _forecast()
    fork = [p["name"] for p in fc.track.paths].index(A_FORK)
    x, z, _ = fc.track.frac_to_world(*step["at"])
    sight = fc.sight if P.needs_sight(step["kind"]) else None
    return fc.track.zones(x, z, D.profile(step["kind"], tiers).range, sight=sight)[fork], fork


def test_cluster_bombs_stand_on_both_reachable_stretches_of_the_a_fork():
    fc = _forecast()
    plan = S.load_all()[BUILD]["plan"]
    place = {st["id"]: st for st in plan if st.get("do") == "place"}
    zone_a, fork = _a_fork_zone(place["bA"], CLUSTER)
    zone_m, _ = _a_fork_zone(place["bM"], CLUSTER)
    fork_len = fc.track.zones(0, 0, None)[fork].length
    assert zone_a and min(zone_a.entry + zone_a.length, fork_len) - zone_a.entry >= MIN_UPPER_REACH
    assert zone_m and zone_m.entry > fork_len / 2
    assert fork_len - zone_m.entry >= MIN_TAIL_REACH


def test_cluster_bombs_come_before_the_first_apache():
    """In the lost game the plan's cash went to two $21,600 Apache steps from
    round 48; the bombs (about $6k each to Recursive Cluster) come first."""
    order = [(st.get("id"), st.get("to") or st["do"]) for st in S.load_all()[BUILD]["plan"]]
    first_apache = next(i for i, (_, to) in enumerate(order) if to.startswith("4-") and order[i][0].startswith("h"))
    for bomb in ("bA", "bM"):
        assert order.index((bomb, "2-0-4")) < first_apache, bomb


def test_replay_places_the_plan_and_rates_no_worse_than_the_general_build():
    model = SIM.map_model(MAP, learned=True)
    r, _ = _replay(BUILD)
    assert r["gaps"] == [], r["gaps"]
    for st in S.load_all()[BUILD]["plan"]:
        if st.get("do") == "place" and st["kind"] != "hero":
            _, _, fx, fy = r["placed"][st["id"]]
            (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(fx, fy)
            assert math.hypot(px - ax, py - ay) <= S.Executor.AT_SEARCH_CELLS, (st["id"], (fx, fy))
    own, general = _margins(BUILD), _margins(GENERAL)
    worst = min(own, key=own.get)
    assert own[worst] >= MIN_MARGIN, f"round {worst} rated {own[worst]:.2f}"
    assert min(own.values()) >= min(general.values())


def test_general_build_is_kept_off_ravine_double_hp():
    d = S.load_all()[GENERAL]
    assert MAP not in d["planner"]["excluded_maps"]      # its Medium/Hard stay open there
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
