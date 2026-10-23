"""Read map geometry out of the game's own asset files (read-only).

What and why
------------
BTD6 ships every map as a Unity asset bundle
(BloonsTD6_Data/StreamingAssets/aa/StandaloneWindows64/Full/map_<id>_scenes_all_<hash>.bundle).
Inside, the map's scene holds components with readable field names:

  * Path   - the bloon route; its child objects are straight "LineNode"s
             and "Curve"s (Bezier control points as the curve's children)
  * Area   - polygons with a type (AREA_TYPES: track, water, land, unplaceable,
             ice, removable obstacle, Mermonkey-only water, shallow water);
             filterInTowerSizes limits which tower sizes fit ("small");
             isBlocker/blockerCircles mark line-of-sight blockers
  * BaseArea - the surface type of everything not covered by an Area
             (land on most maps, water on island maps such as Spice Islands)

and the parts of a map that change during a game ("map mechanics"):

  * Removeable / RoundRemoveable - obstacles the player pays to remove
             (Cornfield's corn, Spillway's boats, Three Mines 'Round's ore);
             the Areas on the obstacle's own object are what it occupies
  * RegenRemovable - paid map switches that come back (Polyphemus' eye,
             Castle Revenge's engine), with a cost formula per round
  * MapEvent - "when <triggers> then <actions>": triggers such as a round
             starting or ending, a removable being bought or a click, and
             actions such as creating, destroying, cycling, rotating or
             moving Areas (Erosion's melting ice, Covered Garden's windows,
             Geared's gears, Sanctuary's platforms), switching paths on or
             off, or suspending the towers standing on an Area
  * PathPointInfo - per path node: bloons there cannot be hit (tunnels,
             gates, holes) or cannot be targeted on the ground
  * Splitters and map gizmos (paid map abilities) - recorded for reference

Reading these gives the exact track and placement map for every map,
including maps added in future updates (each arrives as a new bundle), so
nothing has to be learned by watching bloons or probing placements.
mapgeom.py interprets the mechanics (what changes by itself, when, and what
it means for placement).

Safety: the game's files are never modified. Bundles are copied to a cache
folder outside the game (CACHE) and only the copies are opened, read-only.
No game code is run, injected or patched.

Output: data/map_geometry/<map id>.json, small JSON files in world
coordinates: every point is [x, z, y] with x to the right, z up the screen
and y the height above the ground (some maps have raised or sunken paths;
the camera is tilted, so height moves things on screen). The play field is
centred on the origin.
Use mapgeom.py to turn them into the bot's grids.
"""
import glob
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger("gamefiles")

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_DIR = ROOT / "data" / "map_geometry"
CACHE = Path.home() / ".btd6bot_cache" / "bundles"   # copies of game bundles
MECHANICS_FILE = ROOT / "data" / "map_mechanics.json"   # summary of every map's mechanics
# Bump when the extracted format or its reading changes.
#   7: area ids/state flags, removables, map events, hidden track (PathPointInfo)
GEOMETRY_VERSION = 7

# The game's AreaType enum (Assets.Scripts.Models.Map.AreaType in GameAssembly)
AREA_TYPES = {0: "track", 1: "water", 2: "land", 3: "unplaceable", 4: "ice",
              5: "removable", 6: "water_mermonkey", 7: "shallow_water"}


# ---------------------------------------------------------------------------
# Finding the game
# ---------------------------------------------------------------------------

def find_install():
    """The BloonsTD6 folder: from the running game, else from Steam's library list."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process BloonsTD6 -ErrorAction SilentlyContinue | Select-Object -First 1).Path"],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        if out:
            return Path(out).parent
    except (OSError, subprocess.SubprocessError):
        pass
    for steam in (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
                  Path(r"C:\Program Files\Steam")):
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        libraries = [steam]
        if vdf.exists():
            libraries += [Path(p.replace("\\\\", "\\"))
                          for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="ignore"))]
        for lib in libraries:
            game = lib / "steamapps" / "common" / "BloonsTD6"
            if (game / "BloonsTD6.exe").exists():
                return game
    return None


def bundle_dir(install):
    return install / "BloonsTD6_Data" / "StreamingAssets" / "aa" / "StandaloneWindows64" / "Full"


def map_bundles(install):
    """{map id: bundle path} for every map scene bundle in the game."""
    out = {}
    for f in glob.glob(str(bundle_dir(install) / "map_*_scenes_all_*.bundle")):
        m = re.match(r"map_(.+)_scenes_all_[0-9a-f]+\.bundle$", Path(f).name)
        if m:
            out[m.group(1)] = Path(f)
    return out


def _cached(src):
    """Copy a game file into CACHE once (the hash in its name changes with updates)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    dst = CACHE / src.name
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dst)
    return dst


