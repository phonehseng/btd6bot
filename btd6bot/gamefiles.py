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

Reading these gives the exact track and placement map for every map,
including maps added in future updates (each arrives as a new bundle), so
nothing has to be learned by watching bloons or probing placements.

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
GEOMETRY_VERSION = 4   # bump when the extracted format changes

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
            capture_output=True, text=True, timeout=15).stdout.strip()
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
        self.transforms = {}       # transform id -> typetree
        self.go_transform = {}     # game object id -> transform id
        self.go_name = {}
        for o in env.objects:
            if o.type.name == "Transform":
                t = o.read_typetree()
                self.transforms[o.path_id] = t
                self.go_transform[t["m_GameObject"]["m_PathID"]] = o.path_id
            elif o.type.name == "GameObject":
                self.go_name[o.path_id] = o.read_typetree().get("m_Name", "")

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

    def components(self, class_name):
        """Typetrees of all MonoBehaviours of a given script class."""
        for o in self.env.objects:
            if o.type.name != "MonoBehaviour":
                continue
            mb = o.read()
            script = mb.m_Script.read() if mb.m_Script else None
            if script is not None and script.m_ClassName == class_name:
                yield o.read_typetree()


def _bezier(points, samples=16):
    """Points along a Bezier curve of any degree (de Casteljau)."""
    out = []
    for t in np.linspace(0.0, 1.0, samples):
        q = list(points)
        while len(q) > 1:
            q = [(1 - t) * a + t * b for a, b in zip(q, q[1:])]
        out.append(q[0])
    return out


def _read_paths(scene):
    paths = []
    for tree in scene.components("Path"):
        go = tree["m_GameObject"]["m_PathID"]
        root = scene.go_transform[go]
        points = []
        for child in scene.transforms[root]["m_Children"]:
            cid = child["m_PathID"]
            kids = scene.transforms[cid]["m_Children"]
            if kids:   # a Curve: its children are the Bezier control points
                points += _bezier([scene.world(k["m_PathID"]) for k in kids])
            else:      # a LineNode
                points.append(scene.world(cid))
        paths.append({
            "name": scene.go_name.get(go, ""),
            "active": bool(tree.get("isActive", 1)),
            "hidden": bool(tree.get("isHidden", 0)),
            "points": [[round(float(p[0]), 2), round(float(p[2]), 2), round(float(p[1]), 2)] for p in points],
        })
    return paths


def _read_areas(scene):
    areas = []
    for tree in scene.components("Area"):
        go = tree["m_GameObject"]["m_PathID"]
        tid = scene.go_transform[go]
        polygons = [[[round(float(w[0]), 2), round(float(w[2]), 2), round(float(w[1]), 2)]
                     for w in (scene.world(tid, (p["x"], p["y"], p["z"])) for p in poly["points"])]
                    for poly in tree.get("polygons", [])]
        circles = []
        for c in tree.get("blockerCircles", []) or []:
            # circle fields vary by version; keep whatever position/radius exists
            pos = c.get("position") or c.get("center") or {}
            if pos:
                w = scene.world(tid, (pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)))
                circles.append([round(float(w[0]), 2), round(float(w[2]), 2), float(c.get("radius", 0)),
                                round(float(w[1]), 2)])
        areas.append({
            "name": scene.go_name.get(go, ""),
            "type": AREA_TYPES.get(tree.get("type"), str(tree.get("type"))),
            "blocks_sight": bool(tree.get("isBlocker", 0)),
            "disabled": bool(tree.get("isDisabled", 0)),
            "tower_sizes": tree.get("filterInTowerSizes", ""),
            "polygons": polygons,
            "circles": circles,
        })
    return areas


def extract_map(bundle, monoscripts):
    """Geometry dict of one map bundle (opened from the cache copy)."""
    import UnityPy  # only needed for extraction
    scene = _Scene(UnityPy.load(str(monoscripts), str(_cached(bundle))))
    base = [t.get("type") for t in scene.components("BaseArea")]
    return {"version": GEOMETRY_VERSION, "bundle": bundle.name,
            "base": AREA_TYPES.get(base[0], "land") if base else "land",
            "paths": _read_paths(scene), "areas": _read_areas(scene)}


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
    return done


if __name__ == "__main__":
    # Manual refresh:  python -m btd6bot.gamefiles
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"{len(refresh())} maps extracted to {GEOMETRY_DIR}")
