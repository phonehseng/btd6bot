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
# Plan towers the replay no longer stands on their `at`. dA, the A fork's
# druid (0.393, 0.232), stood there in the build's live win (2026-11-12
# 21:52, placed round 73, never sold). Since 96f125a (Executor._at_in_reach)
# a researched spot must reach the track a standing tower of its kind must
# reach before sell_useless sells it: dA's reaches 57 track cells against a
# floor of 61, no cell within AT_SEARCH_CELLS reaches 61, and the search
# relaxes to (0.323, 0.146). The medal is won and not replayed; left for the
# owner to decide between the rule and the spot (re-pin dA, or let a pinned
# spot that won live keep its tower).
OFF_SPOT_SINCE_96F125A = {"dA"}
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
        if st.get("do") == "place" and st["kind"] != "hero" and st["id"] not in OFF_SPOT_SINCE_96F125A:
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


# The plan's towers standing at round 40 in the build's first game
# (2026-11-12 17:19, case 20261112_172416_Ravine_magic_only), exact spots
# from its journal; lost to round 40's one MOAB with both Sticky Bombs bought.
LOST_R40_BOARD = {
    "nL": ("ninja", (2, 0, 4), 0.152, 0.6409), "nA": ("ninja", (2, 0, 4), 0.436, 0.2398),
    "wM": ("wizard", (0, 2, 2), 0.2753, 0.768), "a1": ("alchemist", (2, 0, 0), 0.142, 0.692),
    "wA": ("wizard", (0, 2, 2), 0.532, 0.164), "dC": ("druid", (0, 3, 0), 0.687, 0.283),
}


# What the L wizard must add to round 40's rating on the lost board (0.33
# measured on 2026-11-12 with the damage model of 93c2d83, 0.27 before it).
R40_WIZARD_GAIN = 0.25


def test_round_40_has_the_l_fork_wizard_after_the_sticky_bombs():
    """Round 40 runs down Path1's two forks. In the lost game the board with
    both Sticky Bombs rated 0.80 there (the L fork, Path1-split1, has nL
    alone); the L wizard at 0-2-2 lifted it to 1.07, so it now follows nL's
    Sticky Bomb at once instead of waiting behind wA's Necromancer.

    Since the damage model counts a lone blimp as few (93c2d83, 2026-11-12
    21:30) the same two boards rate 0.61 and 0.94: the wizard is still worth
    a third of the round, which is what is held here (R40_WIZARD_GAIN), but
    the round is no longer rated over 1.0."""
    plan = S.load_all()[BUILD]["plan"]
    order = [(st.get("id"), st.get("to") or st["do"]) for st in plan]
    i = order.index(("nL", "2-0-4"))
    assert order[i + 1:i + 3] == [("wL", "place"), ("wL", "0-2-2")], order[i:i + 4]
    assert order.index(("wL", "0-2-2")) < order.index(("wA", "0-2-4"))
    fc = _forecast()
    wl = next(st for st in plan if st.get("id") == "wL" and st["do"] == "place")

    def r40(board):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        return fc.margins(towers, [40])[40]
    lost = r40(LOST_R40_BOARD)
    now = r40(dict(LOST_R40_BOARD, wL=("wizard", (0, 2, 2), *wl["at"])))
    assert lost < 1.0 and now - lost >= R40_WIZARD_GAIN, (lost, now)


A_FORK = "Path1+Path1-split2"
A_GROUP_END = 178       # units along the A fork where the A group's reach ends (nA, the farthest)
MIN_LOWER_REACH = 60    # units of the A fork below that a plan tower must reach


def test_a_fork_lower_half_is_covered_before_the_supers():
    """Case 20261112_194415_Ravine_magic_only (2026-11-12 19:31, lost round
    60): the BFB and its MOABs were popped beside A, and their ceramics ran
    the A fork's lower half, where only wM reached 35 units; one got out.
    The plan now has a ninja in the middle that reaches that stretch as a
    4-0-2, bought before the first Super Monkey, and no $21,600 Sun Avatar
    stands in the plan ahead of the cheaper druid and ninja steps (in the
    lost game that step blocked the plan from round 52 while $23k went to
    off-plan towers)."""
    fc = _forecast()
    plan = S.load_all()[BUILD]["plan"]
    fork = [p["name"] for p in fc.track.paths].index(A_FORK)

    def lower_reach(step, tiers):
        x, z, _ = fc.track.frac_to_world(*step["at"])
        sight = fc.sight if P.needs_sight(step["kind"]) else None
        zone = fc.track.zones(x, z, D.profile(step["kind"], tiers).range, sight=sight)[fork]
        if not zone:
            return 0.0
        return max(0.0, zone.entry + zone.length - max(A_GROUP_END, zone.entry))

    order = [(st.get("id"), st.get("to") or st["do"]) for st in plan]
    nm = next(st for st in plan if st.get("id") == "nM" and st["do"] == "place")
    assert lower_reach(nm, (4, 0, 2)) >= MIN_LOWER_REACH, lower_reach(nm, (4, 0, 2))
    first_super = next(i for i, st in enumerate(plan) if st.get("kind") == "super")
    assert order.index(("nM", "4-0-2")) < first_super
    first_avatar = next(i for i, (_, to) in enumerate(order) if to == "3-0-2")
    for step in (("dC", "0-3-1"), ("nL2", "4-0-2"), ("dA", "0-3-1")):
        assert order.index(step) < first_avatar, step


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
