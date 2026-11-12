"""The glass HUD's FIELD layer: what the bot sees of the map, drawn faintly
over the game's play field.

    ground   where a tower may stand, as the bot's placement sees it, in
             two steps: the ground the map allows (MapModel.scan plus the
             spots the game accepted) very faint, and where a small
             tower's centre fits (btd6bot.placement.valid_spots for a dart
             monkey on land, a sub on water: footprint room, the HUD's
             corners and refusals taken off) stronger, with a thin rim.
             Land mint green, water blue. Learned refusals
             (MapModel.refused, spots the game said no to) as a red hatch -
             bolder for the refusals every tower avoids, fainter for one
             tower's own (a big tower's footprint, "land@ace")
    paths    the bloon paths from the map's geometry (btd6bot.mapgeom) as
             smooth lines with small chevrons pointing the way bloons go:
               now    the path an alternating map hands this round - bright gold
               live   paths bloons take every round - warm white
               other  alternating paths of other rounds - pale, dimmer
               idle   paths no bloon takes in this path phase (Erosion) - dashed, dimmest
             On alternating maps each stretch is as strong as the share of
             rounds that pass it (mapgeom.round_share): the stretch every
             route shares stands out from one route's loop. Stretches where
             bloons cannot be hit (tunnels, gates) are dotted.
    track    on a map without geometry, the track the bot learned from
             bloon motion (MapModel.track_weight), as a warm tint instead

The ghosts (planned towers, glass_scene.GlassScene.ghosts) stay a widget of
their own, on top of this layer.

Cheap on purpose: FieldLayer.key() only compares a few small values (the
map, the round's path phase, the learned model's file time, looked at
every MODEL_STAT_S seconds), and the picture is drawn again only when the
key changes - a new map, a new round on a map whose paths alternate, a
model saved with new refusals (the bot saves it every 5 rounds and at the
end), the game window moved. The ground and the paths are cached apart, so
a new round redraws the paths only.

The learned models are read, never written: the copy loaded here is a
MapModel whose save() does nothing.

Switched off with a HUD_NO_FIELD file in the repo root (or
BTD6BOT_HUD_FIELD=off), polled like HUD_NO_THOUGHTS: no restart needed.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# The HUD does no heavy maths: one BLAS thread keeps numpy from committing
# ~750 MB of thread buffers in the HUD's process (measured on this laptop:
# 757 MB of commit with the default thread count, 17 MB with one). Only
# takes effect when numpy is not loaded yet, as in the HUD.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
from PIL import Image

import hud_data
from btd6bot.layout import LAYOUTS

FIELD_OFF = hud_data.ROOT / "HUD_NO_FIELD"   # this file hides the field layer ...
FIELD_ENV = "BTD6BOT_HUD_FIELD"              # ... as does this variable set to "off"
MODEL_STAT_S = 5.0                           # seconds between looks at the learned model's file time

# -- the look (RGB, opacity 0..1) ----------------------------------------------------------------
# Low opacities on purpose: the game has to stay readable under the layer.
# Mint green reads on sand, grass and snow alike and stays apart from the
# water's blue and the refusals' red.
LAND_GROUND = ((120, 255, 170), 0.06)  # land the map allows, very faint ...
LAND = ((120, 255, 170), 0.15)         # ... where a small tower's centre fits ...
LAND_RIM = ((150, 255, 190), 0.60)     # ... and the 1 px rim round that
WATER_GROUND = ((70, 140, 255), 0.08)  # water the map allows ...
WATER = ((70, 140, 255), 0.16)         # ... where a water tower's centre fits ...
WATER_RIM = ((120, 175, 255), 0.55)    # ... and its rim
REFUSED = ((255, 70, 70), 0.42)        # refusals every tower avoids: red hatch stripes
REFUSED_OWN = ((255, 120, 110), 0.20)  # one tower's own refusals (a big footprint): fainter
HATCH_EVERY, HATCH_WIDTH = 8, 2        # hatch stripe spacing and width, pixels at BASE_HEIGHT
TRACK = ((255, 185, 80), 0.30)         # the learned track, maps without geometry
PATHS = {                              # path status -> (colour, opacity, width at BASE_HEIGHT)
    "now": ((255, 210, 80), 0.80, 5.0),
    "live": ((255, 240, 210), 0.62, 4.0),
    "other": ((200, 215, 240), 0.42, 3.0),
    "idle": ((150, 160, 185), 0.28, 2.5),
}
PATH_ORDER = ("idle", "other", "live", "now")    # drawn in this order: the brightest on top
SHARE_FLOOR = 0.30         # a stretch only a few rounds pass keeps this share of its line's opacity
UNDER_ALPHA = 0.28         # a soft dark stroke under each line, so it reads on bright ground
UNDER_EXTRA = 3.0          # ... this many pixels (at BASE_HEIGHT) wider on each side
HIDDEN_ALPHA = 0.45        # a stretch where bloons cannot be hit: dotted, at this share
PIECE_PX = 6.0             # paths are drawn in pieces this long (pixels at BASE_HEIGHT)
CHEVRON_EVERY = 90.0       # a direction chevron every this many pixels along a path ...
CHEVRON_SIZE = 9.0         # ... this long ...
CHEVRON_ALPHA = 1.15       # ... a little stronger than its line (capped at opaque)
BASE_HEIGHT = 1200         # sizes above are pixels on a screen this tall
SUBPIXEL = 4               # cv2 drawing with 2**SUBPIXEL sub-pixel steps
SMALL_LAND_TOWER, WATER_TOWER = "dart", "sub"    # whose placement the ground shows


def field_wanted(root=None):
    """The owner's switch for the field layer: on unless a HUD_NO_FIELD file
    sits in the repo root or BTD6BOT_HUD_FIELD is "off"."""
    off = FIELD_OFF if root is None else Path(root) / FIELD_OFF.name
    return not off.exists() and os.environ.get(FIELD_ENV, "").strip().lower() not in ("off", "0", "no")


def playfield():
    """The play field as fractions of the game's client area (layout.LAYOUTS)."""
    return LAYOUTS["16:10"]["playfield"]


