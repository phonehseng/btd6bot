"""Progression planner: decides what the bot does next on the account.

Public API (every function also returns human readable reasons for logs):

* :func:`choose_tower_unlock` - which tower to take on a level-up choice
* :func:`choose_upgrade_unlocks` - which upgrades to buy with tower XP
* :func:`choose_mk` - Monkey Knowledge priority list
* :func:`next_game` - the next (map, difficulty, mode, strategy, hero)

Progression policy (the owner's order: Hard first, levelled up through the
Hard sub-modes until CHIMPS, Medium and Easy only afterwards). Every
candidate falls in one tier; the best tier wins, the score only ranks
within a tier (see :data:`PHASES` and :func:`_tier`):

    H    first-time Hard standard medal, p >= min_p_new_hard (0.8), on every
         open map - unique Hard wins also open the next map category
    HS   first-time Hard sub-mode medal, p >= its threshold: Magic Monkeys
         Only -> Double HP -> Half Cash, and ABR -> Impoppable -> CHIMPS
    HF   nothing Hard-family clears 0.8: the highest-p Hard-family medal with
         p >= hard_fallback_p (0.7; never CHIMPS)
    B    Hard is blocked by missing upgrades: a Medium/Easy game (p >= 0.7)
         whose towers are mostly the ones the Hard roster still needs XP for
    M    Medium family medal (Medium, Military Only, Apopalypse, Reverse)
    E    Easy family medal (Easy, Primary Only, Deflation)
    FARM no confident medal: replay the best confident game for XP/MM
    LAST nothing is confident at all: the safest (highest-p) game

M/E are reached while the roster is too weak for Hard (they then serve as
XP/unlock games) or once the Hard family is exhausted. In H/HS, maps whose
track is already learned (no placement scan) go first. Within a tier the
score is expected value per minute::

    score = [p*(XP_value + w*MM + medal/unlock/unique value)
             + (1-p)*(XP_fail - loss_penalty)] / [p*T + (1-p)*T_fail]

where ``p`` comes from a Beta posterior over this (map, mode, strategy)'s
record, with a prior from the strategy's declared success rates, the map's
category/ease (scaled by how hard the mode is), how much of the strategy's
upgrade build is unlocked, and the strategy's calibration on other maps.
``T`` is learned from observed game durations (see :class:`_Durations`).
XP is weighted by how much the account still *needs* XP (levels for
tower/MK unlocks, tower XP for upgrades that STRATEGY_NEEDS lists).

The runner only needs to::

    plan = next_game(account, strategies)
    ... play plan ...
    account.record_result(plan.map, plan.mode_key, plan.strategy_id, won, ...)

Strategies are described with :class:`StrategySpec` (or dicts / objects with
the same attributes). ``EXAMPLE_STRATEGIES`` is a reference roster used by the
tests and as a fallback; the real roster should come from the strategy layer.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .account import (
    CATEGORY_UNLOCK_WINS, CATEGORY_XP_MULT, EXCLUDED_MAPS, EXCLUDED_MODES,
    GIFT_BOX_TOWERS, MAPS, MODES, PROJECT_ROOT, TOWER_CATEGORIES, TOWER_TO_CATEGORY,
    AccountState, canonical_map, mode_unlocks, rounds_xp,
)

# Learned map tracks (btd6bot/maplearn.py writes data/maps/<slug>.npz after
# the placement scan of a map's first visit).
MAPS_DIR = PROJECT_ROOT / "data" / "maps"


def map_slug(name: str) -> str:
    """Same slug as maplearn.slug (not imported: maplearn pulls in cv2)."""
    return "".join(c for c in name.lower() if c.isalnum())

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------


@dataclass
class PlannerConfig:
    mm_weight: float = 20.0          # XP-equivalent of 1 MM
    goal_medal_value: float = 60_000  # any first-time medal (tiers decide the order)
    off_goal_medal_value: float = 6_000  # unused since the tier policy (kept for configs)
    unlock_value: float = 3_000      # per mode a medal unlocks
    unique_win_value: float = 25_000  # first win on a map while < 20 unique wins
    threshold_win_bonus: float = 1.5  # multiplier when the win crosses 5/12/20
    farm_bonus: float = 1.25         # XP multiplier for the designated farm while farming
    overhead_minutes: float = 1.0    # menus, loading, collecting rewards
    first_visit_minutes: float = 2.5  # one-time placement scan on a never-played map
    fail_time_frac: float = 0.7      # a loss costs this fraction of the full time
    fail_round_frac: float = 0.6     # ... and reaches this fraction of the rounds
    loss_penalty: float = 15_000     # XP-equivalent cost of a loss on top of the lost time
    prior_strength: float = 3.0      # Beta prior pseudo-games
    # Losses are expensive (time, no rewards): only attempt confident games.
    min_p_new: float = 0.75          # minimum p to attempt an unearned Easy/Medium-group medal
    min_p_new_hard: float = 0.80     # ... an unearned Hard-group medal
    min_p_chimps: float = 0.80
    min_p_repeat: float = 0.85       # minimum p to replay for XP/MM (optional games: be safe)
    # Hard focus: a first-time Hard standard medal with p >= hard_ready_p is
    # "reliable" and gets hard_medal_value on top of every other bonus.
    hard_ready_p: float = 0.80
    hard_medal_value: float = 150_000
    # No Hard-family medal clears its threshold: still play the highest-p one
    # (not CHIMPS) if p >= this, rather than dropping to Medium/Easy.
    hard_fallback_p: float = 0.70
    # Where learned map tracks live (None: only maps already played count as
    # learned - used by tests so they do not depend on data/maps).
    maps_dir: str | None = str(MAPS_DIR)
    # Observed durations: Beta-like shrinkage of observed (EW) averages toward
    # the default estimate with this many pseudo-games, observations clipped
    # to [lo, hi] x the mode default (one-off stalls should not dominate).
    duration_prior_games: float = 2.0
    duration_obs_cap: int = 12       # an EW average is worth at most this many games
    pace_prior_games: float = 3.0
    duration_clip: tuple[float, float] = (0.6, 1.5)
    farm_level_target: int = 30      # repeat Deflation on FARM_MAPS gets farm_bonus below this level
    player_xp_full_until: int = 30   # levels below this: player XP fully valuable
    player_xp_half_until: int = 50
    tower_no_need_value: float = 0.15
    explore_bonus: float = 0.04      # UCB-style bonus for little-tried combos
    # XP into towers whose missing upgrades hold back a Hard-family strategy
    # counts this much extra (per unit of the game's XP share they receive):
    # while Hard is blocked, Medium/Easy games should build the Hard roster.
    hard_build_xp_weight: float = 1.5


DEFAULT_CONFIG = PlannerConfig()

# Map-category success multiplier applied to a strategy's base (beginner) rate
# (full strength in Hard; see MODE_GROUP_MAP_WEIGHT).
CATEGORY_SUCCESS = {"beginner": 1.0, "intermediate": 0.9, "advanced": 0.8, "expert": 0.68}
# How strongly map difficulty (category + ease) matters per medal group: an
# Easy game on an expert map is still easy, Hard/CHIMPS feel the full map.
MODE_GROUP_MAP_WEIGHT = {"easy": 0.45, "medium": 0.75, "hard": 1.0, "chimps": 1.15}
# Win-rate factor of a strategy whose upgrade build is entirely locked
# (towers placed at low tiers; the executor skips what it cannot buy). It
# rises linearly to 1.0 as the build's tower-XP cost gets unlocked.
READINESS_FLOOR = {"easy": 0.9, "medium": 0.75, "hard": 0.45, "chimps": 0.2}

# Relative ease hints within a category (1.0 = typical). Subjective community
# consensus; they only shape the prior - real win/loss stats take over fast.
MAP_EASE: dict[str, float] = {
    # beginner: long single lanes first
    "Monkey Meadow": 1.10, "Logs": 1.10, "Tree Stump": 1.05, "Town Center": 1.05,
    "In The Loop": 1.05, "Park Path": 1.05, "Alpine Run": 1.05, "Resort": 0.95,
    "Skates": 0.95, "Lotus Island": 0.95, "Candy Falls": 0.95, "The Cabin": 0.95,
    "Scrapyard": 0.95, "Skull Tweak": 0.95,
    # intermediate
    "Bloonarius Prime": 1.05, "Rake": 1.0, "Spice Islands": 1.0, "Quarry": 1.0,
    "Firing Range": 0.9, "Chutes": 0.9, "Haunted": 0.95, "Encrypted": 0.95,
    # advanced
    "Geared": 0.8, "Sunken Columns": 0.85, "Cargo": 0.85, "Cornfield": 0.85,
    "Underground": 0.85, "Spillway": 0.85,
    # expert (Dark Castle / Sanctuary / Glacial Trail are the gentlest)
    "Dark Castle": 1.05, "Sanctuary": 1.05, "Glacial Trail": 1.0, "Infernal": 0.95,
    "Ravine": 0.95, "Tricky Tracks": 0.9, "Quad": 0.85, "Flooded Valley": 0.8,
    "Muddy Puddles": 0.8, "Bloody Puddles": 0.75, "Workshop": 0.75,
    "Dark Dungeons": 0.75, "#Ouch": 0.65,
}

# Expert maps used for the Deflation XP farm (short track => fastest rounds).
FARM_MAPS = ("Infernal", "Dark Castle")
FARM_CHAIN = ("easy", "primary_only", "deflation")

# MM rewards: first completion base by reward tier x category multiplier;
# replays pay 20%. (Beginner 75/125/200/300 first, 15/25/40/60 replay; x2/x3/x4
# for intermediate/advanced/expert.) Whether "first time" is per mode or per
# difficulty is UNVERIFIED - observed rewards override.
MM_FIRST_BASE = {"easy": 75, "medium": 125, "hard": 200, "impoppable": 300}
MM_CATEGORY_MULT = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
MM_REPEAT_FRAC = 0.2
MO_MONKEY_MONEY = "Mo' Monkey Money"
MO_MONKEY_MONEY_BONUS = 0.10

HARD_GROUP = ("hard", "magic_only", "double_hp", "half_cash", "abr", "impoppable")
# Medal families in the owner's order. The Hard sub-mode chains (account.MODES
# ``requires``): hard -> magic_only -> double_hp -> half_cash and
# hard -> abr -> impoppable -> chimps.
HARD_FAMILY = HARD_GROUP + ("chimps",)
MEDIUM_FAMILY = ("medium", "military_only", "apopalypse", "reverse")
EASY_FAMILY = ("easy", "primary_only", "deflation")
NORMAL_GROUP = EASY_FAMILY + MEDIUM_FAMILY

# Tiers, best first (index = rank). See the module docstring.
TIERS = ("H", "HS", "HF", "B", "M", "E", "FARM", "LAST")
PHASES = {
    "H": "Hard standard medal on every open map (learned tracks first; "
         "unique Hard wins open the next map category)",
    "HS": "Hard sub-mode chains: Magic Only -> Double HP -> Half Cash, "
          "ABR -> Impoppable -> CHIMPS",
    "HF": "no Hard-family medal clears its threshold: highest-p Hard medal (p >= 0.7)",
    "B": "Hard blocked by missing upgrades: Medium/Easy games (p >= 0.7) that level "
         "the Hard roster's towers",
    "M": "Medium family medals (Medium, Military Only, Apopalypse, Reverse)",
    "E": "Easy family medals (Easy, Primary Only, Deflation)",
    "FARM": "no confident medal left: replay the best confident game for XP/MM",
    "LAST": "nothing is confident: the safest game",
    "DONE": "every medal earned - farm XP/MM",
}

# ---------------------------------------------------------------------------
# Tower unlock priorities
# ---------------------------------------------------------------------------

TOWER_UNLOCK_PRIORITY: dict[str, list[str]] = {
    # L2-6 (all five primaries are unlocked by L6, order only matters briefly).
    #  boomerang: long range + placement tolerant; 0-0-2 Red Hot 'Rangs pops lead
    #    (Easy r28) and 3-0-2 Glaive Ricochet carries early games on its own.
    #  bomb: lead/ceramic/MOAB answer (0-3-2 MOAB Mauler) needed for Medium/Hard.
    #  tack: cheap, strong at track bends; 2-0-4 Overdrive is a solid carry.
    #  glue: support only (MOAB glue/corrosive) - matters from Hard onward.
    #  ice: needs precise placement and pairs badly with simple bot logic.
    "primary": ["boomerang", "bomb", "tack", "glue", "ice"],
    # L7-12.
    #  sniper: global range = zero placement risk; core of the Deflation farm
    #    (0-2-4) so its tower XP should start accruing as early as possible.
    #  heli: can sit anywhere and chases bloons (pursuit); Apache/Comanche carry.
    #  ace: also placement-free, strong 2-0-3/0-0-4 later.
    #  sub: needs water (map-restricted) but 2-0-4 is excellent where usable.
    #  mortar: needs a target point (more fragile), buccaneer: water only.
    "military": ["sniper", "heli", "ace", "sub", "mortar", "buccaneer"],
    # L15-17,19,20.
    #  alchemist: 4-2-0 Stronger Stimulant is the farm buffer - unlock first so
    #    it gains XP. ninja: cheap camo DPS (4-0-2). druid: Obyn synergy, the
    #    Dark Castle CHIMPS/XP route. wizard: 0-2-4 necro is placement tolerant.
    #  super: very strong but expensive; by L20 all five are unlocked anyway.
    "magic": ["alchemist", "ninja", "druid", "wizard", "super"],
    # L22-24,26. village 2-0-2 (farm discount + camo via radar) is in the farm,
    # farm gives income for Hard modes, spike for leak defence, engineer last.
    "support": ["village", "farm", "spike", "engineer"],
}

# ---------------------------------------------------------------------------
# Upgrade needs (what the strategy roster wants unlocked, in priority order)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Need:
    priority: int          # lower = earlier
    label: str
    tower: str
    crosspath: tuple[int, int, int]


STRATEGY_NEEDS: list[Need] = [
    Need(10, "early camo dart", "dart", (0, 0, 2)),
    Need(12, "lead-popping rangs", "boomerang", (0, 0, 2)),
    Need(14, "glaive ricochet carry", "boomerang", (3, 0, 2)),
    Need(16, "MOAB mauler", "bomb", (0, 3, 2)),
    Need(18, "crossbow dart", "dart", (0, 2, 3)),
    Need(20, "deflation farm: sniper full auto", "sniper", (0, 2, 4)),
    Need(21, "deflation farm: alchemist stimulant", "alchemist", (4, 2, 0)),
    Need(22, "deflation farm: village commerce", "village", (2, 0, 2)),
    Need(25, "tack overdrive", "tack", (2, 0, 4)),
    Need(26, "MOAB glue support", "glue", (0, 2, 3)),
    Need(28, "M.O.A.R. glaives", "boomerang", (4, 0, 2)),
    Need(30, "heli pursuit/apache", "heli", (4, 0, 2)),
    Need(31, "sniper maim MOAB", "sniper", (4, 0, 2)),
    Need(32, "ninja bloonjitsu", "ninja", (4, 0, 2)),
    Need(33, "druid of the jungle (Obyn)", "druid", (1, 3, 0)),
    Need(34, "wizard necromancer", "wizard", (0, 2, 4)),
    Need(36, "MOAB assassin", "bomb", (0, 4, 2)),
    Need(38, "banana marketplace", "farm", (2, 0, 3)),
    Need(40, "ace neva-miss", "ace", (2, 0, 3)),
    Need(41, "sub armor piercing", "sub", (2, 0, 4)),
    Need(42, "village MIB", "village", (2, 3, 0)),
    Need(44, "super dark knight", "super", (2, 0, 4)),
    Need(46, "spike MOAB SHREDR", "spike", (0, 3, 2)),
    Need(50, "tack overdrive T5", "tack", (2, 0, 5)),
    Need(52, "druid spirit of the forest", "druid", (0, 4, 0)),
    Need(54, "super sun temple", "super", (4, 0, 2)),
    Need(56, "alchemist permanent brew", "alchemist", (5, 2, 0)),
]

# Tower XP per (tier) - generic estimate; observed costs override.
# UNVERIFIED: real costs differ per tower/upgrade.
UPGRADE_XP_ESTIMATE = {1: 120, 2: 400, 3: 1_500, 4: 7_000, 5: 40_000}

# ---------------------------------------------------------------------------
# Monkey Knowledge priority
# ---------------------------------------------------------------------------

# Names follow community guides (tree/tier layout may have changed since;
# UNVERIFIED for v57 - runner should fuzzy-match on screen). MK does not apply
# in CHIMPS, so the list favours MM/XP gain and robustness in other modes.
MK_PRIORITY: list[tuple[str, str, str]] = [
    (MO_MONKEY_MONEY, "magic", "+10% MM from every win (not CHIMPS)"),
    ("More Cash", "primary", "+$200 starting cash: early-round safety for every strategy"),
    ("Monkey Education", "support", "+XP for monkeys and heroes"),
    ("Bonus Monkey!", "primary", "free Dart Monkey each game"),
    ("Mana Shield", "magic", "extra shield lives - forgiving for bot leaks (non-Impoppable)"),
    ("Big Bloon Sabotage", "military", "MOAB-class spawn with less HP: Hard/Double HP"),
    ("Self Taught Heroes", "heroes", "faster hero levelling"),
    ("Elite Military Training", "military", "XP for military towers (sniper farm)"),
    ("Ceramic Shock", "military", "sniper shots slow ceramics"),
    ("Hot Magic", "magic", "magic towers pop frozen bloons"),
    ("Speedy Brewing", "magic", "alchemist attack speed (farm)"),
    ("Military Conscription", "military", "cheaper military towers"),
    ("Advanced Logistics", "military", "cheaper military towers"),
    ("Flat Pack Buildings", "support", "cheaper villages/farms"),
    ("Veteran Monkey Training", "support", "all monkeys reload faster"),
    ("Better Sell Deals", "support", "better sell value (half cash / repositioning)"),
    ("Increased Lifespan", "primary", "primary projectile lifespan"),
    ("Extra Dart Pops", "primary", "+1 dart pierce"),
    ("Lingering Magic", "magic", "magic projectile lifespan"),
    ("Airforce Upgrades", "military", "ace/heli pierce"),
    ("Heroic Reach", "heroes", "hero range"),
    ("Quick Hands", "heroes", "hero attack speed"),
    ("Global Ability Cooldowns", "support", "ability cooldowns"),
]
# When a target is locked behind tree prerequisites, buy these cheap entry
# nodes in that tree first (tier-1 names per tree, UNVERIFIED for v57).
MK_TREE_ENTRY: dict[str, list[str]] = {
    "primary": ["Increased Lifespan", "Extra Dart Pops", "Fast Tack Attacks"],
    "military": ["Elite Military Training", "Airforce Upgrades", "Naval Upgrades"],
    "magic": ["Lingering Magic", "Super Range", "Magic Tricks"],
    "support": ["Flat Pack Buildings", "One More Spike"],
    "heroes": ["Heroic Reach", "More 'Splody", "Ability Discipline"],
    "powers": ["Bigger Camo Trap", "Just One More", "Cheaper Lakes"],
}

# Hero preference when a strategy does not name one.
HERO_PRIORITY = ["obyn", "striker_jones", "gwendolin", "quincy"]

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_TOWER_ALIASES = {
    "dart_monkey": "dart", "boomerang_monkey": "boomerang", "bomb_shooter": "bomb",
    "tack_shooter": "tack", "ice_monkey": "ice", "glue_gunner": "glue",
    "sniper_monkey": "sniper", "monkey_sub": "sub", "monkey_buccaneer": "buccaneer",
    "monkey_ace": "ace", "heli_pilot": "heli", "mortar_monkey": "mortar",
    "dartling_gunner": "dartling", "wizard_monkey": "wizard", "super_monkey": "super",
    "ninja_monkey": "ninja", "druid_monkey": "druid", "banana_farm": "farm",
    "spike_factory": "spike", "monkey_village": "village", "engineer_monkey": "engineer",
    "beast_handler": "beast",
}


def canon_tower(name: str) -> str:
    n = name.strip().lower().replace(" ", "_").replace("-", "_")
    if n in TOWER_TO_CATEGORY:
        return n
    if n in _TOWER_ALIASES:
        return _TOWER_ALIASES[n]
    try:  # optional richer alias table from towers.py (written separately)
        from . import towers as _towers  # noqa: WPS433 - lazy on purpose
        aliases = getattr(_towers, "TOWER_ALIASES", None) or {}
        if n in aliases:
            return str(aliases[n])
    except Exception:  # towers.py missing or broken: not our problem here
        pass
    return n


@dataclass
class StrategySpec:
    id: str
    towers: dict[str, tuple[int, int, int]]          # required unlocked crosspaths
    modes: frozenset[str] = frozenset({"easy", "medium"})
    base_success: dict[str, float] = field(default_factory=dict)  # per mode, beginner map
    heroes: tuple[str, ...] = ()                     # preference order
    hero_required: bool = False
    maps: frozenset[str] | None = None               # allowlist
    excluded_maps: frozenset[str] = frozenset()
    categories: frozenset[str] | None = None         # allowed map categories
    cost_share: dict[str, float] | None = None       # tower XP split (default equal)
    minutes: dict[str, float] = field(default_factory=dict)  # per-mode runtime override
    notes: str = ""

    @classmethod
    def from_any(cls, obj: Any) -> "StrategySpec":
        if isinstance(obj, StrategySpec):
            return obj
        get = (lambda k, d=None: obj.get(k, d)) if isinstance(obj, Mapping) else \
              (lambda k, d=None: getattr(obj, k, d))
        towers_raw = get("towers") or {}
        towers = {canon_tower(t): tuple(int(x) for x in cp) for t, cp in dict(towers_raw).items()}
        maps = get("maps")
        cats = get("categories")
        return cls(
            id=str(get("id") or get("strategy_id") or get("name")),
            towers=towers,
            modes=frozenset(get("modes") or ("easy", "medium")),
            base_success=dict(get("base_success") or {}),
            heroes=tuple(get("heroes") or ()),
            hero_required=bool(get("hero_required", False)),
            maps=frozenset(canonical_map(m) for m in maps) if maps else None,
            excluded_maps=frozenset(canonical_map(m) for m in (get("excluded_maps") or ())),
            categories=frozenset(cats) if cats else None,
            cost_share=dict(get("cost_share")) if get("cost_share") else None,
            minutes=dict(get("minutes") or {}),
            notes=str(get("notes") or ""),
        )

    def share(self) -> dict[str, float]:
        if self.cost_share:
            tot = sum(self.cost_share.values()) or 1.0
            return {t: v / tot for t, v in self.cost_share.items()}
        n = max(1, len(self.towers))
        return {t: 1.0 / n for t in self.towers}


def _S(id: str, towers: dict[str, tuple[int, int, int]], base: dict[str, float], **kw: Any) -> StrategySpec:
    return StrategySpec(id=id, towers=towers, modes=frozenset(base), base_success=base, **kw)


# Reference roster (what the strategy layer is expected to provide). Rates are
# priors on a *beginner* map; category/ease multipliers scale them down.
EXAMPLE_STRATEGIES: list[StrategySpec] = [
    _S("dart_quincy", {"dart": (0, 0, 0)},
       {"easy": 0.75, "primary_only": 0.70, "medium": 0.40, "hard": 0.12},
       heroes=("quincy",)),
    _S("dart_boomer", {"dart": (0, 0, 2), "boomerang": (3, 0, 2)},
       {"easy": 0.92, "primary_only": 0.90, "medium": 0.80, "reverse": 0.75,
        "hard": 0.50, "abr": 0.40, "deflation": 0.45},
       heroes=("quincy", "striker_jones", "gwendolin")),
    _S("primary_moab", {"dart": (0, 2, 3), "boomerang": (4, 0, 2), "bomb": (0, 3, 2),
                        "glue": (0, 2, 3)},
       {"easy": 0.97, "primary_only": 0.95, "deflation": 0.80, "medium": 0.92,
        "reverse": 0.90, "apopalypse": 0.65, "hard": 0.85, "abr": 0.75,
        "double_hp": 0.60, "half_cash": 0.55},
       heroes=("striker_jones", "gwendolin", "quincy")),
    _S("military_snipe_heli", {"sniper": (4, 0, 2), "heli": (4, 0, 2)},
       {"medium": 0.88, "military_only": 0.85, "apopalypse": 0.70, "reverse": 0.85,
        "hard": 0.75, "abr": 0.70, "double_hp": 0.55},
       heroes=("striker_jones", "obyn", "quincy")),
    _S("deflation_farm", {"sniper": (0, 2, 4), "alchemist": (4, 2, 0), "village": (2, 0, 2)},
       {"deflation": 0.97}, categories=frozenset({"expert", "advanced"}),
       heroes=("obyn", "gwendolin", "quincy"), minutes={"deflation": 5.0},
       cost_share={"sniper": 0.55, "alchemist": 0.2, "village": 0.25}),
    _S("magic_core", {"ninja": (4, 0, 2), "wizard": (0, 2, 4), "alchemist": (4, 2, 0),
                      "druid": (1, 3, 0)},
       {"hard": 0.88, "magic_only": 0.85, "double_hp": 0.75, "half_cash": 0.65,
        "abr": 0.80, "impoppable": 0.55, "medium": 0.92, "reverse": 0.9},
       heroes=("obyn", "gwendolin")),
    _S("late_game_chimps", {"ninja": (4, 0, 2), "alchemist": (4, 2, 0), "village": (2, 3, 0),
                            "super": (2, 0, 4), "sniper": (4, 0, 2), "glue": (0, 2, 3)},
       {"chimps": 0.88, "impoppable": 0.88, "half_cash": 0.80, "double_hp": 0.85,
        "hard": 0.92, "abr": 0.88},
       heroes=("obyn", "striker_jones")),
    _S("obyn_druid_dark_castle", {"druid": (1, 3, 0), "village": (2, 3, 0), "alchemist": (4, 2, 0)},
       {"chimps": 0.85, "impoppable": 0.9, "hard": 0.95},
       heroes=("obyn",), hero_required=True, maps=frozenset({"Dark Castle"})),
]

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class UpgradeStep:
    tower: str
    path: int          # 0..2
    tier: int          # 1..5
    est_cost: float
    affordable: bool
    reason: str


@dataclass
class MKPick:
    name: str
    tree: str
    reason: str


@dataclass
class GamePlan:
    map: str
    difficulty: str          # easy/medium/hard button
    mode: str                # mode button ("standard" for the base mode)
    mode_key: str            # account medal key (pass to record_result)
    strategy_id: str
    hero: str | None
    reason: str
    reasons: list[str]
    phase: str
    p_win: float
    expected_minutes: float
    expected_xp: float
    expected_mm: float
    score: float
    first_time: bool


# ---------------------------------------------------------------------------
# Tower / upgrade / MK choices
# ---------------------------------------------------------------------------


def choose_tower_unlock(category: str, account: AccountState,
                        options: Sequence[str] | None = None) -> tuple[str | None, list[str]]:
    """Pick the tower to unlock for a level-up choice in ``category``.

    ``options`` are the towers the game offers (OCR); if omitted all locked
    non-gift-box towers of the category are assumed available."""
    reasons: list[str] = []
    if options is None:
        options = [t for t in TOWER_CATEGORIES.get(category, [])
                   if t not in GIFT_BOX_TOWERS and t not in account.unlocked_towers]
    opts = [canon_tower(o) for o in options if canon_tower(o) not in account.unlocked_towers]
    if not opts:
        return None, [f"no locked {category} tower offered"]
    prio = TOWER_UNLOCK_PRIORITY.get(category, [])
    for t in prio:
        if t in opts:
            rank = prio.index(t) + 1
            reasons.append(f"{category} pick #{rank} in priority {prio}: {t}")
            needs = [n.label for n in STRATEGY_NEEDS if n.tower == t]
            if needs:
                reasons.append(f"{t} feeds strategy needs: {', '.join(needs[:3])}")
            return t, reasons
    # unknown/new tower (e.g. one added after this list was written)
    pick = sorted(opts)[0]
    reasons.append(f"no priority entry for offered {opts}; taking {pick}")
    return pick, reasons


def _upgrade_cost(account: AccountState, tower: str, path: int, tier: int) -> float:
    obs = account.observed_upgrade_costs.get(tower, {}).get(f"{path}-{tier}")
    return float(obs) if obs is not None else float(UPGRADE_XP_ESTIMATE[tier])


def _unmet_needs(account: AccountState) -> list[Need]:
    out = []
    for n in STRATEGY_NEEDS:
        ups = account.upgrades(n.tower)
        if any(ups[i] < n.crosspath[i] for i in range(3)):
            out.append(n)
    return out


def choose_upgrade_unlocks(account: AccountState, tower_xp: Mapping[str, float] | None = None
                           ) -> tuple[list[UpgradeStep], list[str]]:
    """Ordered upgrade unlocks still wanted by STRATEGY_NEEDS (unlocked towers
    only). Steps are path-sequential (tier n needs tier n-1). ``affordable`` is
    computed by spending each tower's XP in list order."""
    txp = dict(account.tower_xp if tower_xp is None else tower_xp)
    reasons: list[str] = []
    steps: list[UpgradeStep] = []
    planned: dict[str, list[int]] = {}
    for need in sorted(STRATEGY_NEEDS, key=lambda n: n.priority):
        t = need.tower
        if t not in account.unlocked_towers:
            continue
        cur = planned.setdefault(t, account.upgrades(t))
        for path in range(3):
            for tier in range(cur[path] + 1, need.crosspath[path] + 1):
                cost = _upgrade_cost(account, t, path, tier)
                afford = txp.get(t, 0.0) >= cost
                if afford:
                    txp[t] = txp.get(t, 0.0) - cost
                steps.append(UpgradeStep(t, path, tier, cost, afford,
                                         f"needed for '{need.label}' ({t} "
                                         f"{'-'.join(map(str, need.crosspath))})"))
                cur[path] = tier
    n_aff = sum(s.affordable for s in steps)
    reasons.append(f"{len(steps)} upgrade unlocks wanted, {n_aff} affordable now")
    if steps:
        s = steps[0]
        reasons.append(f"top: {s.tower} path{s.path + 1} tier{s.tier} - {s.reason}")
    return steps, reasons


