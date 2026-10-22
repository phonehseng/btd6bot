"""Where a tower may stand, and how much track it can see, from game geometry.

The game's placement rule (as read from its map data and code):
  * the tower's footprint is a circle of radius r (EntityModel.radius) around
    its centre; the whole circle must lie on ground the tower may use:
    land for land towers, water for water towers, either for amphibious ones;
  * it may not overlap track, unplaceable areas, removable obstacles, solid
    line-of-sight blockers, or another tower's footprint;
  * areas with a size filter only take towers up to a size class, where the
    class comes from r (TowerModel.GetTowerSize: r <= 6 small, 7 medium,
    8 large, else XL).

The map side comes from MapModel grids filled by mapgeom.apply (exact
surfaces, no margin); spots the game refused during play come from
MapModel.refused, a separate layer that survives re-applying the geometry.
This module adds each tower's own footprint on top, with a
distance transform: a centre is valid when the nearest forbidden cell is at
least r away.

Maps that change during a game (docs/map_mechanics.md): the model's grids
already leave out ground that does not last the whole game (eroding ice,
cycling roof panes, ground under switched-off towers). Two more rules here:
  * moving ground (Geared's gears, Sanctuary's platforms) carries its towers
    around. Global-range towers may stand there; others only where they keep
    covering the track in every position (mapgeom.steady_spots);
  * removable obstacles are left alone unless valid_spots(removed=...) is
    asked what the map looks like after buying them (mapgeom.removables()
    lists them with their prices).

Where the numbers come from, best first:
  1. the game's own model (gamemodel.py, data/game_model/towers.json and
     heroes.json): each tower's radius and allowed surfaces, exact;
  2. data/placement.json (kept in step with 1 by
     `python tools/decode_sim_model.py --sync-placement`), which also holds
     the hand-written line-of-sight and strategy notes;
  3. the size word, then a default, for anything unknown.

Line of sight: most towers cannot shoot through walls and other blockers
(data/placement.json "needs_line_of_sight"). visible_cover() counts only the
track a spot can see, by sampling straight lines to every track cell in range.
"""
import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import gamemodel
from . import towers as T
from .maplearn import GRID

DATA = Path(__file__).resolve().parents[1] / "data"

# Fallback footprint radii (world units) when only a size word is known: a
# typical radius of each of the game's size classes (small <= 6, medium 7,
# large 8, XL above; Super Monkey, Mortar and Village are 11).
SIZE_WORD_RADIUS = {"small": 6.0, "medium": 7.0, "large": 8.0, "xl": 11.0}
DEFAULT_RADIUS = 7.0
SIGHT_SAMPLES = 16          # points checked along each line of sight


@lru_cache(maxsize=1)
def _tower_table():
    """Per tower/hero id: footprint radius, size word, surfaces, line of sight."""
    try:
        d = json.loads((DATA / "placement.json").read_text(encoding="utf-8"))
        return d.get("towers", {})
    except (OSError, ValueError):
        return {}


def _entry(kind, hero=None):
    table = _tower_table()
    key = hero if kind == "hero" else kind
    if key in table:
        return table[key]
    norm = "".join(c for c in str(key).lower() if c.isalnum())
    for k, v in table.items():   # hero ids differ slightly between tables
        kn = "".join(c for c in k.lower() if c.isalnum())
        if kn == norm or kn.endswith(norm) or norm.endswith(kn):
            return v
    return {}


def footprint_radius(kind, hero=None):
    """Footprint radius in world units: the game's own radius for the tower
    (EntityModel.radius), else placement.json, else a size-word guess."""
    r = gamemodel.footprint_radius(kind, hero)
    if r:
        return r
    e = _entry(kind, hero)
    r = e.get("footprint_radius")
    if r:
        return float(r)
    return SIZE_WORD_RADIUS.get(str(e.get("footprint", "")).lower(), DEFAULT_RADIUS)


def size_level(kind, hero=None):
    """The game's size class 1-4 (small, medium, large, XL) from the radius."""
    return gamemodel.size_class(footprint_radius(kind, hero))


def surfaces(kind, hero=None):
    """{'land'}, {'water'} or both: the area types the game lets the tower
    stand on, else the bot's own tables."""
    decoded = gamemodel.surfaces(kind, hero)
    if decoded:
        return decoded
    if kind == "hero":
        where = T.HEROES.get(hero, {}).get("placement") or _entry(kind, hero).get("placement") or "land"
    else:
        where = T.TOWERS.get(kind, {}).get("placement") or "land"
    return {"land", "water"} if where == "land_or_water" else {where}


def needs_sight(kind, hero=None):
    e = _entry(kind, hero)
    return bool(e.get("needs_line_of_sight", True))


def units_per_cell(model):
    """World units spanned by one grid cell (horizontally)."""
    from .mapgeom import WORLD_PX_PER_UNIT_1920
    cell_frac = (model.playfield[2] - model.playfield[0]) / GRID[0]
    return cell_frac / (WORLD_PX_PER_UNIT_1920 / 1920)


def has_geometry(model):
    return getattr(model, "sight", None) is not None and "land" in model.scan