def _monoscripts(install):
    """The bundle that names the scripts (needed to know which component is a Path)."""
    found = glob.glob(str(bundle_dir(install) / "*_monoscripts_*.bundle"))
    return _cached(Path(found[0])) if found else None


# ---------------------------------------------------------------------------
# Reading one map
# ---------------------------------------------------------------------------

def _quat_rotate(q, v):
    """Rotate vector v by Unity quaternion q (dict with x, y, z, w)."""
    qv = np.array([q["x"], q["y"], q["z"]])
    t = 2 * np.cross(qv, v)
    return v + q["w"] * t + np.cross(qv, t)


class _Scene:
    """Transforms and components of one map scene, with world positions."""

    def __init__(self, env):
        self.env = env
        self.objects = {}          # path id -> UnityPy object reader
        self.transforms = {}       # transform id -> typetree
        self.go_transform = {}     # game object id -> transform id
        self.go_name = {}
        self.go_active = {}        # game object id -> its own m_IsActive flag
        self.script = {}           # MonoBehaviour id -> (namespace, class name)
        self._trees = {}           # MonoBehaviour id -> typetree (read on demand)
        for o in env.objects:
            self.objects[o.path_id] = o
            if o.type.name in ("Transform", "RectTransform"):
                t = o.read_typetree()
                self.transforms[o.path_id] = t
                self.go_transform[t["m_GameObject"]["m_PathID"]] = o.path_id
            elif o.type.name == "GameObject":
                t = o.read_typetree()
                self.go_name[o.path_id] = t.get("m_Name", "")
                self.go_active[o.path_id] = bool(t.get("m_IsActive", 1))
            elif o.type.name == "MonoBehaviour":
                mb = o.read()
                s = mb.m_Script.read() if mb.m_Script else None
                if s is not None:
                    self.script[o.path_id] = (s.m_Namespace, s.m_ClassName)

    def world(self, tid, local=(0.0, 0.0, 0.0)):
        """World position of a point given in transform tid's local space."""
        p = np.array(local, float)
        while tid:
            t = self.transforms[tid]
            scale = np.array([t["m_LocalScale"][k] for k in "xyz"], float)
            pos = np.array([t["m_LocalPosition"][k] for k in "xyz"], float)
            p = _quat_rotate(t["m_LocalRotation"], p * scale) + pos
            tid = t["m_Father"]["m_PathID"]
        return p

    def tree(self, pid):
        """Typetree of one MonoBehaviour (cached)."""
        if pid not in self._trees:
            self._trees[pid] = self.objects[pid].read_typetree()
        return self._trees[pid]

    def class_of(self, pid):
        return self.script.get(pid, ("", ""))[1]

    def ids(self, class_name):
        """Ids of all MonoBehaviours of a script class, in file order."""
        return [pid for pid, (_, cls) in self.script.items() if cls == class_name]

    def components(self, class_name):
        """Typetrees of all MonoBehaviours of a given script class."""
        for pid in self.ids(class_name):
            yield self.tree(pid)

    def go_of(self, pid):
        """Game object id a component belongs to."""
        return self.tree(pid)["m_GameObject"]["m_PathID"]

    def parent_go(self, go):
        father = self.transforms[self.go_transform[go]]["m_Father"]["m_PathID"]
        return self.transforms[father]["m_GameObject"]["m_PathID"] if father else None

    def ancestors(self, go):
        """The game object itself, then its parent, grandparent, ..."""
        while go:
            yield go
            go = self.parent_go(go)

    def active_in_hierarchy(self, go):
        """Unity only runs (and the map loader only finds) objects whose whole
        parent chain is switched on."""
        return all(self.go_active.get(g, True) for g in self.ancestors(go))

    def position(self, go):
        """World position of a game object as [x, z, y] (the geometry's order)."""
        return _xzy(self.world(self.go_transform[go]))


