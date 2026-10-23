"""Progression planner: decides what the bot does next on the account.

Public API (every function also returns human readable reasons for logs):

* :func:`choose_tower_unlock` - which tower to take on a level-up choice
* :func:`choose_upgrade_unlocks` - which upgrades to buy with tower XP
* :func:`choose_mk` - Monkey Knowledge priority list
* :func:`next_game` - the next (map, difficulty, mode, strategy, hero), or
  None when nothing is left to play
* :func:`paragon_status` - towers still short of their paragon (tower XP)

The owner's hard rule: NEVER play a map/mode whose medal is already earned.
A replay pays only ~20% of the first-time Monkey Money (MM_REPEAT_FRAC) and
no medal, unlock or black-border progress, so beaten (map, mode) pairs are
never even candidates (:func:`_candidates` skips them): no tier, fallback or
achievement bonus can bring a replay back. When no first-time medal is
winnable, :func:`next_game` returns None and the runner idles with the
reason "nothing left to play: every unlocked map/mode is beaten or not
winnable yet" (:data:`NOTHING_LEFT`).

Progression policy (the owner's order: Hard first, levelled up through the
Hard sub-modes until CHIMPS, Medium and Easy only afterwards). Every
candidate is a first-time medal and falls in one tier; the best tier wins,
the score only ranks within a tier (see :data:`PHASES` and :func:`_tier`):

    H    Hard standard medal, p >= min_p_new_hard (0.8), on every open map -
         unique Hard wins also open the next map category
    HS   Hard sub-mode medal, p >= its threshold: Magic Monkeys Only ->
         Double HP -> Half Cash, and ABR -> Impoppable -> CHIMPS
    HF   nothing Hard-family clears 0.8: the highest-p Hard-family medal with
         p >= hard_fallback_p (0.7; never CHIMPS)
    B    Hard is blocked by missing upgrades: a Medium/Easy medal (p >= 0.7)
         whose towers are mostly the ones the Hard roster still needs XP for
    M    Medium family medal (Medium, Military Only, Apopalypse, Reverse),
         p >= min_p_new (0.75)
    E    Easy family medal (Easy, Primary Only, Deflation), p >= min_p_new

Within a tier, games with p >= CONFIDENT_P (0.85) go first. (Ranking the
0.7-0.8 Hard fallback below Medium/Easy was tried: in the long simulation
it did not lower the loss rate - those games are only delayed - and it
stalled progress, because Hard wins open map categories and earn the most
tower XP: 340 instead of 560 medals.)

A medal below every bar that applies to it is "not winnable yet" and is not
played at all (losses are never acceptable); it comes back once tower XP,
unlocked upgrades or the strategy's record raise its p. M/E are reached
while the roster is too weak for Hard (they then serve as XP/unlock games)
or once the winnable Hard-family medals are used up. In H/HS, maps whose
track is already learned (no placement scan) go first.

Objective (the bot runs unattended; it maximises Monkey Money + XP + CHIMPS
black borders per hour). Within a tier candidates are ranked by expected
points per hour::

    V_win  = w_xp*XP*(1 + hard_build_xp_weight*build + paragon_xp_weight*paragon)
             + w_mm*MM + black-border progress + CHIMPS medal value
             + unlock/unique-map value + achievement value
    V_loss = w_xp*XP_partial*(same multiplier) - loss_penalty
    points/h = 60 * (p*V_win + (1-p)*V_loss) / (p*T_win + (1-p)*T_loss)

Tower XP is split between tower types by the cash invested in them
(docs/tower_xp.md; StrategySpec.cost_share estimates it from the YAML plan),
and two kinds of tower XP count extra:

    build    share of the game's tower XP going to towers whose missing
             upgrades keep a Hard-family strategy below the fallback bar
    paragon  share going to towers that still lack their paragon, each
             weighted by how close it is to it (1.0 when at most one Hard
             game's XP is missing, 0.5 at twice that, ...), so the nearest
             paragon is finished before XP is spread thin. Counted only in
             games with p >= paragon_min_p (0.85, above every medal
             threshold), so it never makes a riskier game look better and
             never changes p or the tier. See :func:`paragon_status`.

Weights (PlannerConfig; 1 point = 1 player XP):

    w_xp = 1        XP = sum of per-round XP x map multiplier (beginner 1.0,
                    intermediate 1.1, advanced 1.2, expert 1.3); Impoppable/
                    CHIMPS (R6-100) are the best XP per game when winnable
    w_mm = 250      a first-time Hard beginner win (200 MM) ~ 50k points,
                    an expert one (800 MM) ~ 200k
    w_bb = 600,000  per black-bordered map (all 14 medals), spread over its
                    medals on a convex curve (bb_linear_share=0.3 linear,
                    rest quadratic): the 1st medal on a map ~15k, the 14th
                    ~71k, so finishing maps beats spreading thin
    chimps_medal_value = 150,000  the CHIMPS medal itself is the prize
    loss_penalty = 30,000         lost opportunity on top of the wasted time
    achievement_value = 30,000    per achievement, split over its wins

``p`` comes from a Beta posterior over this (map, mode, strategy)'s record,
with a prior from the strategy's declared success rates, the map's
category/ease (scaled by how hard the mode is), how much of the strategy's
upgrade build is unlocked, and the strategy's calibration on other maps.
``T`` is learned from observed game durations incl. menus and the first-visit
placement scan (see :class:`_Durations`). MM is the observed reward for this
(map, mode) when the account has one (``map_stats[map].observed_rewards``),
else the MM_FIRST_BASE x MM_CATEGORY_MULT estimate.

The runner only needs to::

    plan = next_game(account, strategies)
    if plan is None: ... wait and plan again later (nothing winnable is left) ...
    ... play plan ...
    account.record_result(plan.map, plan.mode_key, plan.strategy_id, won, ...)

Strategies are described with :class:`StrategySpec` (or dicts / objects with
the same attributes). ``EXAMPLE_STRATEGIES`` is a reference roster used by the
tests and as a fallback; the real roster should come from the strategy layer.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .account import (
    CATEGORY_UNLOCK_WINS, CATEGORY_XP_MULT, EXCLUDED_MAPS, EXCLUDED_MODES,
    GIFT_BOX_TOWERS, MAPS, MODES, PROJECT_ROOT, TOWER_CATEGORIES, TOWER_TO_CATEGORY,
    AccountState, canonical_map, mode_unlocks, rounds_xp,
)

log = logging.getLogger("planner")

# Learned map tracks (btd6bot/maplearn.py writes data/maps/<slug>.npz after
# the placement scan of a map's first visit).
MAPS_DIR = PROJECT_ROOT / "data" / "maps"
# Tower-XP prices of every upgrade and paragon (docs/tower_xp.md).
TOWER_XP_FILE = PROJECT_ROOT / "data" / "tower_xp.json"

# The one line logged when there is no first-time medal the bot may play.
NOTHING_LEFT = "nothing left to play: every unlocked map/mode is beaten or not winnable yet"


def map_slug(name: str) -> str:
    """Same slug as maplearn.slug (not imported: maplearn pulls in cv2)."""
    return "".join(c for c in name.lower() if c.isalnum())

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------


@dataclass
class PlannerConfig:
    # ---- objective weights (points; 1 point = 1 player XP), see module doc
    w_xp: float = 1.0
    w_mm: float = 250.0              # points per Monkey Money
    w_bb: float = 600_000            # points per black-bordered map (all 14 medals)
    bb_linear_share: float = 0.3     # rest of the black-border value is quadratic in medals
    chimps_medal_value: float = 150_000
    unlock_value: float = 3_000      # per mode a medal unlocks
    unique_win_value: float = 25_000  # first win on a map while < 20 unique wins
    threshold_win_bonus: float = 1.5  # multiplier when the win crosses 5/12/20
    overhead_minutes: float = 1.0    # menus, loading, collecting rewards
    first_visit_minutes: float = 2.5  # one-time placement scan on a never-played map
    fail_time_frac: float = 0.7      # a loss costs this fraction of the full time
    fail_round_frac: float = 0.6     # ... and reaches this fraction of the rounds
    loss_penalty: float = 30_000     # points lost per loss on top of the wasted time
    prior_strength: float = 3.0      # Beta prior pseudo-games
    # Losses are expensive (time, no rewards): only attempt confident games.
    # (Beaten map/modes are never played at all, see the module docstring.)
    min_p_new: float = 0.75          # minimum p to attempt an unearned Easy/Medium-group medal
    min_p_new_hard: float = 0.80     # ... an unearned Hard-group medal
    min_p_chimps: float = 0.80
    # A Hard standard medal with p >= hard_ready_p counts as "reliable" (logs/tests;
    # the tier order itself puts Hard first).
    hard_ready_p: float = 0.80
    # No Hard-family medal clears its threshold: still play the highest-p one
    # (not CHIMPS) if p >= this, rather than dropping to Medium/Easy.
    hard_fallback_p: float = 0.70
    # Where learned map tracks live (None: only maps already played count as
    # learned - used by tests so they do not depend on data/maps).
    maps_dir: str | None = str(MAPS_DIR)
    # Maps whose geometry was read from the game files need no first-visit
    # scan either (False: ignore data/map_geometry - used by tests).
    use_game_geometry: bool = True
    # Achievements: catalog + live scan (None: no achievement planning).
    # A win that advances an incomplete achievement is worth
    # achievement_value / wins_needed extra (moderate: medals still lead).
    achievements_path: str | None = str(PROJECT_ROOT / "data" / "achievements.json")
    achievements_state_path: str | None = str(PROJECT_ROOT / "data" / "achievements_state.json")
    achievement_value: float = 30_000
    # Observed durations: Beta-like shrinkage of observed (EW) averages toward
    # the default estimate with this many pseudo-games, observations clipped
    # to [lo, hi] x the mode default (one-off stalls should not dominate).
    duration_prior_games: float = 2.0
    duration_obs_cap: int = 12       # an EW average is worth at most this many games
    pace_prior_games: float = 3.0
    duration_clip: tuple[float, float] = (0.6, 1.5)
    explore_bonus: float = 0.04      # UCB-style bonus for little-tried combos
    # XP into towers whose missing upgrades hold back a Hard-family strategy
    # counts this much extra (per unit of the game's XP share they receive):
    # while Hard is blocked, Medium/Easy games should build the Hard roster.
    hard_build_xp_weight: float = 1.5
    # Paragon focus (see paragon_status): XP into towers still short of their
    # paragon counts this much extra, times how close each tower is. With 3.0,
    # XP into a tower at most one Hard game away from its paragon counts four
    # times. The owner: "a large part of the script should be to help unlock
    # needed paragons" - among confident games, the build that feeds the
    # nearest paragon wins (every tower has a solo build: strategies/generated).
    paragon_xp_weight: float = 3.0
    # "Close" means at most this much tower XP missing: one full Hard game
    # (rounds 3-80) on a beginner map, from the round XP table (126,150).
    paragon_reach_xp: float = float(rounds_xp(MODES["hard"].start_round, MODES["hard"].end_round))
    # Paragon XP is a bonus goal: it only counts in games the planner is quite
    # sure of (above every medal threshold), so it never trades win chance
    # for tower XP in a marginal game.
    paragon_min_p: float = 0.85
    # Upgrade/paragon XP prices (None: no paragon focus - used by tests).
    tower_xp_path: str | None = str(TOWER_XP_FILE)


DEFAULT_CONFIG = PlannerConfig()

# Map-category success multiplier applied to a strategy's base (beginner) rate
# (full strength in Hard; see MODE_GROUP_MAP_WEIGHT).
CATEGORY_SUCCESS = {"beginner": 1.0, "intermediate": 0.9, "advanced": 0.8, "expert": 0.68}
# How strongly map difficulty (category + ease) matters per medal group: an
# Easy game on an expert map is still easy, Hard/CHIMPS feel the full map.
MODE_GROUP_MAP_WEIGHT = {"easy": 0.45, "medium": 0.75, "hard": 1.0, "chimps": 1.15}
# Modes whose map weight differs from their group's. Deflation counts as an
# Easy medal but plays rounds 31-60 on a fixed $20,000 with no income, so
# the opening must hold the hardest rounds: map difficulty matters as in
# Hard. (Ancient Portal Deflation, rated 0.86 with the Easy weight, leaked
# 91 lives in one wave at round 52; Bloonarius Prime died to one blimp.)
MODE_MAP_WEIGHT = {"deflation": 0.9}
# Share of the map-difficulty penalty a map's own build still takes (its
# base_success was set for that map; a little caution remains until played).
OWN_MAP_WEIGHT = 0.25
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

# MM rewards: first completion base by reward tier x category multiplier;
# replays pay 20% (the reason the planner never replays a beaten map/mode).
# Beginner first-time Easy/Medium/Hard/Impoppable+CHIMPS =
# 75/125/200/300 (as the difficulty screen shows), replays 15/25/40/60;
# intermediate/advanced/expert x2/x3/x4 (community tables, UNVERIFIED for
# v57). Whether "first time" is per mode or per difficulty is UNVERIFIED -
# observed rewards (account map_stats observed_rewards) override.
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

# Tiers, best first (index = rank); every candidate in them is a first-time
# medal. See the module docstring.
# Progression, best first. The owner's order since the evening of
# 2026-10-22: "go back to prioritizing hard mode and hard maps" - Hard
# medals, then the Hard sub-modes, then the safer fallbacks, Medium-family
# and Easy-family last (they pay the least XP and Monkey Money per minute).
# Within a tier, harder maps first (HARD_MAPS_FIRST). Safety stays ahead
# of both: confident games (p >= CONFIDENT_P) sort first in every tier, and
# after repeated losses the circuit breaker (safety.py) allows Easy-family
# medals only. (The morning's warm-up order is TIERS_WARM_UP.)
TIERS_HARD_FIRST = ("H", "HS", "HF", "B", "M", "E")
TIERS_WARM_UP = ("E", "M", "H", "HS", "HF", "B")
TIERS = TIERS_HARD_FIRST
HARD_MAPS_FIRST = True
# Map categories by ease: 3 beginner .. 0 expert.
CATEGORY_EASE = {"beginner": 3, "intermediate": 2, "advanced": 1, "expert": 0}
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
    "NONE": NOTHING_LEFT,   # rank_games found nothing playable: next_game is None
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
    # Tower XP split = cash invested per tower type; the runner passes the
    # YAML plan's cash (strategy.invested_cash). Default: an equal split.
    cost_share: dict[str, float] | None = None
    # The towers that do the plan's damage (placed with role "dps"): whether
    # they can reach a map's track decides how well the plan fits the map
    # (mapfit). Empty: not known, no map-fit adjustment.
    dps_kinds: tuple[str, ...] = ()
    minutes: dict[str, float] = field(default_factory=dict)  # per-mode runtime override
    notes: str = ""
    # Achievement strategies (strategies/achievements/*.yaml): the achievement
    # this plan earns. Planned only while that achievement is single-player,
    # incomplete and ``bot_ready`` is True (unknown readiness = not ready).
    achievement: str | None = None
    bot_ready: bool | None = None
    wins_needed: int | None = None

    @classmethod
    def from_any(cls, obj: Any) -> "StrategySpec":
        if isinstance(obj, StrategySpec):
            return obj
        get = (lambda k, d=None: obj.get(k, d)) if isinstance(obj, Mapping) else \
              (lambda k, d=None: getattr(obj, k, d))
        towers_raw = get("towers") or {}
        towers = {canon_tower(t): tuple(int(x) for x in cp) for t, cp in dict(towers_raw).items()}
        maps = get("maps")
        if not maps and get("map"):  # achievement yaml pins a single map
            maps = [get("map")]
        cats = get("categories")
        cons = get("constraints") or {}
        wins = get("wins_needed") or (cons.get("wins_needed") if isinstance(cons, Mapping) else None)
        ready = get("bot_ready")
        sid = str(get("id") or get("strategy_id") or get("name"))
        ach = get("achievement")
        if not ach and sid.startswith("ach_"):
            # achievement plan passed without its tag: never treat it as a
            # normal strategy (its constraints would be ignored) - unplannable
            ach = "?" + sid
        return cls(
            id=sid,
            towers=towers,
            modes=frozenset(get("modes") or ("easy", "medium")),
            base_success=dict(get("base_success") or {}),
            heroes=tuple(get("heroes") or ()),
            hero_required=bool(get("hero_required", False)),
            maps=frozenset(canonical_map(m) for m in maps) if maps else None,
            excluded_maps=frozenset(canonical_map(m) for m in (get("excluded_maps") or ())),
            categories=frozenset(cats) if cats else None,
            cost_share=dict(get("cost_share")) if get("cost_share") else None,
            dps_kinds=tuple(canon_tower(k) for k in (get("dps_kinds") or ())),
            minutes=dict(get("minutes") or {}),
            notes=str(get("notes") or ""),
            achievement=str(ach) if ach else None,
            bot_ready=None if ready is None else bool(ready),
            wins_needed=int(wins) if wins else None,
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
    first_time: bool         # always True: beaten map/modes are never planned


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
    """(MM for a win, first_time, source). The planner only asks about
    first-time medals; the replay figure documents why it never replays."""
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
    w = MODE_MAP_WEIGHT.get(mode, MODE_GROUP_MAP_WEIGHT[MODES[mode].group])
    if s.maps is not None and len(s.maps) == 1 and not s.achievement:
        # a map's own researched build (strategies/maps): its declared rate
        # is already about THIS map, so its difficulty is not counted twice
        w *= OWN_MAP_WEIGHT
    cat_f = max(0.05, 1.0 - (1.0 - CATEGORY_SUCCESS[category]) * w)
    ease_f = max(0.05, 1.0 + (MAP_EASE.get(map_name, 1.0) - 1.0) * w)
    return min(0.98, max(0.01, base * cat_f * ease_f))


# Double Cash (boosts.py) pays every pop twice. Hard-family games are lost
# when the defence cannot be afforded in time - and map difficulty mostly
# acts through that - so with twice the money the chance of LOSING is
# multiplied by this factor. An estimate: the per-strategy calibration and the
# win/loss record correct it as games are played. First set to 0.35 after
# two clean Hard wins; the next hour lost 6 of 7 Hard games rated 0.85-0.92
# (bad placement and unspent cash, not money), so it is 0.6 until the
# record shows better.
DOUBLE_CASH_LOSS_FACTOR = 0.6


# Map fit (mapfit.py): the share of the early track that the plan's damage
# towers can reach from cells where they may stand. At FULL_FIT or more the
# plan fits; below it the win chance shrinks in proportion, down to
# MIN_FIT_FACTOR. Money does not help a plan whose towers cannot reach the
# bloons, so this applies after Double Cash. (Luminous Cove Hard with a land
# plan - ninjas 0.33, super monkeys 0.09 - was rated 0.86 and lost.)
FULL_FIT = 0.6
MIN_FIT_FACTOR = 0.3


def map_fit_factor(s: StrategySpec, map_name: str, mode: str) -> float:
    """1.0 when the plan's damage towers reach enough of the track (or when
    that is not measured), less when they do not."""
    from .mapfit import strategy_fit
    fit = strategy_fit(map_name, s.dps_kinds, reverse=(mode == "reverse"), weights=s.cost_share,
                       last_round=MODES[mode].end_round)
    if fit is None:
        return 1.0
    return min(1.0, max(MIN_FIT_FACTOR, fit / FULL_FIT))


def prior_win_probability(account: AccountState, s: StrategySpec, map_name: str, mode: str) -> float:
    """Prior p before any record/calibration: declared rate x map x readiness,
    then the account's Double Cash (when it pays in this mode), then how well
    the plan's towers can reach this map's track."""
    from .boosts import double_cash_applies
    p = _prior(s, map_name, account.map_category(map_name), mode)
    p *= strategy_readiness(s, account, mode)
    if double_cash_applies(getattr(account, "boosts", {}), mode):
        p = 1.0 - (1.0 - p) * DOUBLE_CASH_LOSS_FACTOR
    p *= map_fit_factor(s, map_name, mode)
    if s.maps is None:
        # a general build answers for the map's record too: Last Resort Hard
        # was lost by three general builds in turn, each of them rated 0.8-0.9
        # untested there because only its own record counted
        lost = map_mode_losses(account).get((canonical_map(map_name), mode), 0)
        p *= max(MAP_LOSS_FLOOR, MAP_LOSS_FACTOR ** lost)
    ceiling = model_ceiling(map_name, mode)
    if ceiling is not None and ceiling < CEILING_PLAYABLE:
        # no build the map research found holds there: not trusted until a
        # win on record raises the posterior (win_probability)
        p = min(p, CEILING_P_CAP)
    return min(0.98, max(0.01, p))


# Every loss on a (map, mode), by any strategy, scales the prior of the
# general builds there by MAP_LOSS_FACTOR (two losses: 0.49), down to
# MAP_LOSS_FLOOR. Map-specific builds keep only their own record.
MAP_LOSS_FACTOR = 0.7
MAP_LOSS_FLOOR = 0.3


def map_mode_losses(account: AccountState) -> dict[tuple[str, str], int]:
    """{(map, mode): losses by any strategy}, rebuilt when a game was added."""
    key = (id(account), account.games_played, len(account.strategy_stats))
    cached = getattr(account, "_map_mode_losses", None)
    if cached is None or cached[0] != key:
        out: dict[tuple[str, str], int] = {}
        for m, mode, _sid, st in account.iter_strategy_stats():
            if st.get("losses"):
                out[(m, mode)] = out.get((m, mode), 0) + int(st["losses"])
        cached = (key, out)
        try:
            account._map_mode_losses = cached
        except AttributeError:
            pass
    return cached[1]


# Map/modes where even the best build found rates under this margin
# (data/model_ceiling.json) are capped at CEILING_P_CAP - below every play
# threshold - until a win is on record. Bazaar Hard (best 1.76) and Balance
# Hard (1.63) were won the same night; Party Parade Hard (1.33) and Pat's
# Pond Hard (1.35) were lost at their last rounds.
CEILING_PLAYABLE = 1.5
CEILING_P_CAP = 0.5
_CEILINGS = None


def model_ceiling(map_name: str, mode: str) -> float | None:
    """The best margin any researched build reached for (map, mode), or None
    when it was not measured (data/model_ceiling.json; "Map|*" = all modes)."""
    global _CEILINGS
    if _CEILINGS is None:
        import json
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "data" / "model_ceiling.json"
        try:
            _CEILINGS = json.loads(path.read_text(encoding="utf-8")).get("ceilings", {})
        except (OSError, ValueError):
            _CEILINGS = {}
    m = canonical_map(map_name)
    return _CEILINGS.get(f"{m}|{mode}", _CEILINGS.get(f"{m}|*"))


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


def p_threshold(mode: str, cfg: PlannerConfig = DEFAULT_CONFIG) -> float:
    """Minimum p for a first-time medal in ``mode`` to be played in its normal
    tier (the HF/B fallbacks of :func:`_tier` accept down to hard_fallback_p)."""
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
        """Track already known: played before, data/maps/<slug>.npz exists, or
        the map's geometry was read from the game files (no scan needed)."""
        if map_name in self.visited:
            return True
        if map_name not in self._learned:
            d = self.cfg.maps_dir
            known = bool(d) and os.path.exists(os.path.join(d, map_slug(map_name) + ".npz"))
            if d and not known and self.cfg.use_game_geometry:
                from . import mapgeom
                known = mapgeom.map_id_for(map_name) is not None
            self._learned[map_name] = known
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
# Achievements
# ---------------------------------------------------------------------------

