"""Does a set of towers pop a round? An analytic estimate from the game's own numbers.

This is the evaluator behind tools/optimize_builds.py. It answers, for a map,
a mode and a defence (tower kind + crosspath + world position each):

    * which bloons of round r leak, and how many lives that costs;
    * the safety margin: by how much the defence could be weaker and still
      pop the whole round (2.0 = it would hold at half strength);
    * when the round's last bloon is popped (for game length / XP per hour).

It is an estimate, not a replay of the game. docs/optimizer.md explains the
model, its assumptions and how it was calibrated against the bot's own games.

Where the numbers come from
---------------------------
    data/game_model/attacks.json   attack rate, projectiles, pierce, damage,
                                   damage type, bonuses, sub-projectiles and
                                   sub-towers of every tower crosspath
                                   (tools/export_attacks.py); also each mode's
                                   bloon speed multiplier (Medium 1.1, Hard 1.25)
    data/game_model/bloons.json    every bloon's health, speed, children,
                                   immunities, tags, leak damage
    data/game_data/round_sets.json every round's bloon groups and spawn times
    data/map_geometry/<map>.json   the bloon paths in world units (mapgeom)

The model in short
------------------
Bloons travel each route of the map (mapgeom paths joined by the map's
splitters) as "lots": a slice of one spawn group, one layer at a time.
Every tower is a "station": the stretch of route inside its range is its
zone, so a bloon of speed v spends (covered length / v) seconds there.
A station is a single server with deadlines: a lot's job is released
when its bloons reach the zone and must be done before they leave it, and
the station always works on the job that leaves first (the game's default
"first" targeting; single-target towers - snipers - are planned with
"strong" targeting and work on MOAB-class bloons first). A job's "work" is
the layer's health over the HP per second the station deals to it: attack
rate x projectiles x hits per projectile (pierce, limited by how many
bloons are packed close enough) x damage per hit (with the game's bonuses
vs MOABs / ceramics / fortified, zero if the damage type cannot pop it or
the tower cannot see camo). When a layer pops, its children appear where it
popped as new jobs, with the damage that overflowed (the game passes a
hit's excess damage on to the children). Small layers (all but ceramics
and MOAB-class) are worked as one job with everything inside them, which
keeps a round under ~10 ms. Layers a station cannot pop, and whatever it
does not finish in time, go on to the next station along the route; what
is left after the last station leaks and costs lives (the game's leak
damage, children included).

Deliberate simplifications (each is on the safe side unless noted):
    * heroes, abilities, Monkey Knowledge, alchemist brews and
      slows/freezes/knockback are not counted (they only help);
    * towers aimed by hand (Mortar's target point, Dartling's cursor) do
      nothing (the bot cannot aim them);
    * overlapping zones are worked one after another along the route
      (total capacity is right, who pops first is approximate);
    * projectiles never miss and towers never waste shots on the same
      bloon (optimistic: calibration absorbs it);
    * regrowing bloons do not regrow (optimistic, small: regrow is slow);
    * a map whose spawn alternates between routes by round is played on
      every alternative and the worst counts.
The model is used as is (TOWER_EFFICIENCY 1.0); the bot's logged games say
how far its margins can be trusted (docs/optimizer.md, "Calibration"),
which is how tools/optimize_builds.py chose its SAFETY_MARGIN.
"""
from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GAME_MODEL = ROOT / "data" / "game_model"
ROUND_SETS = ROOT / "data" / "game_data" / "round_sets.json"
ROUNDS_FILE = ROOT / "data" / "rounds.json"

# --- calibration (see docs/optimizer.md, "Calibration") ---------------------
# Scales every tower's modelled output. Left at 1.0: replaying the bot's
# 2,104 logged rounds (2026-10-21/22, tools/optimize_builds.py --calibrate)
# showed the model as is to be on the safe side (rounds it rated below 1.0
# lost lives 5.4% of the time, 2.0 and above 0.5%, 6.0 and above never), so
# the safety bar is set in the optimizer (SAFETY_MARGIN) rather than by
# shrinking towers.
TOWER_EFFICIENCY = 1.0

# --- modelling constants (assumptions, documented in docs/optimizer.md) -----
LOTS_PER_GROUP = 6          # time slices a spawn group is split into
TRACK_STEP = 2.0            # world units between sampled path points
CONTACTS_PER_CARRIER = 2.0  # bloons a carrier projectile touches in a crowd (spawn-on-contact chains)
TRAVEL_OVERLAP = 0.35       # share of a flying projectile's path that runs along the lane
MAX_SUBTOWERS = 6           # sub-towers alive at once (sentries, ...) when the model gives no cap
AIR_PATTERN_EFFICIENCY = 0.4  # share of a circling plane's radial darts that cross the lane
LEAK_LIVES_EPS = 0.5        # fluid model: less than half a life lost counts as no leak
CARRIED_STOCK_SECONDS = 30.0  # spikes that outlive the round: production of this long is still lying there
SMALL_LAYER_HP = 4.0        # layers with at most this health (all but ceramics and MOAB-class) are worked
                            # together with their children as one job (speed; see _Rates.subtree)

# Each bot mode is a game difficulty plus mode Mods (ModeType.GetModesForDifficulty:
# Impoppable and CHIMPS are played on Hard). Rules are read from these Mod
# assets in attacks.json "modes" (speed, health, cash).
MODE_MODS = {
    "easy": ["Easy"], "primary_only": ["Easy", "PrimaryOnly"], "deflation": ["Easy", "Deflation"],
    "medium": ["Medium"], "military_only": ["Medium", "MilitaryOnly"], "reverse": ["Medium", "Reverse"],
    "apopalypse": ["Medium", "Apopalypse"],
    "hard": ["Hard"], "magic_only": ["Hard", "MagicOnly"], "double_hp": ["Hard", "DoubleMoabHealth"],
    "half_cash": ["Hard", "HalfCash"], "abr": ["Hard", "AlternateBloonsRounds"],
    "impoppable": ["Hard", "Impoppable"], "chimps": ["Hard", "Impoppable", "Clicks"],
}


# ===========================================================================
# Data files
# ===========================================================================

@lru_cache(maxsize=None)
def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def attacks():
    """data/game_model/attacks.json ({} when it was never exported)."""
    return _json(str(GAME_MODEL / "attacks.json"))


def available():
    """True when the attack export and the bloon table exist."""
    return bool(attacks().get("towers")) and bool(_json(str(GAME_MODEL / "bloons.json")))


def tiers_code(tiers):
    """(0, 2, 4) / [0, 2, 4] / '0-2-4' -> '024' (the model's crosspath key)."""
    if isinstance(tiers, str):
        tiers = [int(x) for x in tiers.replace("-", "")]
    return "".join(str(int(t)) for t in tiers)


def crosspath(kind, tiers):
    """The exported model of one tower crosspath, or None."""
    return ((attacks().get("towers") or {}).get(kind) or {}).get("crosspaths", {}).get(tiers_code(tiers))


