"""Rank the heroes on merit with the damage model: data/hero_merit.json.

Why
---
docs/tower_exclusions_audit.md item 1: no code ever compared heroes on
merit. The generated builds hard-coded Quincy, the optimizer took whatever
hero was equipped, and the fallback lists (strategy.HERO_FALLBACK,
planner.HERO_PRIORITY) were the four free heroes of a fresh account in a
hand order. Twelve of the eighteen heroes were never chosen.

This tool rates every hero the damage model can rate on its own attacks:
the hero stands alone at its best spot of each reference map, at the level
the bot's estimate gives it in each sample round (placed in round 1, as
the optimizer and the live forecast rate it), and the score is the mean of
log2(margin) over the sample rounds (dps_model.round_margin, clamped to its
search range). A hero that holds more rounds, by a wider margin, ranks
higher.

What it leaves out, on purpose:
  * Corvus: dps_model.UNRATED_HEROES (his spellbook is not modelled and the
    bot cannot use it), so he gets no score and comes last.
  * Geraldo's shop: the bot cannot buy or place shop items
    (towers.py ability use "never"); the model rates his own attacks only.
  * Buffs to other towers (Obyn, Striker, Gwendolin) and income (Benjamin):
    a hero alone has nothing to buff. The optimizer's hero sweep
    (optimize_builds.optimize) rates those on the real board; this ranking
    is the order for the cases with no board: fallbacks and generated builds.

Usage:
    python tools/rank_heroes.py            # rewrite data/hero_merit.json
    python tools/rank_heroes.py --check    # print the ranking, write nothing
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402

OUT = ROOT / "data" / "hero_merit.json"
# A Beginner map with one long lane and an Intermediate one with two
# crossing lanes: a hero's reach shows differently on each.
MAPS = ("Monkey Meadow", "Logs")
MODE = "medium"
# Every sixth round from 6 to 78: the early game a hero carries alone, the
# ceramic rounds and the first MOAB-class rounds.
ROUNDS = tuple(range(6, 79, 6))
PLACED_ROUND = 1


def rated(hero):
    """Can the damage model rate this hero at all?"""
    return hero not in D.UNRATED_HEROES and D.profile(D.hero_kind(hero), (1,)) is not None


def score(hero, map_name, rounds=ROUNDS):
    """Mean log2(margin) of the hero alone on one map over `rounds`, or None
    when it has no spot there (a water hero on a land map)."""
    setup = O.MapSetup(map_name, MODE)
    spot = setup.hero_spot(hero, [])
    if spot is None:
        return None
    ev = O.Evaluator(setup, MODE, hero)
    logs = []
    for rnd in rounds:
        tiers = O.hero_tiers_at(hero, map_name, MODE, None, PLACED_ROUND, rnd)
        tower = O.Tower("hero", "hero", spot, tiers, 0.0)
        margin = ev.margins([tower], [rnd])[rnd]
        logs.append(math.log2(min(max(margin, D.MARGIN_LO), D.MARGIN_HI)))
    return sum(logs) / len(logs)


def rank():
    """{hero: mean score over the maps where it has a spot} for every rated
    hero, best first."""
    out = {}
    for hero in T.HEROES:
        if not rated(hero):
            continue
        per_map = [s for s in (score(hero, m) for m in MAPS) if s is not None]
        if per_map:
            out[hero] = round(sum(per_map) / len(per_map), 3)
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="print the ranking, write nothing")
    a = ap.parse_args()
    t0 = time.time()
    scores = rank()
    for hero, s in scores.items():
        print(f"{hero:18s} {s:7.3f}")
    print(f"({time.time() - t0:.0f} s)")
    if a.check:
        return
    data = {
        "about": "Heroes ranked on merit by tools/rank_heroes.py: each hero alone at its best spot, "
                 "at the bot's estimated level, mean log2(damage-model margin) over the sample rounds. "
                 "Read by towers.hero_merit_order (fallbacks, generated builds). Corvus is not rated.",
        "made": date.today().isoformat(),
        "maps": list(MAPS), "mode": MODE, "rounds": list(ROUNDS),
        "unrated": sorted(h for h in T.HEROES if h not in scores),
        "scores": scores,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"written: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
