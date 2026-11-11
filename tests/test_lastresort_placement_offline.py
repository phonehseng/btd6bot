"""Last Resort: short-range towers must stand where every round's bloons pass.

Last Resort sends each round down one of four routes in a 4-round cycle
(the map file's AlternateRoundSplitter, roundsPerPath 0 = the next path
every round): the big loop, the medium loop, the small loop and the
straight. All four enter along the top straight and leave along it; three
of them loop down the map in between. Placement used to value every track
cell alike, and the big loop's long bottom row (a quarter of the rounds)
outweighed the top straight (every round), so the first short-range towers
went to the walkway beside the big loop's bottom row, y 0.60-0.68:
  * Medium, 2026-11-10 06:55 (hard_ninja_alch_sniper, case
    20261110_065908_LastResort_medium): opener, n1, hero, n2 and a1 at y
    0.60-0.68; Fast Track start at round 15 (small loop), round 16
    (straight) and 18 (medium loop) leaked, lives 150 -> 21, lost round 19;
  * Medium, 2026-11-10 19:23 (obyn_druid_poplust): lost round 16 in 72 s.
The fix (mapgeom.round_share, MapModel.track_weight) values each track cell
by the share of rounds that pass it, so the top straight counts four times
a loop cell. Checked here on the map's own geometry (no learned refusals,
so the result does not depend on this machine's games).
Run: python tests/test_lastresort_placement_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM                 # noqa: E402
import test_achievement_strats_offline as F    # noqa: E402  (the fakes)
from btd6bot import dps_model as D             # noqa: E402
from btd6bot import mapgeom as G               # noqa: E402
from btd6bot import strategy as S              # noqa: E402
from btd6bot.forecast import RoundForecast     # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

MAP = "Last Resort"
# screen fractions (1920x1200 window) read off the loss stills (end_026.jpg)
TOP_STRAIGHT = (0.30, 0.115)     # every route passes here, twice on the big loop
BIG_LOOP_BOTTOM = (0.40, 0.765)  # only the big-loop rounds (1, 5, 9, ...)


def _names(geom):
    return {p["id"]: p["name"] for p in geom["paths"]}


def test_round_shares_from_the_splitter():
    geom = G.load(MAP)
    shares = {_names(geom)[p]: s for p, s in G.path_round_shares(geom).items()}
    assert shares == {"Path1": 0.25, "Path2": 0.25, "Path3": 0.25, "Path4": 0.25}, shares
    # Muddy Puddles hands its paths 1, 2, 3, 4, 3, 2: Path2 and Path3 get two turns of six
    mp = G.load("Muddy Puddles")
    mp_shares = {_names(mp)[p]: round(s, 3) for p, s in G.path_round_shares(mp).items()}
    assert mp_shares == {"Path1": 0.167, "Path2": 0.333, "Path3": 0.333, "Path4": 0.167}, mp_shares
    # Erosion's 18-round phases are idle_phase_paths' business, not a share
    assert G.path_round_shares(G.load("Erosion")) == {}


def test_top_straight_counts_four_times_a_loop_cell():
    model = SIM.map_model(MAP)
    weight = model.track_weight()
    top = model.frac_to_cell(*TOP_STRAIGHT)
    loop = model.frac_to_cell(*BIG_LOOP_BOTTOM)
    assert weight[top[1], top[0]] == 1.0, weight[top[1], top[0]]
    assert weight[loop[1], loop[0]] == 0.25, weight[loop[1], loop[0]]
    # a map whose one route carries every round keeps the plain track
    plain = SIM.map_model("Monkey Meadow")
    assert plain.round_share() is None


def _routes_reached(fx, fy, kind="ninja"):
    """Units of each route (big, medium, small loop, straight) a `kind`
    tower at (fx, fy) reaches, line of sight counted."""
    model = SIM.map_model(MAP)
    fc = RoundForecast(MAP, "medium", model.sight,
                       (getattr(model, "sight_height", None), getattr(model, "ground_height", None)))
    assert fc._ready()
    x, z, _ = fc.track.frac_to_world(fx, fy)
    zones = fc.track.zones(x, z, D.profile(kind, (0, 0, 0)).range, sight=fc.sight)
    return [zz.length if zz else 0.0 for zz in zones]


def _first_spot(model, kind="ninja"):
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), model, plan, "medium", F.full_account())
    ex.__dict__["_probed"] = {(kind, -1, -1)}      # no probe of blocked ground (the game refused them)
    spots = ex.pick_spots(kind, {"do": "place", "id": "n1", "kind": kind, "role": "dps"}, n=1)
    assert spots
    return model.cell_to_frac(spots[0][0], spots[0][1])


def test_first_ninja_reaches_every_route():
    model = SIM.map_model(MAP)
    fx, fy = _first_spot(model)
    reach = _routes_reached(fx, fy)
    assert len(reach) == 4, reach
    assert min(reach) > 0, ("a route the first ninja never sees", (fx, fy), reach)
    # what the old weighting chose: the big loop's walkway, which sees only
    # the big loop (the loss games' n1 stood at 0.628,0.675)
    saved = MapModel.round_share
    MapModel.round_share = lambda self: None
    try:
        old = _first_spot(SIM.map_model(MAP))
    finally:
        MapModel.round_share = saved
    assert min(_routes_reached(*old)) == 0.0, (old, _routes_reached(*old))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