ACH_DONE = ("complete", "collect")   # "collect" = finished, reward not claimed yet
_ACH_WINS_RE = re.compile(r"\b(?:win|beat|complete)\s+(\d+)\s+(?:games?|maps?|times)", re.I)
_json_cache: dict[str, tuple[float, Any]] = {}   # path -> (mtime, parsed JSON)


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load_json_cached(path: str | None) -> Any:
    """JSON file, re-read only when its mtime changes; None if missing/broken.
    Used for the achievement files and data/tower_xp.json."""
    if not path:
        return None
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    hit = _json_cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    _json_cache[path] = (mt, data)
    return data


def load_achievements(cfg: PlannerConfig | None = None) -> tuple[list[dict] | None, dict | None]:
    """(catalog, live state) from the paths in the config (None when absent)."""
    cfg = cfg or DEFAULT_CONFIG
    cat = _load_json_cached(cfg.achievements_path)
    if isinstance(cat, Mapping):
        cat = cat.get("achievements")
    return (cat if isinstance(cat, list) else None), _load_json_cached(cfg.achievements_state_path)


def _card_rank(card: Mapping[str, Any]) -> tuple[int, float]:
    st = card.get("status")
    return (2 if st in ACH_DONE else 1 if st == "progress" else 0, float(card.get("progress") or 0))