def choose_mk(account: AccountState) -> tuple[list[MKPick], list[str]]:
    """Remaining MK targets in priority order (runner buys the first one that is
    purchasable; if blocked by prerequisites it buys MK_TREE_ENTRY nodes of
    that tree first)."""
    have = set(account.mk_unlocked)
    picks = [MKPick(n, tree, why) for n, tree, why in MK_PRIORITY if n not in have]
    reasons = [f"{account.mk_points} MK point(s) available, {len(picks)} targets left"]
    if picks:
        reasons.append(f"next MK target: {picks[0].name} ({picks[0].tree}) - {picks[0].reason}")
        entry = [e for e in MK_TREE_ENTRY.get(picks[0].tree, []) if e not in have]
        if entry:
            reasons.append(f"if locked, path via {picks[0].tree} entry nodes {entry}")
    return picks, reasons


# ---------------------------------------------------------------------------
# Value model
# ---------------------------------------------------------------------------


def game_xp(mode: str, category: str, *, fail_frac: float | None = None) -> float:
    mi = MODES[mode]
    end = mi.end_round
    if fail_frac is not None:
        end = mi.start_round + int((mi.end_round - mi.start_round) * fail_frac)
    return rounds_xp(mi.start_round, end) * CATEGORY_XP_MULT[category]


