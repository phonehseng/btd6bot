"""When to press which activated-ability hotkey. Pure logic, no game access.

The match loop feeds an :class:`AbilityPlanner` the towers on the board and
the round/lives state about once a second; ``decide()`` returns the hotkey
numbers (1..9) to press right now.

Assumptions (none of these can be observed directly, so they are kept
conservative and are cheap to be wrong about - pressing a hotkey whose
ability is missing or still cooling down does nothing in BTD6):

* **Hero level** is not read from the screen. It is estimated from the XP of
  the rounds completed since the hero was placed (``account.round_xp`` - the
  same per-round formula the game uses for player XP), divided by the hero's
  levelling-cost scale.  An ability is *pressed* once the optimistic estimate
  (x HERO_XP_OPTIMISM) reaches its level, but only counted as *certainly*
  unlocked once the pessimistic estimate (x HERO_XP_PESSIMISM) does.  For a
  1.0x hero placed on round 1: level 3 is tried from round 7 (certain from
  round 9), level 10 is tried from ~round 47 (certain ~round 60).
* **Hotkeys**: abilities get hotkeys 1..N in the order they appeared on the
  board.  Hero abilities are slotted at their (central-estimate) unlock round,
  tower abilities at the round they were bought.  Identical tower abilities
  (two MOAB Assassins) share one slot.  A tier-5 ability replacing a tier-4
  one is treated as a new slot at the end.  If this ordering is wrong the
  worst case is pressing a different ability; abilities that must never fire
  blindly (targeting / debt / sacrifice) are only a risk through that.
* **Cooldowns** (``cooldown_s``, upper bounds: MK and hero levels shorten
  them) are in game seconds at 1x.  The bot always plays at 2x, so a cooldown
  elapses in ``cooldown_s / speed`` real seconds.  Cooldowns are assumed to
  run only while a round is in progress (BTD6 pauses them between rounds).
* A press is never confirmed.  A press made while the ability is only
  *maybe* available (hero level uncertain, or a tower ability that may still
  have its initial cooldown) is retried every RETRY_GAME_S game seconds; a
  press made while it is *certainly* available waits the full cooldown.
"""
from __future__ import annotations

import logging

from . import towers as T
from .account import round_xp
from .strategy import THREATS

log = logging.getLogger("abilities")

MAX_HOTKEY = 9                # ability hotkeys 1..9 (0/-/= exist but are not used)
RETRY_GAME_S = 20.0           # retry interval for unconfirmed presses (game seconds)
MOAB_DELAY_S = 3.0            # real seconds into a MOAB round before 'moab' abilities fire
MAX_DT_S = 10.0               # longest real gap counted toward cooldowns between calls
HERO_XP_OPTIMISM = 1.5        # "maybe unlocked": XP estimate x this
HERO_XP_PESSIMISM = 0.8       # "certainly unlocked": XP estimate x this

# Rounds with notable MOAB-class content even if the calendar would not say so.
HEAVY_ROUNDS = {40, 60, 63, 76, 78, 80, 95, 98, 100}

# XP needed per level for a 1.0x hero (Quincy): level L needs HERO_LEVEL_XP[L] in total.
_LEVEL_STEP = [180, 460, 1000, 1860, 3280, 5180, 8320, 9380, 13620, 16380,
               14400, 16650, 14940, 16380, 17820, 19260, 20700, 16470, 17280]
HERO_LEVEL_XP = [0, 0]
for _s in _LEVEL_STEP:
    HERO_LEVEL_XP.append(HERO_LEVEL_XP[-1] + _s)

# Levelling-cost scale per hero (higher = levels slower).  # ? (from memory)
HERO_XP_SCALE = {
    "quincy": 1.0, "gwendolin": 1.0, "striker_jones": 1.0, "obyn": 1.0,
    "etienne": 1.0, "geraldo": 1.0,
    "ezili": 1.425, "pat_fusty": 1.425, "admiral_brickell": 1.425, "sauda": 1.425,
    "rosalia": 1.425,  # ?
    "benjamin": 1.5, "psi": 1.5, "corvus": 1.5,  # corvus ?
    "churchill": 1.71, "adora": 1.71,
    "silas": 1.425, "dan_dmonke": 1.425,  # ?
}

