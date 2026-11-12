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
from functools import lru_cache

from . import threats as TH
from . import towers as T
from .account import round_xp
from .strategy import MODE_RULES, THREATS

log = logging.getLogger("abilities")

MAX_HOTKEY = 9                # ability hotkeys 1..9 (0/-/= exist but are not used)
RETRY_GAME_S = 20.0           # retry interval for unconfirmed presses (game seconds)
MOAB_DELAY_S = 3.0            # real seconds into a MOAB / crisis round before abilities fire
EMERGENCY_REPEAT_S = 2.0      # while lives fall: an ability maybe still cooling down is
                              # pressed again at most this often (real seconds)
MAX_DT_S = 10.0               # longest real gap counted toward cooldowns between calls
HERO_XP_OPTIMISM = 1.5        # "maybe unlocked": XP estimate x this
HERO_XP_PESSIMISM = 0.8       # "certainly unlocked": XP estimate x this

# Heavy rounds: the rounds whose MOAB-class HP (threats.round_blimp_load:
# every blimp layer, fortified x2, from data/rounds.json) is at least this
# share of the heaviest round the mode plays. 0.3 takes, in the standard
# set to round 100: R92 (50 fortified MOABs + 4 ZOMGs, 0.32 of R98), R94
# (25 BFBs + 6 ZOMGs, 0.54), R96 (30 BFBs + 40 fortified MOABs + 6 ZOMGs,
# 0.69; Chutes Impoppable was lost there) and R98 itself; R97 (0.23) and
# R100 (0.25) fall below it.
HEAVY_SHARE = 0.3
# Rounds picked by hand before HEAVY_SHARE, kept as a floor: their content is
# notable in ways blimp HP alone does not show (R63's ceramic rush, the
# first MOAB at R40 and BFB at R60, R100's BAD), and R99: 60 MOABs in 12 s
# with 9 fortified camo DDTs from 6.5 s - light in blimp HP (it falls under
# HEAVY_SHARE) but it ended three Spring Spring CHIMPS games (2026-11-07/08)
# and CHIMPS guides spend Bloon Sabotage on it (bloon.games, "Best
# strategies to beat CHIMPS mode": a 0-4-0 ninja for rounds 95 and 99).
HEAVY_FLOOR = frozenset({40, 60, 63, 76, 78, 80, 95, 98, 99, 100})


@lru_cache(maxsize=None)
def heavy_rounds(set_name="standard", end_round=100):
    """Heavy rounds of a round set up to end_round: HEAVY_FLOOR plus every
    round whose blimp HP is at least HEAVY_SHARE of the peak round's
    (rounds 1..end_round). Falls back to HEAVY_FLOOR without round data."""
    loads = {r: (TH.round_blimp_load(set_name, r) or {}).get("hp", 0.0) for r in range(1, end_round + 1)}
    peak = max(loads.values(), default=0.0)
    heavy = {r for r, hp in loads.items() if peak and hp >= HEAVY_SHARE * peak}
    return frozenset(heavy | {r for r in HEAVY_FLOOR if r <= end_round})


# The full standard set (Impoppable and CHIMPS play to round 100).
HEAVY_ROUNDS = heavy_rounds("standard", 100)


def _mode_of(rules):
    """The mode key whose strategy.MODE_RULES entry is `rules` (None if none)."""
    return next((m for m, r in MODE_RULES.items() if r is rules), None)


@lru_cache(maxsize=None)
def first_blimp_s(set_name, rnd):
    """Game seconds into round rnd before its first MOAB-class bloon spawns
    (the groups' start_s in the round data), or None for a round without
    blimps. Round 95 sends its 500 purples and 250 leads in 0-30 s and the
    50 fortified MOABs and 30 camo DDTs only from 30.8 s; round 98's ZOMGs
    come at 0 s."""
    starts = [float(g.get("start_s") or 0.0) for g in TH.round_groups(set_name, rnd)
              if (TH.bloons().get(g["bloon"]) or {}).get("class") == "blimp"]
    return min(starts) if starts else None


