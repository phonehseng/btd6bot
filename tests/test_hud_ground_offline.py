"""The HUD's field layer draws the ground the bot's placement sees.

Audit of 2026-11-12 (dynamic maps, items 23 and 24): the field layer built
its ground without the bot's round, platform pose or phase horizon, so
Sanctuary was drawn in its opening layout, Erosion showed the few cells
that last all game and One Two Tree's opened plots never appeared; and the
ghost towers of a Sanctuary build stood at their raw spots while the bot
clicked the carried ones. The match now writes now_round, pose_round and
ground_horizon to hud.json, the layer builds and keys its ground on them,
and plan_ahead writes carried spots.

Offline: the map geometry alone (an empty models folder), no game.
Run: python tests/test_hud_ground_offline.py"""
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import glass_field as F                      # noqa: E402
from btd6bot import hudstate, mapgeom        # noqa: E402

FOLDER = tempfile.mkdtemp(prefix="hud_ground_maps_")


def source():
    return F.FieldSource(FOLDER)


def land(view):
    return int(view.land.sum())


def test_one_two_tree_shows_opened_plots():
    if mapgeom.load("One Two Tree") is None:
        return
    src = source()
    whole = src.view("One Two Tree", "hard", 80, 80)
    late = src.view("One Two Tree", "hard", 80, 80, ground={"now_round": 80})
    assert land(late) > land(whole), (land(late), land(whole))


def test_erosion_shows_the_phase_ground():
    geom = mapgeom.load("Erosion")
    if geom is None:
        return
    src = source()
    whole = src.view("Erosion", "hard", 1, 80)
    phase = src.view("Erosion", "hard", 1, 80,
                     ground={"now_round": 1, "ground_horizon": mapgeom.phase_end(geom, 1)})
    assert land(phase) > 10 * land(whole), (land(phase), land(whole))


def test_sanctuary_ground_follows_the_platforms():
    if mapgeom.load("Sanctuary") is None:
        return
    src = source()
    views = [src.view("Sanctuary", "hard", r, 80, ground={"now_round": r, "pose_round": r})
             for r in range(1, 12)]
    assert any((v.land != views[0].land).any() for v in views[1:]), "the platforms never moved"


def test_layer_key_follows_the_ground_only_where_it_changes():
    src = source()
    assert src.phase_key("One Two Tree", 20, ground={"now_round": 20}) != \
        src.phase_key("One Two Tree", 20, ground={"now_round": 21})
    assert src.phase_key("Monkey Meadow", 20, ground={"now_round": 20}) == \
        src.phase_key("Monkey Meadow", 20, ground={"now_round": 21})
    snap = SimpleNamespace(now_round=7, pose_round=6, ground_horizon=18)
    assert F.FieldLayer.ground_of(snap) == {"now_round": 7, "pose_round": 6, "ground_horizon": 18}


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn()
                print("ok", name)
    finally:
        shutil.rmtree(FOLDER, True)
    print("all tests passed")
