"""Bloon routes on maps that carry a second set of splitters for Reverse.

Some maps name, for each path, both the path after it and the path before
it (the splitters Reverse uses). dps_model.map_routes took both as
continuations, so the walk ran back and forth and the routes came out as
short or looping pieces. Workshop Medium (2026-11-08, loss case
20261108_184916, hard_ninja_alch_sniper): the model's only routes were two
stretches of 78 and 100 units of the 310-unit belt. It rated rounds 16-39
at 0.06-0.8 while no bloon got past 37% of the track, the bot spent every
round as a crisis, and the round-40 MOAB, which drops from a hidden chute
onto the last third of the belt, ended the game within seconds with all
150 lives. With the routes fixed the same board rates rounds 33-39 at
1.7-11 and round 40 at 0.2.

Offline, on the committed map geometry (data/map_geometry).
Run: python tests/test_reverse_splitters_offline.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _routes(map_file):
    geom = json.loads((ROOT / "data" / "map_geometry" / f"{map_file}.json").read_text(encoding="utf-8"))
    names = {p["id"]: p["name"] for p in geom["paths"]}
    routes, scenarios = D.map_routes(geom)
    return [([names[p] for p in r["paths"]], r["moab"]) for r in routes], scenarios


def test_workshop_belt_and_moab_chute():
    routes, scenarios = _routes("workshop")
    assert (["PathStart", "P1", "PathMiddle1", "P2", "PathMiddle2", "PathMiddle3", "P3",
             "PathMiddle4", "P4", "PathEnd"], False) in routes, routes
    # MOAB-class bloons come out of the chute at the start of PathMiddle3
    assert (["PathMiddle3", "P3", "PathMiddle4", "P4", "PathEnd"], True) in routes, routes
    assert len(routes) == 2 and scenarios == [[0, 1]], (routes, scenarios)


def test_workshop_track_lengths():
    track = D.Track("Workshop")
    belt, chute = track.total_length()
    assert belt > 2.5 * chute > 250, (belt, chute)
    assert track.routes_for(0, True) == [1] and track.routes_for(0, False) == [0]


def test_balance_entrances_end_on_the_far_side():
    routes, _ = _routes("balance")
    assert len(routes) == 8, routes
    for paths, _moab in routes:
        assert len(paths) == 3, paths
        side = "RH" if paths[0] == "PathRHStart" else "LH"
        assert paths[0] == f"Path{side}Start" and paths[-1] == f"Path{side}End", paths


def test_dark_castle_four_entrances_merge():
    routes, _ = _routes("darkcastle")
    starts = sorted(paths[0] for paths, _ in routes)
    assert starts == ["Path1", "Path2", "Path3", "Path4"], routes
    assert all(paths[-1] == "PathMerge2" for paths, _ in routes), routes


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
