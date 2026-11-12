"""Write a map's own copy of a general strategy with an exact spot for every tower.

Why
---
On Advanced and Expert maps the general builds lose their plan to the spots:
the executor picks a spot by role and track segment, the game refuses some of
them, the step is given up, and the money goes to off-plan reinforce buys.
The last-round boards of the Impoppable games of 2026-11-11 (logs/journal)
held far more cash in such buys than in the plan's own towers - Peninsula R95
$11.6k of plan towers against $287k off-plan, Sunken Columns R98 $69k against
$227k - and the plan's late answers (MOAB Eliminator, Perma-Spike) were still
waiting when the game was lost. The CHIMPS builds that won every Beginner map
(strategies/maps/*_chimps.yaml) fix both: an exact legal spot per tower (`at`)
and `plan_first: true`, so the plan owns the cash until it is done.

What it does
------------
For one strategy, map and mode it copies the strategy's plan (the steps for
that mode), `fill`, `panic` and `answers`, and gives each named tower the
plan or the fill places an `at` spot:

  * spots come from the map's geometry with the spots the live game refused
    left out, legal for the tower given the towers placed before it
    (placement.valid_spots) for the whole game. The refusals are read from
    the LIVE map file, data/maps/<map>.npz in the main checkout: a
    worktree's copy is the one git last saw and may hold none of them
    (Sunken Columns 2026-11-12: the worktree's file had no refusals, the
    live one 261 water cells refused for a sub, among them the pinned sb1
    spot; the game turned it and six spots around it down, and the
    one-life game was lost at round 6). A pinned cell is checked once more
    against every refusal layer of its kind (never_refused), and it is off
    the cycling panes while there is room off them (pane_free);
  * a damage tower takes the best free spot the optimizer ranks for its kind
    (most bloon route in range, line of sight counted), and among the spots
    nearly as good (PROVEN_SCORE_SHARE of the best) one where a tower of
    that kind has already stood in a live game (MapModel.spot_stats, or
    accepted_mask) comes first;
  * a tower with `near` (support, or a tower that must stand in a village's
    range) takes the best of those spots within its `near_radius` of the
    towers it names (any legal cell when its kind has no ranked spots), or
    the closest one when none is that near;
  * a step may say where the guide puts the tower, in words turned into a
    box of screen fractions: `area: [x0, y0, x1, y1]` (a draft-only key,
    left out of the written file). Candidates inside the box come first,
    in their usual order (a global tower or a buffer, which rank no spots,
    take the one nearest the box's centre); with none inside, the one
    nearest the box. The Intermediate CHIMPS guide builds (2026-11-12) use
    it for "Sauda at the top middle, as high as possible", "the sniper next
    to the crystal", "the boat in the springs";
  * the hero keeps the executor's own choice unless its step has an
    `area`: then it is pinned like a tower, on the cells the hero itself
    may stand on, ranked by the route a dart-range tower sees from them
    (HERO_PROXY: heroes have no damage profile);
  * `role: exit` towers keep the executor's own choice;
  * a `do: clear` step frees the obstacle's ground for the towers pinned
    after it (such a plan is pinned in plan order).

The written file (strategies/maps/<map id>_<mode>.yaml) is marked untested
and gets the lowest base_success the map builds use (UNTESTED_SUCCESS); the
planner prefers a map's own build to a general one there, and its record
raises or lowers it from its first game.

Usage:
    python tools/pin_spots.py chimps_ninja_sun Quad impoppable
    python tools/pin_spots.py chimps_sub_druid_water "Sunken Columns" impoppable --dry-run
    python tools/pin_spots.py draft.yaml "Midnight Mansion" impoppable   # a hand-written plan
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import maplearn as ML  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.account import canonical_map  # noqa: E402

OUT_DIR = S.STRAT_DIR / "maps"
# Step keys a draft may carry that the written file leaves out (see `area`).
DRAFT_KEYS = ("area", "note")
# The lowest declared success the map builds take (tests/test_map_hints_offline.py
# keeps them within 0.5-0.85): an untested build, below every hand-tested one.
UNTESTED_SUCCESS = 0.5
# Cells between the candidate cells tried for a tower with no ranked spots.
CELL_STRIDE = 2
# A `near` step's radius in cells when it names none (the executor's default).
NEAR_RADIUS = 9
# A ranked spot where the kind already stood in a live game goes first when
# its score is at least this share of the best free ranked spot's.
PROVEN_SCORE_SHARE = 0.8


def live_maps_dir() -> Path:
    """data/maps of the main checkout, where the live bot keeps what it
    learned (refused and accepted spots, spot_stats). In a worktree the
    tracked copy is stale; outside one this is the tree's own data/maps."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        live = Path(common).parent / "data" / "maps"
        return live if live.is_dir() else ML.DATA
    except (OSError, subprocess.CalledProcessError):
        return ML.DATA