def mode_rules(mode):
    """Speed / health / cash rules of a bot mode, combined from its Mods.

    speed:   bloon speed multiplier (product of GlobalSpeedModModel values)
    moab_hp: health multiplier for MOAB-class bloons (Double HP MOABs)
    round_health: [(round, bloon id, multiplier)] one-round changes (Easy R40 MOAB)
    cash:    income multiplier (Half Cash 0.5, Deflation 0)
    start_cash, lives, start_round, end_round, cost_multiplier"""
    mods = (attacks().get("modes") or {})
    out = {"speed": 1.0, "moab_hp": 1.0, "round_health": [], "cash": 1.0, "start_cash": 650.0,
           "lives": None, "start_round": 1, "end_round": None, "cost_multiplier": 1.0}
    for name in MODE_MODS.get(mode, ["Medium"]):
        m = mods.get(name) or {}
        out["speed"] *= m.get("speed_multiplier", 1.0)
        out["moab_hp"] *= (m.get("health_multipliers") or {}).get("Moabs", 1.0)
        out["round_health"] += [(h["round"], h["bloon"], h["multiplier"]) for h in m.get("round_health") or []]
        out["cash"] *= m.get("cash_multiplier", 1.0)
        sc = m.get("starting_cash")
        if sc:
            out["start_cash"] = sc["changeBase"] if sc.get("changeBase") else out["start_cash"] * (sc.get("multiplier") or 1.0)
        for key, src in (("lives", "lives"), ("start_round", "start_round"), ("end_round", "end_round")):
            if m.get(src) is not None:
                out[key] = m[src]
        for c in m.get("cost_multipliers") or []:
            out["cost_multiplier"] += c - 1.0
    return out


# ===========================================================================
# Bloons: the layer tree of every bloon id
# ===========================================================================

@dataclass(frozen=True)
class Layer:
    """One bloon type (one node of a bloon's layer tree)."""
    id: str
    hp: float
    speed: float
    immune: frozenset      # bloon properties: lead, black, white, purple
    camo: bool
    moab: bool             # MOAB-class (cannot be frozen, takes MOAB bonuses)
    tags: frozenset        # the game's tags: "Ceramic", "Moabs", "Fortified", ...
    children: tuple        # ((child id, count), ...)
    leak: float            # lives lost if this bloon (and its children) leak
    radius: float


@lru_cache(maxsize=None)
def bloon_table():
    return _json(str(GAME_MODEL / "bloons.json"))


@lru_cache(maxsize=None)
def layer(bloon_id, moab_hp=1.0):
    """The Layer of a game bloon id ("CeramicRegrowCamo"); MOAB-class health
    scaled by moab_hp (Double HP MOABs, freeplay ramps)."""
    b = bloon_table()[bloon_id]
    moab = bool(b.get("moab_class"))
    children = tuple(sorted((b.get("children") or {}).items()))
    leak = float(b.get("leak_damage") or 0.0) + sum(n * layer(c, moab_hp).leak for c, n in children)
    return Layer(id=bloon_id, hp=float(b["health"]) * (moab_hp if moab else 1.0), speed=float(b["speed"]),
                 immune=frozenset(b.get("immune") or ()), camo=bool(b.get("camo")), moab=moab,
                 tags=frozenset((b.get("tags") or []) + [bloon_id, b.get("base", "").capitalize()]),
                 children=children, leak=leak, radius=float(b.get("radius") or 8.0))


@lru_cache(maxsize=None)
def subtree(bloon_id, moab_hp=1.0):
    """[(Layer, count per top bloon, depth)] for the bloon and all its children."""
    out, stack = [], [(bloon_id, 1.0, 0)]
    while stack:
        bid, n, depth = stack.pop()
        lay = layer(bid, moab_hp)
        out.append((lay, n, depth))
        for child, k in lay.children:
            stack.append((child, n * k, depth + 1))
    return tuple(out)


@lru_cache(maxsize=None)
def rbe(bloon_id, moab_hp=1.0):
    """Total health of the bloon and everything inside it."""
    return sum(lay.hp * n for lay, n, _ in subtree(bloon_id, moab_hp))


# ===========================================================================
# Towers: flattening the attack tree into damage sources
# ===========================================================================

@dataclass
class Source:
    """One kind of projectile that does damage, with how often it comes.

    shots       projectiles per second when bloons are packed (crowd)
    shots_single  projectiles per second against one lone target (chains of
                spawn-on-contact fire less when there is little to touch)
    reach       track length (world units) one projectile can sweep: how
                many bloons it can meet; 0 = only its own target; math.inf =
                it waits on the track and meets everything that passes
    zone_wide   a blast centred on the tower that covers its whole range
                (Ice Monkey): it meets every bloon in the zone
    single_hits hits one projectile can land on the same bloon (lingering
                projectiles that re-hit), at least 1
    placement   "aimed" (fired at targets in range), "track" (laid on the
                track and waiting: spikes), "global" (anywhere on the
                map), "air" (from a plane circling the tower)
    radial      fired all around rather than at a target (tacks, a plane's
                darts): only the share of directions that cross the lane hits
    travel      how far a radial projectile flies (for that share)
    bank        seconds of production a "track" source can stockpile
    lasts_rounds  its projectiles outlive the round (Long Life Spikes): the
                stockpile carries over into the next round
    """
    name: str
    shots: float
    shots_single: float
    pierce: float
    damage: float
    immune: frozenset
    bonus: dict
    camo: bool
    only_tags: frozenset
    excluded_tags: frozenset
    reach: float
    zone_wide: bool = False
    single_hits: float = 1.0
    placement: str = "aimed"
    radial: bool = False
    travel: float = 0.0
    range: float = 0.0
    bank: float = 0.0
    lasts_rounds: bool = False
    dot_total: float = 0.0     # damage over time a hit applies (total)
    dot_rate: float = 0.0      # ... per second on one bloon

    def can_hit(self, lay):
        """Can this source damage this layer at all?"""
        if lay.camo and not self.camo:
            return False
        if self.only_tags and not (self.only_tags & lay.tags):
            return False
        if self.excluded_tags & lay.tags:
            return False
        return not (self.immune & lay.immune)

    def damage_vs(self, lay):
        """Damage of one hit on this layer, with the game's tag bonuses."""
        d = self.damage
        for key, b in self.bonus.items():
            if key in lay.tags:
                d = d * b["mult"] + b["add"]
        return d


@dataclass
class Profile:
    """Everything the evaluator needs to know about one tower crosspath."""
    kind: str
    tiers: tuple
    range: float
    is_global: bool
    sources: list
    aim_bound: bool = False          # needs a hand-aimed target (does nothing for the bot)
    buffs: list = field(default_factory=list)
    income: float = 0.0              # cash per round it makes itself
    pattern_radius: float = 0.0      # a plane's flight circle (Monkey Ace)


def _immune_set(entry):
    return frozenset(x for x in (entry or {}).get("immune", []) if x in ("lead", "black", "white", "purple"))


def _reach_of(p, placement, attack_range):
    """Track length one projectile sweeps (see Source.reach): its own
    diameter plus a bloon's (8 units radius) on each side, plus a share of
    the distance it flies (TRAVEL_OVERLAP: darts cross the lane at an angle),
    counting at most twice the attack's range of flight (beyond that it is
    past the bloons it was fired at; boomerangs live long but loop back)."""
    if p.get("target_only"):
        return 0.0                       # hits its target only (sniper bullets)
    if placement == "track":
        return math.inf                  # waits on the track: every passing bloon meets it
    radius = p.get("radius", 0.0)
    travel = (p.get("speed") or 0.0) * (p.get("lifespan") or 0.0)
    if attack_range and attack_range < 1000.0:
        travel = min(travel, 2.0 * attack_range)
    return 2.0 * (radius + 8.0) + TRAVEL_OVERLAP * travel