def heavy_rounds_for(rules):
    """Heavy rounds for a mode's rules (strategy.MODE_RULES entry): the
    mode's round set (ABR has its own) up to its last round."""
    mode = _mode_of(rules)
    end = (rules or {}).get("end_round") or 100
    return heavy_rounds(TH.set_for_mode(mode), end)

# XP needed per level for a 1.0x hero (Quincy): level L needs HERO_LEVEL_XP[L] in total.
_LEVEL_STEP = [180, 460, 1000, 1860, 3280, 5180, 8320, 9380, 13620, 16380,
               14400, 16650, 14940, 16380, 17820, 19260, 20700, 16470, 17280]
HERO_LEVEL_XP = [0, 0]
for _s in _LEVEL_STEP:
    HERO_LEVEL_XP.append(HERO_LEVEL_XP[-1] + _s)

# Levelling-cost scale per hero (higher = levels slower), the wiki's XP
# ratios (fandom:Heroes_(BTD6), "Hero Leveling"; docs/model_audit_support_
# heroes.md H-XP): 1.0 Quincy, Gwendolin, Striker, Obyn, Etienne, Geraldo;
# 1.425 Ezili, Pat, Brickell, Sauda, Corvus, Rosalia, Dan; 1.5 Benjamin,
# Psi, Silas; 1.71 Churchill, Adora. Corvus and Silas were swapped here.
HERO_XP_SCALE = {
    "quincy": 1.0, "gwendolin": 1.0, "striker_jones": 1.0, "obyn": 1.0,
    "etienne": 1.0, "geraldo": 1.0,
    "ezili": 1.425, "pat_fusty": 1.425, "admiral_brickell": 1.425, "sauda": 1.425,
    "rosalia": 1.425, "corvus": 1.425, "dan_dmonke": 1.425,
    "benjamin": 1.5, "psi": 1.5, "silas": 1.5,
    "churchill": 1.71, "adora": 1.71,
}

# Hero XP bonuses of Monkey Knowledge (fandom:Self_Taught_Heroes,
# fandom:Heroes_(BTD6)): together x1.2474, the figure the wiki's levelling
# table uses. Each counts only when the account owns it and the mode allows
# Monkey Knowledge (match.xp_knowledge: not in CHIMPS).
HERO_XP_KNOWLEDGE = {"Self Taught Heroes": 1.10, "Monkey Education": 1.08, "Monkeys Together Strong": 1.05}


def hero_xp_multiplier(map_name=None, knowledge=()):
    """The factor on the XP a hero earns per round: the map's difficulty
    (+10% per difficulty above Beginner, account.CATEGORY_XP_MULT) times the
    Monkey Knowledge bonuses in `knowledge` (HERO_XP_KNOWLEDGE). Before, the
    level estimate counted Monkey Education alone, so on an Expert map the
    bot thought its hero 1-3 levels lower than it was from round 60 on
    (docs/model_audit_support_heroes.md H-XP)."""
    from .account import CATEGORY_XP_MULT, MAPS, canonical_map
    mult = 1.0
    if map_name:
        name = str(map_name)
        if name.lower().endswith(" reverse"):
            name = name[:-len(" reverse")]
        try:
            name = canonical_map(name)
        except Exception:      # an unknown map name: no difficulty bonus
            pass
        mult *= CATEGORY_XP_MULT.get(MAPS.get(name), 1.0)
    for k in knowledge or ():
        mult *= HERO_XP_KNOWLEDGE.get(k, 1.0)
    return mult

