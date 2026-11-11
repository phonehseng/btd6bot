"""The glass HUD's FIELD layer (tools/glass_field.py): what the bot sees of
the map, drawn over the play field.

Offline: the layer is drawn from the map geometry in data/map_geometry and
learned models in temporary folders (the repo's data/maps is only read);
the window side runs with fake windows. No lock, no control files in the
repo, no game.
Run: python tests/test_glass_field_offline.py"""
import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import glass_field as F                                             # noqa: E402
import hud_data as D                                                # noqa: E402
from btd6bot import mapgeom                                         # noqa: E402
from btd6bot.maplearn import GRID, MapModel                         # noqa: E402
from test_big_hud_offline import fake_root, live_hud                # noqa: E402
from test_glass_hud_offline import Clock, FakeWindow                # noqa: E402

# 16:10, as BTD6 runs here: full screen at four sizes, and a window that
# does not start at the screen's corner
GAME_RECTS = [(0, 0, 1920, 1200), (0, 0, 2560, 1600), (0, 0, 1680, 1050), (0, 0, 1440, 900),
              (37, 64, 1280, 800)]
RENDER_BUDGET_MS = 1500       # one map's first picture, model read included (about 150-500 ms on the laptop)
REDRAW_BUDGET_MS = 600        # a new round's picture on a map whose paths alternate (about 60-130 ms)


def game(map_name, mode="medium", rnd=10, end=60):
    """The little of a hud_data.Snapshot the field layer reads."""
    return SimpleNamespace(game={"map": map_name, "mode": mode, "end_round": end}, round=rnd)


def empty_maps():
    """A folder with no learned model (the layer works from the geometry
    alone), removed when the tests end."""
    folder = tempfile.mkdtemp(prefix="field_maps_")
    atexit.register(shutil.rmtree, folder, True)
    return folder


# -- alignment ----------------------------------------------------------------------------------

