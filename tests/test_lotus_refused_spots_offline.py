"""The executor-faithful replay sees the spots the live game refused.

Lotus Island CHIMPS (2026-11-05 16:53-17:12, loss case
20261105_171203) was lost at round 95. Its replay had bought every plan
step and rated round 95 at 2.5; live, the damage model rated it 0.38-0.47
from round 88 on. The cash was not the gap: the journal's income over rounds
7-93 ($141,018) matches the replay's ($141,322, pops plus the end-of-round
bonus, which CHIMPS still pays), and the live game bought the Carrier
Flagship at round 82 like the replay. The gap was where the towers stood:
the game refused the build's spots for b1, the MIB village, the alchemist
and b3 (logs/bot.log "refused the click"), the village went to the north
end of the map and b3 after it, and the carriers fought round 95's camo
lead DDTs without the MIB.

simulate_threats.CashGame used to accept every spot. Given the map's
learned refusals (map_model(learned=True)) it now refuses the same clicks,
so the replay puts the towers where the live executor does. Checked here
with the refusals that game logged:
  * the 2026-11-05 build replays to round 95 at 2.0+ without them, and
    under 1.0 with them, its village far from its spot (the live gap);
  * the repaired build (strategies/maps/lotusisland_chimps.yaml) keeps
    every tower on its spot and round 95 at 2.0+ with them (gap closed);
  * CashGame tries the next spot after a refused one, as Game.place does.
Run: python tests/test_lotus_refused_spots_offline.py"""
import base64
import copy
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import dps_model as D          # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot import threats as TH           # noqa: E402
import optimize_builds as O                 # noqa: E402
import simulate_threats as SIM              # noqa: E402

MAP, MODE, STRATEGY = "Lotus Island", "chimps", "lotusisland_chimps"
LOST_ROUND = 95
SAFE = O.SAFETY_MARGIN
# The map's learned refused layers as that game left them (data/maps/
# lotusisland.npz, written 17:11:50): the refusals of earlier Lotus Island
# games plus the four spots this one was refused.
REFUSED = ROOT / "tests" / "fixtures" / "lotusisland_refused_20261105.json"
# The spots of the build that was played (commit 5e7180f) where the repair moved them.
PLAYED_SPOTS = {"b1": [0.43, 0.743], "v1": [0.505, 0.811], "a1": [0.452, 0.845]}


def _with_spots(strat, spots):
    """A copy of the build with these `at` spots, in the plan and its answers."""
    out = copy.deepcopy(strat)
    for _, st in S._all_steps(out):
        if st.get("do") == "place" and st.get("id") in spots:
            st["at"] = list(spots[st["id"]])
    return out


def _refused_layers():
    """{surface: bool grid} from the fixture (np.packbits, row-major)."""
    d = json.loads(REFUSED.read_text(encoding="utf-8"))
    n = d["shape"][0] * d["shape"][1]
    return {sf: np.unpackbits(np.frombuffer(base64.b64decode(d[sf]), np.uint8))[:n].astype(bool).reshape(d["shape"])
            for sf in ("land", "water")}


def _learned_model(refused):
    """The map's geometry model with these refused layers ({} for none),
    installed as simulate_threats' learned model for the map."""
    m = copy.deepcopy(SIM.map_model(MAP))
    m.refused = {sf: grid.copy() for sf, grid in refused.items()}
    SIM._MAP_MODELS[(MAP, True)] = m
    return m


def _replay(strat, refused):
    """simulate(real_map, learned) with these refusals: (result, round-95
    margin of the towers where they stand)."""
    _learned_model(refused)
    try:
        r = SIM.simulate(strat, MODE, MAP, real_map=True, learned=True)
    finally:
        SIM._MAP_MODELS.pop((MAP, True), None)
    setup = O.MapSetup(MAP, MODE)
    towers = []
    for tid, (kind, tiers, fx, fy) in r["placed"].items():
        if kind == "hero":
            continue
        x, z, h = setup.track.frac_to_world(fx, fy)
        spot = O.Spot(cell=tuple(setup.model.frac_to_cell(fx, fy)), x=x, z=z, h=h, fx=fx, fy=fy, score=0)
        towers.append(O.Tower(tid, kind, spot, tuple(tiers)))
    st = O.Evaluator(setup, MODE).stations(towers)
    return r, D.round_margin(st, MODE, LOST_ROUND, setup.track)


def _cells_off(strat, r, tid):
    """How far (cells) tower tid stands from its `at` spot."""
    m = SIM.map_model(MAP)
    at = next(st["at"] for st in strat["plan"] if st.get("id") == tid and st.get("do") == "place")
    _, _, fx, fy = r["placed"][tid]
    (ax, ay), (px, py) = m.frac_to_cell(*at), m.frac_to_cell(fx, fy)
    return math.hypot(px - ax, py - ay)


def test_played_build_holds_only_on_spots_the_game_accepts():
    played = _with_spots(S.load_all()[STRATEGY], PLAYED_SPOTS)
    r, ok = _replay(played, {})
    assert r["plan_done"].split("/")[0] == r["plan_done"].split("/")[1], r["plan_done"]
    assert ok >= SAFE, f"the replay the build was gated with: round {LOST_ROUND} at {ok:.2f}"
    r, live = _replay(played, _refused_layers())
    assert _cells_off(played, r, "v1") > S.Executor.AT_SEARCH_CELLS, "the village was moved away"
    assert live < 1.0, f"with the live refusals round {LOST_ROUND} rates {live:.2f}, as live (0.38-0.47)"


def test_repaired_build_keeps_its_spots_and_round_95():
    strat = S.load_all()[STRATEGY]
    r, margin = _replay(strat, _refused_layers())
    for st in strat["plan"]:
        if st.get("do") == "place" and st["kind"] != "hero":
            assert _cells_off(strat, r, st["id"]) <= S.Executor.AT_SEARCH_CELLS, st["id"]
    assert margin >= SAFE, f"round {LOST_ROUND} at {margin:.2f}"


def test_cash_game_tries_the_next_spot_after_a_refused_one():
    m = _learned_model(_refused_layers())
    SIM._MAP_MODELS.pop((MAP, True), None)
    g = SIM.CashGame(S.PRICE_FAMILY[MODE], "admiral_brickell", m)
    g.cash = 10_000
    refused, free = m.cell_to_frac(94, 90), (0.409, 0.675)   # b2, never refused
    p = g.place("v1", "village", *refused, more_spots=[m.cell_to_frac(50, 80)])
    assert p is not None and (p.x, p.y) == m.cell_to_frac(50, 80)
    assert g.refused_spots == [refused] and g.click_refusals == 1
    assert g.place("b9", "buccaneer", *free) is not None, "a spot the game never refused is taken"
    assert g.place("v2", "village", *refused) is None and g.fail_reason == "spot"


def test_chimps_income_is_pops_plus_round_bonus():
    # The journal of that game: cash at each round start plus every purchase
    # between, rounds 7-93, is what the game paid.
    paid_live = 141_018
    model = sum(TH.round_cash(TH.set_for_mode(MODE), r) for r in range(7, 94))
    pops_only = sum(json.loads((ROOT / "data" / "rounds.json").read_text())["standard"][str(r)]["cash_pop"]
                    for r in range(7, 94))
    assert abs(model - paid_live) < abs(pops_only - paid_live), "CHIMPS still pays the round bonus"
    assert abs(model - paid_live) / paid_live < 0.01, (model, paid_live)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
