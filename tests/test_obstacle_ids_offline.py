"""Offline checks for Executor.clear_obstacle on maps whose obstacles share a
name or are simply deleted when bought. Run: python tests/test_obstacle_ids_offline.py

High Finance ABR (2026-11-04) was lost at round 51 with $36k idle: eleven of
its obstacles are all called "Removable", the bot measured each by name -
which always meant the same $350 strip at the top edge - saw no room freed
and never bought one, while the defence had 36 legal ninja cells. Mushroom
Grotto ABR was lost at round 63 the same way: its mushrooms are deleted when
bought ("uncovered") and such obstacles were left out altogether."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import layout as L, mapgeom  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402
from btd6bot.strategy import Executor  # noqa: E402

PF = L.get(1920, 1200)["playfield"]


def _executor(map_name, cash_price=430):
    """An Executor on a fresh model of the map (its geometry applied), no
    towers standing, that records the obstacle it is asked to remove."""
    geom = mapgeom.load(map_name)
    if geom is None:
        return None
    ex = Executor.__new__(Executor)
    ex.m = mapgeom.apply(MapModel(map_name, PF), geom)
    ex.no_removals = False
    ex.land_only = True
    ex.removed, ex.removal_fails = [], {}
    ex.clicked = []
    ex.g = SimpleNamespace(towers={}, hero=None, price=lambda kind: cash_price,
                           remove_obstacle=lambda fx, fy, cost, name="": ex.clicked.append((fx, fy)) or True)
    return ex


def test_same_named_obstacles_are_told_apart():
    ex = _executor("High Finance")
    if ex is None:
        print("skip: no High Finance geometry")
        return
    assert ex.clear_obstacle(5000, "ninja"), "an obstacle that frees room should be bought"
    bought = ex.removed[0]
    rem = {r["id"]: r for r in mapgeom.removables("High Finance", PF)}
    # one of the big $1,500 plazas, not the $350 strip at the top edge
    assert rem[bought]["name"] == "Removable" and rem[bought]["cost"] == 1500, rem[bought]
    # the next purchase is a different "Removable", not the same one again
    assert ex.clear_obstacle(5000, "ninja")
    assert ex.removed[1] != bought and rem[ex.removed[1]]["name"] == "Removable"


def test_deleted_obstacles_count():
    ex = _executor("Mushroom Grotto")
    if ex is None:
        print("skip: no Mushroom Grotto geometry")
        return
    names = {r["id"]: r["name"] for r in mapgeom.removables("Mushroom Grotto", PF)}
    assert ex.clear_obstacle(5000, "ninja")
    assert names[ex.removed[0]] == "RemoveableAreaTriggerMushroom_Main"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