def playfield_rect(game_rect, pf=None):
    """The play field in screen pixels, (x0, y0, x1, y1), widened to whole
    pixels so the layer's window covers all of it. game_rect = (left, top,
    width, height) of the game's client area."""
    left, top, width, height = game_rect
    pf = pf or playfield()
    return (int(np.floor(left + pf[0] * width)), int(np.floor(top + pf[1] * height)),
            int(np.ceil(left + pf[2] * width)), int(np.ceil(top + pf[3] * height)))


def pixel_cells(game_rect, grid, pf=None):
    """For the layer's image over playfield_rect: the grid column of every
    pixel column and the grid row of every pixel row, -1 off the grid. A
    pixel belongs to the cell its centre falls in, the way MapModel.frac_to_cell
    sorts a screen fraction into a cell, so the tint lines up with the
    cells the bot reasons about."""
    left, top, width, height = game_rect
    pf = pf or playfield()
    x0, y0, x1, y1 = playfield_rect(game_rect, pf)
    gw, gh = grid

    def lookup(start, stop, origin, size, f0, f1, n):
        centres = (np.arange(start, stop) + 0.5 - origin) / size      # screen fractions
        idx = np.floor((centres - f0) / (f1 - f0) * n).astype(np.int32)
        idx[(idx < 0) | (idx >= n)] = -1
        return idx

    return (lookup(x0, x1, left, width, pf[0], pf[2], gw),
            lookup(y0, y1, top, height, pf[1], pf[3], gh))


# -- what the bot sees, in cells and fractions (no pixels) ----------------------------------------

@dataclass
class PathLine:
    """One bloon path: its points as screen fractions of the game's client
    area (bloons go from the first to the last), its status (see PATHS), a
    flag per segment for stretches where bloons cannot be hit, and the
    share of rounds per point (None: every round)."""
    name: str
    points: np.ndarray
    status: str
    hidden: np.ndarray
    share: np.ndarray | None = None