def match_achievement_state(catalog: Sequence[Mapping[str, Any]],
                            state: Mapping[str, Any] | None) -> dict[str, dict]:
    """Catalog name -> scanned card. Card names are OCR'd, so they are matched
    fuzzily on the name and, failing that, on the description."""
    cards = (state or {}).get("cards") or {}
    by_name = {_norm_text(e["name"]): e["name"] for e in catalog if e.get("name")}
    by_desc = {_norm_text(e.get("description") or ""): e["name"] for e in catalog
               if e.get("description")}
    out: dict[str, dict] = {}
    for card_name, card in cards.items():
        if not isinstance(card, Mapping):
            continue
        n = _norm_text(card_name)
        hit = by_name.get(n)
        if hit is None and n:
            m = difflib.get_close_matches(n, list(by_name), n=1, cutoff=0.8)
            hit = by_name[m[0]] if m else None
        if hit is None and len(n) >= 6:  # banner titles get cut off: unique prefix
            pre = [full for k, full in by_name.items() if k.startswith(n)]
            hit = pre[0] if len(pre) == 1 else None
        if hit is None and card.get("desc"):
            m = difflib.get_close_matches(_norm_text(card["desc"]), list(by_desc), n=1, cutoff=0.9)
            hit = by_desc[m[0]] if m else None
        if hit is None:
            continue
        if hit not in out or _card_rank(card) > _card_rank(out[hit]):
            out[hit] = dict(card)
    return out


