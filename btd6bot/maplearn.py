"""Learning a map's track from bloon motion, and picking tower spots from it.

The track is never hard-coded. While rounds play, consecutive frames are diffed;
bloons are the main thing that moves steadily, so motion accumulated over a few
rounds outlines the path. The time after round start at which motion first
reaches a pixel gives its progress along the track (entrance -> exit).

Per-map knowledge is cached in data/maps/<map>.npz and improves every game.
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data" / "maps"
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
        self.valid = {}  # tower -> {"x,y": bool} placement validity cache
        self.px_per_unit = None

    # -- persistence ------------------------------------------------------
    @property
    def path(self):
        return DATA / f"{slug(self.name)}.npz"

    def save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self.path, heat=self.heat, t_sum=self.t_sum, t_cnt=self.t_cnt,
            meta=json.dumps({"rounds_traced": self.rounds_traced, "valid": self.valid,
                             "px_per_unit": self.px_per_unit, "playfield": self.playfield}),
        )

    @classmethod
    def load(cls, name, playfield):
        m = cls(name, playfield)
        if m.path.exists():
            d = np.load(m.path, allow_pickle=False)
            m.heat, m.t_sum, m.t_cnt = d["heat"], d["t_sum"], d["t_cnt"]
            meta = json.loads(str(d["meta"]))
            m.rounds_traced = meta.get("rounds_traced", 0)
            m.valid = meta.get("valid", {})
            m.px_per_unit = meta.get("px_per_unit")
        return m

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
    def score_spots(self, range_cells, segment=(0.0, 1.0), avoid=(), min_sep=3.0, near=None,
                    near_radius=None):
        """Score every cell by how much (weighted) track lies within range.

        segment: only count track whose progress lies in this window.
        avoid: cells (cx, cy, r) occupied by placed towers.
        near: (cx, cy) a spot must be within near_radius of (support towers).
        """
        mask = self.track_mask().astype(np.float32)
        prog = self.progress()
        seg = ((prog >= segment[0]) & (prog <= segment[1])).astype(np.float32)
        weight = mask * np.nan_to_num(seg)
        r = max(1, int(round(range_cells)))
        disk = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
        cv2.circle(disk, (r, r), r, 1.0, -1)
        cover = cv2.filter2D(weight, -1, disk, borderType=cv2.BORDER_CONSTANT)
        # cannot stand on the track itself
        on_track = cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0
        cover[on_track] = -1
        hh, ww = cover.shape
        yy, xx = np.mgrid[0:hh, 0:ww]
        for ax, ay, ar in avoid:
            cover[(xx - ax) ** 2 + (yy - ay) ** 2 < (ar + min_sep) ** 2] = -1
        if near is not None:
            nr = near_radius or 6
            cover[(xx - near[0]) ** 2 + (yy - near[1]) ** 2 > nr ** 2] = -1
        # keep a margin from the play-field border (HUD lives there)
        cover[:3, :] = -1
        cover[-2:, :] = -1
        cover[:, :2] = -1
        cover[:, -2:] = -1
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
