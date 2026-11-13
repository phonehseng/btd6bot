"""Pat's Pond ABR: the map build strategies/maps/patspond_abr.yaml.

Case 20261112_113006_PatsPond_abr (2026-11-12 11:23): abr_ninja_alch, played
from round 3 without Fast Track, lost round 30 to ABR's camo leads - its only
lead answer was one ninja dipped by a 2-0-0 alchemist, and the reinforcement
spent ~$5.5k on sharp-only darts and ninjas before it. That was the seventh
Pat's Pond ABR loss by a general land build (hard_glaive_lord, three
double_hp_sniper_sun, three abr_ninja_alch).

Checked here:
  * the build loads, is bot-ready and plays Pat's Pond ABR with Fast Track;
  * every `at` is legal on the live learned map, in plan order (the old
    patspond_hard alchemist spot (0.756, 0.624) is refused there now);
  * the executor-faithful replay (Double Cash, Fast Track start R22) puts
    every tower on its spot and its worst round rates at least WORST_FLOOR,
    above abr_ninja_alch's own replay of the same map;
  * the general builds that lost there stay off the map in ABR.

The replay takes about a minute per build.
Run: python tests/test_patspond_abr_offline.py"""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O                 # noqa: E402
import simulate_threats as SIM              # noqa: E402
from btd6bot import boosts as B             # noqa: E402
from btd6bot import maplearn                # noqa: E402
from btd6bot import placement as PL         # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP = "Pat's Pond"
MODE = "abr"
BUILD = "patspond_abr"
LOSER = "abr_ninja_alch"
BOOSTS = {"double_cash": True, "fast_track": True}   # the main account's
# 1.26 measured 2026-11-12 (round 40, the first MOABs); held a little under it
# 1.2 until 2026-11-13. Since 93c2d83 (2026-11-12, few blimps are few: a
# zone holds no more than the group sent down it, a projectile's pierce
# counts only the blimps within its reach) round 60 rates 0.88 (1.87
# before; the worst was round 40 at 1.23). The build won live on 2026-11-12
# 16:54 (round 80); the floor is today's worst less a little.
WORST_FLOOR = 0.85
# the live checkout's learned maps (refused spots), when this runs in a worktree
LIVE_MAPS = Path(r"C:/Users/phone/OneDrive/Documents/Projects/btd6bot/data/maps")


@lru_cache(maxsize=None)
def _use_live_maps():
    """Read the live learned map files from a copy (never in place), so the
    refused spots are the ones the game really refuses; this checkout's own
    data/maps when the live one is not there."""
    if not LIVE_MAPS.is_dir() or LIVE_MAPS.resolve() == (ROOT / "data" / "maps").resolve():
        return
    tmp = Path(tempfile.mkdtemp(prefix="pp_abr_maps_"))
    for f in LIVE_MAPS.glob("*.npz"):
        shutil.copy2(f, tmp / f.name)
    maplearn.DATA = tmp
    SIM._MAP_MODELS.clear()


def _strats():
    return S.load_all()


@lru_cache(maxsize=None)
def _replay(build):
    """(simulate result, {round: board}) with the account's Fast Track economy."""
    _use_live_maps()
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(_strats()[build], MODE, MAP, real_map=True, learned=True,
                     scenario=scenario, boards=boards)
    return r, boards


@lru_cache(maxsize=None)
def _margins(build):
    """{round: margin} of the replayed start-of-round boards (live forecast)."""
    _, boards = _replay(build)
    m = SIM.map_model(MAP, learned=True)
    fc = RoundForecast(MAP, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        out[rnd] = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
    return out


def test_build_loads_and_keeps_fast_track():
    s = _strats()[BUILD]
    assert s["bot_ready"], s.get("bot_ready_reasons")
    assert s["modes"] == [MODE] and s["planner"]["maps"] == [MAP]
    assert s.get("plan_first") is True
    # played from the round-22 Fast Track start: the case was played from round 3
    assert B.fast_track_wanted(MODE, s) is True


def test_spots_are_legal_on_the_live_map_in_plan_order():
    _use_live_maps()
    m = SIM.map_model(MAP, learned=True)
    s = _strats()[BUILD]
    placed, bad = [], []
    for st in s["plan"]:
        if st["do"] != "place":
            continue
        hero = s["hero"] if st["kind"] == "hero" else None
        fx, fy = st["at"]
        ok = PL.valid_spots(m, st["kind"], hero, placed, last_round=80)
        cx, cy = m.frac_to_cell(fx, fy)
        if not ok[cy, cx]:
            bad.append((st["id"], st["at"]))
        placed.append((cx, cy, st["kind"], hero))
    assert not bad, bad


def test_replay_holds_above_the_floor_and_beats_the_loser():
    r, boards = _replay(BUILD)
    plan_ids = {st["id"]: st["at"] for st in _strats()[BUILD]["plan"] if st["do"] == "place"}
    last = boards[max(boards)]
    for tid, at in plan_ids.items():
        assert tid in last, (tid, "not placed")
        _, _, fx, fy = last[tid]
        assert abs(fx - at[0]) < 0.01 and abs(fy - at[1]) < 0.01, (tid, (fx, fy), at)
    margins = _margins(BUILD)
    worst = min(margins, key=margins.get)
    assert margins[worst] >= WORST_FLOOR, f"round {worst} rated {margins[worst]:.2f}"
    loser = _margins(LOSER)
    assert margins[worst] > min(loser.values()) + 0.5


def test_losing_general_builds_stay_off_patspond_abr():
    strats = _strats()
    for sid in (LOSER, "double_hp_sniper_sun"):
        assert MAP in strats[sid]["planner"].get("excluded_maps", []), sid
    # hard_glaive_lord no longer plays ABR at all
    assert MODE not in strats["hard_glaive_lord"]["modes"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
