"""Learning a map's track from bloon motion, and picking tower spots from it.

The track is never hard-coded. While rounds play, consecutive frames are diffed;
bloons are the main thing that moves steadily, so motion accumulated over a few
rounds outlines the path. The time after round start at which motion first
reaches a pixel gives its progress along the track (entrance -> exit).

Per-map knowledge is cached in data/maps/<map>.npz and improves every game.
"""
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data" / "maps"
# In-game buttons drawn over the play field (client fractions): placing a tower
# there would click the button instead.
UI_OVERLAYS = [
    (0.70, 0.02, 0.855, 0.21),   # round counter, gear, cancel-X while holding
    (0.00, 0.84, 0.14, 0.96),    # powers / hero ability buttons
]
GRID = (160, 108)  # internal resolution of the learned maps (w, h) of the playfield


def slug(name):
    return "".join(c for c in name.lower() if c.isalnum())


class MapModel:
    """Heat (how often bloons were seen) and progress (0 entrance..1 exit)."""

    def __init__(self, name, playfield):
        self.name = name
        self.playfield = playfield
        w, h = GRID
        self.heat = np.zeros((h, w), np.float32)
        self.t_sum = np.zeros((h, w), np.float32)
        self.t_cnt = np.zeros((h, w), np.float32)
        self.rounds_traced = 0
        self.sandbox_rounds = 0  # rounds traced in Sandbox (clean: no towers)
        # from the game's own map files (mapgeom.py); None when not available
        self.geometry_bundle = None   # bundle file the geometry came from
        self.small_only = None        # bool grid: only small towers fit here
        self.sight = None             # bool grid: line-of-sight blockers
        self.size_limit = None        # uint8 grid: largest tower size class allowed (1-4)
        self.mermonkey_water = None   # bool grid: water only a Mermonkey may use
        self.valid = {}  # tower -> {"x,y": bool} placement validity cache
        self.px_per_unit = None
        # placement scan per footprint class ("land"/"water"): 0 unknown, 1 ok, 2 blocked
        self.scan = {}
        # Spots the game refused during play, per surface ("land"/"water"):
        # bool grids, True = refused. Kept apart from `scan` on purpose:
        # mapgeom.apply() rewrites `scan` from the game files whenever the
        # geometry is (re-)applied, and refusals written into `scan` used to
        # vanish with it, so the bot tried the same bad spots on every visit.
        self.refused = {}
        # Spots the game ACCEPTED although the map file marks them blocked
        # (probed while holding a tower; e.g. Water Park's top-left pink
        # circle): bool grids per surface, added to what the geometry allows.
        self.accepted = {}
        # experience: "kind|cx|cy" -> [sum of relative pops-per-dollar, games]
        self.spot_stats = {}

    # -- persistence ------------------------------------------------------
    @property
    def path(self):
        return DATA / f"{slug(self.name)}.npz"

    def save(self):
        """Atomic write with retries (OneDrive can briefly lock files)."""
        DATA.mkdir(parents=True, exist_ok=True)
        scans = {f"scan_{k}": v for k, v in self.scan.items()}
        scans.update({f"refused_{k}": v for k, v in self.refused.items()})
        scans.update({f"accepted_{k}": v for k, v in self.accepted.items()})
        for key in ("small_only", "sight", "size_limit", "mermonkey_water"):
            if getattr(self, key, None) is not None:
                scans[f"geom_{key}"] = getattr(self, key)
        tmp = self.path.with_suffix(".tmp.npz")
        for attempt in range(5):
            try:
                np.savez_compressed(
                    tmp, heat=self.heat, t_sum=self.t_sum, t_cnt=self.t_cnt, **scans,
                    meta=json.dumps({"rounds_traced": self.rounds_traced, "valid": self.valid,
                                     "px_per_unit": self.px_per_unit, "playfield": self.playfield,
                             "spot_stats": self.spot_stats, "sandbox_rounds": self.sandbox_rounds,
                             "geometry_bundle": self.geometry_bundle}),
                )
                os.replace(tmp, self.path)
                return True
            except OSError:
                time.sleep(0.5 * (attempt + 1))
        return False

    @classmethod
    def load(cls, name, playfield):
        m = cls(name, playfield)
        if m.path.exists():
            try:
                d = np.load(m.path, allow_pickle=False)
                d.files  # noqa: B018 - forces the zip directory read
                m.heat, m.t_sum, m.t_cnt = d["heat"], d["t_sum"], d["t_cnt"]
                meta = json.loads(str(d["meta"]))
                m.rounds_traced = meta.get("rounds_traced", 0)
                m.valid = meta.get("valid", {})
                m.px_per_unit = meta.get("px_per_unit")
                m.spot_stats = meta.get("spot_stats", {})
                m.sandbox_rounds = meta.get("sandbox_rounds", 0)
                m.geometry_bundle = meta.get("geometry_bundle")
                for key in ("small_only", "sight", "mermonkey_water"):
                    if f"geom_{key}" in d.files:
                        setattr(m, key, d[f"geom_{key}"].astype(bool))
                if "geom_size_limit" in d.files:
                    m.size_limit = d["geom_size_limit"].astype(np.uint8)
                for k in d.files:
                    if k.startswith("scan_"):
                        m.scan[k[5:]] = d[k]
                    elif k.startswith("refused_"):
                        m.refused[k[len("refused_"):]] = d[k].astype(bool)
                    elif k.startswith("accepted_"):
                        m.accepted[k[len("accepted_"):]] = d[k].astype(bool)
            except Exception:
                return cls(name, playfield)  # corrupt file: relearn rather than crash
        return m

    # -- placement scan -------------------------------------------------------
    def blocked(self, cls="land"):
        """bool grid: True where a tower of this class cannot stand.

        land: unknown cells count as free (the land scan covers nearly everything).
        water: water is a minority of the map and the water scan only probes
        likely cells, so once a water scan exists anything not confirmed
        placeable is blocked. Without one, land-placeable cells are still known
        not to be water."""
        if cls == "land_or_water":  # e.g. Mermonkey: blocked only where both are
            return self.blocked("land") & self.blocked("water")
        return self._scan_blocked(cls) | self.refused_mask(cls)

    def _scan_blocked(self, cls):
        """blocked() as the placement scan alone sees it (no refusals)."""
        s = self.scan.get(cls)
        if cls == "water":
            if s is not None:
                return s != 1
            land = self.scan.get("land")
            if land is not None:
                return land == 1
            return np.zeros(self.heat.shape, bool)
        if s is None:
            return np.zeros(self.heat.shape, bool)
        return s == 2

    def refused_mask(self, surface):
        """bool grid: cells where the game refused a tower on this surface."""
        grid = self.refused.get(surface)
        return grid if grid is not None else np.zeros(self.heat.shape, bool)

    def refuse(self, surface, cx, cy, r=1):
        """Remember that the game refused a tower centred on cell (cx, cy):
        the (2r+1)-cell square around it is never offered again, in this game
        or later ones (saved with the model, untouched by mapgeom.apply)."""
        grid = self.refused.get(surface)
        if grid is None:
            grid = self.refused[surface] = np.zeros(self.heat.shape, bool)
        h, w = grid.shape
        grid[max(0, cy - r):min(h, cy + r + 1), max(0, cx - r):min(w, cx + r + 1)] = True

    def accepted_mask(self, surface):
        """bool grid: cells the game accepted a tower on although the map
        file marks them blocked (see accept)."""
        grid = getattr(self, "accepted", {}).get(surface)
        return grid if grid is not None else np.zeros(self.heat.shape, bool)

    def accept(self, surface, cx, cy):
        """Remember that the game placed a tower centred on cell (cx, cy) that
        the map file marks blocked: it counts as legal from now on (saved)."""
        grid = self.accepted.get(surface)
        if grid is None:
            grid = self.accepted[surface] = np.zeros(self.heat.shape, bool)
        grid[cy, cx] = True

    def scanned(self, cls="land"):
        if cls == "water":  # water scans are sparse by design
            return self.water_scanned()
        return cls in self.scan and (self.scan[cls] > 0).mean() > 0.5

    # -- water ------------------------------------------------------------------
    def water_scanned(self):
        return "water" in self.scan

    def water_cells(self):
        """bool grid: cells confirmed placeable for water towers."""
        s = self.scan.get("water")
        if s is None:
            return np.zeros(self.heat.shape, bool)
        return s == 1

    def has_water(self, min_cells=50):
        """True if a water scan found usable water (>= min_cells grid cells;
        one probe at step 5 marks 25 cells, so this needs >= 2 positive probes)."""
        return int(self.water_cells().sum()) >= min_cells

    def track_estimate(self):
        """bool grid of the track: learned from motion when there is enough of
        it, else guessed from the land scan's thin blocked corridors."""
        traced = self.track_mask()
        if traced.sum() >= 60:
            return traced
        return self.track_guess() > 0

    def water_probe_mask(self, step=5):
        """Cells worth probing with a water tower: blocked for land (water is
        always land-blocked), not yet known, and either off the track estimate
        or right next to confirmed water (lake rims / river banks that the
        track guess swallowed; step = scan lattice spacing)."""
        land = self.scan.get("land")
        if land is None:
            return np.zeros(self.heat.shape, bool)
        water = self.scan.get("water")
        if water is None:
            return (land == 2) & ~self.track_estimate()
        cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (2 * step + 1, 2 * step + 1))
        shore = cv2.dilate((water == 1).astype(np.uint8), cross) > 0
        return (land == 2) & (water == 0) & (~self.track_estimate() | shore)

    def water_pending(self, step=5):
        """How many lattice probe points scan_water(step=step) would still visit
        in its first pass (0 = nothing left to learn with the current track)."""
        m = self.water_probe_mask(step)
        return int(m[step // 2::step, step // 2::step].sum())

    def track_guess(self):
        """Before any bloon has been seen: thin blocked corridors look like track.

        Large obstacles (trees, water, buildings) are blocked too, but their
        interiors are far from any open ground; the track is a narrow band.
        """
        s = self.scan.get("land")
        if s is None:
            return np.zeros(self.heat.shape, np.float32)
        blocked = (s == 2).astype(np.uint8)
        dist = cv2.distanceTransform(blocked, cv2.DIST_L2, 3)
        # keep only blocked components whose widest point is track-like
        n, lab, stats, _ = cv2.connectedComponentsWithStats(blocked)
        thin = np.zeros(blocked.shape, bool)
        for i in range(1, n):
            comp = lab == i
            if dist[comp].max() <= 9 and stats[i, cv2.CC_STAT_AREA] >= 40:
                thin |= comp
            elif stats[i, cv2.CC_STAT_AREA] >= 40:
                thin |= comp & (dist <= 9)
        # border strips are scenery, not track
        thin[:3, :] = thin[-3:, :] = False
        return thin.astype(np.float32)

    # -- learned layers ---------------------------------------------------
    def track_mask(self):
        if self.heat.max() <= 0:
            return np.zeros_like(self.heat, bool)
        h = cv2.GaussianBlur(self.heat, (3, 3), 0)
        thr = max(2.0, 0.12 * np.percentile(h[h > 0], 99))
        mask = (h >= thr).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        # drop specks that are not part of long connected structures
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
        keep = np.zeros_like(mask)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= 25:
                keep[lab == i] = 1
        return keep.astype(bool)

    def progress(self):
        """0..1 progress along the track per grid cell (nan off-track)."""
        with np.errstate(invalid="ignore", divide="ignore"):
            t = self.t_sum / self.t_cnt
        mask = self.track_mask()
        out = np.full_like(t, np.nan)
        if mask.any():
            vals = t[mask]
            lo, hi = np.nanpercentile(vals, 2), np.nanpercentile(vals, 98)
            out[mask] = np.clip((t[mask] - lo) / max(1e-6, hi - lo), 0, 1)
        return out

    def track_weight(self):
        """Best estimate of the track: traced motion, plus scan corridors
        (motion is masked out near our own towers, the scan is not)."""
        traced = self.track_mask().astype(np.float32)
        guess = self.track_guess()
        if traced.sum() < 60:
            return guess
        near = cv2.dilate(traced, np.ones((9, 9), np.uint8)) > 0
        return np.maximum(traced, guess * near * 0.8 + guess * (~near) * 0.4)

    def progress_full(self):
        """progress() extended to every cell from the nearest traced cell."""
        prog = self.progress()
        known = ~np.isnan(prog)
        if not known.any():
            return np.zeros_like(prog)
        src = (~known).astype(np.uint8)
        _, labels = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 3,
                                                   labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(known)
        # label ids of zero-pixels are assigned in raster order
        lut = np.zeros(labels.max() + 1, np.float32)
        order = np.argsort(ys * prog.shape[1] + xs)
        lut[1:len(order) + 1] = prog[ys[order], xs[order]]
        return lut[labels]

    def known(self):
        return self.rounds_traced >= 2 and self.track_mask().sum() > 60

    # -- coordinate helpers -----------------------------------------------
    def cell_to_frac(self, cx, cy):
        x0, y0, x1, y1 = self.playfield
        w, h = GRID
        return x0 + (cx + 0.5) / w * (x1 - x0), y0 + (cy + 0.5) / h * (y1 - y0)

    def frac_to_cell(self, fx, fy):
        x0, y0, x1, y1 = self.playfield
        w, h = GRID
        return int((fx - x0) / (x1 - x0) * w), int((fy - y0) / (y1 - y0) * h)

    def radius_cells(self, range_units, screen_w):
        """Tower range (game units) -> grid cells."""
        ppu = self.px_per_unit or (screen_w / 1920 * 5.4)
        px = range_units * ppu
        cell_px = (self.playfield[2] - self.playfield[0]) * screen_w / GRID[0]
        return px / cell_px

    # -- choosing tower spots ---------------------------------------------
    def spot_weight(self, segment=(0.0, 1.0), covered=None):
        """Per-cell value of track for a new tower: track in the wanted progress
        segment, with track our towers already cover counting less."""
        mask = self.track_weight()
        if self.known() and segment != (0.0, 1.0):
            prog = self.progress_full()
            seg = ((prog >= segment[0]) & (prog <= segment[1])).astype(np.float32)
            weight = mask * seg
        else:
            weight = mask
        if covered is not None:
            # track already in range of our towers counts 30%: spreads defence
            # over every lane instead of stacking on one (multi-lane maps leak)
            weight = weight * (1.0 - 0.7 * np.clip(covered, 0, 1))
        return weight

    def score_spots(self, range_cells, segment=(0.0, 1.0), avoid=(), min_sep=3.0, near=None,
                    near_radius=None, placement="land", extra_block=None, covered=None,
                    valid=None):
        """Score every cell by how much (weighted) track lies within range.

        segment: only count track whose progress lies in this window.
        avoid: cells (cx, cy, r) occupied by placed towers.
        near: (cx, cy) a spot must be within near_radius of (support towers).
        valid: optional bool grid of where this tower may stand (placement.py,
               from the game's geometry incl. footprints and other towers);
               replaces the placement-class check and the avoid list.
        """
        mask = self.track_weight()
        weight = self.spot_weight(segment, covered)
        r = max(1, int(round(range_cells)))
        disk = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
        cv2.circle(disk, (r, r), r, 1.0, -1)
        cover = cv2.filter2D(weight, -1, disk, borderType=cv2.BORDER_CONSTANT)
        # cannot stand on the track itself, nor where the scan found it blocked
        on_track = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        cover[on_track] = -1
        if valid is not None:
            cover[~valid] = -1
        else:
            cover[self.blocked(placement)] = -1
        if extra_block is not None:
            cover[extra_block] = -1
        hh, ww = cover.shape
        yy, xx = np.mgrid[0:hh, 0:ww]
        for ax, ay, ar in (avoid if valid is None else ()):
            cover[(xx - ax) ** 2 + (yy - ay) ** 2 < (ar + min_sep) ** 2] = -1
        if near is not None:
            nr = near_radius or 6
            cover[(xx - near[0]) ** 2 + (yy - near[1]) ** 2 > nr ** 2] = -1
        # keep a margin from the play-field border; lives/cash/round HUD covers
        # roughly the top 8% of the screen
        cover[:8, :] = -1
        cover[-2:, :] = -1
        cover[:, :2] = -1
        cover[:, -4:] = -1
        for rect in UI_OVERLAYS:
            x0, y0 = self.frac_to_cell(rect[0], rect[1])
            x1, y1 = self.frac_to_cell(rect[2], rect[3])
            cover[max(0, y0):y1 + 1, max(0, x0):x1 + 1] = -1
        return cover

    def best_spots(self, cover, n=30):
        flat = cover.ravel()
        idx = np.argsort(flat)[::-1][: n * 6]
        spots, w = [], cover.shape[1]
        for i in idx:
            if flat[i] <= 0:
                break
            cy, cx = divmod(int(i), w)
            if all((cx - sx) ** 2 + (cy - sy) ** 2 >= 4 for sx, sy, _ in spots):
                spots.append((cx, cy, float(flat[i])))
            if len(spots) >= n:
                break
        return spots

    def debug_image(self):
        h = self.heat / max(1e-6, self.heat.max())
        prog = self.progress()
        img = np.zeros((*h.shape, 3), np.uint8)
        img[..., 1] = (h * 255).astype(np.uint8)
        p = np.nan_to_num(prog, nan=0)
        m = ~np.isnan(prog)
        img[m, 2] = (p[m] * 255).astype(np.uint8)
        img[m, 0] = ((1 - p[m]) * 255).astype(np.uint8)
        return cv2.resize(img, (GRID[0] * 6, GRID[1] * 6), interpolation=cv2.INTER_NEAREST)


class PathTracer:
    """Feed it frames while a round is running; it accumulates bloon motion."""

    def __init__(self, model, region_mask=None):
        self.m = model
        self.prev = None
        self.t0 = None
        self.first_seen = None
        self.region_mask = region_mask
        self.ambient = np.zeros(model.heat.shape, np.float32)
        self.ambient_frames = 0

    def _moving(self, cur, prev):
        diff = cv2.absdiff(cur, prev).max(axis=2)
        hsv = cv2.cvtColor(cur, cv2.COLOR_BGR2HSV)
        # bloons are vividly coloured (or black/white/lead later on); darts,
        # leaves and dust are not, so require saturation or very dark/bright
        vivid = (hsv[..., 1] > 110) | (hsv[..., 2] < 50)
        moving = ((diff > 40) & vivid).astype(np.uint8)
        moving = cv2.morphologyEx(moving, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        return cv2.resize(moving.astype(np.float32), GRID, interpolation=cv2.INTER_AREA) > 0.06

    def feed_idle(self, frame):
        """Call between rounds: learns scenery that animates on its own."""
        cur = self._small(frame)
        if self.prev is not None:
            self.ambient += self._moving(cur, self.prev)
            self.ambient_frames += 1
        self.prev = cur

    def ambient_mask(self):
        if self.ambient_frames < 5:
            return np.zeros(self.m.heat.shape, bool)
        amb = (self.ambient / self.ambient_frames) > 0.02
        return cv2.dilate(amb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    def _small(self, frame):
        x0, y0, x1, y1 = self.m.playfield
        h, w = frame.shape[:2]
        pf = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        g = cv2.resize(pf, (GRID[0] * 4, GRID[1] * 4), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(g, (3, 3), 0)

    def start_round(self):
        self.t0 = time.time()
        self.prev = None
        self.first_seen = np.full(self.m.heat.shape, np.nan, np.float32)
        self._amb = self.ambient_mask()

    def feed(self, frame, exclude=()):
        """exclude: list of (cx, cy, r) grid circles to ignore (towers, panels)."""
        cur = self._small(frame)
        if self.prev is None:
            self.prev = cur
            return
        small = self._moving(cur, self.prev)
        self.prev = cur
        small &= ~self._amb
        if self.region_mask is not None:
            small &= self.region_mask
        hh, ww = small.shape
        if exclude:
            yy, xx = np.mgrid[0:hh, 0:ww]
            for cx, cy, r in exclude:
                small[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = False
        # big simultaneous changes are screen transitions, not bloons
        if small.mean() > 0.25:
            return
        t = time.time() - self.t0
        self.m.heat[small] += 1
        newly = small & np.isnan(self.first_seen)
        self.first_seen[newly] = t

    def end_round(self):
        if self.first_seen is None:
            return
        seen = ~np.isnan(self.first_seen)
        if seen.sum() > 20:
            fs = self.first_seen.copy()
            # normalise this round's times to 0..1 so slow/fast rounds mix
            lo, hi = np.nanpercentile(fs[seen], 1), np.nanpercentile(fs[seen], 99)
            norm = np.clip((fs - lo) / max(1e-6, hi - lo), 0, 1)
            self.m.t_sum[seen] += norm[seen]
            self.m.t_cnt[seen] += 1
            self.m.rounds_traced += 1
        self.first_seen = None


def _spot_key(kind, cx, cy, cell=4):
    return f"{kind}|{int(cx) // cell}|{int(cy) // cell}"  # 4x4-cell buckets


def record_spot_results(model, towers):
    """After a game: each damage tower's pops per dollar relative to the game's
    median. Spots where a tower type keeps underperforming (blocked line of
    sight, wrong elevation, poor angle) get avoided next time."""
    rows = [(p, p.pops / max(p.spent, 1)) for p in towers
            if p.kind not in ("hero", "village", "alchemist", "farm")
            and getattr(p, "pops", None) and p.spent > 0]
    if len(rows) < 3:
        return
    med = sorted(r for _, r in rows)[len(rows) // 2] or 1e-9
    for p, r in rows:
        cx, cy = model.frac_to_cell(p.x, p.y)
        k = _spot_key(p.kind, cx, cy)
        tot, n = model.spot_stats.get(k, [0.0, 0])
        model.spot_stats[k] = [tot + min(r / med, 5.0), n + 1]


def spot_factor(model, kind, cx, cy):
    """Score multiplier learned from experience (1.0 when unknown)."""
    tot, n = (getattr(model, "spot_stats", None) or {}).get(_spot_key(kind, cx, cy), [0.0, 0])
    if not n:
        return 1.0
    rel = tot / n
    if rel < 0.35:
        return 0.3   # this tower type barely pops here
    if rel > 1.5:
        return 1.25
    return 1.0
