"""Turn map geometry read from the game files (gamefiles.py) into MapModel grids.

A MapModel describes the play field on a GRID of cells (maplearn.py):
  heat     where bloons travel and can be hit (track cells > 0)
  t_sum/t_cnt  progress along the track, 0 at the entrance .. 1 at the exit
  scan     placement: scan["land"] 1 = a land tower can stand, 2 = blocked;
           scan["water"] 1 = water (water towers only)
plus, from the geometry, two extra masks:
  small_only  cells where only small towers fit (an area's size filter)
  sight       cells occupied by line-of-sight blockers

Maps that change during a game (see "Map mechanics" below and
docs/map_mechanics.md) are planned for pessimistically: a cell is placeable
only if it stays placeable through every change the game makes by itself
(rising water, eroding ice, cycling windows, ...), and a line-of-sight
blocker that is sometimes there counts as always there. Changes only the
player can cause (buying an obstacle, clicking the map) are left out unless
asked for (grids_for(..., removed=...)).

World coordinates: x to the right, z up, the play field centred on the origin.
The game draws WORLD_PX_PER_UNIT_1920 screen pixels per world unit on a
1920-pixel-wide screen (measured by fitting extracted geometry to placement
scans the bot made in-game; see calibrate()).
"""
import difflib
import json
import logging
import math

import cv2
import numpy as np

from .gamefiles import GEOMETRY_DIR, MECHANICS_FILE
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


# Map models of Reverse games are keyed "<map> reverse" (runner, forecast,
# towerxp). Reverse runs the same map backwards, so it has the same geometry.
REVERSE_SUFFIX = " reverse"


def map_id_for(display_name):
    """Geometry file id for a map's display name, or None if not extracted.

    A Reverse game's model key ("Erosion reverse") names the map it is
    played on: without the suffix stripped here, placement_grids() found no
    geometry for the reverse model and placement fell back to the bare
    placement scan, without the per-round ground lifetimes. On Erosion that
    left 4 ace cells instead of 2,600, and every ace step of solo_ace was
    given up on round 1 (loss case 20261107_043112, round 18, 133 lives)."""
    if display_name.endswith(REVERSE_SUFFIX):
        display_name = display_name[:-len(REVERSE_SUFFIX)]
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

    def to_frac(self, points):
        """[[x, z(, y)], ...] -> float array of screen fractions (fx, fy)."""
        p = np.asarray(points, float)
        p = p.reshape(-1, p.shape[-1]) if p.size else np.zeros((0, 2))
        height = p[:, 2] if p.shape[1] > 2 else 0.0
        fx = self.cx + p[:, 0] * self.ux
        fy = self.cy - (p[:, 1] + HEIGHT_FACTOR * height) * self.uy
        return np.stack([fx, fy], axis=1)

    def to_cells(self, points):
        """[[x, z(, y)], ...] -> float array of grid (col, row). y = height."""
        f = self.to_frac(points)
        w, h = GRID
        col = (f[:, 0] - self.x0) / (self.x1 - self.x0) * w
        row = (f[:, 1] - self.y0) / (self.y1 - self.y0) * h
        return np.stack([col, row], axis=1)

    def cell_world(self):
        """World (x, z) of every grid cell's centre at ground height:
        two (h, w) arrays."""
        w, h = GRID
        cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
        fx = self.x0 + cols / w * (self.x1 - self.x0)
        fy = self.y0 + rows / h * (self.y1 - self.y0)
        return (fx - self.cx) / self.ux, (self.cy - fy) / self.uy

    def units_to_cells(self, units):
        return units * self.ux / (self.x1 - self.x0) * GRID[0]


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


def _area_id(area, index):
    """An area's id (its component id in the scene; older extractions had
    none, then its position in the list stands in)."""
    return area.get("id", ("index", index))


def starting_areas(geom):
    """Ids of the areas present when a game starts, as written in the scene:
    not disabled (switched on later by a map event, if ever) and not on a
    switched-off object."""
    return {_area_id(a, i) for i, a in enumerate(geom.get("areas", []))
            if not a.get("disabled") and not a.get("inactive")}


# Stacked areas. Many maps build raised platforms as a placeable area lying
# just above an unplaceable "cliff" area (Quarry, Castle Revenge, Mesa...).
# The game sorts its areas by height, highest first (Simulation Map.CreateMap),
# and Map.CanPlace takes the FIRST area containing the tower's centre: that
# area's type decides. The footprint is then checked only against areas from
# that height up to FOOTPRINT_HEIGHT_WINDOW above it, so lower areas never
# matter. Areas of equal height (most flat maps) keep the old rule: anything
# unplaceable wins. Track polygons always block, at any height (the bot's
# own safety margin; bloon lanes are drawn on top anyway).
# Constants read from GameAssembly.dll's data (Map.CanPlace):
FOOTPRINT_HEIGHT_WINDOW = 5.0   # footprint vs areas up to 5 units above the centre's
MAX_PLACE_HEIGHT = 250.0        # no tower on an area this high (height + render offset)
HEIGHT_TIE = 0.05               # heights closer than this count as equal


def area_height(area):
    """An area's height: the median height of its outline's points."""
    outline = area.get("polygons", [[]])[0] if area.get("polygons") else []
    return float(np.median([p[2] for p in outline if len(p) > 2])) if outline and len(outline[0]) > 2 else 0.0


def area_masks(geom, proj, present=None, retype=None):
    """Bool grids per surface type (track, water, land, unplaceable, ice,
    removable, water_mermonkey, shallow_water), 'sight' for line-of-sight
    blockers, 'blockers' for the blocker areas themselves, and 'size_limit'
    (uint8): the largest tower size class allowed. Each cell is decided by
    the highest area covering it (see FOOTPRINT_HEIGHT_WINDOW above).

    present: ids of the areas to draw (default: the starting state);
    retype:  {area id: surface type} for areas whose type changed (an
             obstacle sold without deleting its area becomes e.g. land)."""
    w, h = GRID
    names = ("track", "water", "land", "unplaceable", "ice", "removable",
             "water_mermonkey", "shallow_water", "sight", "blockers")
    out = {t: np.zeros((h, w), bool) for t in names}
    out["size_limit"] = np.full((h, w), 4, np.uint8)
    # how high the blocker at each cell stands (-inf: no blocker), so a tower
    # on ground as high as a blocker can see over it (see sight_blockers)
    out["sight_height"] = np.full((h, w), -np.inf, np.float32)
    present = starting_areas(geom) if present is None else present
    retype = retype or {}
    drawn = []   # (area, its surface type now, cells, height)
    for i, a in enumerate(geom.get("areas", [])):
        aid = _area_id(a, i)
        if aid in present:
            drawn.append((a, retype.get(aid, a["type"]), _poly_mask(a["polygons"], proj), area_height(a)))
    top = np.full((h, w), -np.inf, np.float32)   # height of the highest area per cell
    for a, kind, m, height in drawn:
        if kind != "track":
            top[m] = np.maximum(top[m], height)
    for a, kind, m, height in drawn:
        eff = m if kind == "track" else m & (height >= top - HEIGHT_TIE)
        if kind in out:
            out[kind] |= eff
        if height + a.get("render_offset", 0.0) >= MAX_PLACE_HEIGHT and kind != "track":
            out["unplaceable"] |= eff
        level = size_level_of_filter(a.get("tower_sizes", ""))
        if level < 4:
            out["size_limit"][eff] = np.minimum(out["size_limit"][eff], level)
        if a.get("blocks_sight"):
            out["blockers"] |= eff
            out["sight"] |= eff
            # the game's own projectile colliders; not over higher ground
            circles = np.zeros((h, w), np.uint8)
            for circle in a.get("circles", []):
                x, z, r = circle[:3]
                y = circle[3] if len(circle) > 3 else 0.0
                c = proj.to_cells([[x, z, y]])[0]
                rad = max(1, int(round(proj.units_to_cells(r))))
                cv2.circle(circles, (int(c[0]), int(c[1])), rad, 1, -1)
            ring = (circles > 0) & (top <= height + HEIGHT_TIE)
            out["sight"] |= ring
            blocked = eff | ring
            out["sight_height"][blocked] = np.maximum(out["sight_height"][blocked], height)
    # the ground a tower would stand on: the highest area that is not track
    out["ground"] = np.where(np.isfinite(top), top, 0.0).astype(np.float32)
    return out


def _visible_span(cells):
    """Indices of the first and last path point inside the grid."""
    w, h = GRID
    inside = (cells[:, 0] >= 0) & (cells[:, 0] < w) & (cells[:, 1] >= 0) & (cells[:, 1] < h)
    idx = np.nonzero(inside)[0]
    return (idx[0], idx[-1]) if idx.size else (0, len(cells) - 1)


def _in_ranges(i, ranges):
    return any(a <= i <= b for a, b in ranges)


def bloon_paths(geom):
    """The paths bloons can take without the player doing anything: active
    at the start, or switched on by the map itself (Cargo's MOAB route after
    round 39, Bloonarius Prime's whirl path). Paths only the player can open
    (Ancient Portal's other side, Spa Pits' easter-egg routes) are left out:
    no bloon comes along them in the bot's games."""
    on = dynamics(geom).paths_on
    return [p for p in geom.get("paths", []) if p.get("active", True) or p.get("id") in on]


# How many rounds before a path phase starts its path is painted as track
# already, so the defence for it is built while the old path still runs.
PHASE_LEAD = 5