@dataclass
class AchievementGoal:
    name: str
    kind: str
    status: str                 # complete/collect/progress/unknown
    progress: float             # percent from the live scan (0 if unknown)
    modes: tuple[str, ...]      # planner modes whose wins advance it passively
    map: str | None             # only on this map (None = any)
    strategy: str | None        # catalog's suggested strategy id
    passive: bool
    wins_needed: int

    @property
    def plannable(self) -> bool:
        return bool(self.modes) or bool(self.strategy)

    def per_game_value(self, cfg: PlannerConfig) -> float:
        """XP-equivalent bonus for one win that advances this achievement."""
        return cfg.achievement_value / max(1, self.wins_needed)


def _wins_needed(entry: Mapping[str, Any]) -> int:
    m = _ACH_WINS_RE.search(entry.get("description") or "")
    if m:
        return int(m.group(1))
    # lifetime counters (pops, kills) need many games; a single win is a step
    return 10 if entry.get("kind") == "cumulative" else 1


def wanted_achievements(account: AccountState, state: Mapping[str, Any] | None,
                        catalog: Sequence[Mapping[str, Any]] | None) -> list[AchievementGoal]:
    """Single-player achievements not complete yet (excluded categories such
    as co-op/boss/race/odyssey/contested territory/daily challenge/events/
    purchase are never returned). ``plannable`` ones have modes or a strategy
    the planner can steer towards; the rest accrue passively. Most advanced
    first."""
    if not catalog:
        return []
    cards = match_achievement_state(catalog, state)
    out: list[AchievementGoal] = []
    for e in catalog:
        if e.get("category") != "single_player" or not e.get("name"):
            continue
        card = cards.get(e["name"], {})
        status = str(card.get("status") or "unknown")
        if status in ACH_DONE:
            continue
        mode = e.get("mode")
        modes = (mode,) if e.get("passive") and mode in MODES and mode not in EXCLUDED_MODES else ()
        mp = e.get("map")
        try:
            mp = canonical_map(mp) if mp else None
        except KeyError:
            mp = None
        if mp in EXCLUDED_MAPS:
            continue
        out.append(AchievementGoal(
            name=e["name"], kind=str(e.get("kind") or ""), status=status,
            progress=float(card.get("progress") or 0), modes=modes, map=mp,
            strategy=e.get("strategy"), passive=bool(e.get("passive")),
            wins_needed=_wins_needed(e)))
    # a CHIMPS/Impoppable medal etc. already earned on the account means the
    # one-win achievements of that mode are done even if the scan lags behind
    out = [g for g in out if not (g.wins_needed == 1 and g.kind == "game_win_constraint"
                                  and g.modes and g.map is None
                                  and _account_has_mode_win(account, g.modes[0]))]
    out.sort(key=lambda g: (-g.progress, g.name))
    return out


