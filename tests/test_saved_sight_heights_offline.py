"""A learned map saved after its geometry was applied keeps the sight
heights, so the live forecast rates boards as the offline replay does - no
game needed.

Why: MapModel.save kept the sight grid but not sight_height / ground_height,
and runner._use_geometry returns early once a map's geometry is applied. From
the second game on a map the live model therefore had no heights: every sight
blocker hid bloons from towers on raised ground too. The Dark Dungeons
solo_mortar game of 2026-11-10 04:18 was rated 0.06 every round live, while
the offline replay (which applies the geometry afresh, with heights) rates
the same board 0.65.

Run: python tests/test_saved_sight_heights_offline.py"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapgeom, maplearn  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import GEOMETRY_GRIDS, MapModel  # noqa: E402
from btd6bot.runner import Bot  # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]
MAP, MODE, ROUND = "Dark Dungeons", "military_only", 16
# the board at the start of round 16 of journal 20261110_041823 (solo_mortar)
BOARD = [("d1", "sniper", (2, 2, 0), 0.6546, 0.4787),
         ("d2", "sniper", (2, 2, 0), 0.4996, 0.5213),
         ("mortar1", "mortar", (0, 0, 0), 0.537, 0.4702),
         ("sniper1", "sniper", (0, 0, 0), 0.318, 0.4531)]


def _towers():
    return [SimpleNamespace(tid=t, kind=k, tiers=ti, x=x, y=y) for t, k, ti, x, y in BOARD]


def _margin(m, heights=True):
    hs = (m.sight_height, m.ground_height) if heights else None
    return RoundForecast(MAP, MODE, m.sight, hs).margin(_towers(), ROUND)


class _TempData:
    """Point maplearn.DATA at a temporary folder (the real learned maps are
    the live bot's and must not be written)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = maplearn.DATA
        maplearn.DATA = Path(self.tmp.name)
        return self

    def __exit__(self, *exc):
        maplearn.DATA = self.saved
        self.tmp.cleanup()


def _applied():
    """A Dark Dungeons model with its geometry applied as the live runner does
    it (Bot._use_geometry; it uses nothing of the runner itself), or None."""
    if mapgeom.load(MAP) is None:
        return None
    m = MapModel(MAP, PF)
    assert Bot._use_geometry(None, m, MAP)   # applies and saves
    return m


def test_saved_model_keeps_heights():
    with _TempData():
        fresh = _applied()
        if fresh is None:
            print(f"skip: no {MAP} geometry")
            return
        loaded = MapModel.load(MAP, PF)
        assert loaded.has_geometry_grids(), "a model saved after the geometry lacks a geometry grid"
        for key, dtype in GEOMETRY_GRIDS.items():
            got, want = getattr(loaded, key), getattr(fresh, key)
            assert got.dtype == np.dtype(dtype), (key, got.dtype)
            assert np.array_equal(got, want), f"{key} changed through save/load"
        assert loaded.geometry_version == fresh.geometry_version
        # the forecast the match builds from the loaded model rates as offline
        assert _margin(loaded) == _margin(fresh)


def test_heights_change_the_rating():
    """The board is sight-dependent: without the heights it rates far lower
    (the live 0.06 of the reported game), with them as offline (~0.65)."""
    m = mapgeom.load(MAP) and mapgeom.apply(MapModel(MAP, PF), mapgeom.load(MAP))
    if not m:
        print(f"skip: no {MAP} geometry")
        return
    without, with_heights = _margin(m, heights=False), _margin(m)
    assert without < 0.2, without
    assert with_heights > 0.5, with_heights


def test_old_save_without_heights_is_reapplied():
    """A model saved before the heights were kept (same geometry stamp) gets
    the geometry applied again instead of playing on without them."""
    with _TempData():
        if _applied() is None:
            print(f"skip: no {MAP} geometry")
            return
        old = MapModel.load(MAP, PF)
        old.sight_height = old.ground_height = old.geometry_version = None
        old.save()                                  # what the old save wrote
        stale = MapModel.load(MAP, PF)
        assert stale.sight_height is None and not stale.has_geometry_grids()
        assert Bot._use_geometry(None, stale, MAP)
        assert stale.has_geometry_grids()
        again = MapModel.load(MAP, PF)              # and the re-applied grids were saved
        assert again.has_geometry_grids()
        assert _margin(again) == _margin(mapgeom.apply(MapModel(MAP, PF), mapgeom.load(MAP)))


if __name__ == "__main__":
    test_saved_model_keeps_heights()
    test_heights_change_the_rating()
    test_old_save_without_heights_is_reapplied()
    print("ok")
