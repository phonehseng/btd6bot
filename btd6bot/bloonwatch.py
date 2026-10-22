"""How far along the track do the bloons get? Observed on screen, not modelled.

In ideal conditions bloons die soon after they enter; a defence whose bloons
reach 90% of the route is one leak away from a lost CHIMPS game (one life),
long before the lives counter shows anything. This module watches for that.

How a look works:
  * After the setup, before round 1 starts, the empty play field is learned
    for about a second and a half (EMPTY_FRAMES looks): per pixel, the range
    of colours it shows on its own (animated water included).
  * During a round, bloon-sized blobs (MIN_BLOB) of colours the empty map
    never showed, lying on a bloon route, are bloons.
  * Their position on the route - from the game's own path data
    (dps_model.Track) - says how far they got: 0 entrance .. 1 exit. Where two
    routes cross the same ground (Balance, Adora's Temple) the lowest
    progress counts, so the depth is never overstated.
  * A look's depth is the deepest blob that was also there, nearly as deep,
    one look earlier: a one-frame flicker is not a bloon.

Not bloons, and masked out:
  * anything that stays put for STICK_S (a tower bought after the setup),
  * spots that light up often (decorations, splashes): FLICKER_MAX,
  * the towers' own footprints and attack animations (TOWER_R),
  * looks with an upgrade panel open (most of its box differs from the
    empty map),
  * the HUD numbers (lives, cash, round) and the strip under the bot's
    status overlay at the top of the screen.

OBSERVE ONLY for now: Match logs each round's deepest point and saves
pictures of deep rounds in logs/bloonwatch/, and nothing is decided on it
until real games show it agrees with the lives counter. (Calibrating it on
the rolling recordings did not work: the 1280-px desktop video shows other
windows over the game and compresses small bloons away.)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("bloonwatch")

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "logs" / "bloonwatch"

WORK_SCALE = 4          # working resolution: the map grid (160 x 108) x 4 = 640 x 432
EMPTY_FRAMES = 15       # looks at the empty map after the setup
MARGIN = 28             # colour steps beyond the empty map's own range
MIN_BLOB = 25           # px at working resolution (a red bloon covers ~60-150)
STICK_S = 3.0           # a "new" spot that does not move for this long is scenery
FLICKER_TAU_S = 60.0    # how often a spot is "new", averaged over about this long ...
FLICKER_MAX = 0.08      # ... above this share it is animated scenery
TOWER_R = 0.02          # screen-width fraction masked around every tower
OVERLAY_BOTTOM = 0.05   # the status overlay (tools/overlay.py) ends above this
CONFIRM_DROP = 0.1      # a blob counts if one look earlier something was this close
PANEL_SHARE = 0.45      # this much of an upgrade panel's box changed: the panel is open
HUD_PAD = (0.06, 0.05)  # HUD boxes grow left (icons) and down (badges) by this much
DEEP = 0.8              # "deep": past this share of the route
SNAP_DEPTH = 0.9        # rounds this deep are saved as pictures ...
SNAPS_PER_GAME = 3      # ... at most this many per game


def route_progress(track, shape, band_cells=2):
    """Grid (shape = working resolution) of the progress (0..1) along the
    bloon routes, NaN off them; the lowest progress where routes overlap.
    Only stretches bloons can be hit on (track.paths[i]["hittable"])."""
    from .maplearn import GRID
    w, h = GRID
    lo = np.full((h, w), np.inf, np.float32)
    for p in track.paths:
        cells = track.proj.to_cells(p["xyz"])
        frac = p["dist"] / max(p["length"], 1e-6)
        for (cx, cy), f, ok in zip(cells, frac, p["hittable"]):
            if not ok:
                continue
            cx, cy = int(cx), int(cy)
            y0, y1 = max(cy - band_cells, 0), min(cy + band_cells + 1, h)
            x0, x1 = max(cx - band_cells, 0), min(cx + band_cells + 1, w)
            lo[y0:y1, x0:x1] = np.minimum(lo[y0:y1, x0:x1], f)
    grid = np.where(np.isfinite(lo), lo, np.nan).astype(np.float32)
    return cv2.resize(grid, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)


class BloonWatch:
    def __init__(self, map_key, playfield, panel_boxes=(), hud_boxes=(), progress=None):
        """map_key: the MapModel name ("<map>" or "<map> reverse").
        playfield: (x0, y0, x1, y1) screen fractions of the play field.
        panel_boxes: the upgrade panels' boxes, hud_boxes the HUD numbers'
        (screen fractions, layout.py). progress: a ready route-progress grid
        (tests); else built from the game's path data on first use."""
        from .maplearn import GRID
        self.playfield = playfield
        self.shape = (GRID[1] * WORK_SCALE, GRID[0] * WORK_SCALE)
        self.map_key = map_key or ""
        self.panel_px = [self._box_px(b) for b in panel_boxes]
        self.hud = np.zeros(self.shape, bool)       # never a bloon: the numbers change
        for x0, y0, x1, y1 in hud_boxes:
            ys, xs = self._box_px((x0 - HUD_PAD[0], y0, x1, y1 + HUD_PAD[1]))
            self.hud[ys, xs] = True
        self._progress = progress
        self.off = progress is None and not map_key
        self._empty = []
        self.lo = self.hi = None
        h, w = self.shape
        self.since = np.full((h, w), np.inf)            # when each spot turned "new"
        self.flicker = np.zeros((h, w), np.float32)
        self._t_prev = None
        self._prev_depths = []
        self._tower_key = None
        self._tower_mask = np.zeros((h, w), bool)
        self.snaps = 0
        self.reset_round()

    # -- set-up ---------------------------------------------------------------
    def _to_px(self, fx, fy):
        x0, y0, x1, y1 = self.playfield
        h, w = self.shape
        return int((fx - x0) / (x1 - x0) * w), int((fy - y0) / (y1 - y0) * h)

    def _box_px(self, box):
        """Rows and columns (slices, working resolution) of a screen box."""
        (x0, y0), (x1, y1) = self._to_px(box[0], box[1]), self._to_px(box[2], box[3])
        h, w = self.shape
        return slice(max(y0, 0), min(y1, h)), slice(max(x0, 0), min(x1, w))

    def progress(self):
        """The route-progress grid, or None (then the watch is off)."""
        if self._progress is None and not self.off:
            try:
                from .dps_model import Track
                rev = self.map_key.endswith(" reverse")
                track = Track(self.map_key[:-len(" reverse")] if rev else self.map_key, reverse=rev)
                grid = route_progress(track, self.shape)
                # the strip under the status overlay is never a route here
                rows = self.playfield[1] + (np.arange(self.shape[0]) + 0.5) / self.shape[0] \
                    * (self.playfield[3] - self.playfield[1])
                grid[rows < OVERLAY_BOTTOM, :] = np.nan
                self._progress = grid
            except Exception as e:     # no geometry for this map: no watch, no harm
                log.info("bloon watch off for %s: %s", self.map_key, e)
                self.off = True
        return self._progress

    def _small(self, frame):
        x0, y0, x1, y1 = self.playfield
        h, w = frame.shape[:2]
        pf = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        return cv2.resize(pf, (self.shape[1], self.shape[0]), interpolation=cv2.INTER_AREA).astype(np.int16)

    def learn_empty(self, frame):
        """One look at the empty map (no bloons, no panel open)."""
        if self.off or self.ready():
            return
        self._empty.append(self._small(frame))
        if len(self._empty) >= EMPTY_FRAMES:
            stack = np.stack(self._empty)
            self.lo = stack.min(axis=0) - MARGIN
            self.hi = stack.max(axis=0) + MARGIN
            self._empty = []

    def ready(self):
        return self.lo is not None and not self.off and self.progress() is not None

    # -- looking --------------------------------------------------------------
    def _towers_mask(self, towers):
        """Cells around every tower (bodies and attack animations)."""
        key = tuple(sorted((round(p.x, 3), round(p.y, 3)) for p in towers))
        if key != self._tower_key:
            self._tower_key = key
            h, w = self.shape
            r = max(1, int(TOWER_R / (self.playfield[2] - self.playfield[0]) * w))
            mask = np.zeros((h, w), np.uint8)
            for fx, fy in key:
                cv2.circle(mask, self._to_px(fx, fy), r, 1, -1)
            self._tower_mask = mask > 0
        return self._tower_mask

    def _panel_open(self, new):
        """An upgrade panel covers most of its box with colours the empty map
        never showed (a stream of bloons covers far less)."""
        return any(new[ys, xs].size and new[ys, xs].mean() > PANEL_SHARE for ys, xs in self.panel_px)

    def look(self, frame, now=None, towers=()):
        """One look during a round. Returns the depth (0..1) of the deepest
        confirmed bloon, 0.0 when none is seen, None when this look does not
        count (not ready, a panel open)."""
        if not self.ready():
            return None
        now = time.time() if now is None else now
        cur = self._small(frame)
        new = ((cur < self.lo) | (cur > self.hi)).any(axis=2)
        if self._panel_open(new):
            self._t_prev = None
            return None
        # scenery: what stays put (a tower bought later) joins the empty map
        self.since = np.where(new, np.minimum(self.since, now), np.inf)
        settled = new & (now - self.since > STICK_S)
        if settled.any():
            self.lo[settled] = np.minimum(self.lo[settled], cur[settled] - MARGIN)
            self.hi[settled] = np.maximum(self.hi[settled], cur[settled] + MARGIN)
            self.since[settled] = np.inf
            new &= ~settled
        # ... and what lights up often (decorations, splashes) is ignored
        dt = 0.2 if self._t_prev is None else min(max(now - self._t_prev, 0.0), 2.0)
        self._t_prev = now
        self.flicker += (new.astype(np.float32) - self.flicker) * (dt / FLICKER_TAU_S)
        prog = self.progress()
        bloon = new & ~np.isnan(prog) & (self.flicker <= FLICKER_MAX) & ~self._towers_mask(towers) & ~self.hud
        bloon = cv2.morphologyEx(bloon.astype(np.uint8), cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(bloon, 8)
        depths, boxes = [], []
        for k in range(1, n):
            if stats[k, cv2.CC_STAT_AREA] < MIN_BLOB:
                continue
            x, y, w, h = (int(v) for v in stats[k, :4])
            inside = lab[y:y + h, x:x + w] == k
            d = float(np.nanmax(prog[y:y + h, x:x + w][inside]))
            depths.append(d)
            boxes.append((d, (x, y, w, h)))
        # confirmed: something was nearly as deep one look earlier
        confirmed = [d for d in depths if any(p >= d - CONFIRM_DROP for p in self._prev_depths)]
        self._prev_depths = depths
        depth = max(confirmed, default=0.0)
        self._note(depth, frame, boxes)
        return depth

    # -- per round ------------------------------------------------------------
    def reset_round(self):
        self.round_max = 0.0
        self.looks = 0
        self.deep_looks = 0
        self._best = None       # (depth, frame, boxes) of the round's deepest look

    def _note(self, depth, frame, boxes):
        self.looks += 1
        self.deep_looks += depth >= DEEP
        if depth > self.round_max:
            self.round_max = depth
            if depth >= SNAP_DEPTH:
                self._best = (depth, frame, boxes)

    def end_round(self, rnd, label=""):
        """The round's summary {"round", "deepest", "deep_share", "looks"} (None
        when nothing was looked at); saves a picture of a deep round."""
        if not self.looks:
            self.reset_round()
            return None
        out = {"round": rnd, "deepest": round(self.round_max, 2),
               "deep_share": round(self.deep_looks / self.looks, 2), "looks": self.looks}
        if self._best is not None and self.snaps < SNAPS_PER_GAME:
            self.snaps += 1
            try:
                self._save(rnd, label, *self._best)
            except Exception as e:
                log.debug("bloon watch picture not saved: %s", e)
        self.reset_round()
        return out

    def _save(self, rnd, label, depth, frame, boxes):
        """The deepest look of a round with every bloon blob boxed and
        labelled with its depth (red: deep), for checking by eye."""
        img = cv2.resize(frame[int(self.playfield[1] * frame.shape[0]):int(self.playfield[3] * frame.shape[0]),
                               int(self.playfield[0] * frame.shape[1]):int(self.playfield[2] * frame.shape[1])],
                         (self.shape[1] * 2, self.shape[0] * 2), interpolation=cv2.INTER_AREA)
        for d, (x, y, w, h) in boxes:
            col = (0, 0, 255) if d >= DEEP else (0, 200, 0)
            cv2.rectangle(img, (2 * x - 3, 2 * y - 3), (2 * (x + w) + 3, 2 * (y + h) + 3), col, 2)
            cv2.putText(img, f"{d:.2f}", (2 * x, 2 * y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        name = "".join(ch for ch in f"{label}_{rnd}_{int(depth * 100)}" if ch.isalnum() or ch in "_-")
        cv2.imwrite(str(SNAP_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}.png"), img)