def _xzy(p):
    """Unity (x, y, z) -> the geometry's [x, z, y] (z up the screen, y height)."""
    return [round(float(p[0]), 2), round(float(p[2]), 2), round(float(p[1]), 2)]


def _bezier(points, samples=16):
    """Points along a Bezier curve of any degree (de Casteljau)."""
    out = []
    for t in np.linspace(0.0, 1.0, samples):
        q = list(points)
        while len(q) > 1:
            q = [(1 - t) * a + t * b for a, b in zip(q, q[1:])]
        out.append(q[0])
    return out


# How the game turns a path's nodes into the route bloons follow. A path's
# GameObject carries one "point source" component (read from GameAssembly's
# Assets.Scripts.Unity.Map classes):
#   PolyLineNodes    straight lines between nodes; a child with children of
#                    its own is a Curve whose children are Bezier points
#   BezierLineNodes  nodes are a chain of cubic Bezier control points:
#                    anchor, handle, handle, anchor, ... sampled with
#                    Math.MakeBezierPoints(start, end, startTangent,
#                    endTangent, division=30)
#   CurvedLineNodes  a natural cubic spline through every node, parametrised
#                    by distance along them (CubicSpline.FitParametric) and
#                    resampled evenly, samplesPer100Units points per 100 units
BEZIER_DIVISION = 30


