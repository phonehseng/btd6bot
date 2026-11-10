"""Glacial Trail map builds: the only two patches of ground beside the track
hold Spiked Mines, everything else pops from anywhere, and the towers are
bought in groups that never freeze together.

Glacial Trail was lost by every general build that played it: Medium at
round 25 (primary_glaive_dart, 2026-11-03), 16 (hard_ninja_alch_sun,
2026-11-05), 25 (hard_ninja_alch_sniper, 2026-11-07) and 40 (primary_core,
2026-11-09 19:20, loss case 20261109_1920*), Easy at 22 and 29, ABR at 31.
Two things beat them:
  * ground: towers fit beside the track only on Floor2 (by the first loop)
    and Floor4 (by the second), one tower each; the snowfield, the loops and
    the ice walls are unplaceable, and from the ice floes and the hills the
    ice walls hide the track from towers that need line of sight;
  * the freeze: every tower but the Ice Monkey sits in ice for two rounds in
    ten counted from its placement round (dps_model.frozen_in), so a Fast
    Track opening bought in one round freezes all at once.
The map build strategies/maps/glacialtrail_medium.yaml (Medium, Reverse) puts a Spike Factory
(no sight needed, grown to Spiked Mines) on each patch, two Druids of the
Jungle (vines reach the whole track from anywhere) on accepted spots of the
ice floe and the right hill, and a heli (global) on the hill, bought in
rounds apart.

Checked here with the executor-faithful replay (simulate_threats.simulate on
the learned map, Fast Track start and Double Cash income as the account plays
each mode), each round's start board rated by the live forecast with the
towers frozen by their placement round (RoundForecast.margins; the placement
round is taken as the board's first round and the one before it, the worse
of the two counts; the hero is not counted):
  * each spike reaches 60+ units of hittable track from its `at` spot (when
    written: Floor4 109, Floor2 73 of 856, range 34);
  * the round-40 MOAB answer (sp1, Spiked Mines) is awake in round 40;
  * no threat gaps, every tower on its `at` spot, nothing off the plan while
    plan steps are left, every round at the build's MIN_MARGIN or more:
    when written Medium worst 2.23 (R43), Reverse 2.23 (R43); the general build that lost Medium replays to 0.06 at rounds 24,
    33, 45 and 53 (its whole board frozen at once), even with the replay
    accepting its spots inside the walls.
Run: python tests/test_glacialtrail_builds_offline.py"""
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
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP = "Glacial Trail"
FIRST_MOAB = {t: r for r, t in S.THREATS}["moab"]      # round 40
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
GENERAL = "primary_core"                               # lost Medium at R40 on 2026-11-09
# build -> [(mode, the worst round rating allowed)]
# 2026-11-10: a druid's vine now grabs one bloon, not a 4-unit blast of a
# packed group (tests/test_druid_vine_one_bloon_offline.py); the two
# druids count for less and Medium's worst is R36 1.37, Reverse's R36 1.34
# (Easy R27 2.48). The floors hold those numbers.
BUILDS = {
    "glacialtrail_medium": [("easy", 2.0), ("medium", 1.3), ("reverse", 1.3)],
}
SPIKES = ("sp1", "sp2")
MOAB_ANSWER = "sp1"


@lru_cache(maxsize=None)
def _replay(build, mode):
    """(simulate result, {round: board}) on the economy the account plays `mode` with."""
    econ = O.economy(mode, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(S.load_all()[build], mode, MAP, real_map=True, learned=True, scenario=scenario, boards=boards)
    return r, boards


@lru_cache(maxsize=None)
def _forecast(mode):
    """The live forecast for the map: the learned map's sight grid and heights."""
    m = SIM.map_model(MAP, learned=True)
    fc = RoundForecast(MAP, mode, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    return fc


def _first_rounds(boards):
    first = {}
    for rnd in sorted(boards):
        for tid in boards[rnd]:
            first.setdefault(tid, rnd)
    return first


def _margins(build, mode):
    """{round: margin} of the replayed boards, each tower frozen by its
    placement round (the worse of the board's first round and the one before)."""
    _, boards = _replay(build, mode)
    first = _first_rounds(boards)
    fc = _forecast(mode)
    out = {}
    for shift in (0, 1):
        for rnd, board in sorted(boards.items()):
            towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=first[t] - shift)
                      for t, (k, ti, fx, fy) in board.items()]
            got = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
            out[rnd] = min(out.get(rnd, math.inf), got)
    return out


def test_spikes_reach_the_track_from_their_spots():
    fc = _forecast("medium")
    for build in BUILDS:
        steps = {st["id"]: st for st in S.load_all()[build]["plan"] if st.get("do") == "place"}
        for tid in SPIKES:
            x, z, _ = fc.track.frac_to_world(*steps[tid]["at"])
            sight = fc.sight if P.needs_sight("spike") else None
            zones = fc.track.zones(x, z, D.profile("spike", (4, 2, 0)).range, sight=sight)
            assert sum(zz.length for zz in zones if zz) >= 60, (build, tid)


def test_moab_answer_is_awake_in_round_40():
    for build, modes in BUILDS.items():
        for mode, _ in modes:
            _, boards = _replay(build, mode)
            first = _first_rounds(boards)[MOAB_ANSWER]
            kind, tiers, _, _ = boards[FIRST_MOAB][MOAB_ANSWER]
            assert kind == "spike" and tiers[0] >= 4, (build, mode, tiers)
            for placed in (first, first - 1):
                assert not D.frozen_in(MAP, placed, FIRST_MOAB), (build, mode, placed)


def test_map_builds_hold_every_round():
    model = SIM.map_model(MAP, learned=True)
    for build, modes in BUILDS.items():
        strat = S.load_all()[build]
        for mode, min_margin in modes:
            r, boards = _replay(build, mode)
            assert r["gaps"] == [], (build, mode, r["gaps"])
            last = strat["plan"][-1]
            done = min((rnd for rnd, b in boards.items()
                        if b.get(last["id"], (None, None))[1] == tuple(int(t) for t in last["to"].split("-"))),
                       default=math.inf)
            early = [(rnd, what) for rnd, what in r["answers"] + r["surplus"] if rnd < done - 1]
            assert early == [], (build, mode, early)
            for st in strat["plan"]:
                if st.get("modes") and mode not in st["modes"]:
                    continue            # a step for other modes (dr0: Easy only)
                if st.get("do") == "place" and st["kind"] != "hero":
                    _, _, fx, fy = r["placed"][st["id"]]
                    (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(fx, fy)
                    assert math.hypot(px - ax, py - ay) <= S.Executor.AT_SEARCH_CELLS, (build, st["id"], (fx, fy))
            margins = _margins(build, mode)
            econ = O.economy(mode, BOOSTS)
            assert min(margins) <= econ.start_round and max(margins) >= econ.end_round, (build, sorted(margins))
            worst = min(margins, key=margins.get)
            assert margins[worst] >= min_margin, f"{build} {mode}: round {worst} rated {margins[worst]:.2f}"


def test_medium_build_beats_the_general_build():
    general = _margins(GENERAL, "medium")
    own = _margins("glacialtrail_medium", "medium")
    assert min(general.values()) < 0.5
    assert min(own.values()) > 4 * min(general.values())


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
