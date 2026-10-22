"""One-time per map: sweep a held tower over the field and record legal spots."""
import logging
import time
from collections import deque

import numpy as np

from .maplearn import GRID

log = logging.getLogger("scanner")


def scan_placement(game, model, kind="dart", cls="land", step=5, settle=0.06):
    """Fill model.scan[cls] (1 = can place, 2 = blocked). Game must be idle."""
    w, h = GRID
    grid = model.scan.get(cls)
    if grid is None:
        grid = np.zeros((h, w), np.uint8)
    game.cancel_hold()
    baseline = game.fresh()
    if not game.hold(kind):
        log.warning("cannot hold %s for scanning", kind)
        return False
    t0 = time.time()
    n = 0
    try:
        for cy in range(step // 2, h, step):
            # serpentine order keeps mouse travel short
            xs = range(step // 2, w, step)
            if (cy // step) % 2:
                xs = reversed(list(xs))
            for cx in xs:
                fx, fy = model.cell_to_frac(cx, cy)
                y0, y1 = max(0, cy - step // 2), min(h, cy + step - step // 2)
                x0, x1 = max(0, cx - step // 2), min(w, cx + step - step // 2)
                if not game.s.owns_point(fx, fy):
                    continue
                ok = game.probe(fx, fy, baseline, settle=settle)
                grid[y0:y1, x0:x1] = 1 if ok else 2
                n += 1
            if not game.is_holding():  # something dropped the tower; pick it up again
                if not game.hold(kind):
                    break
    finally:
        game.cancel_hold()
    model.scan[cls] = grid
    log.info("scanned %d points for %s in %.0fs (%.0f%% placeable)", n, cls,
             time.time() - t0, 100 * (grid == 1).sum() / max(1, (grid > 0).sum()))
    return True


def _serpentine(step, w, h):
    """Lattice probe centres in the same order/positions as scan_placement."""
    for cy in range(step // 2, h, step):
        xs = list(range(step // 2, w, step))
        if (cy // step) % 2:
            xs.reverse()
        for cx in xs:
            yield cx, cy


def scan_water(game, model, kind="sub", step=5, settle=0.03, max_retakes=5):
    """Fill model.scan["water"] cheaply (1 = water tower fits, 2 = blocked, 0 = unknown).

    Water is always land-blocked, so only lattice points the land scan marked
    blocked and that are off the track estimate (learned track, else the guess
    from the land scan) are probed. Land-placeable cells are marked 2 without a
    probe. Points that turn out to be water also queue their land-blocked
    neighbours even if they lie on the guessed track, so lake rims and river
    banks the guess swallowed are still found. Incremental: cells already known
    are never probed again, so calling it later (e.g. once the real track has
    been learned, see model.water_pending()) only fills in the gaps.

    Holding a tower does not spend cash, but the game only lets you pick up a
    tower you can afford: returns False (nothing probed) if cash < price or the
    hold fails; the caller should retry later. Game must be idle (no round
    running). Returns True when every candidate was probed.
    """
    w, h = GRID
    land = model.scan.get("land")
    if land is None:
        log.warning("water scan needs the land scan first")
        return False
    todo = model.water_probe_mask(step)
    grid = model.scan.get("water")
    grid = np.zeros((h, w), np.uint8) if grid is None else grid.copy()
    grid[(land == 1) & (grid == 0)] = 2  # land-placeable is never water
    pts = [(cx, cy) for cx, cy in _serpentine(step, w, h) if todo[cy, cx]]
    if not pts:
        model.scan["water"] = grid
        log.info("water scan: no candidate cells")
        return True
    cash = game.cash_stable()
    price = game.price(kind)
    if cash is not None and price is not None and cash < price:
        log.info("water scan postponed: cash %s < %s price %s", cash, kind, price)
        return False
    game.cancel_hold()
    baseline = game.fresh()
    if not game.hold(kind):
        log.warning("cannot hold %s for water scanning", kind)
        return False

    def block(cx, cy):
        y0, y1 = max(0, cy - step // 2), min(h, cy + step - step // 2)
        x0, x1 = max(0, cx - step // 2), min(w, cx + step - step // 2)
        return slice(y0, y1), slice(x0, x1)

    t0 = time.time()
    queue, seen = deque(pts), set(pts)
    n = hits = retakes = 0
    complete = True
    try:
        while queue:
            cx, cy = queue.popleft()
            fx, fy = model.cell_to_frac(cx, cy)
            if not game.s.owns_point(fx, fy):
                complete = False  # covered by another window: stays unknown
                continue
            ok = game.probe(fx, fy, baseline, settle=settle)
            n += 1
            if ok and not game.is_holding():
                # without a held tower there is no red circle, so every probe
                # reads "ok": re-take the tower and retry this point
                if retakes >= max_retakes or not game.hold(kind):
                    queue.appendleft((cx, cy))
                    complete = False
                    break
                retakes += 1
                queue.appendleft((cx, cy))
                continue
            b = block(cx, cy)
            # a block straddling the shore: its land-placeable cells stay 2
            grid[b] = np.where(land[b] == 1, 2, 1) if ok else 2
            if ok:
                hits += 1
                for nx, ny in ((cx - step, cy), (cx + step, cy), (cx, cy - step), (cx, cy + step)):
                    if (0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen
                            and land[ny, nx] == 2 and grid[ny, nx] == 0):
                        seen.add((nx, ny))
                        queue.append((nx, ny))
    finally:
        game.cancel_hold()
    model.scan["water"] = grid
    log.info("water scan: probed %d points (%d water) in %.0fs, %d water cells",
             n, hits, time.time() - t0, int((grid == 1).sum()))
    return complete and not queue
