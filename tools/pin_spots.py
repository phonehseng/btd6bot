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
that mode), `fill`, `panic` and `answers`, and gives each placed tower of the
plan an `at` spot:

  * spots come from the map's geometry with the spots the live game refused
    left out (MapModel.load, as tools/optimize_builds.py --learned), legal for
    the tower given the towers placed before it (placement.valid_spots) for
    the whole game;
  * a damage tower takes the best free spot the optimizer ranks for its kind
    (most bloon route in range, line of sight counted);
  * a tower with `near` (support, or a tower that must stand in a village's
    range) takes the best of those spots within its `near_radius` of the
    towers it names (any legal cell when its kind has no ranked spots), or
    the closest one when none is that near;
  * the hero and `role: exit` towers keep the executor's own choice.

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.account import canonical_map  # noqa: E402

OUT_DIR = S.STRAT_DIR / "maps"
# The lowest declared success the map builds take (tests/test_map_hints_offline.py
# keeps them within 0.5-0.85): an untested build, below every hand-tested one.
UNTESTED_SUCCESS = 0.5
# Cells between the candidate cells tried for a tower with no ranked spots.
CELL_STRIDE = 2
# A `near` step's radius in cells when it names none (the executor's default).
NEAR_RADIUS = 9


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

    def __init__(self, map_name, mode, hero=None):
        O.USE_LEARNED = True          # leave out the spots the live game refused
        self.setup = O.MapSetup(map_name, mode)
        self.model = self.setup.model
        self.hero = hero
        self.last_round = S.MODE_RULES[mode]["end_round"]
        self.placed = []              # (cx, cy, kind, hero) as placement.valid_spots takes them
        self.cells = {}               # tower id -> (cx, cy)

    def legal(self, kind):
        """Bool grid [cy, cx] of cells where ``kind`` may stand now."""
        return PL.valid_spots(self.model, kind, None, self.placed, last_round=self.last_round)

    def candidates(self, kind, ok):
        """Cells (cx, cy) for ``kind``, best first: its free ranked spots
        (reaching the track), then every legal cell on a CELL_STRIDE grid.
        A buffer (village, alchemist: Executor.BUFFERS) lends to the towers
        around it, not to the track, so it gets the legal cells alone."""
        ranked = [] if kind in S.Executor.BUFFERS else \
            [sp.cell for sp in self.setup.ranked_spots(kind) if ok[sp.cell[1], sp.cell[0]]]
        ys, xs = ok.nonzero()
        grid = [(int(x), int(y)) for x, y in zip(xs, ys) if x % CELL_STRIDE == 0 and y % CELL_STRIDE == 0]
        return ranked + [c for c in grid if c not in set(ranked)]

    def pin(self, tid, kind, near=(), near_radius=NEAR_RADIUS):
        """The `at` [fx, fy] for tower ``tid`` (None when no legal spot).

        With ``near``: the best candidate within ``near_radius`` cells of every
        tower named (the executor's own rule), else the closest one - the
        executor too widens the radius when nothing is free inside it."""
        ok = self.legal(kind)
        if ok is None:
            return None
        cands = self.candidates(kind, ok)
        refs = [self.cells[r] for r in near if r in self.cells]
        if refs:
            inside = [c for c in cands if all(math.dist(c, r) <= near_radius for r in refs)]
            cands = inside or sorted(cands, key=lambda c: sum(math.dist(c, r) for r in refs))
        if not cands:
            return None
        cx, cy = cands[0]
        self.placed.append((cx, cy, kind, None))
        self.cells[tid] = (cx, cy)
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
    plan, unpinned = [], []
    for st in _for_mode(src.get("plan"), mode):
        if st.get("do") == "place" and st.get("kind") != "hero" and st.get("role") != "exit" and st.get("id"):
            at = pinner.pin(st["id"], st["kind"], st.get("near") or (), st.get("near_radius", NEAR_RADIUS))
            if at is None:
                unpinned.append(st["id"])
            else:
                st = dict(st, at=at)
        plan.append(st)
    planner = dict(src.get("planner") or {})
    planner.pop("excluded_maps", None)
    planner.pop("excluded_by_mode", None)
    planner["maps"] = [map_name]
    planner["base_success"] = {mode: UNTESTED_SUCCESS}
    out = {"id": f"{O.map_id(map_name)}_{mode}", "map": map_name, "hero": src.get("hero"),
           "plan_first": True, "modes": [mode], "planner": planner, "plan": plan,
           "notes": src.get("notes") or []}   # a draft's own header lines (to_yaml)
    for key in ("fill", "panic"):
        if src.get(key):
            out[key] = _for_mode(src[key], mode)
    if src.get("answers"):
        # an answer that places a planned tower early places it at its plan spot
        spots = {st["id"]: st["at"] for st in plan if st.get("do") == "place" and st.get("at")}
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