def _account_has_mode_win(account: AccountState, mode: str) -> bool:
    return any(d.get(mode) for d in account.medals.values())


def _strategy_achievement_ok(s: StrategySpec, goals: Mapping[str, AchievementGoal]) -> bool:
    """An achievement strategy is planned only for a wanted (single-player,
    incomplete) achievement and only when its plan is marked bot_ready."""
    if not s.achievement:
        return True
    return s.bot_ready is True and s.achievement in goals


# ---------------------------------------------------------------------------
# Paragon focus
# ---------------------------------------------------------------------------
#
# A paragon needs every regular upgrade of its tower (all three tier 5s) and
# then its own tower-XP price. Tower XP only comes from games that spend cash
# on that tower type. Which towers have a paragon and what each upgrade costs
# is game data (data/tower_xp.json); what the account owns comes from the
# Monkeys-menu sync (unlocked_upgrades, tower_xp = unspent XP, paragons).
# Games that invest in towers still short of their paragon are worth more
# (the "paragon" term of the objective in the module docstring).


@dataclass(frozen=True)
class TowerXpPrices:
    """Tower-XP prices of one tower type, from data/tower_xp.json."""
    tower: str                               # tower id, as in the account and strategies
    upgrade_xp: tuple[tuple[int, ...], ...]  # [path 0..2][tier - 1] -> XP to unlock
    paragon: str | None                      # paragon name (None: the tower has none)
    paragon_xp: int                          # XP to unlock the paragon (0 without one)


def load_tower_xp_prices(path: str | None) -> dict[str, TowerXpPrices]:
    """Tower id -> XP prices. Tower names in the file are matched to ids with
    towers.find_tower; an unknown name (a tower newer than towers.py) is
    skipped. Empty when the file is missing or ``path`` is None."""
    data = _load_json_cached(path)
    if not isinstance(data, Mapping):
        return {}
    from . import towers as _towers  # pure data module, imported lazily like canon_tower
    out: dict[str, TowerXpPrices] = {}
    for name, entry in (data.get("towers") or {}).items():
        tower = _towers.find_tower(name)
        if tower is None or not isinstance(entry, Mapping):
            continue
        paths = entry.get("paths") or {}
        upgrade_xp = tuple(
            tuple(int(u.get("xp") or 0) for u in sorted(paths.get(str(p), []), key=lambda u: u["tier"]))
            for p in (1, 2, 3))
        par = entry.get("paragon") or {}
        out[tower] = TowerXpPrices(tower, upgrade_xp, par.get("name"),
                                   int(par.get("xp_to_unlock") or 0))
    return out


@dataclass(frozen=True)
class ParagonGoal:
    """A tower that still needs tower XP before its paragon can be unlocked."""
    tower: str
    paragon: str
    remaining_xp: float   # locked upgrades + paragon price - unspent tower XP
    closeness: float      # 0..1: 1.0 = at most cfg.paragon_reach_xp missing

    @property
    def label(self) -> str:
        return f"{self.tower} (needs {_fmt_xp(self.remaining_xp)} XP)"