# Activated tower abilities by upgrade name: (cooldown_s at 1x, use). The
# cooldowns are the game model's (attacks.json "abilities" of the upgrade's
# crosspath; tests/test_hero_rating_offline.py checks them).
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
    "Absolute Zero": (25, "on_cooldown"),
    "Glue Strike": (40, "on_cooldown"),
    "Glue Storm": (40, "on_cooldown"),
    "Supply Drop": (90, "on_cooldown"),
    "First Strike Capability": (60, "never"),      # click-targeted
    "Monkey Pirates": (45, "moab"),
    "Pirate Lord": (30, "moab"),
    "Ground Zero": (35, "on_cooldown"),
    "Tsar Bomba": (35, "on_cooldown"),
    "Support Chinook": (90, "on_cooldown"),
    "Special Poperations": (25, "never"),          # marine needs placing
    "Artillery Battery": (60, "on_cooldown"),
    "Pop and Awe": (60, "on_cooldown"),
    "Rocket Storm": (45, "on_cooldown"),
    "Summon Phoenix": (45, "on_cooldown"),
    "Tech Terror": (45, "on_cooldown"),
    "The Anti-Bloon": (30, "on_cooldown"),
    "Legend of the Night": (180, "on_cooldown"),
    "Bloon Sabotage": (60, "moab"),               # slows the whole wave: see ROUND_START
    "Grand Saboteur": (60, "moab"),
    "Transforming Tonic": (60, "on_cooldown"),
    "Total Transformation": (40, "on_cooldown"),
    "Jungle's Bounty": (30, "on_cooldown"),          # its Vine Crush
    "IMF Loan": (85, "never"),                      # takes on debt
    "Monkey-Nomics": (60, "on_cooldown"),
    "Spike Storm": (50, "on_cooldown"),
    "Carpet of Spikes": (50, "on_cooldown"),
    "Call to Arms": (45, "on_cooldown"),
    "Homeland Defense": (45, "on_cooldown"),
    "Overclock": (45, "never"),                     # needs a tower picked
    "Ultraboost": (35, "never"),
}

# 'moab' abilities that act on every bloon of the wave, including those still
# to spawn, rather than on a target on screen. They are pressed when the
# round's first blimp spawns (first_blimp_s), without MOAB_DELAY_S (R98's
# ZOMGs spawn within its first 5 game seconds), and only in heavy rounds
# (heavy_rounds_for), so their 60 s cooldown is not spent on a light round
# right before a heavy one. A crisis round waits for the blimps too; only a
# leak (lives falling) fires them at once.
# Why wait for the blimps: round 95 brings its 30 camo DDTs and 50 fortified
# MOABs from 30.8 game seconds, after 30 s of purples and leads. Pressed at
# the round's start, as before, the slow would be over (and the 60 s
# cooldown running) when the blimps came - the bloons Spring Spring CHIMPS
# lost to in rounds 95 and 99 (2026-11-07/08).
ROUND_START = {"Bloon Sabotage"}
BLIMP_LEAD_S = 1.0            # ROUND_START fires this many game seconds before the first blimp

# Abilities that, once pressed, wait for a click on a tower and then destroy
# it: Adora's Blood Sacrifice (level 7) turns the clicked tower into hero XP.
# The planner never presses them (they are 'never' in towers.HEROES), and
# while one may be on the board it presses NOTHING: the hotkey order is only
# assumed (see the module docstring), so a press meant for The Long Arm of
# Light could arm Blood Sacrifice instead, and the bot's next click on a
# tower - to upgrade it - would sacrifice it. Only a plan's own `do: ability`
# step (strategy.Executor._try_ability) presses one, and it then clicks the
# tower it means to destroy itself (Game.targeted_ability).
DESTRUCTIVE_ABILITIES = {"Blood Sacrifice"}


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
    return rnd is not None and (rnd in heavy_rounds_for(rules) or rnd >= moab_start_round(rules))


def is_heavy_round(rnd, rules=None):
    """A round heavy with blimps for this mode (see heavy_rounds)."""
    return rnd is not None and rnd in heavy_rounds_for(rules)


