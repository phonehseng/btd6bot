"""On maps with the game's own geometry, the bot's track is the painted bloon
paths only - no guessed "thin blocked corridors" - no game needed.

Why: MapModel.track_weight() used to add the land scan's thin blocked
corridors (weight 0.4) to the traced track. That guess is meant for maps the
bot knows nothing about; with geometry the scan's blocked ground is mostly
scenery. On Peninsula (ABR, 2026-11-04) it drew a phantom stretch of track
in the middle of the rock, the ninjas, sniper, Skywarden and alchemist were
all placed to cover it, and round 22 leaked 99 lives past them.

Run: python tests/test_geometry_track_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapgeom, placement  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]


def _model(map_name):
    """A fresh model of the map with its geometry applied (None without it)."""
    geom = mapgeom.load(map_name)
    if geom is None:
        return None
    return mapgeom.apply(MapModel(map_name, PF), geom)


def test_weight_is_the_painted_track():
    m = _model("Peninsula")
    if m is None:
        print("skip: no Peninsula geometry")
        return
    weight = m.track_weight()
    painted = m.track_mask()
    assert painted.sum() > 0, "Peninsula's paths painted no track"
    off = (weight > 0) & ~painted
    assert not off.any(), f"{int(off.sum())} cells of guessed track off the map's paths"


def test_peninsula_rock_top_covers_no_track():
    """The spot the lost game's first ninja stood on (0.446, 0.198), in the
    middle of the rock: a ninja there reaches none of the real lane."""
    m = _model("Peninsula")
    if m is None:
        print("skip: no Peninsula geometry")
        return
    cx, cy = m.frac_to_cell(0.446, 0.198)
    reach = placement.reach_units("ninja") / placement.units_per_cell(m)
    cover = placement.visible_cover(m, cx, cy, reach, m.track_weight())
    assert cover == 0.0, f"rock-top ninja covers {cover} of phantom track"


def test_maps_without_geometry_still_guess():
    """No geometry: the corridor guess is all the bot has, and stays."""
    m = MapModel("Nowhere", PF)
    land = np.full(m.heat.shape, 1, np.uint8)
    land[50:55, 10:150] = 2          # a thin blocked corridor across the map
    m.scan["land"] = land
    assert m.geometry_version is None
    assert (m.track_weight() > 0).sum() > 0


if __name__ == "__main__":
    test_weight_is_the_painted_track()
    test_peninsula_rock_top_covers_no_track()
    test_maps_without_geometry_still_guess()
    print("geometry track tests passed")