def estimate_mm(account: AccountState, map_name: str, mode: str) -> tuple[float, bool, str]:
    """(MM for a win, first_time, source)."""
    first = not account.has_medal(map_name, mode)
    obs = account.map_stats.get(map_name, {}).get("observed_rewards", {}).get(mode, {})
    slot = "first" if first else "repeat"
    if slot in obs:
        return float(obs[slot]), first, "observed"
    cat = account.map_category(map_name)
    base = MM_FIRST_BASE[MODES[mode].reward_tier] * MM_CATEGORY_MULT[cat]
    mm = base if first else base * MM_REPEAT_FRAC
    if MO_MONKEY_MONEY in account.mk_unlocked and mode != "chimps":
        mm *= 1 + MO_MONKEY_MONEY_BONUS
    return mm, first, "estimate"


def _strategy_available(s: StrategySpec, account: AccountState) -> tuple[bool, str]:
    """Playable at all: every tower and a required hero unlocked. Missing
    upgrade tiers do not block (the executor plays what it can, and the game
    is how those towers earn the XP for their upgrades); they lower p via
    :func:`strategy_readiness` instead."""
    for t in s.towers:
        if t not in account.unlocked_towers:
            return False, f"tower {t} locked"
    if s.hero_required and s.heroes and not any(h in account.unlocked_heroes for h in s.heroes):
        return False, f"needs hero {s.heroes}"
    return True, "ok"