def _zone_wide(p, attack_range):
    """A stationary blast as wide as the tower's range (Ice Monkey's freeze)."""
    return p.get("motion") in ("static", "instant") and attack_range > 0 and p.get("radius", 0.0) >= 0.8 * attack_range


def _single_hits(p):
    """Hits one projectile can land on one bloon: 1, or more for lingering
    projectiles that may hit again (ClearHitBloons / RefreshPierce)."""
    life = p.get("lifespan") or 0.0
    again = p.get("rehit_interval") or p.get("pierce_refresh")
    if again and life:
        return max(1.0, min(p.get("pierce", 1.0), life / max(again, 1e-3)))
    return 1.0


def _flatten_projectile(p, shots, shots_single, attack, camo_chain, placement, radial, travel, out, depth=0,
                        subtower_cap=MAX_SUBTOWERS):
    """Add the damage sources of projectile p (and what it spawns) to out."""
    if not p or depth > 8:
        return
    camo = camo_chain and p.get("camo", False)
    attack_range = attack.get("range", 0.0)
    if (p.get("damage") or p.get("dot")) and not p.get("hits_nothing"):
        # a damage source: direct damage, damage over time (corrosive glue,
        # burns), or both; a DoT-only projectile does 0 on the hit itself
        dot = p.get("dot") or {}
        ticks = math.floor((dot.get("lifespan") or 0.0) / max(dot.get("interval") or 1.0, 1e-3)) if dot else 0
        hit = p.get("damage") or {"amount": 0.0, "immune": dot.get("immune", [])}
        dot_tags = frozenset(dot.get("only_tags", []))
        out.append(Source(
            name=f"{attack.get('name')}>{p.get('name')}",
            shots=shots, shots_single=shots_single,
            pierce=max(1.0, p.get("pierce", 1.0)),
            damage=hit.get("amount", 0.0),
            immune=_immune_set(hit) & (_immune_set(dot) if dot else _immune_set(hit)),
            bonus=p.get("bonus") or {},
            camo=camo,
            only_tags=frozenset(p.get("only_tags", [])) | frozenset(attack.get("only_tags", []))
            | (dot_tags if not p.get("damage") else frozenset()),
            excluded_tags=frozenset(p.get("excluded_tags", [])) | frozenset(attack.get("excluded_tags", [])),
            reach=_reach_of(p, placement, attack_range),
            zone_wide=_zone_wide(p, attack_range),
            single_hits=_single_hits(p),
            placement=placement, radial=radial, travel=travel, range=attack_range,
            bank=(p.get("lifespan") or 0.0) if placement == "track" else 0.0,
            lasts_rounds=bool(p.get("lasts_rounds")),
            dot_total=dot.get("amount", 0.0) * ticks if dot else 0.0,
            dot_rate=(dot.get("amount", 0.0) / max(dot.get("interval") or 1.0, 1e-3)) if dot else 0.0,
        ))
    pierce = max(1.0, p.get("pierce", 1.0))
    contacts = min(pierce, CONTACTS_PER_CARRIER)
    contacts_single = min(pierce, _single_hits(p))
    life = p.get("lifespan") or 0.0
    for s in p.get("spawn", []):
        n = s.get("count", 1.0)
        sub = s.get("projectile")
        on = s.get("on")
        if on == "contact":
            k, k1 = contacts * n * s.get("chance", 1.0), contacts_single * n * s.get("chance", 1.0)
        elif on == "interval":
            k = k1 = n * (life / s["every"] if life and s.get("every") else 1.0)
        elif on == "pierce":
            step = s.get("pierce_step") or 1.0
            k = n * min(s.get("max_times", 1e6), pierce / step)
            k1 = n * min(s.get("max_times", 1e6), contacts_single / step)
        elif on == "lightning":
            # a lightning bolt jumps on to `count` more targets: more of the same projectile
            k = k1 = n
            sub = dict(p, spawn=[s2 for s2 in p.get("spawn", []) if s2.get("on") != "lightning"])
        else:                                        # exhaust, expire, blocker: once per projectile
            k = k1 = n
        _flatten_projectile(sub, shots * k, shots_single * k1, attack, camo, placement, radial, travel, out, depth + 1)
    for t in p.get("subtowers", []):
        # sub-towers made by this projectile (an Engineer's sentries): as many
        # stand at once as are made during one lifespan, up to the cap
        lifespan = t.get("lifespan")
        alive = min(subtower_cap, shots * lifespan) if lifespan else min(subtower_cap, max(1.0, shots * 30.0))
        alive *= t.get("share", 1.0)         # one of several sentry types per spawn
        for a in t.get("attacks", []):
            _flatten_attack(a, out, multiplier=alive, depth=depth + 1, parent_camo=camo_chain)


def _flatten_attack(a, out, multiplier=1.0, depth=0, parent_camo=True, follows=False):
    """Add an attack's damage sources (per weapon) to out.
    follows: the tower is a helicopter that flies to the bloons (global reach)."""
    targeting = a.get("targeting", "normal")
    if targeting in ("point", "cursor"):
        return
    if targeting in ("track", "random"):
        placement = "track"
        camo_chain = True                 # thrown onto the track: sees nothing, hits what passes
    elif a.get("air") and a.get("pattern_radius"):
        placement = "air"
        camo_chain = a.get("camo", False)
    elif follows or a.get("air") or a.get("range", 0.0) >= 1000.0:
        placement = "global"
        camo_chain = a.get("camo", False)
    else:
        placement = "aimed"
        camo_chain = a.get("camo", False)
    weapons = a.get("weapons", [])
    # a weapon fired by another (FireAlternateWeaponModel) shoots at that one's rate
    trigger_rate = {w["fires_weapon"]: w.get("rate", 1.0) for w in weapons if w.get("fires_weapon") is not None}
    for i, w in enumerate(weapons):
        rate = w.get("rate", 1.0)
        if w.get("triggered"):
            rate = trigger_rate.get(i, rate)
        rate = max(rate, w.get("rate_min", 0.0), 1e-3)
        shots = multiplier * w.get("count", 1.0) * w.get("burst", 1.0) / rate
        p = w.get("projectile")
        life = (p or {}).get("lifespan") or 0.0
        if w.get("projectile_limit") and life > 0:
            # only so many of its projectiles may exist at once
            shots = min(shots, multiplier * w["projectile_limit"] / life)
        cap = w.get("max_subtowers") or MAX_SUBTOWERS
        radial = w.get("count", 1.0) >= 3 and (p or {}).get("motion") in ("straight", "path") and placement != "track"
        travel = ((p or {}).get("speed") or 0.0) * ((p or {}).get("lifespan") or 0.0)
        if w.get("crit") and p and p.get("damage"):
            # one shot in `every` does crit damage instead: average it in
            c = w["crit"]
            extra = (c["damage"] - p["damage"]["amount"]) / max(c["every"], 1.0)
            p = dict(p, damage=dict(p["damage"], amount=p["damage"]["amount"] + max(0.0, extra)))
        _flatten_projectile(p, shots, shots, a, camo_chain and parent_camo, placement, radial, travel, out, depth,
                            subtower_cap=cap)
        if w.get("alternate"):
            alt = w["alternate"]
            k = alt.get("count", 1.0) / max(alt.get("every", 1.0), 1.0)
            _flatten_projectile(alt["projectile"], shots * k, shots * k, a, camo_chain, placement, radial, travel,
                                out, depth)
        if w.get("extra_projectile"):
            _flatten_projectile(w["extra_projectile"], shots, shots, a, camo_chain, placement, radial, travel,
                                out, depth)


