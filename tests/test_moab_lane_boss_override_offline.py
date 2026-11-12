"""A MOAB-class lane that bosses also take is not a boss-only path.

Sunset Gulch's spawn splitter sends MOAB-class bloons over the railway
bridge (PathSpecial, 390 world units) and names the same path as the boss
override. dps_model._is_boss_path dropped it as boss-only, so the model
rated every blimp on the long canyon road (PathStandard) past all the
towers. Loss case 20261112_122752_SunsetGulch_impoppable: the model rated
round 58 at 1.51, the five MOABs crossed the bridge in about 15 s and ended
the game. With the bridge read as the MOAB lane the same board rates round
58 at 0.38.

Offline, on the committed map geometry (data/map_geometry).
Run: python tests/test_moab_lane_boss_override_offline.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _geom(map_file):
    return json.loads((ROOT / "data" / "map_geometry" / f"{map_file}.json").read_text(encoding="utf-8"))


def _routes(map_file):
    geom = _geom(map_file)
    names = {p["id"]: p["name"] for p in geom["paths"]}
    routes, scenarios = D.map_routes(geom)
    return [([names[p] for p in r["paths"]], r["moab"]) for r in routes], scenarios


def test_sunset_gulch_blimps_take_the_bridge():
    routes, scenarios = _routes("sunsetgulch")
    assert (["PathSpecial"], True) in routes, routes
    assert (["PathStandard"], False) in routes, routes
    assert len(routes) == 2 and scenarios == [[0, 1]], (routes, scenarios)


def test_sunset_gulch_bridge_is_short():
    """The blimps' lane is the bridge, about half the canyon road on screen
    (308 and 612 units of visible track)."""
    track = D.Track("Sunset Gulch")
    routes, _ = D.map_routes(_geom("sunsetgulch"))
    moab = [i for i, r in enumerate(routes) if r["moab"]]
    other = [i for i, r in enumerate(routes) if r["moab"] is False]
    assert track.routes_for(0, True) == moab and track.routes_for(0, False) == other
    lengths = track.total_length()
    assert 250 < lengths[moab[0]] < 400, lengths
    assert lengths[other[0]] > 1.8 * lengths[moab[0]], lengths


def test_castle_revenge_keeps_its_moab_exits():
    """Castle Revenge's MOAB exits 3639 and 3724 are also boss overrides."""
    routes, _ = _routes("castlerevenge")
    moab_paths = {p for paths, moab in routes if moab for p in paths}
    names = {p["id"]: p["name"] for p in _geom("castlerevenge")["paths"]}
    assert names[3639] in moab_paths and names[3724] in moab_paths, routes


def test_boss_only_paths_stay_out():
    """A path only bosses take is still dropped (Ancient Portal's boss tag)."""
    geom = _geom("ancientportal")
    routes, _ = D.map_routes(geom)
    assert all(2297 not in r["paths"] for r in routes), routes


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