def build_fraction(s: StrategySpec, account: AccountState) -> float:
    """Share of the strategy's upgrade build (weighted by tier XP cost) that is
    unlocked: 1.0 = everything the strategy wants is available."""
    need = have = 0.0
    for t, cp in s.towers.items():
        ups = account.upgrades(t)
        for path in range(3):
            for tier in range(1, cp[path] + 1):
                w = UPGRADE_XP_ESTIMATE[tier]
                need += w
                if ups[path] >= tier:
                    have += w
    return 1.0 if need <= 0 else have / need


def strategy_readiness(s: StrategySpec, account: AccountState, mode: str) -> float:
    """Win-rate multiplier for missing upgrades (1.0 when the build is complete)."""
    floor = READINESS_FLOOR[MODES[mode].group]
    return floor + (1.0 - floor) * build_fraction(s, account)


def _strategy_fits(s: StrategySpec, map_name: str, category: str, mode: str) -> bool:
    if mode not in s.modes:
        return False
    if s.maps is not None and map_name not in s.maps:
        return False
    if map_name in s.excluded_maps:
        return False
    if s.categories is not None and category not in s.categories:
        return False
    restr = MODES[mode].restriction
    if restr and any(TOWER_TO_CATEGORY.get(t) != restr for t in s.towers):
        return False
    return True