@lru_cache(maxsize=None)
def profile(kind, tiers):
    """Profile of a tower crosspath (None when the game has no such model)."""
    entry = crosspath(kind, tiers)
    if entry is None:
        return None
    sources = []
    aim_bound = False
    follows = (entry.get("air_unit") or {}).get("movement") == "follows"
    for a in entry.get("attacks", []):
        if a.get("targeting") in ("point", "cursor") and any(
                (w.get("projectile") or {}) for w in a.get("weapons", [])):
            aim_bound = True
        _flatten_attack(a, sources, follows=follows)
    income = (entry.get("income") or {})
    pattern = max((a.get("pattern_radius") or 0.0 for a in entry.get("attacks", [])), default=0.0)
    return Profile(kind=kind, tiers=tuple(int(t) for t in tiers_code(tiers)), range=entry.get("range", 0.0),
                   is_global=bool(entry.get("global")), sources=sources, aim_bound=aim_bound and not sources,
                   buffs=entry.get("buffs", []),
                   income=income.get("per_round", 0.0) + income.get("bananas_per_round", 0.0),
                   pattern_radius=pattern)


# ===========================================================================
# Map geometry: where a tower's range meets the track
# ===========================================================================

@dataclass
class Zone:
    """The part of one path inside a tower's reach.
    entry: distance along the path (world units) where bloons first enter
    length: covered length (sum of all covered stretches)
    angular: share of directions from the tower that cross this path within
             the radial projectile travel (for tacks), 0..1"""
    entry: float
    length: float
    angular: float = 1.0


JOIN_DISTANCE = 6.0   # world units: a path starting this close to another's end continues it


def _is_boss_path(path, splitters):
    """Paths only boss bloons take (no bosses in the modes the bot plays)."""
    pid = path.get("id")
    if "boss" in str(path.get("name", "")).lower():
        return True
    for s in splitters:
        if s.get("overrideBossPath") == pid:
            return True
        tags = s.get("tagOnlyPath") or []
        for p, tag in zip(s.get("paths") or [], tags):
            if p == pid and tag == "Boss":
                return True
    return False


def map_routes(geom):
    """How bloons cross the map: (routes, scenarios).

    routes: [{"paths": [path ids in order], "moab": None | True | False}]
        a route is the sequence of paths one bloon follows from its spawn to
        the exit; "moab" True = only MOAB-class bloons take it (Quiet
        Street's MOAB lane), False = only non-MOAB bloons, None = all.
    scenarios: [[route indices]] - each round uses ONE scenario. Maps whose
        spawn alternates by round (Luminous Cove, Enchanted Glade, Last
        Resort: AlternateRoundSplitter) have one scenario per alternative;
        the evaluator plays every round in every scenario and keeps the
        worst. Within a scenario bloons are shared evenly by the routes
        open to their class (Party Parade's two lanes, Castle Revenge's
        four gates).

    Read from the map's own data (mapgeom / gamefiles splitters):
      * paths bloons can take without the player (mapgeom.bloon_paths),
        minus boss-only paths; on maps with splitters only the paths some
        splitter names (Castle Revenge keeps old unused gate paths);
      * a plain or toggle splitter named after a path X lists where bloons
        go at X's end (Ancient Portal's portal; spawn-type splitters that sit
        on a path's object are not continuations); a path that starts where
        another ends continues it, unless both join each other end to end
        (Quiet Street's two entrances share one road in opposite directions);
      * routes start at paths nothing leads into (else at the spawn
        splitter's paths); MoabOnlySplitter flags say which class goes where;
      * the branches of an AlternateRoundSplitter (or, failing that, of a
        ToggleSplitter that the map flips by itself) are alternatives."""
    from . import mapgeom as G
    mech = geom.get("mechanics") or {}
    splitters = mech.get("splitters") or []
    # a RuleSplitter sends whole rounds down other paths by a rule (Bloonarius
    # Prime: prime-numbered rounds take the whirl path), so its paths count
    # even while switched off at the start
    by_rule = {p for s in splitters if s.get("type") == "RuleSplitter" for p in s.get("paths") or []}
    usable = {p["id"] for p in G.bloon_paths(geom)} | by_rule
    for s in splitters:      # and the paths those continue into
        if s.get("type") == "Splitter" and any(p.get("name") == s.get("name") and p["id"] in by_rule
                                               for p in geom.get("paths", [])):
            usable |= set(s.get("paths") or [])
    paths = {p["id"]: p for p in geom.get("paths", []) if p["id"] in usable
             if len(p.get("points") or ()) >= 2 and not p.get("hidden") and not _is_boss_path(p, splitters)}
    referenced = {p for s in splitters for p in s.get("paths") or []}
    if referenced & set(paths):
        paths = {pid: p for pid, p in paths.items() if pid in referenced}
    if not paths:
        return [], []
    names = {p.get("name"): pid for pid, p in paths.items()}
    # continuations: named plain/toggle splitters first, then geometry
    follow = {pid: [] for pid in paths}
    for s in splitters:
        src = names.get(s.get("name"))
        if src is not None and s.get("type") in ("Splitter", "ToggleSplitter"):
            follow[src] += [p for p in s.get("paths") or [] if p in paths and p != src]
    ends = {pid: np.asarray(p["points"][-1][:2], float) for pid, p in paths.items()}
    starts_xy = {pid: np.asarray(p["points"][0][:2], float) for pid, p in paths.items()}
    # paths a spawn splitter offers side by side are alternatives, never one
    # after the other (Pat's Pond's two lanes start at opposite ends)
    siblings = [set(s.get("paths") or []) for s in splitters
                if s.get("type") in ("BloonTagOnlySplitter", "AlternateRoundSplitter", "RuleSplitter")]
    for a in paths:
        for b in paths:
            if a != b and np.linalg.norm(ends[a] - starts_xy[b]) <= JOIN_DISTANCE \
                    and np.linalg.norm(ends[b] - starts_xy[a]) > JOIN_DISTANCE and b not in follow[a] \
                    and not any(a in sib and b in sib for sib in siblings):
                follow[a].append(b)
    targets = {b for a in follow for b in follow[a]}
    roots = [pid for pid in paths if pid not in targets or pid in by_rule]
    if not roots:   # everything leads somewhere (a loop): start from the spawn splitter
        spawn = [s for s in splitters if s.get("name") not in names]
        roots = [p for s in spawn for p in s.get("paths") or [] if p in paths][:1] or [next(iter(paths))]
    # which class each path is for (MoabOnlySplitter flags)
    moab_flag = {}
    for s in splitters:
        flags = s.get("moabOnlyPath") or []
        if s.get("type") == "MoabOnlySplitter" and any(flags):
            for p, f in zip(s.get("paths") or [], flags):
                moab_flag[p] = bool(f)
    routes = []

    def walk(route):
        nxt = [p for p in follow[route[-1]] if p not in route]
        if not nxt:
            classes = {moab_flag[p] for p in route if p in moab_flag}
            routes.append({"paths": route, "moab": classes.pop() if len(classes) == 1 else None})
            return
        for p in nxt:
            walk(route + [p])

    for r in roots:
        walk([r])
    # alternating spawns / branches: one scenario per alternative
    alternating = [s for s in splitters if str(s.get("type", "")).startswith("AlternateRound")]
    alt_paths = [p for s in alternating for p in s.get("paths") or [] if p in paths]
    if not alt_paths:
        rules = [s for s in splitters if s.get("type") == "RuleSplitter"]
        alt_paths = [p for s in rules[:1] for p in s.get("paths") or [] if p in paths]
        if len(alt_paths) < 2:
            alt_paths = []
    if not alt_paths:
        toggles = [s for s in splitters if s.get("type") == "ToggleSplitter"]
        alt_paths = [p for s in toggles[:1] for p in s.get("paths") or [] if p in paths]
        if len(alt_paths) < 2:
            alt_paths = []
    if alt_paths:
        scenarios = []
        for p in dict.fromkeys(alt_paths):
            idx = [i for i, r in enumerate(routes) if p in r["paths"]]
            if idx:
                scenarios.append(idx)
        others = [i for i, r in enumerate(routes) if not any(p in r["paths"] for p in alt_paths)]
        scenarios = [sorted(set(s) | set(others)) for s in scenarios] or [list(range(len(routes)))]
    else:
        scenarios = [list(range(len(routes)))]
    return routes, scenarios


