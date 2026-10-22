"""How well each tower can reach each map's track - from the map's own geometry.

Why: on Luminous Cove land is only a strip along the bottom; the first ~70%
of both bloon paths runs between pools and walls that land towers cannot
stand on. A land-only plan (ninjas, super monkeys) could therefore only
defend the end of the track, and lost at round 47 although the planner had
rated it 0.86. Water towers (subs, buccaneers) reach those paths easily.

For every map with game geometry (mapgeom) and every tower with a range
(towers.TOWERS[kind]["range"], in world units), this module measures the
share of the EARLY track (the first EARLY_SPAN of progress) that lies within
that range of some cell where the tower may stand (placement.valid_spots:
the right surface, the tower's footprint). Towers with a global range
(sniper, mortar, heli, ace, dartling: range None) reach everything.
Reverse runs the track backwards, so "early" there is the other end.

Results are cached in data/map_fit.json per map, keyed by the geometry
stamp, and recomputed only when a map's geometry changes:
    python -m btd6bot.mapfit            # refresh (a few seconds per map)

The planner uses strategy_fit() to scale a strategy's win chance on a map.
"""
import json
import logging
from pathlib import Path

import cv2
import numpy as np

from . import towers as T

log = logging.getLogger("mapfit")

FIT_FILE = Path(__file__).resolve().parents[1] / "data" / "map_fit.json"
EARLY_SPAN = 0.7     # "early track": the first 70% of the way from entrance to exit


def _model_for(map_name):
    """A fresh MapModel filled from the game geometry, or None."""
    from . import layout as L
    from . import mapgeom as G
    from .maplearn import MapModel
    geom = G.load(map_name)
    if geom is None:
        return None, None
    model = MapModel(map_name, L.LAYOUTS["16:10"]["playfield"])
    G.apply(model, geom)
    return model, f'{geom.get("bundle")}#v{geom.get("version")}'


def kind_coverage(model, kind):
    """{"early": share of the early track in reach, "late": the same for the
    last EARLY_SPAN (what Reverse meets first)} for one tower kind."""
    from .placement import units_per_cell, valid_spots
    rng = T.TOWERS[kind].get("range")
    if rng is None:
        return {"early": 1.0, "late": 1.0}     # global range: the whole map
    ok = valid_spots(model, kind)
    if ok is None:
        return None
    track = model.t_cnt > 0
    if not track.any():
        return None
    progress = np.where(track, model.t_sum / np.maximum(model.t_cnt, 1), -1.0)
    radius = max(1, int(round(rng / units_per_cell(model))))
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    reach = cv2.dilate(ok.astype(np.uint8), disc) > 0
    early = track & (progress <= EARLY_SPAN)
    late = track & (progress >= 1.0 - EARLY_SPAN)

    def share(part):
        n = int(part.sum())
        return round(float((part & reach).sum()) / n, 3) if n else 1.0
    return {"early": share(early), "late": share(late)}


def refresh(maps=None):
    """Recompute the coverage of maps whose geometry changed. Returns the table."""
    from .account import MAPS
    table = load()
    kinds = [k for k in T.TOWERS if k != "hero"]
    changed = 0
    for name in maps or list(MAPS):
        try:
            model, stamp = _model_for(name)
        except Exception:
            log.exception("map fit: geometry of %s could not be applied", name)
            continue
        if model is None or table.get(name, {}).get("stamp") == stamp:
            continue
        cover = {}
        for kind in kinds:
            c = kind_coverage(model, kind)
            if c is not None:
                cover[kind] = c
        table[name] = {"stamp": stamp, "towers": cover}
        changed += 1
    if changed:
        FIT_FILE.write_text(json.dumps(table, indent=1, sort_keys=True), encoding="utf-8")
        log.info("map fit: %d maps measured", changed)
    return table


_CACHE = {"mtime": None, "table": {}}


def load():
    """The cached table ({} when it was never computed)."""
    try:
        mtime = FIT_FILE.stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        try:
            _CACHE["table"] = json.loads(FIT_FILE.read_text(encoding="utf-8"))
            _CACHE["mtime"] = mtime
        except (OSError, ValueError):
            return {}
    return _CACHE["table"]


def strategy_fit(map_name, kinds, reverse=False, weights=None):
    """How much of the early track a plan's damage towers can cover on this
    map, 0..1, or None when not measured: each tower kind's reach, weighted
    by `weights` (the cash the plan puts into it; equal when missing). A
    weighted mean rather than the best kind: one sniper does not make a
    ninja plan fit a map where the ninjas cannot reach the bloons."""
    entry = load().get(map_name)
    if not entry or not kinds:
        return None
    side = "late" if reverse else "early"
    known = [k for k in kinds if k in entry["towers"]]
    if not known:
        return None
    w = {k: max(0.0, (weights or {}).get(k, 1.0)) for k in known}
    total = sum(w.values()) or float(len(known))
    if not sum(w.values()):
        w = {k: 1.0 for k in known}
    return sum(w[k] * entry["towers"][k][side] for k in known) / total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t = refresh()
    for name in ("Luminous Cove", "Monkey Meadow", "Logs", "Lost Crevasse"):
        e = t.get(name, {}).get("towers", {})
        print(name, {k: e[k]["early"] for k in ("ninja", "sub", "super", "buccaneer", "sniper") if k in e})