def _cubic(p0, p1, p2, p3, n=BEZIER_DIVISION):
    t = np.linspace(0.0, 1.0, n)[:, None]
    return list((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3)


def _bezier_chain(nodes):
    """Anchor, handle, handle, anchor, ... -> points along the chained curves."""
    out = [nodes[0]] if nodes else []
    for i in range(0, len(nodes) - 3, 3):
        out += _cubic(nodes[i], nodes[i + 1], nodes[i + 2], nodes[i + 3])[1:]
    return out


def _natural_spline(t, v):
    """Second derivatives of a natural cubic spline through (t, v)."""
    n = len(t)
    m = np.zeros(n)
    if n < 3:
        return m
    h = np.diff(t)
    a = np.zeros(n); b = np.ones(n); c = np.zeros(n); d = np.zeros(n)
    for i in range(1, n - 1):
        a[i], b[i], c[i] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
        d[i] = 6 * ((v[i + 1] - v[i]) / h[i] - (v[i] - v[i - 1]) / h[i - 1])
    for i in range(1, n):            # Thomas algorithm (tridiagonal solve)
        w = a[i] / b[i - 1]
        b[i] -= w * c[i - 1]
        d[i] -= w * d[i - 1]
    m[n - 1] = d[n - 1] / b[n - 1]
    for i in range(n - 2, -1, -1):
        m[i] = (d[i] - c[i] * m[i + 1]) / b[i]
    m[0] = m[-1] = 0.0
    return m


def _spline_eval(t, v, m, q):
    i = np.clip(np.searchsorted(t, q) - 1, 0, len(t) - 2)
    h = t[i + 1] - t[i]
    a = (t[i + 1] - q) / h
    b = (q - t[i]) / h
    return a * v[i] + b * v[i + 1] + ((a ** 3 - a) * m[i] + (b ** 3 - b) * m[i + 1]) * h * h / 6


def _curved(nodes, samples_per_100=100):
    """Natural cubic spline through the nodes, evenly resampled by distance."""
    pts = np.array([n for k, n in enumerate(nodes) if k == 0 or np.linalg.norm(n - nodes[k - 1]) > 1e-6])
    if len(pts) < 3:
        return list(pts)
    t = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    count = max(2, int(t[-1] * samples_per_100 / 100.0))
    q = np.linspace(0.0, t[-1], count)
    cols = [_spline_eval(t, pts[:, k], _natural_spline(t, pts[:, k]), q) for k in range(3)]
    return list(np.stack(cols, axis=1))


# Per-node path settings (PathPointInfo on a node or a curve point). The two
# that matter to the bot, each stored per path as ranges of point indexes:
#   invulnerable       bloons there cannot be hit at all (castle gates,
#                      tunnels, holes they drop into)
#   no_path_targeting  towers that aim at the ground (spikes, Mortar-style
#                      path targeting) cannot pick these points (Mushroom
#                      Grotto's dark caves light up only near its mushrooms)
POINT_FLAGS = {"invulnerable": "bloonsInvulnerable", "no_path_targeting": "disablePathTargeting"}


def _ranges(flags):
    """[False, True, True, False, True] -> [[1, 2], [4, 4]] (inclusive)."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append([start, i - 1])
            start = None
    return out


def _read_paths(scene):
    sources = {}   # game object id -> (point source kind, its fields)
    for kind in ("PolyLineNodes", "BezierLineNodes", "CurvedLineNodes"):
        for t in scene.components(kind):
            sources[t["m_GameObject"]["m_PathID"]] = (kind, t)
    node_info = {scene.go_of(pid): scene.tree(pid) for pid in scene.ids("PathPointInfo")}

    def flags_of(transform_id):
        """{flag: bool} of the node (or curve point) behind a transform."""
        info = node_info.get(scene.transforms[transform_id]["m_GameObject"]["m_PathID"], {})
        return {k: bool(info.get(field, 0)) for k, field in POINT_FLAGS.items()}

    def either(a, b):
        # between two nodes a setting counts when either end has it: the bot
        # would rather miss a little visible track than count hidden track
        return {k: a[k] or b[k] for k in a}

    paths = []
    for pid in scene.ids("Path"):
        tree = scene.tree(pid)
        go = tree["m_GameObject"]["m_PathID"]
        root = scene.go_transform[go]
        kind, fields = sources.get(go, ("PolyLineNodes", {}))
        children = [c["m_PathID"] for c in scene.transforms[root]["m_Children"]]
        node_flags = [flags_of(c) for c in children]
        if kind == "BezierLineNodes":
            nodes = [scene.world(c) for c in children]
            points = _bezier_chain(nodes)
            # each chained curve spans anchors i .. i+3 and adds BEZIER_DIVISION-1 points
            flags = node_flags[:1]
            for i in range(0, len(nodes) - 3, 3):
                span = either(node_flags[i], node_flags[i + 3])
                flags += [span] * (BEZIER_DIVISION - 1)
        elif kind == "CurvedLineNodes":
            nodes = [scene.world(c) for c in children]
            points = _curved(nodes, fields.get("samplesPer100Units", 100))
            # samples are spread by distance along the nodes: find each one's node pair
            pts = np.array(nodes, float)
            along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]) \
                if len(pts) > 1 else np.zeros(len(pts))
            sample_t = np.linspace(0.0, along[-1] if len(along) else 0.0, len(points))
            flags = []
            for t in sample_t:
                k = int(np.clip(np.searchsorted(along, t, side="right") - 1, 0, max(len(nodes) - 2, 0)))
                flags.append(either(node_flags[k], node_flags[min(k + 1, len(nodes) - 1)])
                             if nodes else {f: False for f in POINT_FLAGS})
        else:
            points, flags = [], []
            for cid, own in zip(children, node_flags):
                kids = [k["m_PathID"] for k in scene.transforms[cid]["m_Children"]]
                if kids:   # a Curve: its children are the Bezier points
                    curve = _bezier([scene.world(k) for k in kids])
                    kid_flags = [either(own, flags_of(k)) for k in kids]
                    points += curve
                    # each sample takes the setting of its nearest control point
                    flags += [kid_flags[int(round(j * (len(kids) - 1) / max(len(curve) - 1, 1)))]
                              for j in range(len(curve))]
                else:      # a LineNode
                    points.append(scene.world(cid))
                    flags.append(own)
        flags = (flags + flags[-1:] * len(points))[:len(points)] if flags else []
        entry = {
            "id": pid,
            "name": scene.go_name.get(go, ""),
            "source": kind,
            "active": bool(tree.get("isActive", 1)),
            "hidden": bool(tree.get("isHidden", 0)),
            "points": [_xzy(p) for p in points],
        }
        for k in POINT_FLAGS:
            spans = _ranges(f[k] for f in flags)
            if spans:
                entry[k] = spans
        paths.append(entry)
    return paths


def _seasonal_objects(scene):
    """Game objects switched on only during seasonal events (Halloween,
    Christmas...: the EnableEventObjects component lists them)."""
    out = set()
    for tree in scene.components("EnableEventObjects"):
        out |= {g["m_PathID"] for g in tree.get("gameobjects", []) if g.get("m_PathID")}
    return out


def _read_areas(scene):
    seasonal = _seasonal_objects(scene)
    areas = []
    for pid in scene.ids("Area"):
        tree = scene.tree(pid)
        go = tree["m_GameObject"]["m_PathID"]
        tid = scene.go_transform[go]
        polygons = [[_xzy(scene.world(tid, (p["x"], p["y"], p["z"]))) for p in poly["points"]]
                    for poly in tree.get("polygons", [])]
        circles = []
        for c in tree.get("blockerCircles", []) or []:
            # The circles the game collides projectiles with. They are stored
            # in the simulation's flat plane, where a point at height h sits at
            # y = -(z + h/sqrt(3)): heights already folded in. Kept as
            # [x, z, radius, 0] so the projection adds no height again (every
            # circle centre then lies inside its own blocker polygon).
            pos = c.get("position") or c.get("center") or {}
            if pos:
                circles.append([round(float(pos.get("x", 0)), 2), round(-float(pos.get("y", 0)), 2),
                                round(float(c.get("radius", 0)), 2), 0.0])
        entry = {
            "id": pid,
            "name": scene.go_name.get(go, ""),
            "type": AREA_TYPES.get(tree.get("type"), str(tree.get("type"))),
            "blocks_sight": bool(tree.get("isBlocker", 0)),
            "disabled": bool(tree.get("isDisabled", 0)),
            "tower_sizes": tree.get("filterInTowerSizes", ""),
            "polygons": polygons,
            "circles": circles,
            "origin": scene.position(go),   # what moving-platform rotations turn about
        }
        # Objects switched off in the scene are not part of the map, except
        # seasonal decorations the game switches on during an event.
        if not (scene.active_in_hierarchy(go) and tree.get("m_Enabled", 1)):
            entry["inactive"] = True
            if any(g in seasonal for g in scene.ancestors(go)):
                entry["seasonal"] = True
        if tree.get("renderHeightOffset"):
            entry["render_offset"] = round(float(tree["renderHeightOffset"]), 2)
        pivot = (tree.get("pivotPoint") or {}).get("m_PathID")
        if pivot and pivot in scene.transforms:
            entry["pivot"] = _xzy(scene.world(pivot))
        for key, field in (("tower_sets", "filterInTowerSets"), ("exclude_towers", "filterOutSpecificTowers")):
            text = tree.get(field) or ""
            if text and text != "{empty}":
                entry[key] = text
        if tree.get("dontRemoveExistingTowers"):
            entry["keeps_towers"] = True   # appearing here does not remove towers
        areas.append(entry)
    return areas


# ---------------------------------------------------------------------------
# Map mechanics: removable obstacles, map events, gizmos
# ---------------------------------------------------------------------------

def _plain(value, ndigits=3):
    """A typetree value as plain JSON: references become the referenced
    component's id (None when empty), animation curves become keyframe lists
    [time, value, in-slope, out-slope], Unity bookkeeping fields are dropped."""
    if isinstance(value, dict):
        if set(value) == {"m_FileID", "m_PathID"}:
            return value["m_PathID"] or None
        if "m_Curve" in value:
            return [[round(k["time"], ndigits), round(k["value"], ndigits),
                     round(k["inSlope"], ndigits), round(k["outSlope"], ndigits)] for k in value["m_Curve"]]
        return {k: _plain(v, ndigits) for k, v in value.items() if not k.startswith("m_") and k != "def"}
    if isinstance(value, list):
        return [_plain(v, ndigits) for v in value]
    if isinstance(value, float):
        return round(value, ndigits)
    return value


def _component(scene, pid):
    """{"type": script class, ...its fields} for a trigger or action."""
    if not pid or pid not in scene.script:
        return None
    return {"type": scene.class_of(pid), **_plain(scene.tree(pid))}


def _owned_areas(scene, go, area_ids_by_go):
    """Area ids on a game object and everything below it."""
    out, todo = [], [go]
    while todo:
        g = todo.pop()
        out += area_ids_by_go.get(g, [])
        todo += [scene.transforms[c["m_PathID"]]["m_GameObject"]["m_PathID"]
                 for c in scene.transforms[scene.go_transform[g]]["m_Children"]]
    return sorted(out)


REMOVABLE_CLASSES = ("Removeable", "RoundRemoveable", "CustomMushroomGrottoRemoveable")


def _read_removables(scene, area_ids_by_go):
    """Obstacles the player can pay to remove.

    cost      removealCost (sic) as written in the scene, in dollars
    active    False: hidden until a map event offers it (RemovableActiveAction)
    after     the ground type its areas take when sold; with destroy_area the
              areas are deleted instead, uncovering whatever lies beneath
    areas     ids of the Areas it occupies (on its own object or below)
    rounds / cash_reward   RoundRemoveable (Three Mines 'Round's ore): it is
              mined for `rounds` rounds and then pays `cash_reward`"""
    out = []
    for cls in REMOVABLE_CLASSES:
        for pid in scene.ids(cls):
            t = scene.tree(pid)
            go = t["m_GameObject"]["m_PathID"]
            entry = {
                "id": pid, "class": cls, "name": scene.go_name.get(go, ""),
                "cost": int(t.get("removealCost", 0)),
                "active": bool(t.get("isActive", 1)),
                "after": AREA_TYPES.get(t.get("defaultTerrianType"), str(t.get("defaultTerrianType"))),
                "destroy_area": bool(t.get("destroyArea", 0)),
                "areas": _owned_areas(scene, go, area_ids_by_go),
                "position": scene.position(go),
            }
            if t.get("menuName"):
                entry["menu_name"] = t["menuName"]
            if t.get("denySellIfStackedTowers"):
                entry["deny_if_towers_on_top"] = True
            if t.get("modPathId"):
                entry["changes_path"] = t["modPathId"]
            if cls == "RoundRemoveable":
                entry["rounds"] = int(t.get("durationRounds", 0))
                entry["cash_reward"] = int(t.get("cashReward", 0))
            out.append(entry)
    return out


def _read_regen_removables(scene, area_ids_by_go):
    """Paid switches that can be bought again (RegenRemovable), with their
    LinearRoundBasedCost: base + increase * steps, one step every
    `every` rounds from round `first_round`."""
    out = []
    for pid in scene.ids("RegenRemovable"):
        t = scene.tree(pid)
        go = t["m_GameObject"]["m_PathID"]
        cost = None
        formula = (t.get("costFormula") or {}).get("m_PathID")
        if formula and scene.class_of(formula) == "LinearRoundBasedCost":
            f = scene.tree(formula)
            cost = {"base": f.get("baseCost"), "increase": f.get("costIncrease"),
                    "first_round": f.get("firstRoundForIncrease"), "every": f.get("roundsBetweenIncreases")}
        out.append({"id": pid, "name": scene.go_name.get(go, ""), "active": bool(t.get("isActive", 1)),
                    "cost": cost, "areas": _owned_areas(scene, go, area_ids_by_go),
                    "position": scene.position(go),
                    "inactive_when_bought": bool(t.get("setInactiveOnRemoved", 0))})
    return out


def _read_events(scene):
    """Map events ("when TRIGGERS, do ACTIONS") and the MapActions lists
    they can call (TriggerMapActionsAction). References inside triggers and
    actions are component ids: of Areas, Paths, Removeables, other events."""
    out = []
    for cls in ("MapEvent", "MapActions"):
        for pid in scene.ids(cls):
            t = scene.tree(pid)
            entry = {"id": pid, "kind": "event" if cls == "MapEvent" else "actions",
                     "name": scene.go_name.get(t["m_GameObject"]["m_PathID"], "")}
            if cls == "MapEvent":
                entry.update({
                    "one_time": bool(t.get("oneTimeEvent", 0)),
                    "all_triggers": bool(t.get("allTriggersRequired", 0)),
                    "active": not t.get("inactiveByDefault", 0),
                    "triggers": [c for c in (_component(scene, r.get("m_PathID")) for r in t.get("triggers", [])) if c],
                })
            entry["actions"] = [c for c in (_component(scene, r.get("m_PathID")) for r in t.get("actions", [])) if c]
            out.append(entry)
    return out


GIZMO_NAMESPACE = "Assets.Scripts.Unity.Map.Gizmos"
SPLITTER_NAMESPACE = "Assets.Scripts.Unity.Map.Spawners"


def _read_gizmos(scene):
    """Paid map abilities (Tricky Tracks' train, Workshop's power core and
    reverse motor, Dark Dungeons' statue) - recorded, not used for placement."""
    out = []
    for pid, (ns, cls) in scene.script.items():
        if ns == GIZMO_NAMESPACE and cls not in ("MapGizmo", "GizmoTimeDisplay"):
            go = scene.go_of(pid)
            out.append({"id": pid, "type": cls, "name": scene.go_name.get(go, ""),
                        "position": scene.position(go), **_plain(scene.tree(pid))})
    return out


def _read_splitters(scene):
    """How bloons choose between paths (alternating by round, MOABs only...)."""
    out = []
    for pid, (ns, cls) in scene.script.items():
        if ns == SPLITTER_NAMESPACE and cls != "PathSpawner" or cls == "Splitter":
            fields = _plain(scene.tree(pid))
            out.append({"id": pid, "type": cls, "name": scene.go_name.get(scene.go_of(pid), ""), **fields})
    return out


def _read_mechanics(scene, areas):
    area_ids_by_go = {}
    for a in areas:
        area_ids_by_go.setdefault(scene.go_of(a["id"]), []).append(a["id"])
    out = {"removables": _read_removables(scene, area_ids_by_go),
           "regen_removables": _read_regen_removables(scene, area_ids_by_go),
           "events": _read_events(scene),
           "gizmos": _read_gizmos(scene),
           "splitters": _read_splitters(scene)}
    return {k: v for k, v in out.items() if v}


def extract_map(bundle, monoscripts):
    """Geometry dict of one map bundle (opened from the cache copy)."""
    import UnityPy  # only needed for extraction
    scene = _Scene(UnityPy.load(str(monoscripts), str(_cached(bundle))))
    base = [t.get("type") for t in scene.components("BaseArea")]
    areas = _read_areas(scene)
    return {"version": GEOMETRY_VERSION, "bundle": bundle.name,
            "base": AREA_TYPES.get(base[0], "land") if base else "land",
            "paths": _read_paths(scene), "areas": areas,
            "mechanics": _read_mechanics(scene, areas)}


# ---------------------------------------------------------------------------
# Keeping data/map_geometry up to date
# ---------------------------------------------------------------------------

def geometry_file(map_id):
    return GEOMETRY_DIR / f"{map_id}.json"


def refresh(install=None, only=None, status=None):
    """Extract every map whose bundle changed since the last extraction.
    Returns the list of map ids (re)extracted. Safe to call at every start."""
    install = install or find_install()
    if install is None:
        log.warning("game folder not found - map geometry not refreshed")
        return []
    monoscripts = _monoscripts(install)
    if monoscripts is None:
        log.warning("monoscripts bundle not found - map geometry not refreshed")
        return []
    GEOMETRY_DIR.mkdir(parents=True, exist_ok=True)
    done = []
    for map_id, bundle in sorted(map_bundles(install).items()):
        if only and map_id not in only:
            continue
        f = geometry_file(map_id)
        try:
            old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError:
            old = {}
        if old.get("bundle") == bundle.name and old.get("version") == GEOMETRY_VERSION:
            continue  # unchanged since last time
        if status:
            status(f"reading map geometry from the game files: {map_id}")
        try:
            geom = extract_map(bundle, monoscripts)
        except Exception as e:  # one odd map must not stop the rest
            log.warning("could not read %s: %s", bundle.name, e)
            continue
        geom["map_id"] = map_id
        f.write_text(json.dumps(geom, separators=(",", ":")), encoding="utf-8")
        done.append(map_id)
    if done:
        log.info("map geometry extracted for %d maps: %s", len(done), ", ".join(done))
    if done or not MECHANICS_FILE.exists():
        try:   # the readable summary of every map's mechanics
            from .mapgeom import write_mechanics_summary
            write_mechanics_summary()
        except Exception as e:  # a summary problem must not stop the geometry
            log.warning("could not write %s: %s", MECHANICS_FILE.name, e)
    return done


if __name__ == "__main__":
    # Manual refresh:  python -m btd6bot.gamefiles
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"{len(refresh())} maps extracted to {GEOMETRY_DIR}")
