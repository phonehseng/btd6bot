"""Map mechanics (removable obstacles, map events, moving ground, hidden
track) read from the game files and how placement uses them - no game needed.

Two kinds of checks:
  * synthetic maps built here, so the rules are tested even without data;
  * the extracted maps in data/map_geometry (skipped when absent).
Run: python tests/test_map_mechanics_offline.py"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import gamefiles, mapfit, mapgeom, placement  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]


# ---------------------------------------------------------------------------
# Synthetic maps
# ---------------------------------------------------------------------------

def _square(x0, z0, x1, z1, h=0.0):
    return [[x0, z0, h], [x1, z0, h], [x1, z1, h], [x0, z1, h]]


def _area(aid, kind, poly, **extra):
    return {"id": aid, "name": f"A{aid}", "type": kind, "blocks_sight": False, "disabled": False,
            "tower_sizes": "", "polygons": [poly], "circles": [], **extra}


def _cells(proj, x, z, h=0.0):
    c = proj.to_cells([[x, z, h]])[0]
    return int(c[1]), int(c[0])      # (row, col)


def _synthetic():
    """A water map with two land areas, and on them: a pane cycling every
    round (B), an ice shelf melting after round 18 (C), an obstacle to buy
    (D) whose sale floods a pond (E), a click-only event, and a gear (G)
    turning 90 degrees after each round."""
    areas = [
        _area(9, "land", _square(-150, -100, 150, 30)),
        _area(10, "land", _square(30, 30, 80, 80)),
        _area(1, "track", _square(-150, -5, 150, 5)),
        _area(2, "unplaceable", _square(40, 40, 70, 70), disabled=True),           # B: pane
        _area(3, "land", _square(-100, 40, -60, 80, 10.0)),                         # C: ice shelf
        _area(4, "unplaceable", _square(-100, 40, -60, 80, 9.0)),                   # under C
        _area(5, "unplaceable", _square(80, -80, 120, -40)),                        # D: obstacle
        _area(6, "water", _square(80, -80, 120, -40), disabled=True),               # E: flooded later
        _area(7, "land", _square(-40, -90, 20, -30), pivot=[-10.0, -60.0, 0.0]),   # G: gear
        _area(8, "unplaceable", _square(0, 60, 30, 90), disabled=True),             # click-only
    ]
    events = [
        {"id": 100, "kind": "event", "name": "panes", "one_time": False, "all_triggers": False, "active": True,
         "triggers": [{"type": "AfterRoundTrigger", "round": 0, "everyNthRound": 1}],
         "actions": [{"type": "CycleAreasAction", "areas": [2], "invert": 1, "roundsPerRotate": 1}]},
        {"id": 101, "kind": "event", "name": "melt", "one_time": True, "all_triggers": False, "active": True,
         "triggers": [{"type": "AfterRoundTrigger", "round": 18, "everyNthRound": 0}],
         "actions": [{"type": "DestroyAreaAction", "area": 3}, {"type": "DestroyAreaAction", "area": 4}]},
        {"id": 102, "kind": "event", "name": "flood", "one_time": True, "all_triggers": False, "active": True,
         "triggers": [{"type": "RemoveableSoldTrigger", "removeable": 50}],
         "actions": [{"type": "CreateAreaAction", "area": 6}]},
        {"id": 103, "kind": "event", "name": "click", "one_time": True, "all_triggers": False, "active": True,
         "triggers": [{"type": "InteractableClickTrigger", "interactableClick": 9}],
         "actions": [{"type": "CreateAreaAction", "area": 8}]},
        {"id": 104, "kind": "event", "name": "gear", "one_time": False, "all_triggers": False, "active": True,
         "triggers": [{"type": "AfterRoundTrigger", "round": 1, "everyNthRound": 1}],
         "actions": [{"type": "RotateAreaAction", "area": 7, "rotation": 90.0, "duration": 4.0}]},
    ]
    removables = [{"id": 50, "class": "Removeable", "name": "Rock", "cost": 750, "active": True,
                   "after": "land", "destroy_area": True, "areas": [5], "position": [100.0, -60.0, 0.0]}]
    paths = [{"id": 200, "name": "P", "source": "PolyLineNodes", "active": True, "hidden": False,
              "points": [[-150, 0, 0], [-50, 0, 0], [50, 0, 0], [150, 0, 0]], "invulnerable": [[2, 3]]},
             {"id": 201, "name": "Secret", "source": "PolyLineNodes", "active": False, "hidden": False,
              "points": [[-150, 100, 0], [150, 100, 0]]}]
    return {"version": gamefiles.GEOMETRY_VERSION, "bundle": "synthetic", "base": "water", "paths": paths,
            "areas": areas, "mechanics": {"removables": removables, "events": events}}


def test_events_sorted_into_automatic_and_player():
    geom = _synthetic()
    dyn = mapgeom.dynamics(geom)
    assert 2 in dyn.appear and 2 in dyn.vanish            # the pane cycles
    assert dyn.vanish[3] == 19                            # melts after round 18
    assert 6 not in dyn.appear and 6 not in dyn.present   # flood only if Rock is bought
    assert 8 not in dyn.appear and 8 not in dyn.present   # click-only: the bot never clicks
    assert [m["areas"] for m in dyn.movers] == [[7]] and len(dyn.movers[0]["poses"]) == 3
    short = mapgeom.dynamics(geom, last_round=15)
    assert 3 not in short.vanish                          # a 15-round game never sees the melt
    later = mapgeom.dynamics(geom, now_round=30)
    assert 3 not in later.present                         # by round 30 it has melted for sure
    bought = mapgeom.dynamics(geom, sold=("Rock",))
    assert 5 not in bought.present and 6 in bought.present


def test_placement_plans_for_the_whole_game():
    geom = _synthetic()
    proj = mapgeom.Projection(PF)
    lanes = np.zeros(mapgeom.GRID[::-1], bool)
    heat, _, _ = mapgeom.paint_paths(geom, proj, lanes)
    grids = mapgeom.placement_grids(geom, proj, lanes | (heat > 0))
    pane, shelf, gear = _cells(proj, 55, 55), _cells(proj, -80, 60, 10.0), _cells(proj, -10, -60)
    plain = _cells(proj, -120, -60)
    assert grids["static_land"][pane] and not grids["land"][pane]     # pane closes later
    assert grids["static_land"][shelf] and not grids["land"][shelf]   # ice melts later
    assert grids["land"][plain]
    assert grids["moving"][gear] and grids["land"][gear]              # gear: ground that moves
    assert grids["drift"][_cells(proj, 15, -60)] > 30                 # its rim travels far
    # bloons on the invulnerable stretch (from the node before it) get no
    # heat, but the lane still blocks placement
    assert heat[_cells(proj, -100, 0)] > 0 and heat[_cells(proj, 100, 0)] == 0
    assert lanes[_cells(proj, 100, 0)]
    # the inactive path is opened by nothing automatic: no heat there
    assert heat[_cells(proj, 0, 100)] == 0


def test_raised_ground_wins_over_lower_obstacles():
    """Quarry-style: land at height 31 over an unplaceable cliff at 30 is
    placeable; a tall object (height 100) over land is not; track always blocks."""
    areas = [_area(1, "unplaceable", _square(-60, -60, 60, 60, 30.0)),
             _area(2, "land", _square(-40, -40, 40, 40, 31.0)),
             _area(3, "unplaceable", _square(-10, -10, 10, 10, 100.0)),
             _area(4, "track", _square(-40, 30, 40, 38, 0.0))]
    geom = {"base": "land", "areas": areas, "paths": []}
    proj = mapgeom.Projection(PF)
    land_ok, _, solid = mapgeom._surfaces(geom, mapgeom.area_masks(geom, proj))
    ok = land_ok & ~solid
    assert ok[_cells(proj, 25, -25, 31.0)]          # on the platform
    assert not ok[_cells(proj, 50, -50, 30.0)]      # on the cliff edge
    assert not ok[_cells(proj, 0, 0, 100.0)]        # under the tall object
    assert not ok[_cells(proj, 0, 34, 31.0)]        # track below still blocks


def test_removal_names_and_trigger_words():
    names = {50: "Rock"}
    assert mapgeom._describe_trigger({"type": "AfterRoundTrigger", "round": 18}, names) == "after round 18"
    assert mapgeom._describe_trigger({"type": "AfterRoundTrigger", "round": 0, "everyNthRound": 2},
                                     names) == "after every 2 rounds"
    assert "Rock" in mapgeom._describe_trigger({"type": "RemoveableSoldTrigger", "removeable": 50}, names)


def test_point_flag_ranges():
    assert gamefiles._ranges([False, True, True, False, True]) == [[1, 2], [4, 4]]
    assert gamefiles._ranges([]) == []


def test_curve_and_rotation_math():
    keys = [[0.0, 0.0, 0.0, 0.0], [1.0, 10.0, 0.0, 0.0]]
    assert mapgeom._curve(keys, 0.0) == 0.0 and mapgeom._curve(keys, 1.0) == 10.0
    assert abs(mapgeom._curve(keys, 0.5) - 5.0) < 1e-6
    p = mapgeom._pose_points(np.array([[1.0, 0.0]]), (0.0, 0.0, 90.0, 0.0, 0.0))
    assert np.allclose(p, [[0.0, -1.0]], atol=1e-9)        # Unity: +90 deg turns clockwise
    gear = {"id": 7, "pivot": [0.0, 0.0, 0.0], "polygons": [_square(-1, -1, 1, 1)]}
    poses = mapgeom._mover_poses({"type": "RotateAreaAction", "area": 7, "rotation": 108.0}, {7: gear})
    assert len(poses) + 1 == 10                              # 108 deg: ten positions


def test_mapfit_stamp_and_game_length():
    geom = {"bundle": "b", "version": 7}
    assert mapfit.stamp_of(geom).endswith(f"#r{mapgeom.RULES_VERSION}")
    table = {"Ice": {"towers": {"ninja": {"early": 0.1, "late": 0.1}},
                     "by_last_round": {"40": {"ninja": {"early": 0.7, "late": 0.7}},
                                       "80": {"ninja": {"early": 0.3, "late": 0.3}}}}}
    saved = mapfit.load
    mapfit.load = lambda: table
    try:
        assert mapfit.strategy_fit("Ice", ["ninja"]) == 0.1
        assert mapfit.strategy_fit("Ice", ["ninja"], last_round=40) == 0.7
        assert mapfit.strategy_fit("Ice", ["ninja"], last_round=60) == 0.3
        assert mapfit.strategy_fit("Ice", ["ninja"], last_round=100) == 0.1
    finally:
        mapfit.load = saved
    assert mapfit.game_lengths()[:1] == [40]


# ---------------------------------------------------------------------------
# The extracted maps
# ---------------------------------------------------------------------------

def _model(name):
    geom = mapgeom.load(name)
    if geom is None or "mechanics" not in geom:
        return None, None
    return mapgeom.apply(MapModel(name, PF), geom), geom


def test_removable_obstacles_are_listed_with_prices():
    if mapgeom.load("Cornfield") is None:
        return
    corn = mapgeom.removables("Cornfield", PF)
    assert len(corn) == 13 and all(r["cost"] > 0 for r in corn)
    assert all(0 < r["frac"][0] < 1 and 0 < r["frac"][1] < 1 for r in corn)
    ore = mapgeom.removables("Three Mines 'Round")
    assert ore and all(r["cash_reward"] > r["cost"] for r in ore)
    chain = {r["name"]: r for r in mapgeom.removables("Dark Path")}
    assert chain["CaveATap1"]["available"] and not chain["CaveATap2"]["available"]
    assert "CaveATap1" in chain["CaveATap2"]["unlocked_by"]


def test_buying_obstacles_frees_room():
    m, _ = _model("Cornfield")
    if m is None:
        return
    names = [r["name"] for r in mapgeom.removables("Cornfield")]
    before = placement.valid_spots(m, "dart").sum()
    after = placement.valid_spots(m, "dart", removed=names).sum()
    assert after > 3 * before
    effect = mapgeom.removal_effect(m, names[0])
    assert effect["cells_freed"] > 0 and not effect["lost_land"].any()
    flood, _ = _model("Flooded Valley")
    plate = mapgeom.removables("Flooded Valley")[0]["name"]
    assert mapgeom.removal_effect(flood, plate)["lost_land"].any()   # the dam floods land


def test_blocker_circles_sit_on_their_blockers():
    """The game's projectile colliders are stored in its flat plane
    (height folded in as z + h/sqrt(3)): every circle centre must fall
    inside its own blocker polygon drawn the same way."""
    import cv2
    checked = 0
    for name in ("Quarry", "Bazaar", "Hedge"):
        geom = mapgeom.load(name)
        if geom is None or "mechanics" not in geom:
            continue
        for a in geom["areas"]:
            if not a["blocks_sight"] or not a["circles"]:
                continue
            poly = np.array(a["polygons"][0], np.float32)
            flat = np.stack([poly[:, 0], poly[:, 1] + poly[:, 2] / math.sqrt(3)], 1).reshape(-1, 1, 2)
            for x, z, _, _ in a["circles"]:
                assert cv2.pointPolygonTest(flat, (float(x), float(z)), False) >= 0, (name, a["name"])
                checked += 1
    assert checked == 0 or checked > 20


def test_raised_platforms_are_usable():
    m, _ = _model("Quarry")
    if m is None:
        return
    assert (m.scan["land"] == 1).sum() > 3000      # was 0 before stacked areas were read


def test_changing_maps_are_planned_pessimistically():
    m, _ = _model("Erosion")
    if m is None:
        return
    full = placement.valid_spots(m, "dart").sum()
    short = placement.valid_spots(m, "dart", last_round=40).sum()
    assert short > 3 * full                         # most ice melts only in long games
    garden, geom = _model("Covered Garden")
    proj = mapgeom.Projection(PF)
    grids = mapgeom.placement_grids(geom, proj)
    assert (grids["static_land"] & ~grids["land"]).sum() > 500   # under the cycling roof panes
    mansion, _ = _model("Midnight Mansion")
    fires = [a for a in mapgeom.load("Midnight Mansion")["areas"] if "MagicFire" in a["name"] and a["blocks_sight"]]
    assert fires and all(a["disabled"] for a in fires)
    for a in fires:   # switched off at the start, yet counted as blocking sight
        c = proj.to_cells([np.mean(np.array(a["polygons"][0]), axis=0)])[0]
        assert mansion.sight[int(c[1]), int(c[0])]


def test_moving_ground_only_for_steady_or_global_towers():
    m, _ = _model("Geared")
    if m is None:
        return
    grids = mapgeom.grids_for(m)
    assert grids["moving"].sum() > 1000
    sniper = placement.valid_spots(m, "sniper")
    ninja = placement.valid_spots(m, "ninja")
    assert (sniper & grids["moving"]).sum() > 1000   # global range rides along fine
    steady = mapgeom.steady_spots(m, 40)
    assert not (ninja & grids["moving"] & ~steady).any()
    assert placement.valid_spots(m, "ninja", moving=True).sum() >= ninja.sum()


def test_suspended_and_hidden_parts():
    m, geom = _model("Polyphemus")
    if m is None:
        return
    water = next(a for a in geom["areas"] if a["name"] == "Water")
    c = mapgeom.Projection(PF).to_cells([np.mean(np.array(water["polygons"][0]), axis=0)])[0]
    assert m.scan["water"][int(c[1]), int(c[0])] == 2    # towers there get switched off
    castle, geom = _model("Castle Revenge")
    entrance = next(p for p in geom["paths"] if p["name"] == "PathEntrance1")
    assert entrance["invulnerable"] == [[0, len(entrance["points"]) - 1]]


def test_summary_file_lists_the_mechanics():
    if not gamefiles.MECHANICS_FILE.exists():
        return
    import json
    data = json.loads(gamefiles.MECHANICS_FILE.read_text(encoding="utf-8"))
    kinds = {f["kind"] for m in data["maps"].values() for f in m["features"]}
    for kind in ("removable", "area_cycle", "area_vanishes", "rotating_area", "moving_platform",
                 "towers_suspended", "hidden_track", "round_removable"):
        assert kind in kinds, kind
    assert data["maps"]["geared"]["features"][0]["carries_towers"] is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
