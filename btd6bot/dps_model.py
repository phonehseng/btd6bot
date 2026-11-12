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
    * Monkey Knowledge and alchemist brews are not counted (they only
      help); heroes (HERO_RATING), abilities at their uptime
      (ABILITY_RATING) and slows, stuns, knockback and damage-taken
      debuffs (STATUS_RATING) are, each read cautiously
      (docs/model_fix_plan.md phase 2);
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
#
# Re-checked 2026-11-12 after phase 1 of docs/model_fix_plan.md (the
# over-credits: Bomber Ace bombs, instakill overflow, alternative shots,
# per-attack reach, the dip, Spiked Mines). The boards of 690 journals
# (logs/journal, round events; 526 rounds that leaked, 7,185 of ~27,000
# that held) were rated with the code before and after: separation of
# leaked from held rounds (AUC) 0.797 -> 0.805; rounds at or above 2.0 that
# leaked anyway 0.57% -> 0.53% (11 leaked rounds moved under 2.0, none
# over); the median margin moved x0.98 (a quarter of the rounds x0.89 or
# less: boards with Druid of the Jungle, Bomber Aces, submerged subs).
# The new model reaches the old 2.0's leak rate at about 1.7-1.8, but the
# two bands' uncertainty overlaps (0.38-0.74% at 2.0), so SAFETY_MARGIN
# stays 2.0 and this stays 1.0.
TOWER_EFFICIENCY = 1.0

# --- modelling constants (assumptions, documented in docs/optimizer.md) -----
LOTS_PER_GROUP = 6          # time slices a spawn group is split into
TRACK_STEP = 2.0            # world units between sampled path points
CONTACTS_PER_CARRIER = 2.0  # bloons a carrier projectile touches in a crowd (spawn-on-contact chains)
TRAVEL_OVERLAP = 0.35       # share of a flying projectile's path that runs along the lane
MAX_SUBTOWERS = 6           # sub-towers alive at once (sentries, ...) when the model gives no cap
AIR_PATTERN_EFFICIENCY = 0.4  # share of a circling plane's radial darts that cross the lane
TRACK_ARC_DEG = 180.0       # most of the circle around a tower a track beside it can cover (a straight
                            # line seen from a point off it spans less than half a turn): _sector_shares
LEAK_LIVES_EPS = 0.5        # fluid model: less than half a life lost counts as no leak
CARRIED_STOCK_SECONDS = 30.0  # spikes that outlive the round: production of this long is still lying there
SMALL_LAYER_HP = 4.0        # layers with at most this health (all but ceramics and MOAB-class) are worked
                            # together with their children as one job (speed; see _Rates.subtree)

# Each bot mode is a game difficulty plus mode Mods (ModeType.GetModesForDifficulty:
# Impoppable and CHIMPS are played on Hard). Rules are read from these Mod
# assets in attacks.json "modes" (speed, health, cash).
# CHIMPS is Hard plus the "Clicks" Mod alone, as gamemodel.MODE_MODS prices
# it: Clicks carries its own rounds (6 to 100) and locks the farms, and the
# Impoppable Mod holds nothing else but those rounds and its 1.12 price
# multiplier (no speed, health or cash rule; attacks.json "modes"), so
# listing it here only made CHIMPS towers cost Impoppable prices.
MODE_MODS = {
    "easy": ["Easy"], "primary_only": ["Easy", "PrimaryOnly"], "deflation": ["Easy", "Deflation"],
    "medium": ["Medium"], "military_only": ["Medium", "MilitaryOnly"], "reverse": ["Medium", "Reverse"],
    "apopalypse": ["Medium", "Apopalypse"],
    "hard": ["Hard"], "magic_only": ["Hard", "MagicOnly"], "double_hp": ["Hard", "DoubleMoabHealth"],
    "half_cash": ["Hard", "HalfCash"], "abr": ["Hard", "AlternateBloonsRounds"],
    "impoppable": ["Hard", "Impoppable"], "chimps": ["Hard", "Clicks"],
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
                map), "air" (from a plane circling the tower), "drop"
                (dropped under a plane circling the tower: see blast)
    radial      fired all around rather than at a target (tacks, a plane's
                darts): only the share of directions that cross the lane hits
    spray       degrees an aimed volley fans over (Triple Shot 30, Sun
                Avatar 30, thorns 25; 0 = not a spray): all of it flies at the
                target, and only a volley wider than the track's spread
                around the tower loses the part that misses (_hit_rate)
    travel      how far a radial projectile flies (for that share)
    bank        seconds of production a "track" source can stockpile
    lasts_rounds  its projectiles outlive the round (Long Life Spikes): the
                stockpile carries over into the next round
    camo_shared the tower sees no camo itself but shoots the camo bloons
                another tower's detection covers (a Monkey Sub's Advanced
                Intel: attacks.json "camo_shared"); station_for turns it
                into camo when such a tower stands on the board
    off_struck  a piece its carrier throws off where it struck a bloon and
                that flies away from it (a sniper's Shrapnel Shot, a bomb's
                frags): it never hits the struck bloon, only the other
                bloons near that spot and what the carrier's hit left there
                (see _hit_rate)
    carrier     (damage, immune, bonus) of the projectile that throws an
                off_struck piece off, or None
    blast       for placement "drop" (a bomb that falls from a plane where
                the plane is: Monkey Ace pineapples, Bomber Ace): the radius
                of its explosion, which decides how near the track it must
                fall to hit anything (see _drop_parts)
    over_track_only  a "drop" weapon the game fires only while its plane is
                over the track (CheckAirUnitOverTrackModel, the export's
                "over_track_only": Bomber Ace and Ground Zero)
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
    camo_shared: bool = False
    off_struck: bool = False
    carrier: tuple = None
    blast: float = 0.0
    over_track_only: bool = False
    cooldown: float = 0.0      # "drop": seconds between the weapon's volleys
    pierce_cost: dict = field(default_factory=dict)   # extra pierce per hit, by bloon tag (_pierce_cost)
    rear_fov: float = 0.0      # a Buccaneer's second shot behind the boat: degrees of its target cone
    spray: float = 0.0         # an aimed volley's fan in degrees (see the class docstring)
    refresh: float = 0.0       # a lingering patch whose pierce comes back every `refresh` s (_patch_hits)
    life: float = 0.0          # ... and how long it lies there
    patch_radius: float = 0.0  # ... and its radius
    zone_radius: float = None  # its own attack's reach around the tower (_zone_radius); None = the tower's
    zone_fixed: bool = False   # zone_radius is not changed by range buffs (Glaive Lord's orbit)
    dot_immune: frozenset = frozenset()   # bloon properties its damage over time cannot hurt
                               # (0 = not such a shot; _rear_copies)
    ability: str = ""          # the ability it belongs to, credited at its uptime ("" = the tower's
                               # own attack; _ability_attacks)
    grip_rate: float = 0.0     # a hit that holds its bloon and deals this much a second (Psi: _psi_grip)
    effects: dict = field(default_factory=dict)   # what a hit does besides damage (the export's
                               # "effects": stun, slow, freeze, maim, pushback, blowback, debuff,
                               # removes); read by _Controls
    ability_use: str = ""      # for an ability's source: the bot's use of it ("moab": pressed in
                               # blimp rounds only, see _Controls)

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
    own_radius: float = 0.0          # circle swept around the tower itself (Glaive Lord's glaives)
    flight_speed: float = 0.0        # a plane's speed along its flight circle (air_unit.speed)
    fire_rate: float = 0.0           # weapon shots a second of its own attacks (an Alchemist dip's budget)
    boosts: list = field(default_factory=list)   # its abilities' boosts to its own attacks (_ability_boosts)
    zones: list = field(default_factory=list)    # slow zones around it (the export's "zones": Arctic Wind)


# The bloon properties a damage type can be unable to pop (Layer.immune).
IMMUNITIES = ("lead", "black", "white", "purple")


def _immune_set(entry):
    return frozenset(x for x in (entry or {}).get("immune", []) if x in IMMUNITIES)


# An attack that throws a potion at OTHER TOWERS rather than at bloons: the
# Alchemist's Acidic Mixture Dip and Berserker Brew. The export lists them
# as attacks whose projectile hits its target only and carries an
# "Add<Potion>ToProjectileModel" behaviour - the game attaches it to the
# buffed tower's projectiles. Such an attack is no damage source (it has no
# damage of its own, so _flatten_projectile already skips it) but a support
# buff, like a village's.
POTION_MARK = "ToProjectileModel"


def _potion_buffs(entry):
    """Support buffs derived from a crosspath's potion attacks (POTION_MARK):
    [{"kind": "damage_type", "props": [...], "bonus": {...}, "radius": r}].

    The dip's projectile names bonus damage per bloon tag ("Lead": +1,
    "Ceramic": +1, "Moabs": +1); a bonus against a tag that is also an
    immunity (IMMUNITIES: "Lead") means the buffed tower's projectiles pop
    that bloon, so the buff lifts that immunity and adds the bonus to every
    hit on the tag. Without it the model thought a Ninja + Alchemist build
    popped no lead at all: Dark Dungeons Magic Monkeys Only (2026-11-05,
    loss case 20261105_070008) rated every lead round at the floor (0.06)
    from round 23 on although the game held rounds 28 and 30, so reinforce
    could not tell one purchase from another and nothing was bought for
    round 37's 15 leads. A brew whose numbers the export does not carry
    (Berserker Brew: rate, damage, pierce) adds no buff yet."""
    out = []
    for a in entry.get("attacks", []):
        for w in a.get("weapons", []):
            p = w.get("projectile") or {}
            marks = [o for o in p.get("other", []) if isinstance(o, str) and o.endswith(POTION_MARK)]
            if not marks or not p.get("target_only"):
                continue
            bonus = p.get("bonus") or {}
            props = sorted({t.lower() for t in bonus if t.lower() in IMMUNITIES})
            if not props and not bonus:
                continue
            potion = p.get("potion") or {}
            out.append({"kind": "damage_type", "props": props, "bonus": bonus,
                        "radius": a.get("range") or entry.get("range"), "name": marks[0],
                        "shots": potion.get("shots"), "every": w.get("rate")})
    return out


# A potion that lasts at least this many of the buffed tower's shots never
# runs out: Permanent Brew's dip and brew carry 9,999,999.
PERMANENT_POTION_SHOTS = 1e6


def _dip_share(b, supporter, t, placed):
    """Share of tower t's shots an Alchemist's Acidic Mixture Dip (potion
    buff b of `supporter`) covers.

    The dip is not a permanent aura: the Alchemist throws it at ONE tower
    every `every` seconds (10 s) and it lasts `shots` of that tower's shots
    (10, 12 at x-2-x: AcidicMixtureCheckModel.maxCount, the export's
    "potion"; fandom:Acidic_Mixture_Dip). So an Alchemist dips shots / every
    shots a second, shared by the attacking towers in its range, against t's
    own shots a second (Profile.fire_rate). It is permanent only with
    Permanent Brew (5-x-x: shots 9,999,999). Read as permanent, the dip let
    a Bloonjitsu's 11.5 shots/s all pop lead where about one a second does
    (docs/model_audit_magic.md, finding 2)."""
    shots, every = b.get("shots"), b.get("every")
    if not shots or shots >= PERMANENT_POTION_SHOTS or not every:
        return 1.0
    radius = b.get("radius") or 0.0
    takers = [o for o in placed if o.tid != supporter.tid and o.kind != "alchemist"
              and (profile(o.kind, o.tiers) or Profile("", (), 0.0, False, [])).sources
              and buff_covers(supporter, o, radius)]
    rate = profile(t.kind, t.tiers).fire_rate
    if rate <= 0.0:
        return 1.0
    return min(1.0, shots / every / max(1, len(takers)) / rate)


def _target_only(p):
    """Does projectile p touch its own target and nothing else?

    Two game behaviours say so: a FilterAllExceptTargetModel (sniper
    bullets; the export writes it as "target_only") and a
    CollideOnlyWithTargetModel, which the export leaves uninterpreted in
    "other". The second is the Druid of the Jungle's vine (x-3-x): its
    projectile has 9,999,999 pierce and a 4-unit radius, but the game lets
    it collide with the one bloon it grabbed. Read as a 4-unit blast, a
    vine took ~6 bloons of a packed burst at once, so two druids rated
    Bazaar Half Cash's round 63 (40 ceramics spawned in 0.2 s, three
    times) 1.98 where the game lost all 100 lives in seconds with them
    standing (loss case 20261110_114329_Bazaar_half_cash)."""
    return bool(p.get("target_only")) or "CollideOnlyWithTargetModel" in (p.get("other") or ())


def _reach_of(p, placement, attack_range):
    """Track length one projectile sweeps (see Source.reach): its own
    diameter plus a bloon's (8 units radius) on each side, plus a share of
    the distance it flies (TRAVEL_OVERLAP: darts cross the lane at an angle),
    counting at most twice the attack's range of flight (beyond that it is
    past the bloons it was fired at; boomerangs live long but loop back)."""
    if _target_only(p):
        return 0.0                       # hits its target only (sniper bullets, druid vines)
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


# Lingering patches whose pierce comes back (docs/model_fix_plan.md item 11,
# docs/model_audit_magic.md finding 4): Wall of Fire (10 pierce every
# 0.15 s for 4.5 s), the Druid of the Jungle's brambles (20 pierce every
# 0.3 s for 4.5 s), Mortar Blooncineration's wall, the Mermonkey's trance.
# A patch got one load of pierce and a fixed count of hits: Wall of Fire 10
# where the game gives it up to 300 in a dense stream, a bramble 15 even on
# a lone bloon that crosses its 2-unit circle in three ticks. False reads
# them as before.
#
# Calibrated against item 10: AUC 0.817 -> 0.818, rounds at or above 2.0
# that leaked 0.52% -> 0.53% (0.53% at the matched cut): neutral.
REFRESH_RATING = True


def _refresh_of(p):
    """Seconds between pierce refreshes of a patch that lies still (static
    or instant, with RefreshPierceModel: the export's "pierce_refresh"), 0
    for any other projectile or with REFRESH_RATING off."""
    if not REFRESH_RATING or p.get("motion") not in ("static", "instant"):
        return 0.0
    return float(p.get("pierce_refresh") or 0.0) if p.get("lifespan") else 0.0


def _patch_hits(src, lay, rho):
    """Hits one lingering patch lands over its life (Source.refresh): its
    pierce every refresh, pierce x life / refresh in all, but no more than
    the bloons that cross it while it lies there (1 + rho x (v x life +
    its width)) times the ticks each spends inside ((width) / v / refresh,
    at least 1, at most life / refresh), width = 2 x (patch radius + bloon
    radius). A bloon of base speed v (the layer's: the mode's speed factor
    is not known here) crossing a 15-unit Wall of Fire takes about ten
    ticks; a dense stream fills its 300 hits."""
    v = max(lay.speed, 1e-3)
    width = 2.0 * (src.patch_radius + lay.radius)
    ticks = max(1.0, min(src.life / src.refresh, math.ceil(width / v / src.refresh)))
    passing = 1.0 + rho * (v * src.life + width)
    return min(src.pierce * src.life / src.refresh, passing * ticks)


def _thrown_off(spawn):
    """Is this spawn a piece thrown off where its carrier struck a bloon,
    flying away from it (Shrapnel, Frag), rather than a blast centred on the
    spot (a bomb's Explosion), which takes in the struck bloon too?"""
    sub = spawn.get("projectile") or {}
    return spawn.get("on") == "contact" and sub.get("motion") not in (None, "static", "instant")


def _carrier_of(p):
    """(damage, immune, bonus) of projectile p's own hit (see Source.carrier)."""
    hit = p.get("damage") or {}
    return float(hit.get("amount", 0.0)), _immune_set(hit), p.get("bonus") or {}


def _left_at_spot(carrier, lay):
    """Does the carrier's hit on a bloon of layer `lay` pop it and leave
    children on the spot? Then the pieces thrown off there have bloons to
    hit next to them: the children (a 7-damage bullet on a lead leaves
    greens; on a pink it leaves nothing)."""
    damage, immune, bonus = carrier
    if immune & lay.immune or lay.moab:
        return False
    for key, b in bonus.items():
        if key in lay.tags:
            damage = damage * b["mult"] + b["add"]
    return lay.hp <= damage < rbe(lay.id)


def _impact_pierce(p):
    """Pierce of projectile p for counting its hits.

    An impact projectile - one that bursts when its pierce runs out (an
    "exhaust" spawn) - is capped at its maxPierce (the export's
    "max_pierce"): the Monkey Sub's Airburst dart has pierce 2 but maxPierce
    1, and the wiki gives it "1 impact" before it splits
    (fandom:Airburst_Darts; docs/model_audit_military.md M4). Other
    projectiles keep their pierce: what maxPierce means for them (Glue
    Gunner globs carry 4 / 1) is not confirmed."""
    pierce = max(1.0, p.get("pierce", 1.0))
    cap = p.get("max_pierce")
    if cap and cap < pierce and any(s.get("on") == "exhaust" for s in p.get("spawn", [])):
        pierce = max(1.0, cap)
    return pierce