# A kind with less legal ground than this share of the build's roomiest
# kind's is pinned before the rest (Pinner.scarce).
SCARCE_SHARE = 0.25
# A buffer's room is counted for towers of this footprint (the smallest).
ROOM_KIND = "ninja"
# A buffer's room is weighed for about this many of its candidates, spread
# evenly over them (each count is a valid_spots call).
BUFFER_TRIES = 40


def buffer_range(kind):
    """The range (world units) within which a village or an alchemist
    lends to other towers, at its base tier (the smallest it has); None
    for other kinds."""
    from btd6bot import dps_model as D
    if kind not in S.Executor.BUFFERS:
        return None
    prof = D.profile(kind, (0, 0, 0))
    return prof.range if prof is not None and prof.range else None


def refusal_layers(kind, hero=None):
    """The MapModel.refused layers a spot for ``kind`` must be clear of:
    each surface it may stand on and that surface's own layer for the kind
    (placement.refusal_layer)."""
    out = set()
    for surface in PL.surfaces(kind, hero):
        out |= {surface, PL.refusal_layer(surface, kind, hero)}
    return out


# Heroes have no damage profile: a hero's cells are ranked by the route a
# tower of this kind would see from them (Pinner.candidates).
HERO_PROXY = "dart"


def never_refused(model, kind, cell, hero=None):
    """True when no refusal layer of ``kind`` covers ``cell`` (cx, cy)."""
    cx, cy = cell
    return not any(model.refused_mask(layer)[cy, cx] for layer in refusal_layers(kind, hero))


def pane_free(model, ok):
    """``ok`` without the ground under Covered Garden's cycling panes
    (mapgeom.pane_ground) while it has a cell off them; ``ok`` itself
    elsewhere. A tower under a pane can be clicked one round in four: on
    2026-11-12 (loss 20261112_014133) the Eliminator's and the Perma-Spike's
    upgrades, the round 63-95 answers, waited on shut glass."""
    from btd6bot import mapgeom
    if ok is None:
        return None
    pane = mapgeom.pane_ground(model)
    if pane is None:
        return ok
    free = ok & ~pane
    return free if free.any() else ok


def proven_cells(model, kind):
    """Cells where a tower of ``kind`` has stood in a live game: the
    SPOT_BUCKET squares of its MapModel.spot_stats entries, plus the cells
    the game accepted on its surfaces although the map file marks them
    blocked (accepted_mask)."""
    import numpy as np
    grid = np.zeros(model.heat.shape, bool)
    b = ML.SPOT_BUCKET
    for key in model.spot_stats:
        k, bx, by = key.split("|")
        if k == kind:
            grid[int(by) * b:(int(by) + 1) * b, int(bx) * b:(int(bx) + 1) * b] = True
    for surface in PL.surfaces(kind):
        grid |= model.accepted_mask(surface)
    return grid


def _for_mode(steps, mode):
    """The steps that apply in ``mode`` (no `modes` key, or ``mode`` in it),
    without the `modes` key: the written file serves that one mode."""
    out = []
    for st in steps or []:
        if st.get("modes") and mode not in st["modes"]:
            continue
        out.append({k: v for k, v in st.items() if k != "modes"})
    return out