def _pick_hero(s: StrategySpec, account: AccountState) -> str | None:
    for h in list(s.heroes) + HERO_PRIORITY:
        if h in account.unlocked_heroes:
            return h
    return None


def _prior(s: StrategySpec, map_name: str, category: str, mode: str) -> float:
    """Declared success rate scaled by map difficulty (complete build)."""
    base = s.base_success.get(mode, 0.0)
    w = MODE_GROUP_MAP_WEIGHT[MODES[mode].group]
    cat_f = max(0.05, 1.0 - (1.0 - CATEGORY_SUCCESS[category]) * w)
    ease_f = max(0.05, 1.0 + (MAP_EASE.get(map_name, 1.0) - 1.0) * w)
    return min(0.98, max(0.01, base * cat_f * ease_f))


def prior_win_probability(account: AccountState, s: StrategySpec, map_name: str, mode: str) -> float:
    """Prior p before any record/calibration: declared rate x map x readiness."""
    p = _prior(s, map_name, account.map_category(map_name), mode)
    return min(0.98, max(0.01, p * strategy_readiness(s, account, mode)))


class _Calibration:
    """Per (strategy, mode): observed wins vs. prior-expected wins on all maps."""

    def __init__(self, account: AccountState, strategies: Mapping[str, StrategySpec]):
        self.f: dict[tuple[str, str], float] = {}
        acc: dict[tuple[str, str], list[float]] = {}
        for m, mode, sid, st in account.iter_strategy_stats():
            s = strategies.get(sid)
            if s is None or m not in MAPS or mode not in MODES:
                continue
            games = st.get("wins", 0) + st.get("losses", 0)
            exp = prior_win_probability(account, s, m, mode) * games
            a = acc.setdefault((sid, mode), [0.0, 0.0])
            a[0] += st.get("wins", 0)
            a[1] += exp
        for k, (w, e) in acc.items():
            self.f[k] = min(1.6, max(0.3, (w + 2.0) / (e + 2.0)))

    def get(self, sid: str, mode: str) -> float:
        return self.f.get((sid, mode), 1.0)