class Track:
    """A map's bloon routes in world units, sampled every TRACK_STEP units,
    and the conversions between screen fractions and world positions.

    Built from data/map_geometry (mapgeom.load) and map_routes(). Stretches
    where bloons cannot be hit (tunnels, gates: a path's "invulnerable"
    ranges) and the part outside the screen are left out of every zone.
    self.paths holds one entry per ROUTE (the name is kept from the first
    version of this class, when maps were one path each)."""

    def __init__(self, map_name, reverse=False):
        from . import mapgeom as G
        from .layout import LAYOUTS
        from .maplearn import GRID
        self.map_name = map_name
        self.reverse = reverse
        self.geom = G.load(map_name)
        if self.geom is None:
            raise ValueError(f"no geometry for map {map_name!r}")
        self.playfield = LAYOUTS["16:10"]["playfield"]
        self.proj = G.Projection(self.playfield)
        by_id = {p["id"]: p for p in self.geom.get("paths", [])}
        routes, self.scenarios = map_routes(self.geom)
        self.paths = []
        for route in routes:
            samples, hittable = [], []
            for pid in route["paths"]:
                path = by_id[pid]
                pts = np.asarray(path["points"], float)
                if pts.shape[1] < 3:
                    pts = np.hstack([pts, np.zeros((len(pts), 1))])
                hidden = path.get("invulnerable") or []
                for i in range(len(pts) - 1):
                    seg = pts[i + 1] - pts[i]
                    n = max(1, int(math.ceil(np.linalg.norm(seg[:2]) / TRACK_STEP)))
                    ok = not (G._in_ranges(i, hidden) or G._in_ranges(i + 1, hidden))
                    for k in range(n):
                        samples.append(pts[i] + seg * (k / n))
                        hittable.append(ok)
            samples.append(samples[-1])
            hittable.append(False)
            xyz = np.asarray(samples)
            # off-screen stretches cannot be hit either (a long first segment
            # that starts off screen is still hittable once it is on screen)
            cells = self.proj.to_cells(xyz)
            w, h = GRID
            on_screen = (cells[:, 0] >= 0) & (cells[:, 0] < w) & (cells[:, 1] >= 0) & (cells[:, 1] < h)
            hittable = np.asarray(hittable, bool) & on_screen
            step = np.linalg.norm(np.diff(xyz[:, :2], axis=0), axis=1)
            dist = np.concatenate([[0.0], np.cumsum(step)])
            self.paths.append({"xyz": xyz, "dist": dist, "length": float(dist[-1]),
                               "hittable": hittable, "moab": route["moab"],
                               "name": "+".join(str(by_id[p].get("name")) for p in route["paths"])})
        if not self.paths:
            raise ValueError(f"map {map_name!r} has no visible bloon path")
        self._heights = None

    def routes_for(self, scenario, moab):
        """Route indices of a scenario that bloons of this class (MOAB-class
        or not) take; all of the scenario's routes if none is reserved."""
        open_ = [i for i in self.scenarios[scenario] if self.paths[i]["moab"] in (None, moab)]
        return open_ or list(self.scenarios[scenario])

    # -- screen <-> world -------------------------------------------------------
    def heights(self):
        """Grid (as MapModel cells) of the height of the highest non-track
        area at each cell: a tower standing there is that high, which the
        tilted camera shows HEIGHT_FACTOR x height further up the screen."""
        if self._heights is None:
            from . import mapgeom as G
            from .maplearn import GRID
            top = np.zeros((GRID[1], GRID[0]), np.float32)
            present = G.starting_areas(self.geom)
            for i, area in enumerate(self.geom.get("areas", [])):
                if G._area_id(area, i) in present and area.get("type") != "track":
                    m = G._poly_mask(area["polygons"], self.proj)
                    top[m] = np.maximum(top[m], G.area_height(area))
            self._heights = top
        return self._heights

    def frac_to_world(self, fx, fy):
        """Screen fractions of the window -> world (x, z, height) of a tower
        standing there (on the highest area under that point)."""
        from .mapgeom import HEIGHT_FACTOR
        from .maplearn import GRID
        x0, y0, x1, y1 = self.playfield
        col = int(np.clip((fx - x0) / (x1 - x0) * GRID[0], 0, GRID[0] - 1))
        row = int(np.clip((fy - y0) / (y1 - y0) * GRID[1], 0, GRID[1] - 1))
        h = float(self.heights()[row, col])
        x = (fx - self.proj.cx) / self.proj.ux
        z = (self.proj.cy - fy) / self.proj.uy - HEIGHT_FACTOR * h
        return x, z, h

    def world_to_frac(self, x, z, h=0.0):
        f = self.proj.to_frac([[x, z, h]])[0]
        return float(f[0]), float(f[1])

    # -- zones ---------------------------------------------------------------------
    def total_length(self):
        """Hittable length of each path (world units)."""
        return [float(np.sum(np.diff(p["dist"])[p["hittable"][:-1]])) for p in self.paths]

    def zones(self, x, z, radius, travel=0.0, sight=None):
        """[Zone or None per path] for a reach of `radius` around (x, z).
        radius None or inf = the whole hittable path. sight(x0, z0, pts) ->
        bool mask of points visible from the tower (line of sight), optional."""
        out = []
        for p in self.paths:
            xyz, dist, ok = p["xyz"], p["dist"], p["hittable"]
            if radius is None or not math.isfinite(radius):
                inside = ok.copy()
            else:
                d2 = (xyz[:, 0] - x) ** 2 + (xyz[:, 1] - z) ** 2
                inside = ok & (d2 <= radius * radius)
                if sight is not None and inside.any():
                    vis = sight(x, z, xyz[inside])
                    idx = np.nonzero(inside)[0]
                    inside[idx[~vis]] = False
            if not inside.any():
                out.append(None)
                continue
            steps = np.diff(dist)
            covered = float(np.sum(steps[inside[:-1]]))
            if self.reverse:
                entry = p["length"] - float(dist[np.nonzero(inside)[0][-1]])
            else:
                entry = float(dist[np.nonzero(inside)[0][0]])
            angular = 1.0
            if travel:
                ang = np.arctan2(xyz[inside, 1] - z, xyz[inside, 0] - x)
                near = ((xyz[inside, 0] - x) ** 2 + (xyz[inside, 1] - z) ** 2) <= travel * travel
                sectors = np.unique(((ang[near] + math.pi) / (2 * math.pi) * 36).astype(int) % 36)
                angular = len(sectors) / 36.0
            out.append(Zone(entry=entry, length=covered, angular=angular))
        return out