@dataclass
class ParagonStatus:
    """Where every owned paragon tower stands (see :func:`paragon_status`)."""
    focus: list[ParagonGoal]   # still short of XP, closest to its paragon first
    banked: list[str]          # enough XP banked for every upgrade + the paragon
    unknown: list[str]         # all upgrades unlocked, XP short, paragon not read yet
    done: list[str]            # paragon unlocked (read in the Monkeys menu)

    def reason(self) -> str | None:
        """One log line, or None when there is nothing to say."""
        parts = []
        if self.focus:
            shown = 5  # the closest few are the ones that matter
            more = len(self.focus) - shown
            parts.append("paragon focus (closest first): "
                         + ", ".join(g.label for g in self.focus[:shown])
                         + (f" +{more} more" if more > 0 else ""))
        if self.banked:
            parts.append("paragon XP already banked: " + ", ".join(self.banked))
        if self.unknown:
            parts.append("paragon not read yet (next account sync): " + ", ".join(self.unknown))
        return "; ".join(parts) or None


def _fmt_xp(xp: float) -> str:
    """Short XP amount for log lines: 120000 -> '120k', 1050000 -> '1.05M'."""
    return f"{xp / 1e6:.2f}M" if xp >= 1e6 else f"{xp / 1e3:.0f}k"


def paragon_status(account: AccountState, cfg: PlannerConfig = DEFAULT_CONFIG) -> ParagonStatus:
    """Which owned towers still need XP for their paragon, and how much.

    For every tower that has a paragon in data/tower_xp.json:

    * paragon read as unlocked (account.paragons)          -> done
    * XP still needed = XP of the upgrades still locked + the paragon's
      price - the tower's unspent XP; nothing needed      -> banked
      (either it is unlocked already, or it can be unlocked right now)
    * every upgrade unlocked but the paragon never read    -> unknown: it
      may well be unlocked already, so no XP is steered to it until the
      account sync (xpspend.sync_all) has looked at its upgrade tree
    * otherwise                                            -> focus

    A focus tower's closeness is min(1, paragon_reach_xp / XP needed): a
    tower one Hard game (or less) from its paragon counts fully, one ten
    games away counts 10%. That makes finishing the nearest paragon worth
    more than spreading the same XP over several towers."""
    status = ParagonStatus([], [], [], [])
    for tower, prices in sorted(load_tower_xp_prices(cfg.tower_xp_path).items()):
        if prices.paragon is None or tower not in account.unlocked_towers:
            continue
        if account.paragons.get(tower):
            status.done.append(tower)
            continue
        have = account.upgrades(tower)
        locked_xp = sum(xp for path, tiers in enumerate(prices.upgrade_xp)
                        for tier, xp in enumerate(tiers, start=1) if tier > have[path])
        banked = float(account.tower_xp.get(tower) or 0.0)
        needed = max(0.0, locked_xp + prices.paragon_xp - banked)
        if needed <= 0:
            status.banked.append(tower)
        elif locked_xp == 0 and tower not in account.paragons:
            status.unknown.append(tower)
        else:
            closeness = min(1.0, cfg.paragon_reach_xp / needed)
            status.focus.append(ParagonGoal(tower, prices.paragon, needed, closeness))
    status.focus.sort(key=lambda g: g.remaining_xp)
    return status


def paragon_share(s: StrategySpec, status: ParagonStatus) -> tuple[float, list[ParagonGoal]]:
    """(share of the strategy's tower XP that goes to focus towers, each
    weighted by its closeness - 0..1; the focus towers it feeds, most-fed
    first)."""
    share = s.share()
    fed = sorted(((share[g.tower] * g.closeness, g) for g in status.focus if share.get(g.tower)),
                 key=lambda wg: -wg[0])
    return sum(w for w, _ in fed), [g for _, g in fed]


# ---------------------------------------------------------------------------
# Progression tiers
# ---------------------------------------------------------------------------


def _all_maps() -> list[str]:
    return [m for m in MAPS if m not in EXCLUDED_MAPS]


BB_MODES = tuple(m for m in MODES if m not in EXCLUDED_MODES)  # the 14 medals


def _bb_curve(k: int, cfg: PlannerConfig) -> float:
    """Share of a map's black-border value held with ``k`` of its medals."""
    x = min(1.0, k / len(BB_MODES))
    return cfg.bb_linear_share * x + (1.0 - cfg.bb_linear_share) * x * x


def map_medal_count(account: AccountState, map_name: str) -> int:
    d = account.medals.get(map_name, {})
    return sum(1 for m in BB_MODES if d.get(m))


def black_border_value(account: AccountState, map_name: str, mode: str,
                       cfg: PlannerConfig = DEFAULT_CONFIG) -> float:
    """Points for earning the ``mode`` medal on ``map_name`` now: progress
    toward the map's black border (worth more the closer the map is to all
    medals) plus the CHIMPS medal's own value."""
    if account.has_medal(map_name, mode) or mode not in BB_MODES:
        return 0.0
    k = map_medal_count(account, map_name)
    v = cfg.w_bb * (_bb_curve(k + 1, cfg) - _bb_curve(k, cfg))
    if mode == "chimps":
        v += cfg.chimps_medal_value
    return v


# ---------------------------------------------------------------------------
# next_game
# ---------------------------------------------------------------------------