class Pinner:
    """Exact spots for one map and mode, in plan order."""

    def __init__(self, map_name, mode, hero=None, maps_dir=None):
        O.USE_LEARNED = True          # leave out the spots the live game refused ...
        ML.DATA = Path(maps_dir) if maps_dir else live_maps_dir()   # ... as the live file holds them
        self.setup = O.MapSetup(map_name, mode)
        self.model = self.setup.model
        self.hero = hero
        self.last_round = S.MODE_RULES[mode]["end_round"]
        self.placed = []              # (cx, cy, kind, hero) as placement.valid_spots takes them
        self.cells = {}               # tower id -> (cx, cy)
        self.kinds = {}               # tower id -> kind
        self.removed = ()             # obstacles a `clear` step bought (placement.valid_spots)

    def legal(self, kind, hero=None):
        """Bool grid [cy, cx] of cells where ``kind`` (``hero`` for the
        hero) may stand now, off the cycling panes (pane_free) while any
        such cell is left."""
        ok = PL.valid_spots(self.model, kind, hero, self.placed, last_round=self.last_round,
                            removed=self.removed)
        return pane_free(self.model, ok)

    def clear(self, obstacle):
        """A `do: clear` step: the obstacle's ground counts as free from here."""
        self.removed = tuple(self.removed) + (obstacle,)

    def legal_cells(self, kind):
        """Legal cells for ``kind`` on the empty map, off the panes."""
        ok = pane_free(self.model, PL.valid_spots(self.model, kind, None, [], last_round=self.last_round))
        return 0 if ok is None else int(ok.sum())

    def scarce(self, kind, kinds):
        """True when ``kind`` has far less legal ground than the roomiest of
        the build's ``kinds`` (under SCARCE_SHARE of it): Covered Garden's
        pane-free strips hold 58 cells for an ace and 600 for a ninja."""
        most = max(self.legal_cells(k) for k in kinds)
        return self.legal_cells(kind) < most * SCARCE_SHARE

    def segment_cover(self, kind, cell, segment):
        """Route length (world units, all routes) inside ``kind``'s range
        from ``cell`` and within ``segment`` - the share of each route from
        its entrance, (0.0, 0.5) its first half - that it can see."""
        import numpy as np
        from btd6bot import dps_model as D
        prof = D.profile(kind, (0, 0, 0))
        if prof is None or prof.is_global:
            return 0.0
        x, z = self.world(cell)
        lo, hi = segment
        sight = self.setup.sight_for(kind)
        total = 0.0
        for path in self.setup.track.paths:
            xyz, dist, length = path["xyz"], path["dist"], path["length"]
            progress = dist / length if length else dist * 0
            if self.setup.track.reverse:
                progress = 1.0 - progress
            inside = path["hittable"] & (progress >= lo) & (progress <= hi) &                 (((xyz[:, 0] - x) ** 2 + (xyz[:, 1] - z) ** 2) <= prof.range ** 2)
            if sight is not None and inside.any():
                idx = np.nonzero(inside)[0]
                inside[idx[~sight(x, z, xyz[inside])]] = False
            total += float(np.sum(np.diff(dist)[inside[:-1]]))
        return total

    def candidates(self, kind, ok, segment=None, hero=None):
        """Cells (cx, cy) for ``kind``, best first, none of them refused for
        it (never_refused): its free ranked spots (reaching the track), the
        spots nearly as good as the best (PROVEN_SCORE_SHARE) where the kind
        already stood in a live game first, then every legal cell on a
        CELL_STRIDE grid, proven cells first. With ``segment`` the ranked
        spots are scored by the route they cover inside it. A buffer (village, alchemist:
        Executor.BUFFERS) lends to the towers around it, not to the track,
        so it gets the legal cells alone (pin ranks them by room)."""
        if kind == "hero":
            # no damage profile: the hero's cells ranked by the route a
            # tower of HERO_PROXY's range sees from them
            ys, xs = ok.nonzero()
            cells = [(int(x), int(y)) for x, y in zip(xs, ys) if x % CELL_STRIDE == 0 and y % CELL_STRIDE == 0]
            scored = [(c, self.segment_cover(HERO_PROXY, c, segment or (0.0, 1.0))) for c in cells]
            scored.sort(key=lambda t: -t[1])
            return [c for c, _ in scored if never_refused(self.model, kind, c, hero)]
        proven = proven_cells(self.model, kind)
        spots = [] if kind in S.Executor.BUFFERS else             [(sp.cell, sp.score) for sp in self.setup.ranked_spots(kind) if ok[sp.cell[1], sp.cell[0]]]
        if spots and segment and tuple(segment) != (0.0, 1.0):
            # the step covers its part of the route (`segment`), as the
            # executor weighs it: Mesa (2026-11-12) lost round 9 with its
            # first ninja pinned by whole-route cover at the far end
            on_part = [(c, self.segment_cover(kind, c, segment)) for c, _ in spots]
            on_part = sorted((t for t in on_part if t[1] > 0), key=lambda t: -t[1])
            # none reaches that part (Midnight Mansion's first half): any part
            # of the route, as the executor relaxes the segment too
            spots = on_part or spots
        if spots:
            bar = spots[0][1] * PROVEN_SCORE_SHARE
            spots.sort(key=lambda t: not (t[1] >= bar and proven[t[0][1], t[0][0]]))
        ranked = [c for c, _ in spots]
        ys, xs = ok.nonzero()
        grid = [(int(x), int(y)) for x, y in zip(xs, ys) if x % CELL_STRIDE == 0 and y % CELL_STRIDE == 0]
        grid.sort(key=lambda c: not proven[c[1], c[0]])     # stable: proven cells first
        seen = set(ranked)
        cands = ranked + [c for c in grid if c not in seen]
        return [c for c in cands if never_refused(self.model, kind, c)]

    def world(self, cell):
        """(x, z) world position of a tower standing on ``cell``."""
        sp = self.setup.cell_spot(cell)
        return sp.x, sp.z

    def reach(self, kind, cell, other_kind, other_cell, near_radius):
        """True when two towers stand close enough to work together: inside
        the buffer's range (buffer_range) when one of them is a village or
        an alchemist, else within ``near_radius`` cells (the executor's own
        `near` rule)."""
        rng = buffer_range(kind) or buffer_range(other_kind)
        if rng:
            return math.dist(self.world(cell), self.world(other_cell)) <= rng
        return math.dist(cell, other_cell) <= near_radius

    def room(self, kind, cell):
        """Legal cells for a small tower (ROOM_KIND) inside the range of a
        buffer of ``kind`` standing on ``cell``: how many towers it can lend
        to. Counted on the CELL_STRIDE grid, with the buffer itself placed."""
        rng = buffer_range(kind)
        free = PL.valid_spots(self.model, ROOM_KIND, None, self.placed + [(cell[0], cell[1], kind, None)],
                              last_round=self.last_round)
        free = pane_free(self.model, free)
        if free is None or not rng:
            return 0
        here = self.world(cell)
        ys, xs = free.nonzero()
        return sum(1 for x, y in zip(xs, ys) if x % CELL_STRIDE == 0 and y % CELL_STRIDE == 0
                   and math.dist(self.world((int(x), int(y))), here) <= rng)

    def _inside(self, cell, area):
        """Is ``cell`` inside ``area`` (x0, y0, x1, y1 screen fractions)?"""
        fx, fy = self.model.cell_to_frac(*cell)
        return area[0] <= fx <= area[2] and area[1] <= fy <= area[3]

    def in_area(self, cands, area, kind):
        """``cands`` with those inside ``area`` (x0, y0, x1, y1 screen
        fractions) first. Inside the box the usual order stands, except for
        a kind that ranks no spots (a global tower, a buffer: their order is
        the grid's), which goes nearest the box's centre first; with none
        inside, the candidate nearest the box comes first."""
        if not area or not cands:
            return cands
        x0, y0, x1, y1 = area
        mid = ((x0 + x1) / 2, (y0 + y1) / 2)
        frac = {c: self.model.cell_to_frac(*c) for c in cands}
        inside = [c for c in cands if x0 <= frac[c][0] <= x1 and y0 <= frac[c][1] <= y1]
        if inside:
            unranked = kind in S.Executor.BUFFERS
            if kind != "hero" and not unranked:
                from btd6bot import dps_model as D
                prof = D.profile(kind, (0, 0, 0))
                unranked = prof is not None and prof.is_global
            if unranked:
                inside.sort(key=lambda c: math.dist(frac[c], mid))
            taken = set(inside)
            return inside + [c for c in cands if c not in taken]

        def gap(c):
            fx, fy = frac[c]
            return math.hypot(max(x0 - fx, 0, fx - x1), max(y0 - fy, 0, fy - y1))
        return sorted(cands, key=gap)

    def pin(self, tid, kind, near=(), near_radius=NEAR_RADIUS, segment=None, area=None, hero=None):
        """The `at` [fx, fy] for tower ``tid`` (None when no legal spot).

        With ``near``: the best candidate that works with every tower named
        (reach), else the closest one - the executor too widens its radius
        when nothing is free inside it. A buffer takes, among those, the
        cell with the most room for the towers it is to lend to (room):
        on Sunset Gulch (2026-11-12) the first legal cell left its Eliminator
        78 units from the camo village (range 48)."""
        ok = self.legal(kind, hero)
        if ok is None:
            return None
        cands = self.in_area(self.candidates(kind, ok, segment, hero), area, kind)
        refs = [(self.kinds[r], self.cells[r]) for r in near if r in self.cells]
        if refs:
            inside = [c for c in cands if all(self.reach(kind, c, k, r, near_radius) for k, r in refs)]
            cands = inside or sorted(cands, key=lambda c: sum(math.dist(c, r) for _, r in refs))[:1]
        if kind in S.Executor.BUFFERS and len(cands) > 1:
            if area:
                # the room decides only among the cells where the guide puts it
                cands = [c for c in cands if self._inside(c, area)] or cands
            step = max(1, len(cands) // BUFFER_TRIES)      # spread over all of them
            cands = sorted(cands[::step], key=lambda c: -self.room(kind, c))
        if not cands:
            return None
        cx, cy = cands[0]
        self.placed.append((cx, cy, kind, hero))
        self.cells[tid] = (cx, cy)
        self.kinds[tid] = kind
        fx, fy = self.model.cell_to_frac(cx, cy)
        return [round(float(fx), 3), round(float(fy), 3)]


def load_source(sid):
    """The strategy to copy: an id from strategy.load_all, or a YAML file
    (a hand-written draft kept outside strategies/)."""
    import yaml
    path = Path(sid)
    if path.suffix in (".yaml", ".yml") and path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return S.load_all()[sid]


def pinned_strategy(sid, map_name, mode):
    """The map's own copy of strategy ``sid`` for ``mode`` (a dict), and the
    ids of the plan towers left without a spot."""
    src = load_source(sid)
    map_name = canonical_map(map_name)
    pinner = Pinner(map_name, mode, src.get("hero"))
    unpinned = []

    def pins_wanted(st):
        """A step placing a named tower other than an exit tower or the
        hero (those keep the executor's choice); a hero step with an `area`
        is pinned too."""
        return (st.get("do") == "place" and st.get("role") != "exit" and bool(st.get("id"))
                and (st.get("kind") != "hero" or bool(st.get("area"))))

    plan_steps = _for_mode(src.get("plan"), mode)
    # a fill tower with an id is pinned too, or the executor's choice for it
    # may take ground pinned plan towers need
    fill_steps = _for_mode(src.get("fill"), mode) if src.get("fill") else []
    wanted = [st for st in plan_steps + fill_steps if pins_wanted(st)]
    # Scarce kinds first (pinner.scarce): Covered Garden's pane-free ground
    # holds one ace, and pinned in plan order the towers before it had taken
    # that room. The rest in plan order, each clear of those pinned before.
    if any(st.get("do") == "clear" for st in plan_steps):
        # the ground a clear frees is there for the towers after it only
        order = [st for st in plan_steps + fill_steps if pins_wanted(st) or st.get("do") == "clear"]
    else:
        kinds = {st["kind"] for st in wanted if st["kind"] != "hero"}
        order = [st for st in wanted if not st.get("near") and st["kind"] != "hero"
                 and pinner.scarce(st["kind"], kinds)]
        order += [st for st in wanted if st not in order]
    spots = {}
    for st in order:
        if st.get("do") == "clear":
            pinner.clear(st.get("obstacle"))
            continue
        at = pinner.pin(st["id"], st["kind"], st.get("near") or (), st.get("near_radius", NEAR_RADIUS),
                        segment=st.get("segment") if st.get("role", "dps") == "dps" else None,
                        area=st.get("area"), hero=src.get("hero") if st["kind"] == "hero" else None)
        if at is None:
            unpinned.append(st["id"])
        else:
            spots[st["id"]] = at

    def written(st):
        """The step as the file holds it: its pinned spot, no draft keys."""
        out = {k: v for k, v in st.items() if k not in DRAFT_KEYS}
        return dict(out, at=spots[st["id"]]) if pins_wanted(st) and st["id"] in spots else out
    plan = [written(st) for st in plan_steps]
    fill = [written(st) for st in fill_steps] or None
    planner = dict(src.get("planner") or {})
    planner.pop("excluded_maps", None)
    planner.pop("excluded_by_mode", None)
    planner["maps"] = [map_name]
    planner["base_success"] = {mode: UNTESTED_SUCCESS}
    out = {"id": f"{O.map_id(map_name)}_{mode}", "map": map_name, "hero": src.get("hero"),
           "plan_first": True, "modes": [mode], "planner": planner, "plan": plan,
           "notes": src.get("notes") or []}   # a draft's own header lines (to_yaml)
    if fill:
        out["fill"] = fill
    if src.get("panic"):
        out["panic"] = _for_mode(src["panic"], mode)
    if src.get("answers"):
        # an answer that places a planned tower early places it at its plan spot
        spots = {st["id"]: st["at"] for st in plan + (fill or []) if st.get("do") == "place" and st.get("at")}
        out["answers"] = {threat: [dict(st, at=spots[st["id"]]) if st.get("do") == "place" and st.get("id") in spots
                                   else st for st in _for_mode(steps, mode)]
                          for threat, steps in src["answers"].items()}
    return out, unpinned


def _flow(v):
    """A YAML flow value for a step field."""
    if isinstance(v, str):
        return json.dumps(v) if any(ch in v for ch in ":#,[]{}") or v != v.strip() else v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_flow(x)}" for k, x in v.items()) + "}"
    return json.dumps(v)


