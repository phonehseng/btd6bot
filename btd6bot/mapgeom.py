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
            out["sight"] |= (circles > 0) & (top <= height + HEIGHT_TIE)
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


def paint_paths(geom, proj, lanes=None):
    """heat, t_sum, t_cnt grids from the map's (visible) bloon paths.

    Stretches where bloons cannot be hit (gates, tunnels, holes: the path's
    "invulnerable" ranges) get no heat, so no tower is placed to cover them;
    they still count for the progress scale. `lanes`, a bool grid, receives
    every lane cell including those stretches (no tower may stand on any)."""
    w, h = GRID
    heat = np.zeros((h, w), np.float32)
    t_sum = np.zeros((h, w), np.float32)
    t_cnt = np.zeros((h, w), np.float32)
    for path in bloon_paths(geom):
        if path.get("hidden") or len(path["points"]) < 2:
            continue  # hidden = bloons out of sight (tunnels): towers cannot hit them
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
            if _in_ranges(i, hidden) or _in_ranges(i + 1, hidden):
                continue   # bloons here cannot be hit
            prog = float(np.clip(((dist[i] + dist[i + 1]) / 2 - dist[a]) / span, 0, 1))
            heat[on] = TRACK_HEAT
            t_sum[on] += prog
            t_cnt[on] += 1
    return heat, t_sum, t_cnt


# ---------------------------------------------------------------------------
# Map mechanics: what changes during a game, and when
# ---------------------------------------------------------------------------
#
# gamefiles.py stores each map's events as the game writes them: "when these
# TRIGGERS fire, do these ACTIONS". Here they are sorted into what will
# happen by itself (and so must be planned for) and what only the player can
# set off (buying an obstacle, clicking a statue), which happens only if the
# bot chooses to.

RULES_VERSION = 1   # bump when the interpretation below changes (re-measures mapfit)

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
}
# Triggers that fire once while the map loads, before round 1. (Not
# OnMapLoadedWithActiveRegenRemovableTrigger: it restores a paid switch's
# state when a saved game is loaded, so it counts as "may happen any time".)
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
    other than the one it starts in, as a rotation by `degrees` about (cx, cz)
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
        moved = [areas_by_id[i] for i in _ids(action.get("areasToMove")) if i in areas_by_id]
        times = action.get("stateTimes") or []
        if not moved or not times:
            return []
        start = int(action.get("startingState", 0))
        states = {start} | set(action.get("triggerNumToStateNum") or [])
        t0 = times[min(start, len(times) - 1)]
        cx, cz = (moved[0].get("origin") or [0.0, 0.0])[:2]
        xs, zs, rs = (action.get(k) or [] for k in ("xPosCurve", "zPosCurve", "yRotCurve"))
        poses = []
        for s in sorted(states - {start}):
            t = times[min(s, len(times) - 1)]
            poses.append((_curve(xs, t) - _curve(xs, t0), _curve(zs, t) - _curve(zs, t0),
                          _curve(rs, t) - _curve(rs, t0), cx, cz))
        return poses
    return []


def _pose_points(xz, pose):
    """Move world points (array [..., 2]) to one pose."""
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


def dynamics(geom, sold=(), now_round=None, last_round=None):
    """Sort a map's events into what happens during a game.

    sold:       removables the player buys (ids or names): their areas go,
                and the events their sale triggers fire.
    now_round:  the round being played: one-off changes due by then have
                certainly happened (One Two Tree's plots have opened).
    last_round: the game's last round: changes after it are left out
                (Erosion's late melts do not matter in a 40-round game).
    Without these, every automatic change of the whole game is a "may"."""
    dyn = Dynamics()
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
                    dyn.movers.append({"type": kind, "areas": [i for i in ids if i in areas_by_id],
                                       "poses": poses, "first_round": first, "event": eid})
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
    solid = masks["track"] | masks["unplaceable"] | masks["removable"] | masks["blockers"]
    return land_ok, water_ok, solid


SOLID_TYPES = ("track", "unplaceable", "removable")


