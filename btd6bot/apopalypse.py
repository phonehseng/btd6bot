"""Apopalypse: how the game makes its random rounds, and the rounds it can send.

What the mode is
----------------
Apopalypse is Medium (150 lives, Medium prices) with the standard rounds
replaced by randomly generated ones, and no pause between rounds: as soon as a
round has spawned its last bloon the next one starts spawning, whether or not
the last one's bloons are popped, Auto Start or not. The game is won by
popping everything of rounds 1-60 (the Apopalypse Mod's EndRound is 60:
data/game_model/difficulties.json; bloons.fandom.com Apopalypse_(BTD6):
"victory ... by popping all bloons spawned from Round 1 to Round 60"). The
Survivor achievement asks for round 100, in freeplay after that win. Since
v41 each round pays the end-of-round bonus too ($100 + round), once all its
bloons are popped. With Fast Track the account's games start at round 15 like
Medium (logs: "game starts at round 15", Polyphemus 2026-10-27 and Infernal
2026-11-05).

How a round is made (the game's own code and data)
--------------------------------------------------
FreeplayRoundManager.GetRoundEmissions (GameAssembly.dll, read through
Cpp2IL's dump in ~/.btd6bot_cache/il2cpp; the constants read from the DLL's
data section) does, for round r (1-based):

  1. seed the game's SeededRandom with (game seed + r) and shuffle all 529
     freeplay groups (GameModel.freeplayGroups, exported by
     tools/decode_sim_model.py to data/game_model/freeplay_groups.json; they
     match bloonswiki's Module:BTD6 rounds/Freeplay group for group);
  2. draw m = NextFloat() in [0, 1) and set the budget
        base(r) = 5e-11 * r^7.7 + r^1.75 + 20
        r <= 50:      base(r) / 160 * (400 - 3r) * (1 + 0.01r) * 0.6
        50 < r <= 100: base(r)
        r > 100:       4000r - 225000
     times (1.5 - m) from round 2 on, so 0.5x to 1.5x of that;
  3. walk the shuffled groups: a group whose bounds hold r and whose score is
     at most the budget left is taken and the budget pays its score;
  4. the groups taken are laid end to end: each starts when the one before it
     has spawned its last bloon (no two groups of a round overlap).

A group's score (FreeplayBloonGroupModel.CalculateScore) is its stored score
when that is above 0 (only a few late groups have one), else the sum of its
bloons' total leak damage (lives they cost with their children: a ceramic 104,
a MOAB 616) times 1.1 for camo and 1.1 for regrow ("Camo" and "Grow" tags,
added: 1.2 for both), times a density factor from the seconds between its
bloons (duration / count, applied when count > 1): 0.8 from 1 s, 1.0 from
0.5 s, 1.1 from 0.1 s, 1.4 from 0.08 s, 1.8 below.

Each round is drawn on its own (its seed is the game seed plus the round), so
"the rounds the game can send at round r" is the set of outcomes of steps 1-4
for every shuffle and every m. This module does not claim seed-exact rounds
(the shuffle's exact walk was not read), only the same distribution and the
same set of possible rounds: random_round() draws one, worst_round() builds
the hardest one for a given ordering of the groups, and round_cash() is what
a round pays.

Cash per pop follows the standard rounds' multiplier by round (bloonswiki
Module:BTD6 rounds, cash_mod "Default": 1.0 to round 50, 0.5 to 60, 0.2 to
85, 0.1 to 100): a bloon pays $1 per layer popped (a ceramic $95, a MOAB
$381), at Medium with no other change.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEPLAY_FILE = ROOT / "data" / "game_model" / "freeplay_groups.json"
BLOONS_FILE = ROOT / "data" / "game_model" / "bloons.json"

# The game's win: rounds 1-60 (Apopalypse Mod EndRound).
END_ROUND = 60

# FreeplayRoundManager.GetRoundEmissions: from round 2 on the budget is
# multiplied by (1.5 - NextFloat()), NextFloat() in [0, 1).
BUDGET_MIN_FACTOR, BUDGET_MAX_FACTOR = 0.5, 1.5

# FreeplayBloonGroupModel.CalculateScore: +0.1 per tag, then the density
# factor by seconds between bloons (lower bound inclusive, factor).
TAG_BONUS = {"Camo": 0.1, "Grow": 0.1}
DENSITY_FACTORS = ((1.0, 0.8), (0.5, 1.0), (0.1, 1.1), (0.08, 1.4), (0.0, 1.8))

# Cash per pop by round (bloonswiki Module:BTD6 rounds, cash_mod "Default").
CASH_MOD = ((50, 1.0), (60, 0.5), (85, 0.2), (100, 0.1), (120, 0.08), (140, 0.05))
FREEPLAY_CASH_MOD = 0.02


@dataclass(frozen=True)
class Group:
    """One freeplay group: `count` bloons of one game id, spawned over
    `duration` seconds, allowed on the rounds of `bounds` (inclusive)."""
    name: str
    bloon: str
    count: int
    duration: float
    score: float
    bounds: tuple

    def valid(self, rnd):
        return any(lo <= rnd <= hi for lo, hi in self.bounds)


@lru_cache(maxsize=None)
def _bloons():
    return json.loads(BLOONS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def leak_damage(bloon_id):
    """Lives a bloon costs when it leaks, children included (BloonModel.
    GetTotalLeakDamage: its own leakDamage plus its children's totals)."""
    b = _bloons()[bloon_id]
    return float(b.get("leak_damage") or 0.0) + sum(n * leak_damage(c) for c, n in (b.get("children") or {}).items())


@lru_cache(maxsize=None)
def pops(bloon_id):
    """Layers popped to destroy a bloon and all its children ($ at 1.0x cash)."""
    b = _bloons()[bloon_id]
    return 1 + sum(n * pops(c) for c, n in (b.get("children") or {}).items())


def computed_score(bloon_id, count, duration):
    """FreeplayBloonGroupModel.CalculateScore for a group with no stored score."""
    tags = set(_bloons()[bloon_id].get("tags") or ())
    mult = 1.0 + sum(v for tag, v in TAG_BONUS.items() if tag in tags)
    score = leak_damage(bloon_id) * mult * count
    if count > 1:
        spacing = duration / count
        score *= next(f for lo, f in DENSITY_FACTORS if spacing >= lo)
    return score


@lru_cache(maxsize=None)
def groups():
    """Every freeplay group, in the game's order."""
    out = []
    for g in json.loads(FREEPLAY_FILE.read_text(encoding="utf-8")):
        if g["bloon"] not in _bloons():
            continue
        duration = float(g["end_s"]) - float(g["start_s"])
        stored = float(g.get("score") or 0.0)
        score = stored if stored > 0 else computed_score(g["bloon"], int(g["count"]), duration)
        out.append(Group(g["name"], g["bloon"], int(g["count"]), duration, score,
                         tuple(tuple(b) for b in g["bounds"])))
    return tuple(out)


@lru_cache(maxsize=None)
def valid_groups(rnd):
    """The groups the game may put in round rnd."""
    return tuple(g for g in groups() if g.valid(rnd))


def base_budget(rnd):
    """The round's budget before the random factor (see the module docstring)."""
    base = 5e-11 * rnd ** 7.7 + rnd ** 1.75 + 20.0
    if rnd <= 50:
        return base / 160.0 * (400 - 3 * rnd) * (1.0 + 0.01 * rnd) * 0.6
    if rnd <= 100:
        return base
    return 4000.0 * rnd - 225000.0


def max_budget(rnd):
    """The largest budget round rnd can draw (NextFloat() -> 0)."""
    return base_budget(rnd) * (BUDGET_MAX_FACTOR if rnd > 1 else 1.0)


def fill(rnd, order, budget):
    """The groups a round takes walking `order` with `budget` (step 3)."""
    out = []
    for g in order:
        if g.valid(rnd) and g.score <= budget:
            out.append(g)
            budget -= g.score
    return out


def random_round(rnd, rng=None):
    """One round as the game could draw it: [Group] in spawn order."""
    rng = rng or random
    order = list(groups())
    rng.shuffle(order)
    m = rng.random()
    budget = base_budget(rnd) * ((BUDGET_MAX_FACTOR - m) if rnd > 1 else 1.0)
    return fill(rnd, order, budget)


def worst_round(rnd, hardness):
    """The round the game sends when the shuffle happens to put the groups in
    order of `hardness` (key: lower = harder) and the budget is the largest:
    every hard group that fits is taken, hardest first, and the budget left
    is filled the same way. The game can send it (some shuffle gives that
    order, m near 0), and no round at rnd holds more of the hard groups."""
    order = sorted(valid_groups(rnd), key=hardness)
    return fill(rnd, order, max_budget(rnd))


def as_round_groups(round_groups, offset=0.0):
    """[Group] laid end to end (step 4) as data/game_data/round_sets.json
    groups ({"id", "count", "start_s", "end_s"}), the shape
    dps_model.groups_lots plays. Returns (groups, end time)."""
    out, t = [], offset
    for g in round_groups:
        out.append({"id": g.bloon, "count": g.count, "start_s": round(t, 3), "end_s": round(t + g.duration, 3)})
        t += g.duration
    return out, t


def cash_mod(rnd):
    return next((m for hi, m in CASH_MOD if rnd <= hi), FREEPLAY_CASH_MOD)


def round_cash(rnd, round_groups):
    """Cash round rnd pays at base rates: its pops plus the end-of-round bonus."""
    return sum(g.count * pops(g.bloon) for g in round_groups) * cash_mod(rnd) + 100 + rnd