@dataclass
class FieldView:
    """What the field layer shows for one map at one round."""
    map: str
    land_ground: np.ndarray | None = None   # bool grid: land the map allows a tower on
    water_ground: np.ndarray | None = None  # bool grid: water the map allows a tower on
    land: np.ndarray | None = None          # bool grid: a small land tower's centre fits here
    water: np.ndarray | None = None         # bool grid: a water tower's centre fits here
    refused: np.ndarray | None = None       # bool grid: refusals every tower avoids
    refused_own: np.ndarray | None = None   # bool grid: one tower's own refusals
    track: np.ndarray | None = None         # float grid 0..1: the learned track (no geometry)
    paths: list = field(default_factory=list)
    grid: tuple = (160, 108)
    playfield: tuple = (0.0, 0.04, 0.855, 0.96)

    def ground_key(self):
        """Changes whenever the ground part of the picture would."""
        return tuple(None if g is None else hash(np.packbits(g).tobytes()) if g.dtype == bool
                     else hash(g.tobytes()) for g in (self.land_ground, self.water_ground, self.land, self.water,
                                                       self.refused, self.refused_own, self.track))

    def paths_key(self):
        """Changes whenever the paths part of the picture would."""
        return tuple((p.name, p.status, len(p.points), tuple(np.round(p.points[0], 4))) for p in self.paths)


