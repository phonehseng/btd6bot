"""Ravine Magic Monkeys Only: the map build places beside every fork and
rates better than the general build that lost the medal there.

Case 20261112_113751_Ravine_magic_only (2026-11-12 11:31, lost round 38):
magic_obyn_ninja_wizard lost Ravine Magic Only for the fifth time at rounds
38-40. A Ravine round runs down one entrance and both of its forks at once
(Path1 on even rounds, Path2 on odd); the general build's towers stood by
one fork of each entrance, and the replay rates its rounds 40, 60 and 80 at
the model's 0.06 floor. strategies/maps/ravine_magic_only.yaml puts camo,
lead and MOAB damage beside each fork.

Checked with the executor-faithful replay (simulate_threats.simulate on the
learned map, the account's Fast Track + Double Cash economy), each round's
start board rated by the live forecast (sight and heights), as
tests/test_floodedvalley_builds_offline.py does.
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
MODE = "magic_only"
BUILD = "ravine_magic_only"
GENERAL = "magic_obyn_ninja_wizard"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
# The map build's worst round on 2026-11-12 was 0.25 (R80) against the
# general build's 0.06 floor; held a little under today's number.
MIN_MARGIN = 0.2
MAGIC = {"ninja", "wizard", "alchemist", "druid", "super", "mermonkey", "hero"}
MIN_REACH = 40          # units of track each tower reaches from its `at`, sight counted


@lru_cache(maxsize=None)
def _replay(build):
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
    _, boards = _replay(build)
    fc = _forecast()
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        out[rnd] = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
    return out


def test_only_magic_towers():
    strat = S.load_all()[BUILD]
    kinds = {st["kind"] for st in strat["plan"] if st.get("do") == "place"}
    assert kinds <= MAGIC, kinds - MAGIC


def test_every_fork_has_a_tower_beside_it():
    """Each of the four forks (Track routes) is reached by at least two of
    the build's towers from their `at`, sight counted."""
    fc = _forecast()
    plan = S.load_all()[BUILD]["plan"]
    reach = [0] * len(fc.track.paths)
    for st in plan:
        if st.get("do") != "place" or st["kind"] == "hero":
            continue
        tiers = max((tuple(int(t) for t in u["to"].split("-")) for u in plan
                     if u.get("do") == "upgrade" and u["id"] == st["id"]), default=(0, 0, 0))
        x, z, _ = fc.track.frac_to_world(*st["at"])
        sight = fc.sight if P.needs_sight(st["kind"]) else None
        zones = fc.track.zones(x, z, D.profile(st["kind"], tiers).range, sight=sight)
        for i, zz in enumerate(zones):
            if zz and zz.length >= MIN_REACH:
                reach[i] += 1
    assert min(reach) >= 2, list(zip((p["name"] for p in fc.track.paths), reach))


def test_build_holds_better_than_the_general_build():
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
    assert min(general.values()) < 0.1
    assert min(own.values()) > 2 * min(general.values())
    # the rounds the last game was lost on
    for rnd in (36, 38, 40):
        assert own[rnd] > general[rnd], (rnd, own[rnd], general[rnd])


def test_general_build_is_kept_off_ravine_magic_only():
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
