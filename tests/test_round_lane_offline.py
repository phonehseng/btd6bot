"""A purchase for one weak round stands on the path that round's bloons ride.

Muddy Puddles hands its four lanes to the rounds in turn (Path1, 2, 3, 4,
3, 2), so Path1, the left lane, carries one round in six. Loss case
20261112_121231_MuddyPuddles_impoppable (chimps_ninja_sun): from round 10
the model rated round 13 at 0.59. Every tower stood between the middle
lanes, and reinforce placed its "another dart" by the round-share weighting,
which favours the middle lanes: "another dart would move round 13 only 0.59
-> 0.59 - the cash stays for plan step hero". The hero took the $676, and
round 13's blues leaked on the left lane nine seconds in.

Now reinforce.options also offers each kind at the spot best for the weak
round's own track (mapgeom.round_track, Executor._round_lane,
pick_spots' `for_round`).
Run: python tests/test_round_lane_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM                 # noqa: E402
import test_achievement_strats_offline as F    # noqa: E402  (the fakes)
from btd6bot import layout as L                # noqa: E402
from btd6bot import mapgeom as G               # noqa: E402
from btd6bot import reinforce as R             # noqa: E402
from btd6bot import strategy as S              # noqa: E402
from btd6bot.forecast import RoundForecast     # noqa: E402

MAP = "Muddy Puddles"
PLAYFIELD = L.get(1920, 1200)["playfield"]
# the case's board when round 13 started (game.log 12:08:43-12:11:39)
BOARD = [("n1", "ninja", 0.387, 0.172, (2, 0, 1)), ("starter", "sniper", 0.436, 0.291, (0, 0, 0)),
         ("bonus_dart", "dart", 0.623, 0.325, (0, 0, 0)), ("sniper1", "sniper", 0.419, 0.726, (0, 0, 0)),
         ("sniper2", "sniper", 0.452, 0.513, (0, 0, 0)), ("dart1", "dart", 0.526, 0.641, (0, 0, 2)),
         ("ninja1", "ninja", 0.558, 0.658, (0, 0, 0)), ("hero", "hero", 0.478, 0.402, (0, 0, 0))]


def _lane_columns(mask):
    x0, _, x1, _ = PLAYFIELD
    cols = mask.any(axis=0).nonzero()[0]
    return x0 + cols.min() / mask.shape[1] * (x1 - x0), x0 + cols.max() / mask.shape[1] * (x1 - x0)


def test_round_13_rides_the_left_lane_only():
    geom = G.load(MAP)
    proj = G.Projection(PLAYFIELD)
    lane = G.round_track(geom, proj, 13)
    assert lane is not None
    left, right = _lane_columns(lane)
    assert right < 0.45, ("round 13's track reaches the middle lanes", left, right)
    heat, _, _ = G.paint_paths(geom, proj)
    assert lane.sum() < (heat > 0).sum() * 0.4, "one lane of four"
    # round 12 rides Path2, right of Path1
    assert _lane_columns(G.round_track(geom, proj, 12))[1] > right


def test_maps_whose_rounds_use_every_path_give_none():
    proj = G.Projection(PLAYFIELD)
    for name in ("Monkey Meadow", "Spillway", "Sunset Gulch"):
        assert G.round_track(G.load(name), proj, 13) is None, name


def _executor():
    model = SIM.map_model(MAP)
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), model, plan, "impoppable", F.full_account())
    ex.g.towers = {}
    for tid, kind, x, y, tiers in BOARD:
        p = F.Placed(tid, kind, x, y)
        p.tiers = list(tiers)
        p.spent = 0
        ex.g.towers[tid] = p
    ex.now_round = 13
    return ex, model


def test_a_dart_for_round_13_stands_on_its_lane_and_lifts_it():
    ex, model = _executor()
    usual = ex.pick_spots("dart", {"do": "place", "kind": "dart", "role": "dps", "segment": [0.2, 1.0]})
    lane = ex.pick_spots("dart", {"do": "place", "kind": "dart", "role": "dps", "segment": [0.2, 1.0],
                                  "for_round": 13})
    assert usual and lane
    fx, _ = model.cell_to_frac(lane[0][0], lane[0][1])
    assert fx < 0.4, ("the dart for round 13 is not by the left lane", fx)
    fc = RoundForecast(MAP, "impoppable", model.sight,
                       (getattr(model, "sight_height", None), getattr(model, "ground_height", None)))
    board = R.board(ex)
    before = fc.margin(board, 13)
    on_usual = fc.margin(board + [R.new_tower(ex, "_d", "dart", *model.cell_to_frac(*usual[0][:2]))], 13)
    on_lane = fc.margin(board + [R.new_tower(ex, "_d", "dart", *model.cell_to_frac(*lane[0][:2]))], 13)
    assert on_lane > on_usual + 0.1 and on_lane > before + 0.1, (before, on_usual, on_lane)


def test_options_offer_the_lane_placement():
    ex, _ = _executor()
    whats = [o.what for o in R.options(ex, 500, weak=13)]
    assert "another dart for round 13's path" in whats, whats
    assert not any("for round" in w for w in [o.what for o in R.options(ex, 500)]), "no weak round given"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
