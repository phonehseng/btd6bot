"""Offline checks that the map-fit table counts only the track a tower can
see (mapfit.visible_track), measured on the game's own map geometry.

Flooded Valley's dam hides the river from every land cell. Measured by
range alone a land ninja "reached" 17 % of the track there, and two land
builds lost the map within a minute (Apopalypse round 16, 2026-11-06;
Magic Monkeys Only round 23, 2026-11-10).
Run: python tests/test_mapfit_sight_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapfit  # noqa: E402
from btd6bot import placement  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def _model(name):
    model, _ = mapfit._model_for(name)
    if model is None:
        print("skip: no geometry for", name)
    return model


def test_flooded_valley_land_towers_see_no_track():
    model = _model("Flooded Valley")
    if model is None:
        return
    for kind in ("ninja", "wizard", "dart", "boomerang"):
        cover = mapfit.kind_coverage(model, kind)
        assert cover["early"] == 0.0 and cover["late"] == 0.0, (kind, cover)
    # range alone still reaches some track: the drop comes from sight
    ok = placement.valid_spots(model, "ninja")
    plain = mapfit._coverage(model, "ninja", ok, T.TOWERS["ninja"]["range"])
    assert plain["early"] > 0.05, plain


def test_towers_that_ignore_sight_are_not_limited():
    """A mortar fires over walls (placement.json needs_line_of_sight false):
    its coverage is the range measurement, sight or no sight."""
    model = _model("Flooded Valley")
    if model is None:
        return
    assert not placement.needs_sight("mortar")
    cover = mapfit.kind_coverage(model, "mortar")
    ok = placement.valid_spots(model, "mortar")
    assert cover["early"] == mapfit._coverage(model, "mortar", ok, None)["early"]


def test_visible_track_is_a_subset_of_the_track_in_range():
    model = _model("Peninsula")
    if model is None:
        return
    ok = placement.valid_spots(model, "ninja")
    seen = mapfit.visible_track(model, ok, T.TOWERS["ninja"]["range"])
    if seen is None:      # no sight blockers on this map: nothing to limit
        return
    assert not (seen & ~(model.t_cnt > 0)).any()
    plain = mapfit._coverage(model, "ninja", ok, T.TOWERS["ninja"]["range"])
    sighted = mapfit._coverage(model, "ninja", ok, T.TOWERS["ninja"]["range"], visible=seen)
    assert sighted["early"] <= plain["early"] and sighted["late"] <= plain["late"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