def test_every_cell_lands_on_its_own_pixels():
    """The layer's pixels are sorted into the bot's grid cells the way
    MapModel.frac_to_cell sorts a screen point: each cell's centre, put on
    the screen as hud_data.project puts a tower, falls on a pixel the layer
    paints with that cell, and every cell gets about the same number of
    pixels (no row or column lost or doubled)."""
    pf = F.playfield()
    model = MapModel("alignment", pf)
    gw, gh = GRID
    for rect in GAME_RECTS:
        left, top, width, height = rect
        x0, y0, x1, y1 = F.playfield_rect(rect)
        # the layer's window covers the play field, rounded out to whole pixels
        assert x0 <= left + pf[0] * width < x0 + 1 and x1 - 1 < left + pf[2] * width <= x1, rect
        assert y0 <= top + pf[1] * height < y0 + 1 and y1 - 1 < top + pf[3] * height <= y1, rect
        cols, rows = F.pixel_cells(rect, GRID)
        assert len(cols) == x1 - x0 and len(rows) == y1 - y0
        for cx in range(gw):
            for cy in (0, gh // 2, gh - 1):
                sx, sy = D.project(*model.cell_to_frac(cx, cy), rect)
                px, py = int(sx) - x0, int(sy) - y0
                assert cols[px] == cx and rows[py] == cy, (rect, cx, cy, cols[px], rows[py])
                assert model.frac_to_cell((sx - left) / width, (sy - top) / height) == (cx, cy)
        assert set(cols[cols >= 0]) == set(range(gw)) and set(rows[rows >= 0]) == set(range(gh))
        per_col = np.bincount(cols[cols >= 0])
        per_row = np.bincount(rows[rows >= 0])
        assert per_col.max() - per_col.min() <= 1 and per_row.max() - per_row.min() <= 1, rect


def test_the_painted_ground_is_the_bots_grid():
    """Blown up to pixels, the ground layer shows exactly the cells the
    bot's placement allows: a pixel is tinted when its cell is legal and
    left clear when it is not (rims and hatch aside)."""
    src = F.FieldSource(empty_maps())
    view = src.view("Bazaar", "medium", 10, 60)
    assert view.land is not None and view.land.any() and view.water.any()
    view.refused = view.refused_own = None
    for rect in GAME_RECTS[:2] + GAME_RECTS[-1:]:
        img = np.asarray(F.draw_ground(view, rect))
        cols, rows = F.pixel_cells(rect, GRID)
        legal = view.land_ground | view.water_ground
        for cy in range(0, GRID[1], 7):
            for cx in range(0, GRID[0], 5):
                # the middle pixel of the cell's block of pixels
                px = int(np.flatnonzero(cols == cx).mean())
                py = int(np.flatnonzero(rows == cy).mean())
                assert (img[py, px, 3] > 0) == bool(legal[cy, cx]), (rect, cx, cy)


def test_paths_run_along_the_track_cells():
    """The bloon paths are drawn where the bot's track lies: points along
    each path, put on the screen, fall in (or next to) the cells
    mapgeom.path_masks gives that path."""
    for map_name in ("Bazaar", "Last Resort", "Glacial Trail"):
        geom = mapgeom.load(map_name)
        proj = mapgeom.Projection(F.playfield())
        lines = F.path_lines(geom, F.playfield(), None)
        assert lines, map_name
        rect = (0, 0, 1920, 1200)
        x0, y0, _x1, _y1 = F.playfield_rect(rect)
        cols, rows = F.pixel_cells(rect, GRID)
        for line in lines:
            only = dict(geom, paths=[p for p in geom["paths"] if p.get("name") == line.name])
            mask = mapgeom.path_masks(only, proj)[0]          # the cells the bot gives this path
            near = np.zeros_like(mask)
            near[1:-1, 1:-1] = mask[1:-1, 1:-1] | mask[:-2, 1:-1] | mask[2:, 1:-1] | mask[1:-1, :-2] | mask[1:-1, 2:]
            near |= mask
            # points halfway along each segment that lies on the grid
            mids = (line.points[1:] + line.points[:-1]) / 2
            hits = total = 0
            for (fx, fy), hidden in zip(mids, line.hidden):
                px, py = int(fx * 1920) - x0, int(fy * 1200) - y0
                if hidden or not (0 <= px < len(cols) and 0 <= py < len(rows)) or cols[px] < 0 or rows[py] < 0:
                    continue
                total += 1
                hits += bool(near[rows[py], cols[px]])
            assert total and hits / total > 0.95, (map_name, line.name, hits, total)


def test_paths_this_round():
    """Which path an alternating map hands a round: the first listed on
    round 1, the next one each round (Last Resort: 1 big loop, 2 medium,
    3 small, 0 straight - round 15 rides the small loop, as the frame
    20261110_192339_LastResort_medium/frames/game_003.jpg shows)."""
    lr = mapgeom.load("Last Resort")
    names = {p["id"]: p["name"] for p in lr["paths"]}
    assert [names[next(iter(mapgeom.paths_this_round(lr, r)))] for r in (1, 2, 3, 4, 15, 16)] == \
        ["Path1", "Path2", "Path3", "Path4", "Path3", "Path4"]
    cove = mapgeom.load("Luminous Cove")
    assert {p["id"]: p["name"] for p in cove["paths"]}[next(iter(mapgeom.paths_this_round(cove, 63)))] == \
        "PathLeftStart"                                             # odd rounds on the left
    erosion = mapgeom.load("Erosion")
    en = {p["id"]: p["name"] for p in erosion["paths"]}
    assert [en[next(iter(mapgeom.paths_this_round(erosion, r)))] for r in (1, 18, 19, 36, 37)] == \
        ["Path1", "Path1", "Path2", "Path2", "Path3"]
    assert mapgeom.paths_this_round(mapgeom.load("Glacial Trail"), 5) == frozenset()
    assert mapgeom.paths_this_round(lr, None) == frozenset()


def test_path_statuses_and_round_share():
    """This round's path is "now"; an alternating map's others are "other"
    and drawn by their share of the rounds (the top straight every Last
    Resort route shares counts in full, a loop a quarter); a one-path map
    has a "live" path; Erosion's later phases are "idle"."""
    pf = F.playfield()
    lr = {p.name: p for p in F.path_lines(mapgeom.load("Last Resort"), pf, 15)}
    assert lr["Path3"].status == "now" and {lr[n].status for n in ("Path1", "Path2", "Path4")} == {"other"}
    big = lr["Path1"].share
    assert big is not None and big.max() == 1.0 and 0.2 < big.min() <= 0.5      # shared straight vs its own loop
    assert [p.status for p in F.path_lines(mapgeom.load("Glacial Trail"), pf, 15)] == ["live"]
    erosion = {p.name: p.status for p in F.path_lines(mapgeom.load("Erosion"), pf, 22)}
    assert erosion["Path2"] == "now" and erosion["Path6"] == "idle"
    # a Reverse game runs the paths backwards
    fwd = F.path_lines(mapgeom.load("Glacial Trail"), pf, 15)[0].points
    back = F.path_lines(mapgeom.load("Glacial Trail"), pf, 15, reverse=True)[0].points
    assert np.allclose(fwd[0], back[-1]) and np.allclose(fwd[-1], back[0])


def test_learned_refusals_are_shown_and_the_model_is_never_written():
    """A refusal in a learned model is hatched on ground the map allows;
    the model is only read (its folder unchanged, save() a no-op)."""
    maps = Path(empty_maps())
    model = MapModel("Bazaar", F.playfield())
    mapgeom.apply(model, mapgeom.load("Bazaar"))
    ys, xs = np.nonzero(model.scan["land"] == 1)
    cx, cy = int(xs[len(xs) // 2]), int(ys[len(ys) // 2])
    model.refuse("land", cx, cy)
    model.refuse("land@ace", int(xs[0]), int(ys[0]))
    np.savez_compressed(maps / "bazaar.npz", heat=model.heat, t_sum=model.t_sum, t_cnt=model.t_cnt,
                        scan_land=model.scan["land"], scan_water=model.scan["water"],
                        refused_land=model.refused["land"], **{"refused_land@ace": model.refused["land@ace"]},
                        meta='{"rounds_traced": 0}')
    before = {p.name: p.stat().st_mtime_ns for p in maps.iterdir()}
    src = F.FieldSource(maps)
    view = src.view("Bazaar", "medium", 10, 60)
    assert view.refused[cy, cx] and not view.land[cy, cx]
    assert view.refused_own is not None and view.refused_own[int(ys[0]), int(xs[0])]
    assert src.model("Bazaar").save() is False
    assert {p.name: p.stat().st_mtime_ns for p in maps.iterdir()} == before


# -- cost ---------------------------------------------------------------------------------------

def test_render_time_per_map():
    """Each map's picture is drawn within budget the first time (model and
    geometry read included) and comes from the cache when nothing changed;
    a new round redraws only on maps whose paths alternate."""
    rect = (0, 0, 1920, 1200)
    maps = empty_maps()
    for map_name, alternating in (("Bazaar", True), ("Last Resort", True), ("Glacial Trail", False),
                                  ("Erosion", False), ("Monkey Meadow", False)):
        layer = F.FieldLayer(maps)
        snap = game(map_name, rnd=21)
        t0 = time.perf_counter()
        assert layer.key(snap, rect) is not None
        pic = layer.picture(snap, rect)
        first = (time.perf_counter() - t0) * 1000
        assert pic is not None and first < RENDER_BUDGET_MS, (map_name, first)
        x0, y0, x1, y1 = F.playfield_rect(rect)
        assert (pic.x, pic.y, pic.image.size) == (x0, y0, (x1 - x0, y1 - y0)) and pic.image.mode == "RGBA"
        alpha = np.asarray(pic.image)[..., 3]
        assert alpha.max() > 150, map_name                         # the paths stand out ...
        # ... and the game stays visible: a faint tint at most nearly everywhere
        assert np.median(alpha) < 60 and (alpha > 100).mean() < 0.1, (map_name, np.median(alpha))
        assert layer.picture(snap, rect) is pic                    # unchanged: no drawing at all
        t0 = time.perf_counter()                                   # the next poll of the bot's files:
        assert layer.key(game(map_name, rnd=21), rect) == layer.key(snap, rect)     # a cheap look, no reading
        assert (time.perf_counter() - t0) * 1000 < 50, map_name
        later = game(map_name, rnd=22)
        assert (layer.key(later, rect) != layer.key(snap, rect)) == alternating, map_name
        t0 = time.perf_counter()
        layer.picture(later, rect)
        assert (time.perf_counter() - t0) * 1000 < REDRAW_BUDGET_MS, map_name


def test_a_reverse_game_draws_the_paths_backwards():
    """Reverse mode: the map's own model (no "<map> reverse" one saved) and
    its paths from exit to entrance; a new poll costs no model reading."""
    rect = (0, 0, 1920, 1200)
    layer = F.FieldLayer(empty_maps())
    fwd = layer.source.view("Glacial Trail", "medium", 5, 60).paths[0].points
    back = layer.source.view("Glacial Trail", "reverse", 5, 60).paths[0].points
    assert np.allclose(fwd[::-1], back)
    snap = game("Glacial Trail", mode="reverse", rnd=5)
    assert layer.picture(snap, rect) is not None
    t0 = time.perf_counter()
    for _ in range(5):
        layer.key(game("Glacial Trail", mode="reverse", rnd=5), rect)
    assert (time.perf_counter() - t0) * 1000 < 100


def test_a_bad_map_hides_the_layer_without_retrying_every_tick():
    rect = (0, 0, 1920, 1200)
    layer = F.FieldLayer(empty_maps())
    calls = []

    def broken(*args):
        calls.append(args)
        raise ValueError("bad map file")
    layer.source.view = broken
    snap = game("Bazaar")
    assert layer.picture(snap, rect) is None and "bad map file" in layer.error
    assert layer.picture(game("Bazaar"), rect) is None and len(calls) == 1    # same key: not tried again


def test_nothing_known_nothing_drawn():
    layer = F.FieldLayer(empty_maps())
    rect = (0, 0, 1920, 1200)
    assert layer.key(game("No Such Map"), rect) is None
    assert layer.key(game(None), rect) is None
    assert layer.key(game("Bazaar"), None) is None


# -- the switch and the window -------------------------------------------------------------------

def test_the_switch():
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.pop(F.FIELD_ENV, None)
        try:
            assert F.field_wanted(tmp)                                  # on by default
            (Path(tmp) / "HUD_NO_FIELD").write_text("", encoding="utf-8")
            assert not F.field_wanted(tmp)
            (Path(tmp) / "HUD_NO_FIELD").unlink()
            os.environ[F.FIELD_ENV] = "off"
            assert not F.field_wanted(tmp)
        finally:
            os.environ.pop(F.FIELD_ENV, None)
            if old is not None:
                os.environ[F.FIELD_ENV] = old


def test_glass_hud_shows_the_field_under_the_rest_and_hides_it_on_the_switch():
    """In a game the field gets a window of its own, the lowest of the
    widgets'; a HUD_NO_FIELD file hides it at the next poll of the bot's
    files (no restart), and taking the file away shows it again."""
    import glass_hud
    import hud_controls
    now = time.time()
    old_rect = hud_controls.game_client_rect
    hud_controls.game_client_rect = lambda: (0, 0, 1920, 1200)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            collector = D.Collector(fake_root(tmp, now, hud=live_hud(now)), clock=lambda: now)
            clock = Clock(now)
            hud = glass_hud.GlassHud(None, collector=collector, clock=clock, size=(1920, 1200),
                                     make_window=FakeWindow)
            hud.frame()
            field = hud.windows["field"]
            assert field.shown == 1 and field.picture.image.size == (1642, 1104)
            assert hud.stacking()[0] == "field"                         # re-raised first: everything else above it
            clock.t += glass_hud.POLL_S
            hud.frame()
            assert field.shown == 1                                     # a new poll, the same map: not drawn again
            (Path(tmp) / "HUD_NO_FIELD").write_text("", encoding="utf-8")
            clock.t += glass_hud.POLL_S
            hud.frame()
            assert field.hidden == 1 and field.shown == 1
            (Path(tmp) / "HUD_NO_FIELD").unlink()
            clock.t += glass_hud.POLL_S
            hud.frame()
            assert field.shown == 2
    finally:
        hud_controls.game_client_rect = old_rect


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
