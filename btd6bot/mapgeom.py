"""Turn map geometry read from the game files (gamefiles.py) into MapModel grids.

A MapModel describes the play field on a GRID of cells (maplearn.py):
  heat     where bloons travel (track cells > 0)
  t_sum/t_cnt  progress along the track, 0 at the entrance .. 1 at the exit
  scan     placement: scan["land"] 1 = a land tower can stand, 2 = blocked;
           scan["water"] 1 = water (water towers only)
plus, from the geometry, two extra masks:
  small_only  cells where only small towers fit (an area's size filter)
  sight       cells occupied by line-of-sight blockers

World coordinates: x to the right, z up, the play field centred on the origin.
The game draws WORLD_PX_PER_UNIT_1920 screen pixels per world unit on a
1920-pixel-wide screen (measured by fitting extracted geometry to placement
scans the bot made in-game; see calibrate()).
"""
import difflib
import json
import logging

import cv2
import numpy as np

from .gamefiles import GEOMETRY_DIR
from .maplearn import GRID

log = logging.getLogger("mapgeom")

WORLD_PX_PER_UNIT_1920 = 5.3   # refined by calibrate(); see module docstring
# The game camera is tilted: a point raised by h units appears HEIGHT_FACTOR*h
# units further up the screen. Measured on Luminous Cove (paths at heights
# 54 -> 28 -> 2): live bloons gave 0.55 and the outlines of its raised areas
# against a picture of the map 0.5 (tools/fit_height_edges.py; 2026-10-22).
# Flat maps are unaffected. Re-check with that tool after game updates.
HEIGHT_FACTOR = 0.55
TRACK_HEAT = 10.0              # heat painted on track cells (track_mask needs > 2)
TRACK_THICKNESS = 3            # cells; the drawn width of a bloon lane

# Map ids (bundle names) whose spelling differs from the map's display name.
# Everything else is matched by normalised/fuzzy name. "tutorial" is the scene
# the game uses for Monkey Meadow.
ID_ALIASES = {"tutorial": "Monkey Meadow"}


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


# Map bundles in the game that are not single-player maps the bot plays.
NOT_PLAYABLE_IDS = {"baseeditormap", "blons", "protecttheyacht", "tutorialmap"}


def unknown_map_id(card_label):
    """Geometry id of a map the game has but the bot's map list lacks, whose
    id matches an OCR'd map-select card label; None otherwise.

    A new map must exist in BOTH places - as a bundle in the game files and as
    a card on screen - so OCR debris and banners are never taken for maps."""
    from .account import MAPS
    known = {map_id_for(m) for m in MAPS} | NOT_PLAYABLE_IDS
    candidates = {_norm(f.stem): f.stem for f in GEOMETRY_DIR.glob("*.json")
                  if f.stem not in known}
    key = _norm(card_label)
    if len(key) < 4 or not candidates:
        return None
    close = difflib.get_close_matches(key, candidates, n=1, cutoff=0.85)
    return candidates[close[0]] if close else None


def map_id_for(display_name):
    """Geometry file id for a map's display name, or None if not extracted."""
    ids = [f.stem for f in GEOMETRY_DIR.glob("*.json")]
    for map_id, name in ID_ALIASES.items():
        if _norm(name) == _norm(display_name) and map_id in ids:
            return map_id
    by_norm = {_norm(i): i for i in ids}
    key = _norm(display_name)
    if key in by_norm:
        return by_norm[key]
    close = difflib.get_close_matches(key, by_norm, n=1, cutoff=0.85)
    return by_norm[close[0]] if close else None