def win_probability(account: AccountState, s: StrategySpec, map_name: str, mode: str,
                    cfg: PlannerConfig = DEFAULT_CONFIG, calib: _Calibration | None = None
                    ) -> tuple[float, int]:
    """Beta posterior mean and number of games for (map, mode, strategy)."""
    prior = prior_win_probability(account, s, map_name, mode)
    if calib is not None:
        prior = min(0.98, max(0.01, prior * calib.get(s.id, mode)))
    st = account.strategy_record(map_name, mode, s.id)
    w, l = st.get("wins", 0), st.get("losses", 0)
    k = cfg.prior_strength
    return (prior * k + w) / (k + w + l), w + l


def _player_xp_factor(account: AccountState, cfg: PlannerConfig) -> float:
    if account.player_level < cfg.player_xp_full_until:
        return 1.0
    if account.player_level < cfg.player_xp_half_until:
        return 0.5
    return 0.2


def _tower_need_factor(s: StrategySpec, account: AccountState, unmet_towers: set[str],
                       cfg: PlannerConfig) -> float:
    return sum(sh * (1.0 if t in unmet_towers else cfg.tower_no_need_value)
               for t, sh in s.share().items())


def p_threshold(mode: str, first_time: bool, cfg: PlannerConfig = DEFAULT_CONFIG) -> float:
    """Minimum p for a candidate to be preferred at all."""
    if not first_time:
        return cfg.min_p_repeat
    group = MODES[mode].group
    if group == "chimps":
        return cfg.min_p_chimps
    if group == "hard":
        return cfg.min_p_new_hard
    return cfg.min_p_new


# ---------------------------------------------------------------------------
# Game durations
# ---------------------------------------------------------------------------


def _shrink(prior: float, obs: float | None, n: float, k: float) -> float:
    """Blend an observed average worth ``n`` games into ``prior`` (worth ``k``)."""
    if obs is None or n <= 0:
        return prior
    return (k * prior + n * obs) / (k + n)


class _Durations:
    """Expected minutes of a *won* game for (map, mode, strategy).

    Sources, from general to specific, each blended into the previous level
    with ``duration_prior_games`` pseudo-games so a single observation moves
    the estimate but does not replace it:

    1. default: strategy ``minutes`` override, else ``MODES[mode].minutes``
    2. x account pace: how fast games actually run relative to the defaults,
       pooled over every mode (so Easy observations also calibrate Hard)
    3. this mode's observed average over all maps
    4. this (map, mode)'s exponentially weighted average (``map_stats``)
    5. this (map, mode, strategy)'s exponentially weighted average

    Observations are the EW averages ``AccountState.record_result`` keeps
    (wins only) and count as ``min(n, duration_obs_cap)`` games.
    """

    def __init__(self, account: AccountState, cfg: PlannerConfig):
        self.cfg = cfg
        lo, hi = cfg.duration_clip
        cap = cfg.duration_obs_cap
        wins: dict[tuple[str, str], int] = {}
        self.strat: dict[tuple[str, str, str], tuple[float, float]] = {}
        for m, mode, sid, st in account.iter_strategy_stats():
            if mode not in MODES:
                continue
            wins[(m, mode)] = wins.get((m, mode), 0) + int(st.get("wins", 0))
            avg = st.get("avg_minutes")
            if avg:
                d = MODES[mode].minutes
                n = min(cap, int(st.get("minutes_n") or st.get("wins") or 1))
                self.strat[(m, mode, sid)] = (min(hi * d, max(lo * d, float(avg))), n)
        self.map: dict[tuple[str, str], tuple[float, float]] = {}
        mode_acc: dict[str, list[float]] = {}
        pace_acc = [0.0, 0.0]
        for m, ms in account.map_stats.items():
            for mode, avg in (ms.get("avg_minutes") or {}).items():
                if mode not in MODES or not avg:
                    continue
                d = MODES[mode].minutes
                n = min(cap, int((ms.get("minutes_n") or {}).get(mode) or wins.get((m, mode)) or 1))
                obs = min(hi * d, max(lo * d, float(avg)))
                self.map[(m, mode)] = (obs, n)
                a = mode_acc.setdefault(mode, [0.0, 0.0])
                a[0] += n * obs
                a[1] += n
                pace_acc[0] += n * obs / d
                pace_acc[1] += n
        self.mode = {md: (a[0] / a[1], min(cap, a[1])) for md, a in mode_acc.items() if a[1]}
        self.pace_n = pace_acc[1]
        self.pace = _shrink(1.0, pace_acc[0] / pace_acc[1] if pace_acc[1] else None,
                            min(cap, pace_acc[1]), cfg.pace_prior_games)
        self.visited = {m for m, ms in account.map_stats.items()
                        if ms.get("wins", 0) or ms.get("losses", 0)}
        self._learned: dict[str, bool] = {}

    def learned(self, map_name: str) -> bool:
        """Track already learned: played before, or data/maps/<slug>.npz exists."""
        if map_name in self.visited:
            return True
        if map_name not in self._learned:
            d = self.cfg.maps_dir
            self._learned[map_name] = bool(d) and os.path.exists(
                os.path.join(d, map_slug(map_name) + ".npz"))
        return self._learned[map_name]

    def game_minutes(self, s: StrategySpec, map_name: str, mode: str) -> tuple[float, str]:
        """Minutes of a won game (no menus/scan) and where the number came from."""
        k = self.cfg.duration_prior_games
        default = s.minutes.get(mode) or MODES[mode].minutes
        est = default * self.pace
        src = [f"default {default:g}x pace {self.pace:.2f}"]
        for label, entry in (("mode", self.mode.get(mode)),
                             ("map", self.map.get((map_name, mode))),
                             ("strat", self.strat.get((map_name, mode, s.id)))):
            if entry is not None:
                est = _shrink(est, entry[0], entry[1], k)
                src.append(f"{label} {entry[0]:.1f}(n={entry[1]:g})")
        return est, " + ".join(src)

    def scan_minutes(self, map_name: str) -> float:
        """One-time placement scan the first time the bot plays a map."""
        return 0.0 if self.learned(map_name) else self.cfg.first_visit_minutes


