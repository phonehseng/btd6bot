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

ABR (strategies/maps/glacialtrail_abr.yaml) is its own build: all three
ABR games were lost on round 31 (2026-11-09 03:24 and 21:22, 2026-11-10
11:17), each with a Fast Track opening bought at round 22 and frozen
together in rounds 30-32. ABR starts at round 22 with about $9,000 and
brings camo leads (24, 30) before the first MOAB (40), which the Medium
build cannot meet: it replays to 0.13 (round 40) on ABR. The live Floor2
spike was refused (Medium, 2026-11-10 07:26), so the ABR build keeps one
spike (sp1, Floor4) and puts its weight on two helis, a Spectre ace and
two druids, placed in four phases: h1 at round 22 (frozen rounds 0-2 mod
10), h2 and dr1 at 25 (3-5), sp1 at 26 (4-6: awake for the MOAB rounds
40, 43 and 47), dr2 and a1 at 28-38 (6-8). When written ABR worst 2.35
(R31), then R35 2.40, R58 2.57, R22 2.59.

Apopalypse (strategies/maps/glacialtrail_apopalypse.yaml) is rated with
tools/apopalypse_check.py instead (random rounds, sent back to back, on a
poor game's income), which leaves each round's frozen towers out the same
way (apopalypse_check.frozen_boards). apopalypse_apache_spikes lost there
on round 33 (2026-11-10 20:12) after its whole round-15 opening froze in
rounds 24-25; the check rates it 0.06 at round 24. The map build places
helis at 15 and 18, the spike at 21 and rushes it to Spiked Mines, a third
heli and a druid after: when written worst 0.97 at round 33 (every tower
awake: the cash, not the freeze), then R59 1.11, R41 1.16. Apopalypse has
no fixed first MOAB round (its MOAB groups come from 41), so the round-40
check is not asked of it.
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

import apopalypse_check as AC               # noqa: E402
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
GENERAL_APOPALYPSE = "apopalypse_apache_spikes"        # lost Apopalypse at R33 on 2026-11-10
APOPALYPSE = "apopalypse"
APOP_SAMPLES = 6                                       # random windows per round (the constructed ones decide here)
# build -> [(mode, the worst round rating allowed)]
# 2026-11-10: a druid's vine now grabs one bloon, not a 4-unit blast of a
# packed group (tests/test_druid_vine_one_bloon_offline.py); the two
# druids count for less and Medium's worst is R36 1.37, Reverse's R36 1.34
# (Easy R27 2.48). The floors hold those numbers.
BUILDS = {
    "glacialtrail_medium": [("easy", 2.0), ("medium", 1.3), ("reverse", 1.3)],
    "glacialtrail_abr": [("abr", 1.6)],     # 1.70 at R34 once the druid vine takes one bloon a grab (2026-11-10)
    # 0.97 at R33 when written (2026-11-10): every tower awake, the spike at
    # 3-0-0 with its $9,500 Spiked Mines tier bought during that round - a
    # poor game's cash by round 33 ($23.3k) pays two 3-2-0 helis and a 3-0-0
    # spike, not more. 2.0 and even 1.0 are out of reach on that cash, so
    # the floor is the measured worst less a little.
    "glacialtrail_apopalypse": [(APOPALYPSE, 0.95)],
}
# build -> its spike factories (ABR: Floor4 only - the game refused a spike on Floor2)
SPIKES = {"glacialtrail_medium": ("sp1", "sp2"), "glacialtrail_abr": ("sp1",), "glacialtrail_apopalypse": ("sp1",)}
MOAB_ANSWER = "sp1"


@lru_cache(maxsize=None)
def _replay(build, mode):
    """(simulate result, {round: board}) on the economy the account plays `mode` with
    (Apopalypse: apopalypse_check.boards, a poor game's income)."""
    if mode == APOPALYPSE:
        boards, r = AC.boards(S.load_all()[build], MAP)
        return r, boards
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
    placement round (the worse of the board's first round and the one before).
    Apopalypse: the worst of apopalypse_check's windows for each round."""
    _, boards = _replay(build, mode)
    if mode == APOPALYPSE:
        return {c.rnd: c.margin for c in AC.check_boards(MAP, boards, samples=APOP_SAMPLES)}
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
        for tid in SPIKES[build]:
            x, z, _ = fc.track.frac_to_world(*steps[tid]["at"])
            sight = fc.sight if P.needs_sight("spike") else None
            zones = fc.track.zones(x, z, D.profile("spike", (4, 2, 0)).range, sight=sight)
            assert sum(zz.length for zz in zones if zz) >= 60, (build, tid)


def test_moab_answer_is_awake_in_round_40():
    for build, modes in BUILDS.items():
        for mode, _ in modes:
            if mode == APOPALYPSE:
                continue        # random rounds: no fixed first MOAB (see the docstring)
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
            last = [st for st in strat["plan"] if not st.get("modes") or mode in st["modes"]][-1]
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


def test_apopalypse_build_beats_the_general_build():
    general = _margins(GENERAL_APOPALYPSE, APOPALYPSE)
    own = _margins("glacialtrail_apopalypse", APOPALYPSE)
    assert min(general.values()) < 0.5        # 0.06 at R24 when written: its opening frozen together
    assert min(own.values()) > 4 * min(general.values())


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