# Activated tower abilities by upgrade name: (cooldown_s at 1x, use).  # ? cooldowns
# Passive "abilities" (Bomb Blitz, Energizer) have no button and are left out.
# 'never' = needs a target click, costs money/lives, or otherwise unsafe blind.
TOWER_ABILITIES = {
    "Super Monkey Fan Club": (50, "on_cooldown"),
    "Plasma Monkey Fan Club": (50, "on_cooldown"),
    "Turbo Charge": (45, "on_cooldown"),
    "MOAB Assassin": (30, "moab"),
    "MOAB Eliminator": (10, "moab"),
    "Blade Maelstrom": (20, "on_cooldown"),
    "Super Maelstrom": (20, "on_cooldown"),
    "Snowstorm": (30, "on_cooldown"),
    "Absolute Zero": (20, "on_cooldown"),
    "Glue Strike": (30, "on_cooldown"),
    "Glue Storm": (30, "on_cooldown"),
    "Supply Drop": (60, "on_cooldown"),
    "First Strike Capability": (60, "never"),      # click-targeted
    "Monkey Pirates": (60, "moab"),
    "Pirate Lord": (45, "moab"),
    "Ground Zero": (45, "on_cooldown"),
    "Tsar Bomba": (30, "on_cooldown"),
    "Support Chinook": (60, "on_cooldown"),
    "Special Poperations": (60, "never"),          # marine needs placing
    "Artillery Battery": (60, "on_cooldown"),
    "Pop and Awe": (60, "on_cooldown"),
    "Rocket Storm": (40, "on_cooldown"),
    "Summon Phoenix": (60, "on_cooldown"),
    "Tech Terror": (45, "on_cooldown"),
    "The Anti-Bloon": (45, "on_cooldown"),
    "Legend of the Night": (60, "on_cooldown"),
    "Bloon Sabotage": (60, "on_cooldown"),
    "Grand Saboteur": (60, "moab"),
    "Transforming Tonic": (60, "on_cooldown"),
    "Total Transformation": (60, "on_cooldown"),
    "Jungle's Bounty": (60, "on_cooldown"),
    "IMF Loan": (90, "never"),                      # takes on debt
    "Monkey-Nomics": (90, "on_cooldown"),
    "Spike Storm": (60, "on_cooldown"),
    "Carpet of Spikes": (60, "on_cooldown"),
    "Call to Arms": (45, "on_cooldown"),
    "Homeland Defense": (60, "on_cooldown"),
    "Overclock": (45, "never"),                     # needs a tower picked
    "Ultraboost": (45, "never"),
}


def _tower_ability_index():
    """(kind, path 1..3, tier 1..5) -> upgrade name, for TOWER_ABILITIES."""
    out = {}
    for kind, t in T.TOWERS.items():
        for pi, path in enumerate(t.get("upgrades", []), start=1):
            for u in path:
                if u["name"] in TOWER_ABILITIES:
                    out[(kind, pi, u["tier"])] = u["name"]
    return out


TOWER_ABILITY_AT = _tower_ability_index()


def tower_abilities(kind, tiers):
    """Activated abilities a tower with these tiers has (highest per path, plus
    IMF Loan alongside Monkey-Nomics)."""
    out = []
    for pi, tier in enumerate(tiers or (), start=1):
        names = [TOWER_ABILITY_AT[(kind, pi, t)] for t in range(1, (tier or 0) + 1)
                 if (kind, pi, t) in TOWER_ABILITY_AT]
        if names:
            if names[-1] == "Monkey-Nomics" and "IMF Loan" in names:
                out.append("IMF Loan")
            out.append(names[-1])
    return out


# -- hero level -----------------------------------------------------------------

def hero_xp(placed_round, current_round):
    """XP from the rounds completed since placement (XP is paid at round end;
    the hero earns the round it was placed in)."""
    if placed_round is None or current_round is None or current_round <= placed_round:
        return 0
    return sum(round_xp(r) for r in range(placed_round, current_round))


def level_for_hero_xp(xp, hero=None):
    scale = HERO_XP_SCALE.get(hero, 1.0)
    lvl = 1
    for L in range(2, len(HERO_LEVEL_XP)):
        if xp >= HERO_LEVEL_XP[L] * scale:
            lvl = L
        else:
            break
    return lvl


def estimate_hero_level(hero, placed_round, current_round, factor=1.0):
    return level_for_hero_xp(hero_xp(placed_round, current_round) * factor, hero)


def unlock_round(hero, placed_round, level, factor=1.0, horizon=200):
    """First round during which the hero is estimated to have ``level``."""
    if placed_round is None:
        return None
    for r in range(placed_round, placed_round + horizon):
        if estimate_hero_level(hero, placed_round, r, factor) >= level:
            return r
    return None


# -- rounds -----------------------------------------------------------------------

def moab_start_round(rules=None):
    shift = (rules or {}).get("threat_shift", {})
    for r, threat in THREATS:
        if threat == "moab":
            return shift.get("moab", r)
    return 40


def is_moab_round(rnd, rules=None):
    return rnd is not None and (rnd in HEAVY_ROUNDS or rnd >= moab_start_round(rules))


# -- planner ------------------------------------------------------------------------

class _Slot:
    __slots__ = ("name", "last_press", "last_certain")

    def __init__(self, name):
        self.name = name
        self.last_press = None      # game time of the last press
        self.last_certain = False   # was the ability certainly available then?


