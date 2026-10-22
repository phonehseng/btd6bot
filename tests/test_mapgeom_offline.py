"""Map geometry read from the game files -> MapModel grids (no game needed).

Uses the extracted JSON in data/map_geometry (skipped when it is absent)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapgeom  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]


def _model(name):
    geom = mapgeom.load(name)
    if geom is None:
        return None, None
    return mapgeom.apply(MapModel(name, PF), geom), geom


def test_names_resolve():
    if not mapgeom.GEOMETRY_DIR.exists():
        return
    assert mapgeom.map_id_for("Monkey Meadow") == "tutorial"
    assert mapgeom.map_id_for("Town Center") == "towncentre"
    assert mapgeom.map_id_for("Three Mines 'Round") == "threeminesaround"
    assert mapgeom.map_id_for("#Ouch") == "-ouch"


def test_progress_runs_entrance_to_exit():
    m, geom = _model("Logs")
    if m is None:
        return
    path = next(p for p in geom["paths"] if not p["hidden"])
    cells = mapgeom.Projection(PF).to_cells(path["points"])
    prog = m.progress_full()
    h, w = prog.shape
    inside = [(int(c), int(r)) for c, r in cells if 0 <= c < w and 0 <= r < h]
    first, last = inside[0], inside[-1]
    assert prog[first[1], first[0]] < 0.2 < 0.8 < prog[last[1], last[0]]


def test_water_map_is_mostly_water():
    m, _ = _model("Spice Islands")
    if m is None:
        return
    assert (m.scan["water"] == 1).mean() > 0.4
    assert (m.scan["land"] == 1).mean() < 0.4


def test_track_is_never_placeable():
    m, _ = _model("Monkey Meadow")
    if m is None:
        return
    on_track = m.heat > 0
    assert on_track.sum() > 200
    assert np.all(m.scan["land"][on_track] == 2)


if __name__ == "__main__":
    test_names_resolve()
    test_progress_runs_entrance_to_exit()
    test_water_map_is_mostly_water()
    test_track_is_never_placeable()
    print("ok")
