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
(sniper, mortar, heli, ace, dartling: range None) reach everything - if
the map has room for them to stand (room_for).
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


# Version of the measurement itself (kind_coverage); part of the stamp, so
# bumping it re-measures every map. 2: global-range towers need room to stand.
# 3: water towers also record how many of them the map's water holds ("room").
FIT_VERSION = 3

# A water tower's entry also counts the towers of its kind that fit on the
# map's water at once (room_for), up to this many: a plan placing more subs
# than that cannot be built there (planner._water_towers_have_no_spot).
WATER_ROOM_MAX = 8

# A global-range tower reaches the whole track from any cell it may stand on,
# but only if there is such a cell. Its coverage is the number of them that
# fit side by side (footprints apart), up to this many, as a share: a map
# with room for one Apache pad is not a full fit for a build of six.
GLOBAL_ROOM_FULL = 3


def stamp_of(geom):
    """What a cached measurement depends on: the game's map bundle, the
    extraction version, the version of the measurement and the version of
    the rules that interpret the map's mechanics (any of them changing
    re-measures the map)."""
    from .mapgeom import RULES_VERSION
    return f'{geom.get("bundle")}#v{geom.get("version")}#f{FIT_VERSION}#r{RULES_VERSION}'


def room_for(model, kind, ok, limit=GLOBAL_ROOM_FULL):
    """How many towers of this kind fit on the legal cells `ok` without
    their footprints overlapping (greedy, in reading order), up to `limit`."""
    from .placement import footprint_radius, units_per_cell
    apart = 2 * footprint_radius(kind, None) / units_per_cell(model)
    placed = []
    for cy, cx in zip(*np.nonzero(ok)):
        if all((cx - px) ** 2 + (cy - py) ** 2 >= apart * apart for px, py in placed):
            placed.append((cx, cy))
            if len(placed) >= limit:
                break
    return len(placed)


def kind_coverage(model, kind, last_round=None):
    """{"early": share of the early track in reach, "late": the same for the
    last EARLY_SPAN (what Reverse meets first)} for one tower kind, for a
    game ending at `last_round` (None: the longest game). A water tower's
    entry also carries "room": how many of its kind the water holds at once
    (up to WATER_ROOM_MAX). Castle Revenge's moat holds one sub: the two-sub
    chimps_sub_druid_water gave up its second sub there and lost Impoppable
    at round 33 (2026-11-05, loss case 20261105_063635)."""
    from .placement import units_per_cell, valid_spots
    rng = T.TOWERS[kind].get("range")
    ok = valid_spots(model, kind, last_round=last_round)
    if ok is None:
        return None
    cover = _coverage(model, kind, ok, rng)
    if cover is not None and T.TOWERS[kind].get("placement") == "water":
        cover["room"] = room_for(model, kind, ok, limit=WATER_ROOM_MAX)
    return cover


def _coverage(model, kind, ok, rng):
    """kind_coverage's track shares for the legal cells `ok` of a tower with
    range rng (None: global)."""
    from .placement import units_per_cell
    if rng is None:
        # global range reaches the whole map - from wherever it can stand.
        # Before, this was 1.0 without looking: High Finance has no cell big
        # enough for a heli until its buildings are bought, yet solo_heli was
        # rated 0.84 there and lost Medium with one sniper (2026-11-03).
        share = room_for(model, kind, ok) / GLOBAL_ROOM_FULL
        return {"early": round(share, 3), "late": round(share, 3)}
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