class FieldSource:
    """Reads what the bot knows of a map: its learned model (data/maps, read
    only), its geometry, and from them a FieldView per round. Keeps the
    last model and geometry it read, so asking again is cheap."""

    def __init__(self, maps_dir, clock=time.time):
        self.maps_dir = Path(maps_dir)
        self.clock = clock
        self._stamps = {}           # model file -> (time looked, mtime)
        self._models = {}           # (name, mtime) -> MapModel (the newest one only)
        self._geoms = {}            # map name -> geometry dict or None
        self._panes = {}            # map name -> has panes that open in turn
        self._moving = {}           # map name -> its ground changes during a game (_moving_ground)

    # -- the learned model ------------------------------------------------------------------
    def model_path(self, name):
        from btd6bot.maplearn import slug
        return self.maps_dir / f"{slug(name)}.npz"

    def stamp(self, name):
        """The model file's modification time (None: no file), looked at no
        more than every MODEL_STAT_S seconds."""
        path = self.model_path(name)
        now = self.clock()
        seen = self._stamps.get(path)
        if seen is None or now - seen[0] >= MODEL_STAT_S:
            try:
                t = path.stat().st_mtime_ns
            except OSError:
                t = None
            seen = self._stamps[path] = (now, t)
        return seen[1]

    def model(self, name):
        """The bot's MapModel of `name` as saved, or one painted from the
        map's geometry alone when nothing was saved yet (None when neither
        exists). Never written back."""
        key = (name, self.stamp(name))
        if key in self._models:
            return self._models[key]
        from btd6bot import maplearn, mapgeom
        maps_dir = self.maps_dir

        class ReadOnlyModel(maplearn.MapModel):
            """A MapModel read from this source's folder; save() does nothing."""
            @property
            def path(self):
                return maps_dir / f"{maplearn.slug(self.name)}.npz"

            def save(self):
                return False

        model = ReadOnlyModel.load(name, playfield())
        geom = self.geometry(name)
        if geom is not None and not model.has_geometry_grids():
            mapgeom.apply(model, geom)                 # in memory, as the runner does before a game
        if not model.scan and model.heat.max() <= 0:
            model = None                               # nothing known about this map
        self._models = {key: model}                    # one map at a time
        return model

    def geometry(self, name):
        if name not in self._geoms:
            from btd6bot import mapgeom
            try:
                self._geoms[name] = mapgeom.load(name)
            except Exception:
                self._geoms[name] = None
        return self._geoms[name]

    # -- per round ----------------------------------------------------------------------------
    def phase_key(self, map_name, rnd, pane_round=None, ground=None):
        """What decides the paths' statuses and the ground at round `rnd`:
        the idle paths, the path this round, the round itself only on maps
        whose panes open in turn (Covered Garden), and on maps whose ground
        changes in the game the bot's ground (see ground_args). Equal keys,
        equal views."""
        from btd6bot import mapgeom
        geom = self.geometry(map_name)
        if geom is None:
            return None
        panes = (pane_round or rnd) if self._has_panes(map_name) else None
        moving = self.ground_args(map_name, rnd, pane_round, ground) if self._moving_ground(map_name) else None
        return (mapgeom.idle_phase_paths(geom, rnd), mapgeom.paths_this_round(geom, rnd), panes, moving)

    def ground_args(self, map_name, rnd, pane_round=None, ground=None):
        """(now_round, pose_round, horizon) to build the ground with, as the
        bot's placement does (Executor._legal_cells): the round the bot judges
        ground by, from hud.json - on pane maps the pane the screen shows
        first - the platforms' pose, and the last round new ground must last
        (Erosion: the phase's end). Without them the layer drew the whole-
        game ground: Sanctuary in its opening layout, about 114 cells on
        Erosion, none of One Two Tree's opened plots (audit 2026-11-12)."""
        ground = ground or {}
        now = ground.get("now_round")
        if self._has_panes(map_name):
            now = pane_round or now or rnd
        return now, ground.get("pose_round"), ground.get("ground_horizon")

    def _moving_ground(self, map_name):
        """Does the map's ground change during a game (mapgeom.dynamics:
        panes, areas that come or go, moving platforms) or follow path
        phases? Only there the bot's round and pose change the ground."""
        if map_name not in self._moving:
            from btd6bot import mapgeom
            geom = self.geometry(map_name)
            try:
                dyn = mapgeom.dynamics(geom) if geom is not None else None
                self._moving[map_name] = bool(dyn is not None and (
                    dyn.panes or dyn.appear or dyn.vanish or dyn.movers
                    or mapgeom.phase_end(geom, 1) is not None))
            except Exception:
                self._moving[map_name] = False
        return self._moving[map_name]

    def _has_panes(self, map_name):
        """Does the map have panes that open in turn (mapgeom.dynamics)? Its
        ground then changes every round, as the bot's placement sees it."""
        if map_name not in self._panes:
            from btd6bot import mapgeom
            geom = self.geometry(map_name)
            try:
                self._panes[map_name] = bool(geom is not None and mapgeom.dynamics(geom).panes)
            except Exception:
                self._panes[map_name] = False
        return self._panes[map_name]

    def view(self, map_name, mode=None, rnd=None, end_round=None, pane_round=None, ground=None):
        """The FieldView of `map_name` (a Reverse game's model is the map's
        own, its paths run backwards) at round `rnd` of a game ending at
        `end_round`; None when nothing is known about the map."""
        # pane_round: the round whose pane the bot saw open on screen. The
        # bot's own round lags it by one between rounds (Covered Garden's
        # pane changes as a round ends; the round counter is read later), and
        # the green ground then showed the pane that had just shut - while the
        # bot was buying. Without it, the round as before.
        # ground: the bot's now_round, pose_round and ground_horizon from
        # hud.json (ground_args).
        reverse = is_reverse(mode)
        name = map_name + " reverse" if reverse and self.stamp(map_name + " reverse") is not None else map_name
        model = self.model(name)
        if model is None:
            return None
        geom = self.geometry(map_name)
        from btd6bot.maplearn import GRID
        view = FieldView(map=map_name, grid=GRID, playfield=tuple(model.playfield))
        self._ground(view, model, end_round, geom, self.ground_args(map_name, rnd, pane_round, ground))
        if geom is not None:
            view.paths = path_lines(geom, model.playfield, rnd, reverse)
        if not view.paths:
            weight = model.track_weight()
            if weight.max() > 0:
                view.track = np.clip(weight / weight.max(), 0, 1).astype(np.float32)
        return view

    def _ground(self, view, model, end_round, geom, args):
        """Legal land and water as the bot's placement sees them, and the
        learned refusals on ground the map itself allows. args: ground_args."""
        from btd6bot import placement as PL
        now, pose, horizon = args if geom is not None else (None, None, None)
        last = end_round if horizon is None else horizon if end_round is None else min(end_round, horizon)
        try:
            land = PL.valid_spots(model, SMALL_LAND_TOWER, last_round=last, now_round=now, pose_round=pose)
            water = PL.valid_spots(model, WATER_TOWER, last_round=last, now_round=now, pose_round=pose)
        except Exception:
            land = water = None
        if land is None:            # no geometry: the placement scan as the bot keeps it
            land = ~model.blocked("land") if model.scanned("land") else None
            water = model.water_cells() & ~model.refused_mask("water") if model.water_scanned() else None
        view.land, view.water = land, water
        ground = {s: (model.scan[s] == 1) | model.accepted_mask(s) for s in ("land", "water") if s in model.scan}
        view.land_ground, view.water_ground = ground.get("land"), ground.get("water")
        shared = np.zeros(model.heat.shape, bool)
        own = np.zeros(model.heat.shape, bool)
        for layer, grid in model.refused.items():
            surface = layer.split("@")[0]
            if surface not in ground or grid.shape != shared.shape:
                continue
            (own if "@" in layer else shared)[:] |= grid & ground[surface]
        view.refused = shared if shared.any() else None
        own &= ~shared
        view.refused_own = own if own.any() else None