def is_slow_round(rnd, rules=None):
    """A round for a wave-wide slow (ROUND_START: Bloon Sabotage). On the
    standard round set only the hand-picked rounds of HEAVY_FLOOR, not every
    round over HEAVY_SHARE: rounds 92, 94, 95 and 96 are all heavy by blimp
    HP, and Spring Spring CHIMPS (2026-11-08 22:30) pressed the slow twice in
    round 94 and met round 95's 50 fortified MOABs and 30 camo DDTs without
    it. ABR and other sets keep heavy_rounds_for, which HEAVY_FLOOR does not
    describe."""
    if rnd is None:
        return False
    mode = _mode_of(rules)
    if TH.set_for_mode(mode) == "standard":
        end = (rules or {}).get("end_round") or 100
        return rnd in HEAVY_FLOOR and rnd <= end
    return is_heavy_round(rnd, rules)


# -- planner ------------------------------------------------------------------------

class _Slot:
    __slots__ = ("name", "last_press", "last_certain", "last_emergency")

    def __init__(self, name):
        self.name = name
        self.last_press = None      # game time of the last press
        self.last_certain = False   # was the ability certainly available then?
        self.last_emergency = None  # real time of the last emergency press while not due


class AbilityPlanner:
    def __init__(self, hero=None, rules=None, speed=2.0):
        self.hero = hero
        self.rules = rules or {}
        self.speed = speed
        self.hero_round = None          # round the hero was placed
        self.slots = {}                 # ability name -> _Slot (currently on the board)
        self._tower_seen = {}           # ability name -> (acquired round, game_t, seq)
        self._tower_count = {}          # ability name -> towers on the board that have it
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
        names = {}
        has_hero = False
        for p in towers:
            if p.kind == "hero":
                has_hero = True
                continue
            for n in tower_abilities(p.kind, p.tiers):
                names[n] = names.get(n, 0) + 1
        self._tower_count = names
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

    def destructive_possible(self, rnd):
        """Name of a DESTRUCTIVE_ABILITIES hero ability that may be unlocked
        now (optimistic level estimate), or None."""
        for _, name, _, _, _ in self._hero_abilities(rnd):
            plain = name.split(":", 1)[1]
            if plain in DESTRUCTIVE_ABILITIES:
                return plain
        return None

    def key_candidates(self, name, rnd):
        """Hotkeys to try, in order, for hero ability `name` (its plain name,
        e.g. "Blood Sacrifice"): the assumed slot first, then the other
        slots, nearest first, up to one past the last when the level
        estimate does not list the ability yet (the slot it gets when the
        estimate is behind the game). Slots whose assumed ability is another
        'never' one are left out: pressing those blind is what 'never'
        forbids. The caller checks each try on the screen
        (Game.targeted_ability), so a wrong guess costs one press of a
        harmless ability."""
        entries = self.hotkeys(rnd)
        want = "hero:" + name
        guess = next((k for k, n, _, _, _ in entries if n == want), None)
        last = len(entries) if guess is not None else len(entries) + 1
        if guess is None:
            guess = last
        unsafe = {k for k, n, use, _, _ in entries if use == "never" and n != want}
        keys = sorted(range(1, min(last, MAX_HOTKEY) + 1), key=lambda k: (abs(k - guess), k))
        return [k for k in keys if k not in unsafe]

    def hotkeys(self, rnd):
        """[(hotkey, name, use, cooldown, certain_now)] in assumed hotkey order."""
        entries = list(self._hero_abilities(rnd))
        for n, (r, t0, seq) in self._tower_seen.items():
            cd, use = TOWER_ABILITIES[n]
            # a fresh tower ability may start on cooldown: certain after one cooldown
            certain = self.game_t - t0 >= cd
            # Identical abilities share one button, and each press uses a tower
            # whose ability is ready: with k of them the button comes back k
            # times as often. Spring Spring CHIMPS (2026-11-08) buys two
            # Bloon Sabotage ninjas so the slow is there for round 95's
            # blimps (30.8 s in) after round 94's press, and for both 98 and 99.
            cd = cd / max(1, self._tower_count.get(n, 1))
            entries.append(((r, 1, seq), n, use, cd, certain))
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

    def _blimps_here(self, now, rnd):
        """Has the current round reached its first blimp spawn (less
        BLIMP_LEAD_S)? Game seconds into the round are the real seconds since
        it started times the game speed. A round without blimps, or one the
        round data does not know, counts from its start."""
        if self.round_start is None:
            return False
        first = first_blimp_s(TH.set_for_mode(_mode_of(self.rules)), rnd) if rnd is not None else None
        if not first:
            return True
        return (now - self.round_start) * self.speed >= first - BLIMP_LEAD_S

    def _due(self, slot, cooldown):
        if slot.last_press is None:
            return True
        if slot.last_certain and cooldown:
            wait = cooldown
        else:  # unconfirmed press: retry (a press on cooldown does nothing)
            wait = min(RETRY_GAME_S, cooldown or RETRY_GAME_S)
        return self.game_t - slot.last_press >= wait

    def decide(self, now, rnd, in_round, lives_dropped=False, crisis=False):
        """Hotkey numbers to press now. Call update_towers() first.

        lives_dropped: bloons are leaking right now - every ability that is
        not 'never' fires (an emergency).
        crisis: the damage model expects this round to leak (Match's round
        forecast) - every ability that is not 'never' fires a few seconds
        into the round, once bloons are on the track, instead of waiting
        for the first lives to go."""
        if rnd is None:
            rnd = self._prev_round  # keep the last good reading (slots depend on it)
        in_round = self._advance(now, rnd, in_round)
        crisis_now = (crisis and in_round and self.round_start is not None
                      and now - self.round_start >= MOAB_DELAY_S)
        blimps_here = self._blimps_here(now, rnd)
        fired = []
        live = {}
        guard = self.destructive_possible(rnd)
        if guard:
            # any key could be the one that arms it (DESTRUCTIVE_ABILITIES)
            if not getattr(self, "_guard_logged", False):
                self._guard_logged = True
                log.info("abilities: no hotkey presses from round %s on - %s may be unlocked "
                         "and a wrong guess of its key would arm it", rnd, guard)
            self.last_fired = []
            return []
        for key, name, use, cd, certain in self.hotkeys(rnd):
            slot = live[name] = self.slots.get(name) or _Slot(name)
            if use == "never":
                continue
            if lives_dropped:
                reason = "emergency"
            elif crisis_now and (name not in ROUND_START or blimps_here):
                reason = "crisis round"
            elif crisis_now:
                continue      # a wave-wide slow is kept for the round's blimps
            elif not in_round or use == "save":
                continue
            elif use == "on_cooldown":
                reason = "cooldown"
            elif use == "moab" and name in ROUND_START:
                if not is_slow_round(rnd, self.rules) or not blimps_here:
                    continue
                reason = "heavy round"
            elif use == "moab":
                if not is_moab_round(rnd, self.rules) or self.round_start is None \
                        or now - self.round_start < MOAB_DELAY_S:
                    continue
                reason = "moab round"
            else:
                continue
            due = self._due(slot, cd)
            if reason == "emergency" and not due:
                # It may be off cooldown already (the cooldowns are upper
                # bounds): press anyway, but not on every tick, and leave the
                # cooldown clock alone - a press that did nothing must not
                # push the next real use a whole cooldown later.
                if slot.last_emergency is not None and now - slot.last_emergency < EMERGENCY_REPEAT_S:
                    continue
                slot.last_emergency = now
                fired.append((key, name, reason))
                continue
            if not due:
                continue
            slot.last_press, slot.last_certain = self.game_t, certain
            fired.append((key, name, reason))
        self.slots = live
        self.last_fired = fired
        return [k for k, _, _ in fired]