# ===========================================================================
# Rounds: bloon lots
# ===========================================================================

@dataclass
class Lot:
    """A slice of one spawn group on one route: `count` bloons of one id
    (one layer: a ceramic's rainbows are a lot of their own once it pops).
    t0: the time the slice would be at distance 0 of its route at its speed
    (a station computes arrival = t0 + distance / speed).
    rho: bloons per world unit (how tightly packed), for pierce.
    speed: this layer's speed in world units per second, mode and round
    ramps included; speed_mult: those ramps (children move at their own base
    speed x speed_mult)."""
    path: int
    t0: float
    bloon: str
    count: float
    rho: float
    speed: float
    speed_mult: float = 1.0
    moab_hp: float = 1.0


@lru_cache(maxsize=None)
def _round_groups(set_name, rnd):
    rs = _json(str(ROUND_SETS))
    return tuple((rs.get(set_name) or {}).get(str(rnd), {}).get("groups") or ())


def _round_extra(set_name, rnd):
    """Freeplay ramps from data/rounds.json (speed_mult, blimp_hp_mult)."""
    rd = ((_json(str(ROUNDS_FILE)).get(set_name) or {}).get(str(rnd))) or {}
    return float(rd.get("speed_mult") or 1.0), float(rd.get("blimp_hp_mult") or 1.0)


def round_lots(mode, rnd, track, scenario=0):
    """The lots of round `rnd` in `mode`, on the routes of one scenario of
    the track: each group is shared evenly by the routes its class takes."""
    rules = mode_rules(mode)
    set_name = "abr" if mode == "abr" else "standard"
    groups = _round_groups(set_name, rnd)
    speed_ramp, hp_ramp = _round_extra(set_name, rnd)
    duration = max((g.get("end_s", 0.0) for g in groups), default=0.0)
    lots = []
    for g in groups:
        bid = g.get("id") or g["bloon"].capitalize()
        if bid not in bloon_table():
            continue
        moab_hp = rules["moab_hp"] * hp_ramp
        for r, b, mult in rules["round_health"]:
            if r == rnd and b == bid:
                moab_hp *= mult
        moab_hp = round(moab_hp, 4)
        top = layer(bid, moab_hp)
        speed_mult = rules["speed"] * speed_ramp
        speed = top.speed * speed_mult
        start, end = float(g.get("start_s", 0.0)), float(g.get("end_s", 0.0))
        if mode == "reverse":           # the round's groups come in reverse order
            start, end = duration - end, duration - start
        span = max(end - start, 0.0)
        count = float(g["count"])
        # bloons per world unit of track as they come out; a burst spawned
        # all at once is packed a quarter of a bloon's width apart at most
        spacing = max(span * speed / max(count, 1.0), 2.0 * top.radius / 4.0)
        rho = 1.0 / spacing
        k = max(1, min(LOTS_PER_GROUP, int(count)))
        routes = track.routes_for(scenario, top.moab)
        n = len(routes)
        for route in routes:
            for i in range(k):
                t = start + span * (i + 0.5) / k
                lots.append(Lot(path=route, t0=t, bloon=bid, count=count / k / n, rho=rho / n,
                                speed=speed, speed_mult=speed_mult, moab_hp=moab_hp))
    return lots


# ===========================================================================
# Stations and the round simulation
# ===========================================================================

@dataclass
class Station:
    """A tower on the map, as the round simulation sees it.
    zones: Zone or None per route; sources: Source list (buffs applied);
    order: where along the track it starts working (for the processing order);
    strong: it works on MOAB-class bloons before anything else (single-target
    towers set to "strong" targeting: snipers - the plans say so);
    banked / bank_seconds / bank_start: a spike pile (see _Server)."""
    tid: str
    kind: str
    tiers: tuple
    zones: list
    sources: list
    order: float
    banked: bool = False
    bank_seconds: float = 0.0
    bank_start: float = 0.0      # stock carried over from the last round (seconds of production)
    strong: bool = False
    strength: float = 1.0

    def covers(self, path):
        return path < len(self.zones) and self.zones[path] is not None and self.zones[path].length > 0


def _bloons_met(src, rho, zone):
    """How many bloons one projectile of this source can reach, given the
    packing rho (bloons per world unit of track)."""
    if src.reach == 0.0:                       # its own target only (sniper bullets)
        return 1.0
    if src.zone_wide:                          # a blast over the whole range (Ice Monkey)
        return 1.0 + rho * (zone.length if zone is not None else 0.0)
    if math.isinf(src.reach):                  # waits on the track (spikes): all that pass
        return math.inf
    return 1.0 + rho * src.reach


def _hit_rate(src, lay, rho, zone):
    """Hits per second this source lands on bloons of this layer.

    projectiles per second (fewer for spawn-on-contact chains when bloons
    are sparse, see Source.shots_single), times hits per projectile: its
    pierce, but no more than the bloons it can meet - except that a
    lingering projectile may hit one bloon several times (single_hits)."""
    met = _bloons_met(src, rho, zone)
    sparse = lay.moab or met < 2.0
    shots = src.shots_single if sparse else src.shots
    if src.radial:
        shots *= zone.angular if zone is not None else 1.0
    if src.placement == "air":
        shots *= AIR_PATTERN_EFFICIENCY
    per_shot = min(src.pierce, max(met, src.single_hits))
    return shots * per_shot


