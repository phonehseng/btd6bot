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
MapModel.refused, a separate layer that survives re-applying the geometry
(one shared by every tower for the small towers' refusals, one per kind for
the bigger towers', see refusal_layer).
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
from .mapgeom import HEIGHT_TIE

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


# Footprint radius up to which a refusal is learned for every tower on the
# surface: the smallest towers' (dart, ninja, sniper, alchemist: 6). Where
# the game refuses one of those, the ground itself is bad.
SHARED_REFUSAL_RADIUS = 6.0


def refusal_layer(surface, kind, hero=None):
    """The MapModel.refused layer a refusal of this tower is learned in.

    A small tower's refusal goes into the surface's shared layer, which
    every tower avoids. A bigger tower's goes into a layer of its own
    ("land@ace"): the game turned down its footprint, which reaches further
    than a small tower's. The ground under the centre may be fine. Tricky
    Tracks (2026-11-09): aces refused next to the diagonal tracks (their
    28x18 runway reaches past the radius-12 circle the grid checks) had been
    learned as bad land for every tower. 1,148 refused cells, nearly all 9-16
    units from the track, took 26% of the ground a ninja may use."""
    if footprint_radius(kind, hero) <= SHARED_REFUSAL_RADIUS:
        return surface
    return f"{surface}@{hero if kind == 'hero' and hero else kind}"


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


def hud_zones():
    """Screen rectangles (x0, y0, x1, y1, as fractions) where the in-game HUD
    sits over the map and takes the clicks: the round counter with the
    settings gear top right, from the counter's left edge to the play
    field's right edge. Taken from the calibrated layout (layout.LAYOUTS),
    so it moves with it.

    A tower can be dropped there, but a click on its centre lands on the HUD
    and never opens its upgrade panel. Erosion Reverse (2026-11-06 13:20):
    four surplus snipers bought at y=0.070 under the round counter
    (x 0.724-0.836) were each "not on the map; forgotten" after two failed
    selections and bought again - $1,264 for towers the bot could not use.

    The lives and cash bar top left is left out on purpose: towers there
    were selected and upgraded without trouble (an alchemist at 0.142,0.095
    on 2026-10-24), and several Deflation builds use that strip."""
    from .layout import LAYOUTS
    lay = LAYOUTS["16:10"]
    rnd, gear, playfield = lay["round"], lay["gear"], lay["playfield"]
    top = playfield[1]
    # the gear icon is as far below its centre as above it
    bottom = max(rnd[3], gear[1] + (gear[1] - top))
    return [(rnd[0], top, playfield[2], bottom)]


def hud_cells(model):
    """Bool grid of the play-field cells whose centre lies under the HUD
    (hud_zones): no tower should stand there."""
    w, h = GRID
    x0, y0, x1, y1 = model.playfield
    fx = x0 + (np.arange(w) + 0.5) / w * (x1 - x0)
    fy = y0 + (np.arange(h) + 0.5) / h * (y1 - y0)
    out = np.zeros((h, w), bool)
    for zx0, zy0, zx1, zy1 in hud_zones():
        cols = (fx >= zx0) & (fx <= zx1)
        rows = (fy >= zy0) & (fy <= zy1)
        out |= rows[:, None] & cols[None, :]
    return out


def reach_units(kind, hero=None):
    """A tower's range in world units: None for global range (sniper,
    mortar, heli, ace, dartling, farm); for a hero its range, 0 when not
    known (it then keeps off moving ground).

    The game model's own global_range flag is asked first, so a map-wide
    hero counts as global too: Psi's table range is unknown, and reading it
    as 0 left Psi without a single legal cell on moving ground (Geared,
    Sanctuary) although Psi hits bloons anywhere on screen."""
    entry = gamemodel.entity(kind, hero)
    if entry and entry.get("global_range"):
        return None
    if kind == "hero":
        return T.HEROES.get(hero, {}).get("range") or 0.0
    return T.TOWERS.get(kind, {}).get("range")


def _game_grids(model, removed=(), now_round=None, last_round=None, pose_round=None):
    """The map's placement grids worked out from its geometry (mapgeom,
    cached), or None when the model's map has no geometry file."""
    try:
        from . import mapgeom
        return mapgeom.grids_for(model, removed, now_round, last_round, pose_round)
    except Exception:  # a map-file problem must never stop placement
        return None


def valid_spots(model, kind, hero=None, towers=(), where=None,
                removed=(), now_round=None, last_round=None, moving=None, pose_round=None):
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
            False: never.
    pose_round: on maps with moving platforms (Sanctuary), the last round
            started: the platforms are where they stand in it, not in the
            scene's pose (mapgeom.grids_for). Ignored elsewhere.

    Learned refusals (MapModel.refused) never cover platform ground:
    mapgeom.forget_platform_refusals drops them and the strategy does not
    learn them there."""
    if not has_geometry(model):
        return None
    where = surfaces(kind, hero) & set(where) if where else surfaces(kind, hero)
    ok = np.zeros(model.heat.shape, bool)
    free = np.zeros(model.heat.shape, bool)   # ok minus the spots the game refused
    # spots the game refused in earlier play are learned per surface and kept
    # outside the geometry grids (MapModel.refused), so subtract them here
    def refused(surface):
        mask = getattr(model, "refused_mask", None)
        if not mask:
            return np.zeros(ok.shape, bool)
        own = refusal_layer(surface, kind, hero)    # this tower's own refusals, when big
        return mask(surface) | mask(own) if own != surface else mask(surface)

    # ... and spots the game accepted although the map file says blocked
    def accepted(surface):
        mask = getattr(model, "accepted_mask", None)
        return mask(surface) if mask else np.zeros(ok.shape, bool)

    scan, mermonkey_water, size_limit = model.scan, model.mermonkey_water, model.size_limit
    if removed or now_round is not None or last_round is not None or pose_round is not None:
        alt = _game_grids(model, tuple(removed), now_round, last_round, pose_round)
        if alt is not None:
            scan = alt["scan"]
            mermonkey_water, size_limit = alt["mermonkey_water"], alt["size_limit"]
    if "land" in where:
        land = (scan["land"] == 1) | accepted("land")
        ok |= land
        free |= land & ~refused("land")
    if "water" in where:
        water = scan.get("water", np.full(ok.shape, 2)) == 1
        if kind == "mermonkey" and mermonkey_water is not None:
            water |= mermonkey_water
        water = water | accepted("water")
        ok |= water
        free |= water & ~refused("water")
    if size_limit is not None:
        fits = size_limit >= size_level(kind, hero)
        ok &= fits
        free &= fits
    if moving is not True:
        grids = _game_grids(model, pose_round=pose_round)
        if grids is not None and grids["moving"].any():
            rng = reach_units(kind, hero)
            if moving is False:
                ok &= ~grids["moving"]
                free &= ~grids["moving"]
            elif rng is not None:   # global range does not care where it is carried
                from .mapgeom import steady_spots
                steady = steady_spots(model, rng, pose_round) if rng else None
                carried = ~grids["moving"] | (steady if steady is not None else False)
                ok &= carried
                free &= carried
    upc = units_per_cell(model)
    radius = footprint_radius(kind, hero) / upc
    # distance (in cells) from every allowed cell to the nearest forbidden one;
    # the border counts as forbidden so footprints stay on the map
    padded = np.pad(ok, 1, constant_values=False).astype(np.uint8)
    dist = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
    # Refused spots are taken out only after the footprint check: they are
    # single cells the game said no to, not walls. (Sunset Gulch: ~100
    # learned refusals, each a 3x3 patch, made every cell of the map "too
    # close to a forbidden one" - no legal spot at all, and an Easy game
    # was lost with one sniper.)
    valid = (dist >= radius) & free
    # a tower under the HUD could be bought but never selected again
    if valid.shape == (GRID[1], GRID[0]):
        valid &= ~hud_cells(model)
    if towers:
        hh, ww = valid.shape
        yy, xx = np.mgrid[0:hh, 0:ww]
        for cx, cy, other_kind, other_hero in towers:
            reach = radius + footprint_radius(other_kind, other_hero) / upc
            valid &= (xx - cx) ** 2 + (yy - cy) ** 2 >= reach * reach
    return valid


def sight_blockers(model, cx, cy, sight=None):
    """Bool grid of the cells that block sight for a tower standing at cell
    (cx, cy). A blocker hides bloons only from towers below it: a tower on
    raised ground (Sunken Columns' column tops, Mesa's plateaus) sees over
    blockers as high as its own ground. Falls back to every blocker when the
    map's heights are unknown.

    sight: (blockers, heights) standing in for the model's whole-game
    model.sight / model.sight_height, e.g. the round's own from
    mapgeom.grids_for(now_round) (see visible_cover)."""
    blockers, heights = (model.sight, getattr(model, "sight_height", None)) if sight is None else sight
    ground = getattr(model, "ground_height", None)
    if heights is None or ground is None:
        return blockers
    return heights > ground[cy, cx] + HEIGHT_TIE


def visible_cover(model, cx, cy, range_cells, weight, sight=None):
    """Sum of track weight within range of (cx, cy) that is in line of sight
    (no sight-blocking cell, see sight_blockers, on the straight line between).

    sight: (blockers, heights) of the round being played, when the caller
    knows them (Executor._round_sight); the model's own grids hold every
    blocker that stands at any time of the game. One Two Tree's 23 blocker
    plots, opened as the game goes, and Cargo's centre trucks, gone at the
    first MOAB, blocked sight in them to the end (audit 2026-11-12)."""
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
    blockers = model.sight if sight is None else sight[0]
    if blockers is None or not blockers.any():
        return float(sub[inside].sum())
    sight = sight_blockers(model, cx, cy, sight)
    # sample points strictly between the tower and each target cell
    t = np.linspace(0.1, 0.9, SIGHT_SAMPLES, dtype=np.float32)[:, None]
    px = np.clip(np.rint(cx + (tx - cx) * t), 0, ww - 1).astype(np.int32)
    py = np.clip(np.rint(cy + (ty - cy) * t), 0, hh - 1).astype(np.int32)
    blocked = sight[py, px].any(axis=0)
    return float(sub[inside][~blocked].sum())
