"""Map-independent strategies and the executor that plays them.

A strategy is a YAML build plan (strategies/*.yaml). Steps name *roles*, not
coordinates; the executor turns roles into spots using the learned map model:

  role: dps      maximise covered track (optionally within a progress segment)
  role: support  stand within reach of the towers listed in `near`
  role: exit     cover the last part of the track (spike factories, cleanup)
  role: far      away from the track (banana farms)

Plan steps run in order as cash allows. `fill` steps repeat afterwards to spend
surplus cash; `panic` runs whenever lives drop during a round.

Achievement strategies (strategies/achievements/**/*.yaml)
----------------------------------------------------------
load_all() also loads these. Each one carries `achievement: <name>` (always set,
also `source: "achievements"`), an optional `map:` and a `constraints:` block.
They are *not* general-purpose strategies:

  * usable() rejects every strategy with an `achievement` unless the caller
    passes allow_achievement=True - so a planner that does not know about
    achievements never picks them;
  * load_all() sets `bot_ready` (and `bot_ready_reasons`) on every strategy;
    bot_ready False means "never auto-play", and usable() always rejects it;
  * a strategy pinned to a `map:` also gets planner.maps = [map], and usable()
    rejects other maps when map_name is passed.

Constraints the executor enforces (see Executor / usable / hero_for):
  allowed_towers, forbidden_towers, land_only, no_income_towers, no_sell,
  max_towers_on_screen, max_towers_purchased (the hero counts as a tower for
  both caps), place_hero: false, hero_allowed: false, required_hero,
  allowed_heroes, forbidden_heroes, no_hero_fallback, no_default_panic,
  no_answers, min_difficulty, map; wins_needed is informational; no_powers and
  no_continues always hold (the bot never buys powers or continues).
Anything else (exact cash/lives, pop/damage budgets, MK off, map secrets,
event-only tower sets, plans that leak lives) makes the strategy bot_ready False.
"""
import logging
import math
import time
from pathlib import Path

import numpy as np
import yaml

from . import towers as T

log = logging.getLogger("strategy")
STRAT_DIR = Path(__file__).resolve().parents[1] / "strategies"
ACH_DIR = STRAT_DIR / "achievements"

MODE_FAMILY = {
    "easy": "easy", "primary_only": "easy", "deflation": "easy",
    "medium": "medium", "military_only": "medium", "apopalypse": "medium", "reverse": "medium",
    "hard": "hard", "magic_only": "hard", "double_hp": "hard", "half_cash": "hard", "abr": "hard",
    "impoppable": "impoppable", "chimps": "impoppable",
}
DIFFICULTY_ORDER = ["easy", "medium", "hard", "impoppable"]
MODE_TOWER_FILTER = {
    "primary_only": "primary", "military_only": "military", "magic_only": "magic",
}

# Rounds where a new kind of threat first shows up (standard rounds). The
# executor makes sure an answer is *already built* a couple of rounds earlier:
# DDTs in particular are too fast to answer after they appear.
THREATS = [
    (22, "camo"), (26, "lead"), (36, "ceramic"), (38, "moab"),
    (58, "bfb"), (62, "rush"), (78, "zomg"), (88, "ddt"), (98, "bad"),
]
# What counts as an answer: (tower, path, min tier) - any one is enough.
ANSWERS = {
    # only towers/tiers that really detect camo (Night Vision, Enhanced Eyesight,
    # Monkey Sense, Radar Scanner, Submerge and Support; ninjas and spikes innately)
    "camo": [("dart", 3, 2), ("sniper", 2, 2), ("ninja", 0, 0), ("wizard", 3, 2),
             ("sub", 1, 3), ("village", 2, 2), ("spike", 0, 0)],
    "lead": [("tack", 1, 3), ("bomb", 0, 0), ("boomerang", 3, 2), ("sniper", 1, 1), ("alchemist", 1, 1),
             ("wizard", 2, 1), ("mortar", 0, 0), ("dart", 1, 4), ("ninja", 3, 3), ("spike", 1, 2),
             ("super", 1, 2)],
    "ceramic": [("tack", 1, 3), ("boomerang", 1, 3), ("bomb", 2, 2), ("sniper", 1, 2), ("dart", 3, 3),
                ("heli", 1, 2), ("ninja", 1, 3), ("super", 0, 0), ("spike", 0, 0), ("druid", 1, 3)],
    "moab": [("bomb", 2, 3), ("boomerang", 1, 4), ("tack", 1, 4), ("sniper", 1, 3), ("heli", 1, 3),
             ("dart", 3, 4), ("ninja", 3, 3), ("super", 0, 0), ("spike", 3, 3), ("druid", 2, 4),
             ("wizard", 2, 4), ("ace", 0, 0), ("sub", 3, 3), ("buccaneer", 2, 4)],
    "bfb": [("bomb", 2, 4), ("sniper", 1, 4), ("heli", 1, 4), ("boomerang", 1, 4), ("dart", 3, 4),
            ("super", 1, 3), ("ninja", 3, 4), ("spike", 3, 4), ("druid", 2, 4), ("tack", 1, 4)],
    "rush": [("tack", 1, 4), ("bomb", 3, 3), ("ninja", 1, 4), ("super", 0, 0), ("wizard", 2, 3),
             ("dartling", 0, 0), ("boomerang", 1, 3), ("ice", 3, 3)],
    "zomg": [("bomb", 2, 4), ("sniper", 1, 4), ("super", 1, 3), ("heli", 1, 4), ("spike", 3, 4),
             ("boomerang", 1, 5), ("druid", 2, 4), ("ninja", 3, 4)],
    "ddt": [("sniper", 1, 4), ("bomb", 2, 4), ("heli", 1, 4), ("super", 1, 3), ("spike", 3, 4),
            ("ninja", 3, 4), ("boomerang", 1, 4), ("dart", 3, 4)],
    "bad": [("super", 1, 4), ("bomb", 2, 5), ("sniper", 1, 5), ("ninja", 3, 5), ("spike", 3, 5)],
}
# camo-requiring threats also need camo on the answering tower (or village MIB)
NEEDS_CAMO = {"ddt"}