@dataclass
class _Cand:
    """One (map, mode, strategy) the bot could play next - always a medal the
    account does not have yet (beaten map/modes never become candidates)."""
    map: str
    mode: str
    s: StrategySpec
    p: float
    n: int
    minutes: float
    xp_win: float
    mm: float
    first: bool                 # always True; kept for GamePlan.first_time (runner)
    value_win: float
    value_fail: float
    score: float
    notes: list[str]
    fail_minutes: float = 0.0   # expected minutes of a lost game
    ok: bool = True             # p clears its threshold (p_threshold)
    learned: bool = False       # map track already learned (no placement scan)
    tier: str | None = None     # progression tier (TIERS); None = not winnable yet
    build: float = 0.0          # share of the game's tower XP that feeds the Hard build
    paragon: float = 0.0        # closeness-weighted share feeding unfinished paragons
    ach: float = 0.0            # XP-equivalent achievement value of a win
    achievements: tuple[str, ...] = ()  # achievements a win advances
    per_hour: float = 0.0       # objective: expected points per hour (score * 60)
    ease: int = 0               # map category: 3 beginner .. 0 expert (warm-up order)


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
                cfg: PlannerConfig, playable_maps: set[str] | None,
                paragons: ParagonStatus) -> list[_Cand]:
    """Every (open map, unearned mode, fitting strategy) with its win chance,
    duration, XP and Monkey Money value. Beaten (map, mode) pairs are skipped
    right here, so nothing downstream can ever pick a replay."""
    calib = _Calibration(account, strategies)
    durations = _Durations(account, cfg)
    usable = {sid: s for sid, s in strategies.items() if _strategy_available(s, account)[0]}
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
            if account.has_medal(m, mode):
                continue  # the owner's rule: never replay a beaten map/mode
            mm, _first, mm_src = estimate_mm(account, m, mode)
            for s in usable.values():
                if not _strategy_fits(s, m, cat, mode):
                    continue
                p, n = win_probability(account, s, m, mode, cfg, calib)
                r = strategy_readiness(s, account, mode)
                if (mode in HARD_FAMILY and mode != "chimps" and r < 1.0
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
                         f"mm {mm:.0f} ({mm_src}, first)"]
                out.append(_Cand(m, mode, s, p, n, t_full, xp_win, mm, True,
                                 value_win=0.0, value_fail=xp_fail, score=0.0, notes=notes,
                                 fail_minutes=t_fail, learned=learned,
                                 ok=p >= p_threshold(mode, cfg), ease=CATEGORY_EASE.get(cat, 0)))
    # XP + MM value. Tower XP counts extra where it unblocks the Hard roster
    # and, in games the planner is quite sure of (paragon_min_p), where it
    # brings a paragon closer (it must never make a riskier game look better).
    per_strategy: dict[str, tuple[float, float, list[ParagonGoal]]] = {}
    for c in out:
        if c.s.id not in per_strategy:
            hb = sum(sh for t, sh in c.s.share().items() if t in hard_build)
            per_strategy[c.s.id] = (hb, *paragon_share(c.s, paragons))
        hb, pf, feeds = per_strategy[c.s.id]
        if not (c.ok and c.p >= cfg.paragon_min_p):
            pf, feeds = 0.0, []
        xp_w = cfg.w_xp * (1.0 + cfg.hard_build_xp_weight * hb + cfg.paragon_xp_weight * pf)
        c.build, c.paragon = hb, pf
        c.value_win = c.xp_win * xp_w + cfg.w_mm * c.mm
        c.value_fail = c.value_fail * xp_w
        why = ([f"builds Hard roster {hb:.0%}"] if hb else []) \
            + (["paragon focus: " + ", ".join(g.label for g in feeds[:2])] if feeds else [])
        c.notes.insert(2, f"xp {c.xp_win:,.0f}x{xp_w:.2f}" + (f" ({'; '.join(why)})" if why else ""))
    return out


def _tier(c: _Cand, cfg: PlannerConfig) -> str | None:
    """Progression tier of a first-time medal candidate (``c.ok`` already
    set), or None when its p is below every bar that applies to it: such a
    medal is not winnable yet and is never played."""
    if c.mode in HARD_FAMILY:
        if c.ok:
            return "H" if c.mode == "hard" else "HS"
        if c.mode != "chimps" and c.p >= cfg.hard_fallback_p:
            return "HF"
        return None
    # Medium/Easy: a game that mostly feeds the Hard roster's missing upgrades
    # is worth it at the Hard fallback bar; plain medals need their threshold.
    if c.build >= 0.5 and c.p >= cfg.hard_fallback_p:
        return "B"
    if c.ok:
        return "M" if c.mode in MEDIUM_FAMILY else "E"
    return None


# Within a tier, games the planner is at least this sure of go first, so a
# bonus (an achievement, more Monkey Money) never puts a shaky game ahead of
# a near-certain one: losses are never acceptable.
CONFIDENT_P = 0.85

# The owner's preferred plans: within a tier and confidence class they come
# first. Sniper Elite Defender + a radar village shoots the whole map from
# wherever there is room ("they can solo many maps"), the answer to maps
# with little land near the track.
PREFERRED_STRATEGIES = ("hard_sniper_elite",)


def _sort_key(c: _Cand) -> tuple:
    """Best first with reverse=True: tier, then confident games (p >=
    CONFIDENT_P), then the owner's preferred plans (PREFERRED_STRATEGIES),
    then (H/HS) learned tracks, then score - or p in HF, the
    tier that is about safety."""
    rank = -TIERS.index(c.tier)
    confident = 1 if c.p >= CONFIDENT_P else 0
    # a map's own researched build (strategies/maps: one map only) and the
    # owner's preferred plans come first
    own_map = c.s.maps is not None and len(c.s.maps) == 1 and not c.s.achievement
    preferred = 1 if own_map or c.s.id in PREFERRED_STRATEGIES else 0
    learned = 1 if c.tier in ("H", "HS") and c.learned else 0
    within = c.p if c.tier == "HF" else c.score
    maps = -c.ease if HARD_MAPS_FIRST else c.ease     # expert maps first, or beginner first
    if HARD_MAPS_FIRST:
        # safer first among confident games: a map's own build, a learned
        # track - then the hardest map
        return (rank, confident, preferred, learned, maps, within)
    return (rank, confident, maps, preferred, learned, within)


def _open_unearned(account: AccountState, modes: Iterable[str]) -> bool:
    """Is any of ``modes`` open but not yet beaten on some unlocked map?"""
    return any(account.mode_unlocked(m, mode) and not account.has_medal(m, mode)
               for m in _all_maps() for mode in modes)


def _phase_reasons(account: AccountState, scored: list[_Cand], cands: list[_Cand],
                   cfg: PlannerConfig) -> list[str]:
    """Why the top tier is what it is (for the log). ``scored`` holds every
    first-time candidate, ``cands`` only the playable ones, best first."""
    if not cands:
        line = NOTHING_LEFT
        if scored:  # name the open medal that is closest to winnable
            b = max(scored, key=lambda c: c.p)
            line += (f" (closest: {b.map}/{b.mode} with {b.s.id} p={b.p:.2f}, "
                     f"needs {p_threshold(b.mode, cfg):.2f})")
        return [line]
    top = cands[0].tier
    # every open medal counted once, in the best tier it reaches
    count = {t: 0 for t in TIERS}
    seen: set[tuple[str, str]] = set()
    for c in cands:
        if (c.map, c.mode) not in seen:
            seen.add((c.map, c.mode))
            count[c.tier] += 1
    not_yet = len({(c.map, c.mode) for c in scored} - seen)
    reasons = [f"{top}: {PHASES[top]} (open medals by tier: "
               + ", ".join(f"{t}={count[t]}" for t in TIERS) + f"; not winnable yet: {not_yet})"]
    if TIERS is TIERS_WARM_UP and top in ("M", "E") and any(c.tier in ("H", "HS") for c in scored):
        reasons.append("warm-up order: Easy-family medals first, then Medium, then Hard "
                       "(the Hard medals already in reach wait their turn)")
    elif top in ("B", "M", "E"):
        hard = [c for c in scored if c.mode in HARD_FAMILY]
        if hard:
            b = max(hard, key=lambda c: c.p)
            reasons.append(f"no Hard-family medal clears its bar (best {b.map}/{b.mode}/{b.s.id} "
                           f"p={b.p:.2f}) - playing confident {top} medals for XP/unlocks "
                           f"until the roster is ready")
        elif _open_unearned(account, HARD_FAMILY):
            reasons.append("no strategy in the roster can play the open Hard-family medals yet")
        else:
            reasons.append("every open Hard-family medal is earned")
    if top == "HF":
        reasons.append(f"no Hard-family medal clears its threshold; best is p={cands[0].p:.2f} "
                       f">= fallback {cfg.hard_fallback_p:.2f}")
    return reasons