def expected_minutes(account: AccountState, s: Any, map_name: str, mode: str,
                     config: PlannerConfig | None = None) -> float:
    """Full expected minutes of a won game incl. menus and a first-visit scan."""
    cfg = config or DEFAULT_CONFIG
    d = _Durations(account, cfg)
    m = canonical_map(map_name)
    return d.game_minutes(StrategySpec.from_any(s), m, mode)[0] + cfg.overhead_minutes \
        + d.scan_minutes(m)


# ---------------------------------------------------------------------------
# Progression tiers
# ---------------------------------------------------------------------------


def _all_maps() -> list[str]:
    return [m for m in MAPS if m not in EXCLUDED_MAPS]


def _farm_needed(account: AccountState, cfg: PlannerConfig) -> bool:
    return account.player_level < cfg.farm_level_target


# ---------------------------------------------------------------------------
# next_game
# ---------------------------------------------------------------------------


@dataclass
class _Cand:
    map: str
    mode: str
    s: StrategySpec
    p: float
    n: int
    minutes: float
    xp_win: float
    mm: float
    first: bool
    value_win: float
    value_fail: float
    score: float
    notes: list[str]
    fail_minutes: float = 0.0   # expected minutes of a lost game
    ok: bool = True             # p clears its threshold (p_threshold)
    learned: bool = False       # map track already learned (no placement scan)
    tier: str = "LAST"          # progression tier, see TIERS
    build: float = 0.0          # share of the game's tower XP that feeds the Hard build


def _normalise_strategies(available: Iterable[Any] | None) -> dict[str, StrategySpec]:
    src = EXAMPLE_STRATEGIES if available is None else available
    if isinstance(src, Mapping):
        src = list(src.values())
    out: dict[str, StrategySpec] = {}
    for obj in src:
        s = StrategySpec.from_any(obj)
        out[s.id] = s
    return out


def _missing_towers(s: StrategySpec, account: AccountState) -> set[str]:
    """Unlocked towers of ``s`` that still lack upgrades its build wants."""
    return {t for t, cp in s.towers.items() if t in account.unlocked_towers
            and any(account.upgrades(t)[i] < cp[i] for i in range(3))}


def _candidates(account: AccountState, strategies: Mapping[str, StrategySpec],
                cfg: PlannerConfig, playable_maps: set[str] | None) -> list[_Cand]:
    calib = _Calibration(account, strategies)
    durations = _Durations(account, cfg)
    unmet_towers = {n.tower for n in _unmet_needs(account)}
    usable = {sid: s for sid, s in strategies.items() if _strategy_available(s, account)[0]}
    pf = _player_xp_factor(account, cfg)
    out: list[_Cand] = []
    # Hard-build towers: missing upgrades of a strategy that, with its full
    # build, would clear the Hard fallback bar on some open Hard-family medal.
    # Their tower XP is what turns Hard from "not yet" into "winnable".
    hard_build: set[str] = set()
    for m in _all_maps():
        if playable_maps is not None and m not in playable_maps:
            continue
        if not account.map_unlocked(m):
            continue
        cat = account.map_category(m)
        learned = durations.learned(m)
        for mode in MODES:
            if mode in EXCLUDED_MODES or not account.mode_unlocked(m, mode):
                continue
            mm, first, mm_src = estimate_mm(account, m, mode)
            for s in usable.values():
                if not _strategy_fits(s, m, cat, mode):
                    continue
                p, n = win_probability(account, s, m, mode, cfg, calib)
                r = strategy_readiness(s, account, mode)
                if (first and mode in HARD_FAMILY and mode != "chimps" and r < 1.0
                        and p / r >= cfg.hard_fallback_p):
                    hard_build |= _missing_towers(s, account)
                game_min, _src = durations.game_minutes(s, m, mode)
                scan = durations.scan_minutes(m)
                t_full = game_min + cfg.overhead_minutes + scan
                t_fail = game_min * cfg.fail_time_frac + cfg.overhead_minutes + scan
                xp_win = game_xp(mode, cat)
                xp_fail = game_xp(mode, cat, fail_frac=cfg.fail_round_frac)
                notes = [f"p={p:.2f} (n={n})", f"{t_full:.1f} min"
                         + (f" incl. {scan:g} scan" if scan else ""),
                         f"mm {mm:.0f} ({mm_src}{', first' if first else ''})"]
                out.append(_Cand(m, mode, s, p, n, t_full, xp_win, mm, first,
                                 value_win=0.0, value_fail=xp_fail, score=0.0, notes=notes,
                                 fail_minutes=t_fail, learned=learned))
    # XP value: account level needs, STRATEGY_NEEDS and the Hard build
    tf_cache: dict[str, tuple[float, float]] = {}
    for c in out:
        if c.s.id not in tf_cache:
            tf = _tower_need_factor(c.s, account, unmet_towers | hard_build, cfg)
            hb = sum(sh for t, sh in c.s.share().items() if t in hard_build)
            tf_cache[c.s.id] = (0.6 * pf + 0.4 * tf + cfg.hard_build_xp_weight * hb, hb)
        xp_w, hb = tf_cache[c.s.id]
        c.build = hb
        c.value_win = c.xp_win * xp_w + cfg.mm_weight * c.mm
        c.value_fail = c.value_fail * xp_w
        c.notes.insert(2, f"xp {c.xp_win:,.0f}x{xp_w:.2f}"
                       + (f" (builds Hard roster {hb:.0%})" if hb else ""))
    return out


def _tier(c: _Cand, cfg: PlannerConfig) -> str:
    """Progression tier of a scored candidate (``c.ok`` already set)."""
    if c.mode in HARD_FAMILY:
        if c.first:
            if c.ok:
                return "H" if c.mode == "hard" else "HS"
            if c.mode != "chimps" and c.p >= cfg.hard_fallback_p:
                return "HF"
        return "FARM" if c.ok else "LAST"
    # Medium/Easy: a game that mostly feeds the Hard roster's missing upgrades
    # is worth it at the Hard fallback bar; plain medals need their threshold.
    if c.build >= 0.5 and c.p >= cfg.hard_fallback_p:
        return "B"
    if c.first and c.ok:
        return "M" if c.mode in MEDIUM_FAMILY else "E"
    return "FARM" if c.ok else "LAST"