# What each mode changes. Used by the executor (spending), match loop
# (starting rounds) and runner (map model key).
MODE_RULES = {
    "easy":          {"start_round": 1, "end_round": 40, "lives": 200},
    "primary_only":  {"start_round": 1, "end_round": 40, "lives": 200},
    "deflation":     {"start_round": 31, "end_round": 60, "lives": 200, "income": False,
                      "buy_all_upfront": True},
    "medium":        {"start_round": 1, "end_round": 60, "lives": 150},
    "military_only": {"start_round": 1, "end_round": 60, "lives": 150},
    "apopalypse":    {"start_round": 1, "end_round": 100, "lives": 150, "continuous": True},
    "reverse":       {"start_round": 1, "end_round": 60, "lives": 150, "reversed": True},
    "hard":          {"start_round": 3, "end_round": 80, "lives": 100},
    "magic_only":    {"start_round": 3, "end_round": 80, "lives": 100},
    "double_hp":     {"start_round": 3, "end_round": 80, "lives": 100, "tough_moabs": True},
    "half_cash":     {"start_round": 3, "end_round": 80, "lives": 100, "half_cash": True},
    "abr":           {"start_round": 3, "end_round": 80, "lives": 100,
                      "threat_shift": {"camo": 5, "lead": 10, "bfb": 54, "zomg": 79, "ddt": 88}},
    "impoppable":    {"start_round": 6, "end_round": 100, "lives": 1, "one_life": True},
    "chimps":        {"start_round": 6, "end_round": 100, "lives": 1, "one_life": True,
                      "no_sell": True, "no_income_towers": True, "no_mk": True, "no_powers": True},
}
INCOME_TOWERS = {"farm"}  # banana farms
# income upgrades (tower, path, tier): Merchantman buccaneers, Bloon Trap engineers
INCOME_UPGRADES = {("buccaneer", 3, 3), ("engineer", 3, 4)}

# Towers tried, in order, for the implicit panic step (when a strategy lists none).
PANIC_KINDS = ["tack", "dart", "sniper", "ninja", "wizard", "boomerang", "engineer", "spike"]

# -- achievement constraints ----------------------------------------------------------
# Constraint keys the bot enforces (or that always hold for this bot).
ENFORCED_CONSTRAINTS = {
    "allowed_towers", "forbidden_towers", "land_only", "no_income_towers", "no_sell",
    "max_towers_on_screen", "max_towers_purchased",
    "place_hero", "hero_allowed", "required_hero", "allowed_heroes", "forbidden_heroes",
    "no_hero_fallback", "no_default_panic", "no_answers", "min_difficulty", "wins_needed",
    "no_powers",      # the bot never buys or uses powers (menus.FORBIDDEN)
    "no_continues",   # the bot never continues (menus.leave_defeat)
}
# Constraint keys a screen bot cannot enforce -> bot_ready False (reason).
UNENFORCEABLE_CONSTRAINTS = {
    "one_tower_damage_min": "needs a per-tower damage meter",
    "other_towers_pop_budget": "needs per-tower pop counts (pop budget)",
    "min_spend_one_tower": "needs exact per-tower spend accounting",
    "keep_out_of_discount": "village-discount avoidance is not modelled by spot picking",
    "spend_exact": "needs an exact cash total",
    "mk": "Monkey Knowledge cannot be toggled by the bot",
    "map_secret": "needs a hand-calibrated map-secret click sequence",
    "no_removables": "removable-obstacle rule / precise hidden spots",
    "dynamic_tower_set": "tower set is read from an event screen at play time",
    "event_window_utc": "only playable inside an event window",
}
# Constraint keys that would break the owner's hard rules (never deliberately
# lose lives or games, never spend Monkey Money on continues).
SAFETY_CONSTRAINTS = {
    "end_lives_exact": "SAFETY: requires deliberately leaking lives",
    "lives_lost_exact": "SAFETY: requires deliberately leaking lives",
    "no_life_gain": "SAFETY: part of a deliberate-leak plan",
    "conflicts_with_rule": "SAFETY: conflicts with an owner rule",
    "requires_continue": "SAFETY: requires a Monkey Money continue",
    "leak_lives": "SAFETY: requires deliberately leaking lives",
}
SAFETY_ACHIEVEMENTS = {
    "livingontheedge": "SAFETY: needs deliberately leaked lives (end on exactly 1 life)",
    "illbeback": "SAFETY: needs a Monkey Money continue",
    "snapofyourfingers": "SAFETY: needs exactly 100 deliberately leaked lives",
}
STEP_KEYS = {"do", "id", "kind", "role", "segment", "near", "near_radius", "round", "max",
             "target", "to", "mode"}