def _alternative_spawns(spawns):
    """The spawns of a projectile, with "expire" spawns left out where the
    same projectile is also spawned on "exhaust".

    The two are alternatives: a projectile either uses up its pierce
    (exhaust: it hit) or lives out its lifespan (expire: it missed), never
    both. The model assumes projectiles never miss, so the exhaust one
    stands. Counting both credited every Monkey Sub Airburst dart with two
    bursts of splits (88% of a 2-0-4's crowd rating: docs/model_audit_
    military.md M4) and every Spiked Mine with two explosions
    (docs/model_audit_support_heroes.md S5: "Upon lifespan expiry, create
    two instances of Explosion. Upon pierce expiry, create one instance" -
    on a busy round the mine is exhausted)."""
    on_exhaust = {(sp.get("projectile") or {}).get("name") for sp in spawns if sp.get("on") == "exhaust"}
    return [sp for sp in spawns
            if not (sp.get("on") == "expire" and (sp.get("projectile") or {}).get("name") in on_exhaust)]


def _pierce_cost(p):
    """{bloon tag ("" = every bloon): extra pierce a hit on it uses up} of
    projectile p (CollideExtraPierceReductionModel, the export's
    "extra_pierce_cost"). Frag Bombs' frags have pierce 2 and cost 1 more
    per hit: one hit each, as the wiki gives them "1 pierce"
    (fandom:Frag_Bombs_(BTD6); docs/model_audit_primary.md F11)."""
    return {k: float(v) for k, v in (p.get("extra_pierce_cost") or {}).items() if v}


# The effects of a hit that hold bloons back (_Controls). "removes" (camo)
# and "debuff" act on the damage of other towers instead.
CONTROL_EFFECTS = ("stun", "slow", "freeze", "maim", "pushback", "blowback", "debuff", "removes")


def _controls_of(p):
    """Does projectile p do something to bloons the model counts besides
    damage (CONTROL_EFFECTS)? A glue projectile does no damage and was no
    source at all: every Glue Gunner below 0-0-5 was worth nothing
    (docs/model_audit_primary.md F1)."""
    if not STATUS_RATING:
        return False
    eff = p.get("effects") or {}
    return any(k in eff for k in CONTROL_EFFECTS) and not (
        set(eff) <= {"removes"} and "camo" not in (eff.get("removes") or ()))


def _psi_grip(p):
    """Psi's grip (the export's "psi": PsiEffectModel) as an instakill.

    Psi's projectile does no damage itself: it holds one bloon, which takes
    per_tick every `tick` seconds until it is gone or max_duration ends - an
    instakill that takes time, 0.15 s per layer of health from level 2, 4
    damage per 0.1 s on MOAB-class from level 14 (fandom:Psi_(BTD6);
    docs/model_audit_magic.md finding 16). So one grip destroys a whole
    bloon of up to max_duration / tick x per_tick health (a hit of that
    damage: _Rates._compute counts it as a whole-bloon kill), one grip per
    attack at a time, the cooldown running once it ends; and a held bloon
    loses no more than per_tick / tick a second (Source.grip_rate): a MOAB
    loses 40 HP a second to one attack at level 14, not the 600 a grip can
    deal over its 15 s. Read
    as a 0-damage hit, Psi was worth nothing; read as damage over time on
    every bloon at once, one Psi rated Erosion Reverse's rounds 18-22 near
    15 where the game leaked (docs/model_fix_plan.md item 7 calibration)."""
    g = p["psi"]
    tick = max(float(g.get("tick") or 1.0), 1e-3)
    per_tick = float(g.get("per_tick") or 0.0)
    total = per_tick * max(1.0, math.floor(float(g.get("max_duration") or tick) / tick))
    hit = p.get("damage") or {}
    return dict(p, damage=dict(hit, amount=total), grip_rate=per_tick / tick)


def _flatten_projectile(p, shots, shots_single, attack, camo_chain, placement, radial, travel, out, depth=0,
                        subtower_cap=MAX_SUBTOWERS, carrier=None):
    """Add the damage sources of projectile p (and what it spawns) to out.
    carrier: p was thrown off where this projectile hit struck a bloon
    (_thrown_off; Source.carrier)."""
    if not p or depth > 8:
        return
    if p.get("psi"):
        p = _psi_grip(p)
    camo = camo_chain and p.get("camo", False)
    attack_range = attack.get("range", 0.0)
    if (p.get("damage") or p.get("dot") or _controls_of(p)) and not p.get("hits_nothing"):
        # a damage source: direct damage, damage over time (corrosive glue,
        # burns), or both; a DoT-only projectile does 0 on the hit itself
        dot = p.get("dot") or {}
        ticks = math.floor((dot.get("lifespan") or 0.0) / max(dot.get("interval") or 1.0, 1e-3)) if dot else 0
        hit = p.get("damage") or {"amount": 0.0, "immune": dot.get("immune", [])}
        dot_tags = frozenset(dot.get("only_tags", []))
        out.append(Source(
            name=f"{attack.get('name')}>{p.get('name')}",
            shots=shots, shots_single=shots_single,
            pierce=_impact_pierce(p),
            damage=hit.get("amount", 0.0),
            # The hit's damage type decides what the projectile can touch; a
            # DoT-only projectile (corrosive glue) uses the DoT's. The burn is
            # applied only by a hit that damages, and has immunities of its
            # own (dot_immune). Intersecting the two let Spiked Mines (an
            # explosion immune to black, a burn immune to purple) damage
            # black bloons and DDTs on R95 and R99
            # (docs/model_audit_support_heroes.md S5, fandom:Spiked_Mines).
            immune=_immune_set(hit),
            dot_immune=_immune_set(dot) if dot else frozenset(),
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
            camo_shared=bool(attack.get("camo_shared")) and not camo,
            off_struck=carrier is not None,
            carrier=carrier,
            blast=(p.get("radius") or 0.0) if placement == "drop" else 0.0,
            over_track_only=placement == "drop" and bool(attack.get("over_track_only")),
            cooldown=attack.get("cooldown", 0.0) if placement == "drop" else 0.0,
            pierce_cost=_pierce_cost(p),
            rear_fov=float(attack.get("rear_fov") or 0.0),
            spray=float(attack.get("spray") or 0.0) if depth == 0 else 0.0,
            refresh=_refresh_of(p),
            life=float(p.get("lifespan") or 0.0),
            patch_radius=float(p.get("radius") or 0.0),
            zone_radius=attack.get("zone_radius"),
            zone_fixed=bool(attack.get("zone_fixed")),
            grip_rate=float(p.get("grip_rate") or 0.0),
            effects=dict(p.get("effects") or {}),
        ))
    pierce = max(1.0, _impact_pierce(p) / (1.0 + _pierce_cost(p).get("", 0.0)))
    if "CollideOnlyWithTargetModel" in (p.get("other") or ()):
        # it touches the one bloon it grabbed: one contact, one spawn (a
        # vine's thorn patch), not CONTACTS_PER_CARRIER of its 9,999,999
        # pierce. (Sniper bullets with pierce 3-5 and Shrapnel are
        # target-only too and still count two contacts: left as calibrated.)
        pierce = 1.0
    contacts = min(pierce, CONTACTS_PER_CARRIER)
    contacts_single = min(pierce, _single_hits(p))
    life = p.get("lifespan") or 0.0
    for s in _alternative_spawns(p.get("spawn", [])):
        n = s.get("count", 1.0)
        sub = s.get("projectile")
        on = s.get("on")
        if on == "contact":
            k, k1 = contacts * n * s.get("chance", 1.0), contacts_single * n * s.get("chance", 1.0)
        elif on == "interval" and s.get("once"):
            # emitted a single time, `every` seconds after the carrier appears
            # (CreateProjectileOnIntervalModel.onlyEmitOnce): an Abyss
            # Dweller's tentacle strikes once per rise, not once per 0.15 s of
            # the 1-1.5 s it stays up
            k = k1 = n
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
        _flatten_projectile(sub, shots * k, shots_single * k1, attack, camo, placement, radial, travel, out, depth + 1,
                            carrier=_carrier_of(p) if _thrown_off(s) else None)
    for t in p.get("subtowers", []):
        # sub-towers made by this projectile (an Engineer's sentries): as many
        # stand at once as are made during one lifespan, up to the cap
        lifespan = t.get("lifespan")
        alive = min(subtower_cap, shots * lifespan) if lifespan else min(subtower_cap, max(1.0, shots * 30.0))
        alive *= t.get("share", 1.0)         # one of several sentry types per spawn
        for a in t.get("attacks", []):
            _flatten_attack(a, out, multiplier=alive * _plane_share(t, a), depth=depth + 1,
                            parent_camo=camo_chain, tower_range=t.get("range"))


def _plane_share(subtower, attack):
    """Share of a sub-tower attack's shots the model counts.

    A map-wide sub-tower is a plane its tower launches (the Aircraft Carrier's
    and Carrier Flagship's BuccaneerPlane): it circles the way a Monkey Ace's
    plane does, so its attacks get the same share of the track
    (AIR_PATTERN_EFFICIENCY). Its attacks have no range of their own (the
    export gives them the whole map and no flight pattern), and the model
    used to count them at full rate on the whole track; on Frozen Over CHIMPS
    (2026-11-05, lost at round 56) that made two carriers look several times
    stronger than they were. MOAB-only missiles seek their target wherever it
    is and keep their full rate, as the Ace's own Anti-MoabMissile does."""
    if not subtower.get("global"):
        return 1.0                       # sentries and the like stand still in their own range
    if set(attack.get("only_tags") or ()) == {"Moabs"}:
        return 1.0
    return AIR_PATTERN_EFFICIENCY


def _trigger_rates(weapons):
    """{index of a triggered weapon: the rate it really fires at}.

    A weapon fired by another (FireAlternateWeaponModel) shoots at that
    one's rate; its own rate (0.05 s) is only a readiness check. The export's
    `fires_weapon` index is used when it points at a triggered weapon;
    otherwise the trigger is the nearest untriggered weapon before it, as the
    export lists each primary right before its secondary. (The buccaneer's
    Grape Shot and Cannon pairs carried indexes that point at the primary
    itself or past the list: their secondaries were counted at 20 shots a
    second - 100 Grape Shot shots/s instead of 3.7 - and boat builds were
    rated many times too strong.)"""
    rates = {}
    for i, w in enumerate(weapons):
        j = w.get("fires_weapon")
        if j is not None and j != i and 0 <= j < len(weapons) and weapons[j].get("triggered"):
            rates.setdefault(j, w.get("rate", 1.0))
    for i, w in enumerate(weapons):
        if w.get("triggered") and i not in rates:
            prev = next((k for k in range(i - 1, -1, -1) if not weapons[k].get("triggered")), None)
            if prev is not None:
                rates[i] = weapons[prev].get("rate", 1.0)
    return rates


def _attack_range(a, tower_range):
    """The range an attack really works in. An attack without a range check
    of its own (range >= 1000 in the model) reaches what the export's
    "unbounded" says: the whole map ("map", kept as it is), the circle its
    projectiles sweep around the tower ("self": Glaive Lord's orbiting
    glaives, own_radius), or the tower's range ("tower": Master Bomber's
    sticky bombs). An export without the field is read as before: map-wide."""
    unbounded = a.get("unbounded")
    if unbounded == "self":
        return a.get("own_radius") or tower_range or a.get("range", 0.0)
    if unbounded == "tower" and tower_range:
        return tower_range
    return a.get("range", 0.0)


def _sector_shares(a):
    """(crowd, single): the share of its shots an attack fires when it may
    only pick targets inside a sector of the circle around its tower (the
    export's "sector", in degrees; (1, 1) without one).

    single - one lone bloon walking past is inside a sector of s degrees for
    s / 360 of its way through the range, and the attack has nothing to shoot
    at for the rest.
    crowd - with bloons all along the track, the attack fires whenever its
    sector holds a piece of track. Seen from a tower beside it the track
    covers at most TRACK_ARC_DEG of the circle, so of a ring of such attacks
    that share is busy at once.

    The Abyss Dweller (Mermonkey 3-x-x) is the case: eight tentacle attacks
    of 45 degrees each. Counted all round, with every tentacle striking the
    same bloon, three of them were rated at about 450 damage a second against
    a BFB; Quad Deflation (2026-11-11, case 20261111_210232) relied on them,
    was rated 8.18 for round 60 and its BFB crossed untouched."""
    sector = a.get("sector")
    if not sector or sector >= 360.0:
        return 1.0, 1.0
    return min(1.0, max(sector, TRACK_ARC_DEG) / 360.0), sector / 360.0


def _drops_under_plane(a, w):
    """Does weapon w of attack a drop its bombs under a circling plane?

    Monkey Ace pineapples (0-1-x, 0-2-x) and Bomber Ace / Ground Zero bombs
    (0-3-x and up) are an AttackAirUnitModel with no range check: the export
    marks them "unbounded": "map", and the model used to read that as
    "anywhere on the map". In the game the bomb falls to the ground under
    the plane (FallToGroundModel) and explodes there, and the Bomber Ace
    weapon only fires while the plane is over the track
    (CheckAirUnitOverTrackModel, the export's "over_track_only";
    fandom:Bomber_Ace, fandom:Exploding_Pineapple). Read as map-wide, the
    bombs made up 91% of a 2-3-0 ace's rating and Ground Zero's 15-damage,
    40-pierce bombs made a 2-4-0 look like a whole-map carry
    (docs/model_audit_military.md, M1). The plane's darts circle the
    tower (pattern_radius) and keep their "air" reading."""
    p = w.get("projectile") or {}
    return bool(a.get("air") and not a.get("pattern_radius")
                and (w.get("over_track_only") or "FallToGroundModel" in (p.get("other") or ())))


# Aimed sprays read as aimed (docs/model_fix_plan.md item 10): a volley is
# fired all around only when its fan is at least RADIAL_SPRAY_DEG (a Tack
# Shooter's ring is 360). Triple Shot (30), Sun Avatar (30), Bloonjitsu
# (45), Grandmaster (72), the Druid's thorns (25) and the Desperado's
# shotgun (35) fan out from the shot at their target, and were cut to the
# share of all directions that cross the lane - about 40% beside a straight
# track (docs/model_audit_magic.md finding 3, primary F8). False reads every
# volley of 3 or more as before.
#
# Calibrated against item 9: AUC 0.814 -> 0.817, rounds at or above 2.0
# that leaked 0.52% -> 0.52%, held rounds under 2.0 51.2% -> 49.4%.
SPRAY_RATING = True
RADIAL_SPRAY_DEG = 180.0


def _spray(w, p, placement, a):
    """(radial, attack) for weapon w firing projectile p: whether its volley
    is fired all around, and the attack with "spray" set to the fan of an
    aimed volley (Source.spray). Without the export's "spray" (or with
    SPRAY_RATING off) a volley of 3 or more is radial, as before."""
    moving = (p or {}).get("motion") in ("straight", "path") and placement != "track"
    fan = w.get("spray")
    if not SPRAY_RATING or fan is None:
        return w.get("count", 1.0) >= 3 and moving, dict(a, spray=0.0)
    if fan >= RADIAL_SPRAY_DEG:
        return moving and w.get("count", 1.0) >= 2, dict(a, spray=0.0)
    return False, dict(a, spray=float(fan) if moving and w.get("count", 1.0) >= 2 else 0.0)