def idle_phase_paths(geom, rnd, lead=PHASE_LEAD):
    """Path ids that bloons will not use in rounds rnd .. rnd+lead, because an
    AlternateRoundSplitter with long phases hands each path whole blocks of
    rounds (Erosion: six paths, 18 rounds each, in order, not looping).

    The game counts phase i as rounds offset + i*N .. offset + (i+1)*N - 1
    (roundsPerPath N, currentRoundOffset, the last phase lasting for good
    when doesNotLoop). Splitters that switch every round (roundsPerPath 1:
    Luminous Cove) use all their paths all the time, so none is idle there.
    An empty frozenset when the map has no such phases or rnd is unknown."""
    if rnd is None:
        return frozenset()
    idle = set()
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if not str(s.get("type", "")).startswith("AlternateRound"):
            continue
        n, paths = int(s.get("roundsPerPath") or 1), list(s.get("paths") or [])
        if n < 2 or len(paths) < 2:
            continue
        offset = int(s.get("currentRoundOffset") or 0)

        def phase(r):
            i = max(0, (r - offset) // n)
            return min(i, len(paths) - 1) if s.get("doesNotLoop") else i % len(paths)

        used = {paths[phase(r)] for r in range(rnd, rnd + lead + 1)}
        idle |= set(paths) - used
    if idle:
        # the boss route lies on top of one phase's path (Erosion's PathBoss
        # copies Path3) and no boss comes in the bot's games: painting it
        # would keep that path's track live in every phase
        idle |= _boss_paths(geom)
    return frozenset(idle)


def phase_end(geom, rnd):
    """The last round of the path phase that round `rnd` belongs to, or None
    when it does not apply: no long path phases (see idle_phase_paths), rnd
    unknown, or the final phase of a splitter that does not loop (it lasts
    for good).

    Erosion: Path2 carries rounds 19-36, so phase_end(geom, 22) is 36. Its
    ice melts at the same phase ends, and every phase's own track is in
    reach only from ice that melts when the phase is over: ground that has
    to last the whole game reaches none of it (Erosion Magic Monkeys Only,
    case 20261106_130851, placed every tower in the far corner and lost on
    round 22). The executor therefore asks for ground that lasts until the
    phase ends (Executor.ground_horizon)."""
    if rnd is None:
        return None
    ends = []
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if not str(s.get("type", "")).startswith("AlternateRound"):
            continue
        n, paths = int(s.get("roundsPerPath") or 1), list(s.get("paths") or [])
        if n < 2 or len(paths) < 2:
            continue
        offset = int(s.get("currentRoundOffset") or 0)
        i = max(0, (rnd - offset) // n)           # same count as idle_phase_paths
        if s.get("doesNotLoop") and i >= len(paths) - 1:
            continue
        ends.append(offset + (i + 1) * n - 1)
    return min(ends) if ends else None


def lost_ground(model, geom, old_round, new_round, aspect=1920 / 1200):
    """Bool grid of the cells on areas the map destroys by itself between
    two rounds: changes whose first affected round lies in (old_round,
    new_round]. The game removes every tower that stood there (DestroyArea
    re-checks each one, docs/map_mechanics.md), so the bot has to forget
    them. None when nothing is destroyed in between."""
    if old_round is None or new_round is None or new_round <= old_round:
        return None
    by_id = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    gone = [aid for aid, first in dynamics(geom).vanish.items()
            if first is not None and old_round < first <= new_round and aid in by_id]
    if not gone:
        return None
    proj = Projection(model.playfield, aspect)
    mask = np.zeros(GRID[::-1], bool)
    for aid in gone:
        mask |= _poly_mask(by_id[aid]["polygons"], proj)
    return mask


def paint_paths(geom, proj, lanes=None, skip=()):
    """heat, t_sum, t_cnt grids from the map's (visible) bloon paths.

    Stretches where bloons cannot be hit (gates, tunnels, holes: the path's
    "invulnerable" ranges) get no heat, so no tower is placed to cover them;
    they still count for the progress scale. `lanes`, a bool grid, receives
    every lane cell including those stretches (no tower may stand on any).
    Paths in `skip` (idle_phase_paths: no bloon on them for now) get lanes
    but no heat, so no tower is placed to cover them."""
    w, h = GRID
    heat = np.zeros((h, w), np.float32)
    t_sum = np.zeros((h, w), np.float32)
    t_cnt = np.zeros((h, w), np.float32)
    for path in bloon_paths(geom):
        if path.get("hidden") or len(path["points"]) < 2:
            continue  # hidden = bloons out of sight (tunnels): towers cannot hit them
        idle = path.get("id") in skip
        cells = proj.to_cells(path["points"])
        seg = np.linalg.norm(np.diff(cells, axis=0), axis=1)
        dist = np.concatenate([[0.0], np.cumsum(seg)])
        a, b = _visible_span(cells)
        span = max(dist[b] - dist[a], 1e-6)
        hidden = path.get("invulnerable", [])
        for i in range(len(cells) - 1):
            p0 = tuple(int(round(v)) for v in cells[i])
            p1 = tuple(int(round(v)) for v in cells[i + 1])
            line = np.zeros((h, w), np.uint8)
            cv2.line(line, p0, p1, 1, TRACK_THICKNESS)
            on = line > 0
            if lanes is not None:
                lanes |= on
            if idle or _in_ranges(i, hidden) or _in_ranges(i + 1, hidden):
                continue   # bloons here cannot be hit (or none come for now)
            prog = float(np.clip(((dist[i] + dist[i + 1]) / 2 - dist[a]) / span, 0, 1))
            heat[on] = TRACK_HEAT
            t_sum[on] += prog
            t_cnt[on] += 1
    return heat, t_sum, t_cnt


def path_masks(geom, proj, skip=()):
    """One bool grid per bloon path: the cells where bloons on that path can
    be hit (the same cells paint_paths heats). A bloon follows one path from
    start to end, so on maps whose paths split (Firing Range's two lanes)
    the defence must be shared between these masks: a lane with no real
    tower on it leaks every bloon sent down it. Paths in `skip` (idle for
    now, idle_phase_paths) get no mask."""
    w, h = GRID
    out = []
    for path in bloon_paths(geom):
        if path.get("hidden") or len(path["points"]) < 2 or path.get("id") in skip:
            continue
        cells = proj.to_cells(path["points"])
        hidden = path.get("invulnerable", [])
        mask = np.zeros((h, w), np.uint8)
        for i in range(len(cells) - 1):
            if _in_ranges(i, hidden) or _in_ranges(i + 1, hidden):
                continue
            p0 = tuple(int(round(v)) for v in cells[i])
            p1 = tuple(int(round(v)) for v in cells[i + 1])
            cv2.line(mask, p0, p1, 1, TRACK_THICKNESS)
        if mask.any():
            out.append(mask > 0)
    return out


def _boss_paths(geom):
    """Ids of the paths only boss bloons take (a splitter's overrideBossPath
    or a path it tags "Boss"). No boss comes in the bot's games."""
    out = set()
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if s.get("overrideBossPath") is not None:
            out.add(s["overrideBossPath"])
        for p, tag in zip(s.get("paths") or [], s.get("tagOnlyPath") or []):
            if tag == "Boss":
                out.add(p)
    return out


def path_round_shares(geom):
    """{path id: share of the rounds whose bloons take it} for the paths an
    AlternateRoundSplitter hands a new round every round; {} on maps without
    one. Paths not listed carry bloons every round.

    roundsPerPath 0 (or 1) means the next path every round: every map but
    Erosion (18-round phases, see idle_phase_paths) stores 0, and the guides
    agree - Last Resort runs a 4-round cycle (big loop, medium loop, small
    loop, straight), Luminous Cove and Enchanted Glade alternate two lanes.
    A path listed twice gets two turns of the cycle: Muddy Puddles' order
    1, 2, 3, 4, 3, 2 gives Path2 and Path3 a third of the rounds each."""
    shares = {}
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if s.get("type") != "AlternateRoundSplitter":
            continue
        paths = list(s.get("paths") or [])
        if int(s.get("roundsPerPath") or 1) > 1 or len(paths) < 2:
            continue
        for p in paths:
            shares[p] = shares.get(p, 0.0) + 1.0 / len(paths)
    return shares


def paths_this_round(geom, rnd):
    """Path ids an AlternateRoundSplitter hands round `rnd` (the round the
    game shows, 1 = the first): one per splitter. An empty frozenset when
    the map has no such splitter or rnd is unknown; paths no alternating
    splitter lists carry every round and are not in it.

    Every-round splitters (roundsPerPath 0 or 1) take the next path each
    round, starting with the first listed on round 1: Last Resort's
    [Path1, Path2, Path3, Path4] gives round mod 4 = 1 the big loop, 2 the
    medium, 3 the small one and 0 the straight (docs/backlog.md item 72),
    and Luminous Cove's [PathLeftStart, PathRightStart] odd rounds on the
    left (docs/map_strategies.md). Long phases (Erosion) are counted as in
    idle_phase_paths."""
    if rnd is None:
        return frozenset()
    out = set()
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if s.get("type") != "AlternateRoundSplitter":    # (multi-path splitters send several at once)
            continue
        n, paths = int(s.get("roundsPerPath") or 1), list(s.get("paths") or [])
        if len(paths) < 2:
            continue
        offset = int(s.get("currentRoundOffset") or 0)
        if n < 2:
            out.add(paths[(rnd - 1 - offset) % len(paths)])
            continue
        i = max(0, (rnd - offset) // n)             # same count as idle_phase_paths
        out.add(paths[min(i, len(paths) - 1) if s.get("doesNotLoop") else i % len(paths)])
    return frozenset(out)


def round_share(geom, proj, skip=()):
    """Float grid: on each cell where bloons can be hit (the cells
    path_masks marks), the share of the rounds whose bloons pass it, 0..1.
    None when every path carries bloons every round (path_round_shares is
    empty), so callers keep the plain track.

    Why: placement used to value every track cell alike. On Last Resort the
    four routes of the 4-round cycle all enter along the top straight and
    leave along it, and three of them loop down the map in between. The big
    loop's cells (a quarter of the rounds) outnumber the top straight's
    (every round), so every short-range tower went to the walkway beside the
    big loop's bottom row, out of reach of three rounds in four: Medium was
    lost at rounds 16 and 19 (2026-11-10, obyn_druid_poplust and
    hard_ninja_alch_sniper, Fast Track start at round 15: the small-loop,
    straight and medium-loop rounds 15, 16 and 18 leaked 129 lives). Weighted
    by this grid the top straight counts four times a loop cell.

    A cell on a path no alternating splitter lists (a shared tail after the
    alternating starts) carries every round: 1. Boss-only paths and paths in
    `skip` (idle for now, idle_phase_paths) are left out."""
    shares = path_round_shares(geom)
    if not shares:
        return None
    w, h = GRID
    alternating = np.zeros((h, w), np.float32)
    always = np.zeros((h, w), bool)
    boss = _boss_paths(geom)
    for path in bloon_paths(geom):
        pid = path.get("id")
        if path.get("hidden") or len(path["points"]) < 2 or pid in skip or pid in boss:
            continue
        cells = proj.to_cells(path["points"])
        hidden = path.get("invulnerable", [])
        mask = np.zeros((h, w), np.uint8)
        for i in range(len(cells) - 1):
            if _in_ranges(i, hidden) or _in_ranges(i + 1, hidden):
                continue
            p0 = tuple(int(round(v)) for v in cells[i])
            p1 = tuple(int(round(v)) for v in cells[i + 1])
            cv2.line(mask, p0, p1, 1, TRACK_THICKNESS)
        on = mask > 0      # a cell the path crosses twice still counts once per round
        if pid in shares:
            alternating[on] += shares[pid]
        else:
            always |= on
    out = np.minimum(alternating, 1.0)
    out[always] = 1.0
    return out


def blimp_track(geom, proj, skip=()):
    """Bool grid of the track MOAB-class bloons ride, or None when they ride
    all of it (most maps).

    Some maps send blimps their own way with a MoabOnlySplitter (Workshop's
    chute drops them onto the belt past its middle; Dark Dungeons, Castle
    Revenge and Quiet Street have MOAB lanes). The routes and their classes
    come from dps_model.map_routes, which reads those splitters; this paints
    the paths of every route that is not for non-MOAB bloons only. A blimp
    answer scored on the whole track can stand where no blimp ever passes:
    Workshop ABR (case 20261109_044354) put its MOAB answer at the entrance,
    x 0.02, while the blimps' route is only x 0.57-0.85, and lost round 40.
    Paths in `skip` (idle for now, idle_phase_paths) are left out."""
    from .dps_model import map_routes     # (dps_model imports this module)
    routes, _ = map_routes(geom)
    if not any(r.get("moab") is not None for r in routes):
        return None                       # no class has a route of its own
    ids = {pid for r in routes if r.get("moab") is not False for pid in r["paths"]}
    by_id = {p["id"]: p for p in geom.get("paths", [])}
    w, h = GRID
    mask = np.zeros((h, w), np.uint8)
    for pid in ids - set(skip):
        path = by_id.get(pid)
        if path is None or path.get("hidden") or len(path.get("points") or ()) < 2:
            continue
        cells = proj.to_cells(path["points"])
        hidden = path.get("invulnerable", [])
        for i in range(len(cells) - 1):
            if _in_ranges(i, hidden) or _in_ranges(i + 1, hidden):
                continue
            p0 = tuple(int(round(v)) for v in cells[i])
            p1 = tuple(int(round(v)) for v in cells[i + 1])
            cv2.line(mask, p0, p1, 1, TRACK_THICKNESS)
    return mask > 0 if mask.any() else None


# ---------------------------------------------------------------------------
# Map mechanics: what changes during a game, and when
# ---------------------------------------------------------------------------
#
# gamefiles.py stores each map's events as the game writes them: "when these
# TRIGGERS fire, do these ACTIONS". Here they are sorted into what will
# happen by itself (and so must be planned for) and what only the player can
# set off (buying an obstacle, clicking a statue), which happens only if the
# bot chooses to.

RULES_VERSION = 2   # bump when the interpretation below changes (re-measures mapfit)

# Triggers that fire without any player action (rounds passing, time, the
# map loading, bloons spawning or leaking, the bot's own tower placement).
# Anything unknown counts as automatic too: assuming a change can happen is
# the safe side.
PLAYER_TRIGGERS = {
    "RemoveableSoldTrigger",               # an obstacle was bought
    "InteractableClickTrigger",            # a click on a map object
    "InteractableClickSequenceTrigger",    # a sequence of such clicks
    "RepeatableTrigger",                   # a paid switch (RegenRemovable) bought
    "DarkDungeonsStatueActiveTrigger",     # Dark Dungeons' $30,000 statue
    "EncryptedTrigger",                    # Encrypted's easter egg
    "RoundRemoveableStartedTrigger",       # mining an ore started
    # Restores a paid switch's state when a saved game is loaded. It only
    # replays what a player bought, and the bot never buys switches, so it
    # is a player trigger too. (Counted as "may happen any time" until
    # 2026-11-04, it switched on Ancient Portal's walled left lane: the bot
    # put both ninjas on that empty spiral and lost ABR at round 23.)
    "OnMapLoadedWithActiveRegenRemovableTrigger",
}
# Triggers that fire once while the map loads, before round 1.
AT_START_TRIGGERS = {"StartMapTrigger", "OnMapCreatedTrigger"}

# Area changes made by actions: action type -> (field with the area ids, effect)
AREA_ACTIONS = {
    "CreateAreaAction": ("area", "appear"),
    "CreateAreasAction": ("areas", "appear"),
    "DestroyAreaAction": ("area", "vanish"),
    "DestroyAreasAction": ("areas", "vanish"),
    "CycleAreasAction": ("areas", "cycle"),
}

# A tower on a moving area is carried along. Spots that move at most this
# far (world units, about a small tower's footprint radius) count as steady.
STEADY_DRIFT = 6.0


def _ids(value):
    """A reference field (one id or a list of ids) as a list of ids."""
    if value is None:
        return []
    return [v for v in value if v] if isinstance(value, list) else [value]


def _trigger_timing(t):
    """(automatic, first round it can matter, recurring) for one trigger.

    The round is the first round of play the change can affect: a change
    after round 18 affects round 19 on. 0 = before round 1 (at map load);
    None = any time (time-based, a bloon spawning, the bot's towers...)."""
    kind = t.get("type", "")
    if kind in PLAYER_TRIGGERS:
        return False, None, False
    if kind in AT_START_TRIGGERS:
        return True, 0, False
    if kind in ("StartRoundTrigger", "AfterRoundTrigger"):
        r, n = t.get("round", 0) or 0, t.get("everyNthRound", 0) or 0
        after = 1 if kind == "AfterRoundTrigger" else 0
        if t.get("usePrimeNumbers"):
            return True, 2 + after, True
        if n > 0:
            return True, max(r, n if r <= 0 else r) + after, True
        return True, max(r, 0) + after, False
    return True, None, True


def _describe_trigger(t, names):
    """Human words for a trigger ("after round 18", "every round", ...)."""
    kind = t.get("type", "").replace("Trigger", "")
    r, n = t.get("round", 0) or 0, t.get("everyNthRound", 0) or 0
    if kind in ("StartRound", "AfterRound"):
        word = "start of" if kind == "StartRound" else "after"
        if t.get("usePrimeNumbers"):
            return f"{word} every prime-numbered round"
        if n > 0:
            every = "every round" if n == 1 else f"every {n} rounds"
            return f"{word} {every}" + (f" from round {r}" if r > 1 else "")
        return f"{word} round {r}"
    if kind == "RemoveableSold":
        return f"obstacle bought: {names.get(t.get('removeable'), t.get('removeable'))}"
    if kind in ("InteractableClick", "InteractableClickSequence"):
        return "player clicks a map object"
    if kind == "Repeatable":
        return f"paid switch bought: {names.get(t.get('triggeredBy'), t.get('triggeredBy'))}"
    if kind == "PreBloonSpawn":
        return f"first {t.get('bloonTag', 'bloon')} spawn"
    if kind == "SimTimeElapsed":
        return f"{t.get('time')} s of play"
    if kind in ("StartMap", "OnMapCreated"):
        return "map start"
    if kind == "LivesLowerThan":
        return "lives running low"
    if kind in ("TowerPlaced", "TowerInArea"):
        return f"a {t.get('towerId')} {t.get('tiers')} placed"
    return kind[:1].lower() + "".join(" " + c.lower() if c.isupper() else c for c in kind[1:])


def _curve(keys, t):
    """Value of a Unity AnimationCurve (keyframes [time, value, in, out]) at t:
    cubic Hermite between keyframes, flat outside them."""
    if not keys:
        return 0.0
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for (t0, v0, _, out0), (t1, v1, in1, _) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            dt = max(t1 - t0, 1e-9)
            s = (t - t0) / dt
            return ((2 * s ** 3 - 3 * s ** 2 + 1) * v0 + (s ** 3 - 2 * s ** 2 + s) * dt * out0
                    + (-2 * s ** 3 + 3 * s ** 2) * v1 + (s ** 3 - s ** 2) * dt * in1)
    return keys[-1][1]


def _mover_poses(action, areas_by_id):
    """[(dx, dz, degrees, cx, cz), ...]: every position a moving area takes,
    other than the one the scene holds it in, as a rotation by `degrees` about (cx, cz)
    followed by a shift (dx, dz). Rotations are as in Unity: positive turns
    clockwise seen from above."""
    kind = action["type"]
    if kind == "RotateAreaAction":
        area = areas_by_id.get(action.get("area"))
        if not area:
            return []
        step = float(action.get("rotation") or 0.0)
        if abs(step) < 1e-6:
            return []
        # after k turns it has turned k*step; the positions repeat once k*step
        # is a whole number of turns (45 deg -> 8 positions, 108 deg -> 10)
        k_max = 360 // math.gcd(int(round(abs(step))) or 1, 360) if abs(step - round(step)) < 1e-6 else 36
        cx, cz = (area.get("pivot") or area.get("origin") or [0.0, 0.0])[:2]
        return [(0.0, 0.0, k * step, cx, cz) for k in range(1, k_max)]
    if kind == "MovingPlatformAction":
        poses = _platform_state_poses(action, areas_by_id)
        # the scene's own pose needs no entry
        return [p for _, p in sorted(poses.items()) if any(abs(v) > 1e-6 for v in p[:3])]
    return []


# Sanctuary's two swinging platforms (PlatformLH1, PlatformRH1: the only
# MovingPlatformAction curves that also turn the platform, yRotCurve) do not
# go where their x/z curves say. Measured in the recordings of 2026-11-09
# (Medium game, rounds 15-59, platform stone found on screen per state;
# tools/measure_platforms.py): every state sits where the curve's shift
# lands after turning it PLATFORM_ARM_TURN degrees towards the map's top
# (counter-clockwise for the right arm, clockwise for the left one, as seen
# on screen) and shrinking it by PLATFORM_ARM_SCALE - within 4 world units
# for all eight states, against 25-40 units off as read. The curves are
# most likely kept in a parent transform that is turned and scaled; the
# other four platforms only shift, and their curves fit as read.
PLATFORM_ARM_TURN = 28.0
PLATFORM_ARM_SCALE = 0.84


def _platform_state_poses(action, areas_by_id):
    """{state: pose (dx, dz, degrees, cx, cz)} for every state a
    MovingPlatformAction takes its areas to, measured from the scene.

    The scene holds each platform where its animation clip is at time 0,
    not in its starting state: where a curve is absolute, its time-0 value
    is the area's own origin (Sanctuary: PlatformCentreTop x -26.56 vs
    origin -26.3, PlatformLH2 (-68.8, -74.9) vs (-70.06, -73.15),
    PlatformCentreBottom x -14.8 vs -14.76), while the starting state is
    elsewhere (CentreTop starts in state 1, x = 0). So every state the
    platform takes - the starting one included - is a shift from time 0.
    (Measured from the starting state instead, CentreTop's swept ground lay
    26.5 units too far left.) The state at time 0 has the zero pose."""
    moved = [areas_by_id[i] for i in _ids(action.get("areasToMove")) if i in areas_by_id]
    times = action.get("stateTimes") or []
    if not moved or not times:
        return {}
    start = int(action.get("startingState", 0))
    states = {start} | set(action.get("triggerNumToStateNum") or [])
    cx, cz = (moved[0].get("origin") or [0.0, 0.0])[:2]
    xs, zs, rs = (action.get(k) or [] for k in ("xPosCurve", "zPosCurve", "yRotCurve"))
    out = {}
    for s in sorted(states):
        t = times[min(s, len(times) - 1)]
        dx, dz = _curve(xs, t) - _curve(xs, 0.0), _curve(zs, t) - _curve(zs, 0.0)
        if rs:   # a swinging arm (see PLATFORM_ARM_TURN)
            a = math.radians(PLATFORM_ARM_TURN) * (1.0 if cx > 0 else -1.0)
            dx, dz = (PLATFORM_ARM_SCALE * (dx * math.cos(a) - dz * math.sin(a)),
                      PLATFORM_ARM_SCALE * (dx * math.sin(a) + dz * math.cos(a)))
        out[s] = (dx, dz, _curve(rs, t) - _curve(rs, 0.0), cx, cz)
    return out


def platform_state(mover, rnd):
    """State a moving platform (a dynamics() mover with "seq") stands in
    while round `rnd` is being played. The state changes when a round
    starts (StartRoundTrigger, every round from round 1): round r takes
    seq[(r - 1) % len(seq)], counted from round 1 whatever round the game
    started at. Before Play of a game's first round the platforms stand as
    in the round before it (a Fast Track game waits at round 15 in round
    14's state), and between rounds as in the round just played: the round
    to ask about is the last one STARTED (see Executor._pose_round).
    Confirmed on screen for every round of two games (2026-11-09, Medium
    and Reverse, rounds 15-59) and before Play at round 15."""
    seq = mover.get("seq") or []
    first = mover.get("first_round") or 1
    if not seq or rnd is None or rnd < first:
        return mover.get("start", 0)
    return seq[(rnd - first) % len(seq)]


def _pose_matrix(pose):
    """3x3 matrix of a pose: a tuple (dx, dz, degrees, cx, cz) or a matrix."""
    if isinstance(pose, np.ndarray):
        return pose
    dx, dz, deg, cx, cz = pose
    a = math.radians(deg)
    rot = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    out = np.eye(3)
    out[:2, :2] = rot
    out[:2, 2] = np.array([cx, cz]) - rot @ np.array([cx, cz]) + np.array([dx, dz])
    return out


def relative_pose(base, pose):
    """Matrix taking points from pose `base` to pose `pose` (both measured
    from the scene): undo base, then apply pose."""
    return _pose_matrix(pose) @ np.linalg.inv(_pose_matrix(base))


def _pose_points(xz, pose):
    """Move world points (array [..., 2]) to one pose: a tuple (dx, dz,
    degrees, cx, cz), or a 3x3 matrix (relative_pose)."""
    if isinstance(pose, np.ndarray):
        xz = np.asarray(xz, float)
        return xz @ pose[:2, :2].T + pose[:2, 2]
    dx, dz, deg, cx, cz = pose
    a = math.radians(deg)
    x, z = xz[..., 0] - cx, xz[..., 1] - cz
    # Unity's yaw: x' = x cos a + z sin a, z' = -x sin a + z cos a
    return np.stack([cx + x * math.cos(a) + z * math.sin(a) + dx,
                     cz - x * math.sin(a) + z * math.cos(a) + dz], axis=-1)


def _pose_polygons(polygons, pose):
    out = []
    for poly in polygons:
        p = np.asarray(poly, float)
        moved = _pose_points(p[:, :2], pose)
        out.append(np.concatenate([moved, p[:, 2:]], axis=1).tolist())
    return out


class Dynamics:
    """What a map's events do over a game (see dynamics())."""

    def __init__(self):
        self.present = set()   # area ids present at the start (after certain changes)
        self.appear = {}       # area id -> first round it may appear (automatic)
        self.vanish = {}       # area id -> first round it may disappear (automatic)
        self.retype = {}       # area id -> surface type after an obstacle was bought
        self.movers = []       # [{"type", "areas": [ids], "poses": [...], "first_round"}]
        self.suspend = {}      # area id -> first round towers on it are switched off
        self.paths_on = set()  # path ids switched on by the map itself
        self.sold = set()      # removable ids bought (asked for, or sold along with them)
        self.offered = {}      # removable id -> first round it can be bought
        self.fired = {}        # event id -> (automatic, first round, certain)
        self.panes = []        # timed pane cycles, see _pane_cycle_of()
        self.pose_round = None # last round started, when platforms are posed for it


def _pane_cycle_of(act, areas_by_id):
    """A cycle of panes: a CycleAreasAction with `invert` over plain
    unplaceable areas - all of them there but one, the gap moving one step
    along the list every `roundsPerRotate` rounds (Covered Garden's four
    glass panes). Towers under a pane stay when it closes; while it is
    closed they cannot be clicked (placed, upgraded, sold). Returns
    {"areas": [ids in cycle order], "per": rounds per step, "start"} or None.

    The order is the game's: Covered Garden lists LowerLeft, UpperLeft,
    UpperRight, LowerRight, and the guides say the bottom-left quarter is
    open on round 1 and the open one moves clockwise every round."""
    if act.get("type") != "CycleAreasAction" or not act.get("invert"):
        return None
    ids = [i for i in _ids(act.get("areas")) if i in areas_by_id]
    if len(ids) < 2 or any(areas_by_id[i]["type"] != "unplaceable" or areas_by_id[i].get("blocks_sight")
                           for i in ids):
        return None
    return {"areas": ids, "per": max(1, act.get("roundsPerRotate") or 1),
            "start": act.get("fromStartingRound") or 0}


def pane_open(cycle, rnd):
    """Index (in cycle["areas"]) of the pane open during round rnd (the
    round the HUD shows)."""
    return ((max(1, rnd) - 1 - cycle["start"]) // cycle["per"]) % len(cycle["areas"])


def dynamics(geom, sold=(), now_round=None, last_round=None, pose_round=None):
    """Sort a map's events into what happens during a game.

    sold:       removables the player buys (ids or names): their areas go,
                and the events their sale triggers fire.
    now_round:  the round being played: one-off changes due by then have
                certainly happened (One Two Tree's plots have opened).
    last_round: the game's last round: changes after it are left out
                (Erosion's late melts do not matter in a 40-round game).
    pose_round: the last round started, for maps with moving platforms
                (Sanctuary): each platform mover gets "base", the pose it
                stands in now, and its "poses" become the moves from there
                to its other states (see platform_state).
    Without these, every automatic change of the whole game is a "may"."""
    dyn = Dynamics()
    dyn.pose_round = pose_round
    mech = geom.get("mechanics") or {}
    areas = geom.get("areas", [])
    areas_by_id = {a["id"]: a for a in areas if "id" in a}
    dyn.present = starting_areas(geom)
    removables = {r["id"]: r for r in mech.get("removables", [])}
    by_name = {r["name"]: r["id"] for r in removables.values()}
    dyn.sold = {by_name.get(s, s) for s in sold}
    dyn.offered = {rid: 0 for rid, r in removables.items() if r.get("active", True)}
    events = {e["id"]: e for e in mech.get("events", [])}
    active = {eid for eid, e in events.items() if e.get("kind") == "event" and e.get("active", True)}
    activated_at = {}   # event id -> round another event switched it on

    # Seasonal decorations (Tricky Tracks' Halloween pumpkins) may be there.
    for a in areas:
        if a.get("seasonal") and "id" in a:
            dyn.appear.setdefault(a["id"], None)

    def actions_of(event, seen=()):
        """Actions of an event, with called MapActions lists expanded."""
        for act in event.get("actions", []):
            if act.get("type") == "TriggerMapActionsAction":
                target = events.get(act.get("mapActions"))
                if target and target["id"] not in seen:
                    yield from actions_of(target, (*seen, target["id"]))
            else:
                yield act

    def can_fire(event):
        """(fires, automatic, first round, recurring) for an active event."""
        results = []
        for t in event.get("triggers", []):
            if t.get("type") == "RemoveableSoldTrigger" and t.get("removeable") in dyn.sold:
                results.append((True, True, 0, False))
                continue
            auto, first, recurring = _trigger_timing(t)
            results.append((auto, auto, first, recurring))
        if not results:
            return False, False, None, False
        ok = [r for r in results if r[0]]
        if event.get("all_triggers"):
            if len(ok) < len(results):
                return False, False, None, False
            firsts = [r[2] for r in ok if r[2] is not None]
            return True, True, max(firsts) if firsts else None, any(r[3] for r in ok)
        if not ok:
            return False, False, None, False
        firsts = [r[2] for r in ok]
        first = None if None in firsts else min(firsts)
        return True, True, first, all(r[3] for r in ok)

    changed = True
    while changed:   # events switch other events on and sell obstacles: repeat until stable
        changed = False
        for eid in sorted(active - set(dyn.fired)):
            event = events[eid]
            fires, auto, first, recurring = can_fire(event)
            if not fires:
                continue
            if eid in activated_at:
                first = activated_at[eid] if first is None else max(first, activated_at[eid] or 0)
            sold_trigger = any(t.get("type") == "RemoveableSoldTrigger" and t.get("removeable") in dyn.sold
                               for t in event.get("triggers", []))
            certain = (first == 0 and not recurring) or sold_trigger or (
                now_round is not None and first is not None and first <= now_round
                and event.get("one_time") and not recurring)
            if last_round is not None and first is not None and first > last_round and not sold_trigger:
                continue   # after the game is over
            dyn.fired[eid] = (auto, first, certain)
            changed = True
            for act in actions_of(event):
                kind = act.get("type")
                if kind == "MapEventActiveAction" and act.get("setToActive"):
                    target = act.get("mapEvent")
                    if target in events and target not in active:
                        active.add(target)
                        activated_at[target] = first
                elif kind == "SellRemoveableAction":
                    dyn.sold |= set(_ids(act.get("removeable")))
                elif kind == "RemovableActiveAction" and act.get("setActiveToo"):
                    for rid in _ids(act.get("removeable")):
                        dyn.offered.setdefault(rid, first)
                elif kind in ("PathActiveAction",) and act.get("setActiveToo"):
                    dyn.paths_on |= set(_ids(act.get("path")))
                elif kind == "ToggleSplitterAction":
                    dyn.paths_on |= set(_ids(act.get("pathsToActivate")))

    # what the fired events do to areas
    for eid, (auto, first, certain) in dyn.fired.items():
        for act in actions_of(events[eid]):
            kind = act.get("type")
            cycle = _pane_cycle_of(act, areas_by_id) if auto else None
            if cycle:
                dyn.panes.append(cycle)
                if now_round is not None and now_round >= 1:
                    # the round is known: exactly one pane is open now, and
                    # the ground under it takes towers this round (they stay
                    # when the pane closes again)
                    shut = set(cycle["areas"]) - {cycle["areas"][pane_open(cycle, now_round)]}
                    dyn.present = (dyn.present - set(cycle["areas"])) | shut
                    continue
            if kind in AREA_ACTIONS:
                field, effect = AREA_ACTIONS[kind]
                ids = [i for i in _ids(act.get(field)) if i in areas_by_id]
                for aid in ids:
                    if effect == "cycle":
                        dyn.appear.setdefault(aid, first)
                        dyn.vanish.setdefault(aid, first)
                    elif certain:
                        (dyn.present.add if effect == "appear" else dyn.present.discard)(aid)
                    else:
                        (dyn.appear if effect == "appear" else dyn.vanish).setdefault(aid, first)
            elif kind == "SetAreaActiveAction":
                aid = act.get("area")
                if aid in areas_by_id:
                    on = bool(act.get("isActive"))
                    if certain:
                        (dyn.present.add if on else dyn.present.discard)(aid)
                    else:
                        (dyn.appear if on else dyn.vanish).setdefault(aid, first)
            elif kind in ("RotateAreaAction", "MovingPlatformAction"):
                poses = _mover_poses(act, areas_by_id)
                ids = _ids(act.get("area")) + _ids(act.get("areasToMove"))
                if poses:
                    mover = {"type": kind, "areas": [i for i in ids if i in areas_by_id],
                             "poses": poses, "first_round": first, "event": eid}
                    if kind == "MovingPlatformAction":
                        mover.update(seq=list(act.get("triggerNumToStateNum") or []),
                                     start=int(act.get("startingState", 0)),
                                     state_poses=_platform_state_poses(act, areas_by_id))
                        if pose_round is not None and mover["seq"]:
                            base = mover["state_poses"][platform_state(mover, pose_round)]
                            mover["base"] = base
                            mover["poses"] = [relative_pose(base, p) for s, p in
                                              sorted(mover["state_poses"].items()) if p != base]
                    dyn.movers.append(mover)
            elif kind == "SuspendTowersOnAreaAction" and not act.get("isUnsuspendAction"):
                if act.get("area") in areas_by_id:
                    dyn.suspend.setdefault(act["area"], first)

    # bought obstacles: their areas are deleted, or take the obstacle's
    # "after" type (as Map.DestroyRemoveable does)
    for rid in dyn.sold:
        r = removables.get(rid)
        if not r:
            continue
        for aid in r.get("areas", []):
            if r.get("destroy_area", True):
                dyn.present.discard(aid)
                dyn.appear.pop(aid, None)
            else:
                dyn.retype[aid] = r.get("after", "land")
    # an area that is certainly there and may go away, or certainly gone and
    # may come back, is a "may" both ways; nothing else needs untangling
    return dyn


def _surfaces(geom, masks):
    """(land_ok, water_ok, solid) from one state's area masks: the map's base
    surface, then the areas drawn on top (islands on water maps, ponds on land
    maps); track and obstacles win."""
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
    # A sight blocker is solid by its type (walls, rocks: "unplaceable"). A
    # blocker typed as land is raised ground a tower may stand on - Sunken
    # Columns' column tops, Mesa's plateaus: it blocks sight only for towers
    # below it. Treating it as solid left Sunken Columns with no spot that
    # could see the track (loss case 20261104_104816).
    solid = masks["track"] | masks["unplaceable"] | masks["removable"]
    return land_ok, water_ok, solid


SOLID_TYPES = ("track", "unplaceable", "removable")


def placement_grids(geom, proj, lanes=None, dyn=None):
    """Placement grids that hold through the whole game.

    Returns {"land", "water", "mermonkey_water": bool grids of cells where a
    tower's centre may stand for the whole game as far as the ground goes;
    "size_limit"; "sight": blockers that are there at any time, with
    "sight_height" how high they stand and "ground" how high the ground a
    tower stands on is (a tower sees over blockers no higher); "moving":
    cells on areas that carry towers around (gears, platforms) and "drift":
    how far (world units) each such cell travels; "unsafe": cells left out
    because the ground there changes (with "static_land"/"static_water", the
    starting state alone, to see what the changes cost)}.

    The map is checked in four states - as it starts, with everything that
    may appear, without everything that may vanish, and both - and a cell
    counts only if it is fine in all of them."""
    dyn = dyn or dynamics(geom)
    shape = GRID[::-1]
    appear, vanish = set(dyn.appear), set(dyn.vanish)
    states = [dyn.present, dyn.present | appear, dyn.present - vanish, (dyn.present | appear) - vanish]
    out = {k: np.ones(shape, bool) for k in ("land", "water", "mermonkey_water")}
    out["size_limit"] = np.full(shape, 4, np.uint8)
    out["sight"] = np.zeros(shape, bool)
    out["sight_height"] = np.full(shape, -np.inf, np.float32)
    lanes = np.zeros(shape, bool) if lanes is None else lanes
    for i, present in enumerate(states):
        masks = area_masks(geom, proj, present=present, retype=dyn.retype)
        land_ok, water_ok, solid = _surfaces(geom, masks)
        solid = solid | lanes   # drawn bloon lanes can poke past the track polygon on curves
        if i == 0:
            out["static_land"], out["static_water"] = land_ok & ~solid, water_ok & ~solid
            out["ground"] = masks["ground"]
            # cells an unplaceable sight blocker decides (walls, icicles,
            # rocks): the map file is surest about these (Executor._probe_spot)
            out["solid_blockers"] = masks["blockers"] & masks["unplaceable"]
        out["land"] &= land_ok & ~solid
        out["water"] &= water_ok & ~solid
        out["mermonkey_water"] &= masks["water_mermonkey"] & ~solid
        out["size_limit"] = np.minimum(out["size_limit"], masks["size_limit"])
        out["sight"] |= masks["sight"]
        out["sight_height"] = np.maximum(out["sight_height"], masks["sight_height"])

    # Moving areas: solid ones block every place they pass; ground ones carry
    # their towers, and the ground they pass over is no place for a tower
    # that stays put.
    areas_by_id = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    unsafe = np.zeros(shape, bool)
    moving = np.zeros(shape, bool)
    drift = np.zeros(shape, np.float32)
    carriers = []   # [(cells of a moving ground area, its poses)]
    wx, wz = proj.cell_world()
    world = np.stack([wx, wz], axis=-1)
    for mover in dyn.movers:
        # areas one action moves keep their places on each other (Sanctuary's
        # top platform carries two pools): a pool sweeping over its own
        # platform's ground never reaches the towers riding there
        together = np.zeros(shape, bool)
        for aid in mover["areas"]:
            together |= _poly_mask(areas_by_id[aid]["polygons"], proj)
        for aid in mover["areas"]:
            area = areas_by_id[aid]
            here = _poly_mask(area["polygons"], proj)
            swept = np.zeros(shape, bool)
            for pose in mover["poses"]:
                swept |= _poly_mask(_pose_polygons(area["polygons"], pose), proj)
            if area["type"] in SOLID_TYPES or area.get("blocks_sight"):
                for k in ("land", "water", "mermonkey_water"):
                    out[k] &= ~swept
                if area.get("blocks_sight"):
                    out["sight"] |= swept
                    out["sight_height"][swept] = np.maximum(out["sight_height"][swept], area_height(area))
            else:
                unsafe |= swept & ~together
                moving |= here
                carriers.append((here, mover["poses"]))
                far = np.zeros(shape, np.float32)
                for pose in mover["poses"]:
                    far = np.maximum(far, np.linalg.norm(_pose_points(world, pose) - world, axis=-1))
                drift = np.where(here, np.maximum(drift, far), drift)
    out["carriers"] = carriers
    # towers on these areas are switched off by the map (Polyphemus' eye)
    for aid in dyn.suspend:
        if aid in areas_by_id:
            unsafe |= _poly_mask(areas_by_id[aid]["polygons"], proj)
    for k in ("land", "water", "mermonkey_water"):
        out[k] &= ~unsafe
    out.update({"moving": moving, "drift": drift, "unsafe": unsafe})
    return out


def forget_pane_refusals(model, geom, aspect=1920 / 1200):
    """Refusals under a cycling pane were clicks on glass that was shut at
    the time (before the bot knew the cycle: 567 such cells on Covered
    Garden): they say nothing about the ground, so they are forgotten.
    Returns how many refused cells were dropped."""
    panes = dynamics(geom).panes
    if not panes:
        return 0
    proj = Projection(model.playfield, aspect)
    by_id = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    under = None
    for cycle in panes:
        for aid in cycle["areas"]:
            mask = _poly_mask(by_id[aid]["polygons"], proj)
            under = mask if under is None else under | mask
    dropped = 0
    for grid in getattr(model, "refused", {}).values():
        if grid is not None and grid.shape == under.shape:
            dropped += int((grid & under).sum())
            grid &= ~under
    if dropped:
        log.info("%s: forgot %d refused cells under the panes", model.name, dropped)
    return dropped


def forget_platform_refusals(model, geom, aspect=1920 / 1200):
    """Refusals on ground a moving platform covers at some time (Sanctuary:
    all of its ground) were clicks where the platform was not standing at
    that moment - the grids held it in the scene's pose until 2026-11-09 -
    so they say nothing about the ground and are forgotten: 944 of the 1,016
    refused land cells learned on Sanctuary were such clicks, half of its
    platform ground. Returns how many refused cells were dropped."""
    proj = Projection(model.playfield, aspect)
    ground = _platform_ground(_platform_info(geom, proj), proj)
    if ground is None:
        return 0
    dropped = 0
    for grid in getattr(model, "refused", {}).values():
        if grid is not None and grid.shape == ground.shape:
            dropped += int((grid & ground).sum())
            grid &= ~ground
    if dropped:
        log.info("%s: forgot %d refused cells on the moving platforms", model.name, dropped)
    return dropped


def apply(model, geom, aspect=1920 / 1200):
    """Overwrite a MapModel's track and placement grids from geometry.

    scan["land"] / scan["water"] hold the exact surfaces (1 = a land / water
    tower's centre may stand here as far as the ground goes, 2 = not), for
    the whole game: ground that changes during it is left out (see
    placement_grids). The room each tower's footprint needs is added per
    tower by placement.py. Spots the game refuses in play live in
    model.refused, which this function leaves alone, so re-applying the
    geometry never forgets them."""
    proj = Projection(model.playfield, aspect)
    lanes = np.zeros(GRID[::-1], bool)
    model.heat, model.t_sum, model.t_cnt = paint_paths(geom, proj, lanes)
    model.track_skip = frozenset()   # every path painted (repaint_track narrows it per round)
    grids = placement_grids(geom, proj, lanes | (model.heat > 0))
    model.scan["land"] = np.where(grids["land"], 1, 2).astype(np.uint8)
    model.scan["water"] = np.where(grids["water"], 1, 2).astype(np.uint8)
    model.mermonkey_water = grids["mermonkey_water"]
    model.size_limit = grids["size_limit"]
    model.small_only = grids["size_limit"] <= 1
    model.sight = grids["sight"]
    model.sight_height = grids["sight_height"]
    model.ground_height = grids["ground"]
    model.geometry_version = geom.get("version", 1)
    forget_pane_refusals(model, geom)
    forget_platform_refusals(model, geom)
    log.info("%s: geometry applied (%d paths, %d areas)", model.name,
             len(geom.get("paths", [])), len(geom.get("areas", [])))
    return model


def repaint_track(model, geom, rnd, reverse=False, aspect=1920 / 1200):
    """Repaint a model's track (heat, t_sum, t_cnt) for the path phase of
    round rnd (idle_phase_paths), leaving the placement grids alone.

    apply() paints every path, which suits maps whose paths all carry
    bloons; on Erosion that put the whole defence beside lanes no bloon
    takes before round 37 and lost Easy Primary Only on round 11. The match
    calls this as rounds pass; it does nothing (returns False) while the set
    of idle paths stays the same, and on maps without path phases.
    `reverse` mirrors the progress as runner._use_geometry does."""
    skip = idle_phase_paths(geom, rnd)
    if skip == getattr(model, "track_skip", frozenset()):
        return False
    proj = Projection(model.playfield, aspect)
    model.heat, model.t_sum, model.t_cnt = paint_paths(geom, proj, None, skip)
    if reverse:
        model.t_sum = np.where(model.t_cnt > 0, model.t_cnt - model.t_sum, 0).astype(np.float32)
    model.track_skip = skip
    names = {p["id"]: p["name"] for p in geom.get("paths", []) if "id" in p}
    live = [names[i] for i in names if i not in skip and i in {p["id"] for p in bloon_paths(geom)}]
    log.info("%s: round %s path phase - track painted for %s", model.name, rnd, ", ".join(live))
    return True


_GRIDS_CACHE = {}
_MAP_IDS = {}


def _geometry_file(model):
    """(path, mtime stamp) of a model's geometry file, or None."""
    id_key = (str(GEOMETRY_DIR), model.name)
    map_id = _MAP_IDS.get(id_key) or map_id_for(model.name)
    if map_id is None:
        return None   # (not remembered: the file may be extracted later)
    _MAP_IDS[id_key] = map_id
    path = GEOMETRY_DIR / f"{map_id}.json"
    try:
        return path, path.stat().st_mtime_ns
    except OSError:
        return None


_GEOM_CACHE = {}


def _geometry_of(path, stamp):
    """The parsed geometry file, kept: with its platforms followed,
    Sanctuary's is asked for on every placement."""
    key = (str(path), stamp)
    if key not in _GEOM_CACHE:
        try:
            geom = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if len(_GEOM_CACHE) > 8:
            _GEOM_CACHE.clear()
        _GEOM_CACHE[key] = geom
    return _GEOM_CACHE[key]


_PLATFORM_MOVERS = {}


def _platform_movers(geom):
    """dynamics() movers of the map's moving platforms (MovingPlatformAction
    with a state sequence), in a fixed order; [] on other maps."""
    key = id(geom)
    cached = _PLATFORM_MOVERS.get(key)
    if cached is None or cached[0] is not geom:
        movers = [m for m in dynamics(geom).movers if m["type"] == "MovingPlatformAction" and m.get("seq")]
        if len(_PLATFORM_MOVERS) > 16:
            _PLATFORM_MOVERS.clear()
        cached = _PLATFORM_MOVERS[key] = (geom, movers)
    return cached[1]


def _posed_geometry(geom, dyn):
    """A copy of geom with every platform that dyn poses (mover "base")
    drawn where it stands now."""
    posed = {}
    for mover in dyn.movers:
        if "base" in mover:
            for aid in mover["areas"]:
                posed[aid] = mover["base"]
    if not posed:
        return geom
    out = dict(geom)
    out["areas"] = [dict(a, polygons=_pose_polygons(a["polygons"], posed[a["id"]])) if a.get("id") in posed
                    else a for a in geom.get("areas", [])]
    return out


def grids_for(model, removed=(), now_round=None, last_round=None, pose_round=None):
    """placement_grids() for a model's map (cached), or None without
    geometry. removed: obstacles (names or ids) treated as bought;
    now_round / last_round: see dynamics(). pose_round: the last round
    started, on maps with moving platforms (Sanctuary): the platforms are
    drawn where they stand in it, so "land" is the ground under them now
    (towers ride along; finite-range ones still need steady spots, judged
    from there). Ignored on other maps. The grids hold "scan" as well, in
    MapModel.scan's form, so they can stand in for the model's own.
    Cheap to call again: the answer is kept until the geometry file changes."""
    found = _geometry_file(model)
    if found is None:
        return None
    path, stamp = found
    states = None
    if pose_round is not None:
        geom = _geometry_of(path, stamp)
        if geom is None:
            return None
        movers = _platform_movers(geom)
        if movers:   # one entry per layout of the platforms, not per round
            states = tuple(platform_state(m, pose_round) for m in movers)
        else:
            pose_round = None
    key = (str(path), stamp, tuple(model.playfield), frozenset(removed), now_round, last_round, states)
    if key not in _GRIDS_CACHE:
        geom = _geometry_of(path, stamp)
        if geom is None:
            return None
        if len(_GRIDS_CACHE) > 64:
            _GRIDS_CACHE.clear()
        proj = Projection(model.playfield)
        lanes = np.zeros(GRID[::-1], bool)
        skip = idle_phase_paths(geom, now_round)
        heat, _, _ = paint_paths(geom, proj, lanes, skip)
        dyn = dynamics(geom, removed, now_round, last_round, pose_round)
        grids = placement_grids(_posed_geometry(geom, dyn), proj, lanes | (heat > 0), dyn)
        grids["scan"] = {k: np.where(grids[k], 1, 2).astype(np.uint8) for k in ("land", "water")}
        grids["track"] = heat > 0
        grids["path_masks"] = path_masks(geom, proj, skip)
        # how many of the rounds pass each track cell (None: all of them)
        grids["round_share"] = round_share(geom, proj, skip)
        # where blimps can be hit, when they have a route of their own
        grids["blimp_track"] = blimp_track(geom, proj, skip)
        grids["proj"] = proj
        areas_by_id = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
        grids["panes"] = [(c, [_poly_mask(areas_by_id[i]["polygons"], proj) for i in c["areas"]])
                          for c in dyn.panes]
        grids["platforms"] = _platform_info(geom, proj)
        grids["platform_ground"] = _platform_ground(grids["platforms"], proj)
        grids["pose_round"] = pose_round
        grids["steady"] = {}
        _GRIDS_CACHE[key] = grids
    return _GRIDS_CACHE[key]


# ---------------------------------------------------------------------------
# Moving platforms (Sanctuary): where they stand, on screen and in the grids
# ---------------------------------------------------------------------------

def _platform_info(geom, proj):
    """[{name, mover, areas: [(area, height)], ground}] for each moving
    platform: its areas with their outline height (a tower on one is drawn
    that much higher, Projection.to_frac); `ground` when one of its areas
    takes towers (not a solid body)."""
    areas_by_id = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    events = {e["id"]: e for e in (geom.get("mechanics") or {}).get("events", []) if "id" in e}
    out = []
    for mover in _platform_movers(geom):
        parts = []
        for aid in mover["areas"]:
            area = areas_by_id[aid]
            heights = [pt[2] for poly in area["polygons"] for pt in poly if len(pt) > 2]
            parts.append((area, float(np.mean(heights)) if heights else 0.0))
        out.append({"name": events.get(mover.get("event"), {}).get("name") or str(mover.get("event")),
                    "mover": mover, "areas": parts,
                    "ground": any(a["type"] not in SOLID_TYPES and not a.get("blocks_sight")
                                  for a, _ in parts)})
    return out


def _platform_ground(platforms, proj):
    """Bool grid of every cell a platform that takes towers covers in any of
    its states, or None without platforms."""
    if not platforms:
        return None
    out = np.zeros(GRID[::-1], bool)
    for plat in platforms:
        for area, _ in plat["areas"]:
            if area["type"] in SOLID_TYPES or area.get("blocks_sight"):
                continue
            for pose in plat["mover"]["state_poses"].values():
                out |= _poly_mask(_pose_polygons(area["polygons"], pose), proj)
    return out


def platform_ground(model):
    """Bool grid of the cells some moving platform covers at some time
    (Sanctuary: all of its ground), or None on maps without platforms.
    A refusal there says where the platform was not at that moment, not
    that the ground is bad."""
    grids = grids_for(model)
    return grids.get("platform_ground") if grids else None


def has_platforms(model):
    """True on maps whose ground moves on platforms (Sanctuary)."""
    grids = grids_for(model)
    return bool(grids and grids.get("platforms"))


def _platform_pose_at(plat, rnd):
    """Pose (from the scene) of a platform while round `rnd` is played; the
    scene's own pose for rnd None."""
    if rnd is None:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    mover = plat["mover"]
    return mover["state_poses"][platform_state(mover, rnd)]


def _spot_world(proj, fx, fy, height):
    """Screen fractions -> world (x, z) of a point standing `height` up."""
    return (fx - proj.cx) / proj.ux, (proj.cy - fy) / proj.uy - HEIGHT_FACTOR * height


def _inside(polys, x, z):
    """True when world point (x, z) lies inside the outline (first polygon)
    and outside every hole (the rest)."""
    for i, poly in enumerate(polys):
        pts = np.asarray([p[:2] for p in poly], np.float32)
        if len(pts) < 3:
            continue
        inside = cv2.pointPolygonTest(pts, (float(x), float(z)), False) >= 0
        if i == 0 and not inside:
            return False
        if i > 0 and inside:
            return False
    return True


def platform_under(model, fx, fy, rnd):
    """(platform, height) of the moving platform that takes towers under
    screen spot (fx, fy) while round rnd is played (None: as in the scene),
    or (None, None). Where two cover the spot the higher one counts."""
    grids = grids_for(model)
    plats = grids.get("platforms") if grids else None
    if not plats:
        return None, None
    found = []
    for plat in plats:
        pose = _platform_pose_at(plat, rnd)
        for area, height in plat["areas"]:
            if area["type"] in SOLID_TYPES or area.get("blocks_sight"):
                continue
            if _inside(_pose_polygons(area["polygons"], pose), *_spot_world(grids["proj"], fx, fy, height)):
                found.append((height, id(plat), plat))
    if not found:
        return None, None
    height, _, plat = max(found, key=lambda f: f[:2])
    return plat, height


def carry_spot(model, fx, fy, from_round, to_round):
    """Where a spot (screen fractions) on a moving platform is while round
    to_round is played, given where it was in from_round (None = the scene,
    as a build's `at` spots are written). Spots off the platforms, and maps
    without them, come back unchanged."""
    plat, height = platform_under(model, fx, fy, from_round)
    if plat is None:
        return fx, fy
    return move_with_platform(model, plat, height, fx, fy, from_round, to_round)


def move_with_platform(model, plat, height, fx, fy, from_round, to_round):
    """Spot (screen fractions) on platform `plat` (from platform_under),
    standing `height` up, moved from where the platform is in from_round to
    where it is in to_round (None = the scene)."""
    proj = grids_for(model)["proj"]
    move = relative_pose(_platform_pose_at(plat, from_round), _platform_pose_at(plat, to_round))
    (nx, nz), = _pose_points(np.array([_spot_world(proj, fx, fy, height)], float), move)
    nfx, nfy = proj.to_frac([[nx, nz, height]])[0]
    return float(nfx), float(nfy)


# Reading the platforms off the screen: the stone of a platform's top is a
# dull yellow-olive (OpenCV HSV below); the water, vines and walls around
# it are not. Measured on the recordings of 2026-11-09: the outline of the
# state a platform is in held 55-85 % stone, the outlines of its other
# states 0-40 % (tools/measure_platforms.py).
STONE_HUE = (15, 35)            # OpenCV hue (0-180)
STONE_SAT = (60, 200)
STONE_VAL_MIN = 90
PANEL_X = 0.855                 # columns right of this (the tower list) are not looked at
PLATFORM_READ_MARGIN = 0.10     # the best layout must show this much more stone (share) than the next


def stone_mask(frame):
    """Bool image: pixels that look like platform stone."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h >= STONE_HUE[0]) & (h <= STONE_HUE[1]) & (s >= STONE_SAT[0]) & (s <= STONE_SAT[1])
            & (v >= STONE_VAL_MIN))


def platform_stone(model, frame, rnd):
    """Mean share of stone pixels inside the outlines of the platforms that
    take towers, drawn where they stand in round rnd (the tower list left
    out), or None on maps without platforms."""
    grids = grids_for(model)
    plats = grids.get("platforms") if grids else None
    if not plats or frame is None:
        return None
    if frame.shape[1] > 960:   # plenty to tell the layouts apart, and cheap
        frame = cv2.resize(frame, (960, int(round(frame.shape[0] * 960 / frame.shape[1]))),
                           interpolation=cv2.INTER_AREA)
    stone = stone_mask(frame)
    h, w = stone.shape
    proj = grids["proj"]
    shares = []
    for plat in plats:
        pose = _platform_pose_at(plat, rnd)
        mask = np.zeros((h, w), np.uint8)
        for area, _ in plat["areas"]:
            if area["type"] != "land":
                continue
            for i, poly in enumerate(_pose_polygons(area["polygons"], pose)):
                pts = np.round(proj.to_frac(np.asarray(poly))[:, :2] * [w, h]).astype(np.int32)
                cv2.fillPoly(mask, [pts], 1 if i == 0 else 0)
        mask[:, int(w * PANEL_X):] = 0
        if mask.any():
            shares.append(float(stone[mask > 0].mean()))
    return float(np.mean(shares)) if shares else None


def platform_round_on_screen(model, frame, candidates):
    """Which of the candidate rounds the platforms on screen stand as in,
    or None when the frame does not say clearly (the best layout shows less
    than PLATFORM_READ_MARGIN more stone than the next) or the map has no
    platforms. Candidates whose layouts are the same count as one (the
    first of them is returned)."""
    grids = grids_for(model)
    plats = grids.get("platforms") if grids else None
    if not plats or frame is None:
        return None
    scored = {}
    for rnd in candidates:
        if rnd is None:
            continue
        layout = tuple(platform_state(p["mover"], rnd) for p in plats)
        if layout not in scored:
            share = platform_stone(model, frame, rnd)
            if share is None:
                return None
            scored[layout] = (share, rnd)
    if not scored:
        return None
    ranked = sorted(scored.values(), key=lambda v: -v[0])
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < PLATFORM_READ_MARGIN:
        return None
    return ranked[0][1]


def pane_ground(model):
    """Bool grid (model cells) of the ground under any cycling pane, or None
    on maps without panes. A tower standing there can be clicked only in
    its pane's rounds (pane_at)."""
    grids = grids_for(model)
    panes = grids.get("panes") if grids else None
    if not panes:
        return None
    out = None
    for _, masks in panes:
        for mask in masks:
            out = mask.copy() if out is None else (out | mask)
    return out


def pane_at(model, fx, fy, rnd):
    """For a spot (screen fractions) under a cycling pane: (pane index, open
    during round rnd). (None, True) for ground no pane covers, and on maps
    without panes. A tower there can be clicked - upgraded, sold - only
    while its pane is open."""
    grids = grids_for(model)
    panes = grids.get("panes") if grids else None
    if not panes:
        return None, True
    cx, cy = model.frac_to_cell(fx, fy)
    for cycle, masks in panes:
        for i, mask in enumerate(masks):
            if 0 <= cy < mask.shape[0] and 0 <= cx < mask.shape[1] and mask[cy, cx]:
                return i, rnd is not None and pane_open(cycle, rnd) == i
    return None, True


# Reading the open pane off the screen (Covered Garden). A shut pane is drawn
# as glass with a white grid; the open one shows the ground without it. In the
# live game of 2026-11-07 (recordings rec_20261107_2035-2039, 1280x800) each
# shut quarter showed 12 one-pixel columns of white grid line (6 where the
# upgrade panel hid half of it) and the open quarter none.
PANE_INSET = (0.10, 0.15)       # share of a quarter's box left out at each side (x, y): its frame
PANE_WHITE_V, PANE_WHITE_S = 225, 40   # HSV: a grid-line pixel is this bright and this grey
PANE_LINE_SHARE = 0.6           # a column is grid line when this share of it is white
PANE_OPEN_MAX = 1               # grid columns (per 1280 px of frame width) an open quarter may show
PANE_SHUT_MIN = 3               # ... and a shut one at least shows


def pane_line_columns(model, frame):
    """[grid-line columns in each pane quarter] of a game frame (BGR, any
    size), in cycle order, or None on maps without panes. Columns are
    counted inside each pane's box (its outline, inset by PANE_INSET) and
    scaled to a 1280 px wide frame."""
    grids = grids_for(model)
    panes = grids.get("panes") if grids else None
    if not panes or frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = (hsv[..., 2] > PANE_WHITE_V) & (hsv[..., 1] < PANE_WHITE_S)
    h, w = white.shape
    out = []
    for mask in panes[0][1]:
        rows, cols = np.nonzero(mask)
        (x0, y0), (x1, y1) = (model.cell_to_frac(int(cols.min()), int(rows.min())),
                              model.cell_to_frac(int(cols.max()), int(rows.max())))
        ix, iy = (x1 - x0) * PANE_INSET[0], (y1 - y0) * PANE_INSET[1]
        sub = white[int((y0 + iy) * h):int((y1 - iy) * h), int((x0 + ix) * w):int((x1 - ix) * w)]
        lines = int((sub.mean(axis=0) > PANE_LINE_SHARE).sum()) if sub.size else 0
        out.append(lines * 1280.0 / w)
    return out


def pane_open_on_screen(model, frame):
    """Index (in cycle order) of the pane the screen shows open, or None when
    the frame does not say clearly: exactly one quarter must show no grid
    and every other quarter a grid.

    Why the screen and not the round: while a tower's side panel is open it
    covers the HUD round counter, the bot's round number goes stale, and on
    2026-11-07 (20:37:21-20:38:33) it went on clicking the shut bottom-left
    pane for over a minute while the top-left one was open. The side panel
    hides at most half of the right quarters, so they still show grid."""
    counts = pane_line_columns(model, frame)
    if not counts:
        return None
    open_ = [i for i, c in enumerate(counts) if c <= PANE_OPEN_MAX]
    shut = [i for i, c in enumerate(counts) if c >= PANE_SHUT_MIN]
    if len(open_) == 1 and len(shut) == len(counts) - 1:
        return open_[0]
    return None


def round_for_open_pane(model, index, rnd):
    """The round nearest at or after `rnd` (1 when unknown) whose open pane
    is `index`: a round number consistent with what the screen shows, for
    the code that judges panes by round. The bot's own round lags behind
    when it is stale, so the search goes forward; one cycle covers every pane."""
    grids = grids_for(model)
    panes = grids.get("panes") if grids else None
    if not panes or index is None:
        return rnd
    cycle = panes[0][0]
    base = max(1, rnd or 1)
    for r in range(base, base + len(cycle["areas"]) * max(1, cycle["per"])):
        if pane_open(cycle, r) == index:
            return r
    return rnd


# A tower on moving ground (a gear, a platform) is carried to other places
# during the game, and the track it covers changes with it. Such a spot is
# used only if, wherever the ground takes it, it still covers at least this
# share of the track it covers now (and some track).
STEADY_KEEP = 0.6


def _disc(radius_cells):
    r = max(1, int(round(radius_cells)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _posed_cells(grids, cells_mask, pose):
    """Grid (row, col) where the cells of `cells_mask` end up in a pose."""
    proj = grids["proj"]
    wx, wz = proj.cell_world()
    pts = np.stack([wx[cells_mask], wz[cells_mask]], axis=-1)
    moved = _pose_points(pts, pose)
    cells = proj.to_cells(np.concatenate([moved, np.zeros((len(moved), 1))], axis=1))
    return np.floor(cells[:, 1]).astype(int), np.floor(cells[:, 0]).astype(int)


def steady_spots(model, reach_units, pose_round=None):
    """Bool grid of moving-ground cells (see placement_grids' "moving") where
    a tower with this reach (world units) keeps covering the track wherever
    the ground carries it (STEADY_KEEP), plus moving cells that barely move
    (STEADY_DRIFT). pose_round: platforms where they stand in that round
    (grids_for). None on maps without moving ground."""
    grids = grids_for(model, pose_round=pose_round)
    if grids is None or not grids["moving"].any():
        return None
    key = round(float(reach_units or 0.0), 1)
    if key not in grids["steady"]:
        track = grids["track"].astype(np.float32)
        h, w = track.shape
        # number of track cells within reach of every cell
        count = cv2.filter2D(track, -1, _disc(grids["proj"].units_to_cells(key)).astype(np.float32),
                             borderType=cv2.BORDER_CONSTANT)
        steady = grids["moving"] & (grids["drift"] <= STEADY_DRIFT)
        for here, poses in grids["carriers"]:
            now = count[here]
            worst = now.copy()
            for pose in poses:
                rows, cols = _posed_cells(grids, here, pose)
                inside = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
                there = np.zeros(len(rows), np.float32)
                there[inside] = count[rows[inside], cols[inside]]
                worst = np.minimum(worst, there)
            ok = (worst > 0) & (worst >= STEADY_KEEP * now)
            cells = np.zeros_like(here)
            cells[here] = ok
            steady |= cells
        grids["steady"][key] = steady
    return grids["steady"][key]


def reliable_reach(model, spots, reach_units, targets):
    """Target cells (bool grid) that some cell of `spots` reaches in every
    position the moving ground takes it to (cells not on moving ground reach
    from where they are). Used to measure coverage on Geared and Sanctuary."""
    grids = grids_for(model)
    proj = grids["proj"] if grids is not None else Projection(model.playfield)
    radius = proj.units_to_cells(reach_units)
    fixed = spots & ~grids["moving"] if grids is not None else spots
    reach = cv2.dilate(fixed.astype(np.uint8), _disc(radius)) > 0
    if grids is None or not (spots & grids["moving"]).any():
        return reach & targets
    ty, tx = np.nonzero(targets & ~reach)
    if not len(ty):
        return reach & targets
    covered = np.zeros(len(ty), bool)
    for here, poses in grids["carriers"]:
        cells = here & spots
        if not cells.any():
            continue
        ys, xs = np.nonzero(cells)
        posed = [(ys + 0.5, xs + 0.5)] + [tuple(c + 0.5 for c in _posed_cells(grids, cells, p)) for p in poses]
        for start in range(0, len(ys), 256):   # spots in chunks: memory stays small
            ok = np.ones((min(256, len(ys) - start), len(ty)), bool)
            for py, px in posed:
                d2 = (py[start:start + 256, None] - ty[None, :] - 0.5) ** 2 \
                    + (px[start:start + 256, None] - tx[None, :] - 0.5) ** 2
                ok &= d2 <= radius * radius
            covered |= ok.any(axis=0)
    out = reach & targets
    out[ty[covered], tx[covered]] = True
    return out


# ---------------------------------------------------------------------------
# Removable obstacles
# ---------------------------------------------------------------------------

def _xz(points, ndigits=1):
    return [[round(p[0], ndigits), round(p[1], ndigits)] for p in points]


def _centre(areas):
    """[x, z, height] of the middle of the biggest outline among the areas:
    where an obstacle shows on screen (its scene object can sit elsewhere)."""
    best, best_size = None, -1.0
    for a in areas:
        if not a.get("polygons") or len(a["polygons"][0]) < 3:
            continue
        p = np.asarray(a["polygons"][0], float)
        m = cv2.moments(p[:, :2].astype(np.float32).reshape(-1, 1, 2))
        size = abs(m["m00"])
        if size > best_size:
            cx, cz = (m["m10"] / m["m00"], m["m01"] / m["m00"]) if m["m00"] else p[:, :2].mean(axis=0)
            height = float(np.median(p[:, 2])) if p.shape[1] > 2 else 0.0
            best, best_size = [round(float(cx), 1), round(float(cz), 1), round(height, 1)], size
    return best


def _other_click_points(areas, centre, scene_position):
    """World points [x, z, height] to click when a click on an obstacle's
    `centre` (_centre) opened no removal box, most promising first:

      * the map file's own position of the obstacle's scene object, when it
        lies within one outline's size of the centre (further away it is an
        offset inside a parent object, not a place on the map);
      * the points half-way from the centre to the outline's far, left,
        right and near edge - far (greater z, higher on screen) first,
        because an obstacle is drawn standing up from its outline.

    Mushroom Grotto Impoppable (2026-11-11, loss case
    20261111_111519_MushroomGrotto_impoppable): the main mushroom's outline
    is a small patch at the foot of its stalk. Two clicks on the patch's
    middle opened no box, the obstacle was left alone for the game, and the
    845 legal cells under it - the only ground for a village, a Super Monkey
    or an ace on this map - were never freed. The map file puts the scene
    object 19 units further up, on the mushroom's cap."""
    outline = max((a["polygons"][0] for a in areas if a.get("polygons") and len(a["polygons"][0]) >= 3),
                  key=len, default=None)
    if outline is None:
        return []
    p = np.asarray(outline, float)[:, :2]
    (x0, z0), (x1, z1) = p.min(axis=0), p.max(axis=0)
    cx, cz, height = centre[0], centre[1], (centre[2] if len(centre) > 2 else 0.0)
    points = []
    if scene_position is not None and len(scene_position) >= 2:
        sx, sz = float(scene_position[0]), float(scene_position[1])
        off = float(np.hypot(sx - cx, sz - cz))
        if 1.0 < off <= max(x1 - x0, z1 - z0):
            points.append([round(sx, 1), round(sz, 1), height])
    for x, z in ((cx, (cz + z1) / 2), ((cx + x0) / 2, cz), ((cx + x1) / 2, cz), (cx, (cz + z0) / 2)):
        points.append([round(float(x), 1), round(float(z), 1), height])
    return points


def removables(map_name, playfield=None):
    """The obstacles a player can pay to remove on a map, [] when none:

      name, id, cost   the price written in the map (dollars; live prices
                       may differ by difficulty or mode - check in game)
      available        can be bought from the start (else: unlocked_by)
      after            what its ground becomes: "uncovered" (the area is
                       deleted and what lies beneath shows) or a surface type
      position         world [x, z, height] of the middle of the obstacle
                       (where to click it); "frac" the same as screen
                       fractions (fx, fy) when a playfield is given, and
                       "click_fracs" that point followed by the others to
                       try when it opens no box (_other_click_points)
      polygons         its outline(s), world [x, z]
      blocks_sight     it is (part of) a line-of-sight blocker
      rounds, cash_reward  Three Mines 'Round's ore: mined for that many
                       rounds, then pays out
    How much room it frees is removal_effect()'s job (it needs a model)."""
    geom = load(map_name)
    if geom is None:
        return []
    mech = geom.get("mechanics") or {}
    areas = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    names = {r["id"]: r["name"] for r in mech.get("removables", [])}
    unlockers = _unlockers(geom, names)
    proj = Projection(playfield) if playfield else None
    out = []
    for r in mech.get("removables", []):
        own = [areas[i] for i in r.get("areas", []) if i in areas]
        entry = {
            "id": r["id"], "name": r["name"], "cost": r["cost"],
            "available": bool(r.get("active", True)),
            "unlocked_by": None if r.get("active", True) else unlockers.get(r["id"], "a map event"),
            "after": "uncovered" if r.get("destroy_area", True) else r.get("after"),
            "position": _centre(own) or r["position"],
            "polygons": [_xz(p) for a in own for p in a["polygons"][:1]],
            "blocks_sight": any(a.get("blocks_sight") for a in own),
        }
        if proj is not None:
            points = [entry["position"]] + _other_click_points(own, entry["position"], r.get("position"))
            fracs = [[round(float(v), 4) for v in f] for f in proj.to_frac(points)]
            entry["frac"], entry["click_fracs"] = fracs[0], fracs
        if r.get("class") == "RoundRemoveable":
            entry.update(rounds=r.get("rounds"), cash_reward=r.get("cash_reward"))
        out.append(entry)
    return out


def _unlockers(geom, names):
    """{removable id: words for what makes it buyable}."""
    out = {}
    for e in (geom.get("mechanics") or {}).get("events", []):
        for act in e.get("actions", []):
            if act.get("type") == "RemovableActiveAction" and act.get("setActiveToo"):
                why = " / ".join(_describe_trigger(t, names) for t in e.get("triggers", [])) or e["name"]
                for rid in _ids(act.get("removeable")):
                    out[rid] = why
    # MapActions lists inherit the words of the events that call them
    for e in (geom.get("mechanics") or {}).get("events", []):
        for act in e.get("actions", []):
            if act.get("type") == "TriggerMapActionsAction":
                target = next((x for x in geom["mechanics"]["events"] if x["id"] == act.get("mapActions")), None)
                for a2 in (target or {}).get("actions", []):
                    if a2.get("type") == "RemovableActiveAction":
                        why = " / ".join(_describe_trigger(t, names) for t in e.get("triggers", []))
                        for rid in _ids(a2.get("removeable")):
                            out[rid] = why
    return out


def removal_effect(model, removable):
    """What buying one obstacle (name or id) changes for placement:
    {"freed_land", "freed_water": bool grids of cells that become placeable,
     "lost_land", "lost_water": cells that stop being placeable (Flooded
     Valley's dam floods land), "cells_freed": count}; None without geometry."""
    before = grids_for(model)
    after = grids_for(model, removed=(removable,))
    if before is None or after is None:
        return None
    out = {}
    for k in ("land", "water"):
        out[f"freed_{k}"] = after[k] & ~before[k]
        out[f"lost_{k}"] = before[k] & ~after[k]
    out["cells_freed"] = int((out["freed_land"] | out["freed_water"]).sum())
    return out


# ---------------------------------------------------------------------------
# Summary of every map's mechanics (data/map_mechanics.json)
# ---------------------------------------------------------------------------

def _area_info(area):
    info = {"name": area["name"], "type": area["type"], "polygons": [_xz(p) for p in area["polygons"][:1]]}
    if area.get("blocks_sight"):
        info["blocks_sight"] = True
    return info


def _track_lengths(path, key):
    """(length inside the path's `key` ranges, e.g. invulnerable; total length)."""
    pts = np.asarray(path["points"], float)[:, :2]
    if len(pts) < 2:
        return 0.0, 0.0
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    spans = path.get(key, [])
    inside = [i for i in range(len(seg)) if _in_ranges(i, spans) or _in_ranges(i + 1, spans)]
    return float(seg[inside].sum()), float(seg.sum())


def _track_share(path, key):
    """Share of a path's length inside its `key` ranges."""
    part, total = _track_lengths(path, key)
    return part / max(total, 1e-9)


def hidden_track_share(geom):
    """Share of the length of all bloon paths (as painted) where bloons
    cannot be hit."""
    part = total = 0.0
    for p in bloon_paths(geom):
        if not p.get("hidden"):
            a, b = _track_lengths(p, "invulnerable")
            part, total = part + a, total + b
    return part / total if total else 0.0


# how the bot deals with each kind of feature (docs/map_mechanics.md has more)
TREATMENT = {
    "removable": "placement leaves it alone; mapgeom.removables()/removal_effect() and "
                 "placement.valid_spots(removed=...) show the room it would free",
    "round_removable": "mined for cash; not used by the bot",
    "area_cycle": "every area of the cycle counts as always there",
    "area_appears": "counted as there from the start (it may come)",
    "area_vanishes": "ground that goes is never used; obstacles that go still block",
    "rotating_area": "carries towers: only global-range towers (or spots that barely move) go there",
    "moving_platform": "carries towers: only global-range towers (or spots that barely move) go there; "
                       "the water/land it sweeps over is never used",
    "towers_suspended": "no towers there",
    "path_opens": "track painted if the map opens it by itself, ignored if only the player can",
    "hidden_track": "not counted as coverable track",
    "no_path_targeting": "recorded (only matters for spike-style path targeting)",
    "alternating_paths": "every path is painted, so both get covered",
    "paid_switch": "not used",
    "map_ability": "not used",
    "click_event": "not used (the bot does not click map objects)",
    "seasonal_area": "counted as there (seasonal events switch it on)",
}


def mechanics_summary(geom):
    """{"features": [...], "advice": [...]} for one map: each feature has
    kind, automatic, when, first_round, and kind-specific details (areas
    with world polygons, cost, carries_towers, ...) plus "bot": how the bot
    treats it."""
    mech = geom.get("mechanics") or {}
    areas = {a["id"]: a for a in geom.get("areas", []) if "id" in a}
    paths = {p["id"]: p for p in geom.get("paths", []) if "id" in p}
    rem_names = {r["id"]: r["name"] for r in mech.get("removables", [])}
    rem_names.update({r["id"]: r["name"] for r in mech.get("regen_removables", [])})
    events = {e["id"]: e for e in mech.get("events", [])}
    dyn = dynamics(geom)
    features = []

    def add(kind, automatic, when=None, first_round=None, **extra):
        f = {"kind": kind, "automatic": automatic}
        if when:
            f["when"] = when
        if first_round is not None:
            f["first_round"] = first_round
        f.update(extra)
        f["bot"] = TREATMENT.get(kind, "")
        features.append(f)

    unlockers = _unlockers(geom, rem_names)
    for r in mech.get("removables", []):
        own = [areas[i] for i in r.get("areas", []) if i in areas]
        kind = "round_removable" if r.get("class") == "RoundRemoveable" else "removable"
        extra = {"name": r["name"], "cost": r["cost"], "position": (_centre(own) or r["position"])[:2],
                 "after": "uncovered" if r.get("destroy_area", True) else r.get("after"),
                 "areas": [_area_info(a) for a in own]}
        if not r.get("active", True):
            extra["unlocked_by"] = unlockers.get(r["id"], "a map event")
        if kind == "round_removable":
            extra.update(rounds=r.get("rounds"), cash_reward=r.get("cash_reward"))
        add(kind, False, "the player buys it", **extra)

    for r in mech.get("regen_removables", []):
        own = [areas[i] for i in r.get("areas", []) if i in areas]
        add("paid_switch", False, "the player buys it", name=r["name"], cost=r.get("cost"),
            position=(_centre(own) or r["position"])[:2])

    # what each event does, described once per event (MapActions lists are
    # described through the events that call them)
    def flat_actions(event, seen=()):
        for act in event.get("actions", []):
            if act.get("type") == "TriggerMapActionsAction":
                target = events.get(act.get("mapActions"))
                if target and target["id"] not in seen:
                    yield from flat_actions(target, (*seen, target["id"]))
            else:
                yield act

    clicks = 0
    for e in events.values():
        if e.get("kind") != "event":
            continue
        fired = dyn.fired.get(e["id"])
        automatic = bool(fired and fired[0])
        first = fired[1] if fired else None
        when = " / ".join(_describe_trigger(t, rem_names) for t in e.get("triggers", []))
        if not e.get("active", True):
            when = (when + " (once switched on by another event)").strip()
        did_area = False
        for act in flat_actions(e):
            kind = act.get("type")
            if kind in AREA_ACTIONS:
                field, effect = AREA_ACTIONS[kind]
                own = [areas[i] for i in _ids(act.get(field)) if i in areas]
                if own:
                    did_area = True
                    name = {"cycle": "area_cycle", "appear": "area_appears", "vanish": "area_vanishes"}[effect]
                    extra = {"areas": [_area_info(a) for a in own]}
                    if effect == "cycle":
                        extra["rounds_per_step"] = act.get("roundsPerRotate") or 1
                    add(name, automatic, when, first, event=e["name"], **extra)
            elif kind == "SetAreaActiveAction" and act.get("area") in areas:
                did_area = True
                add("area_appears" if act.get("isActive") else "area_vanishes", automatic, when, first,
                    event=e["name"], areas=[_area_info(areas[act["area"]])])
            elif kind in ("RotateAreaAction", "MovingPlatformAction"):
                own = [areas[i] for i in _ids(act.get("area")) + _ids(act.get("areasToMove")) if i in areas]
                poses = _mover_poses(act, areas)
                did_area = True
                extra = {"areas": [_area_info(a) for a in own], "carries_towers": True,
                         "positions": len(poses) + 1}
                if kind == "RotateAreaAction":
                    a0 = own[0] if own else {}
                    extra.update(degrees_per_step=act.get("rotation"),
                                 pivot=(a0.get("pivot") or a0.get("origin") or [0, 0])[:2])
                else:
                    extra["offsets"] = [[round(p[0], 1), round(p[1], 1), round(p[2], 1)] for p in poses]
                add("rotating_area" if kind == "RotateAreaAction" else "moving_platform",
                    automatic, when, first, event=e["name"], **extra)
            elif kind == "SuspendTowersOnAreaAction" and not act.get("isUnsuspendAction") and act.get("area") in areas:
                did_area = True
                add("towers_suspended", automatic, when, first, event=e["name"],
                    areas=[_area_info(areas[act["area"]])])
            elif kind == "PathActiveAction" and act.get("setActiveToo") or kind == "ToggleSplitterAction":
                ids = _ids(act.get("path")) + _ids(act.get("pathsToActivate"))
                add("path_opens", automatic, when, first, event=e["name"],
                    paths=[paths[i]["name"] for i in ids if i in paths])
        if not did_area and any(t.get("type", "").startswith("InteractableClick") for t in e.get("triggers", [])):
            clicks += 1
    if clicks:
        add("click_event", False, "player clicks a map object", count=clicks)

    for p in geom.get("paths", []):
        for key, kind in (("invulnerable", "hidden_track"), ("no_path_targeting", "no_path_targeting")):
            if p.get(key):
                add(kind, True, "always", path=p["name"], ranges=p[key], share=round(_track_share(p, key), 3))
    alternating = [s for s in mech.get("splitters", []) if s.get("type", "").startswith("AlternateRound")]
    for s in alternating:
        add("alternating_paths", True, f"every {s.get('roundsPerPath') or 1} round(s)",
            paths=[paths[i]["name"] for i in _ids(s.get("paths")) if i in paths])
    for g in mech.get("gizmos", []):
        cost = {k: g[k] for k in ("cost", "costIncrease", "firstUseCost", "roundCost") if k in g}
        add("map_ability", False, "the player buys it", name=g["type"], position=g["position"][:2], cost=cost)
    for a in geom.get("areas", []):
        if a.get("seasonal"):
            add("seasonal_area", True, "during a seasonal event", areas=[_area_info(a)])
    share = round(hidden_track_share(geom), 3)
    return {"features": features, "hidden_track_share": share, "advice": _advice(features, share)}


def _advice(features, hidden_share=0.0):
    """Plain advice for planning on a map, from its features."""
    out = []
    auto = [f for f in features if f["automatic"]]
    if any(f["kind"] in ("area_cycle", "area_appears", "area_vanishes")
           and any(a.get("blocks_sight") for a in f.get("areas", [])) for f in auto):
        out.append("line of sight changes during the game: blockers count as always there; "
                   "global-range towers (sniper, mortar, heli, ace, dartling) do not care")
    if any(f["kind"] == "area_cycle"
           and any(a["type"] in SOLID_TYPES and not a.get("blocks_sight") for a in f.get("areas", []))
           for f in auto):
        out.append("some ground is closed off part of the time (towers already there stay, "
                   "but none can be placed while it is closed): only ground that is always open is used")
    if any(f["kind"] in ("rotating_area", "moving_platform") for f in auto):
        out.append("towers on moving ground are carried around: use it for global-range towers")
    if any(f["kind"] == "area_vanishes" and any(a["type"] in ("land", "water", "ice", "shallow_water")
                                                for a in f.get("areas", [])) for f in auto):
        out.append("ground disappears during the game: only ground that lasts is used")
    if any(f["kind"] == "towers_suspended" for f in auto):
        out.append("towers on part of the map get switched off: that part is not used")
    if hidden_share >= 0.15:
        out.append(f"{hidden_share:.0%} of the track cannot be hit (gates, tunnels): "
                   "cover the open stretches")
    return out


def write_mechanics_summary(path=MECHANICS_FILE):
    """Rebuild data/map_mechanics.json from every extracted map."""
    try:
        from .account import MAPS
        names = {map_id_for(m): m for m in MAPS}
    except Exception:  # the summary is still useful without display names
        names = {}
    maps = {}
    for f in sorted(GEOMETRY_DIR.glob("*.json")):
        try:
            geom = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "mechanics" not in geom:
            continue   # extracted by an older version: refreshed on the next run
        summary = mechanics_summary(geom)
        if summary["features"]:
            maps[f.stem] = {"name": names.get(f.stem) or ID_ALIASES.get(f.stem) or f.stem,
                            "bundle": geom.get("bundle"), **summary}
    data = {"version": RULES_VERSION,
            "about": "Map mechanics read from the game's map scenes (gamefiles.py), "
                     "interpreted by mapgeom.py; see docs/map_mechanics.md",
            "maps": maps}
    path.write_text(_readable_json(data) + "\n", encoding="utf-8")
    return data


def _readable_json(value, indent=0):
    """JSON with one key per line, but lists of plain values (a point, a
    polygon) kept on one line so the file stays short enough to read."""
    pad, inner = " " * indent, " " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{json.dumps(k)}: {_readable_json(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list) and value and any(isinstance(v, dict) for v in value):
        return "[\n" + ",\n".join(inner + _readable_json(v, indent + 1) for v in value) + "\n" + pad + "]"
    return json.dumps(value, separators=(",", ":")) if isinstance(value, list) else json.dumps(value)


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