UNSUPPORTED_STEP_KEYS = {
    "avoid": "spot avoidance (`avoid`) is not implemented by pick_spot",
    "avoid_radius": "spot avoidance (`avoid`) is not implemented by pick_spot",
    "note": "hand-calibrated placement notes (`note`) cannot be followed",
}
TARGET_MODES = {"first", "last", "close", "strong"}  # cycled by Game.target(); no point targets


def rules(mode):
    return MODE_RULES.get(mode, MODE_RULES["hard"])


def constraints(strat):
    return dict(strat.get("constraints") or {})


def _norm(s):
    return "".join(c for c in str(s).lower() if c.isalnum())


def parse_cross(s):
    return [int(c) for c in str(s).split("-")]


def legal_cross(t):
    """3 tiers 0..5, at most two paths used, at most one above tier 2."""
    return (len(t) == 3 and all(0 <= x <= 5 for x in t)
            and sum(x > 0 for x in t) <= 2 and sum(x > 2 for x in t) <= 1)


def _all_steps(strat):
    out = []
    for key in ("plan", "fill", "panic"):
        out += [(key, s) for s in (strat.get(key) or [])]
    for threat, steps in (strat.get("answers") or {}).items():
        out += [(f"answers.{threat}", s) for s in (steps or [])]
    return out


def validate(strat):
    """Structural problems of a strategy (unknown towers/heroes/modes, illegal
    crosspaths, dangling ids, steps that break its own constraints)."""
    probs = []
    c = constraints(strat)
    for m in strat.get("modes") or []:
        if m not in MODE_RULES:
            probs.append(f"unknown mode {m}")
    hero = strat.get("hero")
    if hero is not None and hero not in T.HEROES:
        probs.append(f"unknown hero {hero}")
    for k in ("required_hero",):
        if c.get(k) is not None and c[k] not in T.HEROES:
            probs.append(f"unknown hero {c[k]} in {k}")
    for k in ("allowed_heroes", "forbidden_heroes"):
        for h in c.get(k) or []:
            if h not in T.HEROES:
                probs.append(f"unknown hero {h} in {k}")
    if c.get("min_difficulty") is not None and c["min_difficulty"] not in DIFFICULTY_ORDER:
        probs.append(f"unknown min_difficulty {c['min_difficulty']}")
    for k in ("max_towers_on_screen", "max_towers_purchased"):
        if c.get(k) is not None and not (isinstance(c[k], int) and c[k] >= 1):
            probs.append(f"{k} must be a positive integer")
    for k in ("allowed_towers", "forbidden_towers"):
        for t in c.get(k) or []:
            if t not in T.TOWERS:
                probs.append(f"unknown tower {t} in {k}")
    # planner.towers is the per-path unlock requirement over all towers of a kind
    # (e.g. ninja 4-0-2 + 2-0-4 -> [4, 0, 4]), not one tower's crosspath
    for kind, tiers in ((strat.get("planner") or {}).get("towers") or {}).items():
        if kind not in T.TOWERS:
            probs.append(f"planner: unknown tower {kind}")
        elif len(list(tiers)) != 3 or not all(0 <= x <= 5 for x in tiers):
            probs.append(f"planner: bad tiers {kind} {tiers}")
    placed = {}
    for where, st in _all_steps(strat):
        if st.get("do") == "place" and st.get("id"):
            placed[st["id"]] = st.get("kind")
    merged = {}
    allowed = set(c["allowed_towers"]) if c.get("allowed_towers") is not None else None
    forbidden = set(c.get("forbidden_towers") or ())
    for where, st in _all_steps(strat):
        do = st.get("do")
        if do not in ("place", "upgrade", "target", "sell"):
            probs.append(f"{where}: unknown step {do!r}")
            continue
        kind = st.get("kind")
        if kind is not None and kind != "hero" and kind not in T.TOWERS:
            probs.append(f"{where}: unknown tower {kind}")
            continue
        if do == "place":
            if kind is None:
                probs.append(f"{where}: place without kind")
            elif kind != "hero" and ((allowed is not None and kind not in allowed) or kind in forbidden):
                probs.append(f"{where}: places {kind}, which its constraints forbid")
            elif kind == "hero" and (c.get("place_hero") is False or c.get("hero_allowed") is False):
                probs.append(f"{where}: places the hero although place_hero is false")
        if do == "upgrade":
            try:
                t = parse_cross(st["to"])
            except (KeyError, ValueError):
                probs.append(f"{where}: bad upgrade target {st.get('to')!r}")
                continue
            if not legal_cross(t):
                probs.append(f"{where}: illegal crosspath {st['to']}")
            if st.get("id"):
                if st["id"] not in placed:
                    probs.append(f"{where}: upgrade of {st['id']}, which is never placed")
                m = merged.setdefault(st["id"], [0, 0, 0])
                merged[st["id"]] = [max(a, b) for a, b in zip(m, t)]
        if do in ("target", "sell") and st.get("id") and st["id"] not in placed:
            probs.append(f"{where}: {do} of {st['id']}, which is never placed")
        for n in st.get("near") or []:
            if n not in placed:
                probs.append(f"{where}: near {n}, which is never placed")
    for tid, t in merged.items():
        if not legal_cross(t):
            probs.append(f"{tid}: upgrade targets combine to an illegal crosspath "
                         f"{'-'.join(map(str, t))}")
    return probs