class _Rates:
    """Per station: how fast it takes health off one layer (bloon id) at a
    given packing, and how much damage overflows into the children."""

    def __init__(self, station):
        self.station = station
        self.cache = {}

    def get(self, bloon_id, moab_hp, rho, path):
        """(HP per second, mean overflow per pop) on this layer, or None when
        no source of the station can damage it (immune, camo, MOAB filter)."""
        key = (bloon_id, moab_hp, round(math.log2(max(rho, 1e-4)) * 2), path)
        if key not in self.cache:
            self.cache[key] = self._compute(bloon_id, moab_hp, rho, path)
        return self.cache[key]

    def _compute(self, bloon_id, moab_hp, rho, path):
        zone = self.station.zones[path]
        lay = layer(bloon_id, moab_hp)
        hp_rate = overflow = 0.0
        for src in self.station.sources:
            if not src.can_hit(lay):
                continue
            hits = _hit_rate(src, lay, rho, zone)
            d = src.damage_vs(lay)
            rate = hits * min(d, lay.hp)
            hp_rate += rate
            # the game passes a hit's damage beyond a layer's health on to its
            # children (DamageModel.distributeToChildren): a 3-damage tack pops
            # a lead and two more layers with one hit
            overflow += rate * max(0.0, d - lay.hp)
            if src.dot_total:
                # damage over time: every hit poisons a bloon for dot_total in
                # all; no more than the bloons in the zone, each burning at
                # dot_rate per second
                in_zone = max(1.0, rho * zone.length)
                hp_rate += min(hits * src.dot_total, in_zone * src.dot_rate)
        if hp_rate <= 0.0:
            return None
        return hp_rate * self.station.strength * TOWER_EFFICIENCY, overflow / hp_rate

    def subtree(self, bloon_id, moab_hp, rho, path, free):
        """(seconds of work per bloon, ((id, count), ...) handed on) to pop a
        small bloon and everything inside it that this station can pop.

        Small layers (see SMALL_LAYER_HP) are worked as one job with their
        children instead of a job per layer, which keeps the simulation fast:
        the walk adds each layer's health (less the damage carried in from
        its parent) over the HP per second on it, and stops at layers the
        station cannot damage, which are handed on to the next station."""
        key = (bloon_id, moab_hp, round(math.log2(max(rho, 1e-4)) * 2), path, round(free, 1))
        hit = self.cache.get(("subtree",) + key)
        if hit is not None:
            return hit
        work, passed = 0.0, {}
        stack = [(bloon_id, 1.0, rho, free)]   # (id, bloons per top bloon, packing, damage carried in)
        while stack:
            bid, n, r, f = stack.pop()
            rate = self.get(bid, moab_hp, r, path)
            if rate is None:
                passed[bid] = passed.get(bid, 0.0) + n
                continue
            hp_rate, overflow = rate
            lay = layer(bid, moab_hp)
            need = max(0.0, lay.hp - f)
            carry = max(0.0, f - lay.hp) + (overflow if need > 0.0 else 0.0)
            work += n * need / hp_rate
            kids = sum(k for _, k in lay.children) or 1
            for child, k in lay.children:
                stack.append((child, n * k, r * k, carry / kids))
        out = (work, tuple(sorted(passed.items())))
        self.cache[("subtree",) + key] = out
        return out


@dataclass
class RoundResult:
    leaked: dict           # bloon id -> count that reached the exit
    lives_lost: float
    leaked_rbe: float
    end_time: float        # when the last bloon was popped (seconds of game time at 1x)

    @property
    def safe(self):
        return self.lives_lost < LEAK_LIVES_EPS


@dataclass
class _Job:
    """Popping one lot's layer at one station."""
    release: float         # its bloons enter the zone (or appear in it)
    deadline: float        # ... and leave it
    work: float            # seconds of the station's time to pop them all
    remaining: float
    lot: Lot
    zone: Zone
    pos: float             # distance along the route at `release`
    carry: float           # damage each popped bloon passes on to its children
    priority: int          # 0 first (MOAB-class at a "strong" station), then 1
    passed: tuple = None   # small layers: ((id, count per bloon), ...) handed on when popped


class _Server:
    """One station working through its jobs: always the unfinished job of
    the best priority that leaves the zone first (the game's "first"
    targeting; "strong" stations put MOAB-class bloons first), one second
    of work per second. A popped layer's children appear where it popped,
    as new jobs (or are handed on when the station cannot hurt them).

    A banked station (spike piles) is never idle: while no bloon is in its
    zone it builds stock, up to bank_seconds of production, starting from
    bank_start left over from the last round, and spends it instantly."""

    def __init__(self, station, out):
        self.st = station
        self.rates = _Rates(station)
        self.out = out                 # lots handed on to the next station
        self.pending, self.active = [], []
        self.seq = 0
        self.last_pop = 0.0

    def job(self, lot, zone, release, pos, free):
        """A job for a lot entering (or appearing in) the zone, or None when
        the station cannot damage its layer."""
        r = self.rates.get(lot.bloon, lot.moab_hp, lot.rho, lot.path)
        if r is None:
            return None
        hp_rate, overflow = r
        lay = layer(lot.bloon, lot.moab_hp)
        deadline = release + max(0.0, zone.entry + zone.length - pos) / lot.speed
        prio = 0 if (self.st.strong and lay.moab) else 1
        if not lay.moab and lay.hp <= SMALL_LAYER_HP:
            per_bloon, passed = self.rates.subtree(lot.bloon, lot.moab_hp, lot.rho, lot.path, free)
            work = lot.count * per_bloon
            return _Job(release, deadline, work, work, lot, zone, pos, 0.0, prio, passed)
        need = max(0.0, lay.hp - free)               # health left after the carried damage
        carry = max(0.0, free - lay.hp) + (overflow if need > 0.0 else 0.0)
        work = lot.count * need / hp_rate
        return _Job(release, deadline, work, work, lot, zone, pos, carry, prio)

    def push(self, job):
        self.seq += 1
        heapq.heappush(self.pending, (job.release, self.seq, job))

    def run(self):
        banked, cap = self.st.banked, self.st.bank_seconds
        credit = self.st.bank_start if banked else 0.0
        t = 0.0
        while self.pending or self.active:
            if not self.active:
                nxt = self.pending[0][0]
                if banked and nxt > t:
                    credit = min(cap, credit + (nxt - t))
                t = max(t, nxt)
            while self.pending and self.pending[0][0] <= t + 1e-9:
                _, seq, job = heapq.heappop(self.pending)
                heapq.heappush(self.active, (job.priority, job.deadline, seq, job))
            if not self.active:
                continue
            _, deadline, _, job = self.active[0]
            if deadline <= t + 1e-9 or job.remaining <= 1e-12:
                heapq.heappop(self.active)
                self.finish(job, t)
                continue
            if banked and credit > 0.0:
                use = min(credit, job.remaining)
                credit -= use
                job.remaining -= use
            nxt = self.pending[0][0] if self.pending else math.inf
            step = min(job.remaining, deadline - t, nxt - t)
            job.remaining -= step
            t += step
            if job.remaining <= 1e-12:
                heapq.heappop(self.active)
                self.finish(job, t)

    def finish(self, job, t):
        """The job is done or its bloons left the zone at time t: what was
        not popped goes on; the popped bloons' children appear here."""
        lot = job.lot
        done = 1.0 if job.work <= 0.0 else max(0.0, 1.0 - job.remaining / job.work)
        if done < 1.0 - 1e-9:
            self.out.append(Lot(lot.path, lot.t0, lot.bloon, lot.count * (1.0 - done), lot.rho, lot.speed,
                                lot.speed_mult, lot.moab_hp))
        if done <= 1e-9:
            return
        self.last_pop = max(self.last_pop, t)
        popped = lot.count * done
        end = job.zone.entry + job.zone.length
        pos = min(end, job.pos + lot.speed * (t - job.release))
        if job.passed is not None:
            # a small bloon's whole tree was worked at once: hand on the layers
            # this station cannot pop, from where the bloon was popped
            for child, k in job.passed:
                speed = layer(child, lot.moab_hp).speed * lot.speed_mult
                self.out.append(Lot(lot.path, t - pos / speed, child, popped * k, lot.rho * k, speed,
                                    lot.speed_mult, lot.moab_hp))
            return
        lay = layer(lot.bloon, lot.moab_hp)
        kids = sum(k for _, k in lay.children) or 1
        for child, k in lay.children:
            speed = layer(child, lot.moab_hp).speed * lot.speed_mult
            child_lot = Lot(lot.path, t - pos / speed, child, popped * k, lot.rho * k, speed,
                            lot.speed_mult, lot.moab_hp)
            child_job = self.job(child_lot, job.zone, t, pos, job.carry / kids)
            if child_job is None or child_job.deadline <= t + 1e-9:
                self.out.append(child_lot)
            else:
                self.push(child_job)