def load(display_name):
    map_id = map_id_for(display_name)
    if map_id is None:
        return None
    try:
        return json.loads((GEOMETRY_DIR / f"{map_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Projection:
    """World (x, z) <-> grid cell (float) for a model's play field."""

    def __init__(self, playfield, aspect=1920 / 1200, px_per_unit=WORLD_PX_PER_UNIT_1920):
        self.x0, self.y0, self.x1, self.y1 = playfield
        self.cx = (self.x0 + self.x1) / 2            # play-field centre (screen fractions)
        self.cy = (self.y0 + self.y1) / 2
        self.ux = px_per_unit / 1920                 # screen-width fraction per unit
        self.uy = self.ux * aspect                   # screen-height fraction per unit

    def to_cells(self, points):
        """[[x, z(, y)], ...] -> float array of grid (col, row). y = height."""
        p = np.asarray(points, float)
        p = p.reshape(-1, p.shape[-1]) if p.size else np.zeros((0, 2))
        height = p[:, 2] if p.shape[1] > 2 else 0.0
        fx = self.cx + p[:, 0] * self.ux
        fy = self.cy - (p[:, 1] + HEIGHT_FACTOR * height) * self.uy
        w, h = GRID
        col = (fx - self.x0) / (self.x1 - self.x0) * w
        row = (fy - self.y0) / (self.y1 - self.y0) * h
        return np.stack([col, row], axis=1)


def _poly_mask(polygons, proj):
    """Cells covered by an area. As in the game (Unity Area.ToModel), the first
    polygon is the area's outline and every further polygon is a HOLE in it:
    Logs' track outline has the grass blocks between its lanes as holes."""
    w, h = GRID
    img = np.zeros((h, w), np.uint8)
    for i, poly in enumerate(polygons):
        if len(poly) >= 3:
            pts = np.round(proj.to_cells(poly)).astype(np.int32)
            cv2.fillPoly(img, [pts], 1 if i == 0 else 0)
    return img > 0


# Tower size classes, from the game's TowerModel.GetTowerSize: a footprint
# radius up to 6 is small, exactly 7 medium, exactly 8 large, anything else XL
# (constants 6.0/7.0/8.0 read from GameAssembly.dll). Area size filters are
# cumulative lists ("small,medium"), so an area allows sizes up to a level.
SIZE_LEVELS = {"small": 1, "medium": 2, "large": 3, "xl": 4}


def size_level_of_filter(text):
    """'small,medium' -> 2; '' / '{empty}' (no filter) -> 4 (everything fits)."""
    sizes = [s.strip().lower() for s in (text or "").split(",") if s.strip()]
    sizes = [s for s in sizes if s in SIZE_LEVELS]
    return max((SIZE_LEVELS[s] for s in sizes), default=4)


def area_masks(geom, proj):
    """Bool grids per surface type (track, water, land, unplaceable, ice,
    removable, water_mermonkey, shallow_water), 'sight' for line-of-sight
    blockers, and 'size_limit' (uint8): the largest tower size class allowed."""
    w, h = GRID
    names = ("track", "water", "land", "unplaceable", "ice", "removable",
             "water_mermonkey", "shallow_water", "sight")
    out = {t: np.zeros((h, w), bool) for t in names}
    out["size_limit"] = np.full((h, w), 4, np.uint8)
    for a in geom.get("areas", []):
        if a.get("disabled"):
            continue
        m = _poly_mask(a["polygons"], proj)
        if a["type"] in out:
            out[a["type"]] |= m
        level = size_level_of_filter(a.get("tower_sizes", ""))
        if level < 4:
            out["size_limit"][m] = np.minimum(out["size_limit"][m], level)
        if a.get("blocks_sight"):
            out["sight"] |= m
            for circle in a.get("circles", []):
                x, z, r = circle[:3]
                y = circle[3] if len(circle) > 3 else 0.0
                c = proj.to_cells([[x, z, y]])[0]
                rad = max(1, int(round(r * proj.ux / (proj.x1 - proj.x0) * GRID[0])))
                cv2.circle(out["sight"].view(np.uint8), (int(c[0]), int(c[1])), rad, 1, -1)
    return out


def _visible_span(cells):
    """Indices of the first and last path point inside the grid."""
    w, h = GRID
    inside = (cells[:, 0] >= 0) & (cells[:, 0] < w) & (cells[:, 1] >= 0) & (cells[:, 1] < h)
    idx = np.nonzero(inside)[0]
    return (idx[0], idx[-1]) if idx.size else (0, len(cells) - 1)


def paint_paths(geom, proj):
    """heat, t_sum, t_cnt grids from the map's (visible) bloon paths."""
    w, h = GRID
    heat = np.zeros((h, w), np.float32)
    t_sum = np.zeros((h, w), np.float32)
    t_cnt = np.zeros((h, w), np.float32)
    for path in geom.get("paths", []):
        if path.get("hidden") or len(path["points"]) < 2:
            continue  # hidden = bloons out of sight (tunnels): towers cannot hit them
        cells = proj.to_cells(path["points"])
        seg = np.linalg.norm(np.diff(cells, axis=0), axis=1)
        dist = np.concatenate([[0.0], np.cumsum(seg)])
        a, b = _visible_span(cells)
        span = max(dist[b] - dist[a], 1e-6)
        for i in range(len(cells) - 1):
            p0 = tuple(int(round(v)) for v in cells[i])
            p1 = tuple(int(round(v)) for v in cells[i + 1])
            prog = float(np.clip(((dist[i] + dist[i + 1]) / 2 - dist[a]) / span, 0, 1))
            line = np.zeros((h, w), np.uint8)
            cv2.line(line, p0, p1, 1, TRACK_THICKNESS)
            on = line > 0
            heat[on] = TRACK_HEAT
            t_sum[on] += prog
            t_cnt[on] += 1
    return heat, t_sum, t_cnt


def apply(model, geom, aspect=1920 / 1200):
    """Overwrite a MapModel's track and placement grids from geometry.

    scan["land"] / scan["water"] hold the exact surfaces (1 = a land / water
    tower's centre may stand here as far as the ground goes, 2 = not). The
    room each tower's footprint needs is added per tower by placement.py, and
    spots the game refuses in play are still learned on top of these grids."""
    proj = Projection(model.playfield, aspect)
    masks = area_masks(geom, proj)
    model.heat, model.t_sum, model.t_cnt = paint_paths(geom, proj)

    # Surface per cell: the map's base surface, then the areas drawn on top
    # (islands on water maps, ponds on land maps); track and obstacles win.
    base = geom.get("base", "land")
    shape = GRID[::-1]
    land_ok = np.full(shape, base in ("land", "ice"))
    water_ok = np.full(shape, base == "water")
    for name in ("land", "ice"):
        land_ok |= masks[name]
        water_ok &= ~masks[name]
    water_ok |= masks["water"]
    land_ok &= ~masks["water"]
    land_ok |= masks["shallow_water"]          # shallow water takes both kinds
    water_ok |= masks["shallow_water"]
    solid = masks["track"] | masks["unplaceable"] | masks["removable"] | masks["sight"]
    solid |= model.heat > 0   # the drawn bloon lanes can poke past the track polygon on curves
    model.scan["land"] = np.where(land_ok & ~solid, 1, 2).astype(np.uint8)
    model.scan["water"] = np.where(water_ok & ~solid, 1, 2).astype(np.uint8)
    model.mermonkey_water = masks["water_mermonkey"] & ~solid
    model.size_limit = masks["size_limit"]
    model.small_only = masks["size_limit"] <= 1
    model.sight = masks["sight"]
    model.geometry_version = geom.get("version", 1)
    log.info("%s: geometry applied (%d paths, %d areas)", model.name,
             len(geom.get("paths", [])), len(geom.get("areas", [])))
    return model


def calibrate(models_and_geoms, scales=np.arange(5.0, 5.71, 0.05)):
    """Best px-per-unit: the scale at which geometry 'blocked' cells agree most
    with placement scans measured in-game (list of (model, geom) pairs)."""
    best = None
    for s in scales:
        agree = total = 0
        for model, geom in models_and_geoms:
            scan = model.scan.get("land")
            if scan is None:
                continue
            proj = Projection(model.playfield, px_per_unit=s)
            m = area_masks(geom, proj)
            geo_blocked = m["track"] | m["unplaceable"] | m["water"]
            known = scan > 0
            agree += int(((scan == 2) == geo_blocked)[known].sum())
            total += int(known.sum())
        score = agree / max(total, 1)
        if best is None or score > best[1]:
            best = (float(s), score)
    return best