def readiness(strat):
    """Reasons this strategy must not be auto-played (empty list: bot-ready)."""
    reasons = []
    c = constraints(strat)
    name = _norm(strat.get("achievement") or "")
    if name in SAFETY_ACHIEVEMENTS:
        reasons.append(SAFETY_ACHIEVEMENTS[name])
    for k, v in c.items():
        if k in SAFETY_CONSTRAINTS:
            reasons.append(f"{SAFETY_CONSTRAINTS[k]} ({k})")
        elif k == "mk":
            if _norm(v) in ("off", "false", "no", "disabled"):
                reasons.append(f"{UNENFORCEABLE_CONSTRAINTS['mk']} (mk: {v})")
        elif k == "bot_feasible":
            if _norm(v) in ("no", "false"):
                reasons.append("research marked it not bot-feasible")
        elif k in UNENFORCEABLE_CONSTRAINTS:
            reasons.append(f"{UNENFORCEABLE_CONSTRAINTS[k]} ({k})")
        elif k not in ENFORCED_CONSTRAINTS:
            reasons.append(f"unknown constraint {k}")
    for where, st in _all_steps(strat):
        for k in st:
            if k in UNSUPPORTED_STEP_KEYS:
                reasons.append(f"{UNSUPPORTED_STEP_KEYS[k]} [{where}]")
            elif k not in STEP_KEYS:
                reasons.append(f"unknown step key {k!r} [{where}]")
        for tm in (st.get("target"), st.get("mode") if st.get("do") == "target" else None):
            if tm is not None and str(tm).lower() not in TARGET_MODES:
                reasons.append(f"targeting {tm!r} needs a calibrated point [{where}]")
        if st.get("do") == "sell" and (c.get("no_sell") or "chimps" in (strat.get("modes") or [])):
            reasons.append(f"sells although selling is not allowed [{where}]")
    mp = strat.get("map")
    if mp:
        try:
            from .account import canonical_map
            canonical_map(mp)
        except KeyError:
            reasons.append(f"map {mp!r} is not a real map")
    if not [s for s in strat.get("plan") or [] if s.get("do") == "place"]:
        reasons.append("plan places no tower")
    reasons += validate(strat)
    if strat.get("bot_ready") is False and not reasons:
        reasons.append(strat.get("bot_ready_reason") or "marked bot_ready: false in YAML")
    # de-duplicate, keep order
    return list(dict.fromkeys(reasons))