def _achievement_values(c: _Cand, goals: Mapping[str, AchievementGoal],
                        cfg: PlannerConfig) -> None:
    """Achievements a win of ``c`` advances, and their value."""
    names = []
    for g in goals.values():
        if c.mode in g.modes and (g.map is None or g.map == c.map):
            names.append(g.name)
    g = goals.get(c.s.achievement) if c.s.achievement else None
    # an achievement plan counts in the modes that advance its achievement (or
    # in any of its modes when the plan itself enforces the constraint)
    if g is not None and g.name not in names and (not g.modes or c.mode in g.modes):
        names.append(g.name)
    if names:
        c.achievements = tuple(names)
        c.ach = sum(goals[n].per_game_value(cfg) for n in names)
        c.notes.append("achievement: " + ", ".join(names))


def rank_games(account: AccountState, available_strategies: Iterable[Any] | None = None, *,
               config: PlannerConfig | None = None, playable_maps: Iterable[str] | None = None,
               achievements: tuple[Sequence[Mapping[str, Any]] | None, Mapping[str, Any] | None]
               | None = None,
               ) -> tuple[str, list[str], list[_Cand]]:
    """The candidates the bot may play, best first, plus the phase (top tier,
    or "NONE") and reasons for the log.

    Only first-time medals are candidates, and only those whose p clears the
    bar of a tier (see :func:`_tier`); with none left the phase is "NONE"
    and the first reason is :data:`NOTHING_LEFT`.

    ``achievements``: (catalog, live state); default: loaded from the paths
    in the config (data/achievements.json, data/achievements_state.json)."""
    cfg = config or DEFAULT_CONFIG
    strategies = _normalise_strategies(available_strategies)
    catalog, ach_state = achievements if achievements is not None else load_achievements(cfg)
    goals = {g.name: g for g in wanted_achievements(account, ach_state, catalog)}
    # achievement plans only for wanted, bot-ready achievements
    strategies = {sid: s for sid, s in strategies.items() if _strategy_achievement_ok(s, goals)}
    pm = {canonical_map(m) for m in playable_maps} if playable_maps is not None else None
    paragons = paragon_status(account, cfg)
    scored = _candidates(account, strategies, cfg, pm, paragons)
    uniq = account.unique_map_wins()
    thresholds = sorted(v for v in CATEGORY_UNLOCK_WINS.values() if v > 0)

    for c in scored:
        # what a first win adds on top of XP and MM (all candidates are first-time)
        bb = black_border_value(account, c.map, c.mode, cfg)
        bonus = bb
        k = map_medal_count(account, c.map)
        c.notes.append(f"black border {k}->{k + 1}/{len(BB_MODES)} (+{bb:,.0f})")
        bonus += cfg.unlock_value * len(mode_unlocks(c.mode))
        if k == 0 and uniq < thresholds[-1]:  # no medal on this map yet
            u = cfg.unique_win_value
            if uniq + 1 in thresholds:
                u *= cfg.threshold_win_bonus
                c.notes.append(f"win #{uniq + 1} opens a category")
            bonus += u
            c.notes.append("new unique map")
        _achievement_values(c, goals, cfg)
        bonus += c.ach
        vw = c.value_win + bonus
        vf = c.value_fail - cfg.loss_penalty
        minutes = c.p * c.minutes + (1 - c.p) * (c.fail_minutes or c.minutes * cfg.fail_time_frac)
        score = (c.p * vw + (1 - c.p) * vf) / minutes
        score *= 1.0 + cfg.explore_bonus / math.sqrt(c.n + 1)
        c.per_hour = score * 60.0
        c.notes.append(f"{c.per_hour:,.0f} pts/h")
        c.tier = _tier(c, cfg)
        if not c.ok:
            c.notes.append(f"below p threshold {p_threshold(c.mode, cfg)}")
        if c.learned:
            c.notes.append("learned track")
        c.score = score
    # Playable: a tier, i.e. p clears the bar that applies. Achievement plans
    # never use the lower HF/B fallback bars (losses are unacceptable).
    cands = [c for c in scored if c.tier is not None and (c.ok or not c.s.achievement)]
    cands.sort(key=_sort_key, reverse=True)
    reasons = _phase_reasons(account, scored, cands, cfg)
    paragon_line = paragons.reason()
    if paragon_line:
        reasons.append(paragon_line)
    if goals:
        steer = [g.name for g in goals.values() if g.plannable]
        reasons.append(f"achievements: {len(goals)} incomplete single-player, "
                       f"{len(steer)} steerable" + (f" ({', '.join(steer[:6])}"
                                                   + (", ..." if len(steer) > 6 else "") + ")"
                                                   if steer else ""))
    return (cands[0].tier if cands else "NONE"), reasons, cands


def next_game(account: AccountState, available_strategies: Iterable[Any] | None = None, *,
              config: PlannerConfig | None = None, playable_maps: Iterable[str] | None = None,
              achievements: tuple[Sequence[Mapping[str, Any]] | None, Mapping[str, Any] | None]
              | None = None,
              ) -> GamePlan | None:
    """Best next game, or None when no first-time medal is winnable (every
    open map/mode is beaten or below its p bar); the reason is logged.

    ``available_strategies``: StrategySpec / dict / objects (see StrategySpec);
    defaults to EXAMPLE_STRATEGIES. ``playable_maps`` restricts to maps the
    bot has placement data for."""
    phase, preasons, cands = rank_games(account, available_strategies, config=config,
                                        playable_maps=playable_maps, achievements=achievements)
    if not cands:
        log.info("%s", preasons[0])
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