def is_reverse(mode):
    """Does this mode run the map backwards (strategy.MODE_RULES "reversed")?"""
    if not mode:
        return False
    try:
        from btd6bot.strategy import MODE_RULES
        return bool(MODE_RULES.get(mode, {}).get("reversed"))
    except Exception:
        return mode == "reverse"


def path_lines(geom, pf, rnd, reverse=False):
    """[PathLine] for the paths bloons can take on this map (boss-only and
    out-of-sight paths left out, as the bot leaves them out), with their
    status at round `rnd`."""
    from btd6bot import mapgeom
    from btd6bot.maplearn import GRID
    proj = mapgeom.Projection(pf)
    idle = mapgeom.idle_phase_paths(geom, rnd)
    now = mapgeom.paths_this_round(geom, rnd)
    alternating = set(mapgeom.path_round_shares(geom))
    for s in (geom.get("mechanics") or {}).get("splitters") or []:
        if s.get("type") == "AlternateRoundSplitter":
            alternating |= set(s.get("paths") or ())
    boss = mapgeom._boss_paths(geom)
    share_grid = mapgeom.round_share(geom, proj, idle)
    if share_grid is not None:
        import cv2
        share_grid = cv2.dilate(share_grid, np.ones((3, 3), np.uint8))   # lines run a cell off-centre at times
    out = []
    for path in mapgeom.bloon_paths(geom):
        pid = path.get("id")
        if path.get("hidden") or len(path.get("points") or ()) < 2 or pid in boss:
            continue
        status = ("idle" if pid in idle else "now" if pid in now
                  else "other" if pid in alternating else "live")
        pts = proj.to_frac(path["points"])
        hidden = np.zeros(len(pts) - 1, bool)
        for a, b in path.get("invulnerable", []):
            hidden[max(0, a - 1):max(0, b + 1)] = True   # segments touching a hidden point (as paint_paths)
        share = None
        if share_grid is not None:
            cells = proj.to_cells(path["points"])
            col = np.clip(cells[:, 0].astype(int), 0, GRID[0] - 1)
            row = np.clip(cells[:, 1].astype(int), 0, GRID[1] - 1)
            share = share_grid[row, col]
        if reverse:
            pts, hidden = pts[::-1], hidden[::-1]
            share = None if share is None else share[::-1]
        out.append(PathLine(path.get("name", str(pid)), pts, status, hidden, share))
    return out


# -- drawing ----------------------------------------------------------------------------------