def load_all():
    """All strategies by id: strategies/*.yaml plus strategies/achievements/**/*.yaml.

    Every strategy gets `bot_ready` (bool). Achievement strategies also get
    `source: "achievements"`, `bot_ready_reasons`, and planner.maps from `map:`.
    Ids stay unique: a later file with a used id is skipped (logged)."""
    out = {}
    for f in sorted(STRAT_DIR.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d.setdefault("id", f.stem)
        d.setdefault("bot_ready", True)
        out[d["id"]] = d
    if ACH_DIR.is_dir():
        for f in sorted(ACH_DIR.rglob("*.yaml")):
            try:
                d = yaml.safe_load(f.read_text(encoding="utf-8"))
            except Exception as e:  # one broken research file must not stop the bot
                log.error("achievement strategy %s does not parse: %s", f.name, e)
                continue
            if not isinstance(d, dict):
                log.error("achievement strategy %s is not a mapping", f.name)
                continue
            d.setdefault("id", f.stem)
            if d["id"] in out:
                log.error("duplicate strategy id %s in %s - skipped", d["id"], f)
                continue
            d.setdefault("achievement", f.stem)
            d["source"] = "achievements"
            try:
                reasons = readiness(d)
            except Exception as e:
                reasons = [f"validation failed: {e!r}"]
            d["bot_ready"] = not reasons
            d["bot_ready_reasons"] = reasons
            mp = d.get("map")
            if mp and d["bot_ready"]:
                p = dict(d.get("planner") or {})
                p.setdefault("maps", [mp])
                d["planner"] = p
            out[d["id"]] = d
    return out


def achievement_strategies(strats, cards=None):
    """Bot-ready achievement strategies whose achievement is still wanted.

    cards: achievements.Achievements.load() ({name: {status, ...}}); an achievement
    whose card says "complete" or "collect" is done. None: all bot-ready ones."""
    done = set()
    for name, card in (cards or {}).items():
        if (card or {}).get("status") in ("complete", "collect", "claimed"):
            done.add(_norm(name))
    return {sid: s for sid, s in strats.items()
            if s.get("achievement") and s.get("bot_ready") and _norm(s["achievement"]) not in done}


HERO_FALLBACK = ["obyn", "striker_jones", "gwendolin", "quincy"]


def _hero_fits(h, c):
    """Does hero h satisfy the constraints c (required/allowed/forbidden/land_only)?"""
    if h is None:
        return False
    if c.get("required_hero") and h != c["required_hero"]:
        return False
    if c.get("allowed_heroes") is not None and h not in c["allowed_heroes"]:
        return False
    if h in (c.get("forbidden_heroes") or ()):
        return False
    if c.get("land_only") and T.HEROES.get(h, {}).get("placement") == "water":
        return False
    return True


def hero_for(strat, account):
    """The hero to equip: the strategy's (or required) hero if owned, else the best
    owned fallback that its constraints allow. If no owned hero is allowed, an owned
    hero is still returned (one must be equipped) and the Executor never places it."""
    c = constraints(strat)
    want = c.get("required_hero") or strat.get("hero")
    if account is None:
        if want or not c:
            return want
        owned = None
    else:
        owned = account.unlocked_heroes
    have = (lambda h: True) if owned is None else (lambda h: h in owned)
    cands = [want] + list(c.get("allowed_heroes") or []) + HERO_FALLBACK
    for h in cands:
        if h and have(h) and _hero_fits(h, c):
            return h
    for h in [want] + HERO_FALLBACK:
        if h and have(h):
            return h
    return "quincy"


def usable(strat, mode, account, map_name=None, allow_achievement=False):
    """Can this account run this strategy in this mode (on this map)? Returns (ok, why).

    Achievement strategies are refused unless allow_achievement=True; strategies
    with bot_ready False are always refused."""
    if strat.get("bot_ready") is False:
        why = "; ".join(strat.get("bot_ready_reasons") or []) or "marked not bot-ready"
        return False, f"not bot-ready: {why}"
    if strat.get("achievement") and not allow_achievement:
        return False, "achievement strategy (not targeted)"
    if mode not in strat.get("modes", []):
        return False, "mode not supported"
    c = constraints(strat)
    if map_name is not None and strat.get("map"):
        from .account import canonical_map
        try:
            if canonical_map(map_name) != canonical_map(strat["map"]):
                return False, f"only for map {strat['map']}"
        except KeyError:
            return False, f"unknown map {map_name}"
    if c.get("min_difficulty"):
        fam = MODE_FAMILY.get(mode, "hard")
        if DIFFICULTY_ORDER.index(fam) < DIFFICULTY_ORDER.index(c["min_difficulty"]):
            return False, f"needs {c['min_difficulty']} or harder"
    cat = MODE_TOWER_FILTER.get(mode)
    allowed = set(c["allowed_towers"]) if c.get("allowed_towers") is not None else None
    forbidden = set(c.get("forbidden_towers") or ())
    # Core towers must be unlocked; optional ones (fill, backups, answers) are
    # simply skipped in-game when locked.
    core = set((strat.get("planner") or {}).get("towers") or {})
    if not core:
        core = {st["kind"] for st in strat.get("plan") or []
                if st.get("do") == "place" and st.get("kind") not in (None, "hero")}
    for k in core:
        if k not in T.TOWERS:
            return False, f"unknown tower {k}"
        if cat and T.TOWERS[k]["category"] != cat:
            return False, f"{k} not allowed in {mode}"
        if (allowed is not None and k not in allowed) or k in forbidden:
            return False, f"{k} breaks the strategy's own constraints"
        if c.get("land_only") and T.TOWERS[k].get("placement") == "water":
            return False, f"{k} is a water tower (land_only)"
        if account is not None and k not in account.unlocked_towers:
            return False, f"{k} locked"
    if (mode == "chimps" or c.get("no_income_towers")) and strat.get("uses_income"):
        return False, "income not allowed"
    # a locked preferred hero falls back to an owned one (see hero_for) - unless
    # the strategy needs exactly that hero
    need_hero = c.get("required_hero") or (strat.get("hero") if c.get("no_hero_fallback") else None)
    if need_hero and account is not None and need_hero not in account.unlocked_heroes:
        return False, f"hero {need_hero} not owned"
    for kind, need in (strat.get("requires_upgrades") or {}).items():
        have = account.unlocked_upgrades.get(kind, [0, 0, 0]) if account else [5, 5, 5]
        if any(h < n for h, n in zip(have, parse_cross(need))):
            return False, f"{kind} {need} not unlocked"
    return True, "ok"


class Executor:
    def __init__(self, game, model, strat, mode, account=None):
        self.g = game
        self.m = model
        self.strat = strat
        self.mode = mode
        self.account = account
        self.rules = rules(mode)
        c = self.c = constraints(strat)
        self.no_sell = bool(self.rules.get("no_sell") or c.get("no_sell"))
        self.no_income = bool(self.rules.get("no_income_towers") or c.get("no_income_towers"))
        self.no_answers = bool(c.get("no_answers"))
        self.allowed = set(c["allowed_towers"]) if c.get("allowed_towers") is not None else None
        self.forbidden = set(c.get("forbidden_towers") or ())
        self.land_only = bool(c.get("land_only"))
        self.max_on_screen = c.get("max_towers_on_screen")
        self.max_purchased = c.get("max_towers_purchased")
        self.purchased = len(game.towers)  # towers bought this game (hero included)
        self.hero_ok = self._hero_placeable()
        self._id_kind = {s.get("id"): s.get("kind") for _, s in _all_steps(strat)
                         if s.get("do") == "place" and s.get("id")}
        self.plan = [dict(s) for s in strat.get("plan") or [] if self._step_allowed(s)]
        self.fill = [dict(s) for s in strat.get("fill") or [] if self._step_allowed(s)]
        self.panic_steps = [dict(s) for s in strat.get("panic") or [] if self._step_allowed(s)]
        if not self.panic_steps and not c.get("no_default_panic"):
            k = self._best_panic_kind()
            if k:
                self.panic_steps = [{"do": "place", "kind": k, "role": "exit"}]
        self.idx = 0
        self.counter = {}
        self.capped = set()          # (tid, path) that turned out locked
        self.failed_spots = set()
        self.panic_pending = 0
        self.unanswerable = set()
        self.hold_fails = {}       # kind -> times the hotkey would not pick it up
        self.upgrade_fails = {}    # (tid, path) -> non-XP failures this game
        self.last_try = 0.0
        self.blocked = np.zeros(model.heat.shape, bool)  # this game's no-go cells
        for p in game.towers.values():
            cx, cy = model.frac_to_cell(p.x, p.y)
            self._block(cx, cy, 3)

    # -- constraints --------------------------------------------------------------
    def _hero_placeable(self):
        c = self.c
        if c.get("place_hero") is False or c.get("hero_allowed") is False:
            return False
        if not (c.get("required_hero") or c.get("allowed_heroes") is not None
                or c.get("forbidden_heroes") or c.get("land_only")):
            return True
        return _hero_fits(getattr(self.g, "hero", None), c)

    def kind_allowed(self, kind):
        """May a tower of this kind be placed at all in this game?"""
        if kind == "hero":
            return self.hero_ok
        if kind not in T.TOWERS:
            return False
        if self.allowed is not None and kind not in self.allowed:
            return False
        if kind in self.forbidden:
            return False
        if self.land_only and T.TOWERS[kind].get("placement") == "water":
            return False
        if self.no_income and kind in INCOME_TOWERS:
            return False
        only = MODE_TOWER_FILTER.get(self.mode)
        if only and T.TOWERS[kind]["category"] != only:
            return False
        return True

    def _is_income(self, kind, target):
        if kind in INCOME_TOWERS:
            return True
        return any(k == kind and target[path - 1] >= tier for k, path, tier in INCOME_UPGRADES)

    def _step_allowed(self, step):
        do = step.get("do")
        if do == "place":
            return self.kind_allowed(step.get("kind"))
        if do == "upgrade" and self.no_income:
            kind = step.get("kind") or self._id_kind.get(step.get("id"))
            try:
                return not (kind and self._is_income(kind, parse_cross(step["to"])))
            except (KeyError, ValueError):
                return False
        if do == "sell":
            return not self.no_sell
        return True

    def at_tower_cap(self):
        if self.max_on_screen is not None and len(self.g.towers) >= self.max_on_screen:
            return True
        if self.max_purchased is not None and self.purchased >= self.max_purchased:
            return True
        return False

    # -- helpers ------------------------------------------------------------
    def _learn_blocked(self, kind, cx, cy):
        """The game refused this spot although the saved scan said it was fine:
        correct the map's scan so later games (any mode) never try it again."""
        if kind == "hero":
            cls = T.HEROES.get(self.g.hero, {}).get("placement") or "land"
        else:
            cls = T.TOWERS.get(kind, {}).get("placement") or "land"
        grid = self.m.scan.get(cls) if cls in ("land", "water") else None
        if grid is not None:
            h, w = grid.shape
            grid[max(0, cy - 1):min(h, cy + 2), max(0, cx - 1):min(w, cx + 2)] = 2
            log.info("learned: %s spot (%d,%d) is not placeable on this map", cls, cx, cy)

    def _block(self, cx, cy, r):
        h, w = self.blocked.shape
        self.blocked[max(0, cy - r):min(h, cy + r + 1), max(0, cx - r):min(w, cx + r + 1)] = True

    def _best_panic_kind(self):
        """Cheapest sensible panic tower that this game's rules and constraints allow
        (None if there is none)."""
        for k in PANIC_KINDS:
            if not self.kind_allowed(k):
                continue
            if self.account is None or k in self.account.unlocked_towers:
                return k
        if self.kind_allowed("dart"):
            return "dart"  # always unlocked
        return None

    def _new_tid(self, kind):
        self.counter[kind] = self.counter.get(kind, 0) + 1
        return f"{kind}{self.counter[kind]}"

    def _range_cells(self, kind):
        if kind == "hero":
            rng = T.HEROES.get(self.g.hero, {}).get("range") or 40
        else:
            rng = T.TOWERS[kind].get("range") or 400
        return self.m.radius_cells(rng, self.g.s.width)

    def _occupied(self):
        out = []
        for p in self.g.towers.values():
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            out.append((cx, cy, 3))  # footprints: ~3 cells radius each
        return out

    def pick_spot(self, kind, step):
        role = step.get("role", "dps")
        if kind == "hero":
            placement = T.HEROES.get(self.g.hero, {}).get("placement") or "land"
        else:
            placement = T.TOWERS[kind].get("placement") or "land"
        if self.land_only and placement == "land_or_water":
            placement = "land"
        rc = min(self._range_cells(kind), 60)
        seg = tuple(step.get("segment", (0.0, 1.0)))
        near, near_r = None, None
        if role == "exit":
            seg = (0.65, 1.0)
        if role == "support" and step.get("near"):
            ids = [i for i in step["near"] if i in self.g.towers]
            if ids:
                xs = [self.g.towers[i].x for i in ids]
                ys = [self.g.towers[i].y for i in ids]
                near = self.m.frac_to_cell(sum(xs) / len(xs), sum(ys) / len(ys))
                near_r = step.get("near_radius", 9)
        if role == "far":
            cover = -self.m.score_spots(rc, seg, self._occupied(), placement=placement,
                                        extra_block=self.blocked)
            cover[cover >= 1] = -1  # still exclude blocked/occupied
        else:
            cover = self.m.score_spots(rc, seg, self._occupied(), near=near, near_radius=near_r,
                                       placement=placement, extra_block=self.blocked)
        for cx, cy, score in self.m.best_spots(cover, n=12):
            if (kind, cx, cy) in self.failed_spots:
                continue
            return (cx, cy, score)
        return None

    def _next_path(self, p, target):
        """Cheapest next tier that moves p toward target crosspath."""
        if any(c > t for c, t in zip(p.tiers, target)):
            return None  # tower already went another way; target unreachable
        best = None
        for i in range(3):
            if p.tiers[i] >= target[i] or (p.tid, i + 1) in self.capped:
                continue
            tier = p.tiers[i] + 1
            cost = (T.upgrade_cost(p.kind, i + 1, tier, MODE_FAMILY[self.mode])
                    if p.kind != "hero" else 0)
            if best is None or cost < best[1]:
                best = (i + 1, cost)
        return best

    # -- step execution ---------------------------------------------------------
    def _resolve_targets(self, step):
        if "id" in step and step["id"] in self.g.towers:
            return [self.g.towers[step["id"]]]
        if "kind" in step:
            return [p for p in self.g.towers.values() if p.kind == step["kind"]]
        return []

    def try_step(self, step, cash, rnd):
        """Returns 'done', 'wait' or 'skip'."""
        if rnd is not None and step.get("round") and rnd < step["round"]:
            return "wait"
        do = step["do"]
        if do == "place":
            kind = step["kind"]
            if self.account and kind != "hero" and kind not in self.account.unlocked_towers:
                return "skip"
            if kind == "hero" and any(p.kind == "hero" for p in self.g.towers.values()):
                return "done"
            if step.get("id") and step["id"] in self.g.towers:
                return "done"
            # the one gate every placement passes (plan, fill, panic, answers)
            if not self.kind_allowed(kind):
                return "skip"
            if self.at_tower_cap():
                return "skip"
            if "max" in step and sum(p.kind == kind for p in self.g.towers.values()) >= step["max"]:
                return "skip"
            price = self.g.price(kind)
            if cash is None or cash < price:
                return "wait"
            if self.hold_fails.get(kind, 0) >= 3:
                return "skip"  # cannot pick it up (locked / mode-restricted / unbound)
            spot = self.pick_spot(kind, step)
            if spot is None:
                return "skip"
            cx, cy, _ = spot
            fx, fy = self.m.cell_to_frac(cx, cy)
            tid = step.get("id") or self._new_tid(kind)
            if self.g.place(tid, kind, fx, fy):
                self.purchased += 1
                self._block(cx, cy, 3)
                if step.get("target"):
                    self.g.target(self.g.towers[tid], step["target"])
                return "bought"
            reason = self.g.fail_reason
            if reason == "hold":
                self.hold_fails[kind] = self.hold_fails.get(kind, 0) + 1
            elif reason in ("spot", "click"):
                # only blame the spot when the spot was the problem
                self.failed_spots.add((kind, cx, cy))
                self._block(cx, cy, 2)
                self._learn_blocked(kind, cx, cy)
            return "wait"
        if do == "upgrade":
            target = parse_cross(step["to"])
            targets = self._resolve_targets(step)
            if self.no_income:
                targets = [p for p in targets if not self._is_income(p.kind, target)]
            for p in targets:
                nxt = self._next_path(p, target)
                if nxt is None:
                    continue
                path, cost = nxt
                if cash is None or cash < cost:
                    return "wait"
                if self.g.upgrade(p, path):
                    if self.account and p.kind != "hero":
                        self.account.note_bought(p.kind, path, p.tiers[path - 1])
                    return "progress" if self._next_path(p, target) else "bought"
                reason = self.g.fail_reason
                if reason == "xp":
                    # locked behind tower XP we do not have (yet)
                    self.capped.add((p.tid, path))
                    if self.account and self.g.locked_seen:
                        self.account.note_locked(*self.g.locked_seen)
                else:
                    self.upgrade_fails[(p.tid, path)] = self.upgrade_fails.get((p.tid, path), 0) + 1
                    if self.upgrade_fails[(p.tid, path)] >= 4:
                        self.capped.add((p.tid, path))  # give up on it this game only
                return "wait"
            reached = [p for p in targets if all(c >= t for c, t in zip(p.tiers, target))]
            return "done" if reached else "skip"
        if do == "target":
            for p in self._resolve_targets(step):
                self.g.target(p, step["mode"])
            return "done"
        if do == "sell":
            if self.no_sell:
                return "skip"
            for p in self._resolve_targets(step):
                self.g.sell(p)
            return "bought"
        return "skip"

    # -- threat calendar ---------------------------------------------------------
    def has_answer(self, threat):
        if threat in NEEDS_CAMO and not self.has_answer("camo"):
            return False  # DDTs are camo: the blimp popper must be able to see them
        for p in self.g.towers.values():
            if p.kind == "hero":
                continue
            for kind, path, tier in ANSWERS.get(threat, []):
                if p.kind == kind and (path == 0 or p.tiers[path - 1] >= tier):
                    return True
        return False

    def due_threat(self, rnd, lookahead=3):
        """First upcoming threat with no answer built yet."""
        if rnd is None or self.no_answers:
            return None
        start = self.rules.get("start_round", 1)
        if self.rules.get("one_life"):
            lookahead = max(lookahead, 6)  # one leak = defeat: build answers early
        shift = self.rules.get("threat_shift", {})
        for r, threat in sorted((shift.get(t, r), t) for r, t in THREATS):
            # threats that began before our first round are present from the start
            r = max(r, start)
            # past r+1 it is no longer "early"; stop holding the plan hostage
            if r - lookahead <= rnd <= r + 1 and threat not in self.unanswerable \
                    and not self.has_answer(threat):
                return threat
        return None

    def answer_threat(self, threat, cash, rnd):
        """Run the strategy's `answers:` steps for this threat (or a generic one).
        Returns 'bought', 'wait' (saving for it) or 'none' (nothing applicable)."""
        steps = (self.strat.get("answers") or {}).get(threat)
        if steps is None:
            steps = self._generic_answer(threat)
        for st in steps:
            if not self._step_allowed(st):
                continue
            r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("threat %s: bought toward answer %s", threat, st)
                return "bought"
            if r == "wait":
                return "wait"
        return "none"

    def _generic_answer(self, threat):
        """Upgrade an existing tower (from its current tiers) toward a listed answer."""
        steps = []
        for p in self.g.towers.values():
            for kind, path, tier in ANSWERS.get(threat, []):
                if p.kind != kind or not path:
                    continue
                to = list(p.tiers)
                to[path - 1] = max(to[path - 1], tier)
                if self.no_income and self._is_income(kind, to):
                    continue
                if sum(t > 0 for t in to) <= 2 and sum(t > 2 for t in to) <= 1:
                    steps.append({"do": "upgrade", "id": p.tid, "to": "-".join(map(str, to))})
        return steps[:3]

    def tick(self, cash, rnd, lives_dropped=False):
        """Do at most one action. Returns True if something was bought."""
        if cash is None:
            return False  # never act on an unreadable cash value
        if lives_dropped:
            self.panic_pending = 2
        if self.panic_pending:
            for st in self.panic_steps:
                r = self.try_step(dict(st), cash, rnd)
                if r in ("bought", "progress"):
                    self.panic_pending -= 1
                    return True
        threat = self.due_threat(rnd)
        if threat:
            r = self.answer_threat(threat, cash, rnd)
            if r == "bought":
                return True
            if r == "wait":
                return False  # hold cash for the answer
            self.unanswerable.add(threat)  # nothing applicable; don't block the plan
        while self.idx < len(self.plan):
            r = self.try_step(self.plan[self.idx], cash, rnd)
            if r in ("done", "skip", "bought"):
                self.idx += 1
                if r == "bought":
                    return True
                continue
            return r == "progress"  # waiting for cash / round, or mid-upgrade
        for st in self.fill:
            if self.try_step(st, cash, rnd) in ("bought", "progress"):
                return True
        return False

    def defended(self):
        return any(p.kind != "hero" for p in self.g.towers.values()) or \
            any(p.kind == "hero" for p in self.g.towers.values())