class AbilityPlanner:
    def __init__(self, hero=None, rules=None, speed=2.0):
        self.hero = hero
        self.rules = rules or {}
        self.speed = speed
        self.hero_round = None          # round the hero was placed
        self.slots = {}                 # ability name -> _Slot (currently on the board)
        self._tower_seen = {}           # ability name -> (acquired round, game_t, seq)
        self._seq = 0
        self.game_t = 0.0               # in-round game seconds elapsed
        self._prev_now = None
        self._prev_in_round = False
        self._prev_round = None
        self.round_start = None         # real time the current round started
        self.last_fired = []            # [(hotkey, name, reason)] of the last decide()

    # -- board state ------------------------------------------------------------
    def update_towers(self, towers, rnd):
        """towers: objects with .tid, .kind ('hero' or a tower id) and .tiers."""
        names = set()
        has_hero = False
        for p in towers:
            if p.kind == "hero":
                has_hero = True
                continue
            names.update(tower_abilities(p.kind, p.tiers))
        if has_hero and self.hero_round is None:
            self.hero_round = rnd if rnd is not None else self.rules.get("start_round", 1)
        if not has_hero:
            self.hero_round = None
        for n in names:
            if n not in self._tower_seen:
                self._seq += 1
                self._tower_seen[n] = (rnd if rnd is not None else 0, self.game_t, self._seq)
        for n in list(self._tower_seen):
            if n not in names:
                del self._tower_seen[n]  # sold: a later re-buy is a new slot

    def _hero_abilities(self, rnd):
        """[(order key, name, use, cooldown, certain)] for hero abilities that may be unlocked."""
        if self.hero_round is None or rnd is None:
            return []
        out = []
        abilities = T.HEROES.get(self.hero, {}).get("abilities", [])
        lvl_hi = estimate_hero_level(self.hero, self.hero_round, rnd, HERO_XP_OPTIMISM)
        lvl_lo = estimate_hero_level(self.hero, self.hero_round, rnd, HERO_XP_PESSIMISM)
        for i, ab in enumerate(abilities):
            if lvl_hi < ab["level"]:
                continue
            ur = unlock_round(self.hero, self.hero_round, ab["level"]) or rnd
            out.append(((ur, 0, i), "hero:" + ab["name"], ab.get("use", "never"),
                        ab.get("cooldown_s"), lvl_lo >= ab["level"]))
        return out

    def hotkeys(self, rnd):
        """[(hotkey, name, use, cooldown, certain_now)] in assumed hotkey order."""
        entries = list(self._hero_abilities(rnd))
        for n, (r, t0, seq) in self._tower_seen.items():
            cd, use = TOWER_ABILITIES[n]
            # a fresh tower ability may start on cooldown: certain after one cooldown
            entries.append(((r, 1, seq), n, use, cd, self.game_t - t0 >= cd))
        entries.sort(key=lambda e: e[0])
        return [(i, name, use, cd, certain)
                for i, (_, name, use, cd, certain) in enumerate(entries, start=1)
                if i <= MAX_HOTKEY]

    # -- decisions --------------------------------------------------------------
    def _advance(self, now, rnd, in_round):
        if self.rules.get("continuous"):
            in_round = True
        if self._prev_now is not None and in_round and self._prev_in_round:
            self.game_t += max(0.0, min(now - self._prev_now, MAX_DT_S)) * self.speed
        if in_round and (not self._prev_in_round or rnd != self._prev_round):
            self.round_start = now
        if not in_round:
            self.round_start = None
        self._prev_now, self._prev_in_round, self._prev_round = now, in_round, rnd
        return in_round

    def _due(self, slot, cooldown):
        if slot.last_press is None:
            return True
        if slot.last_certain and cooldown:
            wait = cooldown
        else:  # unconfirmed press: retry (a press on cooldown does nothing)
            wait = min(RETRY_GAME_S, cooldown or RETRY_GAME_S)
        return self.game_t - slot.last_press >= wait

    def decide(self, now, rnd, in_round, lives_dropped=False):
        """Hotkey numbers to press now. Call update_towers() first."""
        if rnd is None:
            rnd = self._prev_round  # keep the last good reading (slots depend on it)
        in_round = self._advance(now, rnd, in_round)
        fired = []
        live = {}
        for key, name, use, cd, certain in self.hotkeys(rnd):
            slot = live[name] = self.slots.get(name) or _Slot(name)
            if use == "never":
                continue
            if lives_dropped:
                reason = "emergency"
            elif not in_round or use == "save":
                continue
            elif use == "on_cooldown":
                reason = "cooldown"
            elif use == "moab":
                if not is_moab_round(rnd, self.rules) or self.round_start is None \
                        or now - self.round_start < MOAB_DELAY_S:
                    continue
                reason = "moab round"
            else:
                continue
            if reason != "emergency" and not self._due(slot, cd):
                continue
            slot.last_press, slot.last_certain = self.game_t, certain
            fired.append((key, name, reason))
        self.slots = live
        self.last_fired = fired
        return [k for k, _, _ in fired]