def _flatten_attack(a, out, multiplier=1.0, depth=0, parent_camo=True, follows=False, tower_range=None):
    """Add an attack's damage sources (per weapon) to out.
    follows: the tower is a helicopter that flies to the bloons (global reach).
    tower_range: the owning tower's range (see _attack_range)."""
    targeting = a.get("targeting", "normal")
    if targeting in ("point", "cursor"):
        return
    a = dict(a, range=_attack_range(a, tower_range))
    share_crowd, share_single = _sector_shares(a)
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
    trigger_rate = _trigger_rates(weapons)
    attack_placement, attack = placement, a
    for i, w in enumerate(weapons):
        placement, a = attack_placement, attack
        if _drops_under_plane(a, w):
            placement = "drop"
            a = dict(a, over_track_only=bool(w.get("over_track_only")))
        rate = w.get("rate", 1.0)
        if w.get("triggered"):
            if i not in trigger_rate:
                continue      # nothing fires it: its own rate is only a readiness check
            rate = trigger_rate[i]
        rate = max(rate, w.get("rate_min", 0.0), 1e-3)
        if placement == "drop":
            a = dict(a, cooldown=rate)      # for the over-track volleys (_drop_share)
        shots = multiplier * w.get("count", 1.0) * w.get("burst", 1.0) / rate
        p = w.get("projectile")
        life = (p or {}).get("lifespan") or 0.0
        if w.get("projectile_limit") and life > 0:
            # only so many of its projectiles may exist at once
            shots = min(shots, multiplier * w["projectile_limit"] / life)
        cap = w.get("max_subtowers") or MAX_SUBTOWERS
        radial, a = _spray(w, p, placement, a)
        travel = ((p or {}).get("speed") or 0.0) * ((p or {}).get("lifespan") or 0.0)
        if w.get("crit") and p and p.get("damage"):
            # one shot in `every` does crit damage instead: average it in
            c = w["crit"]
            extra = (c["damage"] - p["damage"]["amount"]) / max(c["every"], 1.0)
            p = dict(p, damage=dict(p["damage"], amount=p["damage"]["amount"] + max(0.0, extra)))
        crowd, single = shots * share_crowd, shots * share_single
        if w.get("triggered"):
            # A weapon fired by another one (FireWhenAlternateWeaponIsReady:
            # every such weapon in the export is a Buccaneer's "Secondary"
            # dart, grape shot or cannon) shoots a second copy at 180 degrees
            # "if bloons are detected behind" (fandom:Grape_Shot_(BTD6),
            # fandom:Destroyer_(BTD6)). It used to fire at its trigger's full
            # rate; station_for now keeps it only where the boat's range
            # holds track behind it as well, inside the cone its target must
            # stand in (the export's "target_fov": 90 degrees; _rear_copies,
            # docs/model_audit_military.md M5).
            a = dict(a, rear_fov=w.get("target_fov") or 180.0)
        main_share = 1.0
        if w.get("alternate"):
            # every `every`-th shot fires the alternate projectile INSTEAD of
            # the normal one: Recursive Cluster's "every second shot,
            # replaced with Recursive Bomb" (fandom:Recursive_Cluster), the
            # Spectre's barrage that "alternates between launching Dart and
            # Shell" (fandom:Spectre_(BTD6)), a Ninja's every-4th Flash Bomb.
            # Both used to be counted at the normal shot's full rate
            # (docs/model_audit_primary.md F9, military M8).
            main_share = 1.0 - 1.0 / max(w["alternate"].get("every", 1.0), 1.0)
        _flatten_projectile(p, crowd * main_share, single * main_share, a, camo_chain and parent_camo, placement,
                            radial, travel, out, depth, subtower_cap=cap)
        if w.get("alternate"):
            alt = w["alternate"]
            # the replaced shots fire the alternate's own emission instead of the weapon's
            k = alt.get("count", 1.0) / max(w.get("count", 1.0), 1.0) / max(alt.get("every", 1.0), 1.0)
            _flatten_projectile(alt["projectile"], crowd * k, single * k, a, camo_chain, placement, radial, travel,
                                out, depth)
        if w.get("extra_projectile"):
            _flatten_projectile(w["extra_projectile"], crowd, single, a, camo_chain, placement, radial, travel,
                                out, depth)


def _pulse_at_tower(a, entry):
    """An attack the export calls map-wide ("unbounded": "map") whose every
    projectile is a static pulse, on a tower that stays where it stands (no
    air unit, not aimed by hand), works only around the tower: read it as
    "self" with its pulses' radius as own_radius. Returns the attack as it is
    otherwise.

    The case: the Monkey Sub's submerged pulse (3-x-x Submerge and Support,
    4-x-x Bloontonium Reactor). The export marks it "map" because the sub is
    a map-wide tower in the game's model (TowerModel.isGlobalRange, for
    Advanced Intel), so the damage model let one Reactor's 100-pierce
    radiation burn the whole track. Bazaar Half Cash (2026-11-09 08:45 and
    21:03, loss cases 20261109_084520 / 20261109_210310) stood three
    Reactors in the canal; the model rated round 63 2.20 (1.51 without one
    Reactor), and the round's ceramics and leads took 100 lives in nine
    seconds. In the game the pulse is a 52-unit circle around the sub."""
    if a.get("unbounded") != "map" or a.get("air") or entry.get("air_unit") \
            or a.get("targeting") in ("point", "cursor"):
        return a
    projectiles = [w.get("projectile") or {} for w in a.get("weapons", [])]
    if not projectiles or any(p.get("motion") != "static" for p in projectiles):
        return a
    radius = max(p.get("radius") or 0.0 for p in projectiles)
    if radius <= 0.0:
        return a
    return dict(a, unbounded="self", own_radius=radius)


def _zone_radius(a, entry):
    """{"zone_radius", "zone_fixed"} for a tower's own attack a: the circle
    around the tower that attack works in, when it is not the tower's range.

    A station used to give every source of a tower the tower's largest
    reach. Glaive Lord's orbiting glaives (a 30-unit circle, "unbuffable
    range": fandom:Glaive_Lord_(BTD6)) were credited over the 43-unit throw
    circle, and a Desperado's 40-unit pistol over its 80-unit rifle circle
    (docs/model_audit_primary.md F4). Now each attack keeps its own radius:
    its range, or for an attack that sweeps the tower's own spot ("self")
    its projectiles' radius, which range buffs do not change. Attacks of a
    plane (pattern) and map-wide ones keep the tower's reach (None)."""
    if a.get("pattern_radius") or a.get("air"):
        return {}
    if a.get("unbounded") == "self":
        radius = a.get("own_radius") or 0.0
        return {"zone_radius": radius, "zone_fixed": True} if radius > 0.0 else {}
    radius = _attack_range(a, entry.get("range"))
    if 0.0 < radius < 1000.0:
        return {"zone_radius": radius}
    return {}


SUBMERGED_PREFIX = "SubmergedAttack"


def _surfaced_or_submerged(entry):
    """The attacks a tower uses as the bot plays it.

    A Monkey Sub with Submerge and Support (3-x-x and up) has a submerged
    attack (the export's "SubmergedAttack..." pulse) beside its darts.
    Upgrading sets Submerge targeting by itself and the bot never changes
    it, and "while set on Submerge targeting, it cannot attack with darts"
    (fandom:Submerge_and_Support_(BTD6), fandom:Bloontonium_Reactor). The
    darts were counted on top of the pulse (docs/model_audit_military.md
    M12); now such a sub has only its submerged attacks."""
    attacks = entry.get("attacks", [])
    submerged = [a for a in attacks if str(a.get("name", "")).startswith(SUBMERGED_PREFIX)]
    return submerged or attacks


# ===========================================================================
# Heroes
# ===========================================================================

# Heroes are rated (docs/model_fix_plan.md item 7, docs/model_audit_support_
# heroes.md finding 1). Before, every consumer dropped the hero: the optimizer
# paid $540-2,160 for it and counted nothing, so it never chose one by value,
# and Etienne's map-wide camo or Obyn's Druid buffs were invisible. A hero is
# a tower of kind "hero:<id>" whose tiers are (level,), at the level the
# bot's own estimate gives for the round (abilities.estimate_hero_level);
# forecast.py and tools/optimize_builds.py add it to the board. False leaves
# every hero out again, as before phase 2.
#
# Calibrated on the same 7,735 journal rounds as phase 1 (526 leaked; the
# hero at its estimated level, Monkey Education counted outside CHIMPS):
# separation of leaked from held rounds (AUC) 0.805 -> 0.815, rounds at or
# above 2.0 that leaked 0.52% -> 0.52%, at or above 1.5 0.63% -> 0.64%,
# and held rounds under 2.0 58.9% -> 56.6% (the planner over-defends fewer
# of them). Obyn boards rose a median x1.03, Quincy x1.01, Psi x1.15.
HERO_RATING = True

HERO_PREFIX = "hero:"

# Heroes whose export cannot be rated as it stands. Corvus's mana spells
# (Ancestral Might, Malevolence) are exported as permanent attacks, while in
# the game they cost mana and drain it every second, and his permanent
# Spirit is missing (fandom:Corvus; audit section 4.2): rated from the
# export he would read as the strongest hero in the game. He stays out
# until his spellbook is modelled.
UNRATED_HEROES = {"corvus": "mana spells exported as permanent attacks; spellbook not modelled"}


def hero_kind(hero):
    """The model's tower kind of a hero ("obyn" -> "hero:obyn")."""
    return HERO_PREFIX + str(hero)


def hero_of(kind):
    """The hero id of a hero kind ("hero:obyn" -> "obyn"), or None for a tower."""
    return kind[len(HERO_PREFIX):] if isinstance(kind, str) and kind.startswith(HERO_PREFIX) else None


def hero_entry(hero, level):
    """The exported model of one hero level (attacks.json "heroes"), or None
    (no such hero, or one of UNRATED_HEROES)."""
    if hero in UNRATED_HEROES:
        return None
    levels = ((attacks().get("heroes") or {}).get(hero) or {}).get("levels") or {}
    if not levels:
        return None
    top = max(int(k) for k in levels)
    return levels.get(str(min(max(int(level), 1), top)))


def _hero_weapons(entry):
    """A hero level with Quincy's LongWeapon left out where a MainWeapon fires
    beside it: since v57 the long shot is his Focus mode, an alternative to
    the main arrow at the same rate, not a second arrow (fandom:Quincy_(BTD6);
    docs/model_audit_primary.md section 4). Counted as well it doubled him."""
    out = []
    for a in entry.get("attacks", []):
        names = {w.get("name") for w in a.get("weapons", [])}
        if "MainWeapon" in names and "LongWeapon" in names:
            a = dict(a, weapons=[w for w in a["weapons"] if w.get("name") != "LongWeapon"])
        out.append(a)
    return dict(entry, attacks=out)


def _subtower_buffs(entry):
    """Support buffs carried by the sub-towers a tower makes (its attacks'
    projectiles' "subtowers"), as buffs of the tower itself.

    Etienne's level-8 UAV is such a sub-tower: "all non-Paragon towers on
    screen will now receive external camo detection" (fandom:Etienne_(BTD6))
    is a camo buff with "global" on the UAV, and the tower's own buffs list
    holds only a range buff. profile() read the tower's list alone, so the
    map-wide camo was lost (docs/model_audit_support_heroes.md G1)."""
    out = []

    def walk(p, depth=0):
        if not p or depth > 8:
            return
        for t in p.get("subtowers", []):
            out.extend(t.get("buffs") or [])
            for a in t.get("attacks", []):
                for w in a.get("weapons", []):
                    walk(w.get("projectile"), depth + 1)
        for s in p.get("spawn", []):
            walk(s.get("projectile"), depth + 1)

    for a in entry.get("attacks", []):
        for w in a.get("weapons", []):
            walk(w.get("projectile"))
    return out


# ===========================================================================
# Abilities, credited by their uptime
# ===========================================================================

# The bot presses the abilities it may blindly press on cooldown, and the
# MOAB ones in blimp rounds (abilities.py), so their effect is part of the
# defence (docs/model_fix_plan.md item 8; docs/model_audit_primary.md F2,
# military M10, support V4/S2). Each pressed ability counts at its uptime,
# min(1, duration / cooldown): MOAB Eliminator's 4,500-damage missile once
# every 10 s, Super Maelstrom's blades 9 s in 20, Call to Arms' x1.5 attack
# speed and pierce 15 s in 45 (+42% on average for a pierce-bound tower),
# Homeland Defense's x2 20 s in 45 (+133%). Abilities the bot never presses
# blind ('never' in abilities.TOWER_ABILITIES and towers.HEROES: First
# Strike, Overclock, Blood Sacrifice) count nothing. The average reading
# is the cautious one: the bot also saves nothing for a heavy round.
# Two more cautious rules came out of the calibration: an ability adds only
# to layers its tower can hit without it (_own_attack_hits), and an
# ability's map-wide blast meets only the bloons on the track (_bloons_met).
# False leaves every ability out again.
#
# Calibrated on the same rounds as the heroes (item 7): AUC 0.815 -> 0.813,
# rounds at or above 2.0 that leaked 0.52% -> 0.54% (0.53% at the cut that
# rejects as many held rounds as 2.0 did before), held rounds under 2.0
# 56.7% -> 54.6%: no clear change either way, so it stays on. Before the two
# rules, three Ground Zero aces rated a lost Quad Impoppable round 16.0.
ABILITY_RATING = True

# Uses of abilities.TOWER_ABILITIES / towers.HEROES that the bot presses
# without a target click.
PRESSED_USES = ("on_cooldown", "moab")


def _squash(text):
    return "".join(c for c in str(text or "").lower() if c.isalnum())


@lru_cache(maxsize=None)
def _tower_ability_uses():
    """{(tower kind, exported ability name): the bot's use of it} for every
    tower ability of abilities.TOWER_ABILITIES.

    The export names an ability by the game's display name ("Assassinate
    MOAB", "Sabotage") and the bot by the upgrade that brings it ("MOAB
    Assassin", "Bloon Sabotage"). They are matched on the one-path
    crosspath of that upgrade: the ability that appears at that tier and
    not one below (by name where the names agree, else the only new one,
    else the one with the bot's cooldown). An ability that replaces one the
    bot knows on a higher tier of the same path, under a name the bot does
    not list, keeps its button and so its use: Perma Charge (0-5-0) is
    pressed as the Turbo Charge it replaces."""
    from .abilities import TOWER_ABILITIES, TOWER_ABILITY_AT
    out = {}
    towers = attacks().get("towers") or {}
    for kind, entry in towers.items():
        cps = entry.get("crosspaths") or {}
        for path in (1, 2, 3):
            before, last = set(), None
            for tier in range(1, 6):
                code = ["0", "0", "0"]
                code[path - 1] = str(tier)
                here = cps.get("".join(code), {}).get("abilities") or []
                new = [a for a in here if _squash(a.get("name")) not in before and not a.get("interval")]
                before = {_squash(a.get("name")) for a in here}
                name = TOWER_ABILITY_AT.get((kind, path, tier))
                if name is None:
                    if last is not None and len(new) == 1:
                        out[(kind, new[0].get("name"))] = last        # the button stays
                    continue
                same = [a for a in new if _squash(name) in (_squash(a.get("name")), _squash(a.get("upgrade")))
                        or _squash(a.get("name")) in _squash(name)]
                pick = same[0] if same else new[0] if len(new) == 1 else next(
                    (a for a in new if a.get("cooldown") == TOWER_ABILITIES[name][0]), None)
                if pick is not None:
                    out[(kind, pick.get("name"))] = last = TOWER_ABILITIES[name][1]
    return out


def _hero_ability_use(hero, name):
    """The bot's use of a hero ability (towers.HEROES), matched by name; None
    when the bot does not list it."""
    from .towers import HEROES
    for ab in (HEROES.get(hero) or {}).get("abilities", []):
        mine, theirs = _squash(ab["name"]), _squash(name)
        if mine and (mine in theirs or theirs in mine or mine[:8] == theirs[:8]):
            return ab.get("use")
    return None


def _pressed_abilities(kind, tiers, entry):
    """The exported abilities of a tower crosspath or hero level that the bot
    uses: pressed blind (PRESSED_USES) or cast by the tower itself on an
    interval (Carpet of Spikes' Spike Storm every 15 s). [] when
    ABILITY_RATING is off."""
    if not ABILITY_RATING:
        return []
    hero = hero_of(kind)
    out = []
    for ab in entry.get("abilities") or []:
        if ab.get("interval"):
            out.append(ab)
            continue
        use = (_hero_ability_use(hero, ab.get("name")) if hero is not None
               else _tower_ability_uses().get((kind, ab.get("name"))))
        if use in PRESSED_USES:
            out.append(ab)
    return out


@lru_cache(maxsize=None)
def _own_attack_hits(kind, tiers, lay):
    """Can one of the tower's own attacks (no ability) damage this layer?

    An ability is credited only on layers its tower can hit without it. Its
    uptime is an average, and on a layer nothing else of the tower touches
    the average decides alone: Obyn's Brambles (100 pierce of track thorns
    every 30 s) were the only camo answer of a Ship Capture Half Cash board
    and lifted round 24 from the floor to 2.77, a round that lost lives
    (calibration of item 8). The cautious reading: an ability adds strength,
    not a capability the bot would rely on between presses."""
    p = profile(kind, tiers)
    return p is not None and any(s.can_hit(lay) for s in p.sources if not s.ability)


def _uptime(ab, duration):
    """Share of the time an ability's effect of `duration` seconds is up
    when it is pressed on every cooldown (or cast on every interval)."""
    every = ab.get("interval") or ab.get("cooldown") or 0.0
    if every <= 0.0 or not duration:
        return 0.0
    return min(1.0, float(duration) / float(every))


