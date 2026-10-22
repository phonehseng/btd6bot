"""Exact tower, upgrade, hero and bloon numbers from the game's own model.

tools/decode_sim_model.py decodes the game's simulation model (the
`sim_model` file inside the game_model bundle) into small JSON files under
data/game_model/. This module only *reads* those files; it is cheap to
import and never touches the game. docs/game_model.md explains the format.

    towers.json        per tower id (the bot's ids: "dart", "ninja", ...):
                       cost, footprint, range, placement, camo / lead / ...
                       popping at base, and the same facts for every
                       upgrade combination the game has ("crosspaths")
    upgrades.json      per tower: 3 paths x 5 tiers of name, cost, XP and
                       what the upgraded tower can do
    heroes.json        per hero id: cost, footprint, range, placement, MM price
    bloons.json        per game bloon id ("CeramicRegrowCamo"): speed,
                       health, children, RBE, immunities
    difficulties.json  the price multipliers of each difficulty and mode

Every function returns None (or an empty answer) when the data has not been
extracted on this machine, so callers can fall back to their own tables.
"""
import json
import logging
import math
import struct
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("gamemodel")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "game_model"
TOOL = ROOT / "tools" / "decode_sim_model.py"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _table(name):
    """One JSON file of data/game_model ({} when it is missing or broken)."""
    try:
        return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reload():
    """Forget the cached files (after a refresh wrote new ones)."""
    _table.cache_clear()
    _bloon_index.cache_clear()


def available():
    """True when the decoded tables exist."""
    return bool(_table("towers"))


def refresh(install=None):
    """Re-decode the game model if the game updated (see the tool). Returns
    True when new files were written. Meant for start-up, next to
    gamedata.refresh(); it never raises."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("decode_sim_model", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        changed = tool.refresh(install)
    except Exception as e:  # the bot must keep running whatever happens here
        log.warning("game model refresh failed: %s", e)
        return False
    if changed:
        reload()
    return changed


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def tower(tower_id):
    """The tower's entry in towers.json (bot id, e.g. "dart"), or None."""
    return _table("towers").get(tower_id)


def upgrade(tower_id, path, tier):
    """Upgrade on path 1-3, tier 1-5 of a tower, or None."""
    entry = _table("upgrades").get(tower_id)
    if not entry or not 1 <= path <= len(entry["paths"]):
        return None
    tiers = entry["paths"][path - 1]
    return tiers[tier - 1] if 1 <= tier <= len(tiers) else None


def hero(hero_id):
    """The hero's entry in heroes.json (bot id, e.g. "quincy"), or None."""
    return _table("heroes").get(hero_id)


@lru_cache(maxsize=1)
def _bloon_index():
    return {key.lower(): key for key in _table("bloons")}


def bloon(bloon_id, regrow=False, fortified=False, camo=False):
    """A bloon by its game id ("CeramicRegrowCamo", any case), or by base
    name plus modifiers: bloon("ceramic", camo=True). Modifiers go in the
    game's own order (Regrow, Fortified, Camo, as in the round files)."""
    name = str(bloon_id) + ("Regrow" if regrow else "") + ("Fortified" if fortified else "") + \
        ("Camo" if camo else "")
    key = _bloon_index().get(name.lower())
    return _table("bloons").get(key) if key else None


def entity(kind, hero_id=None):
    """Tower or hero entry the way placement code names things:
    entity("dart") or entity("hero", "quincy")."""
    return hero(hero_id) if kind == "hero" else tower(kind)


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def footprint_radius(kind, hero_id=None):
    """The game's radius for the tower (EntityModel.radius, world units).

    For the round towers this is their footprint circle. Ace, Heli Pilot,
    Banana Farm (and Rosalia) have rectangular footprints; their radius
    lies between the rectangle's inner and outer circle."""
    e = entity(kind, hero_id)
    return float(e["radius"]) if e and e.get("radius") else None


def surfaces(kind, hero_id=None):
    """{"land"}, {"water"} or both, from the tower's allowed area types."""
    e = entity(kind, hero_id)
    if not e:
        return None
    return {s for s in e.get("placement", []) if s in ("land", "water")} or None


# TowerModel.GetTowerSize compares the radius with three constants from the
# game's code (see docs/decompiling_notes.md): <= 6 small, 7 medium, 8 large.
SIZE_LIMITS = (6.0, 7.0, 8.0)


def size_class(radius):
    """The game's tower size class: 1 small, 2 medium, 3 large, 4 XL."""
    small, medium, large = SIZE_LIMITS
    if radius <= small:
        return 1
    if radius == medium:
        return 2
    if radius == large:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
#
# How the game prices things (read from its code, see docs/game_model.md):
#
# 1. A game is played with a difficulty Mod plus maybe a mode Mod (Impoppable
#    and CHIMPS are modes of Hard). Each GlobalCostModModel(m) in them adds
#    (m - 1) x the Medium price: a tower's float cost += (m - 1) * cost, an
#    upgrade's whole-number cost += (int)((m - 1) * cost), cut toward zero.
#    All arithmetic is 32-bit float.
# 2. When buying, the price (after discounts) goes through
#    Math.RoundToNearestInt(price, 5) = round(price / 5) * 5, where round()
#    is banker's rounding (exact halves go to the even number).