def _grid_tints(view):
    """The ground's tints composited at grid resolution ((rows, cols, 4)
    uint8, straight alpha): cheap, as the grid has only ~17,000 cells."""
    gw, gh = view.grid
    rgb = np.zeros((gh, gw, 3), np.float32)
    a = np.zeros((gh, gw), np.float32)

    def over(mask, look):
        colour, alpha = look
        t = np.asarray(mask, np.float32) * alpha
        new_a = t + a * (1 - t)
        rgb[:] = (np.asarray(colour, np.float32) * t[..., None] + rgb * (a * (1 - t))[..., None]) \
            / np.maximum(new_a, 1e-6)[..., None]
        a[:] = new_a

    if view.track is not None:
        over(view.track, TRACK)
    for grid, look in ((view.land_ground, LAND_GROUND), (view.water_ground, WATER_GROUND),
                       (view.land, LAND), (view.water, WATER)):
        if grid is not None and grid.any():
            over(grid, look)
    out = np.zeros((gh, gw, 4), np.uint8)
    out[..., :3] = np.round(rgb)
    out[..., 3] = np.round(a * 255)
    return out


def _rim(mask):
    """The 1 px inner edge of a bool mask (pixels with a 4-neighbour outside it)."""
    inner = mask.copy()
    inner[1:] &= mask[:-1]
    inner[:-1] &= mask[1:]
    inner[:, 1:] &= mask[:, :-1]
    inner[:, :-1] &= mask[:, 1:]
    return mask & ~inner


def _paint(out, mask, look):
    """Set `out` (RGBA uint8) to a colour at an opacity wherever `mask` is
    (painted over what is there: rims and hatch sit on top of the tints)."""
    colour, alpha = look
    out[mask] = (*colour, int(round(255 * alpha)))


def draw_ground(view, game_rect):
    """The ground layer over playfield_rect(game_rect) as an RGBA image.
    The tints are composited on the grid and then blown up to pixels (each
    pixel taking its cell's colour, see pixel_cells); only the rims and the
    hatch are worked out per pixel."""
    cols, rows = pixel_cells(game_rect, view.grid, view.playfield)
    h, w = len(rows), len(cols)
    inside = (rows[:, None] >= 0) & (cols[None, :] >= 0)
    rr, cc = np.clip(rows, 0, None), np.clip(cols, 0, None)

    def up(grid):          # a bool cell grid at the layer's pixels
        return grid[rr[:, None], cc[None, :]] & inside

    out = _grid_tints(view)[rr[:, None], cc[None, :]]
    out[~inside] = 0
    for grid, rim in ((view.land, LAND_RIM), (view.water, WATER_RIM)):
        if grid is not None and grid.any():
            _paint(out, _rim(up(grid)), rim)
    unit = game_rect[3] / BASE_HEIGHT
    every = max(3, int(round(HATCH_EVERY * unit)))
    stripe = np.add.outer(np.arange(h), np.arange(w)) % every < max(1, int(round(HATCH_WIDTH * unit)))
    for grid, look in ((view.refused_own, REFUSED_OWN), (view.refused, REFUSED)):
        if grid is not None and grid.any():
            m = up(grid)
            _paint(out, m & stripe, look)
            _paint(out, _rim(m), (look[0], look[1] * 0.6))
    return Image.fromarray(out, "RGBA")