def _ability_attacks(ab):
    """The attacks of an ability as attacks that fire at their average rate:
    every weapon fires as many volleys per cooldown as it does while the
    ability is up - one for a one-shot ability (MOAB Eliminator: one missile
    every 10 s), duration / rate for one that keeps firing (Super
    Maelstrom: 9 s / 0.045 s = 200 volleys every 20 s; Spike Storm: 2 s /
    0.04 s = 50 piles per attack, 200 in all)."""
    every = ab.get("interval") or ab.get("cooldown") or 0.0
    if every <= 0.0:
        return []
    out = []
    for a in ab.get("attacks") or []:
        weapons = []
        for w in a.get("weapons", []):
            rate = max(w.get("rate", 1.0), w.get("rate_min", 0.0), 1e-3)
            duration = a.get("duration") or 0.0
            volleys = 1.0 if (a.get("one_shot") or duration <= rate) else duration / rate
            weapons.append({k: v for k, v in w.items() if k != "rate_min"} | {"rate": every / volleys})
        out.append(dict(a, weapons=weapons))
    return out


def _ability_buffs(ab):
    """Timed buffs of an ability to other towers (Call to Arms, Homeland
    Defense, Absolute Zero's Ice Monkey speed), as buffs that cover their
    uptime share of the buffed towers' shots (Source shares, see
    _buffed_sources); one "group" per ability, as the game does not let a
    second press stack on an active buff."""
    out = []
    for b in ab.get("buffs") or []:
        share = _uptime(ab, b.get("duration"))
        if share > 0.0:
            out.append(dict(b, share=share, group=_squash(ab.get("name")), ability=True))
    return out


def _ability_boosts(ab, entry, kind):
    """Boosts of an ability to the tower's own attacks: TurboModel (Turbo
    Charge: weapon rate x0.2 and +1 damage for 10 s of 45) and DamageUp
    (Perma Charge: +10 damage for 15 s of 45), and its timed buffs where
    they reach the tower itself (Absolute Zero speeds up its own Ice
    Monkey). [{"share", "rate", "damage_add"}]."""
    out = []
    own = ab.get("self") or {}
    share = _uptime(ab, own.get("duration"))
    if share > 0.0:
        out.append({"share": share, "rate": own.get("rate") or 1.0, "damage_add": own.get("damage_add") or 0.0})
    game_id = ((attacks().get("towers") or {}).get(kind) or {}).get("game_id")
    for b in ab.get("buffs") or []:
        if b.get("kind") == "rate" and b.get("towers") and game_id in b["towers"]:
            share = _uptime(ab, b.get("duration"))
            if share > 0.0:
                out.append({"share": share, "rate": b.get("value") or 1.0, "damage_add": 0.0})
    return out


@lru_cache(maxsize=None)
def profile(kind, tiers):
    """Profile of a tower crosspath, or of a hero at a level (kind
    "hero:<id>", tiers (level,)); None when the game has no such model."""
    hero = hero_of(kind)
    if hero is not None:
        entry = hero_entry(hero, tuple(tiers)[0] if tiers else 1)
        if entry is None:
            return None
        entry = _hero_weapons(entry)
        tiers = tuple(int(t) for t in tiers)
    else:
        entry = crosspath(kind, tiers)
        if entry is None:
            return None
        tiers = tuple(int(t) for t in tiers_code(tiers))
    sources = []
    aim_bound = False
    follows = (entry.get("air_unit") or {}).get("movement") == "follows"
    entry = dict(entry, attacks=[_pulse_at_tower(a, entry) for a in _surfaced_or_submerged(entry)])
    for a in entry.get("attacks", []):
        if a.get("targeting") in ("point", "cursor") and any(
                (w.get("projectile") or {}) for w in a.get("weapons", [])):
            aim_bound = True
        _flatten_attack(dict(a, **_zone_radius(a, entry)), sources, follows=follows, tower_range=entry.get("range"))
    income = (entry.get("income") or {})
    pattern = max((a.get("pattern_radius") or 0.0 for a in entry.get("attacks", [])), default=0.0)
    own = max((a.get("own_radius") or 0.0 for a in entry.get("attacks", []) if a.get("unbounded") == "self"),
              default=0.0)
    # The export calls an ace with pineapples or Bomber Ace bombs map-wide
    # ("global") only because of those bombs' "unbounded": "map"; they fall
    # under the plane (_drops_under_plane), so the ace itself is not map-wide.
    map_wide = [a for a in entry.get("attacks", []) if a.get("unbounded") == "map"]
    is_global = bool(entry.get("global")) and not (
        map_wide and all(_drops_under_plane(a, w) for a in map_wide for w in a.get("weapons", [])))
    pressed = _pressed_abilities(kind, tiers, entry)
    for ab in pressed:
        # the ability's attacks and the towers it makes, at their uptime;
        # marked (Source.ability) so a board whose abilities the bot does
        # not press can leave them out (station_for: pressed)
        extra = []
        for a in _ability_attacks(ab):
            _flatten_attack(dict(a, **_zone_radius(a, entry)), extra, tower_range=entry.get("range"))
        for made in ab.get("towers") or ():
            share = _uptime(ab, made.get("duration"))
            for a in made.get("attacks", []):
                _flatten_attack(a, extra, multiplier=share, tower_range=made.get("range"))
        use = (_hero_ability_use(hero_of(kind), ab.get("name")) if hero_of(kind) is not None
               else _tower_ability_uses().get((kind, ab.get("name")))) or ""
        for s in extra:
            s.ability = ab.get("name") or "ability"
            s.ability_use = "interval" if ab.get("interval") else use
        sources += extra
    return Profile(kind=kind, tiers=tiers, range=entry.get("range", 0.0),
                   is_global=is_global, sources=sources, aim_bound=aim_bound and not sources,
                   buffs=list(entry.get("buffs", [])) + _subtower_buffs(entry) + _potion_buffs(entry)
                   + [b for ab in pressed for b in _ability_buffs(ab)],
                   boosts=[b for ab in pressed for b in _ability_boosts(ab, entry, kind)],
                   zones=list(entry.get("zones") or []),
                   income=income.get("per_round", 0.0) + income.get("bananas_per_round", 0.0),
                   pattern_radius=pattern, own_radius=own,
                   flight_speed=float((entry.get("air_unit") or {}).get("speed") or 0.0),
                   fire_rate=sum(w.get("burst", 1.0) / max(w.get("rate", 1.0), w.get("rate_min", 0.0), 1e-3)
                                 for a in entry.get("attacks", []) for w in a.get("weapons", [])
                                 if not w.get("triggered") and w.get("projectile")))


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