MODE_MODS = {   # bot difficulty / mode name -> the game's Mod assets applied
    "easy": ("Easy",), "medium": ("Medium",), "hard": ("Hard",),
    "impoppable": ("Hard", "Impoppable"), "chimps": ("Hard", "Clicks"),
}
# Used only when difficulties.json has not been extracted yet.
FALLBACK_MULTIPLIERS = {"easy": [0.85], "medium": [], "hard": [1.08],
                        "impoppable": [1.08, 1.12], "chimps": [1.08]}


def cost_multipliers(difficulty):
    """The GlobalCostModModel multipliers a difficulty applies, in order."""
    difficulty = difficulty.lower()
    mods = _table("difficulties")
    if difficulty in MODE_MODS and all(m in mods for m in MODE_MODS[difficulty]):
        return [x for m in MODE_MODS[difficulty] for x in mods[m]["cost_multipliers"]]
    return list(FALLBACK_MULTIPLIERS[difficulty])


def _f32(x):
    """x rounded to a 32-bit float, as the game's arithmetic does."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _bankers_round(x):
    """Round half to even (System.Math.Round / IL2CPP's bankers_round)."""
    low = math.floor(x)
    frac = x - low
    if frac != 0.5:
        return low + (1 if frac > 0.5 else 0)
    return low if low % 2 == 0 else low + 1


def round_to_5(value):
    """The game's Math.RoundToNearestInt(value, 5)."""
    return int(_f32(_bankers_round(_f32(_f32(value) / 5.0)) * 5.0))


def price(base_cost, difficulty="medium", kind="tower", discount=0.0):
    """What the game charges on `difficulty` for something whose Medium
    price is base_cost. kind: "tower" (towers and heroes) or "upgrade".
    discount: fraction off (village / Monkey Knowledge), applied before
    rounding as the game does."""
    mults = cost_multipliers(difficulty)
    if kind == "upgrade":
        cost = int(base_cost)
        for m in mults:   # cvttss2si: the change is cut toward zero
            cost += int(_f32(_f32(_f32(m) - 1.0) * _f32(base_cost)))
        cost = _f32(cost)
    else:
        start = cost = _f32(base_cost)
        for m in mults:
            cost = _f32(cost + _f32(_f32(_f32(m) - 1.0) * start))
    value = _f32(_f32(1.0 - discount) * cost)
    return round_to_5(value) if value > 0 else 0


def tower_price(tower_id, difficulty="medium"):
    t = tower(tower_id)
    return price(t["cost"], difficulty) if t else None


def upgrade_price(tower_id, path, tier, difficulty="medium"):
    u = upgrade(tower_id, path, tier)
    return price(u["cost"], difficulty, kind="upgrade") if u else None


def hero_price(hero_id, difficulty="medium"):
    h = hero(hero_id)
    return price(h["cost"], difficulty) if h else None


# ---------------------------------------------------------------------------
# What towers can do
# ---------------------------------------------------------------------------
#
# Capability words, per upgrade combination ("crosspaths" in towers.json):
#   camo        some attack targets camo bloons and its projectiles hit them
#               (the game's camo detection)
#   hits_camo   some damaging projectile can hit camo bloons, aimed or not
#               (spikes on the track pop camo bloons that run over them)
#   lead, black, white, purple, frozen
#               some damage can pop bloons with that property
#   decamo      strips camo off bloons for good (Shimmer, Signal Flare,
#               Counter-Espionage, Submerge and Support, Cleansing Foam)
#   gives_camo  lets other towers in range see camo (Radar Scanner)
#   gives_damage_type   lets other towers pop everything (MIB)
#   moab_bonus  extra damage against MOAB-class bloons
# Abilities are left out: they are not always on.

CAPABILITIES = ("camo", "hits_camo", "lead", "black", "white", "purple", "frozen",
                "decamo", "gives_camo", "gives_damage_type", "moab_bonus")


def _code(tiers):
    return "".join(str(int(t)) for t in tiers)


def can(tower_id, tiers, capability):
    """True/False: can this tower with these path tiers, e.g. (0, 2, 3), do
    it? None when unknown (no data, or a combination the game doesn't allow)."""
    t = tower(tower_id)
    words = (t or {}).get("crosspaths", {}).get(_code(tiers))
    return None if words is None else capability in words


def answers(capability, include_unavailable=False):
    """[(tower id, path, min tier)]: for every tower, the lowest tier of each
    path that has the capability on its own (a tower can appear once per
    path); (tower, 0, 0) alone when the base tower already has it. Same
    shape as strategy.ANSWERS."""
    out = []
    for tower_id, t in _table("towers").items():
        if not (t.get("available") or include_unavailable):
            continue
        cross = t.get("crosspaths", {})
        if capability in cross.get("000", []):
            out.append((tower_id, 0, 0))
            continue
        for path in (1, 2, 3):
            for tier in range(1, 6):
                tiers = [0, 0, 0]
                tiers[path - 1] = tier
                if capability in cross.get(_code(tiers), []):
                    out.append((tower_id, path, tier))
                    break
    return out


def immune(bloon_id):
    """The properties a bloon is immune to, e.g. ["lead"] or ["black", "white"]."""
    b = bloon(bloon_id)
    return list(b["immune"]) if b else None