def _resample(pts, step):
    """A polyline (N x 2 pixels) cut into pieces about `step` long:
    (starts, ends, segment index of each piece, distance along the line at
    each piece's middle, how far along its segment each middle lies 0..1)."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    dist = np.concatenate([[0.0], np.cumsum(seg)])
    total = dist[-1]
    if total <= 0:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, int), np.zeros(0), np.zeros(0)
    n = max(1, int(np.ceil(total / step)))
    d = np.linspace(0, total, n + 1)
    xy = np.stack([np.interp(d, dist, pts[:, 0]), np.interp(d, dist, pts[:, 1])], axis=1)
    mid = (d[:-1] + d[1:]) / 2
    index = np.clip(np.searchsorted(dist, mid) - 1, 0, len(seg) - 1)
    along = np.clip((mid - dist[index]) / np.maximum(seg[index], 1e-6), 0, 1)
    return xy[:-1], xy[1:], index, mid, along


def draw_paths(view, game_rect):
    """The paths layer over playfield_rect(game_rect) as an RGBA image. Each
    status's lines are drawn as an opacity mask with OpenCV (anti-aliased,
    sub-pixel), then tinted and composited, a soft dark stroke under all."""
    import cv2
    x0, y0, x1, y1 = playfield_rect(game_rect, view.playfield)
    w, h = x1 - x0, y1 - y0
    left, top, gw, gh = game_rect
    unit = gh / BASE_HEIGHT
    scale = 1 << SUBPIXEL
    under = np.zeros((h, w), np.uint8)
    layers = {s: np.zeros((h, w), np.uint8) for s in PATH_ORDER}
    for status in PATH_ORDER:
        colour, alpha, width = PATHS[status]
        thick = max(1, int(round(width * unit)))
        for line in (p for p in view.paths if p.status == status):
            px = np.stack([left + line.points[:, 0] * gw - x0, top + line.points[:, 1] * gh - y0], axis=1)
            a, b, seg, mid, along = _resample(px, max(2.0, PIECE_PX * unit))
            if not len(a):
                continue
            if line.share is not None:      # the share at each piece: that of its segment's nearer end
                share = np.where(along < 0.5, line.share[seg], line.share[seg + 1])
                share = np.where(share > 0, share, 1.0)     # a point off every listed path: every round
            else:
                share = np.ones(len(a))
            # the path this round is drawn in full; the others as strong as their share of the rounds
            strength = alpha * (np.ones(len(a)) if status == "now" else SHARE_FLOOR + (1 - SHARE_FLOOR) * share)
            hidden = line.hidden[seg]
            for k in range(len(a)):
                if hidden[k] and k % 2:
                    continue                    # dotted where bloons cannot be hit
                v = strength[k] * (HIDDEN_ALPHA if hidden[k] else 1.0)
                p0 = tuple(int(round(c * scale)) for c in a[k])
                p1 = tuple(int(round(c * scale)) for c in b[k])
                cv2.line(layers[status], p0, p1, int(round(255 * min(1.0, v))), thick, cv2.LINE_AA, SUBPIXEL)
                cv2.line(under, p0, p1, int(round(255 * UNDER_ALPHA * min(1.0, v / alpha))),
                         thick + 2 * max(1, int(round(UNDER_EXTRA * unit))), cv2.LINE_AA, SUBPIXEL)
            # chevrons pointing the way bloons go, on stretches where they can be hit
            size = CHEVRON_SIZE * unit
            for d in np.arange(CHEVRON_EVERY * unit / 2, mid[-1] if len(mid) else 0, CHEVRON_EVERY * unit):
                k = min(int(np.searchsorted(mid, d)), len(a) - 1)
                if hidden[k]:
                    continue
                tip = (a[k] + b[k]) / 2
                t = b[k] - a[k]
                t = t / max(1e-6, np.linalg.norm(t))
                n = np.array([-t[1], t[0]])
                v = int(round(255 * min(1.0, strength[k] * CHEVRON_ALPHA)))
                for wing in (tip - size * t + 0.75 * size * n, tip - size * t - 0.75 * size * n):
                    q0 = tuple(int(round(c * scale)) for c in tip)
                    q1 = tuple(int(round(c * scale)) for c in wing)
                    cv2.line(layers[status], q0, q1, v, max(1, int(round(2.5 * unit))), cv2.LINE_AA, SUBPIXEL)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for colour, alpha in [((0, 0, 0), under)] + [(PATHS[s][0], layers[s]) for s in PATH_ORDER]:
        if alpha.any():          # a solid colour seen through the drawn opacities, over what is there
            out.alpha_composite(Image.merge("RGBA", [Image.new("L", (w, h), c) for c in colour]
                                            + [Image.fromarray(alpha, "L")]))
    return out


class FieldLayer:
    """The field layer for the glass HUD: key() says when the picture would
    change, picture() draws it (glass_scene.Picture over the play field).
    `maps_dir` is where the bot keeps its learned models (data/maps)."""

    def __init__(self, maps_dir=None, clock=time.time):
        self.source = FieldSource(maps_dir or hud_data.ROOT / "data" / "maps", clock)
        self._key_memo = (None, None)          # (snapshot, key): one key per poll of the bot's files
        self._ground = (None, None)            # (key, RGBA image): kept apart, so a new round ...
        # ... on an alternating map draws only the paths again
        self._paths = (None, None)
        self._picture = (None, None)           # (key, Picture): the last picture drawn
        self.error = None                      # why the last picture could not be drawn, if it could not
        self.last_ms = None                   # how long the last picture took to draw

    @staticmethod
    def game_of(snap):
        """(map, mode, round, end round) of the game in a snapshot."""
        g = snap.game or {}
        return g.get("map"), g.get("mode"), snap.round, g.get("end_round")

    @staticmethod
    def pane_round_of(snap):
        """The round Covered Garden's open pane belongs to, as the bot saw
        it on screen (hud.json "pane_round"); None when the bot did not say."""
        return getattr(snap, "pane_round", None)

    @staticmethod
    def ground_of(snap):
        """The bot's ground facts from hud.json (FieldSource.ground_args)."""
        return {k: getattr(snap, k, None) for k in ("now_round", "pose_round", "ground_horizon")}

    def key(self, snap, game_rect):
        """A small tuple that changes when the picture would; None when there
        is nothing to show (no map, nothing known about it)."""
        if self._key_memo[0] is snap and self._key_memo[1][0] == game_rect:
            return self._key_memo[1][1]
        map_name, mode, rnd, end = self.game_of(snap)
        key = None
        if map_name and game_rect:
            try:
                name = map_name + " reverse" if is_reverse(mode) else map_name
                stamps = (self.source.stamp(name), self.source.stamp(map_name))
                if any(s is not None for s in stamps) or self.source.geometry(map_name) is not None:
                    phase = self.source.phase_key(map_name, rnd, self.pane_round_of(snap), self.ground_of(snap))
                    key = (map_name, mode, end, phase, stamps, tuple(game_rect))
            except Exception:
                key = None
        self._key_memo = (snap, (game_rect, key))
        return key

    def picture(self, snap, game_rect):
        """The layer as a glass_scene.Picture, or None with nothing to show.
        A map whose files cannot be read leaves the layer hidden (the error
        kept in self.error) until the key changes: one bad map file must not
        make the HUD redraw every widget on every tick."""
        key = self.key(snap, game_rect)
        if key is not None and self._picture[0] == key:
            return self._picture[1]                 # nothing changed since it was drawn
        try:
            picture = self._draw(snap, game_rect)
            self.error = None
        except Exception as e:                      # (MemoryError and the like included)
            picture, self.error = None, f"{type(e).__name__}: {e}"
        self._picture = (key, picture)
        return picture

    def _draw(self, snap, game_rect):
        from glass_scene import Picture
        t0 = time.perf_counter()
        map_name, mode, rnd, end = self.game_of(snap)
        if not map_name or not game_rect:
            return None
        view = self.source.view(map_name, mode, rnd, end, self.pane_round_of(snap), self.ground_of(snap))
        if view is None:
            return None
        rect = tuple(game_rect)
        gk, pk = (view.ground_key(), rect), (view.paths_key(), rect)
        if self._ground[0] != gk:
            self._ground = (gk, draw_ground(view, rect))
        if self._paths[0] != pk:
            self._paths = (pk, draw_paths(view, rect))
        x0, y0, _x1, _y1 = playfield_rect(rect, view.playfield)
        picture = Picture(Image.alpha_composite(self._ground[1], self._paths[1]), x0, y0)
        self.last_ms = (time.perf_counter() - t0) * 1000
        return picture
