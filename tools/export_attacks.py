"""Export every tower's attack stats from the game's own model -> data/game_model/attacks.json.

Why
---
tools/decode_sim_model.py decodes the game's simulation model (sim_model,
224,031 objects) but only exported what towers *can* do (camo, lead, ...).
How *much* they do - damage, pierce, attack rate, what each projectile
spawns, how long it lives - stayed inside the model. btd6bot/dps_model.py
needs those numbers to estimate whether a defence pops a round, so this tool
writes them out, for every tower and every upgrade combination the game
builds, plus every hero level.

Where the numbers live in the model
-----------------------------------
The game keeps one finished TowerModel per tower *and* crosspath
("DartMonkey", "DartMonkey-200", "DartMonkey-024", ...): upgrades are not
stored as deltas, each combination is its own complete model. Under it:

    TowerModel.behaviors
      AttackModel / AttackAirUnitModel     one attack: range, targeting filters
        WeaponModel                        rate (seconds between shots),
                                           emission (how many projectiles a shot fires)
          ProjectileModel                  pierce, radius, filters (camo, MOAB, ...)
            DamageModel                    damage, immuneBloonProperties (damage type)
            DamageModifierForTagModel      extra damage vs a tag ("Moabs", "Ceramic")
            AddBehaviorToBloonModel        damage over time (DamageOverTimeModel), ...
            CreateProjectileOn...Model     sub-projectiles (a bomb's explosion, ...)
            CreateTowerModel               sub-towers (an Engineer's sentries)
      RateSupportModel, RangeSupportModel, ...   buffs to other towers (villages)
      PerRoundCashBonusTowerModel, BankModel ... income

Abilities (AbilityModel subtrees) are left out: the stats here are what a
tower does on its own, all the time.

Output
------
data/game_model/attacks.json:

    "source"    which bundle / sim_model hash it came from
    "frames_per_second"   the simulation tick, derived from the model
    "modes"     per difficulty / mode Mod asset: bloon speed multiplier,
                starting cash and lives, price multiplier, rounds, health mods
                (read from the game_data bundle, like difficulties.json)
    "towers"    {bot tower id: {"game_id", "crosspaths": {"000": TOWER, "200": ...}}}
    "heroes"    {bot hero id: {"game_id", "levels": {"1": TOWER, ...}}}

TOWER = {"range", "global", "attacks": [ATTACK], "subtowers": [...],
         "buffs": [...], "income": {...}, "zones": [...], "air_unit": {...}}
ATTACK = {"name", "range", "camo", "targets", "targeting", "weapons": [WEAPON]}
WEAPON = {"name", "rate", "count", "burst", "projectile": PROJECTILE, ...}
PROJECTILE = {"name", "pierce", "radius", "camo", "hits", "motion", "speed",
              "lifespan", "damage": {"amount", "immune", "type"},
              "bonus": {tag: {"mult", "add"}}, "dot": {...},
              "spawn": [{"on", "count", "projectile"}], "effects": {...},
              "other": [behaviour types not interpreted]}

Field meanings are documented next to the code that fills them below, and in
docs/optimizer.md. Every number is copied from the model; nothing is typed in.

Rules followed (the project's own): only copies of the game's files in
~/.btd6bot_cache are read, nothing of the game is modified, no game code or
DLL is run, no mods. The decoder's format derivation reads Cpp2IL's text
output, as described in docs/game_model.md.

Usage
-----
    python tools/export_attacks.py           # write data/game_model/attacks.json
    python tools/export_attacks.py --check   # print the headline numbers of the
                                             # base towers (no file written)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import decode_sim_model as dsm  # noqa: E402  (the decoder lives next to this tool)

log = logging.getLogger("export_attacks")

ROOT = TOOLS.parent
OUT_FILE = dsm.OUT_DIR / "attacks.json"
EXPORT_VERSION = 1

# Bloon properties (BloonProperties flags) that damage types are immune to,
# in the five names of normal play; "Immune"/"Glass" are event mechanics.
PROPERTY_NAMES = ("Lead", "Black", "White", "Purple", "Frozen")
# Community names of damage types (the decoder's table, plus "magic": what
# a Wizard's bolt cannot pop - lead and purple - and "plasma"-like sets).
DAMAGE_TYPE_NAMES = {**dsm.DAMAGE_TYPE_NAMES, frozenset({"Lead", "Purple"}): "magic",
                     frozenset({"Purple", "Frozen"}): "plasma"}

# Projectile behaviour types that only draw, sound or animate: never listed
# as "not interpreted". (dsm.COSMETIC covers most; these are the rest.)
QUIET_TYPES = ("DisplayModel", "ProjectileFilterModel", "ScaleProjectileModel",
               "HeightOffsetProjectileModel", "FadeProjectileModel", "SetSpriteFromPierceModel",
               "RotateModel", "ProjectileZeroRotationModel", "EndOfRoundClearBypassModel",
               "ExpireProjectileOnBossSpawnedModel", "DestroyProjectileIfTowerDestroyedModel",
               "CreateTextEffectModel", "ShowTextOnHitModel", "CantBeReflectedModel",
               "DontDestroyOnContinueModel", "WeaponRateAnimationSpeedModel",
               "CreateLightningEffectModel", "ChipMapBasedObjectModel")

# Recursion guard: sub-towers spawn projectiles that may spawn towers again.
MAX_DEPTH = 6


# ===========================================================================
# Reading the cached copies
# ===========================================================================

def cached_bundle(pattern, prefer=None):
    """A bundle copy in ~/.btd6bot_cache/bundles: the one named `prefer`
    (the bundle data/game_model was made from) if it is there, else the
    newest. Never looks into the game folder itself."""
    candidates = sorted(dsm.BUNDLE_CACHE.glob(pattern), key=lambda p: p.stat().st_mtime)
    if prefer:
        for c in candidates:
            if c.name == prefer:
                return c
    return candidates[-1] if candidates else None


def recorded_source():
    """data/game_model/source.json: which bundles towers.json came from."""
    try:
        return json.loads((dsm.OUT_DIR / "source.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_mode_rules(game_data_bundle, monoscripts):
    """{Mod name: rules} for every difficulty / mode Mod asset of the
    game_data bundle (the same assets decode_sim_model reads for prices).

    Each Mod lists mutators; the ones that matter for planning:
      GlobalSpeedModModel    bloon speed multiplier (Medium 1.1, Hard 1.25)
      StartingCashModModel   starting cash (changeBase) or a multiplier
      StartingHealthModModel lives
      GlobalCostModModel     price multiplier
      ModifyAllCashModModel  income multiplier (Half Cash 0.5, Deflation 0)
      BonusCashPerRoundModModel  end-of-round bonus: baseCash + round x roundMultiple
      StartingRoundModModel / EndRoundModModel   first and last round
      BloonHealthModel       health multiplier for a bloon tag (Double HP MOABs)
      SetHealthForBloonModModel  one round's bloon health change (Easy R40 MOAB)
      LockTowerModModel      towers that may not be built"""
    import UnityPy  # only needed here
    env = UnityPy.load(str(monoscripts), str(game_data_bundle))
    out = {}
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        mb = o.read()
        script = mb.m_Script.read() if mb.m_Script else None
        if script is None or script.m_ClassName != "Mod":
            continue
        tree = o.read_typetree()
        rules = {}
        for ref in (tree.get("references") or {}).get("RefIds") or []:
            cls, data = (ref.get("type") or {}).get("class"), ref.get("data") or {}
            if cls == "GlobalSpeedModModel":
                rules["speed_multiplier"] = dsm.short_float(data.get("multiplier", 1.0))
            elif cls == "StartingCashModModel":
                rules["starting_cash"] = {k: dsm.short_float(data.get(k, 0.0))
                                          for k in ("changeBase", "addition", "multiplier")}
            elif cls == "StartingHealthModModel":
                rules["lives"] = dsm.short_float(data.get("addition", 0.0))
            elif cls == "GlobalCostModModel":
                rules.setdefault("cost_multipliers", []).append(dsm.short_float(data["multiplier"]))
            elif cls == "ModifyAllCashModModel":
                rules["cash_multiplier"] = dsm.short_float(data.get("multiplier", 1.0))
            elif cls == "BonusCashPerRoundModModel":
                rules["round_bonus"] = {"base": dsm.short_float(data.get("baseCash", 0.0)),
                                        "per_round": dsm.short_float(data.get("roundMultiple", 0.0))}
            elif cls == "StartingRoundModModel":
                rules["start_round"] = data.get("round")
            elif cls == "EndRoundModModel":
                rules["end_round"] = data.get("round")
            elif cls == "BloonHealthModel":
                rules.setdefault("health_multipliers", {})[data.get("bloonTag") or "*"] = \
                    dsm.short_float(data.get("healthMod", 1.0))
            elif cls == "SetHealthForBloonModModel":
                rules.setdefault("round_health", []).append(
                    {"round": data.get("round"), "bloon": data.get("bloonId"),
                     "multiplier": dsm.short_float(data.get("healthMultiplier", 1.0))})
            elif cls == "LockTowerModModel":
                rules.setdefault("locked_towers", []).append(data.get("towerToLock"))
        out[tree["m_Name"]] = rules
    return dict(sorted(out.items()))


# ===========================================================================
# Small helpers over decoded objects
# ===========================================================================

def objs(x):
    """The model objects in x (an object, a list of them, or nothing)."""
    if isinstance(x, dsm.Obj):
        return [x]
    if isinstance(x, list):
        return [o for o in x if isinstance(o, dsm.Obj)]
    return []


def num(x, default=0.0):
    """x as a float, or default when it is not a number."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def clean(d):
    """Drop None / empty / False entries so the JSON stays short."""
    return {k: v for k, v in d.items() if v not in (None, [], {}, False, "")}


