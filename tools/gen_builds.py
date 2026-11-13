"""Generate one solo XP build per tower: strategies/generated/solo_<kind>.yaml.

Why
---
Tower XP is split at every round end between tower TYPES in proportion to the
cash invested in them (docs/tower_xp.md). A paragon needs all 15 upgrades of
its tower plus 500k-1M more XP, so the planner must be able to play a game
that puts most of its money into ANY tower. This tool writes one such build
per tower (towers.TOWERS; heroes are not towers), derived from the game's own
data rather than from hand-written lists:

  * btd6bot/gamemodel.py (data/game_model): prices, upgrade names, placement
    surfaces, and what every crosspath can pop and see;
  * btd6bot/threats.py + data/counters.json: which single attack pops which
    bloon signature, rough blimp damage per crosspath, towers that must be
    aimed, what support towers lend to towers in range;
  * strategy.ANSWERS: the tiers the executor (and coverage()) accept as an
    answer to ceramic, MOAB, BFB, ZOMG, DDT, BAD and rush rounds;
  * data/rounds.json and the game's round sets: when each threat comes and
    what each round pays;
  * data/map_fit.json: where a water tower reaches the track.

How a build is made
-------------------
1. Carry or support. A tower "carries" a game when it pops bloons itself, has
   a blimp damage figure, is neither a support/income tower nor a buffer, and
   does not have to be aimed. A carry gets a solo build. Every other tower
   gets a compact defence made of the best carry that may stand beside it in
   the same modes, and the rest of the money goes into the tower itself.
2. Main path. Every path is judged at tier 4 (and tier 5) by what ONE tower
   can do there: the share of the round calendar's bloon signatures it pops
   by itself, the ANSWERS threats it answers, its blimp damage per dollar and
   what it lends to towers in range. Copies work at the highest tier of the
   best path that a Medium game pays for four times over; one copy later goes
   to tier 4 and tier 5 (the game allows one tier 5 per upgrade).
3. Complement. One or two copies on another path, the one that adds most of
   what the main path misses (lead, camo, a threat, blimp damage). Its tier 5
   is the build's second tier 5.
4. Support, only where needed: a radar village (0-2-0) when no copy sees camo,
   one exit spike factory as leak insurance. `answers:` name the tower's own
   way first and then a helper of another kind, so that an account whose own
   tiers are still locked (the reason to grind its XP) can play the build
   (see _answers).
5. Every build is played through tools/simulate_threats.py in each candidate
   mode (real prices, the game's round income, no Double Cash). A mode that
   leaves a bloon nobody can pop, or too little blimp damage, is dropped; Hard
   (and Apopalypse) also needs the damage to come from the build itself.
   base_success comes from the same results and stays below the hand-tested
   strategies of the same difficulty: the planner calibrates it from games.
6. Hero. Every land hero the damage model rates is tried with the build on
   a reference map, and the build names the one it rates best with
   (pick_hero).

Usage:
    python tools/gen_builds.py              # rewrite every build + docs/builds.md, print a report
    python tools/gen_builds.py ninja sub    # only these towers
    python tools/gen_builds.py --check      # report only, write nothing
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import gamemodel as GM  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.game import Game  # noqa: E402


def _load_tool(name):
    """Another script of tools/ as a module (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location(f"_gen_{name}", ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod     # dataclasses look their module up there (optimize_builds)
    spec.loader.exec_module(mod)
    return mod


SIM = _load_tool("simulate_threats")
OPT = _load_tool("optimize_builds")

OUT_DIR = S.STRAT_DIR / "generated"
DOC = ROOT / "docs" / "builds.md"
DOC_START, DOC_END = "<!-- builds:start -->", "<!-- builds:end -->"
STD = "standard"
# The hero a build names when pick_hero cannot choose (no damage model
# data): owned by every account and placed on land. It used to be every
# build's hero (docs/tower_exclusions_audit.md item 1).
HERO = "quincy"

# ---------------------------------------------------------------------------
# Money: what the game pays (data/rounds.json, base rates, no Double Cash)
# ---------------------------------------------------------------------------
START_CASH = SIM.DEFAULT_START_CASH


def income(last_round, first_round=1):
    """Starting cash plus what rounds first..last pay at base rates."""
    return START_CASH + sum(TH.round_cash(STD, r) for r in range(first_round, last_round + 1))


# A build's plan is sized so that a Medium game can finish it ...
PLAN_BUDGET = income(S.MODE_RULES["medium"]["end_round"])
# ... with at least four copies at their working crosspath ...
COPY_BUDGET = PLAN_BUDGET / 4
# ... and a tier 5 belongs in the plan when half a Hard game pays for it
# (dearer ones stay in `fill`: XP sinks for games that get that far).
TIER5_BUDGET = income(S.MODE_RULES["hard"]["end_round"]) / 2
MAX_COPIES = 6        # copies of the main crosspath in the plan
FILL_EXTRA = 4        # more copies `fill` may place on top of the plan's

# ---------------------------------------------------------------------------
# Threats
# ---------------------------------------------------------------------------
# camo / lead / purple are answered by signature (threats.py) - every round
# that brings them; the rest of strategy.ANSWERS are "strength" threats that
# coverage() checks against its tier tables.
PROPERTY = ("camo", "lead", "purple")
STRENGTH = tuple(t for t in S.ANSWERS if t not in PROPERTY)
FIRST_ROUND = {t: r for r, t in S.THREATS}
# MOAB-class threats (data/bloons.json): the executor's blimp ramp check runs
# their answers too, not only when the threat has no answer (see _answers).
BLIMP_CLASSES = frozenset(t for t in STRENGTH if TH.bloons().get(t, {}).get("class") == "blimp")

# Track segments (share of the way from entrance to exit) the copies spread
# over, in placement order: the first ones hold the early track.
SEGMENTS = ([0.0, 0.5], [0.3, 0.8], [0.5, 1.0], [0.0, 0.7], [0.2, 0.9], [0.4, 1.0],
            [0.1, 0.6], [0.3, 1.0])

# Score weights for one crosspath (Profile.score). Popping every kind of
# bloon by itself matters most; then the ANSWERS threats it answers; then
# blimp damage per $1000; then what it lends to towers in range.
W_COVERAGE = 4.0
W_STRENGTH = 1.0
W_BLIMP = 0.5
W_AURA = 1.5

# Towers whose default targeting follows the mouse cursor, and the upgrade
# (path, tier) that gives them a target mode of their own. The game model has
# no targeting data; docs/placement.md: "never leave Follow Touch: the bot
# moves the mouse constantly" - Pursuit (2-x-x) is bought first.
CURSOR_FIX = {"heli": (1, 2)}

# ---------------------------------------------------------------------------
# Mode choice
# ---------------------------------------------------------------------------
# Blimp damage the simulation must show: blimp damage in reach / blimp HP of
# the round (threats.blimp_capacity). It is a rough, pessimistic estimate -
# the hand-tested Medium strategies sit at 0.5-0.7 - so Easy and Medium only
# ask for the executor's own panic bar, Hard for its "enough" bar.
MIN_RATIO = {"easy": S.Executor.RAMP_PANIC, "medium": S.Executor.RAMP_PANIC,
             "hard": S.Executor.RAMP_OK}
# Win-chance priors of a generated build, per difficulty: below every
# hand-tested strategy of the same difficulty (Easy 0.94-0.98, Medium
# 0.90-0.95, Hard 0.85-0.88), because no generated build has been played yet.
#
# Hard used to start at 0.80, under the planner's paragon bar
# (planner.Config.paragon_min_p, 0.85): no generated Hard build could ever
# be a paragon game (docs/tower_exclusions_audit.md item 9). It now starts
# at that bar, which is still the bottom of the hand-tested Hard range, and
# only a build that passed Hard cleanly gets there (base_success takes off
# helpers, a support build and blimp damage short of the executor's bar).
# The planner trusts no untested Hard prior above 0.85 anyway
# (runner.planner_specs) and calibrates it from games. The Impoppable
# family (one life, to round 100) starts one hand-tested step lower: the
# gap between the Medium and Hard ranges above.
HAND_STEP = 0.05
BASE_CEILING = {"easy": 0.92, "medium": 0.86, "hard": P.DEFAULT_CONFIG.paragon_min_p}
BASE_CEILING["impoppable"] = round(BASE_CEILING["hard"] - HAND_STEP, 2)
# A mode in which the tower being levelled ends with less than a fifth of the
# cash spent is no XP game for it (the planner reads the share from the plan,
# which would overstate it), so the mode is dropped. A fifth of a Medium game
# is still ~11,000 XP: enough for a tier 3 or 4 of a tower still unlocking.
MIN_SHARE = 0.2
HELPER_PENALTY = 0.03   # per other tower kind the simulation had to buy as an answer
# A support build's defence is deliberately small (the money goes into the
# tower being levelled), so it starts a little lower still.
SUPPORT_PENALTY = 0.03
BASE_FLOOR = 0.6


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def cross(t):
    return "-".join(str(int(x)) for x in t)


def name(kind):
    return T.TOWERS[kind]["name"]


def upgrade_name(kind, path, tier):
    u = GM.upgrade(kind, path, tier)
    return (u or {}).get("name") or T.upgrade(kind, path, tier)["name"]


def top_upgrade(kind, tiers):
    """Name of the highest upgrade of a crosspath ('Sharp Shooter')."""
    path = max(range(3), key=lambda i: (tiers[i], -i))
    return upgrade_name(kind, path + 1, tiers[path]) if tiers[path] else name(kind)


def category(kind):
    return T.TOWERS[kind]["category"]


def placement(kind):
    return T.TOWERS[kind].get("placement") or "land"


def needs_aim(kind):
    return bool(TH.tower_facts(kind).get("needs_aim"))


def mode_family(mode):
    return S.MODE_FAMILY.get(mode, "hard")


def path_tiers(path, tier, second=None, second_tier=2):
    """(p1, p2, p3) with `tier` on path and `second_tier` on the second path."""
    t = [0, 0, 0]
    t[path - 1] = tier
    if second:
        t[second - 1] = second_tier
    return tuple(t)


# ---------------------------------------------------------------------------
# What one crosspath can do
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def calendar_pairs():
    """(round, signature) pairs of the standard rounds 1-100: every round a
    signature comes counts once, so the frequent ones weigh most."""
    return tuple((r, n) for n, rounds in TH.calendar(STD, 1, 100).items() for r in rounds)


def answer_table(threat):
    """The (tower, path, tier) answers to a strength threat the generator
    builds with: the hand-listed ones (strategy.HAND_ANSWERS), and the
    damage model's (strategy._answers_from_damage_model) only for towers the
    hand table lists no answer of theirs for that threat.

    With every model answer, Tack's complement went from Overdrive 0-2-4 to
    Blade Maelstrom 0-4-2 (the model lists 0-4-x as a MOAB answer), and the
    build lost all its modes: the threat simulation's blimp damage table
    (counters.json blimp_dps, hand figures for the Tack) has nothing for
    that path. Towers with no answer of their own, the gift-box towers
    among them, still get the model's (docs/tower_exclusions_audit.md
    item 3)."""
    hand = S.HAND_ANSWERS.get(threat)
    full = S.ANSWERS.get(threat, ())
    if hand is None or threat in ("camo", "lead"):
        return list(full)
    listed = {k for k, _, _ in hand}
    return [a for a in full if a in hand or a[0] not in listed]


def answers_threat(kind, tiers, threat, towers):
    """Does a tower of this kind at these tiers answer a strength threat the
    way coverage() and the executor count it (strategy.ANSWERS)? A DDT answer
    must also hurt DDTs itself (camo + lead + black at once)."""
    for k, path, tier in answer_table(threat):
        if k == kind and (path == 0 or tiers[path - 1] >= tier):
            if threat == "ddt":
                me = {t[0] for t in towers if t[1] == kind and tuple(t[2]) == tuple(tiers)}
                return TH.covers(towers, TH.sig_from_name("ddt"), poppers=me)[0]
            return True
    return False


@dataclass(frozen=True)
class Profile:
    """What one tower at one crosspath can do on its own."""
    kind: str
    tiers: tuple
    cost: int                 # Medium price, tower + upgrades
    sees_camo: bool           # targets camo itself (threats.camo_access)
    pops: frozenset           # signature names a lone tower pops
    coverage: float           # share of the calendar's (round, signature) pairs it pops
    strength: frozenset       # ANSWERS threats it answers
    blimp: float              # rough blimp damage per second (counters.json)
    auras: frozenset          # what it lends towers in range (radar, MIB, lead dip ...)

    @property
    def score(self):
        return (W_COVERAGE * self.coverage + W_STRENGTH * len(self.strength)
                + W_BLIMP * 1000.0 * self.blimp / max(self.cost, 1) + W_AURA * len(self.auras))


@lru_cache(maxsize=None)
def profile(kind, tiers):
    tiers = tuple(tiers)
    me = [("me", kind, tiers)]
    names = TH.calendar(STD, 1, 100)
    pops = frozenset(n for n in names if TH.covers(me, TH.sig_from_name(n))[0])
    pairs = calendar_pairs()
    return Profile(
        kind, tiers, T.total_cost(kind, tiers),
        TH.camo_access(kind, tiers) is not None,
        pops, sum(n in pops for _, n in pairs) / len(pairs),
        frozenset(t for t in STRENGTH if answers_threat(kind, tiers, t, me)),
        TH.blimp_dps(kind, tiers), TH.auras(kind, tiers))


def union_coverage(towers):
    """Share of calendar pairs that a set of (kind, tiers) towers pops together."""
    tw = [(f"t{i}", k, tuple(t)) for i, (k, t) in enumerate(towers)]
    names = TH.calendar(STD, 1, 100)
    ok = {n: TH.covers(tw, TH.sig_from_name(n))[0] for n in names}
    pairs = calendar_pairs()
    return sum(ok[n] for _, n in pairs) / len(pairs)


def drops_bananas(kind, tiers):
    """Game.drops_bananas for a crosspath: does the bot have to collect it?"""
    return Game.drops_bananas(SimpleNamespace(kind=kind, tiers=list(tiers)))


# ---------------------------------------------------------------------------
# Choosing paths
# ---------------------------------------------------------------------------

@dataclass
class Line:
    """One way of upgrading copies: the path, its second path, the working
    tier copies stop at, and the tier-4/5 targets of the copy that goes on."""
    kind: str
    path: int
    second: int | None
    work_tier: int

    def at(self, tier):
        return path_tiers(self.path, tier, self.second)

    @property
    def work(self):
        return self.at(self.work_tier)

    @property
    def stage1(self):
        """First upgrades (cheap): two tiers of the path, one of the second
        path. The path stays strictly ahead, because the executor's surplus()
        spends idle cash on a tower's highest path - on a tie it would take
        the lower-numbered one, which may not be this line's."""
        t = list(self.at(min(2, self.work_tier)))
        fix = CURSOR_FIX.get(self.kind)
        if fix and fix[0] == self.second:
            t[self.second - 1] = fix[1]          # a target mode of its own comes first
        elif self.second:
            t[self.second - 1] = min(t[self.second - 1], max(0, t[self.path - 1] - 1))
        return tuple(t)

    @property
    def t4(self):
        return self.at(4)


def _second_paths(kind, path):
    """Second-path choices for a main path, best first: the one whose tier 2
    adds most (Profile.score at tier 4), then the dearer one - when the game
    model cannot tell two upgrades apart, the price is the best guess of power."""
    fix = CURSOR_FIX.get(kind)
    if fix and fix[0] != path:
        return [fix[0]]                     # e.g. a heli always buys Pursuit
    opts = [q for q in (1, 2, 3) if q != path]
    return sorted(opts, key=lambda q: (profile(kind, path_tiers(path, 4, q)).score,
                                       T.total_cost(kind, path_tiers(path, 4, q))), reverse=True)


def working_tier(kind, path, second):
    """Highest tier (2-4) of a path whose crosspath fits COPY_BUDGET."""
    for tier in (4, 3):
        if T.total_cost(kind, path_tiers(path, tier, second)) <= COPY_BUDGET:
            return tier
    return 2


def path_score(kind, path, second):
    """How good a path is: its tier 4, plus half of its tier 5 (the late game
    and the XP sink), as one tower can use them."""
    return profile(kind, path_tiers(path, 4, second)).score \
        + 0.5 * profile(kind, path_tiers(path, 5, second)).score


def income_path(kind):
    """For an income tower (Banana Farm): the cheapest path whose tier 3 pays
    without bananas to collect (Game.drops_bananas) - Marketplace."""
    ok = [p for p in (1, 2, 3) if not drops_bananas(kind, path_tiers(p, 3))]
    return min(ok or (1, 2, 3), key=lambda p: T.total_cost(kind, path_tiers(p, 3)))


def main_line(kind):
    """The tower's main path (with its second path and working tier)."""
    if kind in S.INCOME_TOWERS:
        path = income_path(kind)
        # the game model has no income figures: the cheaper side path, so the
        # income starts sooner (a tie goes to the lower-numbered path)
        second = min((q for q in (1, 2, 3) if q != path),
                     key=lambda q: (T.total_cost(kind, path_tiers(path, 3, q)), q))
        return Line(kind, path, second, 3)
    best = max(((path_score(kind, p, _second_paths(kind, p)[0]), -p, p) for p in (1, 2, 3)))
    path = best[2]
    second = _second_paths(kind, path)[0]
    return Line(kind, path, second, working_tier(kind, path, second))


def complement_line(kind, main):
    """A line on another path that adds most of what the main line misses,
    or None when nothing on another path helps."""
    base = profile(kind, main.work)
    base4 = profile(kind, main.t4)
    best = None
    for path in (1, 2, 3):
        if path == main.path:
            continue
        second = _second_paths(kind, path)[0]
        line = Line(kind, path, second, working_tier(kind, path, second))
        prof = profile(kind, line.work)
        gain = (W_COVERAGE * (union_coverage([(kind, main.work), (kind, line.work)]) - base.coverage)
                + W_STRENGTH * len(prof.strength - base4.strength)
                + (1.0 if prof.sees_camo and not base.sees_camo else 0.0))
        key = (round(gain, 3), path_score(kind, path, second), -path)
        if best is None or key > best[0]:
            best = (key, line)
    return best[1] if best else None


def is_carry(kind):
    """Can this tower carry a game by itself? (see the module docstring)"""
    if category(kind) == "support" or kind in S.INCOME_TOWERS or needs_aim(kind):
        return False
    line = main_line(kind)
    prof = profile(kind, line.t4)
    if prof.auras - {"deregrow"}:
        return False          # a buffer (Alchemist): its value is in the towers beside it
    return prof.blimp > 0 and prof.coverage > 0


def restricted_modes(kind):
    """Category-only modes this tower may be played in (primary_only ...)."""
    return [m for m, cat in S.MODE_TOWER_FILTER.items() if cat == category(kind)]


def defence_for(kind):
    """The carry that defends a support build: a land tower buyable on round 1
    (it IS the early defence), of the same category when the tower has a
    category-only mode (so the pair may play it there). First choice: one
    whose own lines see camo (a radar village is a support tower, which those
    modes forbid); then the best working crosspath (Profile.score)."""
    cats = {category(kind)} if restricted_modes(kind) else None
    best = None
    for k in T.TOWERS:
        if k == kind or not is_carry(k) or placement(k) != "land" or T.tower_cost(k) > START_CASH:
            continue
        if cats and category(k) not in cats:
            continue
        line = main_line(k)
        comp = complement_line(k, line)
        sees = profile(k, line.work).sees_camo or (comp is not None and profile(k, comp.work).sees_camo)
        key = (sees, profile(k, line.work).score, -T.tower_cost(k))
        if best is None or key > best[0]:
            best = (key, k)
    return best[1] if best else None


def opener_for(kind):
    """A cheap carry for round 1 when the tower itself costs more than the
    starting cash: the cheapest land carry of the same category (so a
    category-only mode may place it), or of any category."""
    cands = [k for k in T.TOWERS if k != kind and is_carry(k) and placement(k) == "land"
             and T.tower_cost(k) <= START_CASH]
    same = [k for k in cands if category(k) == category(kind)]
    pool = same or cands
    return min(pool, key=lambda k: (T.tower_cost(k), k)) if pool else None


def water_maps(kind):
    """Maps where a water tower reaches enough of the track (data/map_fit.json:
    early or late side, at least the planner's FULL_FIT)."""
    from btd6bot import mapfit
    out = []
    for m, entry in sorted(mapfit.load().items()):
        fit = (entry.get("towers") or {}).get(kind)
        if fit and max(fit.get("early", 0), fit.get("late", 0)) >= P.FULL_FIT:
            out.append(m)
    return out


# ---------------------------------------------------------------------------
# A build: steps plus the reasons behind them
# ---------------------------------------------------------------------------

@dataclass
class Build:
    kind: str
    plan: list = field(default_factory=list)       # [(step, comment)]
    fill: list = field(default_factory=list)
    panic: list = field(default_factory=list)
    answers: dict = field(default_factory=dict)    # threat -> [(step, comment)]
    kinds: dict = field(default_factory=dict)      # tower id -> kind
    tiers: dict = field(default_factory=dict)      # tower id -> tiers the plan reaches
    core: dict = field(default_factory=dict)       # kind -> per-path tiers the build needs
    notes: list = field(default_factory=list)      # header lines (reasoning)
    roles: dict = field(default_factory=dict)      # tower id -> place step
    lines: dict = field(default_factory=dict)      # "main"/"comp"/"defence"/... -> Line
    support: list = field(default_factory=list)    # support tower ids (village, spike ...)
    history: dict = field(default_factory=dict)    # tower id -> tiers after each plan step
    maps: list | None = None
    uses_income: bool = False
    hero: str = HERO                               # pick_hero, set by _assemble
    extra: int = 0                                 # Hard reinforcement copies (generate)
    carry: bool = True                             # solo build (False: defence + the tower)

    def place(self, tid, kind, why=None, **kw):
        st = {"do": "place", "id": tid, "kind": kind, **kw}
        self.plan.append((st, why))
        self.kinds[tid] = kind
        self.tiers[tid] = (0, 0, 0)
        self.history[tid] = [(0, 0, 0)]
        self.roles[tid] = st

    def upgrade(self, tid, tiers, why=None):
        cur = self.tiers[tid]
        new = tuple(max(a, b) for a, b in zip(cur, tiers))
        if new == cur:
            return
        assert TH.legal(new), (tid, new)
        self.plan.append(({"do": "upgrade", "id": tid, "to": cross(new)}, why))
        self.tiers[tid] = new
        self.history[tid].append(new)

    def need(self, kind, tiers):
        """Record a crosspath the build needs to be safe (planner.towers)."""
        have = self.core.get(kind, [0, 0, 0])
        self.core[kind] = [max(a, b) for a, b in zip(have, tiers)]

    def strategy(self, modes=(), base=None):
        """The build as a strategy dict (what load_all would read)."""
        d = {"id": f"solo_{self.kind}", "xp_target": self.kind, "hero": self.hero,
             "modes": list(modes)}
        if self.uses_income:
            d["uses_income"] = True
        gen = {}
        if self.extra:
            gen["hard_extra"] = self.extra
        if self.carry != is_carry(self.kind):
            gen["carry"] = self.carry
        if gen:
            d["generator"] = gen      # how to make it again (tests/test_generated_builds_offline.py)
        planner = {"towers": {k: list(v) for k, v in self.core.items()},
                   "base_success": dict(base or {m: BASE_FLOOR for m in modes})}
        if self.maps is not None:
            planner["maps"] = list(self.maps)
        d["planner"] = planner
        d["plan"] = [dict(s) for s, _ in self.plan]
        d["fill"] = [dict(s) for s, _ in self.fill]
        d["panic"] = [dict(s) for s, _ in self.panic]
        d["answers"] = {t: [dict(s) for s, _ in steps] for t, steps in self.answers.items()}
        return d


def _final_towers(b):
    """(id, kind, tiers) of every tower the plan ends with."""
    return [(tid, k, b.tiers[tid]) for tid, k in b.kinds.items()]


def _describe(kind, tiers):
    prof = profile(kind, tiers)
    bits = []
    if prof.sees_camo:
        bits.append("sees camo")
    props = [p for p in ("lead", "purple", "black", "white") if p in prof.pops]
    if props:
        bits.append("pops " + "/".join(props))
    if prof.strength:
        bits.append("answers " + ", ".join(t for t in STRENGTH if t in prof.strength))
    if prof.blimp:
        bits.append(f"~{prof.blimp:g} blimp dmg/s")
    if prof.auras - {"deregrow"}:
        bits.append("lends " + ", ".join(sorted(prof.auras - {"deregrow"})))
    return f"{cross(tiers)} {top_upgrade(kind, tiers)} ({'; '.join(bits) or 'no attack of its own'})"


# ---------------------------------------------------------------------------
# Building the steps
# ---------------------------------------------------------------------------

def _copies(cost, budget):
    return max(2, min(MAX_COPIES, int(budget // max(cost, 1))))


def _affordable_tier(line, top):
    """Highest tier up to `top` on a line's path whose every upgrade from the
    working tier on costs at most TIER5_BUDGET (half a Hard game)."""
    tier = line.work_tier
    while tier < top and T.upgrade_cost(line.kind, line.path, tier + 1) <= TIER5_BUDGET:
        tier += 1
    return tier


def _late_power(b, ids_main, main, ids_comp, comp, before_tier5=None):
    """One main copy (and the first complement) on to tier 4 and tier 5 - one
    tier 5 per path, as the game allows - and the second main copy to tier 4.
    All tier 3/4 upgrades come before the tier 5s. A tier dearer than half a
    Hard game goes to fill instead: a $100,000 Sun Temple in the plan would
    hold up every step after it."""
    jobs = [(ids_main[0], main, 5)]
    if len(ids_main) > 1:
        jobs.append((ids_main[1], main, 4))
    if comp and ids_comp:
        jobs.append((ids_comp[0], comp, 5))
    steps = []
    for tid, line, top in jobs:
        reach = _affordable_tier(line, top)
        steps += [(tier, tid, line) for tier in range(line.work_tier + 1, reach + 1)]
        if reach < top:
            price = T.upgrade_cost(line.kind, line.path, reach + 1)
            b.fill.append(({"do": "upgrade", "id": tid, "to": cross(line.at(top))},
                           f"{upgrade_name(line.kind, line.path, reach + 1)} costs ${price:,}, more than "
                           f"half a Hard game: only in fill"))
    hook_done = before_tier5 is None
    for tier, tid, line in sorted(steps, key=lambda s: s[0]):
        if tier == 5 and not hook_done:
            before_tier5()
            hook_done = True
        name5 = upgrade_name(line.kind, line.path, tier)
        why = (f"tier 5 {name5} (${T.upgrade_cost(line.kind, line.path, 5):,}): one per path, "
               f"the biggest XP sink" if tier == 5 else f"{name5}: late-game power")
        b.upgrade(tid, line.at(tier), why)
    if not hook_done:
        before_tier5()


def _radar_village(b, near):
    """Radar Scanner village beside the copies: every tower in range sees camo."""
    kind, path, tier = S.RADAR
    tiers = path_tiers(path, tier)
    b.place("rv", kind, f"no copy sees camo: a {upgrade_name(kind, path, tier)} village lends it",
            role="support", near=list(near[:4]), near_radius=8)
    b.upgrade("rv", tiers)
    b.support.append("rv")


def _exit_spike(b):
    """One spike factory at the exit as leak insurance: the cheapest crosspath
    whose spikes pop every bloon property (they lie on the track, so camo too)."""
    kind = "spike"
    need = {"lead", "black", "white", "purple"}
    words = (GM.tower(kind) or {}).get("crosspaths", {})
    best = None
    for t in TH.all_crosspaths():
        if max(t) > 2:
            continue
        if need <= set(words.get("".join(map(str, t)), ())):
            c = T.total_cost(kind, t)
            if best is None or c < best[0]:
                best = (c, t)
    tiers = best[1] if best else (0, 0, 0)
    b.place("ex", kind, f"exit spike factory {cross(tiers)}: catches leaks, spikes hit camo on the track",
            role="exit")
    b.upgrade("ex", tiers)
    b.support.append("ex")


def _answering_crosspaths(kind, threat, final, towers=()):
    """Crosspaths no further than `final` at which one tower of this kind
    answers a threat, cheapest first: for camo/lead/purple it pops that
    signature itself (threats.covering_crosspaths), for the others it is an
    entry of strategy.ANSWERS (a DDT answer must also hurt DDTs itself)."""
    if threat in PROPERTY:
        opts = TH.covering_crosspaths(kind, TH.sig_from_name(threat), caps=final)
    else:
        opts = []
        for k, path, tier in answer_table(threat):
            want = path_tiers(path, tier) if path else (0, 0, 0)
            if k == kind and all(w <= f for w, f in zip(want, final)):
                if threat != "ddt" or answers_threat(kind, want, "ddt", list(towers) + [("me", kind, want)]):
                    opts.append(want)
    return sorted(set(opts), key=lambda t: (T.total_cost(kind, t), t))


def _own_answer(b, threat, ids):
    """(cost, tower id, crosspath): the cheapest way one of these planned
    towers answers a threat on its own plan path, or None."""
    towers = _final_towers(b)
    best = None
    for tid in ids:
        kind, final = b.kinds[tid], b.tiers[tid]
        opts = _answering_crosspaths(kind, threat, final, [t for t in towers if t[0] != tid])
        if opts:
            c = T.total_cost(kind, opts[0])
            if best is None or c < best[0]:
                best = (c, tid, opts[0])
    return best


def _steps_for(b, tid, want):
    """Answer steps that bring tower `tid` to crosspath `want`, and place it
    if the plan has not yet. When the threat comes the tower may stand at any
    stage of its plan, and the executor never upgrades a tower toward a target
    it has passed on some path, so there is one upgrade step per plan stage
    (`want` joined with that stage), earliest first: the first one the tower
    has not passed is the one that buys. Stages that already have `want` are
    left out: a tower there answers the threat, and a step toward a later
    stage would buy more than the answer needs (a tier 5 for a MOAB)."""
    targets = []
    for stage in b.history.get(tid) or [(0, 0, 0)]:
        if all(s >= w for s, w in zip(stage, want)):
            break
        t = tuple(max(a, c) for a, c in zip(stage, want))
        if TH.legal(t) and any(t) and t not in targets:
            targets.append(t)
    steps = [({"do": "upgrade", "id": tid, "to": cross(t)}, None) for t in targets]
    return steps + [(dict(b.roles[tid]), None)]


def _helper_options(threat, b, exclude, allowed_cats, water_only, used_ids=()):
    """[(cost, steps, description, (id, kind, tiers))]: helpers of a kind not
    in `exclude` - a tower the build already has (exit spike, radar village,
    opener, earlier helpers) upgraded on its own path, or a new one. Ranked by
    the full price of the answering crosspath (a planned tower may not stand
    yet when the threat comes), so tier-0 answers - the ones an account with
    locked upgrades can still buy - come first; a tower of the build wins a tie."""
    towers = _final_towers(b)
    sig = TH.sig_from_name(threat) if threat in PROPERTY else None
    out = []
    for kind in T.TOWERS:
        # Gift-box towers (Desperado, Mermonkey, Skywarden, Beast Handler,
        # Dartling) were never helpers: "they may be locked". The executor
        # skips a step whose tower the account lacks and goes on to the next
        # answer, as for any locked tower, and the live account has all of
        # them (docs/tower_exclusions_audit.md item 9). A tower that must be
        # aimed (the Dartling) is still no helper.
        if kind in exclude or kind in S.INCOME_TOWERS or needs_aim(kind):
            continue
        if allowed_cats is not None and category(kind) not in allowed_cats:
            continue
        if placement(kind) == "water" and not water_only:
            continue
        if sig is not None:
            wants = TH.covering_crosspaths(kind, sig)
        else:
            wants = _answering_crosspaths(kind, threat, (5, 5, 5), towers)
        for want in wants:
            # 1. a tower of the build of that kind, if its own path allows it
            for tid, k, have in towers:
                if k != kind or tid in used_ids:
                    continue
                new = tuple(max(a, c) for a, c in zip(have, want))
                if not TH.legal(new):
                    continue
                out.append((T.total_cost(kind, want), 0, _steps_for(b, tid, want),
                            f"{tid} ({name(kind)}) {cross(want)}", (tid, kind, new)))
            # 2. a new helper tower, with its own id (a helper of the same kind
            # bought for another threat may stand on another path)
            hid, n = f"h_{kind}", 1
            while hid in b.kinds:
                n += 1
                hid = f"h_{kind}{n}"
            role = {"role": "exit"} if kind in S.EXIT_KINDS else {"role": "dps", "segment": [0.0, 0.7]}
            steps = ([({"do": "upgrade", "id": hid, "to": cross(want)}, None)] if any(want) else []) + \
                [({"do": "place", "id": hid, "kind": kind, **role}, None)]
            out.append((T.total_cost(kind, want), 1, steps, f"a {name(kind)} {cross(want)}", (hid, kind, want)))
    out.sort(key=lambda o: (o[0], o[1], o[3]))
    return [(cost, steps, desc, tower) for cost, _, steps, desc, tower in out]


def _more_copies(b, kind):
    """For a blimp class answered by the tower being levelled: `place another
    <kind>` (up to as many as the plan places), so that a short blimp damage
    estimate first buys more of the tower the plan buys anyway, and the
    helper after it only comes when they all stand (or the tower's own tiers
    are locked)."""
    # not the Hard reinforcement's late copies (_extra_copies): counting them
    # let this step buy bare copies early - on the sub build one more
    # ("max" 7 -> 8) took the round-40 blimp ratio from 3.72 to 0.41
    planned = [st for st, _ in b.plan if st.get("do") == "place" and st.get("kind") == kind
               and not str(st.get("id", "")).startswith(EXTRA_PREFIXES)]
    if not planned:
        return None
    first = planned[0]
    step = {"do": "place", "kind": kind, "role": first.get("role", "dps")}
    for key in ("segment", "near", "near_radius"):
        if key in first:
            step[key] = first[key] if key != "segment" else [0.0, 1.0]
    step["max"] = len(planned)
    return step


def _remember(b, steps):
    """A helper chosen for one threat is a tower of the build for the next ones."""
    for st, _ in steps:
        if st["do"] == "place" and st["id"] not in b.kinds:
            b.kinds[st["id"]] = st["kind"]
            b.tiers[st["id"]] = (0, 0, 0)
            b.history[st["id"]] = [(0, 0, 0)]
            b.roles[st["id"]] = dict(st)
    for st, _ in steps:
        if st["do"] == "upgrade":
            new = tuple(max(a, c) for a, c in zip(b.tiers[st["id"]], S.parse_cross(st["to"])))
            if new != b.tiers[st["id"]]:
                b.tiers[st["id"]] = new
                b.history[st["id"]].append(new)


def _answers(b, core, allowed_cats, last_round, water_only=False):
    """`answers:` for every threat up to last_round (camo, lead, purple and the
    strength threats of strategy.ANSWERS), each tried in order in game:

      1. a copy of the tower being levelled, on its own plan path (keeps the
         cash in it; the executor takes it only when it is about as cheap as
         any other answer);
      2. another tower of the plan (defence, radar village, exit spike);
      3. a helper of another kind - from the category of a category-only mode
         when the build has one, and then the cheapest of any category when
         that one is cheaper (a mode skips steps it forbids).

    The helpers are what lets coverage() (and the planner) accept the build on
    an account whose own tiers are still locked - exactly when the tower needs
    the XP. The executor only reaches them when the steps before cannot buy.

    No helper when the answer is the bare tower of the build's own kind (it
    cannot be locked). Blimp classes (MOAB ... BAD): the executor's blimp ramp
    check also runs their answers whenever its (pessimistic) damage estimate
    is short, and an own step that is already done falls through to the next
    one. So when the tower being levelled answers one itself, "another copy of
    it" (up to the plan's count) stands between its own steps and the helper:
    a short estimate first buys more of that tower, the helper only when all
    copies stand or its tiers are locked. Trade-off, chosen for the owner's
    rules (every tower playable when it needs XP; never lose): a few percent
    of the cash can go to a helper on a fully unlocked account."""
    notes = []
    core = set(core)
    plan_ids = [tid for tid in b.kinds if b.kinds[tid] != "hero"]
    for threat in sorted((t for t in PROPERTY + STRENGTH if FIRST_ROUND.get(t, 999) <= last_round),
                         key=lambda t: (FIRST_ROUND[t], t)):
        steps, used, used_ids = [], [], set()
        # a tower the bot cannot aim is never counted on for an answer
        mine = [t for t in plan_ids if b.kinds[t] == b.kind] if not needs_aim(b.kind) else []
        own = _own_answer(b, threat, mine) \
            or _own_answer(b, threat, [t for t in plan_ids if b.kinds[t] != b.kind and not t.startswith("h_")])
        if own:
            _, tid, want = own
            steps += _steps_for(b, tid, want)
            used.append(f"{tid} {cross(want)}")
            used_ids.add(tid)
            if not any(want) and b.kinds[tid] in core:
                b.answers[threat] = steps
                notes.append(f"{threat}: {used[0]}")
                continue
            if threat in BLIMP_CLASSES and b.kinds[tid] == b.kind:
                more = _more_copies(b, b.kind)
                if more:
                    steps.append((more, None))
                    used.append(f"another {name(b.kind)} (up to {more['max']})")
        # a helper is another kind than the towers already answering above
        exclude = core | {b.kinds[t] for t in used_ids}
        opts = _helper_options(threat, b, exclude, allowed_cats, water_only, used_ids)
        anyc = _helper_options(threat, b, exclude, None, water_only, used_ids) if allowed_cats is not None else []
        picks = opts[:1]
        if anyc and (not opts or (anyc[0][0] < opts[0][0] and anyc[0][2] != opts[0][2])):
            picks.insert(0, anyc[0])        # cheapest first; a mode that forbids it skips it
        for _cost, hsteps, desc, _tower in picks:
            steps += hsteps
            used.append(desc)
            _remember(b, hsteps)
        if steps:
            b.answers[threat] = steps
            notes.append(f"{threat}: " + ", else ".join(used))
        else:
            notes.append(f"{threat}: nothing answers it (the executor's own checks decide)")
    return notes


def _segments_for(kind):
    """Spikes throw onto the track in range: they spread over the later track."""
    if kind in S.EXIT_KINDS:
        return [[0.5, 1.0], [0.3, 0.9], [0.6, 1.0], [0.4, 1.0]]
    return list(SEGMENTS)


def first_stage(kind, line):
    """A line's first upgrades: its stage1 plus the cheap tiers (no path above
    2) that already give properties its working crosspath has - lead, camo,
    purple ... - so they come before those bloons do (R24-28)."""
    prof = profile(kind, line.work)
    props = {p for p in ("lead", "purple", "black", "white") if p in prof.pops}
    if prof.sees_camo:
        props.add("camo")
    tiers = list(line.stage1)
    for prop in sorted(props):
        opts = [t for t in TH.covering_crosspaths(kind, TH.sig_from_name(prop), caps=line.work)
                if max(t) <= 2]
        if opts:
            best = min(opts, key=lambda t: (T.total_cost(kind, t), t))
            merged = [max(a, c) for a, c in zip(tiers, best)]
            if TH.legal(merged):
                tiers = merged
    return tuple(tiers)


def property_fix(kind, line, lacking):
    """The cheapest crosspath on the way to a line's working crosspath that
    pops/sees the properties (lead, camo, purple ...) another line lacks,
    or None when the line cannot."""
    tiers = list(line.stage1)
    for prop in sorted(lacking):
        opts = TH.covering_crosspaths(kind, TH.sig_from_name(prop), caps=line.work)
        if not opts:
            return None
        best = min(opts, key=lambda t: T.total_cost(kind, t))
        tiers = [max(a, c) for a, c in zip(tiers, best)]
    return tuple(tiers) if TH.legal(tiers) else None


def _lacking(p_main, p_other):
    """Properties the other crosspath has and the main one lacks."""
    props = {"lead", "purple", "black", "white"} & set(p_other.pops - p_main.pops)
    if p_other.sees_camo and not p_main.sees_camo:
        props.add("camo")
    return props


EXTRA_PREFIXES = ("hx", "dx")      # tower ids of the Hard reinforcement's copies


def _extra_copies(b, kind, line, n, segs, prefix="hx"):
    """The Hard reinforcement (generate): n more copies of a line at its
    working crosspath, placed after the tier 3/4 upgrades and before the
    tier 5s (_late_power's before_tier5): at the very end of a plan a Hard
    game does not finish by its last blimp rounds, they were never bought
    (the sub build stayed at 0.84 with one to four of them)."""
    for i in range(n):
        tid = f"{prefix}{i + 1}"
        b.place(tid, kind, "Hard: more blimp damage than a Medium game needs" if i == 0 else None,
                role="dps", segment=list(segs[(i + 2) % len(segs)]))
        b.upgrade(tid, line.work)


def build_carry(kind, extra=0):
    """A solo build: copies of the tower on its main and complement lines.
    extra: more main-line copies than the Medium budget sizes it for (the
    Hard reinforcement, see generate).

    Order of the plan, with the reason for each part:
      * two copies at their cheap first tiers (rounds 1-20);
      * the complement brought to the crosspath that adds what the main
        line lacks (lead, camo ...) before those bloons come (R24-28), so
        the threat checks need not buy another tower for them;
      * a radar village only when no copy sees camo;
      * the first copy at its working crosspath before the first MOAB (R40),
        then the others; the exit spike once the copies stand;
      * one copy per path to tier 4 and tier 5 (XP sinks, late power)."""
    b = Build(kind)
    main = main_line(kind)
    comp = complement_line(kind, main)
    b.lines.update(main=main, comp=comp)
    pm = profile(kind, main.work)
    pc = profile(kind, comp.work) if comp else None
    lacking = _lacking(pm, pc) if pc else set()
    fix = property_fix(kind, comp, lacking) if lacking else None
    n_comp = (2 if lacking else 1) if comp else 0
    comp_cost = n_comp * (pc.cost if pc else 0)
    n_main = _copies(pm.cost, PLAN_BUDGET * 0.75 - comp_cost)
    if placement(kind) == "water":
        b.maps = water_maps(kind)

    b.notes += [f"Main line x{n_main}: {_describe(kind, main.work)}",
                f"  path chosen at tier 4: {_describe(kind, main.t4)}"]
    if comp:
        b.notes.append(f"Complement x{n_comp}: {_describe(kind, comp.work)}")
        if lacking:
            b.notes.append(f"  adds {', '.join(sorted(lacking))} the main line lacks"
                           + (f" (from {cross(fix)}, bought early)" if fix else ""))

    # -- early game -----------------------------------------------------------
    segs = _segments_for(kind)
    if T.tower_cost(kind) > START_CASH:
        op = opener_for(kind)
        if op:
            b.place("o1", op, f"{name(kind)} costs ${T.tower_cost(kind):,} - more than the "
                    f"${START_CASH} start: a {name(op)} holds the first rounds", role="dps",
                    segment=[0.0, 0.6])
    a = [f"a{i + 1}" for i in range(n_main)]
    k = [f"b{i + 1}" for i in range(n_comp)]
    b.place(a[0], kind, f"main line: {cross(main.work)}", role="dps", segment=segs[0])
    b.place("hero", "hero", "heroes take no share of tower XP", role="dps", segment=[0.0, 0.6])
    b.upgrade(a[0], first_stage(kind, main), "cheap tiers first (and lead/camo if they are cheap)")
    b.place(a[1], kind, None, role="dps", segment=segs[1])
    b.upgrade(a[1], first_stage(kind, main))
    if k:
        b.place(k[0], kind, f"complement: {cross(comp.work)}", role="dps", segment=segs[3])
        b.upgrade(k[0], fix or comp.stage1,
                  f"{', '.join(sorted(lacking))} before those bloons come" if fix else None)
    # -- support ----------------------------------------------------------------
    camo_ok = pm.sees_camo or (pc is not None and pc.sees_camo)
    if not camo_ok:
        _radar_village(b, a[:2] + k[:1])
    # -- mid game: copies to their working crosspath -------------------------------
    b.upgrade(a[0], main.at(min(3, main.work_tier)))
    b.upgrade(a[0], main.work, "blimp power before the first MOAB round")
    b.upgrade(a[1], main.at(min(3, main.work_tier)))
    if k:
        b.upgrade(k[0], comp.work)
    b.upgrade(a[1], main.work)
    for i, tid in enumerate(a[2:], start=2):
        b.place(tid, kind, None, role="dps", segment=segs[i % len(segs)])
        b.upgrade(tid, main.work)
        if i == 2 and len(k) > 1:
            b.place(k[1], kind, None, role="dps", segment=segs[(i + 3) % len(segs)])
            b.upgrade(k[1], comp.work)
    if len(k) > 1 and k[1] not in b.kinds:
        b.place(k[1], kind, None, role="dps", segment=segs[5])
        b.upgrade(k[1], comp.work)
    if kind not in S.EXIT_KINDS:
        _exit_spike(b)
    # -- late game: tier 4 and the tier 5s ----------------------------------------------
    _late_power(b, a, main, k, comp, before_tier5=lambda: _extra_copies(b, kind, main, extra, segs))

    b.need(kind, main.work)
    if comp:
        b.need(kind, comp.work)
    b.fill += [({"do": "place", "kind": kind, "role": "dps", "max": n_main + n_comp + FILL_EXTRA},
                "surplus cash: more copies (XP follows the cash)"),
               ({"do": "upgrade", "kind": kind, "to": cross(main.work)}, None)]
    if main.work_tier < 4:
        b.fill.append(({"do": "upgrade", "kind": kind, "to": cross(main.t4)}, None))
    b.panic += [({"do": "place", "kind": kind, "role": "dps"}, None)]
    if kind not in S.EXIT_KINDS:
        b.panic.append(({"do": "place", "kind": "spike", "role": "exit"}, None))
    return b


def build_support(kind, extra=0):
    """A support/income/aimed tower: a compact defence of the best carry that
    may stand beside it, then the tower itself, and the surplus into it.
    extra: more copies of the tower itself when it has blimp damage of its
    own, else more defence copies (the Hard reinforcement, see generate)."""
    b = Build(kind)
    dkind = defence_for(kind)
    dmain = main_line(dkind)
    dcomp = complement_line(dkind, dmain)
    line = main_line(kind)
    comp = complement_line(kind, line) if kind not in S.INCOME_TOWERS else None
    b.lines.update(main=line, comp=comp, defence=dmain, dcomp=dcomp)
    pd = profile(dkind, dmain.work)
    pdc = profile(dkind, dcomp.work) if dcomp else None
    pk = profile(kind, line.work)
    b.uses_income = kind in S.INCOME_TOWERS

    why_support = ("an income tower" if kind in S.INCOME_TOWERS else
                   "it must be aimed and the bot does not aim" if needs_aim(kind) else
                   "a support tower" if category(kind) == "support" else
                   "a buffer: its value is in the towers beside it" if pk.auras - {"deregrow"} else
                   "it has no blimp damage figure (counters.json): it cannot be shown to stop MOABs")
    b.notes += [f"{name(kind)} cannot carry a game alone ({why_support}), so a compact defence "
                f"of {name(dkind)}s holds the track and the rest of the money goes into it.",
                f"Defence x2: {_describe(dkind, dmain.work)}"]
    if dcomp:
        b.notes.append(f"Defence complement x1: {_describe(dkind, dcomp.work)}")
    b.notes.append(f"{name(kind)} line: {_describe(kind, line.work)}")
    if comp:
        b.notes.append(f"{name(kind)} second line (its other tier 5): {_describe(kind, comp.work)}")

    # role of the tower itself
    if kind in S.INCOME_TOWERS:
        role = {"role": "far"}
    elif (pk.auras - {"deregrow"}) or (category(kind) == "support" and not pk.coverage):
        role = {"role": "support"}       # a buffer stands next to the towers it buffs
    else:
        role = {"role": "dps"}

    b.place("d1", dkind, f"defence: {cross(dmain.work)}", role="dps", segment=[0.0, 0.5])
    b.place("hero", "hero", "heroes take no share of tower XP", role="dps", segment=[0.0, 0.6])
    b.upgrade("d1", first_stage(dkind, dmain), "cheap tiers first (and lead/camo if they are cheap)")
    k_cost = pk.cost
    n_k = max(2, min(MAX_COPIES, int((PLAN_BUDGET * 0.8 - 2 * pd.cost - (pdc.cost if pdc else 0)) // max(k_cost, 1))))
    # The executor's surplus() places more of the plan's most-placed kind:
    # the tower being levelled must outnumber the defence in the plan.
    n_def = 2 + (1 if dcomp else 0)
    n_k = max(n_k, n_def + 1 - (1 if comp else 0))
    own_extra = extra if pk.blimp > 0 and not needs_aim(kind) else 0
    extra_def = extra - own_extra
    n_k = max(n_k, n_def + extra_def + 1 - (1 if comp else 0))   # still outnumbers the defence
    kids = [f"x{i + 1}" for i in range(n_k)]

    def place_k(i, why=None):
        kw = dict(role)
        if kw["role"] == "dps":
            kw["segment"] = list(_segments_for(kind)[i % 4])
        elif kw["role"] == "support":
            kw.update(near=["d1", "d2"] if i % 2 == 0 else ["d2", "dc"] if dcomp else ["d1", "d2"],
                      near_radius=8)
        b.place(kids[i], kind, why, **kw)

    if b.uses_income:
        # farms pay back over ~15 rounds: the first one goes in early
        place_k(0, f"{name(kind)} {cross(line.work)}: {upgrade_name(kind, line.path, 3)} first - "
                   f"its cash is paid without bananas to collect")
        b.upgrade(kids[0], path_tiers(line.path, 3), f"{upgrade_name(kind, line.path, 3)} first")
    b.place("d2", dkind, None, role="dps", segment=[0.3, 0.9])
    b.upgrade("d2", first_stage(dkind, dmain))
    lacking = _lacking(pd, pdc) if pdc else set()
    fix = property_fix(dkind, dcomp, lacking) if lacking else None
    if fix:
        b.place("dc", dkind, f"defence complement {cross(dcomp.work)}", role="dps", segment=[0.0, 0.7])
        b.upgrade("dc", fix, f"{', '.join(sorted(lacking))} before those bloons come")
    gives_camo = bool(pk.auras & {"camo", "all_types"}) or bool(profile(kind, line.t4).auras & {"camo"})
    camo_ok = pd.sees_camo or (pdc is not None and pdc.sees_camo) or gives_camo
    if not camo_ok:
        _radar_village(b, ["d1", "d2"] + (["dc"] if dcomp else []))
    b.upgrade("d1", dmain.at(min(3, dmain.work_tier)))
    b.upgrade("d1", dmain.work, "blimp power before the first MOAB round")
    if not b.uses_income:
        place_k(0, f"{name(kind)} {cross(line.work)}")
        b.upgrade(kids[0], first_stage(kind, line))
    b.upgrade("d2", dmain.at(min(3, dmain.work_tier)))
    b.upgrade(kids[0], line.work)
    if dcomp:
        if "dc" not in b.kinds:
            b.place("dc", dkind, f"defence complement {cross(dcomp.work)}", role="dps", segment=[0.0, 0.7])
        b.upgrade("dc", dcomp.work)
    b.upgrade("d2", dmain.work)
    for i in range(1, n_k):
        place_k(i)
        b.upgrade(kids[i], line.work)
        if i == 1 and kind not in S.EXIT_KINDS:
            _exit_spike(b)
    if kind not in S.EXIT_KINDS and "ex" not in b.kinds:
        _exit_spike(b)
    kc = []
    if comp:
        kc = ["y1"]
        kw = dict(role)
        if kw["role"] == "dps":
            kw["segment"] = [0.2, 0.9]
        elif kw["role"] == "support":
            kw.update(near=["d1", "d2"], near_radius=8)
        b.place("y1", kind, f"second {name(kind)} line: {cross(comp.work)}", **kw)
        b.upgrade("y1", comp.work)
    _late_power(b, kids, line, kc, comp, before_tier5=lambda: (
        _extra_copies(b, kind, line, own_extra, _segments_for(kind)),
        _extra_copies(b, dkind, dmain, extra_def, SEGMENTS, prefix="dx")))

    b.need(dkind, dmain.work)
    if dcomp:
        b.need(dkind, dcomp.work)
    b.need(kind, line.work)
    fill_role = dict(role)
    if fill_role["role"] == "support":
        fill_role.update(near=["d1", "d2"], near_radius=10)
    b.fill += [({"do": "place", "kind": kind, **fill_role, "max": n_k + 1 + FILL_EXTRA},
                f"surplus cash goes into {name(kind)}s (XP follows the cash)"),
               ({"do": "upgrade", "kind": kind, "to": cross(line.work)}, None)]
    if line.work_tier < 4:
        b.fill.append(({"do": "upgrade", "kind": kind, "to": cross(line.t4)}, None))
    b.fill.append(({"do": "upgrade", "kind": dkind, "to": cross(dmain.t4)},
                   "then the defence's own tier 4"))
    b.panic += [({"do": "place", "kind": dkind, "role": "dps"}, None)]
    if kind not in S.EXIT_KINDS:
        b.panic.append(({"do": "place", "kind": "spike", "role": "exit"}, None))
    return b


# ---------------------------------------------------------------------------
# The hero, on merit
# ---------------------------------------------------------------------------
# Every build used to name Quincy (docs/tower_exclusions_audit.md item 1).
# Now each build is rated in the damage model with every hero the model can
# rate, and the best one is named: the build's plan is bought on a
# reference map as a Medium game pays for it, round by round, with the hero
# at its place in the plan, at its own price and at its level by round. The
# score is the mean log2(margin) over the sample rounds, as
# tools/rank_heroes.py scores a hero alone. A hero's price and its buffs to
# the build's own towers (Obyn's to magic towers, Etienne's camo) count this
# way, which a ranking of heroes alone cannot see.
#
# A generated build plays on any map, so only heroes that stand on land are
# tried. Corvus has no profile (dps_model.UNRATED_HEROES); Geraldo is rated
# on his own attack (the game model exports no shop, and the bot cannot use
# it). An account that lacks the named hero gets the best owned one
# (strategy.hero_for).
HERO_MAP = "Monkey Meadow"
HERO_MODE = "medium"
HERO_ROUNDS = tuple(range(8, 81, 8))


def hero_candidates():
    """Land heroes the damage model can rate, best on merit first."""
    from btd6bot import dps_model as D
    return [h for h in T.hero_merit_order()
            if h not in D.UNRATED_HEROES and (T.HEROES[h].get("placement") or "land") == "land"
            and D.profile(D.hero_kind(h), (1,)) is not None]


def _step_cost(step, standing):
    """Medium price of a place or upgrade step (the hero's is priced apart).
    standing: {tower id: (kind, tiers)} before the step."""
    if step["do"] == "place":
        return T.tower_cost(step["kind"])
    kind, have = standing[step["id"]]
    want = S.parse_cross(step["to"])
    return sum(T.upgrade_cost(kind, path + 1, tier) for path in range(3)
               for tier in range(have[path] + 1, want[path] + 1))


def boards_by_round(plan, hero, rounds):
    """({round: [(id, kind, tiers)]}, {id: round placed}): the plan's steps
    bought in order, each once the cash a Medium game has paid by the start
    of that round (income) covers it, the hero at its own price."""
    standing, placed, boards = {}, {}, {}
    spent, i = 0.0, 0
    for rnd in range(1, max(rounds) + 1):
        budget = income(rnd - 1) if rnd > 1 else START_CASH
        while i < len(plan):
            st = plan[i]
            if st["do"] == "place":
                cost = T.hero_cost(hero) if st["kind"] == "hero" else _step_cost(st, standing)
            elif st["do"] == "upgrade" and st.get("id") in standing:
                cost = _step_cost(st, standing)
            else:
                i += 1              # nothing to buy (an upgrade of a tower not placed)
                continue
            if spent + cost > budget:
                break
            spent += cost
            if st["do"] == "place":
                standing[st["id"]] = (st["kind"], (0, 0, 0))
                placed[st["id"]] = rnd
            else:
                kind, have = standing[st["id"]]
                standing[st["id"]] = (kind, tuple(max(a, b) for a, b in zip(have, S.parse_cross(st["to"]))))
            i += 1
        if rnd in rounds:
            boards[rnd] = [(tid, kind, tiers) for tid, (kind, tiers) in standing.items()]
    return boards, placed


def rate_hero(plan, hero, setup):
    """Mean log2(margin) of the plan with this hero over HERO_ROUNDS on the
    reference map (setup: optimize_builds.MapSetup of HERO_MAP). A round
    with nothing standing scores the model's floor."""
    import math
    from btd6bot import dps_model as D
    boards, placed = boards_by_round(plan, hero, HERO_ROUNDS)
    ev = OPT.Evaluator(setup, HERO_MODE, hero)
    spots, taken, logs = {}, [], []
    for rnd in HERO_ROUNDS:
        towers = []
        for tid, kind, tiers in boards[rnd]:
            if tid not in spots:            # each tower keeps the spot it was given first
                spots[tid] = (setup.hero_spot(hero, taken) if kind == "hero"
                              else setup.free_spot(kind, taken))
                if spots[tid] is not None:
                    taken.append(OPT.Tower(tid, kind, spots[tid], (0, 0, 0)))
            if spots[tid] is None:
                continue
            if kind == "hero":
                tiers = OPT.hero_tiers_at(hero, HERO_MAP, HERO_MODE, None, placed[tid], rnd)
            towers.append(OPT.Tower(tid, kind, spots[tid], tiers))
        margin = ev.margins(towers, [rnd])[rnd] if towers else D.MARGIN_LO
        logs.append(math.log2(min(max(margin, D.MARGIN_LO), D.MARGIN_HI)))
    return sum(logs) / len(logs)


_HERO_PICKS = {}


def pick_hero(b):
    """The hero the build rates best with (rate_hero); HERO when the damage
    model is missing. A tie goes to the hero ranked higher on merit.
    Remembered by the plan's steps: generate() assembles a build several
    times, and the hero does not change the steps."""
    from btd6bot import dps_model as D
    if not D.available() or not D.HERO_RATING:
        return HERO
    plan = [dict(st) for st, _ in b.plan]
    key = repr(plan)
    if key not in _HERO_PICKS:
        setup = OPT.MapSetup(HERO_MAP, HERO_MODE)
        best = None
        for hero in hero_candidates():
            score = rate_hero(plan, hero, setup)
            if best is None or score > best[0] + 1e-9:
                best = (score, hero)
        _HERO_PICKS[key] = best[1] if best else HERO
    return _HERO_PICKS[key]


# ---------------------------------------------------------------------------
# Candidate modes and validation
# ---------------------------------------------------------------------------

def candidate_modes(kind):
    """Modes worth trying, in the order the YAML lists them: every mode the
    game has, the category-only ones for the tower's own category, and
    CHIMPS only for a tower that is not income (it forbids income towers).

    Double HP, Half Cash, ABR, Impoppable and CHIMPS were never tried
    (docs/tower_exclusions_audit.md item 9); each is now kept wherever the
    build passes the same checks (judge: coverage, the offline threat
    simulation, and for the Hard and Impoppable families blimp damage of
    the build's own)."""
    modes = ["easy"]
    if category(kind) == "primary":
        modes.append("primary_only")
    modes += ["deflation", "medium"]
    if category(kind) == "military":
        modes.append("military_only")
    modes += ["reverse", "apopalypse", "hard"]
    if category(kind) == "magic":
        modes.append("magic_only")
    modes += ["double_hp", "half_cash", "abr", "impoppable"]
    if kind not in S.INCOME_TOWERS:
        modes.append("chimps")
    return modes


def needs_own_damage(mode):
    """Must the build hold this mode's blimps with its own damage, no
    helper bought for the blimp ramp? Every mode of the Hard and Impoppable
    families (judge), and Apopalypse (random rounds, no breaks)."""
    return mode_family(mode) in ("hard", "impoppable") or mode == "apopalypse"


def for_mode(strat, mode):
    """The strategy as the executor plays it in a category-only mode: steps of
    towers that mode forbids are skipped (Executor._step_allowed)."""
    only = S.MODE_TOWER_FILTER.get(mode)
    if not only:
        return strat
    kinds = {st.get("id"): st.get("kind") for _, st in S._all_steps(strat) if st.get("do") == "place"}

    def ok(st):
        k = st.get("kind") or kinds.get(st.get("id"))
        return k in (None, "hero") or T.TOWERS[k]["category"] == only
    out = dict(strat)
    for key in ("plan", "fill", "panic"):
        out[key] = [st for st in strat.get(key) or [] if ok(st)]
    out["answers"] = {t: [st for st in v if ok(st)] for t, v in (strat.get("answers") or {}).items()}
    return out


def _tid_kind(tid, strat_kinds):
    if tid in strat_kinds:
        return strat_kinds[tid]
    if tid == "hero":
        return "hero"
    if tid.startswith("ans_"):
        return next((k for k in sorted(T.TOWERS, key=len, reverse=True) if tid.endswith("_" + k)), None)
    return next((k for k in sorted(T.TOWERS, key=len, reverse=True)
                 if tid.startswith(k) and tid[len(k):].isdigit()), None)


@dataclass
class Verdict:
    mode: str
    ok: bool
    why: str
    ratio: float | None = None
    share: float | None = None
    helpers: tuple = ()
    plan_done: str = ""


def _simulate(strat, mode, water):
    """simulate_threats.simulate with both tick counts the tests use."""
    runs = []
    for ticks in (8, 10):
        runs.append(SIM.simulate(strat, mode, water=water, ticks=ticks))
    return runs


def _share(run, strat, kind, mode):
    kinds = {st.get("id"): st.get("kind") for _, st in S._all_steps(strat) if st.get("do") == "place"}
    fam = S.PRICE_FAMILY.get(mode, "hard")
    spent = {}
    for tid, cp in run["build"].items():
        k = _tid_kind(tid, kinds)
        if k in (None, "hero"):
            continue
        spent[k] = spent.get(k, 0) + T.total_cost(k, cp, fam)
    total = sum(spent.values())
    return (spent.get(kind, 0) / total) if total else 0.0


def _without_blimp_helpers(strat):
    """The strategy without the helper towers its blimp-class answers name
    (the same object when there are none)."""
    answers = strat.get("answers") or {}
    if not any(str(st.get("id", "")).startswith("h_") for t in BLIMP_CLASSES for st in answers.get(t, ())):
        return strat
    trimmed = {t: ([st for st in v if not str(st.get("id", "")).startswith("h_")] if t in BLIMP_CLASSES else v)
               for t, v in answers.items()}
    return dict(strat, answers={t: v for t, v in trimmed.items() if v})


def judge(b, strat, mode, defence_only=None):
    """Verdict for one mode: usable, covered, and the offline simulation."""
    kind = b.kind
    fam = mode_family(mode)
    acct = SIM.full_account()
    probs = S.readiness(strat)
    if probs:
        return Verdict(mode, False, "not bot-ready: " + "; ".join(probs[:3]))
    ok, why = S.usable(strat, mode, acct)
    if not ok:
        return Verdict(mode, False, f"not usable: {why}")
    ok, missing = S.coverage(for_mode(strat, mode), mode, acct)
    if not ok:
        return Verdict(mode, False, "threats not covered in this mode: " + ", ".join(missing[:5]))
    waters = (True, False) if placement(kind) in ("water", "land_or_water") else (False,)
    runs = [r for w in waters for r in _simulate(strat, mode, w)]
    if defence_only is not None:
        runs += _simulate(defence_only, mode, False)
    gaps = [g for r in runs for g in r["gaps"]]
    if gaps:
        rnd, need, how = gaps[0]
        return Verdict(mode, False, f"gap R{rnd}: {need} ({how})")
    ratios = [x for r in runs for _, x in r["ramp"]]
    ratio = min(ratios) if ratios else None
    # towers bought as answers: the executor's own ("ans_...") and the
    # build's helpers ("h_..."); a blimp helper is one bought for the blimp ramp
    kinds = {st.get("id"): st.get("kind") for _, st in S._all_steps(strat) if st.get("do") == "place"}
    bought = {tid for r in runs for tid in r["build"] if tid.startswith(("ans_", "h_"))}
    helper_kinds = sorted({_tid_kind(t, kinds) or "?" for t in bought} - {kind})
    blimp_helpers = any(t.startswith("ans_blimps") for t in bought)
    if needs_own_damage(mode):
        # "has the damage": also without the helpers the build lists for blimp
        # classes (bought because strategy.ANSWERS does not list the tower for
        # that class, not for damage), and without the executor buying any
        own = _without_blimp_helpers(strat)
        if own is not strat:
            extra = _simulate(own, mode, waters[0])
            ratios += [x for r in extra for _, x in r["ramp"]]
            ratio = min(ratios) if ratios else None
            blimp_helpers = blimp_helpers or any(t.startswith("ans_blimps") for r in extra for t in r["build"])
            gaps = [g for r in extra for g in r["gaps"]]
            if gaps:
                rnd, need_, how = gaps[0]
                return Verdict(mode, False, f"without its blimp helpers: gap R{rnd}: {need_} ({how})")
    share = min(_share(r, strat, kind, mode) for r in runs[:len(waters) * 2])
    plan_done = runs[0]["plan_done"]
    need = MIN_RATIO[fam if fam in MIN_RATIO else "hard"]
    if mode == "apopalypse":
        need = MIN_RATIO["hard"]     # random rounds to 100, no breaks: Hard's bar
    # (the Impoppable family, one life to round 100, takes Hard's bar too)
    v = Verdict(mode, True, "ok", ratio, share, tuple(helper_kinds), plan_done)
    if ratio is not None and ratio < need:
        v.ok, v.why = False, f"blimp damage {ratio:.2f} < {need:.2f}"
    elif needs_own_damage(mode) and blimp_helpers:
        v.ok, v.why = False, "the executor had to buy blimp damage from other towers"
    elif share < MIN_SHARE:
        v.ok, v.why = False, f"{name(kind)} gets only {share:.0%} of the cash: no XP game for it"
    return v


def base_success(v, carry=True):
    """Conservative prior for a mode the simulation passed: the difficulty's
    ceiling (below the hand-tested strategies), less HELPER_PENALTY per other
    tower kind the executor had to buy, less SUPPORT_PENALTY for a support
    build, and less when blimp damage is short of the executor's 'enough' bar."""
    fam = mode_family(v.mode)
    p = BASE_CEILING.get(fam, BASE_CEILING["impoppable"])
    p -= HELPER_PENALTY * len(v.helpers)
    if not carry:
        p -= SUPPORT_PENALTY
    if v.ratio is not None and v.ratio < S.Executor.RAMP_OK:
        p -= 0.05 * (1.0 - v.ratio / S.Executor.RAMP_OK)
    return round(max(BASE_FLOOR, min(BASE_CEILING.get(fam, BASE_CEILING["impoppable"]), p)), 2)


def defence_only_strategy(b, strat):
    """The build without the tower's own steps (the defence alone), for towers
    the bot cannot aim: their damage may never land, so the defence must hold."""
    kind = b.kind
    kinds = {st.get("id"): st.get("kind") for _, st in S._all_steps(strat) if st.get("do") == "place"}

    def keep(st):
        return (st.get("kind") or kinds.get(st.get("id"))) != kind
    out = dict(strat, id=strat["id"] + "_defence_only")
    for key in ("plan", "fill", "panic"):
        out[key] = [st for st in strat.get(key) or [] if keep(st)]
    out["answers"] = {t: [st for st in v if keep(st)] for t, v in (strat.get("answers") or {}).items()}
    return out


# ---------------------------------------------------------------------------
# Generating one tower
# ---------------------------------------------------------------------------

@dataclass
class Result:
    kind: str
    carry: bool
    build: Build
    strat: dict
    verdicts: list
    modes: list
    base: dict


def _assemble(kind, modes, extra=0, carry=None, hero=None):
    """The build with helpers for the strength threats of these modes' rounds.
    extra: the Hard reinforcement's added copies; carry: a solo build (True)
    or a defence plus the tower (False), default is_carry; hero: the hero to
    name, default pick_hero (see generate for when these are overridden)."""
    carry = is_carry(kind) if carry is None else carry
    b = build_carry(kind, extra) if carry else build_support(kind, extra)
    b.extra, b.carry = extra, carry
    restricted = [m for m in modes if m in S.MODE_TOWER_FILTER]
    allowed = {S.MODE_TOWER_FILTER[m] for m in restricted} if restricted else None
    last = max(S.MODE_RULES[m]["end_round"] for m in modes)
    core = {kind} | ({b.lines["defence"].kind} if "defence" in b.lines else set())
    notes = _answers(b, core, allowed, last, water_only=placement(kind) == "water")
    if notes:
        b.notes.append("Answers, tried in order when a threat is due and the defence has none: the "
                       "tower's own path first, then a helper (for accounts whose own tiers are "
                       "still locked): " + "; ".join(notes))
    b.hero = hero or pick_hero(b)
    if b.hero != HERO:
        b.notes.append(f"Hero {b.hero}: of every land hero the damage model rates, the build rates best "
                       f"with it on {HERO_MAP} ({HERO_MODE}); see gen_builds.pick_hero.")
    return b


def _judge_all(kind, modes, extra=0, carry=None, hero=None):
    b = _assemble(kind, modes, extra, carry, hero)
    strat = b.strategy(modes)
    defence = defence_only_strategy(b, strat) if needs_aim(kind) else None
    verdicts = [judge(b, strat, m, defence) for m in modes]
    # A category-only mode is its difficulty's standard mode with fewer towers
    # to fall back on: a build that fails the standard mode passing it would
    # be a fluke of the simulation's cash flow, so it needs both.
    ok = {v.mode for v in verdicts if v.ok}
    for v in verdicts:
        base_mode = mode_family(v.mode)
        if v.ok and v.mode in S.MODE_TOWER_FILTER and base_mode in modes and base_mode not in ok:
            v.ok, v.why = False, f"{base_mode} itself does not pass"
    return b, verdicts


# Choices the merit rules make that the threat simulation may not agree
# with, screened before the full run (generate):
#   * the hero: pick_hero rates heroes in the damage model, which counts
#     their damage; the threat simulation counts only their price, so a dear
#     hero (Churchill $2,000) can leave a build short of blimp damage at
#     round 40 (Tack: every mode lost in the trial of 2026-11-12);
#   * carry or support: a tower whose only blimp damage figure is derived
#     from the game model (counters.json model_towers: Ice, Glue, Mermonkey,
#     Desperado, Skywarden) becomes a carry, and a weak solo build of it can
#     lose modes its defence-plus-tower build passed (Ice: Easy only).
# The merit choice stays unless the other one is stronger on the screen.
SCREEN_MODES = ("easy", "medium", "hard")


def carry_from_model(kind):
    """Does is_carry rest on a blimp figure derived from the game model
    (no hand blimp_dps row for the tower)?"""
    return (is_carry(kind) and kind not in (TH.counters().get("blimp_dps") or {})
            and bool(TH.model_facts(kind).get("blimp_dps")))


def screen(kind, modes, carry=None, hero=None):
    """(modes passed, sum of their blimp ratios) of a build variant over
    `modes`: what generate compares variants by."""
    b = _assemble(kind, modes, carry=carry, hero=hero)
    strat = b.strategy(modes)
    defence = defence_only_strategy(b, strat) if needs_aim(kind) else None
    verdicts = [judge(b, strat, m, defence) for m in modes]
    passed = [v for v in verdicts if v.ok]
    return len(passed), round(sum(min(v.ratio, 10.0) for v in passed if v.ratio is not None), 3), b


def choose_variant(kind, candidates):
    """(carry, hero) for the build: the merit choices (is_carry, pick_hero)
    unless a variant with the other carry rule or the default hero (HERO)
    is stronger on SCREEN_MODES. None means the default."""
    modes = [m for m in SCREEN_MODES if m in candidates]
    passed, ratios, b = screen(kind, modes)
    best_score, best = (passed, ratios), (None, None)
    picked = b.hero
    variants = []
    if picked != HERO:
        variants.append((None, HERO))
    if carry_from_model(kind):
        variants.append((False, None))
        if picked != HERO:
            variants.append((False, HERO))
    for carry, hero in variants:
        passed, ratios, _ = screen(kind, modes, carry, hero)
        if (passed, ratios) > best_score:
            best_score, best = (passed, ratios), (carry, hero)
    return best


def _resolve(kind, candidates, extra=0, carry=None, hero=None):
    """Simulate every candidate mode and keep the ones that pass; the build
    is then made again for the kept modes only (no helpers for threats that
    come after their last round) and checked again, until it is stable.
    Returns (build, kept modes, {mode: verdict} kept, {mode: verdict} dropped)."""
    b, verdicts = _judge_all(kind, candidates, extra, carry, hero)
    dropped = {v.mode: v for v in verdicts if not v.ok}
    kept = [v.mode for v in verdicts if v.ok]
    kept_v = {}
    while kept:
        b, again = _judge_all(kind, kept, extra, carry, hero)
        newly = [v for v in again if not v.ok]
        dropped.update({v.mode: v for v in newly})
        kept_v = {v.mode: v for v in again if v.ok}
        kept = [m for m in kept if m in kept_v]
        if not newly:
            break
    if not kept:
        b = _assemble(kind, candidates, extra, carry, hero)
    return b, kept, kept_v, dropped


# Hard reinforcement. Most solo builds failed Hard on their own blimp damage
# (docs/builds.md: only ace, bomb, heli and sniper had a Hard build), because
# the plan is sized for a Medium game. A Hard game pays for more: when Hard
# fails on blimp damage, the build is made again with up to HARD_EXTRA_MAX
# more copies of its blimp damage (build_carry / build_support `extra`), and
# the first that passes Hard is kept - if it also keeps every mode the plain
# build passed. docs/tower_exclusions_audit.md item 9.
HARD_EXTRA_MAX = 4
BLIMP_SHORT = ("blimp damage", "the executor had to buy blimp damage", "without its blimp helpers")


def _hard_extra(kind, candidates, carry=None, hero=None):
    """The fewest extra copies (1..HARD_EXTRA_MAX) with which the build
    passes Hard, or 0 when none does or Hard fails for another reason."""
    for extra in range(1, HARD_EXTRA_MAX + 1):
        b = _assemble(kind, candidates, extra, carry, hero)
        strat = b.strategy(candidates)
        v = judge(b, strat, "hard", defence_only_strategy(b, strat) if needs_aim(kind) else None)
        if v.ok:
            return extra
        if not v.why.startswith(BLIMP_SHORT):
            return 0          # a gap or a share more copies cannot fix
    return 0


def generate(kind):
    """Build, simulate every candidate mode and keep the ones that pass
    (_resolve); when Hard fails on blimp damage, try the Hard reinforcement
    (_hard_extra) and keep it if it passes Hard without losing a mode."""
    candidates = candidate_modes(kind)
    carry, hero = choose_variant(kind, candidates)
    b, kept, kept_v, dropped = _resolve(kind, candidates, 0, carry, hero)
    if "hard" in candidates and "hard" not in kept and dropped["hard"].why.startswith(BLIMP_SHORT):
        extra = _hard_extra(kind, candidates, carry, hero)
        if extra:
            hb, hkept, hkept_v, hdropped = _resolve(kind, candidates, extra, carry, hero)
            if "hard" in hkept and set(kept) <= set(hkept):
                b, kept, kept_v, dropped = hb, hkept, hkept_v, hdropped
                b.notes.append(f"Hard reinforcement: {extra} more cop{'y' if extra == 1 else 'ies'} of the "
                               f"build's blimp damage than a Medium game needs, so Hard passes on the "
                               f"build's own damage.")
    final = [dropped[m] if m in dropped else kept_v[m] for m in candidates]
    base = {m: base_success(kept_v[m], b.carry) for m in kept}
    return Result(kind, b.carry, b, b.strategy(kept, base), final, kept, base)


# ---------------------------------------------------------------------------
# YAML output (with the reasoning as comments)
# ---------------------------------------------------------------------------

_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]-[0-9]-[0-9]")


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items()) + "}"
    s = str(v)
    return s if _PLAIN.fullmatch(s) else json.dumps(s)


def _steps_yaml(steps, indent="  "):
    lines = []
    for st, why in steps:
        line = f"{indent}- {_fmt(st)}"
        if why:
            line += f"   # {why}"
        lines.append(line)
    return lines


def _wrap(text, width=76, prefix="# "):
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            out.append(prefix + cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(prefix + cur)
    return out


EXCLUSIONS = ROOT / "data" / "generated_exclusions.json"


def exclusions(kind):
    """{"maps": [...], "why": [...]} for the solo build of `kind`: maps a
    live loss took the generated build off (data/generated_exclusions.json,
    written by hand after a loss's diagnosis). The simulation cannot see
    them - Workshop's MOABs drop down a chute out of a solo tower's reach -
    and a file written here is overwritten on every run, so they live
    outside the generated files and are copied into each as
    planner.excluded_maps."""
    try:
        data = json.loads(EXCLUSIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get(kind) or {}


def to_yaml(r):
    b, kind = r.build, r.kind
    excluded = exclusions(kind)
    prices = P.load_tower_xp_prices(str(P.TOWER_XP_FILE)).get(kind)
    par = f" (paragon {prices.paragon}: {prices.paragon_xp:,} XP on top of all 15 upgrades)" \
        if prices and prices.paragon else ""
    lines = ["# GENERATED by tools/gen_builds.py from the game's own data - do not edit by hand:",
             "# change the generator and run `python tools/gen_builds.py` (see docs/builds.md).",
             "#"]
    lines += _wrap(f"Solo XP build for the {name(kind)}{par}. Tower XP is split between tower types by "
                   f"the cash invested in them, so this game puts most of its money into "
                   f"{name(kind)}s.")
    lines.append("#")
    for n in b.notes:
        lines += _wrap(n.strip(), prefix="#   " if n.startswith("  ") else "# ")
    if b.maps is not None:
        lines += _wrap(f"Water tower: only maps where it reaches at least {P.FULL_FIT:.0%} of the "
                       f"track (data/map_fit.json).")
    lines.append("#")
    lines.append("# Modes - offline simulation at real prices and base income "
                 "(tools/simulate_threats.py):")
    for v in r.verdicts:
        if v.ok:
            ratio = f"min blimp ratio {v.ratio:.2f}" if v.ratio is not None else "no blimp rounds"
            helpers = f", answers bought: {', '.join(v.helpers)}" if v.helpers else ""
            lines += _wrap(f"{v.mode}: kept - no gaps, {ratio}, {name(kind)} share of the cash "
                           f"{v.share:.0%}{helpers}", prefix="#   ")
        else:
            lines += _wrap(f"{v.mode}: dropped - {v.why}", prefix="#   ")
    lines += _wrap("base_success: an untested generated build, so each mode starts below every "
                   "hand-tested strategy of its difficulty, minus a little for every other tower the "
                   "simulation had to buy"
                   + ("" if r.carry else ", for the deliberately small defence")
                   + " and for blimp damage short of the executor's bar; the planner calibrates it "
                   "from real games.")
    d = r.strat
    lines.append(f"id: {d['id']}")
    lines.append(f"xp_target: {kind}   # the tower this build levels up")
    lines.append(f"hero: {d['hero']}   # equipped if owned, else a fallback (strategy.hero_for)")
    lines.append(f"modes: {_fmt(d['modes'])}")
    if d.get("uses_income"):
        lines.append("uses_income: true   # never CHIMPS")
    if d.get("generator"):
        lines.append(f"generator: {_fmt(d['generator'])}   # Hard reinforcement (gen_builds.generate)")
    lines.append("planner:")
    lines.append(f"  towers: {_fmt(d['planner']['towers'])}   # the crosspaths the build needs to be safe")
    lines.append(f"  base_success: {_fmt(d['planner']['base_success'])}")
    if "maps" in d["planner"]:
        lines.append(f"  maps: {_fmt(d['planner']['maps'])}")
    for note in excluded.get("why") or ():
        lines += _wrap(note, prefix="  # ")
    if excluded.get("maps"):
        lines.append(f"  excluded_maps: {_fmt(excluded['maps'])}")
    lines.append("plan:")
    lines += _steps_yaml(b.plan)
    lines.append("fill:")
    lines += _steps_yaml(b.fill)
    lines.append("panic:")
    lines += _steps_yaml(b.panic)
    if b.answers:
        lines.append("answers:")
        for threat, steps in b.answers.items():
            lines.append(f"  {threat}:")
            lines += _steps_yaml(steps, indent="    ")
    return "\n".join(lines) + "\n"


def write_atomic(path, text):
    """Write via a temporary file and rename: the bot reloads strategies
    between games and must never read a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# docs/builds.md table
# ---------------------------------------------------------------------------

def plan_share(strat, kind):
    """Share of the plan's cash that goes into the tower (strategy.invested_cash:
    what the planner reads as the game's XP split)."""
    inv = S.invested_cash(strat) or {}
    total = sum(inv.values())
    return inv.get(kind, 0) / total if total else 0.0


def doc_table(results):
    rows = ["| Tower | Build | Plan share | Simulated share | Modes (base_success) | Why not the others |",
            "|---|---|---|---|---|---|"]
    for r in results:
        b = r.build
        main = b.lines.get("main")
        comp = b.lines.get("comp")
        if r.carry:
            build = f"solo: {cross(main.work)} {top_upgrade(r.kind, main.work)}"
            if comp:
                build += f" + {cross(comp.work)} {top_upgrade(r.kind, comp.work)}"
            extra = [s for s in b.support]
            if extra:
                build += " (+ " + ", ".join("radar village" if s == "rv" else "exit spike" for s in extra) + ")"
        else:
            d = b.lines["defence"]
            build = (f"defence {name(d.kind)} {cross(d.work)}, then {name(r.kind)} "
                     f"{cross(main.work)} {top_upgrade(r.kind, main.work)}")
        modes = ", ".join(f"{m} {r.base[m]:.2f}" for m in r.modes) or "none"
        dropped = [v for v in r.verdicts if not v.ok]
        why = "; ".join(f"{v.mode}: {v.why}" for v in dropped) or "all candidate modes pass"
        shares = [v.share for v in r.verdicts if v.ok and v.share is not None]
        sim = f"{min(shares):.0%}-{max(shares):.0%}" if shares else "-"
        rows.append(f"| {name(r.kind)} | {build} | {plan_share(r.strat, r.kind):.0%} | {sim} | {modes} | {why} |")
    return "\n".join(rows)


def update_doc(results):
    """Rewrite the generated table between the markers of docs/builds.md."""
    if not DOC.exists():
        return False
    text = DOC.read_text(encoding="utf-8")
    if DOC_START not in text or DOC_END not in text:
        return False
    head, rest = text.split(DOC_START, 1)
    _, tail = rest.split(DOC_END, 1)
    write_atomic(DOC, head + DOC_START + "\n" + doc_table(results) + "\n" + DOC_END + tail)
    return True


# ---------------------------------------------------------------------------

def report(r):
    b = r.build
    kind = r.kind
    main = b.lines["main"]
    comp = b.lines.get("comp")
    head = f"{kind:14s} {'carry' if r.carry else 'support':8s} main {cross(main.work)}"
    if comp:
        head += f" comp {cross(comp.work)}"
    if not r.carry:
        head += f" defence {b.lines['defence'].kind} {cross(b.lines['defence'].work)}"
    print(head)
    for v in r.verdicts:
        mark = "ok  " if v.ok else "drop"
        extra = ""
        if v.ok:
            extra = (f" ratio {v.ratio if v.ratio is None else round(v.ratio, 2)} share {v.share:.0%} "
                     f"base {r.base[v.mode]} plan {v.plan_done} helpers {list(v.helpers)}")
        print(f"    {mark} {v.mode:13s} {v.why}{extra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kinds", nargs="*", help="tower ids (default: every tower)")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR, format="%(name)s: %(message)s")
    kinds = a.kinds or list(T.TOWERS)
    unknown = [k for k in kinds if k not in T.TOWERS]
    if unknown:
        ap.error(f"unknown tower(s): {unknown}")
    results = []
    for kind in kinds:
        r = generate(kind)
        report(r)
        results.append(r)
        if not r.modes:
            print(f"    no safe mode for {kind}: written with `modes: []` (never planned)")
        if not a.check:
            write_atomic(OUT_DIR / f"solo_{kind}.yaml", to_yaml(r))
    if not a.check and not a.kinds:
        update_doc(results)


if __name__ == "__main__":
    main()
