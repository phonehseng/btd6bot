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

Map mechanics count (docs/map_mechanics.md): the spots are those valid for
the WHOLE game (ground that erodes, floods or is closed off later is left
out), stretches of track where bloons cannot be hit (gates, tunnels) are not
counted, and a tower on moving ground (Geared, Sanctuary) only reaches what
it reaches in every position the ground carries it to.

Results are cached in data/map_fit.json per map, keyed by the geometry
stamp and the version of the mechanics rules (mapgeom.RULES_VERSION), and
recomputed only when one of them changes:
    python -m btd6bot.mapfit            # refresh (a few seconds per map)
Each entry also lists the map's mechanics ("mechanics") and plain advice
("advice", e.g. that global-range towers suit it better).

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
    return model, stamp_of(geom)


def stamp_of(geom):
    """What a cached measurement depends on: the game's map bundle, the
    extraction version, and the version of the rules that interpret the
    map's mechanics (any of them changing re-measures the map)."""
    from .mapgeom import RULES_VERSION
    return f'{geom.get("bundle")}#v{geom.get("version")}#r{RULES_VERSION}'


def kind_coverage(model, kind, last_round=None):
    """{"early": share of the early track in reach, "late": the same for the
    last EARLY_SPAN (what Reverse meets first)} for one tower kind, for a
    game ending at `last_round` (None: the longest game)."""
    from .placement import units_per_cell, valid_spots
    rng = T.TOWERS[kind].get("range")
    if rng is None:
        return {"early": 1.0, "late": 1.0}     # global range: the whole map
    ok = valid_spots(model, kind, last_round=last_round)
    if ok is None:
        return None
    track = model.t_cnt > 0
    if not track.any():
        return None
    progress = np.where(track, model.t_sum / np.maximum(model.t_cnt, 1), -1.0)
    try:   # moving ground: only what is reached in every position counts
        from .mapgeom import reliable_reach
        reach = reliable_reach(model, ok, rng, track)
    except Exception:
        log.exception("map fit: reach on %s measured without moving ground", model.name)
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
        table[name] = {"stamp": stamp, "towers": cover, **_mechanics_notes(name)}
        # maps whose ground changes by round (Erosion) fit short games better
        shorter = {}
        if _changes_by_round(name):
            for last in game_lengths():
                part = {k: c for k in kinds if (c := kind_coverage(model, k, last)) is not None}
                if part != cover:
                    shorter[str(last)] = part
        if shorter:
            table[name]["by_last_round"] = shorter
        changed += 1
    if changed:
        FIT_FILE.write_text(json.dumps(table, indent=1, sort_keys=True), encoding="utf-8")
        log.info("map fit: %d maps measured", changed)
    return table


def game_lengths():
    """Last rounds of the shorter games (Easy, Medium, Hard: 40, 60, 80),
    read from the decoded game model; the longest game is the default."""
    path = FIT_FILE.parent / "game_model" / "difficulties.json"
    try:
        modes = json.loads(path.read_text(encoding="utf-8"))
        ends = {m.get("end_round") for name, m in modes.items() if name in ("Easy", "Medium", "Hard")}
        return sorted(e for e in ends if e)
    except (OSError, ValueError, AttributeError):
        return [40, 60, 80]


def _changes_by_round(map_name):
    """True when the map's ground changes at set rounds (so a shorter game
    leaves more of it usable)."""
    from . import mapgeom as G
    geom = G.load(map_name)
    if not geom:
        return False
    dyn = G.dynamics(geom)
    return any(r for r in list(dyn.appear.values()) + list(dyn.vanish.values()) + list(dyn.suspend.values()))


def _mechanics_notes(map_name):
    """{"mechanics": [kinds of map mechanics], "advice": [...]} for the
    table (empty for maps without mechanics)."""
    from . import mapgeom as G
    geom = G.load(map_name)
    if not geom or "mechanics" not in geom:
        return {}
    summary = G.mechanics_summary(geom)
    kinds = sorted({f["kind"] for f in summary["features"]})
    out = {}
    if kinds:
        out["mechanics"] = kinds
    if summary["advice"]:
        out["advice"] = summary["advice"]
    return out


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


def strategy_fit(map_name, kinds, reverse=False, weights=None, last_round=None):
    """How much of the early track a plan's damage towers can cover on this
    map, 0..1, or None when not measured: each tower kind's reach, weighted
    by `weights` (the cash the plan puts into it; equal when missing). A
    weighted mean rather than the best kind: one sniper does not make a
    ninja plan fit a map where the ninjas cannot reach the bloons.
    last_round: the game's last round, for maps whose ground changes by
    round (Erosion); None plans for the longest game."""
    entry = load().get(map_name)
    if not entry or not kinds:
        return None
    side = "late" if reverse else "early"
    towers = entry["towers"]
    if last_round is not None and entry.get("by_last_round"):
        fits = sorted(int(r) for r in entry["by_last_round"] if int(r) >= last_round)
        if fits:
            towers = entry["by_last_round"][str(fits[0])]
    known = [k for k in kinds if k in towers]
    if not known:
        return None
    w = {k: max(0.0, (weights or {}).get(k, 1.0)) for k in known}
    total = sum(w.values()) or float(len(known))
    if not sum(w.values()):
        w = {k: 1.0 for k in known}
    return sum(w[k] * towers[k][side] for k in known) / total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t = refresh()
    for name in ("Luminous Cove", "Monkey Meadow", "Logs", "Lost Crevasse"):
        e = t.get(name, {}).get("towers", {})
        print(name, {k: e[k]["early"] for k in ("ninja", "sub", "super", "buccaneer", "sniper") if k in e})