def map_routes(geom, with_keys=False):
    """How bloons cross the map: (routes, scenarios), and with `with_keys`
    (routes, scenarios, keys).

    routes: [{"paths": [path ids in order], "moab": None | True | False}]
        a route is the sequence of paths one bloon follows from its spawn to
        the exit; "moab" True = only MOAB-class bloons take it (Quiet
        Street's MOAB lane), False = only non-MOAB bloons, None = all.
    scenarios: [[route indices]] - each round uses ONE scenario. Maps whose
        spawn alternates by round (Luminous Cove, Enchanted Glade, Last
        Resort: AlternateRoundSplitter) have one scenario per alternative;
        the evaluator plays each round in the scenarios it really uses
        (Track.scenarios_in; every one when the round is unknown) and
        keeps the worst. Within a scenario bloons are shared evenly by the routes
        open to their class (Party Parade's two lanes, Castle Revenge's
        four gates).
    keys: [path id or None] per scenario - the alternative path it was made
        for (None: the map has one scenario), so Track.scenarios_in can
        tell which scenarios a round really uses.

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
        return ([], [], []) if with_keys else ([], [])
    names = {p.get("name"): pid for pid, p in paths.items()}
    ends = {pid: np.asarray(p["points"][-1][:2], float) for pid, p in paths.items()}
    starts_xy = {pid: np.asarray(p["points"][0][:2], float) for pid, p in paths.items()}

    def leads_back(src, p):
        """Path p ends where src starts and does not start where src ends:
        it comes before src, so a splitter naming it is for Reverse."""
        return (np.linalg.norm(ends[p] - starts_xy[src]) <= JOIN_DISTANCE
                and np.linalg.norm(ends[src] - starts_xy[p]) > JOIN_DISTANCE)
    # continuations: named plain/toggle splitters first, then geometry. A map
    # may carry a second set of splitters for Reverse, naming each path's
    # predecessor (Workshop: "P1" -> PathMiddle1 and "P1" -> PathStart); those
    # are not continuations. Kept, they turned Workshop's belt into a loop
    # whose only routes were two short stretches (78 and 100 units of 440),
    # and the live model rated Workshop Medium's rounds 0.06-0.8 while no
    # bloon got past 37% of the track (loss case 20261108_184916).
    follow = {pid: [] for pid in paths}
    for s in splitters:
        src = names.get(s.get("name"))
        if src is not None and s.get("type") in ("Splitter", "ToggleSplitter"):
            follow[src] += [p for p in s.get("paths") or [] if p in paths and p != src
                            and not leads_back(src, p)]
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
    # A MOAB-only branch onto a hidden path (Workshop's chute, switched on
    # after round 39): MOAB-class bloons drop out of sight and come out on
    # the belt where the chute ends. Their route is what follows the chute,
    # for MOAB-class bloons only - without it they rode the whole belt in
    # the model, which is far longer than the real drop.
    by_id = {p["id"]: p for p in geom.get("paths", [])}
    for pid, is_moab in list(moab_flag.items()):
        hp = by_id.get(pid)
        if not is_moab or pid in paths or hp is None or not hp.get("hidden") or pid not in usable:
            continue
        drop = np.asarray(hp["points"][-1][:2], float)
        nxt = [p for s in splitters if s.get("name") == hp.get("name") and s.get("type") == "Splitter"
               for p in s.get("paths") or [] if p in paths
               and np.linalg.norm(starts_xy[p] - drop) <= JOIN_DISTANCE]
        for p in nxt:
            before = len(routes)
            walk([p])
            for r in routes[before:]:
                r["moab"] = True
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
    scenarios, keys = [], []
    if alt_paths:
        for p in dict.fromkeys(alt_paths):
            idx = [i for i, r in enumerate(routes) if p in r["paths"]]
            if idx:
                scenarios.append(idx)
                keys.append(p)
        others = [i for i, r in enumerate(routes) if not any(p in r["paths"] for p in alt_paths)]
        scenarios = [sorted(set(s) | set(others)) for s in scenarios]
    if not scenarios:
        scenarios, keys = [list(range(len(routes)))], [None]
    return (routes, scenarios, keys) if with_keys else (routes, scenarios)


# Maps whose towers are switched off for part of the game: (rounds off,
# cycle length in rounds). Glacial Trail freezes every tower in ice for 2
# rounds in 10, counted from that tower's own placement round
# (docs/placement.md, "Map specials"). The model does not know each tower's
# phase, so it counts the average: a tower works (cycle - off) / cycle of
# the time, and every round is rated at that share of the build's strength.
# (Glacial Trail Medium 2026-11-03 was rated safe and lost at round 25 with
# most boomerangs frozen.)
TOWER_FREEZE = {"Glacial Trail": (2, 10)}

# The first frozen round, counted from the round a tower was placed in (the
# round on the HUD when it was bought). Read off two lost games whose whole
# defence was bought in one round: placed in round 22 -> free in round 30,
# frozen in round 31 (Glacial Trail ABR 2026-11-09, end_025/end_028.jpg);
# placed in round 15 -> free in 22, frozen in 25 (Medium 2026-11-07). So a
# tower placed in round p is frozen in rounds p+9, p+10, p+19, p+20, ...
FREEZE_FIRST_OFFSET = 9


def _freeze_cycle(map_name):
    """(rounds off, cycle length) of the map's tower freeze, (0, 1) where
    towers never freeze. Takes the display name or the file key, with or
    without the " reverse" of a Reverse game's map model: the ice is the
    same either way. Glacial Trail Reverse (2026-11-11, loss case
    20261111_080458_GlacialTrail_reverse) looked up "Glacial Trail reverse",
    found no freeze, and forgot the frozen sp1 as "not on the map" - its
    Spiked Mines, the round-40+ answer, was never bought."""
    name = str(map_name)
    if name.lower().endswith(" reverse"):
        name = name[:-len(" reverse")]
    key = "".join(c for c in name.lower() if c.isalnum())
    if key.endswith("reverse") and key[:-len("reverse")] in {
            "".join(c for c in m.lower() if c.isalnum()) for m in TOWER_FREEZE}:
        key = key[:-len("reverse")]        # the file key of a Reverse model ("glacialtrailreverse")
    by_key = {"".join(c for c in m.lower() if c.isalnum()): v for m, v in TOWER_FREEZE.items()}
    return by_key.get(key, (0, 1))


def tower_uptime(map_name):
    """Share of the time a tower on this map can attack (1.0 on maps that
    never switch towers off; see TOWER_FREEZE). Takes the display name or
    the file key ("Glacial Trail" or "glacialtrail")."""
    off, cycle = _freeze_cycle(map_name)
    return (cycle - off) / cycle


def frozen_in(map_name, placed_round, rnd):
    """True when a tower placed in `placed_round` sits in ice during round
    `rnd` on this map (False on maps without a freeze, or when either round
    is unknown). Towers bought in the same round share one phase, so a
    Fast Track opening bought in one round freezes all at once - the
    average uptime hides that round (backlog 18)."""
    off, cycle = _freeze_cycle(map_name)
    if not off or placed_round is None or rnd is None:
        return False
    since = rnd - placed_round - FREEZE_FIRST_OFFSET
    return since >= 0 and since % cycle < off


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
        self.uptime = tower_uptime(map_name)   # < 1 where towers freeze
        self.geom = G.load(map_name)
        if self.geom is None:
            raise ValueError(f"no geometry for map {map_name!r}")
        self.playfield = LAYOUTS["16:10"]["playfield"]
        self.proj = G.Projection(self.playfield)
        by_id = {p["id"]: p for p in self.geom.get("paths", [])}
        routes, self.scenarios, self.scenario_paths = map_routes(self.geom, with_keys=True)
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

    def scenarios_in(self, rnd):
        """Indices of the scenarios round `rnd` really uses: those whose
        alternative path carries bloons that round (mapgeom.
        live_alternatives - Erosion's phase path, with the next one from
        PHASE_LEAD rounds before it starts; the path of the round on maps
        that alternate every round; Bloonarius Prime's prime lane on prime
        rounds). Every scenario when the round is unknown or the map does
        not say.

        Rated against all of them, a round was as weak as the worst path
        it never takes: two 2-0-2 ninjas beside Erosion's Path1 rated
        round 5 at the 0.0625 floor and 5.97 on Path1 alone, so every
        Erosion round read as a crisis (panic and reinforce spending,
        Deflation's too_weak_to_start); Last Resort rated each round
        against all four loops of its 4-round cycle."""
        every = list(range(len(self.scenarios)))
        if len(every) < 2:
            return every
        from . import mapgeom as G
        live = G.live_alternatives(self.geom, rnd)
        if not live:
            return every
        used = [k for k, p in enumerate(self.scenario_paths) if p is None or p in live]
        return used or every

    # -- screen <-> world -------------------------------------------------------
    def heights(self):
        """Grid (as MapModel cells) of the height of the highest non-track
        area at each cell: a tower standing there is that high, which the
        tilted camera shows HEIGHT_FACTOR x height further up the screen.

        Areas present at the start count, except unplaceable ones the map
        removes by itself (mapgeom.dynamics().vanish): no tower stands on
        one while it is there, so a tower in its outline was placed after
        it went, on the ground below. One Two Tree's BlockerPlots stand 60
        high and open during the game; counted, a tower on an opened plot
        was read 60 high, about 33 units off on the screen (dynamic-map
        audit 2026-11-12, item 14). Ground that vanishes but holds towers
        while it lasts (Erosion's ice, 10 high) is kept: the towers on it
        stand at its height, and only a sub put in the water after the
        melt reads a few units high."""
        if self._heights is None:
            from . import mapgeom as G
            from .maplearn import GRID
            top = np.zeros((GRID[1], GRID[0]), np.float32)
            present = G.starting_areas(self.geom)
            goes = set(G.dynamics(self.geom).vanish)
            for i, area in enumerate(self.geom.get("areas", [])):
                aid = G._area_id(area, i)
                if area.get("type") == "unplaceable" and aid in goes:
                    continue
                if aid in present and area.get("type") != "track":
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
    def near_track(self, pts, radius):
        """Bool per (x, z) point of `pts`: lies within `radius` of a hittable
        stretch of some route (see Track: tunnels and off-screen parts do
        not count)."""
        hit = getattr(self, "_hittable_xz", None)
        if hit is None:
            hit = self._hittable_xz = np.concatenate([p["xyz"][p["hittable"], :2] for p in self.paths])
        pts = np.asarray(pts, float).reshape(-1, 2)
        if not len(hit) or not len(pts):
            return np.zeros(len(pts), bool)
        d2 = ((pts[:, None, 0] - hit[None, :, 0]) ** 2 + (pts[:, None, 1] - hit[None, :, 1]) ** 2).min(axis=1)
        return d2 <= radius * radius

    def behind_share(self, x, z, radius, fov=180.0):
        """Share of the hittable track within `radius` of (x, z) that has more
        track on the far side of the tower: seen from the tower, some other
        covered point lies inside the cone of `fov` degrees pointing straight
        away from it (behind the tower when it faces that point). 0 when the
        circle covers no track. Used for a Buccaneer's rear shot
        (_rear_copies), with bloons all along the covered track."""
        pts = np.concatenate([p["xyz"][p["hittable"], :2] for p in self.paths])
        d2 = (pts[:, 0] - x) ** 2 + (pts[:, 1] - z) ** 2
        pts = pts[d2 <= radius * radius]
        if not len(pts):
            return 0.0
        bins = 72                                   # 5-degree sectors
        ang = np.arctan2(pts[:, 1] - z, pts[:, 0] - x)
        idx = ((ang + math.pi) / (2.0 * math.pi) * bins).astype(int) % bins
        count = np.bincount(idx, minlength=bins)
        occupied = count > 0
        half_cone = int(round(fov / 2.0 / (360.0 / bins)))
        behind = np.zeros(bins, bool)
        for i in range(bins):
            far = [(i + bins // 2 + k) % bins for k in range(-half_cone, half_cone + 1)]
            behind[i] = occupied[far].any()
        return float(count[behind].sum() / count.sum())

    def total_length(self):
        """Hittable length of each path (world units)."""
        return [float(np.sum(np.diff(p["dist"])[p["hittable"][:-1]])) for p in self.paths]

    def zones(self, x, z, radius, travel=0.0, sight=None, lent=()):
        """[Zone or None per path] for a reach of `radius` around (x, z).
        radius None or inf = the whole hittable path. sight(x0, z0, pts) ->
        bool mask of points visible from the tower (line of sight), optional.
        lent: more (x, z, radius) circles the tower may also shoot into
        (an Advanced Intel sub borrows other towers' ranges, station_for)."""
        out = []
        for p in self.paths:
            xyz, dist, ok = p["xyz"], p["dist"], p["hittable"]
            if radius is None or not math.isfinite(radius):
                inside = ok.copy()
            else:
                d2 = (xyz[:, 0] - x) ** 2 + (xyz[:, 1] - z) ** 2
                inside = ok & (d2 <= radius * radius)
                for lx, lz, lr in lent:
                    inside |= ok & (((xyz[:, 0] - lx) ** 2 + (xyz[:, 1] - lz) ** 2) <= lr * lr)
            if sight is not None and inside.any():
                # map-wide or not, a tower that needs sight hits only what it sees
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


def _delay_at(segs, x):
    """Seconds a lot has lost by distance x to the controls on its route:
    segs = ((a, b, seconds), ...), each spread evenly over [a, b]."""
    d = 0.0
    for a, b, sec in segs:
        if x >= b:
            d += sec
        elif x > a:
            d += sec * (x - a) / (b - a)
    return d


def _time_at(lot, segs, x):
    """When the lot is at distance x of its route (t0 is its time at 0
    without delays, Lot)."""
    return lot.t0 + x / lot.speed + (_delay_at(segs, x) if segs else 0.0)


def _pos_at(lot, segs, t):
    """Distance along its route the lot has reached at time t (the inverse
    of _time_at; piecewise linear between the segments' ends)."""
    if not segs:
        return (t - lot.t0) * lot.speed
    marks = sorted({0.0} | {a for a, _, _ in segs} | {b for _, b, _ in segs})
    prev_x, prev_t = 0.0, _time_at(lot, segs, 0.0)
    if t <= prev_t:
        return (t - lot.t0) * lot.speed
    for x in marks[1:]:
        tx = _time_at(lot, segs, x)
        if tx >= t:
            return prev_x + (x - prev_x) * (t - prev_t) / max(tx - prev_t, 1e-12)
        prev_x, prev_t = x, tx
    return prev_x + (t - prev_t) * lot.speed


@lru_cache(maxsize=None)
def _round_groups(set_name, rnd):
    rs = _json(str(ROUND_SETS))
    return tuple((rs.get(set_name) or {}).get(str(rnd), {}).get("groups") or ())


def _round_extra(set_name, rnd):
    """Freeplay ramps from data/rounds.json (speed_mult, blimp_hp_mult)."""
    rd = ((_json(str(ROUNDS_FILE)).get(set_name) or {}).get(str(rnd))) or {}
    return float(rd.get("speed_mult") or 1.0), float(rd.get("blimp_hp_mult") or 1.0)


def round_lots(mode, rnd, track, scenario=0, turn=None):
    """The lots of round `rnd` in `mode`, on the routes of one scenario of
    the track: each group is shared evenly by the routes its class takes
    (turn: see groups_lots)."""
    set_name = "abr" if mode == "abr" else "standard"
    speed_ramp, hp_ramp = _round_extra(set_name, rnd)
    return groups_lots(mode, _round_groups(set_name, rnd), track, scenario, rnd=rnd,
                       speed_ramp=speed_ramp, hp_ramp=hp_ramp, turn=turn)


def _undivided(top, count, routes):
    """Does a spawn group go down its routes as whole bloons rather than as
    an even share? True for blimps that are fewer than the routes open to
    them: one BFB on a map with four lanes takes one lane, whole.

    Sharing it evenly put a quarter of a BFB (175 health and one MOAB) on
    each lane of Quad, so the towers beside every lane were each rated
    against a quarter of the blimp that really passes one of them. Quad
    Deflation (2026-11-11, cases 20261111_164906 and 20261111_210232) was
    rated 4.22 and 8.18 for round 60; both times the BFB went in at the left
    gate and out at the top one with hardly a scratch. Smaller bloons come
    in numbers, and for them the even share is what the lanes see."""
    return top.moab and 1 < len(routes) and count < len(routes)


def round_turns(mode, rnd, track, scenario=0):
    """The `turn` values round `rnd` has to be played with (groups_lots):
    one per route when the round has a blimp group that is not shared
    (_undivided) - which lane the game sends it down is not known, so every
    lane gets its turn and the worst counts - and (None,) otherwise."""
    set_name = "abr" if mode == "abr" else "standard"
    most = 0
    for g in _round_groups(set_name, rnd):
        bid = g.get("id") or g["bloon"].capitalize()
        if bid not in bloon_table():
            continue
        top = layer(bid)
        routes = track.routes_for(scenario, top.moab)
        if _undivided(top, float(g["count"]), routes):
            most = max(most, len(routes))
    return tuple(range(most)) if most else (None,)


def groups_lots(mode, groups, track, scenario=0, rnd=None, speed_ramp=1.0, hp_ramp=1.0, turn=None):
    """The lots of any list of spawn groups ({"id" or "bloon", "count",
    "start_s", "end_s"}, the shape of data/game_data/round_sets.json) in
    `mode`: round_lots for a standard round, btd6bot/apopalypse.py for the
    random rounds of Apopalypse. rnd: the round, for one-round health
    changes (Easy's round-40 MOAB); speed_ramp / hp_ramp: freeplay ramps.

    turn: None shares every group evenly by its routes. A number sends the
    blimps of a group too small to share (_undivided) down the routes whole,
    one each, starting with route number `turn` of those open to them."""
    rules = mode_rules(mode)
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
        if turn is not None and _undivided(top, count, routes):
            whole = max(1, int(round(count)))
            for j in range(whole):
                lots.append(Lot(path=routes[(turn + j) % n], t0=start + span * (j + 0.5) / whole, bloon=bid,
                                count=count / whole, rho=rho, speed=speed, speed_mult=speed_mult, moab_hp=moab_hp))
            continue
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
    # paths where this tower's shared camo sight (Advanced Intel, see
    # Source.camo_shared) holds: those some camo-detecting tower reaches.
    # None = no limit (the tower shares no camo).
    camo_paths: frozenset = None
    # the same tower's local sources as a station of their own, when its
    # other sources reach the whole map (station_for); played with it
    parts: list = field(default_factory=list)
    # slow zones around the tower (Profile.zones: Arctic Wind's 40% slow)
    slow_zones: list = field(default_factory=list)
    # damage-taken debuffs and camo removal from other towers that reach
    # this one's zones, set by _Controls before a round is played
    influence: object = None

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
    if src.ability and src.reach >= MAP_BLAST_REACH and zone is not None:
        # an ability's blast that covers the whole map (Ground Zero's
        # 9,999,999-unit explosion) meets the bloons on the covered track,
        # not rho times its 20,000,000-unit "reach": uncapped, three Ground
        # Zero aces' one bomb each 35 s destroyed 57 whole bloons a second
        # each and rated Quad Impoppable's round 93 16.0 (calibration of
        # item 8, docs/model_fix_plan.md; the round lost a life). Towers'
        # own attacks keep the phase-1 reading.
        return 1.0 + rho * zone.length
    return 1.0 + rho * src.reach


# A projectile reach (Source.reach) at least this long is a map-wide blast
# (_bloons_met).
MAP_BLAST_REACH = 1000.0


def _hit_rate(src, lay, rho, zone):
    """Hits per second this source lands on bloons of this layer.

    projectiles per second (fewer for spawn-on-contact chains when bloons
    are sparse, see Source.shots_single), times hits per projectile: its
    pierce, but no more than the bloons it can meet - except that a
    lingering projectile may hit one bloon several times (single_hits)."""
    met = _bloons_met(src, rho, zone)
    if src.off_struck and not src.zone_wide and not math.isinf(met):
        # thrown off the bloon its carrier struck and flying away from it:
        # the game's frags and shrapnel never hit the struck bloon, only the
        # other bloons near that spot and the children the carrier's hit
        # left there. Counting the struck bloon itself credited every piece
        # with a hit even on a lone bloon - five Shrapnel hits per sniper
        # bullet - and rated sniper boards several times too strong on
        # spread-out rounds (Sanctuary, 2026-11-08/09; docs/optimizer.md
        # "Thrown-off pieces")
        if not _left_at_spot(src.carrier, lay):
            met -= 1.0
    sparse = lay.moab or met < 2.0
    shots = src.shots_single if sparse else src.shots
    if src.radial:
        shots *= zone.angular if zone is not None else 1.0
    elif src.spray and zone is not None:
        # an aimed fan of src.spray degrees: the track spans zone.angular of
        # the circle around the tower; a fan wider than that loses the rest
        shots *= min(1.0, zone.angular * 360.0 / src.spray)
    if src.placement == "air":
        shots *= AIR_PATTERN_EFFICIENCY
    pierce = src.pierce
    if src.pierce_cost:
        # every hit on this layer uses up 1 + its extra cost (_pierce_cost);
        # the first hit is always made
        cost = sum(c for tag, c in src.pierce_cost.items() if tag == "" or tag in lay.tags)
        pierce = max(1.0, pierce / (1.0 + cost))
    if src.refresh and src.life > 0.0:
        per_shot = _patch_hits(src, lay, rho) * pierce / max(src.pierce, 1e-9)
    elif src.off_struck:
        per_shot = min(pierce, met)
    else:
        per_shot = min(pierce, max(met, src.single_hits))
    return shots * per_shot


class _Rates:
    """Per station: how fast it takes health off one layer (bloon id) at a
    given packing, and how much damage overflows into the children."""

    def __init__(self, station):
        self.station = station
        self.cache = {}

    def get(self, bloon_id, moab_hp, rho, path):
        """(HP per second, mean overflow per ordinary pop, share of pops that
        destroy the whole bloon, mean overflow per pop of every kind) on this
        layer, or None when no source of the station can damage it (immune,
        camo, MOAB filter). See _compute."""
        key = (bloon_id, moab_hp, round(math.log2(max(rho, 1e-4)) * 2), path)
        if key not in self.cache:
            self.cache[key] = self._compute(bloon_id, moab_hp, rho, path)
        return self.cache[key]

    def _compute(self, bloon_id, moab_hp, rho, path):
        """See get(). A station's pops are of two kinds.

        Ordinary hits pass their damage beyond the layer's health on to the
        children (DamageModel.distributeToChildren): a 3-damage tack pops a
        lead and two more layers with one hit. That carry is averaged over
        the station's ordinary pops.

        A hit whose damage is at least the whole bloon's health (rbe) destroys
        the bloon and everything inside it: Druid of the Jungle's vine
        (9,999,999 damage). Such pops are kept apart as a share: their
        bloons leave no children. Averaged in with the rest, the vine's
        ~10,000,000 of overflow gave every 1-damage bramble pop beside it a
        carry of ~625,000, so one 1-3-0 druid popped ~6 whole Rainbows or
        Leads a second; the game gets ~0.4 (docs/model_audit_magic.md,
        finding 1). The last value, for the layers inside a bloon (subtree),
        averages every pop's carry, a whole-bloon hit counting what is left
        inside the bloon (its expected damage to the children)."""
        zone = self.station.zones[path]
        lay = layer(bloon_id, moab_hp)
        whole = rbe(bloon_id, moab_hp)
        hp_rate = overflow = kill_rate = kill_carry = 0.0
        camo_paths = self.station.camo_paths
        infl = self.station.influence
        bonus, seen = infl.on(lay, path, rho) if infl is not None else (0.0, 0.0)
        plain = None
        for src in self.station.sources:
            share = 1.0
            if not src.can_hit(lay):
                # camo bloons another tower stripped of their camo upstream
                # (Embrittlement, Shimmer: _Influence) are hit as plain ones
                if not (seen > 0.0 and lay.camo and not src.camo):
                    continue
                if plain is None:
                    plain = _decamo(lay)
                if not src.can_hit(plain):
                    continue
                share = seen
            if src.ability and not _own_attack_hits(self.station.kind, self.station.tiers, lay):
                continue     # an ability adds to what its tower can hit, no more (_own_attack_hits)
            if lay.camo and src.camo_shared and camo_paths is not None and path not in camo_paths:
                continue     # Advanced Intel sees camo only where a detector reaches
            hits = _hit_rate(src, lay, rho, zone) * share
            d = src.damage_vs(lay)
            if bonus and d > 0.0:
                d += bonus           # a debuffed bloon takes more from every hit (_Influence)
            if src.grip_rate:
                # a grip holds its bloon for (what it deals) / grip_rate
                # seconds, and the attack waits for it before its cooldown
                # starts again: 1 / (cooldown + 0.15 s per layer of health)
                # grips a second at level 2 (docs/model_audit_magic.md
                # finding 16); and one grip per bloon in the zone (_psi_grip)
                held = min(d, whole) / src.grip_rate
                hits = min(hits / (1.0 + src.shots * held), max(1.0, rho * zone.length) / max(held, 1e-6))
            rate = hits * min(d, lay.hp)
            hp_rate += rate
            if lay.children and d >= whole:
                kill_rate += rate          # destroys the whole bloon: no children, no carry
                kill_carry += rate * (whole - lay.hp)
            else:
                overflow += rate * max(0.0, d - lay.hp)
            if src.dot_total and not (src.dot_immune & lay.immune):
                # damage over time: every hit poisons a bloon for dot_total in
                # all; no more than the bloons in the zone, each burning at
                # dot_rate per second
                in_zone = max(1.0, rho * zone.length)
                hp_rate += min(hits * src.dot_total, in_zone * src.dot_rate)
        if hp_rate <= 0.0:
            return None
        ordinary = hp_rate - kill_rate
        carry = overflow / ordinary if ordinary > 0.0 else 0.0
        return (hp_rate * self.station.strength * TOWER_EFFICIENCY, carry, kill_rate / hp_rate,
                (overflow + kill_carry) / hp_rate)

    def subtree(self, bloon_id, moab_hp, rho, path, free):
        """(seconds of work per bloon, ((id, count), ...) handed on) to pop a
        small bloon and everything inside it that this station can pop.

        Small layers (see SMALL_LAYER_HP) are worked as one job with their
        children instead of a job per layer, which keeps the simulation fast:
        the walk adds each layer's health (less the damage carried in from
        its parent) over the HP per second on it, and stops at layers the
        station cannot damage, which are handed on to the next station.

        Hits that destroy the whole bloon it starts on (_compute) work beside
        the walk: they take `kills` whole bloons a second, the ordinary hits
        one bloon per walk, so the station gets through kills + 1 / walk
        bloons a second. Inside the bloon every hit counts at its expected
        carry (a bomb that destroys a whole Green carries its health on). A Druid of the Jungle 1-3-0 (vine every 2.6 s, brambles of 1
        damage) gets 0.38 + 5.8 / 47 = 0.51 whole Rainbows a second, the
        audit's "about 0.4" with the model's vine rate
        (docs/model_audit_magic.md, finding 1; the vine's longer digest of
        big bloons is not modelled)."""
        key = (bloon_id, moab_hp, round(math.log2(max(rho, 1e-4)) * 2), path, round(free, 1))
        hit = self.cache.get(("subtree",) + key)
        if hit is not None:
            return hit
        top = self.get(bloon_id, moab_hp, rho, path)
        kills = 0.0
        if top is not None and max(0.0, layer(bloon_id, moab_hp).hp - free) > 0.0:
            kills = top[0] * top[2] / layer(bloon_id, moab_hp).hp
        work, passed = 0.0, {}
        stack = [(bloon_id, 1.0, rho, free)]   # (id, bloons per top bloon, packing, damage carried in)
        while stack:
            bid, n, r, f = stack.pop()
            rate = self.get(bid, moab_hp, r, path)
            if rate is not None and bid == bloon_id and n == 1.0 and kills > 0.0:
                hp, overflow = rate[0] * (1.0 - rate[2]), rate[1]    # the kills are counted apart
            elif rate is not None:
                hp, overflow = rate[0], rate[3]
            else:
                hp = overflow = 0.0
            if hp <= 0.0:
                passed[bid] = passed.get(bid, 0.0) + n
                continue
            lay = layer(bid, moab_hp)
            need = max(0.0, lay.hp - f)
            carry = max(0.0, f - lay.hp) + (overflow if need > 0.0 else 0.0)
            work += n * need / hp
            kids = sum(k for _, k in lay.children) or 1
            for child, k in lay.children:
                stack.append((child, n * k, r * k, carry / kids))
        if kills > 0.0:
            ordinary = 0.0 if bloon_id in passed else (1.0 / work if work > 0.0 else math.inf)
            if math.isinf(ordinary):
                out = (work, tuple(sorted(passed.items())))
            else:
                share = ordinary / (kills + ordinary)        # bloons the ordinary hits handle
                passed = {} if bloon_id in passed else {k: v * share for k, v in passed.items()}
                out = (1.0 / (kills + ordinary), tuple(sorted(passed.items())))
        else:
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
    killed: float = 0.0    # share of the popped bloons destroyed whole (no children; _Rates._compute)


class _Server:
    """One station working through its jobs: always the unfinished job of
    the best priority that leaves the zone first (the game's "first"
    targeting; "strong" stations put MOAB-class bloons first), one second
    of work per second. A popped layer's children appear where it popped,
    as new jobs (or are handed on when the station cannot hurt them).

    A banked station (spike piles) is never idle: while no bloon is in its
    zone it builds stock, up to bank_seconds of production, starting from
    bank_start left over from the last round, and spends it instantly."""

    def __init__(self, station, out, controls=None):
        self.st = station
        self.controls = controls       # _Controls: delays on the lots' routes (None: no status effects)
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
        hp_rate, overflow, killed, _ = r
        lay = layer(lot.bloon, lot.moab_hp)
        end = zone.entry + zone.length
        segs = self.segs(lot)
        if segs:
            deadline = release + max(0.0, _time_at(lot, segs, max(end, pos)) - _time_at(lot, segs, pos))
        else:
            deadline = release + max(0.0, end - pos) / lot.speed
        prio = 0 if (self.st.strong and lay.moab) else 1
        if not lay.moab and lay.hp <= SMALL_LAYER_HP:
            per_bloon, passed = self.rates.subtree(lot.bloon, lot.moab_hp, lot.rho, lot.path, free)
            work = lot.count * per_bloon
            return _Job(release, deadline, work, work, lot, zone, pos, 0.0, prio, passed)
        need = max(0.0, lay.hp - free)               # health left after the carried damage
        carry = max(0.0, free - lay.hp) + (overflow if need > 0.0 else 0.0)
        work = lot.count * need / hp_rate
        return _Job(release, deadline, work, work, lot, zone, pos, carry, prio,
                    killed=killed if need > 0.0 else 0.0)

    def segs(self, lot):
        """The delays on this lot's route (_Controls.segments), () without.
        Kept on the lot for this play (lots are shared between plays of a
        margin search, each with its own controls)."""
        if self.controls is None:
            return ()
        held = lot.__dict__.get("_segs")
        if held is not None and held[0] is self.controls:
            return held[1]
        segs = self.controls.segments(lot)
        lot.__dict__["_segs"] = (self.controls, segs)
        return segs

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

    def born(self, lot, pos):
        """A lot that appears at distance pos (children of a popped bloon,
        made with t0 = t - pos / speed): its t0 moved back by the delays its
        own route has before pos, so that _time_at(lot, pos) is t."""
        segs = self.segs(lot)
        if segs:
            lot.t0 -= _delay_at(segs, pos)
        return lot

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
        segs = self.segs(lot)
        if segs:
            pos = min(end, max(job.pos, _pos_at(lot, segs, t)))
        else:
            pos = min(end, job.pos + lot.speed * (t - job.release))
        if job.passed is not None:
            # a small bloon's whole tree was worked at once: hand on the layers
            # this station cannot pop, from where the bloon was popped
            for child, k in job.passed:
                speed = layer(child, lot.moab_hp).speed * lot.speed_mult
                self.out.append(self.born(Lot(lot.path, t - pos / speed, child, popped * k, lot.rho * k, speed,
                                              lot.speed_mult, lot.moab_hp), pos))
            return
        lay = layer(lot.bloon, lot.moab_hp)
        kids = sum(k for _, k in lay.children) or 1
        popped *= 1.0 - job.killed          # destroyed whole: no children
        for child, k in lay.children:
            speed = layer(child, lot.moab_hp).speed * lot.speed_mult
            child_lot = self.born(Lot(lot.path, t - pos / speed, child, popped * k, lot.rho * k, speed,
                                      lot.speed_mult, lot.moab_hp), pos)
            child_job = self.job(child_lot, job.zone, t, pos, job.carry / kids)
            if child_job is None or child_job.deadline <= t + 1e-9:
                self.out.append(child_lot)
            else:
                self.push(child_job)


def _lots(mode, rnd, track):
    """The lot lists round `rnd` is played with, remembered on the track
    (lots are never changed in place): one per scenario the round really
    uses (Track.scenarios_in: alternating spawns, Erosion's phases,
    Bloonarius Prime's prime rounds) and, within it, one per turn of a
    blimp too few to share between the lanes (round_turns)."""
    cache = track.__dict__.setdefault("_lot_cache", {})
    key = (mode, rnd)
    if key not in cache:
        cache[key] = [round_lots(mode, rnd, track, sc, turn)
                      for sc in track.scenarios_in(rnd)
                      for turn in round_turns(mode, rnd, track, sc)]
    return cache[key]


# ===========================================================================
# Status effects: time added on the track, damage-taken debuffs, decamo
# ===========================================================================

# Stuns, slows, freezes and knockback hold bloons back, and a slowed bloon
# spends longer in every tower's reach - the way the model already counts
# time in range (docs/model_fix_plan.md item 9; docs/model_audit_primary.md
# F1, military M3, magic finding 13). Each controlling tower adds a delay
# to the lots it can touch, spread over the stretch of route where it
# holds them: a stun of s seconds per hit at h hits a second on the n
# bloons of its zone holds each for a share u = h / n * s of the time
# there (Maim MOAB's 3 s per 1.59 s keeps a lone MOAB held for good, a
# BFB's 1.5 s 94% of the time: fandom:Maim_MOAB); a slow to m for L s
# costs a bloon it hits L * (1 - m) s; a push of d units costs d / v.
# Debuffs make every hit on a debuffed bloon count more: Cripple MOAB +5
# (bw:Cripple_MOAB_(BTD6)), Embrittlement +1, Super Brittle +4, Glue
# Strike +2, at their uptime on the bloons of the debuffer's zone, for the
# towers whose zones overlap it; Embrittlement's and Shimmer's camo removal
# lets towers further on hit the share it touched as plain bloons.
# Conservative on purpose: a stun holds a bloon at most MAX_HOLD of the time
# in its zone, all delays together add at most MAX_STALL x the lot's own
# time on the track, BADs ignore every control the game does not let
# through (a "Bad" slow modifier, Cripple's BAD duration), effects do not
# carry into a popped bloon's children, and frozen bloons stay hittable by
# sharp towers; a slow reaches blimps only with a MOAB modifier or none at
# all (_moab_slowable). False plays every round as before.
#
# Calibrated on the same rounds, against items 7-8: AUC 0.813 -> 0.814,
# rounds at or above 2.0 that leaked 0.54% -> 0.52% (0.53% at the matched
# cut), held rounds under 2.0 54.6% -> 51.2%; at or above 1.0 0.81% ->
# 0.88% (0.84% matched): neutral at the safety bar, so it stays on. The
# median margin of held rounds rose 1.81 -> 1.94, of leaked ones 0.55 ->
# 0.69.
STATUS_RATING = True
MAX_HOLD = 2.0 / 3.0         # a stun keeps a bloon at most this share of its time in the zone (x3 time)
MAX_STALL = 1.0              # all delays add at most this many times the lot's undelayed time on its route
MIN_DELAY_S = 0.05           # delays shorter than this are left out (they only cost time to play)
MAIM_KEYS = {"Moab": "moabDuration", "Bfb": "bfbDuration", "Zomg": "zomgDuration", "Ddt": "ddtDuration",
             "Bad": "badDuration"}


def _decamo(lay):
    """The layer as a bloon stripped of its camo."""
    return Layer(**{**lay.__dict__, "camo": False})


def _is_bad(lay):
    return "Bad" in lay.tags


def _control_applies(eff, kind, lay):
    """Does effect `kind` of a hit's effects reach a bloon of this layer?
    The effect's own filters (only_tags / excluded_tags), MOAB-class only
    where the game lets it (a freeze needs "moabs"; a slow on MOAB-class
    needs a MOAB slow modifier (_moab_slowable); a BAD needs a "Bad" one)."""
    e = eff.get(kind) or {}
    if isinstance(e, dict):
        if e.get("only_tags") and not (set(e["only_tags"]) & lay.tags):
            return False
        if set(e.get("excluded_tags") or ()) & lay.tags:
            return False
    mods = eff.get("slow_modifier") or {}
    if kind == "maim":
        key = next((MAIM_KEYS[t] for t in MAIM_KEYS if t in lay.tags), None)
        return key is not None and (e.get(key) or 0.0) > 0.0
    if kind == "freeze":
        return (not lay.moab or bool(e.get("moabs"))) and not _is_bad(lay)
    if kind in ("stun", "slow"):
        # a BAD ignores slows and stuns unless the effect names it (Bloon
        # Sabotage's and MOAB Glue's "Bad" modifier)
        if _is_bad(lay):
            return "Bad" in mods
        return kind == "stun" or not lay.moab or _moab_slowable(eff)
    if kind == "debuff" and "slow" in eff and lay.moab:
        return _moab_slowable(eff)          # Glue Strike's +2 is for glued bloons
    if kind == "pushback":
        tag = e.get("tag") or ""
        return not _is_bad(lay) and (not tag or tag in lay.tags)
    if kind == "blowback":
        return not _is_bad(lay) and (not lay.moab or bool(e.get("moabs")))
    return True


def _moab_slowable(eff):
    """Does a slow reach MOAB-class bloons? Only with a "Moabs" slow
    modifier other than 1 (MOAB Glue's x2.5: the 37.5% blimp slow,
    fandom:MOAB_Glue), or with no "Moabs" entry at all (Bloon Sabotage's
    wave-wide slow). Every glue carries "Moabs": 1.0, and a glue without
    MOAB Glue glues no blimp - read as a slow, two glues (one with Glue
    Storm) rated a Peninsula Primary Only round 40 at 3.29 that lost 60
    lives (calibration of item 9)."""
    mods = eff.get("slow_modifier") or {}
    return "Moabs" not in mods or float(mods["Moabs"]) != 1.0


def _slow_factor(eff, lay):
    """Speed multiplier of a slow on this layer (its slow modifier for the
    layer's tags: MOAB Glue x2.5 -> 37.5% on MOAB-class)."""
    m = float((eff.get("slow") or {}).get("multiplier", 1.0))
    for tag, mod in (eff.get("slow_modifier") or {}).items():
        if tag in lay.tags:
            m *= float(mod)
    return min(1.0, max(0.0, m))


class _Influence:
    """Damage-taken debuffs and camo removal that reach one station from
    the debuffing towers whose zones overlap its own (set by _Controls)."""

    def __init__(self, ctl, station):
        self.ctl, self.station = ctl, station
        self.cache = {}

    def on(self, lay, path, rho):
        """(extra damage per hit, share of camo bloons seen as plain) on this
        layer at this packing."""
        key = (lay.id, path, round(math.log2(max(rho, 1e-4)) * 2))
        if key not in self.cache:
            self.cache[key] = self.ctl.influence(self.station, lay, path, rho)
        return self.cache[key]


class _Controls:
    """The status effects of a board for one play of a round: which stations
    hold bloons back, which debuff them, which strip camo; and per lot the
    delays on its route (segments)."""

    def __init__(self, stations, track, strength):
        self.track, self.strength = track, strength
        self.holders = []          # (station, source) with a stun / slow / freeze / maim / push
        self.debuffers = []        # (station, source) with a debuff or Cripple's damage_add
        self.decamo = []           # (station, source) that removes camo
        self.zoned = [st for st in stations if st.slow_zones]
        for st in stations:
            for src in st.sources:
                eff = src.effects
                if not eff:
                    continue
                if any(k in eff for k in ("stun", "slow", "freeze", "maim", "pushback", "blowback")):
                    self.holders.append((st, src))
                if "debuff" in eff or (eff.get("maim") or {}).get("damage_add"):
                    self.debuffers.append((st, src))
                if "camo" in (eff.get("removes") or ()):
                    self.decamo.append((st, src))
        self.active = bool(self.holders or self.debuffers or self.decamo or self.zoned)
        self.cache = {}
        if self.debuffers or self.decamo:
            for st in stations:
                st.influence = _Influence(self, st)

    @staticmethod
    def _reaches(src, lay):
        """Can this controlling source touch the layer at all (camo, tags,
        damage type - a slow rides on its projectile's hit)?"""
        return src.can_hit(lay) or (not src.immune and not src.damage and src.can_hit(
            Layer(**{**lay.__dict__, "immune": frozenset()})))

    def _per_bloon(self, st, src, lay, rho, path):
        """(hits a second on one bloon of the zone, seconds a bloon spends
        in the zone) for a controlling source of station st."""
        zone = st.zones[path]
        hits = _hit_rate(src, lay, rho, zone) * self.strength
        if src.ability_use == "moab" and not lay.moab:
            hits = 0.0             # pressed in blimp rounds, for the blimps (abilities.py)
        n = max(1.0, rho * zone.length)
        return hits / n, zone.length / max(lay.speed, 1e-6)

    def segments(self, lot):
        """((a, b, seconds), ...) of delays on this lot's route, cached by
        bloon, route and packing."""
        key = (lot.bloon, lot.moab_hp, lot.path, round(math.log2(max(lot.rho, 1e-4)) * 2),
               round(lot.speed, 2))
        hit = self.cache.get(key)
        if hit is None:
            hit = self.cache[key] = self._segments(lot)
        return hit

    def _segments(self, lot):
        lay = layer(lot.bloon, lot.moab_hp)
        lay = Layer(**{**lay.__dict__, "speed": lot.speed})
        path = lot.path
        out = []
        for st, src in self.holders:
            if not st.covers(path) or not self._reaches(src, lay):
                continue
            zone = st.zones[path]
            per, stay = self._per_bloon(st, src, lay, lot.rho, path)
            if per <= 0.0:
                continue
            eff = src.effects
            delay = 0.0
            hold = 0.0
            for kind in ("stun", "freeze"):
                if kind in eff and _control_applies(eff, kind, lay):
                    hold += float(eff[kind].get("lifespan") or 0.0)
            if "maim" in eff and _control_applies(eff, "maim", lay):
                key = next(MAIM_KEYS[t] for t in MAIM_KEYS if t in lay.tags)
                hold += float(eff["maim"].get(key) or 0.0)
            if hold > 0.0:
                u = min(MAX_HOLD, per * hold)
                delay += stay * u / (1.0 - u)
            if "slow" in eff and _control_applies(eff, "slow", lay):
                m = _slow_factor(eff, lay)
                life = min(float(eff["slow"].get("lifespan") or 0.0), 60.0)
                delay += min(1.0, per * stay) * life * (1.0 - m)
            touches = min(1.0, per * stay) if (per * stay) < 1.0 else per * stay
            for kind, dist in (("pushback", lambda e: float(e.get("amount") or 0.0)),
                               ("blowback", lambda e: float(e.get("chance") or 1.0) * 0.5 * (
                                   float(e.get("distance_min") or 0.0) + float(e.get("distance_max") or 0.0)))):
                if kind in eff and _control_applies(eff, kind, lay):
                    if _is_bad(lay):
                        continue
                    d = dist(eff[kind]) * (0.5 if "Zomg" in lay.tags else 1.0)
                    delay += touches * d / max(lot.speed, 1e-6)
            if delay > 0.0:
                a = zone.entry
                b = zone.entry + max(zone.length, TRACK_STEP)
                out.append((a, b, delay))
        for st in self.zoned:
            if not st.covers(path):
                continue
            zone = st.zones[path]
            for z in st.slow_zones:
                if set(z.get("excluded_tags") or ()) & lay.tags:
                    continue
                if z.get("only_tags") and not (set(z["only_tags"]) & lay.tags):
                    continue
                scale = max(float(z.get("speed_scale") or 1.0), 0.05)
                delay = zone.length / max(lot.speed, 1e-6) * (1.0 / scale - 1.0)
                out.append((zone.entry, zone.entry + max(zone.length, TRACK_STEP), delay))
        merged = {}
        for a, b, d in out:                 # one segment per stretch (towers side by side)
            merged[(a, b)] = merged.get((a, b), 0.0) + d
        out = [(a, b, d) for (a, b), d in merged.items() if d >= MIN_DELAY_S]
        if not out:
            return ()
        cap = MAX_STALL * self.track.paths[path]["length"] / max(lot.speed, 1e-6)
        total = sum(d for _, _, d in out)
        if total > cap:
            out = [(a, b, d * cap / total) for a, b, d in out]
        return tuple(sorted(out))

    def influence(self, station, lay, path, rho):
        """(extra damage per hit, decamo share) that reaches `station`'s zone
        on `path` for bloons of this layer (see _Influence)."""
        zone = station.zones[path] if path < len(station.zones) else None
        if zone is None:
            return 0.0, 0.0
        lo, hi = zone.entry, zone.entry + zone.length
        bonus = 0.0
        for st, src in self.debuffers:
            if st is station or not st.covers(path) or not self._reaches(src, lay):
                continue
            eff = src.effects
            z = st.zones[path]
            if "debuff" in eff:
                add, life = float(eff["debuff"].get("add") or 0.0), float(eff["debuff"].get("lifespan") or 0.0)
                if not _control_applies(eff, "debuff", lay):
                    continue
            elif _control_applies(eff, "maim", lay):
                add = float(eff["maim"]["damage_add"])
                life = float(eff["maim"].get(next(MAIM_KEYS[t] for t in MAIM_KEYS if t in lay.tags)) or 0.0)
            else:
                continue
            reach = z.entry + z.length + life * lay.speed
            if hi < z.entry or lo > reach:
                continue          # the debuffed bloons never stand in this zone
            per, _ = self._per_bloon(st, src, lay, rho, path)
            bonus += add * min(1.0, per * life)
        seen = 0.0
        if lay.camo:
            for st, src in self.decamo:
                if st is station or not st.covers(path) or not self._reaches(src, _decamo(lay)):
                    continue
                z = st.zones[path]
                if z.entry > hi:
                    continue          # strips camo only after this zone
                per, stay = self._per_bloon(st, src, _decamo(lay), rho, path)
                seen = max(seen, min(1.0, per * stay))
        return bonus, seen


def simulate_round(stations, mode, rnd, track, strength=1.0):
    """Play round `rnd` against the stations (see the module docstring) in
    every scenario of the track the round uses and every turn of its
    blimps (_lots) and return the worst. strength scales every station's output (margin
    search)."""
    worst = None
    for lots in _lots(mode, rnd, track):
        res = _play(stations, track, lots, strength)
        if worst is None or (res.lives_lost, res.end_time) > (worst.lives_lost, worst.end_time):
            worst = res
    return worst


def with_parts(stations):
    """The stations with their local parts (Station.parts) listed too."""
    out = []
    for st in stations:
        out.append(st)
        out.extend(getattr(st, "parts", None) or ())
    return out


def _play(stations, track, lots, strength):
    """One scenario of one round: lots flow through the stations in track
    order; what is left after the last one leaks."""
    lots = list(lots)
    end_time = 0.0
    # towers frozen part of the time (Glacial Trail) attack at that share
    strength *= getattr(track, "uptime", 1.0)
    every = sorted(with_parts(stations), key=lambda s: s.order)
    controls = _Controls(every, track, strength) if STATUS_RATING else None
    if controls is not None and not controls.active:
        controls = None
    for st in every:
        st.strength = strength
        out = []
        server = _Server(st, out, controls)
        for lot in lots:
            if lot.count <= 1e-9:
                continue
            if not st.covers(lot.path):
                out.append(lot)
                continue
            z = st.zones[lot.path]
            job = server.job(lot, z, _time_at(lot, server.segs(lot), z.entry), z.entry, 0.0)
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
        segs = controls.segments(lot) if controls is not None else ()
        end_time = max(end_time, _time_at(lot, segs, path_len[lot.path]))
    for st in every:
        st.influence = None
    return RoundResult(leaked=leaked, lives_lost=lives, leaked_rbe=leak_rbe, end_time=end_time)


# The margin search looks between these strengths. A round that leaks even
# with every tower MARGIN_HI times stronger is reported at MARGIN_FLOOR: at
# the floor every board reads the same, whatever it is bought (reinforce.py
# then judges purchases by the lives they save instead, see at_floor).
MARGIN_LO = 1 / 16
MARGIN_HI = 16.0
MARGIN_FLOOR = 1.0 / MARGIN_HI


def at_floor(margin):
    """Is `margin` the margin search's floor (MARGIN_FLOOR) - a round so far
    out of reach that the margin cannot tell two boards apart? False for
    None (not rated)."""
    return margin is not None and margin <= MARGIN_FLOOR * 1.001


def round_margin(stations, mode, rnd, track, lo=MARGIN_LO, hi=MARGIN_HI, iterations=9):
    """The safety margin of round rnd: the factor by which every tower could
    be weaker and the round still pop without a leak (2.0 = holds at half
    strength; below 1.0 = leaks at full strength). Bisection on strength,
    worst over the track's scenarios this round uses and the turns of its
    blimps (_lots)."""
    return lots_margin(stations, track, _lots(mode, rnd, track), lo, hi, iterations)


def lots_margin(stations, track, lots_by_scenario, lo=MARGIN_LO, hi=MARGIN_HI, iterations=9):
    """round_margin for lots built by the caller (groups_lots), one list per
    scenario of the track: the worst margin over them."""
    worst = 1.0 / lo
    for lots in lots_by_scenario:
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
    """A profile's sources with support buffs applied: rate, pierce, camo,
    and damage_type - a Monkey Intelligence Bureau village lets its towers
    pop every bloon, an Alchemist's dip (_potion_buffs) the properties it
    names ("props") and adds its bonus damage per tag.

    A buff with a "share" under 1 (an Alchemist's dip, _dip_share) covers
    only that share of the tower's shots: each source is split into a
    dipped copy at that share of its rate and a plain one at the rest.
    Several dips add their shares. An ability's timed buff (its "group":
    Call to Arms, _ability_buffs) is a share of its own: a source is split
    once per group, at the group's largest share (the game lets no second
    press stack on an active one), with all of that group's buffs on the
    buffed copy - Call to Arms' rate and pierce together."""
    groups = {}
    steady = []
    for b in buffs_here:
        if b.get("share", 1.0) >= 1.0:
            steady.append(b)
        else:
            groups.setdefault(b.get("group", "dip"), []).append(b)
    splits = []
    for name, bs in groups.items():
        share = min(1.0, sum(b["share"] for b in bs)) if name == "dip" else max(b["share"] for b in bs)
        if share >= 1.0:
            steady += bs
        elif share > 0.0:
            splits.append((name, share, bs))
    out = [_with_buffs(s, steady) for s in p.sources]
    for name, share, bs in splits:
        tag = " (dipped)" if name == "dip" else f" ({name})"
        nxt = []
        for full in out:
            buffed = _with_buffs(full, bs)
            nxt.append(Source(**{**full.__dict__, "shots": full.shots * (1.0 - share),
                                 "shots_single": full.shots_single * (1.0 - share)}))
            nxt.append(Source(**{**buffed.__dict__, "name": buffed.name + tag, "shots": buffed.shots * share,
                                 "shots_single": buffed.shots_single * share}))
        out = nxt
    return out


def _boosted_sources(sources, boosts):
    """sources with a tower's own ability boosts (Profile.boosts: Turbo
    Charge, Perma Charge, Absolute Zero on its own Ice Monkey) at their
    uptime: each of the tower's own attacks is split into a boosted copy at
    the boost's share of its shots - weapon rate x "rate" (a shorter
    interval: more shots), "damage_add" more per hit - and a plain one at
    the rest."""
    out = list(sources)
    for b in boosts:
        share, rate, add = b["share"], max(b.get("rate") or 1.0, 1e-3), b.get("damage_add") or 0.0
        nxt = []
        for s in out:
            if s.ability:
                nxt.append(s)
                continue
            nxt.append(Source(**{**s.__dict__, "shots": s.shots * (1.0 - share),
                                 "shots_single": s.shots_single * (1.0 - share)}))
            nxt.append(Source(**{**s.__dict__, "name": s.name + " (boosted)",
                                 "shots": s.shots * share / rate, "shots_single": s.shots_single * share / rate,
                                 "damage": s.damage + (add if s.damage > 0.0 else 0.0)}))
        out = nxt
    return out


def _with_buffs(s, buffs):
    """Source s with these support buffs applied (see _buffed_sources)."""
    shots, single, pierce, camo = s.shots, s.shots_single, s.pierce, s.camo
    immune, bonus = s.immune, dict(s.bonus)
    for b in buffs:
        if b["kind"] == "rate" and b.get("value"):
            shots /= b["value"]
            single /= b["value"]
        elif b["kind"] == "pierce" and b.get("value"):
            pierce += b["value"]
        elif b["kind"] == "pierce_mult" and b.get("value"):
            pierce *= b["value"]                # Call to Arms: +50% pierce
        elif b["kind"] == "camo":
            camo = True
        elif b["kind"] == "damage_type":
            props = b.get("props")
            immune = immune - frozenset(props) if props else frozenset()
            for tag, extra in (b.get("bonus") or {}).items():
                cur = bonus.get(tag, {"mult": 1.0, "add": 0.0})
                bonus[tag] = {"mult": cur.get("mult", 1.0), "add": cur.get("add", 0.0) + extra.get("add", 0.0)}
    return Source(**{**s.__dict__, "shots": shots, "shots_single": single, "pierce": pierce, "camo": camo,
                     "immune": immune, "bonus": bonus})


MAP_WIDE_NEEDS_SIGHT = ("sniper",)

# The strict reading (station_for strict=True) of towers the model lets work
# map-wide although they fight in a circle of their own: an Advanced Intel
# sub (2-x-x) shoots what other towers see but stands in one place, and an
# ace's pineapples and Bomber Ace bombs fall along its flight circle. The
# Beginner map builds were checked this way (docs/map_strategies/beginner.md,
# "sight-strict" and gap 3); strict limits them to their own range and flight
# circle (range + pattern radius).
STRICT_OWN_REACH = ("sub", "ace")

# Advanced Intel (Monkey Sub 2-x-x): the game lets the sub shoot bloons
# inside the range of its other towers, which attacks.json records as a
# map-wide reach (profile.is_global). The model used to give such a sub the
# whole track. Two games of 2026-11-08 lost 105 and 143 lives by round 21
# with the defence rated 5-16x: Spillway Medium (two 2-0-x subs and an
# alchemist, nothing else attacking) and Erosion Reverse (two Intel subs
# and a map-wide sniper; 80 greens of round 18 leaked). An Intel sub now
# reaches its own circle plus the circles of the other attacking towers
# (intel_lent_circles); map-wide towers lend nothing, since the leak with a
# sniper on the board shows the sub did not shoot along its sight.
INTEL_KINDS = ("sub",)


@lru_cache(maxsize=None)
def detects_camo(kind, tiers):
    """Does a tower crosspath see camo bloons on its own - some aimed
    source of its profile targets them (the game's camo detection)? Spikes
    laid on the track pop camo bloons without seeing them and do not count:
    an Advanced Intel sub shares what a tower *targets*. Nor do its
    abilities (Source.ability): they are up part of the time only."""
    p = profile(kind, tiers)
    return bool(p) and any(s.camo and s.placement != "track" and not s.ability for s in p.sources)


@lru_cache(maxsize=None)
def tower_set(kind):
    """The game's tower set of a tower kind ("primary", "military", "magic",
    "support"), from data/game_model/towers.json "category"; None if unknown."""
    return (_json(str(GAME_MODEL / "towers.json")).get(kind) or {}).get("category")


def buff_reaches(b, kind, tiers=None):
    """Does support buff b (an attacks.json "buffs" entry) apply to a tower of
    this kind (and crosspath)? Its "sets" filter (Primary Training / Primary
    Mentoring: Primary towers only), "towers" filter (game tower ids) and
    "min_tiers" filter (Obyn's +40% range: Druids of the Jungle, x-3-x and
    up) must let the tower through; a buff without filters reaches every
    tower, heroes included. Set and tower filters never let a hero through
    (its kind is "hero:<id>", in no tower set)."""
    if b.get("sets") and tower_set(kind) not in b["sets"]:
        return False
    if b.get("towers"):
        game_id = ((attacks().get("towers") or {}).get(kind) or {}).get("game_id")
        if game_id not in b["towers"]:
            return False
    if b.get("min_tiers"):
        if tiers is None or hero_of(kind) is not None or len(tuple(tiers)) != len(b["min_tiers"]):
            return False
        if any(int(have) < int(need) for have, need in zip(tiers, b["min_tiers"])):
            return False
    return True


def buff_covers(supporter, t, radius):
    """Does a support buff of this radius, from a tower standing at
    `supporter`, reach tower t? Only when t's centre lies inside the radius.

    The game's exact rule (centre, or any part of the footprint) is not
    confirmed, and with one life the strict reading is the safe one: it can
    only make the bot buy more defence. The model used to add the buffed
    tower's footprint radius (8 for a buccaneer) to the buff radius. On
    Frozen Over CHIMPS (2026-11-05 14:34) the village's planned spot was
    refused, the Radar Scanner (radius 48) stood 49.3 units from an Aircraft
    Carrier, the model still gave the carrier camo and rated round 56 at 16;
    in the recording the carrier did not shoot the camo pinks beside it and
    the 40 camo rainbows of round 56 ended the game."""
    return math.hypot(supporter.x - t.x, supporter.z - t.z) <= radius


def _joined(main, parts):
    """`main` with `parts` added to its Station.parts; the first of the parts
    stands in for a missing main (None when there is nothing at all)."""
    parts = [s for s in parts if s is not None]
    if main is None:
        if not parts:
            return None
        main, parts = parts[0], parts[1:]
    main.parts = list(main.parts) + parts
    return main


def station_for(t, placed, track, sight=None, strict=False, pressed=True):
    """The Station of one Placed tower, or None when it does no damage or
    reaches no track. strict: STRICT_OWN_REACH towers reach only their own
    circle, not the whole map. Support buffs of the other towers in `placed`
    (villages: camo, attack rate, range, pierce) apply when this tower's
    centre stands inside the supporter's buff radius (buff_covers) and the
    buff's filters let its kind through (buff_reaches). sight(x, z, pts) ->
    visible mask, used for towers that need line of sight
    (placement.needs_sight).

    Bombs dropped under a plane (placement "drop": pineapples, Bomber Ace)
    are stations of their own along the flight circle (_drop_parts).

    pressed: the bot presses abilities on this board. False when a
    destructive hero ability may be unlocked (abilities.DESTRUCTIVE_
    ABILITIES: with Adora at level 7 or more the bot presses no hotkey at
    all) - then no ability counts (Source.ability, Profile.boosts and the
    ability buffs of the supporters)."""
    p = profile(t.kind, t.tiers)
    if p is None:
        return None
    main = _station_for(t, placed, track, sight, strict, pressed)
    if not any(s.placement == "drop" for s in p.sources):
        return main
    camo_paths = None if main is None else main.camo_paths
    drops = [s for s in _buffed_sources(p, _buffs_at(t, placed, pressed)[0]) if s.placement == "drop"]
    return _joined(main, _drop_parts(t, drops, p, track, camo_paths))


@dataclass(frozen=True)
class RangeBuff:
    """The range buffs a tower gets from its supporters: its range becomes
    range x mult + add. mult is the largest percentage buff (several are not
    added up: the cautious reading of docs/model_audit_support_heroes.md G3);
    add is the largest additive one - Primary Mentoring's +5, Obyn level
    11's +5 to Magic towers, Silas's +5 to Ice Monkeys - which the game
    applies after the multipliers ("Range buffs apply after all other range
    multipliers", fandom:Obyn_Greenfoot_(BTD6)). The additive buffs used to
    be dropped."""
    mult: float = 1.0
    add: float = 0.0

    def __call__(self, radius):
        return radius * self.mult + self.add


def _buffs_at(t, placed, pressed=True):
    """(support buffs that reach tower t, RangeBuff) from the other towers
    in `placed` (see station_for)."""
    buffs_here = []
    mult, add = 1.0, 0.0
    for o in placed:
        q = profile(o.kind, o.tiers) if o.tid != t.tid else None
        if q is None:
            continue
        for b in q.buffs:
            if not buff_reaches(b, t.kind, t.tiers):
                continue
            if b.get("ability") and not pressed:
                continue
            if b.get("global") or buff_covers(o, t, b.get("radius") or q.range):
                if b["kind"] == "range" and b.get("value"):
                    mult = max(mult, 1.0 + b["value"])
                elif b["kind"] == "range" and b.get("additive"):
                    add = max(add, float(b["additive"]))
                elif b.get("shots"):
                    buffs_here.append(dict(b, share=_dip_share(b, o, t, placed)))
                else:
                    buffs_here.append(b)
    return buffs_here, RangeBuff(mult, add)


def _station_for(t, placed, track, sight=None, strict=False, pressed=True):
    """station_for without the "drop" sources."""
    from .placement import needs_sight
    p = profile(t.kind, t.tiers)
    if p is None:
        return None
    buffs_here, range_mult = _buffs_at(t, placed, pressed)
    sources = [s for s in _buffed_sources(p, buffs_here) if s.placement != "drop" and (pressed or not s.ability)]
    if pressed and p.boosts:
        sources = _boosted_sources(sources, p.boosts)
    sources = [s for s in _rear_copies(sources, t, range_mult(p.range), track)
               if s.shots > 0.0 or not s.rear_fov]
    if not sources:
        return None
    camo_paths = None
    detectors = [o for o in placed if o.tid != t.tid and detects_camo(o.kind, o.tiers)]
    if any(s.camo_shared and not s.camo for s in sources) and detectors:
        # Advanced Intel: the sub shoots the camo bloons another tower's
        # detection covers - but only there. The model used to give it camo
        # on the whole map: Muddy Puddles Impoppable (2026-11-06 08:46) had
        # one camo dart in a corner reaching two of the four lanes, two
        # Advanced Intel subs, round 33 rated 16.0, and the camo yellows of
        # the other lanes ended the game. Limited per path (a detector's
        # reach on a path counts for all of that path - coarse, but it
        # catches separate lanes).
        camo_paths = frozenset().union(*(_reach_paths(o, track, sight) for o in detectors))
        sources = [Source(**{**s.__dict__, "camo": True}) if s.camo_shared else s for s in sources]
    # all of a tower's sources share one station: its time is spent once
    reach_radius = range_mult(p.range)
    if p.pattern_radius:
        reach_radius = p.pattern_radius + range_mult(p.range)
    # orbiting glaives sweep their own circle, which may reach past the range
    reach_radius = max(reach_radius, p.own_radius)
    is_global = p.is_global or any(s.placement == "global" for s in sources)
    if strict and t.kind in STRICT_OWN_REACH:
        is_global = False
    lent = ()
    if is_global and t.kind in INTEL_KINDS and not any(s.placement == "global" for s in sources):
        # Advanced Intel: the sub's darts reach its own circle and the
        # circles of the other towers - not the whole map (see INTEL_KINDS)
        is_global = False
        lent = intel_lent_circles(t, placed)
        own = [s for s in sources if not s.camo_shared]
        shared = [s for s in sources if s.camo_shared]
        if not shared:
            lent = ()      # a submerged sub (_surfaced_or_submerged): its pulse works around it only
        if own and shared and lent:
            # the submerged pulse (_pulse_at_tower) works around the sub
            # only; the borrowed circles are for its darts
            main = _make_station(t, shared, False, reach_radius, track, sight, camo_paths, lent)
            part = _make_station(t, own, False, reach_radius, track, sight, camo_paths)
            if main is None:
                return part
            if part is not None:
                main.parts = [part]
            return main
    # A tower with map-wide AND local sources (Inferno Ring: meteor + ring of
    # fire; Aircraft Carrier / Carrier Flagship: planes + the boat's own
    # cannons; Druid of the Jungle: vines + thorns; ace planes + a map-wide
    # drop) is two stations: the map-wide sources over the whole map and the
    # local ones only in the tower's own reach (Station.parts). Before, one
    # map-wide source gave every source of the tower the whole map: Lost
    # Crevasse CHIMPS (2026-11-08 01:37, loss case 20261108_014123) had an
    # Inferno Ring on the lake shore whose ring reached no track (the bot read
    # 0 pops at 4-0-2), the model let the ring burn the whole track, rated
    # round 93 2.95, and a fortified MOAB of round 93 leaked at the exit.
    glob = [s for s in sources if s.placement == "global"]
    local = [s for s in sources if s.placement != "global"]
    if is_global and glob and local:
        main = _make_station(t, glob, True, reach_radius, track, sight, camo_paths)
        if t.kind in INTEL_KINDS:
            parts = [_make_station(t, local, False, reach_radius, track, sight, camo_paths,
                                   intel_lent_circles(t, placed))]
        else:
            parts = _local_stations(t, local, p, range_mult, track, sight, camo_paths)
        return _joined(main, parts)
    if is_global or lent:
        return _make_station(t, sources, is_global, reach_radius, track, sight, camo_paths, lent)
    return _joined(None, _local_stations(t, sources, p, range_mult, track, sight, camo_paths))


def _local_stations(t, sources, p, range_mult, track, sight, camo_paths):
    """Stations for a tower's local sources, one per reach (_zone_radius):
    sources of the same reach share one station (one server), as all of a
    tower's sources used to. A source without a reach of its own works in
    the tower's: its range (with range buffs), or a plane's flight pattern
    plus its range. range_mult: the tower's RangeBuff."""
    base = (p.pattern_radius or 0.0) + range_mult(p.range)
    groups = {}
    for s in sources:
        if s.zone_radius is None:
            radius = base
        elif s.zone_fixed:
            radius = s.zone_radius
        else:
            radius = range_mult(s.zone_radius)
        groups.setdefault(round(radius, 1), []).append(s)
    return [_make_station(t, group, False, radius, track, sight, camo_paths)
            for radius, group in sorted(groups.items(), reverse=True)]


# How far from a route's centre line a plane still counts as "over the
# track" for CheckAirUnitOverTrackModel (Bomber Ace). The maps' own track
# areas (data/map_geometry, areas of type "track") are narrow strips around
# the bloon path: the median distance from the path to their edge measured
# 2.4 (Cubism) to 9.1 (Dark Path), about 5 on most maps (Monkey Meadow 5.0,
# Logs 4.4, Bazaar 4.3, Peninsula 4.9, Skates 5.3; 2026-11-12).
OVER_TRACK_HALF_WIDTH = 5.0


def _flight_circle(t, radius):
    """(x, z) points every TRACK_STEP along the circle a plane flies around
    tower t (the model's flight pattern: Profile.pattern_radius)."""
    n = max(24, int(math.ceil(2.0 * math.pi * radius / TRACK_STEP)))
    ang = np.arange(n) * (2.0 * math.pi / n)
    return np.stack([t.x + radius * np.cos(ang), t.z + radius * np.sin(ang)], axis=1)


def _runs(flags):
    """Lengths (in points) of the runs of True in a circular bool array."""
    flags = np.asarray(flags, bool)
    if flags.all():
        return [len(flags)]
    start = int(np.argmin(flags))           # begin at a False point, so no run wraps round
    rolled = np.roll(flags, -start)
    runs, n = [], 0
    for f in rolled:
        if f:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    return runs


def _drop_share(src, circle, track, speed):
    """(share of its full rate a "drop" source keeps, bool mask of the circle
    points its bombs fall from) for a plane flying `circle` at `speed`.

    Pineapples fall wherever the plane is: a bomb counts when it falls
    within its blast radius of the track, so the share is the part of the
    circle that close to it.

    A Bomber Ace fires only while the plane is over the track
    (src.over_track_only). Its weapon still waits `cooldown` seconds between
    volleys, so it does not fire for the share of TIME spent over the track:
    each pass over the track (a run of circle points within
    OVER_TRACK_HALF_WIDTH of it) gets one volley when the plane arrives
    (the weapon has reloaded during the flight in between), plus one more
    for every cooldown the pass lasts. The share is those volleys per lap
    against the lap time over the cooldown (one volley per cooldown when
    the whole circle lies on the track). A circle of radius 40 at speed 60
    takes 4.2 s; crossing one straight lane twice gives 2 volleys a lap
    against 3.5 at full rate."""
    if src.over_track_only:
        over = track.near_track(circle, OVER_TRACK_HALF_WIDTH)
        step = float(np.hypot(*(circle[1] - circle[0])))      # flight between two circle points
        lap = step * len(circle) / speed if speed > 0 else 0.0
        if lap <= 0.0 or src.cooldown <= 0.0:
            return float(over.mean()), over      # no speed known: the share of time over the track
        volleys = sum(1 + math.floor(n * step / speed / src.cooldown) for n in _runs(over))
        return min(1.0, volleys * src.cooldown / lap), over
    near = track.near_track(circle, max(src.blast, OVER_TRACK_HALF_WIDTH))
    return float(near.mean()), near


def _drop_parts(t, drops, p, track, camo_paths):
    """Stations for the "drop" sources of tower t (profile p): one per kind
    of drop (over-track or not, blast radius), each covering the track
    within the blast radius of the circle points its bombs fall from, with
    the sources' rate cut to the share that falls there (_drop_share)."""
    radius = p.pattern_radius or p.range
    circle = _flight_circle(t, radius)
    groups = {}
    for s in drops:
        groups.setdefault((s.over_track_only, s.blast, s.cooldown), []).append(s)
    out = []
    for group in groups.values():
        share, falls = _drop_share(group[0], circle, track, p.flight_speed)
        if share <= 0.0 or not falls.any():
            continue
        blast = max(group[0].blast, OVER_TRACK_HALF_WIDTH)
        discs = tuple((float(x), float(z), blast) for x, z in circle[falls])
        sources = [Source(**{**s.__dict__, "shots": s.shots * share, "shots_single": s.shots_single * share})
                   for s in group]
        st = _make_station(t, sources, False, 0.0, track, None, camo_paths, discs)
        if st is not None:
            out.append(st)
    return out


def _rear_copies(sources, t, radius, track):
    """sources with each Buccaneer rear shot (Source.rear_fov) cut to the
    share of the time a second target stands behind the boat: the share of
    the covered track with more track in the cone straight behind the boat
    (Track.behind_share; the game's FilterTargetAngleFilterModel, 90 degrees).
    A boat on a shore with the lane on one side gets no rear shots; one
    between two lanes keeps them (docs/model_audit_military.md M5: "Can
    shoot a second copy of Dart at 180 degrees from first Dart if bloons
    are detected behind", fandom:Grape_Shot_(BTD6))."""
    shares = {}
    out = []
    for s in sources:
        if s.rear_fov:
            if s.rear_fov not in shares:
                shares[s.rear_fov] = track.behind_share(t.x, t.z, radius, s.rear_fov)
            share = shares[s.rear_fov]
            s = Source(**{**s.__dict__, "shots": s.shots * share, "shots_single": s.shots_single * share})
        out.append(s)
    return out


def intel_lent_circles(t, placed):
    """The (x, z, radius) circles an Advanced Intel sub t borrows from the
    other towers in `placed`: each tower that attacks, with its own reach
    (range or flight pattern, no range buffs). Map-wide towers (snipers,
    mortars, heli pilots) lend nothing, and another Intel sub lends only its
    own circle (see INTEL_KINDS)."""
    out = []
    for o in placed:
        if o.tid == t.tid:
            continue
        q = profile(o.kind, o.tiers)
        if q is None or not q.sources:
            continue
        if o.kind in INTEL_KINDS:
            out.append((o.x, o.z, q.range))
            continue
        if q.is_global or any(s.placement == "global" for s in q.sources if not s.ability):
            continue
        out.append((o.x, o.z, max((q.pattern_radius or 0.0) + q.range, q.own_radius)))
    return tuple(out)


def _make_station(t, sources, is_global, reach_radius, track, sight, camo_paths, lent=()):
    """The Station of tower t for these sources: over the whole map when
    is_global, else within reach_radius and the `lent` circles (None when
    that reaches no track)."""
    from .placement import needs_sight
    travel = max((s.travel for s in sources if s.radial or s.spray), default=0.0)
    # Snipers reach the whole map but still need line of sight; the other
    # map-wide towers (planes, helis, mortars, Advanced Intel subs) do not.
    # Skipping the sight test for snipers let the optimizer line them up in
    # corners that see little of the track (Balance's top row).
    sees = needs_sight(t.kind) and (not is_global or t.kind in MAP_WIDE_NEEDS_SIGHT)
    blocked = sight if (sight is not None and sees) else None
    zones = track.zones(t.x, t.z, None if is_global else reach_radius, travel=travel, sight=blocked,
                        lent=() if is_global else lent)
    if not any(zones):
        return None
    order = min((z.entry / max(pl["length"], 1e-6) for z, pl in zip(zones, track.paths) if z), default=1.0)
    banked = all(s.placement == "track" for s in sources)
    bank = max((s.bank for s in sources), default=0.0)
    start = min(bank, CARRIED_STOCK_SECONDS) if banked and any(s.lasts_rounds for s in sources) else 0.0
    # single-target towers (sniper bullets) are set to "strong" targeting by
    # the plans: they shoot MOAB-class bloons first
    strong = any(s.reach == 0.0 for s in sources)
    prof = profile(t.kind, t.tiers)
    slow_zones = [z for z in (prof.zones if prof is not None else []) if z.get("kind") == "slow"
                  and z.get("follows_range") and z.get("speed_scale", 1.0) < 1.0] if STATUS_RATING else []
    return Station(tid=t.tid, kind=t.kind, tiers=tuple(t.tiers), zones=zones, sources=sources,
                   order=order, banked=banked, bank_seconds=bank, bank_start=start, strong=strong,
                   camo_paths=camo_paths, slow_zones=slow_zones)


def _reach_paths(t, track, sight=None):
    """The path indexes a tower's own attacks reach (its range, flight
    pattern or the whole map), without range buffs from other towers -
    the cautious reading, used for where it lends camo sight."""
    from .placement import needs_sight
    p = profile(t.kind, t.tiers)
    if p is None:
        return frozenset()
    radius = max((p.pattern_radius or 0.0) + p.range, p.own_radius)
    is_global = p.is_global or any(s.placement == "global" for s in p.sources if not s.ability)
    sees = needs_sight(t.kind) and (not is_global or t.kind in MAP_WIDE_NEEDS_SIGHT)
    zones = track.zones(t.x, t.z, None if is_global else radius,
                        sight=sight if (sight is not None and sees) else None)
    return frozenset(i for i, z in enumerate(zones) if z is not None and z.length > 0)


def sight_test(grid, track, samples=12, heights=None):
    """A sight(x, z, pts) function for station_for from a MapModel's bool
    sight grid (True = blocks sight): a track point is visible from a tower
    when no blocking cell lies on the straight line between (sampled
    `samples` times). None when the map has no sight blockers.

    heights: (MapModel.sight_height, MapModel.ground_height) when known, so
    a tower on raised ground sees over blockers no higher than that ground
    (placement.sight_blockers)."""
    if grid is None or not grid.any():
        return None
    h, w = grid.shape
    t = np.linspace(0.1, 0.9, samples)[:, None]
    from .mapgeom import HEIGHT_TIE
    blocker_h, ground_h = heights if heights is not None else (None, None)
    if blocker_h is None or ground_h is None:
        blocker_h = None

    def blockers_for(x, z):
        """The grid of cells that block sight for a tower at world (x, z)."""
        if blocker_h is None:
            return grid
        cx, cy = np.rint(track.proj.to_cells([[x, z, 0.0]])[0][:2]).astype(int)
        return blocker_h > ground_h[min(max(cy, 0), h - 1), min(max(cx, 0), w - 1)] + HEIGHT_TIE

    def sight(x, z, pts):
        block = blockers_for(x, z)
        px = x + (pts[:, 0][None, :] - x) * t
        pz = z + (pts[:, 1][None, :] - z) * t
        ph = pts[:, 2][None, :] * t
        cells = np.rint(track.proj.to_cells(np.stack([px.ravel(), pz.ravel(), ph.ravel()], axis=1))).astype(int)
        cells[:, 0] = np.clip(cells[:, 0], 0, w - 1)
        cells[:, 1] = np.clip(cells[:, 1], 0, h - 1)
        return ~block[cells[:, 1], cells[:, 0]].reshape(samples, -1).any(axis=0)
    return sight


def stations_for(placed, track, sight=None, strict=False, pressed=True):
    """Stations for a list of Placed towers on a Track (see station_for)."""
    return [st for st in (station_for(t, placed, track, sight, strict, pressed) for t in placed) if st is not None]


def evaluate(placed, mode, rounds, track, sight=None, margins=False):
    """{round: RoundResult} (and {round: margin} when margins=True) for a
    fixed defence over a list of rounds."""
    st = stations_for(placed, track, sight)
    results = {r: simulate_round(st, mode, r, track) for r in rounds}
    if not margins:
        return results
    return results, {r: round_margin(st, mode, r, track) for r in rounds}
