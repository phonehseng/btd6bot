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
TRACK_HEAT = 10.0              # heat painted on track cells (track_mask needs > 2)
TRACK_THICKNESS = 3            # cells; the drawn width of a bloon lane

# Map ids (bundle names) whose spelling differs from the map's display name.
# Everything else is matched by normalised/fuzzy name. "tutorial" is the scene
# the game uses for Monkey Meadow.
ID_ALIASES = {"tutorial": "Monkey Meadow"}


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


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
        """[[x, z], ...] -> float array of grid (col, row)."""
        p = np.asarray(points, float).reshape(-1, 2)
        fx = self.cx + p[:, 0] * self.ux
        fy = self.cy - p[:, 1] * self.uy
        w, h = GRID
        col = (fx - self.x0) / (self.x1 - self.x0) * w
        row = (fy - self.y0) / (self.y1 - self.y0) * h
        return np.stack([col, row], axis=1)


def _poly_mask(polygons, proj):
    w, h = GRID
    img = np.zeros((h, w), np.uint8)
    for poly in polygons:
        if len(poly) >= 3:
            pts = np.round(proj.to_cells(poly)).astype(np.int32)
            cv2.fillPoly(img, [pts], 1)
    return img > 0


def area_masks(geom, proj):
    """{area type: bool grid} plus 'sight' for line-of-sight blockers."""
    w, h = GRID
    out = {t: np.zeros((h, w), bool) for t in ("track", "water", "land", "unplaceable", "sight", "small_only")}
    for a in geom.get("areas", []):
        if a.get("disabled"):
            continue
        m = _poly_mask(a["polygons"], proj)
        if a["type"] in out:
            out[a["type"]] |= m
        if a["type"] == "land" and a.get("tower_sizes", "") not in ("", "{empty}"):
            out["small_only"] |= m
        if a.get("blocks_sight"):
            out["sight"] |= m
            for x, z, r in a.get("circles", []):
                c = proj.to_cells([[x, z]])[0]
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
    """Overwrite a MapModel's track and placement grids from geometry."""
    proj = Projection(model.playfield, aspect)
    masks = area_masks(geom, proj)
    model.heat, model.t_sum, model.t_cnt = paint_paths(geom, proj)

    # Surface per cell: the map's base surface, then land/water areas on top
    # (islands on water maps, ponds on land maps); track and unplaceable win.
    base = geom.get("base", "land")
    is_water = np.full(GRID[::-1], base == "water")
    is_water[masks["water"]] = True
    is_water[masks["land"]] = False
    # maps whose base is "unplaceable" only allow towers on their land/water areas
    no_ground = np.full(GRID[::-1], base == "unplaceable")
    no_ground[masks["land"] | masks["water"]] = False
    land = np.ones(GRID[::-1], np.uint8)            # 1 = placeable
    blocked = masks["track"] | masks["unplaceable"] | is_water | no_ground
    blocked |= masks["sight"]                        # blockers are solid objects
    # a tower's centre also needs room for its footprint: keep 1 cell clear
    blocked = cv2.dilate(blocked.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    land[blocked] = 2
    water = np.where(is_water & ~(masks["track"] | masks["unplaceable"]), 1, 2).astype(np.uint8)
    model.scan["land"] = land
    model.scan["water"] = water
    model.small_only = masks["small_only"]
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