def to_yaml(d, sid, unpinned):
    """The strategy as YAML text with a header saying what it is and is not."""
    lines = [
        f"# {d['map']}, {d['modes'][0]}: {Path(sid).stem} with an exact spot per tower and plan_first.",
        "#",
        "# UNTESTED: written by tools/pin_spots.py, never played as it stands. The plan",
        f"# is {Path(sid).stem}'s; each tower's `at` is the best legal spot for its kind on this map",
        "# (the geometry minus the spots the live game refused), and a tower with `near`",
        "# stands at the legal spot closest to the towers it names. plan_first: the",
        "# plan's late answers are bought before any off-plan reinforce buy (on",
        "# 2026-11-11 such buys outweighed the plan's own towers on these maps and its",
        "# MOAB Eliminator / Perma-Spike were still waiting when the game was lost).",
        f"# base_success is the map builds' lowest ({UNTESTED_SUCCESS}); the record sets it from here.",
    ]
    if d.get("notes"):
        lines.append("#")
        lines += [f"# {ln}" for ln in d["notes"]]
    if unpinned:
        lines.append(f"# No legal spot was found for: {', '.join(unpinned)} (left to the executor).")
    lines += [f"id: {d['id']}", f"map: {_flow(d['map'])}", f"hero: {d['hero']}",
              "plan_first: true      # the plan owns the cash: no off-plan reinforce/surplus buys",
              f"modes: [{', '.join(d['modes'])}]", "planner:"]
    for k, v in d["planner"].items():
        lines.append(f"  {k}: {_flow(v)}")
    for key in ("plan", "fill", "panic"):
        if key in d:
            lines.append(f"{key}:")
            lines += [f"  - {_flow(st)}" for st in d[key]]
    if "answers" in d:
        lines.append("answers:")
        for threat, steps in d["answers"].items():
            lines.append(f"  {threat}:")
            lines += [f"    - {_flow(st)}" for st in steps]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("strategy", help="id of the strategy to copy (e.g. chimps_ninja_sun), or a draft YAML file")
    ap.add_argument("map", help='map name, e.g. "Sunken Columns"')
    ap.add_argument("mode", help="bot mode key, e.g. impoppable")
    ap.add_argument("--dry-run", action="store_true", help="print the file instead of writing it")
    a = ap.parse_args()
    d, unpinned = pinned_strategy(a.strategy, a.map, a.mode)
    text = to_yaml(d, a.strategy, unpinned)
    if a.dry_run:
        print(text)
        return
    path = OUT_DIR / f"{d['id']}.yaml"
    path.write_text(text, encoding="utf-8")
    print(f"{path.relative_to(ROOT)}: {sum(1 for st in d['plan'] if st.get('at'))} spots pinned"
          + (f", none for {unpinned}" if unpinned else ""))


if __name__ == "__main__":
    main()