def reach_units(kind, hero=None):
    """A tower's range in world units: None for global range (sniper,
    mortar, heli, ace, dartling, farm); for a hero its range, 0 when not
    known (it then keeps off moving ground)."""
    if kind == "hero":
        return T.HEROES.get(hero, {}).get("range") or 0.0
    return T.TOWERS.get(kind, {}).get("range")


def _game_grids(model, removed=(), now_round=None, last_round=None):
    """The map's placement grids worked out from its geometry (mapgeom,
    cached), or None when the model's map has no geometry file."""
    try:
        from . import mapgeom
        return mapgeom.grids_for(model, removed, now_round, last_round)
    except Exception:  # a map-file problem must never stop placement
        return None


def valid_spots(model, kind, hero=None, towers=(), where=None,
                removed=(), now_round=None, last_round=None, moving=None):
    """Bool grid: cells where this tower's centre may go. None without geometry.

    towers: [(cx, cy, kind, hero)] already placed (their footprints block).
    where:  restrict the surfaces (e.g. {'land'} in modes without water use).
    removed: removable obstacles (names or ids, mapgeom.removables) to treat
            as bought - the room they free counts, the room their sale floods
            or wrecks does not.
    now_round / last_round: the round being played and the game's last
            round: ground that opens by now counts (One Two Tree's plots),
            changes after the last round do not (Erosion in a short game).
            Without them every change of the whole game is planned for.
    moving: moving ground (gears, platforms) - None: global-range towers
            anywhere on it, others only on steady spots; True: anywhere;
            False: never."""
    if not has_geometry(model):
        return None
    where = surfaces(kind, hero) & set(where) if where else surfaces(kind, hero)
    ok = np.zeros(model.heat.shape, bool)
    # spots the game refused in earlier play are learned per surface and kept
    # outside the geometry grids (MapModel.refused), so subtract them here
    def refused(surface):
        mask = getattr(model, "refused_mask", None)
        return mask(surface) if mask else np.zeros(ok.shape, bool)

    scan, mermonkey_water, size_limit = model.scan, model.mermonkey_water, model.size_limit
    if removed or now_round is not None or last_round is not None:
        alt = _game_grids(model, tuple(removed), now_round, last_round)
        if alt is not None:
            scan = alt["scan"]
            mermonkey_water, size_limit = alt["mermonkey_water"], alt["size_limit"]
    if "land" in where:
        ok |= (scan["land"] == 1) & ~refused("land")
    if "water" in where:
        water = scan.get("water", np.full(ok.shape, 2)) == 1
        if kind == "mermonkey" and mermonkey_water is not None:
            water |= mermonkey_water
        ok |= water & ~refused("water")
    if size_limit is not None:
        ok &= size_limit >= size_level(kind, hero)
    if moving is not True:
        grids = _game_grids(model)
        if grids is not None and grids["moving"].any():
            rng = reach_units(kind, hero)
            if moving is False:
                ok &= ~grids["moving"]
            elif rng is not None:   # global range does not care where it is carried
                from .mapgeom import steady_spots
                steady = steady_spots(model, rng) if rng else None
                ok &= ~grids["moving"] | (steady if steady is not None else False)
    upc = units_per_cell(model)
    radius = footprint_radius(kind, hero) / upc
    # distance (in cells) from every allowed cell to the nearest forbidden one;
    # the border counts as forbidden so footprints stay on the map
    padded = np.pad(ok, 1, constant_values=False).astype(np.uint8)
    dist = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
    valid = dist >= radius
    if towers:
        hh, ww = valid.shape
        yy, xx = np.mgrid[0:hh, 0:ww]
        for cx, cy, other_kind, other_hero in towers:
            reach = radius + footprint_radius(other_kind, other_hero) / upc
            valid &= (xx - cx) ** 2 + (yy - cy) ** 2 >= reach * reach
    return valid


def visible_cover(model, cx, cy, range_cells, weight):
    """Sum of track weight within range of (cx, cy) that is in line of sight
    (no sight-blocking cell on the straight line between)."""
    hh, ww = weight.shape
    r = int(np.ceil(range_cells))
    y0, y1 = max(0, cy - r), min(hh, cy + r + 1)
    x0, x1 = max(0, cx - r), min(ww, cx + r + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sub = weight[y0:y1, x0:x1]
    inside = ((xx - cx) ** 2 + (yy - cy) ** 2 <= range_cells ** 2) & (sub > 0)
    if not inside.any():
        return 0.0
    tx, ty = xx[inside].astype(np.float32), yy[inside].astype(np.float32)
    sight = model.sight
    if sight is None or not sight.any():
        return float(sub[inside].sum())
    # sample points strictly between the tower and each target cell
    t = np.linspace(0.1, 0.9, SIGHT_SAMPLES, dtype=np.float32)[:, None]
    px = np.clip(np.rint(cx + (tx - cx) * t), 0, ww - 1).astype(np.int32)
    py = np.clip(np.rint(cy + (ty - cy) * t), 0, hh - 1).astype(np.int32)
    blocked = sight[py, px].any(axis=0)
    return float(sub[inside][~blocked].sum())
