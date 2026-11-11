"""Last Resort Medium: the map's own build holds where the general builds
the planner picked did not.

Last Resort had 1 win in 14 games by 2026-11-10. Every route of its 4-round
cycle (big, medium, small loop, straight) runs along the top straight, but
the land near it is scarce: thick snow, the frozen pool and the fence take
most of it, so short-range towers stand on the walkway beside the big loop
and miss three rounds in four. Medium was lost by general builds at round
19 (hard_ninja_alch_sniper, 06:55, lives 150 -> 21 in rounds 15-18) and
round 16 (obyn_druid_poplust, 19:23, 72 s). The map's own build,
strategies/maps/lastresort_medium.yaml, shoots from the left and right
edges with snipers (global range, line of sight over the snow) and held
rounds 15-39 with all 150 lives on 2026-10-27.

Checked here with the executor-faithful replay (simulate_threats.simulate on
the learned map, Fast Track start and Double Cash income as the account
plays Medium), each round's start board rated by the live forecast on all
four routes (the hero is not counted):
  * no threat gaps, every tower on its `at` spot;
  * every round at MIN_MARGIN or more; rounds 15-25 (the Fast Track opening
    that the general builds lost) at EARLY_MARGIN or more. When written:
    worst 1.48 (round 60, a BFB on the straight), 1.65 (round 15), 2.54
    (round 40, the MOAB that ended the 2026-10-27 game);
  * the general build that lost round 19 replays under 1.0 in that opening.
Run: python tests/test_lastresort_builds_offline.py"""
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
from btd6bot import strategy as S           # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

MAP = "Last Resort"
MODE = "medium"
BOOSTS = {"double_cash": True, "fast_track": True}     # the main account's (account.boosts)
BUILD = "lastresort_medium"
GENERAL = "hard_ninja_alch_sniper"                     # lost round 19 on 2026-11-10 06:55
MIN_MARGIN = 1.45       # data/model_ceiling.json records this build's worst (1.48) for Last Resort|medium
EARLY_MARGIN = 1.6      # rounds 15-25
OPENING = range(15, 26)


@lru_cache(maxsize=None)
def _replay(build):
    """(simulate result, {round: board}) on the economy the account plays Medium with."""
    econ = O.economy(MODE, BOOSTS)
    scenario = {"start_round": econ.start_round, "start_cash": econ.start_cash,
                "income_multiplier": econ.cash_mult}
    boards = {}
    r = SIM.simulate(S.load_all()[build], MODE, MAP, real_map=True, learned=True,
                     scenario=scenario, boards=boards)
    return r, boards


@lru_cache(maxsize=None)
def _margins(build):
    """{round: margin} of the replayed boards, rated by the live forecast."""
    m = SIM.map_model(MAP, learned=True)
    fc = RoundForecast(MAP, MODE, m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    _, boards = _replay(build)
    out = {}
    for rnd, board in sorted(boards.items()):
        towers = [SimpleNamespace(tid=t, kind=k, tiers=ti, x=fx, y=fy, placed_round=1)
                  for t, (k, ti, fx, fy) in board.items()]
        out[rnd] = (fc.margins(towers, [rnd]) or {}).get(rnd, 0.0)
    return out


def test_map_build_stands_on_its_spots_without_gaps():
    model = SIM.map_model(MAP, learned=True)
    r, _ = _replay(BUILD)
    assert r["gaps"] == [], r["gaps"]
    for st in S.load_all()[BUILD]["plan"]:
        if st.get("do") == "place" and st["kind"] != "hero" and st.get("at"):
            _, _, fx, fy = r["placed"][st["id"]]
            (ax, ay), (px, py) = model.frac_to_cell(*st["at"]), model.frac_to_cell(fx, fy)
            assert math.hypot(px - ax, py - ay) <= S.Executor.AT_SEARCH_CELLS, (st["id"], (fx, fy))


def test_map_build_holds_every_round():
    margins = _margins(BUILD)
    assert min(margins) == 15 and max(margins) == 60, (min(margins), max(margins))
    low = {r: round(m, 2) for r, m in margins.items() if m < MIN_MARGIN}
    assert not low, low
    early = {r: round(margins[r], 2) for r in OPENING if margins[r] < EARLY_MARGIN}
    assert not early, early


def test_the_losing_general_build_does_not_hold_the_opening():
    """The comparison the planner change rests on (planner._own_builds_first)."""
    margins = _margins(GENERAL)
    assert min(margins[r] for r in OPENING) < 1.0, {r: round(margins[r], 2) for r in OPENING}


if __name__ == "__main__":
    logging.disable(logging.WARNING)
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
