"""Persistent model of the BTD6 account the bot is playing on (v57).

Everything the planner needs to know about progress lives here and is
persisted to ``data/account.json`` with an atomic write:

* player level / XP, Monkey Money (MM), Monkey Knowledge (MK)
* unlocked towers, heroes and per-tower upgrade tiers + unspent tower XP
* medals per map and mode, per-map stats, observed MM rewards
* per (map, mode, strategy) win/loss stats used by the planner to learn
  which strategy actually works where.

Static game data that both this module and :mod:`btd6bot.planner` need
(maps, mode tree, level rewards, XP formulas) is also defined here so the
planner can import it without a circular dependency.

Facts marked ``UNVERIFIED`` could not be confirmed against a v57 source and
should be overwritten by values the bot observes on screen (the account has
override slots for categories, rewards and upgrade costs).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / "data" / "account.json"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Towers / heroes
# ---------------------------------------------------------------------------

TOWER_CATEGORIES: dict[str, list[str]] = {
    "primary": ["dart", "boomerang", "bomb", "tack", "ice", "glue", "desperado"],
    "military": ["sniper", "sub", "buccaneer", "ace", "heli", "mortar", "dartling"],
    "magic": ["wizard", "super", "ninja", "alchemist", "druid", "mermonkey", "skywarden"],
    "support": ["farm", "spike", "village", "engineer", "beast"],
}
TOWER_TO_CATEGORY: dict[str, str] = {
    t: cat for cat, towers in TOWER_CATEGORIES.items() for t in towers
}
# Not offered as level-up choices; unlocked from post-L30 gift boxes.
# UNVERIFIED: desperado's category and whether skywarden (v56, magic) is a
# gift-box tower or a level choice.
GIFT_BOX_TOWERS = frozenset({"dartling", "beast", "mermonkey", "desperado", "skywarden"})

STARTING_TOWERS = frozenset({"dart"})
STARTING_HEROES = frozenset({"quincy"})

# level -> tower category the player chooses a tower from
LEVEL_TOWER_CHOICE: dict[int, str] = {
    **{lvl: "primary" for lvl in (2, 3, 4, 5, 6)},
    **{lvl: "military" for lvl in (7, 8, 9, 10, 11, 12)},
    **{lvl: "magic" for lvl in (15, 16, 17, 19, 20)},
    **{lvl: "support" for lvl in (22, 23, 24, 26)},
}
LEVEL_HEROES: dict[int, str] = {1: "quincy", 14: "gwendolin", 21: "striker_jones", 28: "obyn"}
LEVEL_MM: dict[int, int] = {13: 50, 18: 50, 25: 50, 27: 50, 29: 50, 33: 200, 36: 200}
MK_UNLOCK_LEVEL = 30  # one MK point per level from here (UNVERIFIED whether L30 itself grants one)

# Cumulative XP needed to *reach* a level (research anchors, linear interpolation
# between them; above L50 extrapolated with the L40->50 per-level cost).
LEVEL_XP_ANCHORS: list[tuple[int, int]] = [
    (1, 0), (2, 480), (5, 3_350), (10, 19_850), (14, 38_000), (20, 96_000),
    (26, 189_000), (30, 274_000), (40, 799_000), (50, 1_829_000),
]


def xp_for_level(level: int) -> int:
    """Approximate cumulative XP needed to reach ``level``."""
    if level <= 1:
        return 0
    for (l0, x0), (l1, x1) in zip(LEVEL_XP_ANCHORS, LEVEL_XP_ANCHORS[1:]):
        if l0 <= level <= l1:
            return int(round(x0 + (x1 - x0) * (level - l0) / (l1 - l0)))
    l0, x0 = LEVEL_XP_ANCHORS[-2]
    l1, x1 = LEVEL_XP_ANCHORS[-1]
    per = (x1 - x0) / (l1 - l0)
    return int(round(x1 + per * (level - l1)))


def level_for_xp(xp: float) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
        if level > 1000:
            break
    return level


# ---------------------------------------------------------------------------
# XP formulas
# ---------------------------------------------------------------------------

def round_xp(r: int) -> int:
    if r <= 20:
        return 20 * r + 20
    if r <= 50:
        return 40 * (r - 20) + 420
    return 90 * (r - 50) + 1620


def rounds_xp(start: int, end: int) -> int:
    """Base XP for playing rounds start..end inclusive (no map multiplier)."""
    return sum(round_xp(r) for r in range(start, end + 1))


CATEGORY_XP_MULT = {"beginner": 1.0, "intermediate": 1.1, "advanced": 1.2, "expert": 1.3}
CATEGORIES = ("beginner", "intermediate", "advanced", "expert")
# Unique map wins needed to open a category.
CATEGORY_UNLOCK_WINS = {"beginner": 0, "intermediate": 5, "advanced": 12, "expert": 20}

# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModeInfo:
    key: str            # account/medal key
    difficulty: str     # difficulty button on the map screen: easy/medium/hard
    ui_mode: str        # mode button within the difficulty ("standard" for the base mode)
    group: str          # medal group: easy/medium/hard/chimps
    start_round: int
    end_round: int
    requires: str | None   # medal on the same map needed to unlock
    restriction: str | None  # tower category only (primary/military/magic)
    minutes: float      # rough bot runtime at fast-forward (planner default)
    reward_tier: str    # MM table row: easy/medium/hard/impoppable


MODES: dict[str, ModeInfo] = {m.key: m for m in [
    ModeInfo("easy", "easy", "standard", "easy", 1, 40, None, None, 9.0, "easy"),
    ModeInfo("primary_only", "easy", "primary_only", "easy", 1, 40, "easy", "primary", 9.0, "easy"),
    ModeInfo("deflation", "easy", "deflation", "easy", 31, 60, "primary_only", None, 5.5, "easy"),
    ModeInfo("medium", "medium", "standard", "medium", 1, 60, None, None, 15.0, "medium"),
    ModeInfo("military_only", "medium", "military_only", "medium", 1, 60, "medium", "military", 15.0, "medium"),
    ModeInfo("apopalypse", "medium", "apopalypse", "medium", 1, 60, "military_only", None, 12.0, "medium"),
    ModeInfo("reverse", "medium", "reverse", "medium", 1, 60, "medium", None, 15.0, "medium"),
    ModeInfo("hard", "hard", "standard", "hard", 3, 80, None, None, 27.0, "hard"),
    ModeInfo("magic_only", "hard", "magic_only", "hard", 3, 80, "hard", "magic", 27.0, "hard"),
    ModeInfo("double_hp", "hard", "double_hp", "hard", 3, 80, "magic_only", None, 29.0, "hard"),
    ModeInfo("half_cash", "hard", "half_cash", "hard", 3, 80, "double_hp", None, 28.0, "hard"),
    ModeInfo("abr", "hard", "abr", "hard", 3, 80, "hard", None, 27.0, "hard"),
    ModeInfo("impoppable", "hard", "impoppable", "hard", 6, 100, "abr", None, 36.0, "impoppable"),
    ModeInfo("chimps", "hard", "chimps", "chimps", 6, 100, "impoppable", None, 38.0, "impoppable"),
]}
MODE_KEYS = tuple(MODES)
# Things the bot must never plan (kept for explicit assertions / filtering).
EXCLUDED_MODES = frozenset({"boss", "elite_boss", "coop", "race", "odyssey",
                            "contested_territory", "daily_challenge", "sandbox"})


def mode_unlocks(mode: str) -> list[str]:
    """Modes whose prerequisite is ``mode``."""
    return [m.key for m in MODES.values() if m.requires == mode]


# ---------------------------------------------------------------------------
# Maps (v57). Display names are the canonical keys.
# ---------------------------------------------------------------------------

_BEGINNER = [
    "Monkey Meadow", "In The Loop", "Tree Stump", "Town Center", "Cubism",
    "Four Circles", "Hedge", "End Of The Road", "Logs", "Frozen Over",
    "Alpine Run", "Park Path", "Carved", "Winter Park", "Candy Falls",
    "Lotus Island", "Skates", "Resort", "The Cabin", "Scrapyard",
    "One Two Tree", "Middle of the Road", "Tinkerton", "Spa Pits",
    "Three Mines 'Round", "Skull Tweak",
]
_INTERMEDIATE = [
    "Lost Crevasse", "Luminous Cove", "Ancient Portal", "Sulfur Springs",
    "Water Park", "Polyphemus", "Covered Garden", "Quarry", "Quiet Street",
    "Bloonarius Prime", "Balance", "Encrypted", "Bazaar", "Adora's Temple",
    "Spring Spring", "KartsNDarts", "Moon Landing", "Haunted", "Downstream",
    "Firing Range", "Cracked", "Streambed", "Chutes", "Rake", "Spice Islands",
]
# UNVERIFIED: sources disagree whether Ship Capture (v57) is Intermediate or
# Advanced; the account's map_category_overrides fixes it once seen in-game.
_ADVANCED = [
    "Off The Coast", "Cornfield", "Underground", "High Finance", "Another Brick",
    "Peninsula", "Pat's Pond", "Cargo", "Spillway", "Geared", "Mesa", "X Factor",
    "Sunken Columns", "Midnight Mansion", "Erosion", "Dark Path", "Castle Revenge",
    "Last Resort", "Enchanted Glade", "Sunset Gulch", "Party Parade",
    "Mushroom Grotto", "Ascent", "Ship Capture",
]
_EXPERT = [
    "Muddy Puddles", "#Ouch", "Dark Castle", "Quad", "Workshop", "Bloody Puddles",
    "Infernal", "Flooded Valley", "Ravine", "Sanctuary", "Dark Dungeons",
    "Glacial Trail", "Tricky Tracks",
]
MAPS: dict[str, str] = {
    **{m: "beginner" for m in _BEGINNER},
    **{m: "intermediate" for m in _INTERMEDIATE},
    **{m: "advanced" for m in _ADVANCED},
    **{m: "expert" for m in _EXPERT},
}
# Not playable as normal single-player standard maps -> never planned.
EXCLUDED_MAPS = frozenset({"Protect The Yacht", "Blons"})


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


_MAP_BY_NORM = {_norm(m): m for m in list(MAPS) + list(EXCLUDED_MAPS)}
_MAP_BY_NORM.update({"ouch": "#Ouch", "kartsndarts": "KartsNDarts",
                     "threeminesround": "Three Mines 'Round"})


def canonical_map(name: str) -> str:
    """Map an OCR'd / loosely typed name onto the canonical display name."""
    if name in MAPS or name in EXCLUDED_MAPS:
        return name
    key = _norm(name)
    if key in _MAP_BY_NORM:
        return _MAP_BY_NORM[key]
    raise KeyError(f"unknown map {name!r}")


