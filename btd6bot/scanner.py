"""One-time per map: sweep a held tower over the field and record legal spots."""
import logging
import time

import numpy as np

from .maplearn import GRID

log = logging.getLogger("scanner")


def scan_placement(game, model, kind="dart", cls="land", step=5, settle=0.03):
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
