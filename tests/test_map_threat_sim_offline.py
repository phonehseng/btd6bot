"""Offline test: every map strategy passes the threat simulation.

For each strategies/maps/*.yaml build and each mode it lists, the offline
threat simulation (tools/simulate_threats.py: real prices, the game's base
income, no Double Cash) must find no round that brings a bloon the defence
cannot pop. A Deflation-family build must also buy its whole plan from the
starting cash.

Why this is its own file, split into shards: the simulation runs the live
strategy's tick with the damage model, and since the Impoppable map builds
(2026-11-13) one Impoppable game takes up to four minutes to simulate
(Bloonarius Prime: 233 s, measured 2026-11-13 17:20, almost all of it in
dps_model._play). Inside tests/test_map_hints_offline.py the whole loop ran
for over an hour, so no caretaker run could finish tools/check.py and six
fixes waited on branches. tools/check.py now runs this file as several
shards side by side (`--shard k/n`); each shard simulates every n-th game.

Run: python tests/test_map_threat_sim_offline.py [--shard k/n]
(no argument = every game, one after another). Never touches the game.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

# the map-hints test module sets up the paths and logging and reads the builds
import test_map_hints_offline as MH  # noqa: E402

S, SIM = MH.S, MH.SIM

# Builds whose won medal lets their plan end short in the simulation:
# darkpath_easy (Dark Path Easy won): since an upgrade step keeps tiers a
# threat answer bought on another path (Executor._widened, 2026-11-11) its
# m1/de1 steps run where they used to be skipped, and the plan is 40/42 at R40.
# lastresort_primary_only (case 20261112_111354_LastResort_primary_only): its
# last tiers are a 5-2-0 desperado ($21k), round 40's MOAB answer on the
# straight, which only the account's Double Cash pays by round 39; at base
# income the plan is 11/14 at R40 with no threat gap (tests/
# test_lastresort_primary_offline.py replays it on the account's economy).
PLAN_SHORT_OK = {"darkpath_easy", "lastresort_primary_only"}


def games():
    """[(strategy id, strategy, mode)] in shard order: the slowest games first
    (Impoppable, then the longest games), so that dealing them out in turn
    spreads the slow ones over the shards instead of piling them on one."""
    out = [(sid, s, mode) for sid, s in MH.map_strategies().items() for mode in s["modes"]]
    out.sort(key=lambda g: (g[2] != "impoppable", -S.MODE_RULES[g[2]]["end_round"], g[0], g[2]))
    return out


def shard_games(k=1, n=1):
    """The games of shard k (1-based) of n: every n-th game from the k-th."""
    return games()[k - 1::n]


def check_game(sid, s, mode):
    """Simulate one build in one mode and assert it leaves no threat open."""
    r = SIM.simulate(dict(s, bot_ready=True), mode)
    assert not r["gaps"], (sid, mode, r["gaps"][:3])
    done, total = (int(x) for x in r["plan_done"].split("/"))
    if S.MODE_FAMILY[mode] == "easy" and sid not in PLAN_SHORT_OK:
        # Deflation: everything is bought with the starting cash
        assert done == total or (done == total - 1 and s["plan"][-1].get("kind") == "hero"), \
            (sid, mode, r["plan_done"])


def test_shards_cover_every_game_once():
    """Dealing the games out over any number of shards keeps each exactly once."""
    every = [(sid, mode) for sid, _, mode in games()]
    for n in (1, 5, 12):
        dealt = [(sid, mode) for k in range(1, n + 1) for sid, _, mode in shard_games(k, n)]
        assert sorted(dealt) == sorted(every), n


def test_map_strategies_pass_the_threat_simulation(k=1, n=1):
    """No round brings a bloon the defence cannot pop, in every listed mode."""
    for sid, s, mode in shard_games(k, n):
        check_game(sid, s, mode)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default="1/1", help="k/n: run the k-th of n shards")
    k, n = (int(x) for x in ap.parse_args().shard.split("/"))
    fails = 0
    test_shards_cover_every_game_once()
    for sid, s, mode in shard_games(k, n):
        try:
            check_game(sid, s, mode)
            print("ok  ", sid, mode, flush=True)
        except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
            fails += 1
            print("FAIL", sid, mode, repr(e)[:600], flush=True)
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