def short_name(obj):
    """'ProjectileModel_Explosion' -> 'Explosion', 'WeaponModel_Weapon' -> 'Weapon'."""
    name = obj.get("id") or obj.get("_name") or obj.type
    for prefix in ("ProjectileModel_", "WeaponModel_", "AttackModel_", "AttackAirUnitModel_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.strip("_") or obj.type


def frames_per_second(view_table):
    """The simulation tick, derived from the model: weapons that store a
    burst interval both in seconds and in frames (BurstWeaponBehaviorModel
    interval 0.1, intervalFrames 6) give frames per second."""
    ratios = Counter()
    for o in view_table:
        if isinstance(o, dsm.Obj) and o.type == "BurstWeaponBehaviorModel":
            seconds, frames = num(o.get("interval")), num(o.get("intervalFrames"))
            if seconds > 0 and frames > 0:
                ratios[round(frames / seconds)] += 1
    if not ratios:
        raise ValueError("no BurstWeaponBehaviorModel with both interval fields: cannot derive the tick")
    return ratios.most_common(1)[0][0]


# ===========================================================================
# The exporter
# ===========================================================================

class AttackExporter:
    """Turns TowerModels into the plain dicts described in the module docstring."""

    def __init__(self, view, fps):
        self.view = view
        self.fps = fps
        self.uninterpreted = Counter()     # behaviour types seen but not read (for the report)

    # -- filters -------------------------------------------------------------
    def bloon_filter(self, filters):
        """What a list of filters lets through, as a small dict:
        camo: False when camo bloons are filtered out;
        only_tags / excluded_tags: bloon tags required / refused
            (FilterWithTag(s)Model: inclusive False keeps only bloons WITH the
            tag(s), inclusive True removes them - checked against the game's
            own use: Sticky Bomb and MOAB Press only hit MOABs, Jungle's
            Bounty vines and Trance never MOABs);
        skips_frozen: frozen bloons are not hit (an Ice Monkey's blast)."""
        out = {"camo": not self.view.blocks_camo(filters), "only_tags": [], "excluded_tags": []}
        for f in objs(filters):
            t = f.type
            if t == "FilterOutTagModel" and f.get("tag"):
                out["excluded_tags"].append(f["tag"])
            elif t == "FilterOutBloonModel" and f.get("bloonId"):
                out["excluded_tags"].append(f["bloonId"])
            elif t == "FilterMoabModel":
                (out["excluded_tags"] if f.get("flip") else out["only_tags"]).append("Moabs")
            elif t in ("FilterWithTagModel", "FilterWithTagsModel"):
                tags = [f["tag"]] if f.get("tag") else list(f.get("tags") or [])
                (out["excluded_tags"] if f.get("inclusive") else out["only_tags"]).extend(tags)
            elif t == "FilterFrozenBloonsModel":
                out["skips_frozen"] = True
            elif t == "FilterAllModel":
                out["hits_nothing"] = True
            elif t == "FilterAllExceptTargetModel":
                out["target_only"] = True
        out["only_tags"] = sorted(set(out["only_tags"]))
        out["excluded_tags"] = sorted(set(out["excluded_tags"]))
        return out

    # -- damage ----------------------------------------------------------------
    def damage(self, dmg):
        """DamageModel (or DamageInRingRadiusModel) -> {amount, immune, type}.
        immune: the bloon properties this damage cannot pop (the game's only
        notion of a damage type); type: the community name for that set."""
        mask = int(dmg.get("immuneBloonProperties") or 0)
        immune = [n for n in self.view.flag_names(mask) if n in PROPERTY_NAMES]
        return clean({
            "amount": num(dmg.get("damage")),
            "max": num(dmg.get("maxDamage")) if num(dmg.get("maxDamage")) > 0 else None,
            "immune": [n.lower() for n in immune],
            "type": DAMAGE_TYPE_NAMES.get(frozenset(immune)) or "not " + "/".join(immune),
        })

    @staticmethod
    def add_bonus(bonus, key, mult, add):
        """Keep the strongest modifier per key (tags stack in the game only
        through different models; the export keeps one entry per key)."""
        b = bonus.setdefault(key, {"mult": 1.0, "add": 0.0})
        b["mult"] = max(b["mult"], num(mult, 1.0))
        b["add"] = max(b["add"], num(add))

    def bonuses(self, behaviors):
        """Extra damage against tags or bloon ids:
        DamageModifierForTagModel        tag(s) like "Moabs", "Ceramic", "Fortified", "Boss"
        DamageModifierForBloonTypeModel  bloon ids like "Ceramic" (with its children? includeChildren)
        Conditional ones (bloon states: frozen, glued, stunned) go to "conditional"."""
        bonus, conditional = {}, {}
        for b in objs(behaviors):
            if b.type == "DamageModifierForTagModel":
                for tag in ([b.get("tag")] if b.get("tag") else []) + list(b.get("tags") or []):
                    if tag and (num(b.get("damageMultiplier"), 1.0) != 1.0 or num(b.get("damageAddative"))):
                        self.add_bonus(bonus, tag.strip(), b.get("damageMultiplier"), b.get("damageAddative"))
            elif b.type == "DamageModifierForBloonTypeModel":
                for bid in ([b.get("bloonId")] if b.get("bloonId") else []) + list(b.get("bloonIds") or []):
                    if bid:
                        self.add_bonus(bonus, bid, b.get("damageMultiplier"), b.get("damageAdditive"))
            elif b.type in ("DamageModifierForBloonStateModel", "DamageModifierForBloonStateAndTypeModel"):
                for state in ([b.get("bloonState")] if b.get("bloonState") else []) + list(b.get("bloonStates") or []):
                    if state:
                        self.add_bonus(conditional, state, b.get("damageMultiplier"), b.get("damageAdditive"))
        return bonus, conditional

    def dot(self, add_behavior):
        """AddBehaviorToBloonModel carrying a DamageOverTimeModel: damage
        every `interval` seconds for `lifespan` seconds (burns, acid, bleed)."""
        for b in objs(add_behavior.get("behaviors")):
            if b.type == "DamageOverTimeModel" and num(b.get("damage")) > 0:
                flt = self.bloon_filter(objs(add_behavior.get("filter")) + objs(add_behavior.get("filters")))
                mask = int(b.get("immuneBloonProperties") or 0)
                return clean({
                    "amount": num(b.get("damage")),
                    "interval": num(b.get("interval"), 1.0),
                    "lifespan": num(add_behavior.get("lifespan")),
                    "immune": [n.lower() for n in self.view.flag_names(mask) if n in PROPERTY_NAMES],
                    "only_tags": flt["only_tags"],
                    "excluded_tags": flt["excluded_tags"],
                })
        return None

    # -- what a projectile does to bloons besides damage ------------------------
    def effects(self, behaviors):
        """Slows, freezes, knockback, blowback, camo/fortify/regrow removal,
        cash. Read for the evaluator's time-in-range and for reports."""
        out = {}
        for b in objs(behaviors):
            t = b.type
            if t in ("SlowModel", "SlowForBloonModel"):
                key = "stun" if num(b.get("multiplier"), 1.0) == 0.0 else "slow"
                out[key] = clean({"multiplier": num(b.get("multiplier"), 1.0), "lifespan": num(b.get("lifespan")),
                                  "layers": b.get("layers"), "only_tags": [b["bloonTag"]] if b.get("bloonTag") else None})
                flt = self.bloon_filter(objs(b.get("filters")))
                if flt["excluded_tags"]:
                    out[key]["excluded_tags"] = flt["excluded_tags"]
            elif t == "SlowModifierForTagModel" and b.get("tag"):
                out.setdefault("slow_modifier", {})[b["tag"]] = num(b.get("slowMultiplier"), 1.0)
            elif t == "FreezeModel":
                out["freeze"] = clean({"lifespan": num(b.get("lifespan")), "layers": b.get("layers"),
                                       "moabs": bool(b.get("canFreezeMoabs"))})
            elif t == "SlowMaimMoabModel":
                out["maim"] = {k: num(b.get(k)) for k in ("moabDuration", "bfbDuration", "zomgDuration",
                                                          "ddtDuration", "badDuration")}
            elif t == "KnockbackModel":
                out["knockback"] = {"lifespan": num(b.get("lifespan")), "moab": num(b.get("moabMultiplier"))}
            elif t == "WindModel":
                out["blowback"] = {"chance": num(b.get("chance")), "distance_min": num(b.get("distanceMin")),
                                   "distance_max": num(b.get("distanceMax")), "moabs": bool(b.get("affectMoab"))}
            elif t == "PushBackModel":
                out["pushback"] = {"amount": num(b.get("pushAmount")), "tag": b.get("tag")}
            elif t == "RemoveBloonModifiersModel":
                words = [w for w, k in (("camo", "cleanseCamo"), ("regrow", "cleanseRegen"),
                                        ("fortified", "cleanseFortified"), ("lead", "cleanseLead")) if b.get(k)]
                if words:
                    out["removes"] = sorted(set(out.get("removes", [])) | set(words))
            elif t == "CashModel":
                out["cash"] = {"min": num(b.get("minimum")), "max": num(b.get("maximum"))}
        return out

    # -- projectiles -------------------------------------------------------------
    def emission_count(self, emission):
        """Projectiles one emission fires: ArcEmissionModel.Count,
        RandomEmissionModel.count, EmissionWithOffsetsModel.projectileCount,
        ParallelEmissionModel.count, ...; 1 for single emissions."""
        for e in objs(emission):
            for key in ("Count", "count", "projectileCount"):
                v = num(e.get(key))
                if v > 0:
                    return v
        return 1.0

    def projectile(self, p, depth=0):
        """One ProjectileModel and everything it spawns (see the module
        docstring for the fields).

        motion / speed / lifespan: how it moves and how long it exists
            straight (TravelStraitModel: speed, lifespan), instant (InstantModel:
            hits where it appears), seeking (TrackTargetModel), arrive
            (ArriveAtTargetModel: flies to a point, e.g. spikes onto the track),
            path (FollowPathModel / TravelAlongPathModel: boomerangs, ...),
            static (only an AgeModel: lies where it was made);
        rehit_interval: ClearHitBloonsModel - may hit the same bloon again
            after this many seconds (otherwise once per bloon);
        pierce_refresh: RefreshPierceModel - pierce restored every interval;
        bounces: RetargetOnContactModel - jumps to a new target after a hit;
        extra_pierce_cost: CollideExtraPierceReductionModel - a hit on that
            tag uses up more pierce (e.g. {"": 1} = every hit costs one more);
        spawn: sub-projectiles, "on" = contact (per bloon hit), exhaust (when
            its pierce or life runs out), expire (when it ends), interval
            (every `every` seconds while alive), pierce (every `pierce_step`
            pierce used), lightning (chain jumps), multi (fired alongside);
        subtowers: towers it builds (CreateTowerModel: sentries, ...; with a
            "share" when the game picks one of several types per spawn)."""
        behaviors = objs(p.get("behaviors"))
        filters = self.view.projectile_filters(p)
        flt = self.bloon_filter(filters)
        out = {
            "name": short_name(p),
            "pierce": num(p.get("pierce")),
            "max_pierce": num(p.get("maxPierce")) if num(p.get("maxPierce")) > 0 else None,
            "radius": num(p.get("radius")),
            "camo": flt["camo"],
            "only_tags": flt["only_tags"],
            "excluded_tags": flt["excluded_tags"],
            "skips_frozen": flt.get("skips_frozen"),
            "hits_nothing": flt.get("hits_nothing"),
            "target_only": flt.get("target_only"),
        }
        motion, speed, lifespan = "static", 0.0, 0.0
        damage, spawns, subtowers, dot = None, [], [], None
        for b in behaviors:
            t = b.type
            if t == "DamageModel" or t == "DamageInRingRadiusModel":
                if damage is None or num(b.get("damage")) > damage.get("amount", 0):
                    damage = self.damage(b)
            elif t == "FreezeModel" and isinstance(b.get("damageModel"), dsm.Obj) and damage is None:
                damage = self.damage(b["damageModel"])
            elif t == "TravelStraitModel" or t == "TravelStraitSlowdownModel" or t == "RandomRangeTravelStraitModel":
                motion, speed = "straight", num(b.get("speed"))
                lifespan = max(lifespan, num(b.get("lifespan")))
            elif t == "InstantModel":
                motion = "instant"
            elif t in ("TrackTargetModel", "AdoraTrackTargetModel", "TrackTargetWithinTimeModel"):
                motion = "seeking"
            elif t == "ArriveAtTargetModel":
                motion = "arrive"
                out["arrive_time"] = num(b.get("timeToTake"))
            elif t in ("FollowPathModel", "TravelAlongPathModel", "TravelCurvyModel"):
                motion, speed = "path", num(b.get("speed"))
                lifespan = max(lifespan, num(b.get("lifespan")))
            elif t in ("AgeModel", "AgeRandomModel"):
                lifespan = max(lifespan, num(b.get("lifespan")))
                if int(b.get("rounds") or 0) > 1:
                    out["lasts_rounds"] = int(b["rounds"])
            elif t == "ClearHitBloonsModel":
                out["rehit_interval"] = num(b.get("interval"))
            elif t == "RefreshPierceModel":
                out["pierce_refresh"] = num(b.get("interval"))
            elif t == "RetargetOnContactModel":
                out["bounces"] = int(min(num(b.get("maxBounces")), 1e6))
            elif t == "CollideExtraPierceReductionModel":
                out.setdefault("extra_pierce_cost", {})[b.get("bloonTag") or ""] = num(b.get("extraAmount"))
            elif t == "AddBehaviorToBloonModel":
                dot = self.dot(b) or dot
            elif t in ("CreateProjectileOnContactModel", "CreateProjectileOnExhaustFractionModel",
                       "CreateDistanceProjectileOnExhaustFractionModel", "CreateProjectileOnExpireModel",
                       "CreateProjectileOnIntervalModel", "CreateProjectileOnExhaustPierceModel",
                       "CreateProjectileOnBlockerCollideModel", "EmitOnDamageModel", "EmitOnDamageWithStateModel"):
                spawn = self.spawn(b, depth)
                if spawn:
                    spawns.append(spawn)
            elif t == "LightningModel":
                spawns.append({"on": "lightning", "count": num(b.get("splits")),
                               "range": num(b.get("splitRange"))})
            elif t == "CreateTowerModel":
                if isinstance(b.get("tower"), dsm.Obj) and depth < MAX_DEPTH:
                    subtowers.append(self.tower(b["tower"], depth + 1))
            elif t == "CreateTypedTowerModel" and depth < MAX_DEPTH:
                # Sentry Expert: each spawn is one of several typed sentries
                # (crushing, boom, cold, energy); each gets an equal share
                typed = [v for k, v in b.items() if k.endswith("Tower") and isinstance(v, dsm.Obj)]
                for tower in typed:
                    subtowers.append({**self.tower(tower, depth + 1), "share": round(1.0 / len(typed), 4)})
            elif t.startswith(("DamageModifier", "BloonTagDamageOverride")) or t in (
                    "SlowModel", "SlowForBloonModel", "SlowModifierForTagModel", "FreezeModel",
                    "SlowMaimMoabModel", "KnockbackModel", "WindModel", "PushBackModel",
                    "RemoveBloonModifiersModel", "CashModel", "FreezeModifierForTagsModel"):
                pass   # read by bonuses() / effects() below
            elif not t.startswith(dsm.COSMETIC) and not any(c in t for c in dsm.COSMETIC) and t not in QUIET_TYPES:
                self.uninterpreted[t] += 1
                out.setdefault("other", []).append(t)
        bonus, conditional = self.bonuses(behaviors)
        out.update({
            "motion": motion,
            "speed": speed or None,
            "lifespan": lifespan or None,
            "damage": damage,
            "bonus": bonus,
            "conditional_bonus": conditional,
            "dot": dot,
            "effects": self.effects(behaviors),
            "spawn": spawns,
            "subtowers": subtowers,
        })
        if "other" in out:
            out["other"] = sorted(set(out["other"]))
        return clean(out)

    def spawn(self, b, depth):
        """One CreateProjectileOn...Model as {"on", "count", "projectile", ...}."""
        p = b.get("projectile")
        if not isinstance(p, dsm.Obj) or depth >= MAX_DEPTH:
            return None
        t = b.type
        entry = {"count": self.emission_count(b.get("emission")), "projectile": self.projectile(p, depth + 1)}
        if t in ("EmitOnDamageModel", "EmitOnDamageWithStateModel"):
            entry["on"] = "contact"          # emitted when it damages a bloon (Shrapnel Shot)
        elif t == "CreateProjectileOnContactModel":
            entry["on"] = "contact"
            if b.get("useChance"):
                entry["chance"] = num(b.get("chance"))
        elif t in ("CreateProjectileOnExhaustFractionModel", "CreateDistanceProjectileOnExhaustFractionModel"):
            entry["on"] = "exhaust"
        elif t == "CreateProjectileOnExpireModel":
            entry["on"] = "expire"
        elif t == "CreateProjectileOnIntervalModel":
            entry["on"] = "interval"
            entry["every"] = num(b.get("intervalFrames")) / self.fps
            if b.get("onlyIfHasTarget"):
                entry["needs_target"] = True
        elif t == "CreateProjectileOnExhaustPierceModel":
            entry["on"] = "pierce"
            entry["pierce_step"] = num(b.get("pierceInterval"), 1.0)
            entry["max_times"] = min(num(b.get("count"), 1.0), 1e6)
        else:
            entry["on"] = "blocker"
        return entry

    # -- weapons and attacks -------------------------------------------------------
    def weapon(self, w, depth=0):
        """WeaponModel: rate = seconds between shots (already including every
        upgrade of this crosspath); count = projectiles per shot; burst =
        shots fired per cycle (BurstWeaponBehaviorModel); per_round = a cap on
        shots per round (EmissionsPerRoundFilterModel: banana farms);
        alternate: every `every`-th shot fires another projectile;
        crit: every `every` shots one hit does `damage` instead;
        fires_weapon / triggered: FireAlternateWeaponModel makes this weapon
            fire weapon number `fires_weapon` of the same attack each time it
            fires, and FireWhenAlternateWeaponIsReadyModel marks a weapon that
            only fires when triggered that way (its own rate is just a
            readiness check: a Buccaneer's second dart, rate 0.05);
        max_subtowers: SubTowerFilterModel cap on sub-towers alive;
        projectile_limit: LimitProjectileModel cap on its projectiles alive;
        over_track_only: CheckAirUnitOverTrackModel - fires only while its
            aircraft is over the track."""
        out = {"name": short_name(w), "rate": num(w.get("rate")),
               "count": self.emission_count(w.get("emission"))}
        emission = w.get("emission")
        if isinstance(emission, dsm.Obj):
            if emission.type == "EmissionOverTimeModel":
                out["over_time"] = num(emission.get("timeBetween")) * out["count"]
            extra = emission.get("secondaryProjectileModel") or emission.get("projectileInitialHitModel")
            if isinstance(extra, dsm.Obj):
                out["extra_projectile"] = self.projectile(extra, depth + 1)
        for b in objs(w.get("behaviors")):
            if b.type in ("BurstWeaponBehaviorModel", "BurstWeaponIncreasingArcBehaviorModel"):
                out["burst"] = num(b.get("count"), 1.0)
            elif b.type == "EmissionsPerRoundFilterModel":
                out["per_round"] = num(b.get("count"))
            elif b.type == "AlternateProjectileModel" and isinstance(b.get("projectile"), dsm.Obj):
                out["alternate"] = {"every": num(b.get("interval"), 1.0),
                                    "count": self.emission_count(b.get("emissionModel")),
                                    "projectile": self.projectile(b["projectile"], depth + 1)}
            elif b.type == "CritMultiplierModel":
                out["crit"] = {"damage": num(b.get("damage")),
                               "every": (num(b.get("lower")) + num(b.get("upper"))) / 2 or 1.0}
            elif b.type == "WeaponRateMinModel":
                out["rate_min"] = num(b.get("min"))
            elif b.type == "FireAlternateWeaponModel":
                out["fires_weapon"] = int(num(b.get("weaponId")))
            elif b.type == "FireWhenAlternateWeaponIsReadyModel":
                out["triggered"] = True
            elif b.type == "SubTowerFilterModel":
                out["max_subtowers"] = num(b.get("maxNumberOfSubTowers"))
            elif b.type == "LimitProjectileModel":
                out["projectile_limit"] = num(b.get("limit"))
            elif b.type == "CheckAirUnitOverTrackModel":
                out["over_track_only"] = True
        p = w.get("projectile")
        out["projectile"] = self.projectile(p, depth) if isinstance(p, dsm.Obj) else None
        return clean(out)

    def attack(self, a, depth=0):
        """AttackModel / AttackAirUnitModel.
        camo: may target camo bloons (no active invisibility filter on the attack);
        targets: only_tags / excluded_tags of the attack's own filter;
        targeting: how it picks targets by default (the first match wins) -
            "normal" (it has first/last/close/strong modes, also their
            camo-priority and shared-range variants), "track" (onto the
            track: spike factories, caltrops), "cursor" (TargetPointerModel:
            follows the mouse - Dartling Gunner), "point" (only
            TargetSelectedPointModel: a hand-picked spot - Mortar Monkey),
            "random" (a random spot nearby: banana farms, sentries);
        air: fired from a plane / helicopter that moves (AttackAirUnitModel);
        pattern_radius: radius of the plane's flight pattern (Monkey Ace)."""
        behaviors = objs(a.get("behaviors"))
        attack_filters = [f for b in behaviors if self.view.is_a(b, "AttackFilterModel")
                          for f in objs(b.get("filters"))]
        flt = self.bloon_filter(attack_filters)
        suppliers = {b.type for b in behaviors + objs(a.get("targetProvider"))}
        # The default target mode decides: bloon targeting (first/last/close/
        # strong, also their camo-priority and shared-range variants) wins,
        # then "onto the track" modes, then the hand-aimed ones.
        if any(s.startswith("Target") and any(w in s for w in ("First", "Last", "Close", "Strong"))
               for s in suppliers):
            targeting = "normal"
        elif any("TargetTrack" in s or "TrackOrDefault" in s for s in suppliers):
            targeting = "track"
        elif any(s.startswith("TargetPointer") for s in suppliers):
            targeting = "cursor"
        elif "TargetSelectedPointModel" in suppliers:
            targeting = "point"
        elif any(s.startswith("RandomPosition") for s in suppliers):
            targeting = "random"
        else:
            targeting = "normal"
        patterns = [num(b.get("radius")) for b in behaviors if b.type in ("CirclePatternModel", "FigureEightPatternModel")]
        return clean({
            "name": short_name(a),
            "range": num(a.get("range")),
            "camo": flt["camo"],
            "only_tags": flt["only_tags"],
            "excluded_tags": flt["excluded_tags"],
            "targeting": targeting,
            "air": a.type == "AttackAirUnitModel" or None,
            "pattern_radius": min(patterns) if patterns else None,
            "through_walls": bool(a.get("attackThroughWalls")),
            "weapons": [self.weapon(w, depth) for w in objs(a.get("weapons"))],
        })

    # -- tower-level behaviours ----------------------------------------------------
    def buffs(self, behaviors):
        """Support models that change OTHER towers in range (villages,
        temples, ...): rate (multiplier on attack interval), range, pierce,
        damage, camo (VisibilitySupportModel: towers in range see camo),
        damage_type (DamageTypeSupportModel: MIB), discount (DiscountZoneModel)."""
        out = []
        for b in behaviors:
            t = b.type
            kind = {"RateSupportModel": "rate", "RangeSupportModel": "range", "PierceSupportModel": "pierce",
                    "PiercePercentageSupportModel": "pierce_percent", "DamageSupportModel": "damage",
                    "VisibilitySupportModel": "camo", "DamageTypeSupportModel": "damage_type",
                    "DiscountZoneModel": "discount", "ProjectileSpeedSupportModel": "projectile_speed",
                    "DamageModifierSupportModel": "damage_modifier"}.get(t)
            if kind is None or b.get("onlyAffectParagon"):
                continue
            value = None
            for key in ("multiplier", "pierce", "increase", "discountMultiplier", "percentIncrease"):
                if isinstance(b.get(key), (int, float)) and not isinstance(b.get(key), bool):
                    value = num(b[key])
                    break
            out.append(clean({
                "kind": kind, "value": value, "additive": num(b.get("additive")) or None,
                "global": bool(b.get("isGlobal") or b.get("isGlobalRange")),
                "radius": num(b.get("customRadius")) if b.get("isCustomRadius") else None,
                "towers": list(b.get("towerBaseIdList") or []) or None,
            }))
        return out

    def income(self, behaviors, attacks):
        """Cash a tower makes by itself: per_round from PerRoundCashBonusTowerModel
        (Monkey Bank deposits, Marketplace, ...), bank capacity/interest
        (BankModel), and banana cash = shots per round x bananas x value
        (CashModel inside the projectile of a weapon with a per-round cap)."""
        out = {}
        for b in behaviors:
            if b.type == "PerRoundCashBonusTowerModel":
                out["per_round"] = out.get("per_round", 0.0) + num(b.get("cashPerRound"))
            elif b.type == "BankModel":
                out["bank"] = {"capacity": num(b.get("capacity")), "interest": num(b.get("interest"))}
        bananas = 0.0
        for a in attacks:
            for w in a.get("weapons", []):
                cash = ((w.get("projectile") or {}).get("effects") or {}).get("cash")
                if cash and w.get("per_round"):
                    bananas += w["per_round"] * w.get("count", 1.0) * (cash["min"] + cash["max"]) / 2
        if bananas:
            out["bananas_per_round"] = bananas
        return out

    def zones(self, behaviors):
        """Area effects around the tower: SlowBloonsZoneModel (bloons in the
        zone move at speed x speedScale: Arctic Wind)."""
        out = []
        for b in behaviors:
            if b.type == "SlowBloonsZoneModel":
                flt = self.bloon_filter(objs(b.get("filters")))
                out.append(clean({"kind": "slow", "speed_scale": num(b.get("speedScale"), 1.0),
                                  "radius": num(b.get("zoneRadius")),
                                  "follows_range": bool(b.get("bindRadiusToTowerRange")),
                                  "excluded_tags": flt["excluded_tags"], "only_tags": flt["only_tags"]}))
        return out

    def tower(self, t, depth=0):
        """One TowerModel (a crosspath, a hero level or a sub-tower)."""
        behaviors = [b for b in objs(t.get("behaviors"))
                     if not any(c in b.type for c in dsm.COSMETIC) and not self.view.is_a(b, "AbilityModel")]
        attacks = [self.attack(b, depth) for b in behaviors if self.view.is_a(b, "AttackModel")]
        air = None
        for b in behaviors:
            if b.type == "AirUnitModel":
                for m in objs(b.get("behaviors")):
                    if m.type in ("PathMovementModel", "HeliMovementModel"):
                        air = {"movement": "pattern" if m.type == "PathMovementModel" else "follows",
                               "speed": num(m.get("speed") or m.get("maxSpeed"))}
        expire = next((b for b in behaviors if b.type == "TowerExpireModel"), None)
        ranges = [a["range"] for a in attacks if a.get("range")]
        return clean({
            "name": t.get("_name"),
            "range": num(t.get("range")),
            "global": bool(t.get("isGlobalRange")) or any(r >= 1000 for r in ranges),
            "attacks": attacks,
            "buffs": self.buffs(behaviors),
            "income": self.income(behaviors, attacks),
            "zones": self.zones(behaviors),
            "air_unit": air,
            "lifespan": (num(expire.get("lifespan")) if expire and num(expire.get("lifespan")) < 1e6 else None),
            "expires_on_round_end": bool(expire and expire.get("expireOnRoundComplete")),
        })


# ===========================================================================
# Putting it together
# ===========================================================================

def headline(entry):
    """The numbers people quote for a tower: of its first attack that does
    damage, the first weapon's rate and projectile count, and the damage and
    pierce of the first projectile in its tree that carries damage (a
    bomb's explosion, not the bomb). For validation and reports."""
    def first_damaging(p):
        if not p:
            return None
        if p.get("damage") and not p.get("hits_nothing"):
            return p
        for s in p.get("spawn", []):
            found = first_damaging(s.get("projectile"))
            if found:
                return found
        return None

    for a in entry.get("attacks", []):
        for w in a.get("weapons", []):
            p = first_damaging(w.get("projectile"))
            if p:
                return {"attack": a["name"], "range": a.get("range"), "rate": w["rate"],
                        "count": w.get("count", 1.0), "damage": p["damage"]["amount"],
                        "pierce": p.get("pierce"), "type": p["damage"].get("type"),
                        "camo": bool(a.get("camo") and p.get("camo"))}
    return None


def export(view, table, bot_towers, bot_heroes):
    """The attacks.json content (without "source" and "modes")."""
    ex = AttackExporter(view, frames_per_second(table))
    towers = {}
    for bot_id, info in bot_towers.items():
        gid = info["game_id"]
        crosspaths = {}
        for name, t in view.towers.items():
            if t.get("baseId") != gid or t.get("isParagon"):
                continue
            code = "000" if name == gid else name[len(gid) + 1:]
            if name != gid and not (name.startswith(gid + "-") and code.isdigit() and len(code) == 3):
                continue
            crosspaths[code] = ex.tower(t)
        towers[bot_id] = {"game_id": gid, "crosspaths": dict(sorted(crosspaths.items()))}
    heroes = {}
    hero_set = next(k for k, v in view.tower_sets.items() if v == "Hero")
    for bot_id, info in bot_heroes.items():
        gid = info["game_id"]
        levels = {str(t["tier"]): ex.tower(t) for t in view.towers.values()
                  if t.get("baseId") == gid and t.get("towerSet") == hero_set}
        heroes[bot_id] = {"game_id": gid, "levels": dict(sorted(levels.items(), key=lambda kv: int(kv[0])))}
    return {"frames_per_second": ex.fps, "towers": towers, "heroes": heroes}, ex.uninterpreted


def write(content):
    """Write attacks.json readably but compactly: the top levels indented,
    one line per crosspath / hero level (diffs stay readable per upgrade).
    Written to a temporary file first, then renamed, so a reader never sees
    half a file."""
    def line(obj):
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

    parts = ["{"]
    for key in ("source", "frames_per_second", "modes"):
        parts.append(f' "{key}": {json.dumps(content[key], indent=1, ensure_ascii=False)},')
    for group, inner in (("towers", "crosspaths"), ("heroes", "levels")):
        parts.append(f' "{group}": {{')
        items = list(content[group].items())
        for i, (bot_id, entry) in enumerate(items):
            parts.append(f'  "{bot_id}": {{"game_id": {line(entry["game_id"])}, "{inner}": {{')
            rows = list(entry[inner].items())
            for j, (code, tower) in enumerate(rows):
                parts.append(f'   "{code}": {line(tower)}' + ("," if j < len(rows) - 1 else ""))
            parts.append("  }}" + ("," if i < len(items) - 1 else ""))
        parts.append(" }" + ("," if group == "towers" else ""))
    parts.append("}")
    tmp = OUT_FILE.with_suffix(".json.tmp")
    tmp.write_text("\n".join(parts) + "\n", encoding="utf-8")
    tmp.replace(OUT_FILE)


def run(check_only=False):
    """Decode the cached sim_model, export, validate the shape, write."""
    t0 = time.time()
    src = recorded_source()
    model_bundle = cached_bundle("game_model_assets_all_*.bundle", src.get("bundle"))
    data_bundle = cached_bundle("game_data_assets_all_*.bundle", src.get("game_data_bundle"))
    mono = cached_bundle("*_monoscripts_*.bundle")
    if model_bundle is None:
        raise SystemExit("no cached game_model bundle in ~/.btd6bot_cache/bundles (run the decoder first)")
    data = dsm.read_sim_model(model_bundle)
    program = dsm.LoaderProgram()
    root, table = dsm.decode(data, program)
    view = dsm.ModelView(root, program)
    towers_json = json.loads((dsm.OUT_DIR / "towers.json").read_text(encoding="utf-8"))
    heroes_json = json.loads((dsm.OUT_DIR / "heroes.json").read_text(encoding="utf-8"))
    content, uninterpreted = export(view, table, towers_json, heroes_json)
    if check_only:
        for bot_id, entry in content["towers"].items():
            print(f"{bot_id:14s} {headline(entry['crosspaths'].get('000', {}))}")
        return content
    content["modes"] = read_mode_rules(data_bundle, mono) if data_bundle and mono else {}
    content["source"] = {
        "bundle": model_bundle.name,
        "game_data_bundle": data_bundle.name if data_bundle else None,
        "sim_model_sha1": hashlib.sha1(data).hexdigest(),
        "version": EXPORT_VERSION,
        "crosspaths": sum(len(t["crosspaths"]) for t in content["towers"].values()),
        "hero_levels": sum(len(h["levels"]) for h in content["heroes"].values()),
        "uninterpreted_behaviours": dict(uninterpreted.most_common()),
    }
    write(content)
    log.info("attacks.json: %d crosspaths, %d hero levels, %d behaviour types left uninterpreted (%.1f s)",
             content["source"]["crosspaths"], content["source"]["hero_levels"], len(uninterpreted),
             time.time() - t0)
    return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="print base-tower headline numbers, write nothing")
    run(check_only=ap.parse_args().check)