def _sort_key(c: _Cand) -> tuple:
    """Best first with reverse=True: tier, then (H/HS) learned tracks first,
    then score - or p where the tier is about safety (HF, LAST)."""
    rank = -TIERS.index(c.tier)
    learned = 1 if c.tier in ("H", "HS") and c.learned else 0
    within = c.p if c.tier in ("HF", "LAST") else c.score
    return (rank, learned, within)


def _phase_reasons(account: AccountState, cands: list[_Cand], cfg: PlannerConfig) -> list[str]:
    """Why the top tier is what it is (for the log)."""
    reasons: list[str] = []
    if not cands:
        return reasons
    top = cands[0].tier
    count = {t: 0 for t in TIERS}
    seen: set[tuple[str, str]] = set()
    for c in cands:
        if c.first and (c.map, c.mode) not in seen and c.tier != "LAST":
            seen.add((c.map, c.mode))
            count[c.tier] += 1
    reasons.append(f"{top}: {PHASES[top]} (open medals by tier: "
                   + ", ".join(f"{t}={count[t]}" for t in ("H", "HS", "HF", "B", "M", "E")) + ")")
    if top in ("B", "M", "E", "FARM", "LAST"):
        hard = [c for c in cands if c.first and c.mode in HARD_FAMILY]
        if hard:
            b = max(hard, key=lambda c: c.p)
            reasons.append(f"no Hard-family medal reaches p>={cfg.hard_fallback_p:.2f} "
                           f"(best {b.map}/{b.mode}/{b.s.id} p={b.p:.2f}) - "
                           f"playing {top} for XP/unlocks until the roster is ready")
        elif any(c.mode in HARD_FAMILY for c in cands):
            reasons.append("every open Hard-family medal is earned")
        else:
            reasons.append("no strategy in the roster can play a Hard-family mode yet")
    if top == "HF":
        reasons.append(f"no Hard-family medal clears its threshold; best is p={cands[0].p:.2f} "
                       f">= fallback {cfg.hard_fallback_p:.2f}")
    return reasons


def rank_games(account: AccountState, available_strategies: Iterable[Any] | None = None, *,
               config: PlannerConfig | None = None, playable_maps: Iterable[str] | None = None
               ) -> tuple[str, list[str], list[_Cand]]:
    """All scored candidates, best first, plus the phase (top tier) and reasons."""
    cfg = config or DEFAULT_CONFIG
    strategies = _normalise_strategies(available_strategies)
    pm = {canonical_map(m) for m in playable_maps} if playable_maps is not None else None
    cands = _candidates(account, strategies, cfg, pm)
    uniq = account.unique_map_wins()
    thresholds = sorted(v for v in CATEGORY_UNLOCK_WINS.values() if v > 0)
    farming = _farm_needed(account, cfg)

    for c in cands:
        bonus = 0.0
        if c.first:
            bonus += cfg.goal_medal_value
            nu = len(mode_unlocks(c.mode))
            if nu:
                bonus += cfg.unlock_value * nu
            if not account.medals.get(c.map) and uniq < thresholds[-1]:
                u = cfg.unique_win_value
                if uniq + 1 in thresholds:
                    u *= cfg.threshold_win_bonus
                    c.notes.append(f"win #{uniq + 1} opens a category")
                bonus += u
                c.notes.append("new unique map")
            if c.mode == "hard" and c.p >= cfg.hard_ready_p:
                bonus += cfg.hard_medal_value
                c.notes.append("reliable Hard medal")
        vw = c.value_win + bonus
        vf = c.value_fail - cfg.loss_penalty
        if farming and not c.first and c.map in FARM_MAPS and c.mode == "deflation":
            vw = c.value_win * cfg.farm_bonus
            c.notes.append("designated farm")
        minutes = c.p * c.minutes + (1 - c.p) * (c.fail_minutes or c.minutes * cfg.fail_time_frac)
        score = (c.p * vw + (1 - c.p) * vf) / minutes
        score *= 1.0 + cfg.explore_bonus / math.sqrt(c.n + 1)
        thr = p_threshold(c.mode, c.first, cfg)
        c.ok = c.p >= thr
        c.tier = _tier(c, cfg)
        if not c.ok:
            c.notes.append(f"below p threshold {thr}")
        if c.learned:
            c.notes.append("learned track")
        c.score = score
    cands.sort(key=_sort_key, reverse=True)
    if not account.remaining_goals():
        return "DONE", [PHASES["DONE"]], cands
    if not cands:
        return "LAST", ["no playable candidate"], cands
    return cands[0].tier, _phase_reasons(account, cands, cfg), cands


def next_game(account: AccountState, available_strategies: Iterable[Any] | None = None, *,
              config: PlannerConfig | None = None, playable_maps: Iterable[str] | None = None
              ) -> GamePlan | None:
    """Best next game, or None if no strategy can be played on any open map.

    ``available_strategies``: StrategySpec / dict / objects (see StrategySpec);
    defaults to EXAMPLE_STRATEGIES. ``playable_maps`` restricts to maps the
    bot has placement data for."""
    phase, preasons, cands = rank_games(account, available_strategies,
                                        config=config, playable_maps=playable_maps)
    if not cands:
        return None
    c = cands[0]
    mi = MODES[c.mode]
    hero = _pick_hero(c.s, account)
    reasons = list(preasons)
    chosen = (f"[{phase}] {c.map} / {c.mode} with {c.s.id}: score {c.score:,.0f}/min; "
              + ", ".join(c.notes))
    reasons.append(chosen)
    if len(cands) > 1:
        r = cands[1]
        reasons.append(f"runner-up {r.map}/{r.mode}/{r.s.id} score {r.score:,.0f}/min")
    if account.pending_tower_choices:
        reasons.append(f"pending tower choices: {account.pending_tower_choices}")
    xp_exp = c.p * c.xp_win + (1 - c.p) * game_xp(c.mode, account.map_category(c.map),
                                                    fail_frac=DEFAULT_CONFIG.fail_round_frac)
    return GamePlan(
        map=c.map, difficulty=mi.difficulty, mode=mi.ui_mode, mode_key=c.mode,
        strategy_id=c.s.id, hero=hero, reason=chosen,
        reasons=reasons, phase=phase, p_win=round(c.p, 3),
        expected_minutes=round(c.minutes, 1), expected_xp=round(xp_exp),
        expected_mm=round(c.p * c.mm), score=round(c.score, 1), first_time=c.first,
    )


def strategy_by_id(strategy_id: str, available_strategies: Iterable[Any] | None = None
                   ) -> StrategySpec | None:
    return _normalise_strategies(available_strategies).get(strategy_id)


def split_tower_xp(strategy: StrategySpec, xp: float) -> dict[str, float]:
    """Approximate per-tower XP for a game when the runner cannot OCR it
    (game XP is split by cash spent; cost_share approximates that)."""
    return {t: xp * sh for t, sh in strategy.share().items()}