def placement_grids(geom, proj, lanes=None, dyn=None):
    """Placement grids that hold through the whole game.

    Returns {"land", "water", "mermonkey_water": bool grids of cells where a
    tower's centre may stand for the whole game as far as the ground goes;
    "size_limit"; "sight": blockers that are there at any time; "moving":
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
    lanes = np.zeros(shape, bool) if lanes is None else lanes
    for i, present in enumerate(states):
        masks = area_masks(geom, proj, present=present, retype=dyn.retype)
        land_ok, water_ok, solid = _surfaces(geom, masks)
        solid = solid | lanes   # drawn bloon lanes can poke past the track polygon on curves
        if i == 0:
            out["static_land"], out["static_water"] = land_ok & ~solid, water_ok & ~solid
        out["land"] &= land_ok & ~solid
        out["water"] &= water_ok & ~solid
        out["mermonkey_water"] &= masks["water_mermonkey"] & ~solid
        out["size_limit"] = np.minimum(out["size_limit"], masks["size_limit"])
        out["sight"] |= masks["sight"]

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
            else:
                unsafe |= swept & ~here
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
    grids = placement_grids(geom, proj, lanes | (model.heat > 0))
    model.scan["land"] = np.where(grids["land"], 1, 2).astype(np.uint8)
    model.scan["water"] = np.where(grids["water"], 1, 2).astype(np.uint8)
    model.mermonkey_water = grids["mermonkey_water"]
    model.size_limit = grids["size_limit"]
    model.small_only = grids["size_limit"] <= 1
    model.sight = grids["sight"]
    model.geometry_version = geom.get("version", 1)
    log.info("%s: geometry applied (%d paths, %d areas)", model.name,
             len(geom.get("paths", [])), len(geom.get("areas", [])))
    return model


_GRIDS_CACHE = {}
_MAP_IDS = {}


def grids_for(model, removed=(), now_round=None, last_round=None):
    """placement_grids() for a model's map (cached), or None without
    geometry. removed: obstacles (names or ids) treated as bought;
    now_round / last_round: see dynamics(). The grids hold "scan" as well,
    in MapModel.scan's form, so they can stand in for the model's own.
    Cheap to call again: the answer is kept until the geometry file changes."""
    id_key = (str(GEOMETRY_DIR), model.name)
    map_id = _MAP_IDS.get(id_key) or map_id_for(model.name)
    if map_id is None:
        return None   # (not remembered: the file may be extracted later)
    _MAP_IDS[id_key] = map_id
    path = GEOMETRY_DIR / f"{map_id}.json"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(path), stamp, tuple(model.playfield), frozenset(removed), now_round, last_round)
    if key not in _GRIDS_CACHE:
        try:
            geom = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if len(_GRIDS_CACHE) > 64:
            _GRIDS_CACHE.clear()
        proj = Projection(model.playfield)
        lanes = np.zeros(GRID[::-1], bool)
        heat, _, _ = paint_paths(geom, proj, lanes)
        dyn = dynamics(geom, removed, now_round, last_round)
        grids = placement_grids(geom, proj, lanes | (heat > 0), dyn)
        grids["scan"] = {k: np.where(grids[k], 1, 2).astype(np.uint8) for k in ("land", "water")}
        grids["track"] = heat > 0
        grids["proj"] = proj
        grids["steady"] = {}
        _GRIDS_CACHE[key] = grids
    return _GRIDS_CACHE[key]


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


def steady_spots(model, reach_units):
    """Bool grid of moving-ground cells (see placement_grids' "moving") where
    a tower with this reach (world units) keeps covering the track wherever
    the ground carries it (STEADY_KEEP), plus moving cells that barely move
    (STEADY_DRIFT). None on maps without moving ground."""
    grids = grids_for(model)
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


def removables(map_name, playfield=None):
    """The obstacles a player can pay to remove on a map, [] when none:

      name, id, cost   the price written in the map (dollars; live prices
                       may differ by difficulty or mode - check in game)
      available        can be bought from the start (else: unlocked_by)
      after            what its ground becomes: "uncovered" (the area is
                       deleted and what lies beneath shows) or a surface type
      position         world [x, z, height] of the middle of the obstacle
                       (where to click it); "frac" the same as screen
                       fractions (fx, fy) when a playfield is given
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
            entry["frac"] = [round(float(v), 4) for v in proj.to_frac([entry["position"]])[0]]
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