# ---------------------------------------------------------------------------
# Account state
# ---------------------------------------------------------------------------

def _stat_key(map_name: str, mode: str, strategy_id: str) -> str:
    return f"{map_name}|{mode}|{strategy_id}"


def split_stat_key(key: str) -> tuple[str, str, str]:
    a, b, c = key.split("|", 2)
    return a, b, c


@dataclass
class AccountState:
    player_level: int = 1
    xp: float | None = 0.0              # cumulative XP if known (None = unknown)
    monkey_money: int = 0
    unlocked_towers: set[str] = field(default_factory=lambda: set(STARTING_TOWERS))
    unlocked_heroes: set[str] = field(default_factory=lambda: set(STARTING_HEROES))
    tower_xp: dict[str, float] = field(default_factory=dict)       # unspent per tower
    unlocked_upgrades: dict[str, list[int]] = field(default_factory=dict)  # tower -> [p1,p2,p3]
    mk_points: int = 0                  # unspent
    mk_unlocked: list[str] = field(default_factory=list)
    medals: dict[str, dict[str, bool]] = field(default_factory=dict)
    map_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    strategy_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_tower_choices: list[str] = field(default_factory=list)  # categories awaiting a pick
    map_category_overrides: dict[str, str] = field(default_factory=dict)
    observed_upgrade_costs: dict[str, dict[str, int]] = field(default_factory=dict)  # tower -> "p-t" -> xp
    games_played: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    path: str | None = None             # where this state is persisted (not serialised)

    HISTORY_LIMIT = 500

    # ------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path: str | Path | None = None) -> "AccountState":
        p = Path(path) if path else DEFAULT_PATH
        if not p.exists():
            st = cls()
            st.path = str(p)
            return st
        with open(p, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        st = cls.from_dict(raw)
        st.path = str(p)
        return st

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AccountState":
        st = cls()
        st.player_level = int(raw.get("player_level", 1))
        st.xp = raw.get("xp", 0.0)
        st.monkey_money = int(raw.get("monkey_money", 0))
        st.unlocked_towers = set(raw.get("unlocked_towers", STARTING_TOWERS))
        st.unlocked_heroes = set(raw.get("unlocked_heroes", STARTING_HEROES))
        st.tower_xp = {k: float(v) for k, v in raw.get("tower_xp", {}).items()}
        st.unlocked_upgrades = {k: list(v) for k, v in raw.get("unlocked_upgrades", {}).items()}
        st.mk_points = int(raw.get("mk_points", 0))
        st.mk_unlocked = list(raw.get("mk_unlocked", []))
        st.medals = {k: dict(v) for k, v in raw.get("medals", {}).items()}
        st.map_stats = raw.get("map_stats", {})
        st.strategy_stats = raw.get("strategy_stats", {})
        st.pending_tower_choices = list(raw.get("pending_tower_choices", []))
        st.map_category_overrides = dict(raw.get("map_category_overrides", {}))
        st.observed_upgrade_costs = raw.get("observed_upgrade_costs", {})
        st.games_played = int(raw.get("games_played", 0))
        st.history = list(raw.get("history", []))
        return st

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "player_level": self.player_level,
            "xp": self.xp,
            "monkey_money": self.monkey_money,
            "unlocked_towers": sorted(self.unlocked_towers),
            "unlocked_heroes": sorted(self.unlocked_heroes),
            "tower_xp": self.tower_xp,
            "unlocked_upgrades": self.unlocked_upgrades,
            "mk_points": self.mk_points,
            "mk_unlocked": self.mk_unlocked,
            "medals": self.medals,
            "map_stats": self.map_stats,
            "strategy_stats": self.strategy_stats,
            "pending_tower_choices": self.pending_tower_choices,
            "map_category_overrides": self.map_category_overrides,
            "observed_upgrade_costs": self.observed_upgrade_costs,
            "games_played": self.games_played,
            "history": self.history[-self.HISTORY_LIMIT:],
        }

    def save(self, path: str | Path | None = None) -> Path:
        """Atomic write: temp file in the same dir, then os.replace (retried,
        because OneDrive/AV can briefly lock the target on Windows)."""
        p = Path(path or self.path or DEFAULT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.to_dict(), indent=1, sort_keys=False)
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            last_err: Exception | None = None
            for attempt in range(10):
                try:
                    os.replace(tmp, p)
                    last_err = None
                    break
                except PermissionError as e:  # pragma: no cover - timing dependent
                    last_err = e
                    time.sleep(0.1 * (attempt + 1))
            if last_err is not None:
                raise last_err
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self.path = str(p)
        return p

    # ------------------------------------------------------------ map queries
    def map_category(self, map_name: str) -> str:
        m = canonical_map(map_name)
        return self.map_category_overrides.get(m) or MAPS[m]

    def has_medal(self, map_name: str, mode: str) -> bool:
        return bool(self.medals.get(canonical_map(map_name), {}).get(mode))

    def unique_map_wins(self) -> int:
        return sum(1 for m, d in self.medals.items()
                   if m in MAPS and any(d.values()))

    def category_unlocked(self, category: str) -> bool:
        return self.unique_map_wins() >= CATEGORY_UNLOCK_WINS[category]

    def map_unlocked(self, map_name: str) -> bool:
        m = canonical_map(map_name)
        if m in EXCLUDED_MAPS:
            return False
        return self.category_unlocked(self.map_category(m))

    def mode_unlocked(self, map_name: str, mode: str) -> bool:
        if mode not in MODES or mode in EXCLUDED_MODES:
            return False
        if not self.map_unlocked(map_name):
            return False
        req = MODES[mode].requires
        return req is None or self.has_medal(map_name, req)

    def upgrades(self, tower: str) -> list[int]:
        return list(self.unlocked_upgrades.get(tower, [0, 0, 0]))

    # ---------------------------------------------------------- progression
    def apply_level(self, level: int) -> list[str]:
        """Advance to ``level`` and apply free rewards (heroes, MM milestones,
        MK points). Tower choices are *queued* in pending_tower_choices; the
        planner picks them. Returns event strings for logging."""
        events: list[str] = []
        old = self.player_level
        for lvl in range(old + 1, level + 1):
            if lvl in LEVEL_HEROES and LEVEL_HEROES[lvl] not in self.unlocked_heroes:
                self.unlocked_heroes.add(LEVEL_HEROES[lvl])
                events.append(f"L{lvl}: hero {LEVEL_HEROES[lvl]} unlocked")
            if lvl in LEVEL_MM:
                self.monkey_money += LEVEL_MM[lvl]
                events.append(f"L{lvl}: +{LEVEL_MM[lvl]} MM")
            if lvl in LEVEL_TOWER_CHOICE:
                cat = LEVEL_TOWER_CHOICE[lvl]
                self.pending_tower_choices.append(cat)
                events.append(f"L{lvl}: choose a {cat} tower")
            if lvl >= MK_UNLOCK_LEVEL:
                self.mk_points += 1
                events.append(f"L{lvl}: +1 MK point")
        if level > old:
            self.player_level = level
            if self.xp is not None and self.xp < xp_for_level(level):
                self.xp = float(xp_for_level(level))
        return events

    def sync_level(self, level: int) -> list[str]:
        """Use the on-screen level as ground truth (OCR)."""
        return self.apply_level(level) if level > self.player_level else []

    def unlock_tower(self, tower: str) -> None:
        self.unlocked_towers.add(tower)
        cat = TOWER_TO_CATEGORY.get(tower)
        if cat in self.pending_tower_choices:
            self.pending_tower_choices.remove(cat)

    def unlock_upgrade(self, tower: str, path: int, tier: int, cost: float | None = None) -> None:
        """path is 0..2, tier 1..5. Deducts tower XP when cost is given."""
        ups = self.upgrades(tower)
        ups[path] = max(ups[path], tier)
        self.unlocked_upgrades[tower] = ups
        if cost is not None:
            self.tower_xp[tower] = max(0.0, self.tower_xp.get(tower, 0.0) - cost)
            self.observed_upgrade_costs.setdefault(tower, {})[f"{path}-{tier}"] = int(cost)

    def note_locked(self, tower: str, path: int, tier: int) -> None:
        """In-game evidence that tier ``tier`` of path ``path`` (1..3) is still locked."""
        ups = self.upgrades(tower)
        ups[path - 1] = min(ups[path - 1], tier - 1)
        self.unlocked_upgrades[tower] = ups

    def note_bought(self, tower: str, path: int, tier: int) -> None:
        """Buying a tier in-game proves it is unlocked (path 1..3)."""
        self.unlock_upgrade(tower, path - 1, tier)

    def unlock_mk(self, name: str, mm_cost: int = 0) -> None:
        if name not in self.mk_unlocked:
            self.mk_unlocked.append(name)
            self.mk_points = max(0, self.mk_points - 1)
            self.monkey_money -= mm_cost

    def add_tower_xp(self, gains: dict[str, float]) -> None:
        for t, v in gains.items():
            self.tower_xp[t] = self.tower_xp.get(t, 0.0) + float(v)

    # --------------------------------------------------------------- results
    def strategy_record(self, map_name: str, mode: str, strategy_id: str) -> dict[str, Any]:
        return self.strategy_stats.get(_stat_key(canonical_map(map_name), mode, strategy_id),
                                       {"wins": 0, "losses": 0})

    def record_result(self, map_name: str, mode: str, strategy_id: str, won: bool,
                      round_reached: int | None = None, minutes: float | None = None,
                      xp_gained: float | None = None, mm_gained: int | None = None,
                      tower_xp_gained: dict[str, float] | None = None,
                      hero: str | None = None) -> list[str]:
        """Record a finished game. Returns event strings (level ups etc.)."""
        m = canonical_map(map_name)
        if mode not in MODES:
            raise ValueError(f"unknown/excluded mode {mode!r}")
        events: list[str] = []
        first_time = not self.has_medal(m, mode)
        self.games_played += 1

        # medals
        if won and first_time:
            self.medals.setdefault(m, {})[mode] = True
            events.append(f"medal {m}/{mode}")
            for nm in mode_unlocks(mode):
                events.append(f"unlocked mode {m}/{nm}")

        # map stats
        ms = self.map_stats.setdefault(m, {"wins": 0, "losses": 0, "best_round": 0,
                                           "avg_minutes": {}, "observed_rewards": {}})
        ms["wins" if won else "losses"] += 1
        if round_reached is not None:
            ms["best_round"] = max(ms.get("best_round", 0), int(round_reached))
        if minutes is not None and won:
            am = ms.setdefault("avg_minutes", {})
            prev = am.get(mode)
            am[mode] = round(minutes if prev is None else 0.7 * prev + 0.3 * minutes, 2)
        if mm_gained is not None and won:
            slot = "first" if first_time else "repeat"
            ms.setdefault("observed_rewards", {}).setdefault(mode, {})[slot] = int(mm_gained)

        # strategy stats
        key = _stat_key(m, mode, strategy_id)
        ss = self.strategy_stats.setdefault(key, {"wins": 0, "losses": 0, "games": 0,
                                                  "best_round": 0, "avg_minutes": None})
        ss["games"] = ss.get("games", 0) + 1
        ss["wins" if won else "losses"] += 1
        if round_reached is not None:
            ss["best_round"] = max(ss.get("best_round", 0), int(round_reached))
        if minutes is not None and won:
            prev = ss.get("avg_minutes")
            ss["avg_minutes"] = round(minutes if prev is None else 0.7 * prev + 0.3 * minutes, 2)

        # currencies
        if mm_gained:
            self.monkey_money += int(mm_gained)
        if tower_xp_gained:
            self.add_tower_xp(tower_xp_gained)
        if xp_gained and self.xp is not None:
            self.xp += float(xp_gained)
            new_level = level_for_xp(self.xp)
            if new_level > self.player_level:
                events += self.apply_level(new_level)

        self.history.append({
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "map": m, "mode": mode,
            "strategy": strategy_id, "hero": hero, "won": bool(won),
            "round": round_reached, "minutes": minutes, "xp": xp_gained, "mm": mm_gained,
        })
        if len(self.history) > self.HISTORY_LIMIT:
            del self.history[: len(self.history) - self.HISTORY_LIMIT]
        return events

    # ---------------------------------------------------------- convenience
    def iter_strategy_stats(self) -> Iterable[tuple[str, str, str, dict[str, Any]]]:
        for k, v in self.strategy_stats.items():
            m, mode, sid = split_stat_key(k)
            yield m, mode, sid, v

    def medal_count(self) -> int:
        return sum(1 for d in self.medals.values() for v in d.values() if v)

    def all_goals(self) -> list[tuple[str, str]]:
        return [(m, mode) for m in MAPS if m not in EXCLUDED_MAPS for mode in MODES]

    def remaining_goals(self) -> list[tuple[str, str]]:
        return [(m, mode) for m, mode in self.all_goals() if not self.has_medal(m, mode)]