def _lots(mode, rnd, track, scenario):
    """round_lots, remembered on the track (lots are never changed in place)."""
    cache = track.__dict__.setdefault("_lot_cache", {})
    key = (mode, rnd, scenario)
    if key not in cache:
        cache[key] = round_lots(mode, rnd, track, scenario)
    return cache[key]


def simulate_round(stations, mode, rnd, track, strength=1.0):
    """Play round `rnd` against the stations (see the module docstring) in
    every scenario of the track (alternating spawns) and return the worst.
    strength scales every station's output (margin search)."""
    worst = None
    for sc in range(len(track.scenarios)):
        res = _play(stations, track, _lots(mode, rnd, track, sc), strength)
        if worst is None or (res.lives_lost, res.end_time) > (worst.lives_lost, worst.end_time):
            worst = res
    return worst


def _play(stations, track, lots, strength):
    """One scenario of one round: lots flow through the stations in track
    order; what is left after the last one leaks."""
    lots = list(lots)
    end_time = 0.0
    for st in sorted(stations, key=lambda s: s.order):
        st.strength = strength
        out = []
        server = _Server(st, out)
        for lot in lots:
            if lot.count <= 1e-9:
                continue
            if not st.covers(lot.path):
                out.append(lot)
                continue
            z = st.zones[lot.path]
            job = server.job(lot, z, lot.t0 + z.entry / lot.speed, z.entry, 0.0)
            if job is None:
                out.append(lot)             # cannot touch this layer: passes untouched
            else:
                server.push(job)
        server.run()
        end_time = max(end_time, server.last_pop)
        lots = out
    path_len = [p["length"] for p in track.paths]
    leaked, lives, leak_rbe = {}, 0.0, 0.0
    for lot in lots:
        if lot.count <= 1e-9:
            continue
        leaked[lot.bloon] = leaked.get(lot.bloon, 0.0) + lot.count
        lives += lot.count * layer(lot.bloon, lot.moab_hp).leak
        leak_rbe += lot.count * rbe(lot.bloon, lot.moab_hp)
        end_time = max(end_time, lot.t0 + path_len[lot.path] / lot.speed)
    return RoundResult(leaked=leaked, lives_lost=lives, leaked_rbe=leak_rbe, end_time=end_time)


def round_margin(stations, mode, rnd, track, lo=1 / 16, hi=16.0, iterations=9):
    """The safety margin of round rnd: the factor by which every tower could
    be weaker and the round still pop without a leak (2.0 = holds at half
    strength; below 1.0 = leaks at full strength). Bisection on strength,
    worst over the track's scenarios."""
    worst = 1.0 / lo
    for sc in range(len(track.scenarios)):
        lots = _lots(mode, rnd, track, sc)
        if not lots:
            continue

        def safe(strength):
            return _play(stations, track, lots, strength).safe

        if not safe(hi):
            return 1.0 / hi
        if safe(lo):
            continue
        a, b = math.log(lo), math.log(hi)       # unsafe at exp(a), safe at exp(b)
        for _ in range(iterations):
            m = (a + b) / 2
            if safe(math.exp(m)):
                b = m
            else:
                a = m
        worst = min(worst, 1.0 / math.exp(b))
    return worst


# ===========================================================================
# Building stations for towers on a map
# ===========================================================================

@dataclass
class Placed:
    """A tower of a plan: kind, crosspath, world position."""
    tid: str
    kind: str
    tiers: tuple
    x: float
    z: float


def _buffed_sources(p, buffs_here):
    """A profile's sources with support buffs applied (rate, pierce, camo)."""
    out = []
    for s in p.sources:
        shots, single, pierce, camo = s.shots, s.shots_single, s.pierce, s.camo
        for b in buffs_here:
            if b["kind"] == "rate" and b.get("value"):
                shots /= b["value"]
                single /= b["value"]
            elif b["kind"] == "pierce" and b.get("value"):
                pierce += b["value"]
            elif b["kind"] == "camo":
                camo = True
        out.append(Source(**{**s.__dict__, "shots": shots, "shots_single": single, "pierce": pierce, "camo": camo}))
    return out


def station_for(t, placed, track, sight=None):
    """The Station of one Placed tower, or None when it does no damage or
    reaches no track. Support buffs of the other towers in `placed`
    (villages: camo, attack rate, range, pierce) apply when this tower stands
    inside the supporter's range. sight(x, z, pts) -> visible mask, used for
    towers that need line of sight (placement.needs_sight)."""
    from . import gamemodel
    from .placement import needs_sight
    p = profile(t.kind, t.tiers)
    if p is None:
        return None
    buffs_here = []
    range_mult = 1.0
    for o in placed:
        q = profile(o.kind, o.tiers) if o.tid != t.tid else None
        if q is None:
            continue
        for b in q.buffs:
            reach = b.get("radius") or q.range
            if b.get("global") or math.hypot(o.x - t.x, o.z - t.z) <= reach + (gamemodel.footprint_radius(t.kind) or 6.0):
                if b["kind"] == "range" and b.get("value"):
                    range_mult = max(range_mult, 1.0 + b["value"])
                else:
                    buffs_here.append(b)
    sources = _buffed_sources(p, buffs_here)
    if not sources:
        return None
    # all of a tower's sources share one station: its time is spent once
    reach_radius = p.range * range_mult
    if p.pattern_radius:
        reach_radius = p.pattern_radius + p.range * range_mult
    is_global = p.is_global or any(s.placement == "global" for s in sources)
    travel = max((s.travel for s in sources if s.radial), default=0.0)
    blocked = sight if (sight is not None and not is_global and needs_sight(t.kind)) else None
    zones = track.zones(t.x, t.z, None if is_global else reach_radius, travel=travel, sight=blocked)
    if not any(zones):
        return None
    order = min((z.entry / max(pl["length"], 1e-6) for z, pl in zip(zones, track.paths) if z), default=1.0)
    banked = all(s.placement == "track" for s in sources)
    bank = max((s.bank for s in sources), default=0.0)
    start = min(bank, CARRIED_STOCK_SECONDS) if banked and any(s.lasts_rounds for s in sources) else 0.0
    # single-target towers (sniper bullets) are set to "strong" targeting by
    # the plans: they shoot MOAB-class bloons first
    strong = any(s.reach == 0.0 for s in sources)
    return Station(tid=t.tid, kind=t.kind, tiers=tuple(t.tiers), zones=zones, sources=sources,
                   order=order, banked=banked, bank_seconds=bank, bank_start=start, strong=strong)


def stations_for(placed, track, sight=None):
    """Stations for a list of Placed towers on a Track (see station_for)."""
    return [st for st in (station_for(t, placed, track, sight) for t in placed) if st is not None]


def evaluate(placed, mode, rounds, track, sight=None, margins=False):
    """{round: RoundResult} (and {round: margin} when margins=True) for a
    fixed defence over a list of rounds."""
    st = stations_for(placed, track, sight)
    results = {r: simulate_round(st, mode, r, track) for r in rounds}
    if not margins:
        return results
    return results, {r: round_margin(st, mode, r, track) for r in rounds}
