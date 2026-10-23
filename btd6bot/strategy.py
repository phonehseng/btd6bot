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

from . import threats as TH
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

# Round where each kind of threat first shows up, from data/rounds.json (built
# from the game's round data, standard and Alternate Bloons Rounds). The
# executor builds the answer a few rounds BEFORE it: DDTs, MOABs and the
# round-63 ceramic rush are too fast to answer after they appear.
_FIRST_KEYS = {"camo": "camo", "purple": "purple", "lead": "lead", "ceramic": "ceramic",
               "moab": "moab", "bfb": "bfb", "zomg": "zomg", "ddt": "ddt", "bad": "bad"}


def _first_appearance():
    import json
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).resolve().parents[1] / "data" / "rounds.json")
                       .read_text(encoding="utf-8"))["first_appearance"]
        std = {k: d["standard"][v] for k, v in _FIRST_KEYS.items()}
        abr = {k: d["abr"][v] for k, v in _FIRST_KEYS.items()}
        return std, abr
    except (OSError, ValueError, KeyError):
        std = {"camo": 24, "purple": 25, "lead": 28, "ceramic": 38, "moab": 40,
               "bfb": 60, "zomg": 80, "ddt": 90, "bad": 100}
        abr = {"camo": 5, "purple": 15, "lead": 10, "ceramic": 32, "moab": 40,
               "bfb": 54, "zomg": 79, "ddt": 88, "bad": 99}
        return std, abr


_STD, _ABR = _first_appearance()
_STD["rush"] = _ABR["rush"] = 63   # 122 ceramics + 75 leads (14,413 RBE)
# camo in bulk: one camo-capable tower handles round 24's lone camo green, not
# camo ceramics (51) or camo leads (59; ABR 24) - those need "strong camo"
try:
    import json as _json
    from pathlib import Path as _Path
    _fa = _json.loads((_Path(__file__).resolve().parents[1] / "data" / "rounds.json")
                      .read_text(encoding="utf-8"))["first_appearance"]
    _STD["camo_ceramic"], _ABR["camo_ceramic"] = _fa["standard"]["camo_ceramic"], _fa["abr"]["camo_ceramic"]
    _STD["camo_lead"], _ABR["camo_lead"] = _fa["standard"]["camo_lead"], _fa["abr"]["camo_lead"]
except (OSError, ValueError, KeyError):
    _STD.update(camo_ceramic=51, camo_lead=59)
    _ABR.update(camo_ceramic=51, camo_lead=24)
THREATS = sorted((r, t) for t, r in _STD.items())
ABR_SHIFT = {t: r for t, r in _ABR.items() if r != _STD.get(t)}

# What counts as an answer: (tower, path, min tier) - any one is enough.
ANSWERS = {
    # purple bloons are immune to fire, energy and plasma (Inferno Ring, wizard
    # bolts, plasma darts): needs plain sharp/explosive/cold damage too
    "purple": [("dart", 0, 0), ("boomerang", 0, 0), ("bomb", 0, 0), ("sniper", 0, 0),
               ("sub", 0, 0), ("buccaneer", 0, 0), ("ninja", 0, 0), ("ice", 0, 0),
               ("heli", 0, 0), ("ace", 0, 0), ("mortar", 0, 0), ("spike", 0, 0),
               ("druid", 0, 0), ("engineer", 0, 0), ("super", 0, 0)],
    # towers/tiers that detect camo (corrected from the game model: Night Vision
    # is 0-1-0, the Sub's own camo attack comes at 4-x-x, 3-x-x only strips
    # camo); spikes hit camo on the track without detection. Replaced below
    # by gamemodel.answers("camo") when the game model is available.
    "camo": [("dart", 3, 2), ("sniper", 2, 1), ("ninja", 0, 0), ("wizard", 3, 2),
             ("sub", 1, 4), ("village", 2, 2), ("spike", 0, 0), ("ice", 1, 2), ("ace", 2, 2),
             ("heli", 2, 2), ("mortar", 3, 1), ("dartling", 2, 1), ("buccaneer", 3, 2),
             ("super", 3, 2), ("mermonkey", 3, 1)],
    # the Alchemist's acid pops lead from tier 0 (game model)
    "lead": [("tack", 1, 3), ("bomb", 0, 0), ("boomerang", 3, 2), ("sniper", 1, 1), ("alchemist", 0, 0),
             ("wizard", 2, 1), ("mortar", 0, 0), ("dart", 1, 4), ("ninja", 3, 3), ("spike", 1, 2),
             ("super", 1, 2)],
    "ceramic": [("tack", 1, 3), ("boomerang", 1, 3), ("bomb", 2, 2), ("sniper", 1, 2), ("dart", 3, 3),
                ("heli", 1, 2), ("ninja", 1, 3), ("super", 0, 0), ("spike", 0, 0), ("druid", 1, 3)],
    "moab": [("bomb", 2, 3), ("boomerang", 1, 4), ("tack", 1, 4), ("sniper", 1, 3), ("heli", 1, 3),
             ("dart", 3, 4), ("ninja", 3, 3), ("super", 0, 0), ("spike", 3, 3), ("druid", 2, 4),
             ("wizard", 2, 4), ("ace", 0, 0), ("sub", 3, 3), ("buccaneer", 2, 4)],
    "bfb": [("tack", 1, 5), ("bomb", 2, 4), ("sniper", 1, 4), ("heli", 1, 4), ("boomerang", 1, 4), ("dart", 3, 4),
            ("super", 1, 3), ("ninja", 3, 4), ("spike", 3, 4), ("druid", 2, 4), ("tack", 1, 4)],
    "rush": [("tack", 1, 4), ("bomb", 3, 3), ("ninja", 1, 4), ("super", 0, 0), ("wizard", 2, 3),
             ("dartling", 0, 0), ("boomerang", 1, 3), ("ice", 3, 3)],
    "zomg": [("tack", 1, 5), ("bomb", 2, 4), ("sniper", 1, 4), ("super", 1, 3), ("heli", 1, 4), ("spike", 3, 4),
             ("boomerang", 1, 5), ("druid", 2, 4), ("ninja", 3, 4)],
    "ddt": [("sniper", 1, 4), ("bomb", 2, 4), ("heli", 1, 4), ("super", 1, 3), ("spike", 3, 4),
            ("ninja", 3, 4), ("boomerang", 1, 4), ("dart", 3, 4)],
    "bad": [("super", 1, 4), ("bomb", 2, 5), ("sniper", 1, 5), ("ninja", 3, 5), ("spike", 3, 5)],
}


def _answers_from_game_model():
    """Camo and lead answers straight from the game's own model
    (gamemodel.answers: the lowest tier of each path that has it), so these
    two lists follow game updates. Spikes are kept as a camo answer: they hit
    camo on the track without detecting it. Hand lists stay when the model
    is missing."""
    try:
        from . import gamemodel
        if not gamemodel.available():
            return
        camo, lead = gamemodel.answers("camo"), gamemodel.answers("lead")
    except Exception as e:     # a broken model file must not stop the bot
        log.warning("game model answers unavailable: %r", e)
        return
    if camo:
        # + spikes (camo on the track) and the Radar Scanner village (lends camo)
        ANSWERS["camo"] = list(camo) + [a for a in ANSWERS["camo"] if a[0] in ("spike", "village")
                                        and a not in camo]
    if lead:
        ANSWERS["lead"] = list(lead)


_answers_from_game_model()

# Prices: CHIMPS is a Hard mode in the game (x1.08), not Impoppable (x1.2);
# MODE_FAMILY keeps it with Impoppable for difficulty order (min_difficulty).
PRICE_FAMILY = dict(MODE_FAMILY, chimps="hard")
UNREAD_RETRY_S = 10.0   # seconds before a path whose price was not read is tried again
RESERVED_CELLS = 4      # a tower placed by role keeps this far from a later step's exact spot

# Towers that belong at the end of the track: spike factories throw their
# spikes onto the last stretch and catch what leaks past everything else.
EXIT_KINDS = {"spike"}

# camo-requiring threats also need camo on the answering tower (or village MIB)
NEEDS_CAMO = {"ddt"}
STRONG_CAMO = {"camo_ceramic", "camo_lead"}
RADAR = ("village", 2, 2)   # Radar Scanner: every tower in range sees camo


def strong_camo(builds):
    """builds: iterable of (kind, tiers). Village Radar Scanner, or at least two
    camo-capable towers upgraded to tier 3+ on some path."""
    n = 0
    for kind, tiers in builds:
        if kind == RADAR[0] and tiers[RADAR[1] - 1] >= RADAR[2]:
            return True
        for k, path, tier in ANSWERS["camo"]:
            if k == kind and (path == 0 or tiers[path - 1] >= tier) and max(tiers) >= 3:
                n += 1
                break
    return n >= 2

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
                      "threat_shift": ABR_SHIFT},
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
             "target", "to", "mode",
             "at"}   # exact spot [fx, fy] (screen fractions) from a map's own build
UNSUPPORTED_STEP_KEYS = {
    "avoid": "spot avoidance (`avoid`) is not implemented by pick_spot",
    "avoid_radius": "spot avoidance (`avoid`) is not implemented by pick_spot",
    "note": "hand-calibrated placement notes (`note`) cannot be followed",
}
TARGET_MODES = {"first", "last", "close", "strong"}  # cycled by Game.target(); no point targets


def final_build(strat, account=None):
    """{kind: [p1, p2, p3]} the plan ends with (plan + answers), each path capped
    at what the account has unlocked (unknown upgrades count as locked above
    tier 2: tiers 1-2 are cheap and usually unlockable in-game)."""
    answer_steps = [a for v in (strat.get("answers") or {}).values() for a in v]
    places = [st for st in strat.get("plan", []) + answer_steps if st.get("do") == "place"]
    ids = {st["id"]: st["kind"] for st in places if st.get("id") and st.get("kind")}
    build = {}
    for st in places:
        if st.get("kind") not in (None, "hero"):
            build.setdefault(st["kind"], [0, 0, 0])
    steps = strat.get("plan", []) + [a for v in (strat.get("answers") or {}).values() for a in v]         + strat.get("fill", [])
    for st in steps:
        if st.get("do") != "upgrade":
            continue
        kind = st.get("kind") or ids.get(st.get("id"))
        if kind not in T.TOWERS:
            continue
        have = build.setdefault(kind, [0, 0, 0])
        tgt = parse_cross(st["to"])
        for i in range(3):
            have[i] = max(have[i], tgt[i])
    if account is not None:
        for kind, tiers in build.items():
            build[kind] = [min(t, reachable_tier(account, kind, i)) for i, t in enumerate(tiers)]
    return build


def invested_cash(strat):
    """{kind: dollars} the strategy's `plan` steps put into each tower type
    (Medium prices from towers.py), or None when the plan places no towers.

    Tower XP is split between tower types by the cash invested in them at
    each round end (docs/tower_xp.md), so this is what the planner uses to
    estimate which towers a game levels up. Only the `plan` section counts:
    `fill`, `panic` and `answers` depend on how the game goes. Heroes are
    left out, as the game leaves them out of the split."""
    kinds = {}    # placed tower id -> kind
    tiers = {}    # placed tower id -> [p1, p2, p3] it ends the plan with
    for st in strat.get("plan") or []:
        kind = st.get("kind")
        if st.get("do") == "place" and kind in T.TOWERS:
            tid = st.get("id") or f"#{len(kinds)}"   # unnamed towers stay separate
            kinds.setdefault(tid, kind)
            tiers.setdefault(tid, [0, 0, 0])
        elif st.get("do") == "upgrade" and st.get("to"):
            # by id: that tower; by kind only: every placed tower of the kind
            targets = [st["id"]] if st.get("id") in tiers else \
                [tid for tid, k in kinds.items() if k == kind and not st.get("id")]
            want = parse_cross(st["to"])
            for tid in targets:
                tiers[tid] = [max(a, b) for a, b in zip(tiers[tid], want)]
    cash = {}
    for tid, kind in kinds.items():
        cash[kind] = cash.get(kind, 0) + T.total_cost(kind, tuple(tiers[tid]))
    return cash or None


def reachable_tier(account, kind, path0):
    """Highest tier on path (0-based) this account has, or can unlock before the
    game: unlocked tiers, plus tiers 1-2 when the tower has banked XP for them."""
    unl = account.upgrades(kind)[path0]
    xp = float((account.tower_xp or {}).get(kind, 0) or 0)
    if unl < 2 and xp >= 1200:
        return 2
    if unl < 1 and xp >= 300:
        return 1
    return unl


# Camo backups, best first: (kind, crosspath) giving strong camo help.
CAMO_BACKUPS = [("village", "0-2-0"), ("dart", "0-2-3"), ("sniper", "3-2-0"),
                ("ninja", "3-0-0"), ("wizard", "0-0-3"), ("sub", "3-0-0")]


def camo_backup(strat, account=None, mode=None):
    """Steps adding strong camo when the strategy's own build lacks it: the best
    backup this account has unlocked and the mode allows. [] if not needed."""
    if strong_camo(final_build(strat, account).items()):
        return []
    cons = strat.get("constraints") or {}
    allowed = cons.get("allowed_towers")
    only = MODE_TOWER_FILTER.get(mode)
    for kind, cross in CAMO_BACKUPS:
        if allowed is not None and kind not in allowed:
            continue
        if kind in (cons.get("forbidden_towers") or ()):
            continue
        if only and T.TOWERS[kind]["category"] != only:
            continue
        if account is not None:
            if kind not in account.unlocked_towers:
                continue
            need = parse_cross(cross)
            if any(n > reachable_tier(account, kind, i) for i, n in enumerate(need)):
                continue
        sid = f"camo_{kind}"
        place = {"do": "place", "id": sid, "kind": kind}
        place.update({"role": "support", "near": [st["id"] for st in strat.get("plan", [])
                                                 if st.get("do") == "place" and st.get("id")][:4],
                      "near_radius": 8} if kind == "village" else {"role": "dps", "segment": [0.0, 0.7]})
        return [place, {"do": "upgrade", "id": sid, "to": cross}]
    return []


def coverage(strat, mode, account=None):
    """(ok, missing): does the strategy's final build answer every threat that
    appears in this mode's rounds, given the account's unlocked upgrades?"""
    backup = camo_backup(strat, account, mode)
    if backup:
        strat = dict(strat, answers=dict(strat.get("answers") or {}, camo_ceramic=backup))
    build = final_build(strat, account)
    r = rules(mode)
    start, end = r.get("start_round", 1), r.get("end_round", 80)
    shift = r.get("threat_shift", {})

    # tower instances per kind (the build is per kind; strong camo counts towers)
    answer_steps = [a for v in (strat.get("answers") or {}).values() for a in v]
    copies = {}
    for st in strat.get("plan", []) + answer_steps:
        if st.get("do") == "place" and st.get("kind") in build:
            copies[st["kind"]] = copies.get(st["kind"], 0) + 1

    # the final build as towers for threats.covers (copies of a kind share its tiers)
    towers = [(f"{k}{i}", k, tuple(t)) for k, t in build.items() for i in range(copies.get(k, 1))]
    use_sigs = TH.available()

    def answered(threat):
        if threat in STRONG_CAMO:
            return strong_camo([(k, t) for k, t in build.items() for _ in range(copies.get(k, 1))])
        if threat == "ddt" and use_sigs:
            # the DDT-tier tower itself must hurt DDTs (camo + lead + black at once)
            sig = TH.sig_from_name("ddt")
            for kind, path, tier in ANSWERS["ddt"]:
                tiers = build.get(kind)
                if tiers is not None and (path == 0 or tiers[path - 1] >= tier) and \
                        TH.covers(towers, sig, poppers={t[0] for t in towers if t[1] == kind})[0]:
                    return True
            return False
        if threat in NEEDS_CAMO and not answered("camo"):
            return False
        for kind, path, tier in ANSWERS.get(threat, []):
            tiers = build.get(kind)
            if tiers is not None and (path == 0 or tiers[path - 1] >= tier):
                return True
        return False

    missing = [t for rnd, t in THREATS if shift.get(t, rnd) <= end and not answered(t)]
    if use_sigs:
        # Bloons the build cannot pop at all (threats.py), from this mode's own
        # rounds. Fine if the final build pops them, or if the Executor can buy
        # a tower that does in-game (allowed by the mode, the strategy's
        # constraints and the account; land towers only, as the map is unknown).
        kinds = _answer_kinds(strat, mode, account)
        for need in TH.calendar(TH.set_for_mode(mode), start, end):
            sig = TH.sig_from_name(need)
            if need in missing or TH.covers(towers, sig)[0]:
                continue
            if not constraints(strat).get("no_answers") and any(
                    TH.covering_crosspaths(k, sig, towers, caps) for k, caps in kinds):
                continue
            missing.append(need)
    return (not missing), missing


def _answer_kinds(strat, mode, account=None):
    """[(kind, caps)] towers the Executor could buy as an answer in this mode:
    the mode's category, the strategy's constraints, the account's unlocks;
    no income towers, no towers that must be aimed, no water towers."""
    c = constraints(strat)
    only = MODE_TOWER_FILTER.get(mode)
    out = []
    for kind, facts in T.TOWERS.items():
        if kind in INCOME_TOWERS or (only and facts["category"] != only):
            continue
        if (c.get("allowed_towers") is not None and kind not in c["allowed_towers"]) \
                or kind in (c.get("forbidden_towers") or ()):
            continue
        if (facts.get("placement") or "land") == "water" or TH.tower_facts(kind).get("needs_aim"):
            continue
        if account is not None and kind not in account.unlocked_towers:
            continue
        caps = [reachable_tier(account, kind, i) if account is not None else 5 for i in range(3)]
        out.append((kind, caps))
    return out


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


# An optimized build's win chance before it has been played, from the
# model's lowest margin over all its rounds (docs/optimizer.md, section 3:
# 0.5% of logged rounds at a margin of 2.0 or more lost lives, 5.4% below
# 1.0). Below OPTIMIZED_MIN_MARGIN it is never auto-played. Kept under
# the researched map builds (0.9): the model misses what some map files do
# not record - Ravine Easy, rated 2.99, was lost at round 18 (2026-10-23),
# while researched builds won their first seven Hard games.
OPTIMIZED_SAFE_MARGIN = 2.0
OPTIMIZED_MIN_MARGIN = 1.0
OPTIMIZED_PRIOR = {"safe": 0.88, "thin": 0.8}


def _optimized_prior(d, planner):
    """Set planner.base_success and d["needs_boosts"] for an optimized
    build from its `optimizer:` block; returns reasons it may not be played."""
    opt = d.get("optimizer") or {}
    worst = opt.get("worst_margin")
    if worst is None:
        return ["optimized build without optimizer.worst_margin"]
    if opt.get("unsafe_rounds") or worst < OPTIMIZED_MIN_MARGIN:
        return [f"model margin too thin (worst {worst:.2f}, unsafe rounds {opt.get('unsafe_rounds')})"]
    p = OPTIMIZED_PRIOR["safe" if worst >= OPTIMIZED_SAFE_MARGIN else "thin"]
    planner["base_success"] = {m: p for m in d.get("modes") or ()}
    # planned with the account's Double Cash / Fast Track income: not proven
    # safe without them (runner.planner_specs skips it then)
    boosts = (opt.get("scenario") or {}).get("boosts") or []
    d["needs_boosts"] = [b.replace(" ", "_") for b in boosts]
    return []


def load_all():
    """All strategies by id: strategies/*.yaml, strategies/generated/*.yaml and
    strategies/achievements/**/*.yaml.

    Every strategy gets `bot_ready` (bool). Achievement strategies also get
    `source: "achievements"`, `bot_ready_reasons`, and planner.maps from `map:`.
    Generated builds (tools/gen_builds.py: one solo XP build per tower) get
    `source: "generated"` and `bot_ready_reasons`; one that does not parse is
    skipped and one that fails readiness() is never auto-played, so a bad
    file there can neither stop the bot nor be played.
    Ids stay unique: a later file with a used id is skipped (logged)."""
    out = {}
    for f in sorted(STRAT_DIR.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d.setdefault("id", f.stem)
        d.setdefault("bot_ready", True)
        out[d["id"]] = d
    gen_dir = STRAT_DIR / "generated"
    for f in sorted(gen_dir.glob("*.yaml")) if gen_dir.is_dir() else ():
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception as e:  # a half-written or broken file must not stop the bot
            log.error("generated strategy %s does not parse: %s", f.name, e)
            continue
        if not isinstance(d, dict):
            log.error("generated strategy %s is not a mapping", f.name)
            continue
        d.setdefault("id", f.stem)
        if d["id"] in out:
            log.error("duplicate strategy id %s in %s - skipped", d["id"], f)
            continue
        d["source"] = "generated"
        try:
            reasons = readiness(d)
        except Exception as e:
            reasons = [f"validation failed: {e!r}"]
        d["bot_ready"] = not reasons
        d["bot_ready_reasons"] = reasons
        out[d["id"]] = d
    # Map-specific builds, only ever planned on their own map:
    #   strategies/maps       researched per map (docs/map_strategies.md)
    #   strategies/optimized  proven round by round on the game's own numbers
    #                         (tools/optimize_builds.py, docs/optimizer.md)
    # Both carry exact `at` spots.
    for source in ("maps", "optimized"):
        src_dir = STRAT_DIR / source
        for f in sorted(src_dir.glob("*.yaml")) if src_dir.is_dir() else ():
            try:
                d = yaml.safe_load(f.read_text(encoding="utf-8"))
            except Exception as e:  # a broken file must not stop the bot
                log.error("%s strategy %s does not parse: %s", source, f.name, e)
                continue
            if not isinstance(d, dict) or not d.get("map"):
                log.error("%s strategy %s has no `map:` - skipped", source, f.name)
                continue
            d.setdefault("id", f.stem)
            if d["id"] in out:
                log.error("duplicate strategy id %s in %s - skipped", d["id"], f)
                continue
            d["source"] = source
            try:
                reasons = readiness(d)
            except Exception as e:
                reasons = [f"validation failed: {e!r}"]
            planner = dict(d.get("planner") or {})
            planner["maps"] = [d["map"]]          # never on another map
            if source == "optimized":
                reasons += _optimized_prior(d, planner)
            d["bot_ready"] = not reasons
            d["bot_ready_reasons"] = reasons
            d["planner"] = planner
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
        if not T.TOWERS[k].get("hotkey"):
            # placed by hotkey only: Desperado, Mermonkey and Skywarden have
            # none by default (docs/backlog.md) - a build leaning on them
            # would start its rounds with towers missing
            return False, f"{k} has no hotkey bound"
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
        backup = camo_backup(strat, account, mode)
        if backup:  # strong camo for rounds 51/59 the plan itself lacks
            answers = dict(strat.get("answers") or {})
            answers.setdefault("camo_ceramic", backup)
            answers.setdefault("camo_lead", backup)
            strat = dict(strat, answers=answers)
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
        self.plan = self._with_opener([dict(s) for s in strat.get("plan") or [] if self._step_allowed(s)])
        self.fill = [dict(s) for s in strat.get("fill") or [] if self._step_allowed(s)]
        self.panic_steps = [dict(s) for s in strat.get("panic") or [] if self._step_allowed(s)]
        if not self.panic_steps and not c.get("no_default_panic"):
            k = self._best_panic_kind()
            if k:
                self.panic_steps = [{"do": "place", "kind": k, "role": "exit" if k in EXIT_KINDS else "dps"}]
        self.idx = 0
        self.counter = {}
        self.capped = set()          # (tid, path) that turned out locked
        self.unread_until = {}       # (tid, path) -> time: its price was not read, try later
        self.failed_spots = set()
        self.panic_pending = 0
        self.unanswerable = set()
        self.hold_fails = {}       # kind -> times the hotkey would not pick it up
        # Refused spots are counted per step under a key that survives copying
        # (_step_key): panic and answer steps run from fresh dict copies, so a
        # count keyed by id(step) never added up and they retried forever.
        self.step_spot_fails = {}  # step key -> spots refused in a row for that step
        self.dead_steps = set()    # step keys given up for this game (no spot accepted)
        self.deferred = []         # plan steps retried later instead (the hero)
        self.retry_at = {}         # step key -> time before which it is not retried
        self.hero_misses = 0       # times the hero ran out of accepted spots
        self.learned_blocks = 0
        self.upgrade_fails = {}    # (tid, path) -> non-XP failures this game
        self.panel_price = {}      # (tid, path, tier) -> price the panel asked (above table)
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

    CHEAP_OPENERS = ("dart", "tack", "boomerang", "sniper", "sub", "wizard")

    def _with_opener(self, plan):
        """Rounds 1-5 leak when a plan opens with one slow/expensive tower (seen:
        lone base Ninja on Medium). Prepend a $200 Dart near the entrance unless
        the plan already opens cheap or the mode/constraints forbid darts."""
        if self.rules.get("start_round", 1) > 5 or self.rules.get("buy_all_upfront"):
            return plan  # no early rounds to hold (Deflation starts at 31 on fixed cash)
        first = next((st for st in plan if st.get("do") == "place"), None)
        if first is None or first.get("kind") in self.CHEAP_OPENERS + ("hero",):
            return plan  # a hero (or cheap tower) already holds the early rounds
        cons = self.strat.get("constraints") or {}
        if self.strat.get("achievement") or cons:
            return plan  # constrained plans are exact; never add towers to them
        if not self.kind_allowed("dart"):
            return plan
        return [{"do": "place", "id": "opener", "kind": "dart", "role": "dps",
                 "segment": [0.05, 0.45]}] + plan

    def kind_allowed(self, kind):
        """May a tower of this kind be placed at all in this game?"""
        if kind == "hero":
            return self.hero_ok
        if kind not in T.TOWERS:
            return False
        if not T.TOWERS[kind].get("hotkey"):
            # it cannot be picked up (Game.hold): a threat answer chose a
            # Mermonkey, which has no hotkey bound, on every tick of a game
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
        """The game refused this spot although the map model said it was fine:
        record it in the model's refused layer (MapModel.refuse), so later
        games (any mode) never try it again.

        Root cause of the refused-spot loop: refusals used to be written into
        model.scan, which mapgeom.apply() rebuilds from the game files; and
        after 10 refusals the scan was dropped "to rescan next visit", which
        on a map with game geometry only re-applied the same geometry (the
        bad spots came back) and, for the rest of that game, left spot
        picking with no placement data at all. The refused layer is never
        touched by the geometry, so neither happens any more."""
        if kind == "hero":
            cls = T.HEROES.get(self.g.hero, {}).get("placement") or "land"
        else:
            cls = T.TOWERS.get(kind, {}).get("placement") or "land"
        refuse = getattr(self.m, "refuse", None)
        if refuse is None:
            return
        # Ground under a cycling pane (Covered Garden) is only open one round
        # in four: a refusal there most likely means the round turned over
        # between reading it and clicking, not that the ground is bad.
        try:
            from . import mapgeom
            if mapgeom.pane_at(self.m, *self.m.cell_to_frac(cx, cy), None)[0] is not None:
                log.info("spot (%d,%d) under a pane refused - not learned (the pane may have just closed)",
                         cx, cy)
                return
        except Exception:
            pass
        # an amphibious tower refused here stands neither on land nor on water
        for surface in (("land", "water") if cls == "land_or_water" else (cls,)):
            refuse(surface, cx, cy)
        log.info("learned: %s spot (%d,%d) is not placeable on this map", cls, cx, cy)
        self.learned_blocks += 1
        if (self.learned_blocks > 10 and cls in self.m.scan
                and getattr(self.m, "geometry_bundle", None) is None):
            # only a map without game geometry has a scan of its own that can
            # be wrong as a whole: redo that scan next visit
            log.warning("map scan disagrees with the game too often - rescanning next visit")
            self.m.scan.pop(cls, None)

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
        """An id for a tower placed without one (surplus, fills, answers):
        never one the board or the build already uses - a surplus "sub1"
        made the plan's own sub1 look placed, so it was never built and its
        upgrades went to the other tower."""
        if not hasattr(self, "_reserved_ids"):
            steps = list(self.plan) + list(self.strat.get("fill") or []) \
                + [a for v in (self.strat.get("answers") or {}).values() for a in v]
            self._reserved_ids = {st["id"] for st in steps if st.get("id")}
        while True:
            self.counter[kind] = self.counter.get(kind, 0) + 1
            tid = f"{kind}{self.counter[kind]}"
            if tid not in self._reserved_ids and tid not in self.g.towers:
                return tid

    def _range_cells(self, kind):
        if kind == "hero":
            rng = T.HEROES.get(self.g.hero, {}).get("range") or 40
        else:
            rng = T.TOWERS[kind].get("range") or 400
        return self.m.radius_cells(rng, self.g.s.width)

    def _covered(self):
        """Grid of track already within range of placed damage towers (0/1)."""
        import cv2
        grid = np.zeros(self.m.heat.shape, np.float32)
        for p in self.g.towers.values():
            if p.kind in ("village", "alchemist", "farm"):
                continue  # support towers do not pop
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            r = int(round(min(self._range_cells(p.kind), 60)))
            cv2.circle(grid, (int(cx), int(cy)), max(1, r), 1.0, -1)
        return grid

    def _occupied(self):
        out = []
        for p in self.g.towers.values():
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            out.append((cx, cy, 3))  # footprints: ~3 cells radius each
        return out

    def pick_spot(self, kind, step):
        """The best spot (cx, cy, score) for this step, or None."""
        spots = self.pick_spots(kind, step, n=1)
        return spots[0] if spots else None

    def pick_spots(self, kind, step, n=1):
        """Up to n spots (cx, cy, score), best first, at least 3 cells apart:
        the alternatives Game.place tries while still holding the tower.
        (Neighbouring cells of a refused spot are usually refused too.)"""
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
        if role == "exit" and kind not in EXIT_KINDS:
            # Only leak-catchers belong at the exit. A lead/camo answer or a
            # panic tower placed there pops a lead whose children then escape;
            # it covers the most still-uncovered track instead.
            role = "dps"
        if role == "exit":
            seg = (0.65, 1.0)
        if role == "support" and step.get("near"):
            ids = [i for i in step["near"] if i in self.g.towers]
            if ids:
                xs = [self.g.towers[i].x for i in ids]
                ys = [self.g.towers[i].y for i in ids]
                near = self.m.frac_to_cell(sum(xs) / len(xs), sum(ys) / len(ys))
                near_r = step.get("near_radius", 9)
        # Where this tower fits, from the game's own map geometry: its
        # footprint on allowed ground, clear of track, obstacles and the towers
        # already placed (None on maps without geometry: old grid checks)
        from . import placement as PL
        hero = self.g.hero if kind == "hero" else None
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        # the game's last round: ground that only changes later (Erosion's ice
        # melts after round 54) is usable in a shorter game
        valid = PL.valid_spots(self.m, kind, hero, placed,
                               where={"land"} if self.land_only else None,
                               last_round=self.rules.get("end_round"), now_round=self._pane_round())
        covered = None if role == "support" else self._covered()
        if role == "far":
            cover = -self.m.score_spots(rc, seg, self._occupied(), placement=placement,
                                        extra_block=self.blocked, valid=valid)
            cover[cover >= 1] = -1  # still exclude blocked/occupied
        else:
            cover = self.m.score_spots(rc, seg, self._occupied(), near=near, near_radius=near_r,
                                       placement=placement, extra_block=self.blocked,
                                       covered=covered, valid=valid)
        from .maplearn import spot_factor
        cands = self.m.best_spots(cover, n=30 if valid is not None else 12)
        if valid is not None and role not in ("support", "far") and PL.needs_sight(kind, hero):
            # count only the track this spot can actually see past walls/blockers
            weight = self.m.spot_weight(seg, covered)
            cands = [(cx, cy, PL.visible_cover(self.m, cx, cy, rc, weight)) for cx, cy, _ in cands]
        edge = self._edge_band()
        ranked = sorted(((cx, cy, sc * spot_factor(self.m, kind, cx, cy)
                          * (self.EDGE_PENALTY if edge is not None and edge[cy, cx] else 1.0))
                         for cx, cy, sc in cands), key=lambda t: -t[2])
        out = []
        exact = self._exact_spot(step, valid)
        if exact is not None:
            out.append(exact)       # the build's researched spot comes first
        floor = self._reach_floor(kind, valid) if role in ("dps", "exit") else None
        probe = self._probe_spot(kind, valid) if role in ("dps", "exit") else None
        if probe is not None:
            out.append(probe)       # tried first; a refusal costs ~0.1 s and is learned
        reserved = self._reserved_cells(step)
        for cx, cy, score in ranked:
            if (kind, cx, cy) in self.failed_spots:
                continue
            if floor is not None and self._reach(kind)[cy, cx] < floor:
                continue  # its range only grazes the track (see MIN_REACH_SHARE)
            if any((cx - rx) ** 2 + (cy - ry) ** 2 < RESERVED_CELLS ** 2 for rx, ry in reserved):
                continue  # a later step of the build places a tower right here
            if any((cx - ox) ** 2 + (cy - oy) ** 2 < 9 for ox, oy, _ in out):
                continue
            out.append((cx, cy, score))
            if len(out) >= n:
                break
        return out

    def _reserved_cells(self, step):
        """Cells of the exact spots (`at`) the build's later place steps
        still need. A tower placed by role must leave them free: on Ravine
        Easy the hero, placed by role, sat beside two planned bomb spots,
        and those bombs went to the far side of the map."""
        out = []
        strat = getattr(self, "strat", None) or {}
        for st in list(getattr(self, "plan", None) or []) + list(strat.get("fill") or []):
            at = st.get("at")
            if st.get("do") != "place" or not at or st is step or st.get("id") == step.get("id"):
                continue
            if st.get("id") in self.g.towers:
                continue    # placed already
            out.append(self.m.frac_to_cell(float(at[0]), float(at[1])))
        return out

    def _next_path(self, p, target):
        """Cheapest next tier that moves p toward target crosspath."""
        if any(c > t for c, t in zip(p.tiers, target)):
            return None  # tower already went another way; target unreachable
        best = None
        for i in range(3):
            if p.tiers[i] >= target[i] or (p.tid, i + 1) in self.capped:
                continue
            if time.time() < getattr(self, "unread_until", {}).get((p.tid, i + 1), 0):
                continue      # its price was just unreadable (Game._path_closed): later
            tier = p.tiers[i] + 1
            cost = (T.upgrade_cost(p.kind, i + 1, tier, PRICE_FAMILY.get(self.mode, "hard"))
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

    # Placing: spots probed per pick-up of a tower, refused spots in a row
    # after which a step is given up for the rest of the game, and the pause
    # before the hero (never given up) is tried again at the next-best spots.
    # A probe while holding costs ~0.1 s; cancelling and picking the tower up
    # again (the "pick a monkey, then X" the owner saw mid-round) costs ~1.4 s,
    # so a pick-up tries many spots: 22 games logged 166 refused spots.
    SPOTS_PER_HOLD = 10
    SPOT_LIMIT = 20
    # Refused spots cluster at the track's edge (3 cells from the path line:
    # 59% refused, against 26% from 7 cells out), so the edge band ranks lower.
    EDGE_CELLS = 3
    EDGE_PENALTY = 0.75
    HERO_RETRY_S = 8.0        # first pause; it doubles after every further miss ...
    HERO_RETRY_MAX_S = 120.0  # ... up to this
    # Failed selections in a row after which a tower is taken to be absent.
    MAX_SELECT_FAILS = 2

    @staticmethod
    def _step_key(step):
        """A name for a step that is the same for every copy of it. Panic and
        answer steps are run from fresh dict copies on every tick, so a count
        keyed by id(step) started from zero each time and never gave up."""
        return (step.get("do"), step.get("kind"), step.get("role", "dps"), step.get("id"),
                tuple(step.get("near") or ()), tuple(step.get("segment") or ()))

    def _pane_round(self):
        """The round being played, on maps whose panes open in turn (Covered
        Garden): the open pane's ground takes towers this round. None
        elsewhere, so other maps keep their whole-game grids."""
        from . import mapgeom
        try:
            grids = mapgeom.grids_for(self.m)
        except Exception:
            return None
        if grids and grids.get("panes"):
            return getattr(self, "now_round", None)
        return None

    def _reachable(self, p):
        """False while a closed pane covers tower p: a click there hits the
        glass, so it cannot be upgraded or sold this round."""
        from . import mapgeom
        try:
            return mapgeom.pane_at(self.m, p.x, p.y, getattr(self, "now_round", None))[1]
        except Exception:
            return True

    def try_step(self, step, cash, rnd):
        """Returns 'done', 'wait', 'skip', 'bought' or 'progress'."""
        if rnd is not None and step.get("round") and rnd < step["round"]:
            return "wait"
        do = step["do"]
        if do == "place":
            return self._try_place(step, cash)
        if do == "upgrade":
            target = parse_cross(step["to"])
            targets = self._resolve_targets(step)
            if self.no_income:
                targets = [p for p in targets if not self._is_income(p.kind, target)]
            for p in targets:
                nxt = self._next_path(p, target)
                if nxt is None:
                    continue
                if not self._reachable(p):
                    return "wait"     # under a closed pane: its round comes
                path, cost = nxt
                # a panel that asked more than the price table is believed
                cost = max(cost, self.panel_price.get((p.tid, path, p.tiers[path - 1] + 1), 0))
                if cash is None or cash < cost:
                    self.wait_cost = cost
                    return "wait"
                if self.g.upgrade(p, path):
                    if self.account and p.kind != "hero":
                        self.account.note_bought(p.kind, path, p.tiers[path - 1])
                    return "progress" if self._next_path(p, target) else "bought"
                self._upgrade_failed(p, path, cash)
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
            targets = self._resolve_targets(step)
            if any(not self._reachable(p) for p in targets):
                return "wait"         # under a closed pane: its round comes
            for p in targets:
                self.g.sell(p)
            return "bought"
        return "skip"

    def _try_place(self, step, cash):
        """One attempt at a `place` step (see try_step for the results)."""
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
        key = self._step_key(step)
        if key in self.dead_steps or time.time() < self.retry_at.get(key, 0):
            return "skip"  # no spot was accepted (this game / the hero, for a few seconds)
        price = self.g.price(kind)
        if cash is None or cash < price:
            self.wait_cost = price
            return "wait"
        if self.hold_fails.get(kind, 0) >= 6:
            return "skip"  # cannot pick it up (locked / mode-restricted / unbound)
        if kind in self.BUFFERS and not self._damage_towers():
            return self._defer(step, key, self.BUFFER_RETRY_S)   # nothing to buff yet
        spots = self._spots_widening(kind, step)
        if not spots:
            return self._out_of_spots(step, key)
        fracs = [self.m.cell_to_frac(cx, cy) for cx, cy, _ in spots]
        tid = step.get("id") or self._new_tid(kind)
        placed = self.g.place(tid, kind, *fracs[0], more_spots=fracs[1:])
        self._note_refused(kind, key, spots, fracs)
        if placed:
            p = self.g.towers[tid]
            self._learn_probe(kind, p)
            self.purchased += 1
            self.hold_fails.pop(kind, None)
            # refusals count in a row: a fill or panic step that keeps finding
            # spots between refusals must not be given up
            self.step_spot_fails.pop(key, None)
            self._block(*self.m.frac_to_cell(p.x, p.y), 3)
            if step.get("target"):
                self.g.target(p, step["target"])
            return "bought"
        reason = self.g.fail_reason
        if reason == "hold":
            self.hold_fails[kind] = self.hold_fails.get(kind, 0) + 1
        elif reason in ("spot", "click") and self.step_spot_fails.get(key, 0) >= self.SPOT_LIMIT:
            return self._out_of_spots(step, key)
        elif reason == "unverified":
            self._avoid_unverified(kind)
        return "wait"

    def _note_refused(self, kind, key, spots, fracs):
        """Learn every spot the last Game.place call found refused: never
        again in this game (failed_spots, blocked) nor on this map (refused
        layer), and count it against the step."""
        for spot in getattr(self.g, "refused_spots", None) or ():
            if spot not in fracs:
                continue
            cx, cy, _ = spots[fracs.index(spot)]
            self.failed_spots.add((kind, cx, cy))
            self._block(cx, cy, 2)
            self._learn_blocked(kind, cx, cy)
            self.step_spot_fails[key] = self.step_spot_fails.get(key, 0) + 1

    # A support tower placed "near" others (an alchemist next to the ninja it
    # buffs) may find no free cell inside near_radius; then the radius grows
    # by these factors, and finally the step is placed by its role alone.
    # (Lost Crevasse Hard: the alchemist and the village were given up at
    # once - "after 0 refused spots" - and the game was played without them.)
    NEAR_WIDENING = (1.5, 2.2)

    AT_SEARCH_CELLS = 6   # an `at` spot taken (or refused) moves to the nearest legal cell this close

    # A damage tower must reach at least this share of the track that the
    # best legal spot for it on this map reaches - its range (the grey circle
    # while placing) has to cover the route, not graze it. The owner, of
    # Water Park: "some of these tack shooters barely even touch the route".
    MIN_REACH_SHARE = 0.45
    # Placed damage towers reaching less than this share are sold (outside
    # no-sell modes, never while lives fall): their cash goes into towers
    # that pop bloons.
    SELL_REACH_SHARE = 0.25

    BUFFERS = ("village", "alchemist")   # towers whose value is the towers around them

    def _damage_towers(self):
        return [p for p in self.g.towers.values()
                if p.kind != "hero" and p.kind not in self.BUFFERS and p.kind != "farm"]

    def _buffed(self, kind, cx, cy):
        """How many damage towers a `kind` buffer at cell (cx, cy) has in range."""
        r2 = self._range_cells(kind) ** 2
        n = 0
        for p in self._damage_towers():
            tx, ty = self.m.frac_to_cell(p.x, p.y)
            n += (tx - cx) ** 2 + (ty - cy) ** 2 <= r2
        return n

    def _buff_spots(self, kind):
        """Legal cells where a buffer reaches the most damage towers (at least
        one), best first; [] when no damage tower stands yet."""
        from . import placement as PL
        if not self._damage_towers():
            return []
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        valid = PL.valid_spots(self.m, kind, None, placed, where={"land"} if self.land_only else None,
                               now_round=self._pane_round())
        if valid is None:
            return []
        ys, xs = np.nonzero(valid & ~self.blocked)
        scored = sorted(((self._buffed(kind, x, y), x, y) for x, y in zip(xs.tolist(), ys.tolist())
                         if (kind, x, y) not in self.failed_spots), reverse=True)
        out = []
        for n, x, y in scored:
            if n < 1:
                break
            if any((x - ox) ** 2 + (y - oy) ** 2 < 9 for ox, oy, _ in out):
                continue
            out.append((x, y, float(n)))
            if len(out) >= self.SPOTS_PER_HOLD:
                break
        return out

    PROBE_GAIN = 1.2       # probe a blocked spot only if it reaches this much more track
    POP_GRACE_ROUNDS = 6   # rounds a damage tower may stand without a single pop
    BUFFER_RETRY_S = 20.0  # a village/alchemist with nothing to buff yet waits this long

    def _probe_spot(self, kind, valid):
        """One cell the map file marks blocked but whose range would reach
        PROBE_GAIN times more track than any legal spot (Water Park's
        top-left pink circle, inside the slide's loop): tried first while
        the tower is held. A refusal is learned like any refused spot (never
        probed again), an acceptance too (_learn_probe). None when nothing
        is worth it."""
        if kind == "hero" or valid is None or not valid.any():
            return None
        reach = self._reach(kind)
        if reach is None:
            return None
        probed = self.__dict__.setdefault("_probed", set())
        if any(k == kind for k, _, _ in probed):
            return None            # one probe per tower kind and game
        cnt = getattr(self.m, "t_cnt", None)
        on_track = (cnt > 0) if isinstance(cnt, np.ndarray) else np.zeros(valid.shape, bool)
        surface = "water" if T.TOWERS.get(kind, {}).get("placement") == "water" else "land"
        refused_mask = getattr(self.m, "refused_mask", None)
        refused = refused_mask(surface) if refused_mask else np.zeros(valid.shape, bool)
        best_legal = float(reach[valid].max())
        cand = ~valid & ~on_track & ~refused & ~self.blocked & (reach > self.PROBE_GAIN * best_legal)
        ys, xs = np.nonzero(cand)
        for i in np.argsort(-reach[ys, xs])[:50]:
            cx, cy = int(xs[i]), int(ys[i])
            if (kind, cx, cy) in self.failed_spots:
                continue
            probed.add((kind, cx, cy))
            log.info("%s: probing a spot the map file marks blocked (reaches %.0f track cells, "
                     "the best legal one %.0f)", kind, reach[cy, cx], best_legal)
            return (cx, cy, 2e9)
        return None

    def _learn_probe(self, kind, p):
        """The tower stands where a probe was tried: the game accepts that
        spot, so it is legal on this map from now on (MapModel.accept)."""
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
        probed = self.__dict__.get("_probed", set())
        hit = any(k == kind and abs(x - cx) <= 1 and abs(y - cy) <= 1 for k, x, y in probed)
        if hit and hasattr(self.m, "accept"):
            surface = "water" if T.TOWERS.get(kind, {}).get("placement") == "water" else "land"
            self.m.accept(surface, cx, cy)
            log.warning("learned: the game accepts %s at a spot the map file marks blocked (%d,%d)",
                        kind, cx, cy)

    def _reach(self, kind):
        """Grid: how many track cells a `kind` tower centred on each cell has
        in range (computed once per kind and game)."""
        cache = self.__dict__.setdefault("_reach_cache", {})
        if kind not in cache:
            import cv2
            cnt = getattr(self.m, "t_cnt", None)
            track = (cnt > 0).astype(np.float32) if isinstance(cnt, np.ndarray) else None
            if track is None:
                cache[kind] = None
            else:
                r = max(1, int(round(min(self._range_cells(kind), 60))))
                disc = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
                cv2.circle(disc, (r, r), r, 1.0, -1)
                cache[kind] = cv2.filter2D(track, -1, disc, borderType=cv2.BORDER_CONSTANT)
        return cache[kind]

    def _reach_floor(self, kind, valid):
        """The least track a `kind` tower must reach here, or None when it
        does not apply (global range, no track or no legal ground known)."""
        if kind == "hero" or T.TOWERS.get(kind, {}).get("range") is None:
            return None
        reach = self._reach(kind)
        if reach is None or valid is None or not valid.any():
            return None
        best = float(reach[valid].max())
        return self.MIN_REACH_SHARE * best if best > 0 else None

    def sell_useless(self, rnd, lives_dropped=False):
        """Sell one placed damage tower whose range reaches almost no track
        (less than SELL_REACH_SHARE of the best legal spot's reach). Not in
        no-sell modes (CHIMPS), not while lives are falling, never the last
        real tower. Returns True when one was sold."""
        if self.no_sell or lives_dropped or getattr(self, "_sold_round", None) == rnd:
            return False
        from . import placement as PL
        towers = [p for p in self.g.towers.values() if p.kind != "hero"]
        if len(towers) <= 1:
            return False
        for p in towers:
            if not hasattr(p, "placed_round"):
                p.placed_round = rnd
        # 1. a damage tower that popped NOTHING in POP_GRACE_ROUNDS: the map's
        #    reading of the route there is wrong (Water Park: a tack "below the
        #    slide", where the map file put the second route)
        for p in towers:
            if p.kind in self.BUFFERS or p.kind in ("farm", "spike"):
                continue
            if rnd - p.placed_round < self.POP_GRACE_ROUNDS or getattr(p, "pops", 0) > 0:
                continue                    # too new to judge, or proven to pop: no more clicks
            if getattr(p, "pops_round", -1) < rnd - 2:
                if self.g.select(p):        # its panel shows the pop count (Game._read_pops)
                    self.g.deselect(p)
                    p.pops_round = rnd
                    # two reads of 0, rounds apart, before a sale: one misread is not proof
                    p.zero_reads = getattr(p, "zero_reads", 0) + 1 if getattr(p, "pops", None) == 0 else 0
                break                       # one panel read per round at most
            if getattr(p, "zero_reads", 0) >= 2:
                log.warning("selling %s (%s): not a single pop in %d rounds", p.tid, p.kind,
                            rnd - p.placed_round)
                self._sold_round = rnd
                return bool(self.g.sell(p))
        # 2. a buffer with no damage tower in its radius;
        # 3. a damage tower whose range barely reaches the track
        for p in towers:
            if p.kind in self.BUFFERS:
                cx, cy = self.m.frac_to_cell(p.x, p.y)
                if len(self._damage_towers()) >= 2 and self._buffed(p.kind, cx, cy) == 0:
                    log.warning("selling %s (%s): no tower in its radius to buff", p.tid, p.kind)
                    self._sold_round = rnd
                    return bool(self.g.sell(p))
                continue
            if p.kind in ("farm", "spike") or T.TOWERS.get(p.kind, {}).get("range") is None:
                continue   # income, exit and global-range towers stay
            reach = self._reach(p.kind)
            valid = PL.valid_spots(self.m, p.kind)
            if reach is None or valid is None or not valid.any():
                continue
            best = float(reach[valid].max())
            cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
            if best > 0 and reach[cy, cx] < self.SELL_REACH_SHARE * best:
                log.warning("selling %s (%s): its range reaches %.0f track cells, the best spot "
                            "reaches %.0f", p.tid, p.kind, reach[cy, cx], best)
                self._sold_round = rnd
                return bool(self.g.sell(p))
        return False

    def _exact_spot(self, step, valid):
        """The cell of a step's exact spot (`at: [fx, fy]`, from a map's own
        build), or the nearest legal cell within AT_SEARCH_CELLS when it is
        taken or was refused; None when there is no `at` or nothing close."""
        at = step.get("at")
        if not at or len(at) != 2:
            return None
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(float(at[0]), float(at[1])))
        h, w = self.blocked.shape
        best = None
        for dy in range(-self.AT_SEARCH_CELLS, self.AT_SEARCH_CELLS + 1):
            for dx in range(-self.AT_SEARCH_CELLS, self.AT_SEARCH_CELLS + 1):
                x, y = cx + dx, cy + dy
                if not (0 <= x < w and 0 <= y < h) or self.blocked[y, x]:
                    continue
                if valid is not None and not valid[y, x]:
                    continue
                if (step.get("kind"), x, y) in self.failed_spots:
                    continue
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, x, y)
        return None if best is None else (best[1], best[2], 1e9)

    def _edge_band(self):
        """Cells within EDGE_CELLS of the bloon path's line (computed once per
        game), or None when the track is not known."""
        if not hasattr(self, "_edge"):
            import cv2
            cnt = getattr(self.m, "t_cnt", None)   # test models may have no track grids
            track = (cnt > 0).astype(np.uint8) if isinstance(cnt, np.ndarray) else None
            if track is None or not track.any():
                self._edge = None
            else:
                dist = cv2.distanceTransform(1 - track, cv2.DIST_L2, 3)
                self._edge = (dist > 0) & (dist <= self.EDGE_CELLS)
        return self._edge

    def _spots_widening(self, kind, step):
        """Candidate spots for a place step. A step that finds none is
        relaxed in stages before it may be given up, because a damage tower
        not placed is cash left idle while bloons leak (Covered Garden Hard:
        $49,876 unspent at round 75, steps "given up after 0 refused spots"):
          1. a `near` search widens (x1.5, x2.2), then drops `near`;
          2. the progress `segment` is dropped (any part of the track);
          3. a support/far step is tried as a damage tower would be;
          4. a global-range tower (sniper, mortar, ...) takes any legal spot.
        A buffer (village, alchemist) never relaxes into a spot chosen by
        role alone: it goes next to the most damage towers (_buff_spots).
        Each relaxation that finds spots is logged; a real dead end logs how
        much legal ground there was, so the cause shows in the log."""
        if kind in self.BUFFERS and not any(i in self.g.towers for i in step.get("near") or ()):
            # none of the towers it was meant to buff stands (Water Park: a
            # lone village buffing nothing)
            return self._buff_spots(kind)
        spots = self.pick_spots(kind, step, n=self.SPOTS_PER_HOLD)
        if spots:
            return spots
        label = step.get("id", kind)
        tries = []
        if step.get("near"):
            radius = step.get("near_radius", 9)   # pick_spots' default
            for factor in self.NEAR_WIDENING:
                tries.append((dict(step, near_radius=radius * factor),
                              f"no spot within {radius:g} of {step['near']} - using radius {radius * factor:g}"))
            step = {k: v for k, v in step.items() if k not in ("near", "near_radius")}
            if kind not in self.BUFFERS:
                tries.append((step, f"no spot near the towers it supports - placing by role only"))
        if "segment" in step:
            step = {k: v for k, v in step.items() if k != "segment"}
            tries.append((step, "no spot covering its part of the track - any part of the track"))
        buffer = kind in self.BUFFERS
        if step.get("role") in ("support", "far") and kind != "hero" and not buffer:
            step = dict(step, role="dps")
            tries.append((step, "no support spot - placing it where it covers track"))
        for relaxed, why in tries:
            spots = self.pick_spots(kind, relaxed, n=self.SPOTS_PER_HOLD)
            if spots:
                log.info("%s: %s", label, why)
                return spots
        if buffer:
            # a village/alchemist buffs the towers in its radius: next to the
            # most damage towers, never on its own (a lone village buffed
            # nothing on Water Park)
            spots = self._buff_spots(kind)
            if spots:
                log.info("%s: placed where it buffs the most towers", label)
            return spots
        spots = self._any_legal_spot(kind)
        if spots:
            log.info("%s: no spot reaches the track - global range, any legal spot", label)
        return spots

    def _any_legal_spot(self, kind):
        """For a tower with global range (range None: sniper, mortar, heli,
        ace, dartling), any legal cell will do. [] for other towers, and logs
        how much legal ground there was (the diagnosis of a dead end)."""
        from . import placement as PL
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        valid = PL.valid_spots(self.m, kind, self.g.hero if kind == "hero" else None, placed,
                               where={"land"} if self.land_only else None,
                               last_round=self.rules.get("end_round"), now_round=self._pane_round())
        if valid is None:
            return []
        legal = int(valid.sum())
        if kind == "hero" or T.TOWERS.get(kind, {}).get("range", 0) is not None:
            log.info("%s: no spot found (%d legal cells, none in reach of the track)", kind, legal)
            return []
        ys, xs = np.nonzero(valid)
        out = []
        for cx, cy in zip(xs.tolist(), ys.tolist()):
            if (kind, cx, cy) in self.failed_spots or self.blocked[cy, cx]:
                continue
            if any((cx - ox) ** 2 + (cy - oy) ** 2 < 9 for ox, oy, _ in out):
                continue
            out.append((cx, cy, 1.0))
            if len(out) >= self.SPOTS_PER_HOLD:
                break
        if not out:
            log.info("%s: no legal spot left (%d legal cells, all tried)", kind, legal)
        return out

    def _out_of_spots(self, step, key):
        """No spot was accepted for this step: SPOT_LIMIT refusals in a row,
        or no candidate left at all. Returns 'skip'.

        The hero is never given up (it was skipped for whole games after 4
        refusals on Tree Stump): it goes to the deferred list that tick()
        works through and is tried again at the next-best spots after a
        pause. Each later try is a single pick-up (SPOTS_PER_HOLD spots) and
        the pause doubles, so a hero the map keeps refusing costs little.
        Any other step is given up for the rest of this game, once: a fill or
        panic step is re-run every tick and used to re-probe forever (516
        refused-spot probes of ~1.45 s in one log, 8 of them per panic while
        lives fell to 12 on Luminous Cove)."""
        if step.get("kind") == "hero":
            self.hero_misses += 1
            pause = min(self.HERO_RETRY_MAX_S, self.HERO_RETRY_S * 2 ** (self.hero_misses - 1))
            self.step_spot_fails[key] = self.SPOT_LIMIT - self.SPOTS_PER_HOLD
            self.retry_at[key] = time.time() + pause
            if all(self._step_key(s) != key for s in self.deferred):
                self.deferred.append(step)
            log.warning("no spot accepted for the hero yet - trying again in %.0f s", pause)
            return "skip"
        if key not in self.dead_steps:
            self.dead_steps.add(key)
            log.warning("giving up on step %s for this game after %d refused spots",
                        step, self.step_spot_fails.get(key, 0))
        return "skip"

    def _defer(self, step, key, pause):
        """Put a place step aside for `pause` seconds; tick() tries it again
        from the deferred list. Returns 'skip' so the plan moves on."""
        self.retry_at[key] = time.time() + pause
        if all(self._step_key(s) != key for s in self.deferred):
            self.deferred.append(step)
        return "skip"

    def _avoid_unverified(self, kind):
        """Game.place released the hold but no tower showed up ('unverified'):
        the spot may be bad, or the purchase silently failed. Avoid that spot
        for this game only; it is not learned for the map."""
        spot = getattr(self.g, "last_spot", None)
        if spot:
            cx, cy = self.m.frac_to_cell(*spot)
            self.failed_spots.add((kind, cx, cy))
            self._block(cx, cy, 2)

    def _upgrade_failed(self, p, path, cash):
        """Book-keeping after Game.upgrade said no (see its fail_reason)."""
        reason = self.g.fail_reason
        price = getattr(self.g, "last_price", None)
        if reason == "xp":
            # locked behind tower XP we do not have (yet)
            self.capped.add((p.tid, path))
            if self.account and self.g.locked_seen:
                self.account.note_locked(*self.g.locked_seen)
        elif reason == "capped":
            self.capped.add((p.tid, path))   # the panel shows the path closed or maxed
        elif reason == "unread":
            # no price on a path its tiers allow: likelier a misread - another
            # look in a while (three blank looks close it, Game._path_closed)
            self.unread_until[(p.tid, path)] = time.time() + UNREAD_RETRY_S
        elif reason == "drift":
            pass   # tiers corrected from the panel prices: the next tick re-plans
        elif reason == "cash" and price and cash is not None and price > cash:
            # the panel asks more than the price table: save up for that price
            # instead of opening the panel again on every tick
            self.panel_price[(p.tid, path, p.tiers[path - 1] + 1)] = price
            self.wait_cost = price
        elif reason == "select":
            self._forget_if_missing(p)
        else:
            self.upgrade_fails[(p.tid, path)] = self.upgrade_fails.get((p.tid, path), 0) + 1
            if self.upgrade_fails[(p.tid, path)] >= 4:
                self.capped.add((p.tid, path))  # give up on it this game only

    def _forget_if_missing(self, p):
        """Selecting p failed. MAX_SELECT_FAILS failures in a row mean it is
        not on the map (a purchase the game never made: on Ancient Portal a
        phantom ninja failed 8 selections of ~3 s each). Forget it, so that
        defended() stops counting it and a plan tower gets placed again.
        `purchased` keeps counting it: if it does exist after all, a tower
        cap must still include it. Returns True when it was forgotten."""
        if p.kind == "hero" or getattr(p, "select_fails", 0) < self.MAX_SELECT_FAILS:
            return False
        self.g.towers.pop(p.tid, None)
        log.warning("%s (%s) could not be selected %d times in a row - not on the map; forgotten",
                    p.tid, p.kind, p.select_fails)
        step = next((s for s in self.plan[:self.idx]
                     if s.get("do") == "place" and s.get("id") == p.tid), None)
        if step is not None:
            self.plan.insert(self.idx, dict(step))   # placed again before its upgrades
        return True

    def _recheck_doubtful(self):
        """When no verified tower is left (defended() False) but one of them is
        only doubtful (its last selection failed), select it again: it either
        shows up (verified again) or, failing twice, is forgotten. Rounds do
        not start while defended() is False, so this must not wait."""
        if self.defended():
            return
        for p in list(self.g.towers.values()):
            if p.kind != "hero" and not getattr(p, "verified", True):
                if self.g.select(p):
                    self.g.deselect(p)
                else:
                    self._forget_if_missing(p)
                return

    # -- threat calendar ---------------------------------------------------------
    # Two kinds of threat are checked ahead of the round they arrive in.
    #
    #  * Property threats (threats.py): bloons the defence cannot pop AT ALL -
    #    camo, lead, purple, zebra, camo lead, DDT ... Each is a signature (the
    #    immunities ONE attack has to get past). Their rounds come from the
    #    game's own round set for this mode, and every round they appear in
    #    counts, not only the first: a camo tower that never got placed matters
    #    again at the next camo round. Buying starts early enough to afford the
    #    cheapest answer from the income of the rounds in between.
    #  * Strength threats (THREATS / ANSWERS above): ceramic rounds, MOAB-class
    #    rounds, the R63 rush, strong camo - a tower of the right tier must
    #    stand - plus a rough blimp-damage ramp check (threats.blimp_capacity).

    MIN_LEAD = 3             # rounds ahead a property answer is bought at the latest
    MIN_LEAD_ONE_LIFE = 5    # Impoppable/CHIMPS: one leak loses, so start earlier
    MAX_LEAD = 10            # never hold the plan for a threat further away than this
    LEAD_MARGIN = 1.25       # count on only 80 % of the income still to come
    PLAN_FIRST_FACTOR = 1.5  # follow the plan when it covers the threat for <= 1.5x ...
    PLAN_FIRST_SLACK = 300   # ... (or <= $300 more than) the cheapest answer
    HOLD_MAX_S = 30.0        # longest wait between rounds to buy an affordable answer
    RAMP_OK = 1.0            # blimp damage in reach / blimp HP a round brings
    RAMP_PANIC = 0.4         # below this, the round before, buy blimp damage even mid-plan
    DEFAULT_TRACK = 600.0    # world units of track when the map geometry is unknown

    def _init_threats(self):
        """Set up the threat checks (on first use, so that every Executor gets
        them however it was built)."""
        self.round_set = TH.set_for_mode(self.mode)
        self.window = (self.rules.get("start_round", 1), self.rules.get("end_round", 80))
        self.calendar = TH.calendar(self.round_set, *self.window) if TH.available() else {}
        self.latched = {}      # threat -> round it is being answered for (stays due until covered)
        self.noted = set()     # what was already logged, so that each line appears once
        self.opt_cache = {}    # answer options per (threat, towers on the map)
        self.hold_since = {}   # round -> when Play was first held for it
        self.cash_seen = 0
        self.targets, self.kind_targets = self._upgrade_targets(self.strat)
        self.track_len = None
        # income the threat calendar plans with (Double Cash and farms left out)
        self.income_mult = 0.0 if self.rules.get("income") is False else (
            0.5 if self.rules.get("half_cash") else 1.0)

    @staticmethod
    def _upgrade_targets(strat):
        """({tower id: tiers}, {kind: tiers}) every upgrade step of the strategy
        aims at (plan, answers, fill, panic), so that an answer never takes a
        tower off the path its plan still needs."""
        by_id, by_kind = {}, {}
        for _, st in _all_steps(strat):
            if st.get("do") != "upgrade" or not st.get("to"):
                continue
            try:
                want = parse_cross(st["to"])
            except ValueError:
                continue
            key, table = (st["id"], by_id) if st.get("id") else (st.get("kind"), by_kind)
            if key is not None:
                table[key] = [max(a, b) for a, b in zip(table.get(key, [0, 0, 0]), want)]
        return by_id, by_kind

    def _towers(self):
        """The real towers on the map (a hero is never counted as an answer:
        what it can pop changes with its level)."""
        return [p for p in self.g.towers.values() if p.kind != "hero"]

    def _near_ids(self):
        """The (up to) three biggest damage towers: where a new village goes."""
        main = sorted((p for p in self._towers() if p.kind not in ("village", "farm")),
                      key=lambda p: -getattr(p, "spent", 0))
        return [p.tid for p in main[:3]]

    def _range_fn(self):
        """in_range(aura_tid, tid) for threats.covers: is tower `tid` inside the
        range of support tower `aura_tid`? Positions are read once per call
        of this method (the option search asks this question many times).

        '__new__' is a tower not bought yet: a new village is placed next to
        the biggest towers (_near_ids); a new damage tower is placed by track
        coverage, so it is not assumed to stand in any village's range."""
        towers = self._towers()
        near = set(self._near_ids())
        pos = {p.tid: self.m.frac_to_cell(p.x, p.y) for p in towers}
        reach = {p.tid: self._range_cells(p.kind) + 2 for p in towers}   # + about a footprint

        def in_range(aura_tid, tid):
            if aura_tid == "__new__":
                return tid in near
            if tid == "__new__" or aura_tid not in pos or tid not in pos:
                return False
            (ax, ay), (bx, by) = pos[aura_tid], pos[tid]
            return (ax - bx) ** 2 + (ay - by) ** 2 <= reach[aura_tid] ** 2
        return in_range

    def _in_range(self, aura_tid, tid):
        """See _range_fn (one-off question)."""
        return self._range_fn()(aura_tid, tid)

    def _covers(self, sig, poppers=None):
        """threats.covers for the towers on the map: (ok, how / what is missing)."""
        return TH.covers(self._towers(), sig, self._range_fn(), poppers)

    def has_answer(self, threat):
        """Does the defence on the map answer this threat?"""
        sig = TH.sig_from_name(threat) if TH.available() else None
        if sig is not None:
            if not self._covers(sig)[0]:
                return False          # nothing on the map can pop it at all
            if threat == "ddt":
                return self._strong_ddt()
            if threat not in STRONG_CAMO:
                return True           # the exact property check beats the tier tables
        if threat in STRONG_CAMO:
            return strong_camo((p.kind, p.tiers) for p in self._towers())
        if threat in NEEDS_CAMO and not self.has_answer("camo"):
            return False  # DDTs are camo: the blimp popper must be able to see them
        for p in self._towers():
            for kind, path, tier in ANSWERS.get(threat, []):
                if p.kind == kind and (path == 0 or p.tiers[path - 1] >= tier):
                    return True
        return False

    def _strong_ddt(self):
        """A DDT-tier tower (ANSWERS['ddt']) that can itself hurt DDTs: it gets at
        camo (own detection, a radar village, a decamo) AND one of its attacks
        gets past lead and black at once. A MOAB Assassin cannot (explosions),
        nor can a Maim MOAB sniper without Night Vision Goggles."""
        sig = TH.sig_from_name("ddt")
        for p in self._towers():
            strong = any(p.kind == k and (path == 0 or p.tiers[path - 1] >= tier)
                         for k, path, tier in ANSWERS["ddt"])
            if strong and self._covers(sig, poppers={p.tid})[0]:
                return True
        return False

    def due_threats(self, rnd, lookahead=4):
        """Threats to act on now, most urgent first: property threats (see
        _property_due), then strength threats from the older calendar that
        have no answer on the map yet."""
        if rnd is None or self.no_answers:
            return []
        if not hasattr(self, "calendar"):
            self._init_threats()
        due = [need for _, need in self._property_due(rnd)]
        start = self.rules.get("start_round", 1)
        if self.rules.get("one_life"):
            lookahead = max(lookahead, 6)  # one leak = defeat: build answers early
        shift = self.rules.get("threat_shift", {})
        for r, threat in sorted((shift.get(t, r), t) for r, t in THREATS):
            if threat in due or threat in self.unanswerable:
                continue
            if self.calendar and threat != "ddt" and threat not in STRONG_CAMO \
                    and TH.sig_from_name(threat) is not None:
                continue  # camo, lead, purple: property threats, timed from the round set above
            if r > self.rules.get("end_round", 80):
                continue  # arrives after the game's last round (rush 63 in a 60-round Medium game)
            # threats that began before our first round are present from the start
            r = max(r, start)
            # past r+1 it is no longer "early"; stop holding the plan hostage
            if r - lookahead <= rnd <= r + 1 and not self.has_answer(threat):
                due.append(threat)
        return due

    def due_threat(self, rnd, lookahead=4):
        """First upcoming threat with no answer built yet (None if there is none)."""
        due = self.due_threats(rnd, lookahead)
        return due[0] if due else None

    def _property_due(self, rnd):
        """[(round, threat)] property threats to act on now: the next round that
        brings the signature is within its lead time and nothing on the map
        pops it. A threat that became due stays due until it is covered, so
        the cash saved for it is not spent elsewhere. Logs (once) when a
        threat in range is covered, and when it gets answered."""
        out = []
        for need, rounds in self.calendar.items():
            if need in self.unanswerable:
                continue
            nxt = next((r for r in rounds if r >= rnd), None)
            held = self.latched.get(need)
            if held is not None:
                nxt = held if held >= rnd else nxt
            if nxt is None or nxt - rnd > self.MAX_LEAD:
                continue
            sig = TH.sig_from_name(need)
            ok, how = self._covers(sig)
            if ok:
                self._note(need, nxt, f"covered by {how}", answered=held is not None)
                self.latched.pop(need, None)
                continue
            if held is None and rnd < nxt - self._lead_rounds(need, sig, nxt, rnd):
                continue
            if held is None:
                self.latched[need] = nxt
                opts = self._options(need, sig)
                plan = (f"cheapest answer {opts[0]['desc']} (${opts[0]['cost']})" if opts
                        else "NO allowed tower can answer it")
                log.warning("threat %s arrives round %d and the defence cannot pop it (%s) - %s",
                            need, nxt, how, plan)
            out.append((nxt, need))
        return sorted(out)

    def _note(self, need, rnd, text, answered=False):
        """Log a threat's coverage: once per game, and again when it was answered."""
        if answered:
            log.warning("threat %s (round %d): answered - %s", need, rnd, text)
        elif need not in self.noted:
            log.info("threat %s (round %d): %s", need, rnd, text)
        self.noted.add(need)

    def _lead_rounds(self, need, sig, due_round, rnd):
        """Rounds before due_round to start answering: enough for the income of
        the rounds in between (with LEAD_MARGIN) to pay for the cheapest answer
        on top of the cash in hand; never fewer than MIN_LEAD."""
        least = self.MIN_LEAD_ONE_LIFE if self.rules.get("one_life") else self.MIN_LEAD
        opts = self._options(need, sig)
        short = (opts[0]["cost"] - self.cash_seen) if opts else 0
        if short <= 0:
            return least
        income, k = 0.0, 0
        for r in range(due_round - 1, max(rnd, self.window[0]) - 1, -1):
            income += TH.round_cash(self.round_set, r) * self.income_mult
            k += 1
            if income >= short * self.LEAD_MARGIN:
                break
        else:
            k = due_round - rnd      # not affordable in time even so: start now
        return min(self.MAX_LEAD, max(least, k))

    def _caps(self, kind, p=None):
        """Highest tier per path an answer may use: what the account has (or can
        unlock before the game), and for a placed tower no further on a path
        that turned out locked this game."""
        caps = [reachable_tier(self.account, kind, i) if self.account is not None else 5
                for i in range(3)]
        if p is not None:
            caps = [p.tiers[i] if (p.tid, i + 1) in self.capped else max(c, p.tiers[i])
                    for i, c in enumerate(caps)]
        return caps

    def _map_has_water(self):
        f = getattr(self.m, "has_water", None)
        try:
            return bool(f()) if f else False
        except Exception:      # a half-built model must not stop the game
            return False

    def _answer_kind_ok(self, kind):
        """May a NEW tower of this kind be bought as an answer?"""
        if kind in INCOME_TOWERS or not self.kind_allowed(kind):
            return False
        if self.account is not None and kind not in self.account.unlocked_towers:
            return False
        if self.hold_fails.get(kind, 0) >= 6:
            return False          # the hotkey would not pick it up this game
        if TH.tower_facts(kind).get("needs_aim"):
            return False          # Mortar/Dartling must be aimed; the bot does not aim
        if (T.TOWERS[kind].get("placement") or "land") == "water" and not self._map_has_water():
            return False
        return True

    def _new_tower_option(self, need, kind, cost, tiers):
        """An answer option that places a new tower and upgrades it."""
        tid = f"ans_{need.replace('+', '_')}_{kind}"
        place = {"do": "place", "id": tid, "kind": kind}
        if kind == "village":
            place.update(role="support", near=self._near_ids(), near_radius=8)
        else:
            place.update(role="dps", segment=[0.0, 0.7])
        cross = "-".join(map(str, tiers))
        steps = [place] + ([{"do": "upgrade", "id": tid, "to": cross}] if any(tiers) else [])
        return {"cost": cost, "desc": f"new {kind} {cross}", "steps": steps}

    def _options(self, need, sig):
        """Ways to cover a signature, cheapest first: [{cost, desc, steps}].

        1. upgrade a tower already on the map - never off its plan path, never
           past what the account has unlocked or what turned out locked;
        2. place a new tower the mode, the strategy's constraints, the tower
           caps and the account allow, at its cheapest covering crosspath.
        Towers that must be aimed (Mortar, Dartling) and water towers on a map
        without water are never bought as answers."""
        towers = self._towers()
        key = (need, tuple((p.tid, p.kind, tuple(p.tiers)) for p in towers), frozenset(self.capped))
        if key in self.opt_cache:
            return self.opt_cache[key]
        fam = PRICE_FAMILY.get(self.mode, "hard")
        in_range = self._range_fn()
        opts = []
        for p in towers:
            plan_t = self.targets.get(p.tid) or self.kind_targets.get(p.kind)
            others = [q for q in towers if q is not p]
            for t in TH.covering_crosspaths(p.kind, sig, others, self._caps(p.kind, p), p.tiers,
                                            in_range, tid=p.tid):
                if plan_t is not None and not TH.legal([max(a, b) for a, b in zip(t, plan_t)]):
                    continue      # the plan could not finish this tower any more
                if self.no_income and self._is_income(p.kind, list(t)):
                    continue
                cost = sum(T.upgrade_cost(p.kind, i + 1, k, fam)
                           for i in range(3) for k in range(p.tiers[i] + 1, t[i] + 1))
                cross = "-".join(map(str, t))
                opts.append({"cost": cost, "desc": f"upgrade {p.tid} to {cross}",
                             "steps": [{"do": "upgrade", "id": p.tid, "to": cross}]})
        if not self.at_tower_cap():
            for kind in T.TOWERS:
                if not self._answer_kind_ok(kind):
                    continue
                best = None
                for t in TH.covering_crosspaths(kind, sig, towers, self._caps(kind),
                                                in_range=in_range):
                    if self.no_income and self._is_income(kind, list(t)):
                        continue
                    cost = T.total_cost(kind, tuple(t), fam)
                    if best is None or cost < best[0]:
                        best = (cost, t)
                if best is not None:
                    opts.append(self._new_tower_option(need, kind, *best))
        opts.sort(key=lambda o: o["cost"])
        if len(self.opt_cache) > 64:
            self.opt_cache.clear()
        self.opt_cache[key] = opts
        return opts

    def _plan_cost_to_cover(self, sig, due_round, budget, steps=None):
        """What the plan's own next steps (or the given steps, e.g. a strategy
        answer) cost up to the one after which the defence covers sig - or
        None if that is more than `budget` or comes after a `round:` gate at or
        past due_round. Towers the steps place are taken to stand where the
        steps put them (villages near what they serve)."""
        fam = PRICE_FAMILY.get(self.mode, "hard")
        sim = {p.tid: (p.kind, list(p.tiers)) for p in self._towers()}
        cost, n = 0, 0
        for st in (self.plan[self.idx:] if steps is None else steps):
            if st.get("round") and st["round"] >= due_round:
                break                       # the plan waits past the threat
            do, kind = st.get("do"), st.get("kind")
            if do == "place" and kind not in (None, "hero") and self.kind_allowed(kind):
                tid = st.get("id") or f"__plan{n}"
                n += 1
                if tid not in sim:
                    sim[tid] = (kind, [0, 0, 0])
                    cost += T.tower_cost(kind, fam)
            elif do == "upgrade" and st.get("to"):
                try:
                    want = parse_cross(st["to"])
                except ValueError:
                    continue
                ids = [st["id"]] if st.get("id") in sim else \
                    [t for t, (k, _) in sim.items() if k == kind and not st.get("id")]
                for tid in ids:
                    k, have = sim[tid]
                    new = [max(h, min(w, c)) for h, w, c in zip(have, want, self._caps(k))]
                    cost += sum(T.upgrade_cost(k, i + 1, t, fam)
                                for i in range(3) for t in range(have[i] + 1, new[i] + 1))
                    sim[tid] = (k, new)
            else:
                continue
            if cost > budget:
                return None
            if TH.covers([(t, k, tuple(v)) for t, (k, v) in sim.items()], sig)[0]:
                return cost
        return None

    def answer_threat(self, threat, cash, rnd):
        """Buy toward the answer of one due threat. Returns 'bought', 'wait'
        (saving for it), 'plan' (the plan's own next steps cover it in time:
        carry on with the plan) or 'none' (nothing applicable).

        A property gap (nothing on the map can pop it) goes to _answer_gap.
        A strength threat runs the strategy's own `answers:` for it, or
        _generic_answer when the strategy has none."""
        if not hasattr(self, "calendar"):
            self._init_threats()
        sig = TH.sig_from_name(threat) if TH.available() else None
        if sig is not None and not self._covers(sig)[0]:
            return self._answer_gap(threat, sig, cash, rnd)
        steps = (self.strat.get("answers") or {}).get(threat)
        if steps is None:
            steps = self._generic_answer(threat)
        return self._run_answer(threat, steps, cash, rnd)

    def _run_answer(self, threat, steps, cash, rnd):
        """Try answer steps in order: 'bought', 'wait' or 'none'."""
        for st in steps or ():
            if not self._step_allowed(st):
                continue
            r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("threat %s: bought toward answer %s", threat, st)
                return "bought"
            if r == "wait":
                return "wait"
        return "none"

    def _answer_gap(self, threat, sig, cash, rnd):
        """Nothing on the map pops this signature. In this order:

        1. the plan's next steps, 2. the strategy's own `answers:` for it -
           each only if it covers the gap for little more than the cheapest
           option (PLAN_FIRST_FACTOR / _SLACK) while there is still a round to
           spare, or with the cash in hand right now;
        3. the cheapest option from _options.
        (A Flash Bomb ninja at $2,430 is a fine lead answer at R20 but not
        when R28's leads come in three rounds: then a $405 Bomb Shooter is.)"""
        due_round = self.latched.get(threat, rnd)
        opts = self._options(threat, sig)
        if not opts:
            log.error("threat %s (round %d): no tower this mode, the strategy's constraints and "
                      "the account allow can pop it", threat, due_round)
            return "none"
        cheapest = opts[0]["cost"]
        budget = max(cheapest * self.PLAN_FIRST_FACTOR, cheapest + self.PLAN_FIRST_SLACK)
        own = (self.strat.get("answers") or {}).get(threat)
        for source, steps in (("plan", None), ("answers", own)):
            if source == "answers" and not own:
                continue
            cost = self._plan_cost_to_cover(sig, due_round, max(budget, self.cash_seen), steps)
            if cost is None or not (cost <= self.cash_seen or (rnd < due_round - 1 and cost <= budget)):
                continue
            if (source, threat) not in self.noted:
                self.noted.add((source, threat))
                log.info("threat %s (round %d): the strategy's %s cover it ($%d; cheapest other "
                         "answer $%d)", threat, due_round,
                         "next plan steps" if source == "plan" else "own answer", cost, cheapest)
            if source == "plan":
                return "plan"
            r = self._run_answer(threat, own, cash, rnd)
            if r != "none":
                return r
        for opt in opts:
            st = opt["steps"][0]
            r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("threat %s (round %d): bought %s %s - cheapest answer: %s ($%d in all)",
                            threat, due_round, st["do"], st.get("kind") or st.get("id"),
                            opt["desc"], opt["cost"])
                return "bought"
            if r == "wait":
                self.wait_note = f"saving ${opt['cost']} for the {threat} answer ({opt['desc']})"
                return "wait"
        return "none"

    # -- blimp damage ramp ---------------------------------------------------------
    def _track_length(self):
        """Visible track length of this map in world units (from the game's map
        geometry; DEFAULT_TRACK when it is unknown)."""
        if self.track_len is None:
            length = None
            try:
                from . import mapgeom
                length = TH.track_length(mapgeom.load(self.m.name))
            except Exception as e:   # geometry is optional: never let it stop a game
                log.debug("no track length for %s: %s", getattr(self.m, "name", "?"), e)
            self.track_len = length or self.DEFAULT_TRACK
        return self.track_len

    @staticmethod
    def _range_units(kind):
        return float(T.TOWERS.get(kind, {}).get("range") or 40.0)

    TRACK_MASK_TTL_S = 30.0   # how long a computed track mask is reused

    def _reach_fn(self):
        """reach(tid, kind) -> world units of track inside a placed tower's range,
        from the map model's track cells; None for a tower not placed yet, or
        when the model has no usable track (then threats uses 2.5 x range)."""
        now = time.time()
        cached = getattr(self, "_mask_cache", None)
        if cached is None or now - cached[0] > self.TRACK_MASK_TTL_S:
            mask = None
            try:
                f = getattr(self.m, "track_mask", None)
                mask = f() if f else None
            except Exception:      # a half-learned model must not stop the game
                mask = None
            if mask is not None and int(mask.sum()) < 30:
                mask = None
            cached = self._mask_cache = (now, mask)
        mask = cached[1]
        if mask is None:
            return None
        total = float(mask.sum())
        ys, xs = np.nonzero(mask)
        per_cell = self._track_length() / total      # fraction of the track per cell

        def reach(tid, kind):
            p = self.g.towers.get(tid)
            if p is None or p.kind != kind:
                return None
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            r = self._range_cells(kind)
            return float(((xs - cx) ** 2 + (ys - cy) ** 2 <= r * r).sum()) * per_cell
        return reach

    def blimp_ratio(self, load, towers=None):
        """Blimp damage the defence deals in reach / blimp HP the round brings."""
        cap = TH.blimp_capacity(self._towers() if towers is None else towers, load,
                                self._track_length(), self._range_units, self._reach_fn())
        return cap / max(load["hp"], 1.0)

    def _ramp_due(self, rnd):
        """(round, load, ratio) for the next blimp round within MIN_LEAD rounds,
        or None. Logs the estimate once per blimp round."""
        if rnd is None or self.no_answers or not TH.available():
            return None
        for R in range(max(rnd, self.window[0]), min(rnd + self.MIN_LEAD, self.window[1]) + 1):
            load = TH.round_blimp_load(self.round_set, R, double_hp=bool(self.rules.get("tough_moabs")))
            if not load:
                continue
            ratio = self.blimp_ratio(load)
            if ("ramp", R) not in self.noted:
                self.noted.add(("ramp", R))
                log.info("blimp check round %d: %.0f blimp HP, %.0f units of track; the defence "
                         "deals about %.1fx that in reach%s", R, load["hp"], self._track_length(),
                         ratio, "" if ratio >= self.RAMP_OK else " - short")
            return R, load, ratio
        return None

    def _dps_options(self, load):
        """Blimp damage to buy, most damage per dollar first: a placed tower
        upgraded to a crosspath listed in counters.json blimp_dps (on its plan
        path), or a new tower at such a crosspath."""
        fam = PRICE_FAMILY.get(self.mode, "hard")
        track, rng, reach = self._track_length(), self._range_units, self._reach_fn()
        table = TH.counters().get("blimp_dps") or {}
        opts = []
        for p in self._towers():
            plan_t = self.targets.get(p.tid) or self.kind_targets.get(p.kind)
            caps = self._caps(p.kind, p)
            before = TH.blimp_capacity([p], load, track, rng, reach)
            for cross, _ in table.get(p.kind) or ():
                t = [max(a, b) for a, b in zip(p.tiers, TH._tiers(cross))]
                if t == list(p.tiers) or any(a > c for a, c in zip(t, caps)) or not TH.legal(t) or \
                        (plan_t is not None and not TH.legal([max(a, b) for a, b in zip(t, plan_t)])):
                    continue
                if self.no_income and self._is_income(p.kind, t):
                    continue
                gain = TH.blimp_capacity([(p.tid, p.kind, t)], load, track, rng, reach) - before
                if gain > 0:
                    cross = "-".join(map(str, t))
                    cost = sum(T.upgrade_cost(p.kind, i + 1, k, fam)
                               for i in range(3) for k in range(p.tiers[i] + 1, t[i] + 1))
                    opts.append({"gain": gain, "cost": cost, "desc": f"upgrade {p.tid} to {cross}",
                                 "steps": [{"do": "upgrade", "id": p.tid, "to": cross}]})
        if not self.at_tower_cap():
            for kind, entries in (TH.counters().get("blimp_dps") or {}).items():
                if kind not in T.TOWERS or not self._answer_kind_ok(kind):
                    continue
                caps = self._caps(kind)
                for cross, _ in entries:
                    t = TH._tiers(cross)
                    if any(a > c for a, c in zip(t, caps)) or (self.no_income and self._is_income(kind, list(t))):
                        continue
                    gain = TH.blimp_capacity([("__new__", kind, t)], load, track, rng)
                    if gain > 0:
                        opt = self._new_tower_option("blimps", kind, T.total_cost(kind, t, fam), t)
                        opt["gain"] = gain
                        opts.append(opt)
        opts.sort(key=lambda o: -o["gain"] / max(o["cost"], 1))
        return opts[:8]

    def _answer_ramp(self, R, load, ratio, cash, rnd):
        """More blimp damage for round R. The strategy's own answer for that
        round's biggest blimp class comes first; otherwise the plan carries on
        (it is the strategy's own ramp) - unless it is used up, or the round is
        next and the defence is far short (RAMP_PANIC): then the most blimp
        damage per dollar is bought."""
        cls = max((g["bloon"] for g in TH.round_groups(self.round_set, R)
                   if TH.bloons().get(g["bloon"], {}).get("class") == "blimp"),
                  key=TH.blimp_hp, default=None)
        for st in (self.strat.get("answers") or {}).get(cls) or ():
            if not self._step_allowed(st):
                continue
            r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d: bought toward answer %s", R, st)
                return "bought"
            if r == "wait":
                return "wait"
        if self.idx < len(self.plan) and not (rnd >= R - 1 and ratio < self.RAMP_PANIC):
            return "plan"
        # Only what can be paid before round R (cash now + the rounds in between),
        # and only buys that matter: the cheapest one closing the whole shortfall,
        # else the most damage per dollar among those adding at least a tenth of
        # it. If nothing fits, save for the cheapest that closes it.
        money = self.cash_seen + sum(TH.round_cash(self.round_set, r) * self.income_mult
                                     for r in range(rnd, R))
        short = (self.RAMP_OK - ratio) * load["hp"]
        opts = self._dps_options(load)
        closing = sorted((o for o in opts if o["gain"] >= short), key=lambda o: o["cost"])
        fits = [o for o in closing if o["cost"] <= money] or \
            [o for o in opts if o["cost"] <= money and o["gain"] >= 0.1 * short]
        for opt in fits or (closing or sorted(opts, key=lambda o: o["cost"]))[:1]:
            r = self.try_step(dict(opt["steps"][0]), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d (%.1fx): bought toward %s ($%d)", R, ratio,
                            opt["desc"], opt["cost"])
                return "bought"
            if r == "wait":
                return "wait"
        return "none"

    def _threat_tick(self, cash, rnd):
        """The threat part of tick(): True (bought), False (holding cash for an
        answer) or None (nothing to do: go on with the plan)."""
        if not hasattr(self, "calendar"):
            self._init_threats()
        self.cash_seen = cash
        # an answer due now beats every plan step
        for threat in self.due_threats(rnd):
            self.wait_note = None
            r = self.answer_threat(threat, cash, rnd)
            if r == "bought":
                return True
            if r == "wait":
                self.waiting = self.wait_note or f"saving for {threat} answer"
                self.saving_for_threat = True
                return False  # hold cash for the answer
            if r == "plan":
                continue      # the plan's own next steps cover it in time
            log.warning("threat %s: nothing applicable to buy - not holding the plan for it", threat)
            self.unanswerable.add(threat)  # nothing applicable; don't block the plan
        ramp = self._ramp_due(rnd)
        if ramp and ramp[2] < self.RAMP_OK:
            r = self._answer_ramp(*ramp, cash, rnd)
            if r == "bought":
                return True
            if r == "wait":
                self.waiting = f"saving for blimp damage before round {ramp[0]}"
                self.saving_for_threat = True
                return False
        return None

    # -- between rounds -------------------------------------------------------------
    def hold_round(self, rnd, cash):
        """Should Play wait? True while the coming round (rnd, or rnd + 1 if the
        HUD still shows the round just played) brings a bloon the defence
        cannot pop AND the first step of an answer is affordable now: tick()
        buys it before the round starts. At most HOLD_MAX_S per round, so a
        purchase that keeps failing can never stall the game."""
        if rnd is None or cash is None or self.no_answers or not TH.available():
            return False
        if not hasattr(self, "calendar"):
            self._init_threats()
        since = self.hold_since.get(rnd)
        if since is not None and time.time() - since > self.HOLD_MAX_S:
            return False
        for R in (rnd, rnd + 1):
            if not self.window[0] <= R <= self.window[1]:
                continue
            for sig in TH.round_signatures(self.round_set, R):
                need = TH.sig_name(sig)
                if need in self.unanswerable or self._covers(sig)[0]:
                    continue
                opts = self._options(need, sig)
                if opts and self._first_step_cost(opts[0]["steps"][0]) <= cash:
                    self.hold_since.setdefault(rnd, time.time())
                    self.waiting = f"holding round {R}: buying the {need} answer first"
                    return True
        return False

    def _first_step_cost(self, step):
        """Cash the first step of an answer needs (inf if it cannot be bought)."""
        if step.get("do") == "place":
            return self.g.price(step["kind"])
        p = self.g.towers.get(step.get("id"))
        nxt = self._next_path(p, parse_cross(step["to"])) if p is not None else None
        return nxt[1] if nxt else float("inf")

    def _generic_answer(self, threat):
        """Upgrade an existing tower (from its current tiers) toward a listed answer."""
        steps = []
        if threat in STRONG_CAMO:
            # a Radar Scanner village beside the main towers lets all of them see camo
            if self.kind_allowed("village"):
                village = next((p for p in self.g.towers.values() if p.kind == "village"), None)
                if village is None:
                    main = sorted((p for p in self.g.towers.values() if p.kind != "hero"),
                                  key=lambda p: -p.spent)[:3]
                    steps.append({"do": "place", "kind": "village", "role": "support",
                                  "near": [p.tid for p in main], "near_radius": 8})
                else:
                    to = list(village.tiers)
                    to[1] = max(to[1], 2)
                    if sum(t > 0 for t in to) <= 2 and sum(t > 2 for t in to) <= 1:
                        steps.append({"do": "upgrade", "id": village.tid, "to": "-".join(map(str, to))})
            threat = "camo"  # and/or upgrade camo towers to tier 3+
        for p in self.g.towers.values():
            for kind, path, tier in ANSWERS.get(threat, []):
                if p.kind != kind or not path:
                    continue
                to = list(p.tiers)
                to[path - 1] = max(to[path - 1], tier)
                if self.no_income and self._is_income(kind, to):
                    continue
                if threat == "ddt" and TH.available() and not TH.covers(
                        [q for q in self._towers() if q is not p] + [(p.tid, p.kind, tuple(to))],
                        TH.sig_from_name("ddt"), self._range_fn(), poppers={p.tid})[0]:
                    continue  # e.g. a MOAB Assassin: explosions cannot hurt DDTs
                if sum(t > 0 for t in to) <= 2 and sum(t > 2 for t in to) <= 1:
                    steps.append({"do": "upgrade", "id": p.tid, "to": "-".join(map(str, to))})
        return steps[:3]

    def tick(self, cash, rnd, lives_dropped=False):
        """Do at most one action. Returns True if something was bought."""
        self.now_round = rnd
        if cash is None:
            return False  # never act on an unreadable cash value
        self.wait_cost = None
        self._recheck_doubtful()
        if lives_dropped:
            self.panic_pending = 2
        if self.panic_pending:
            for st in self.panic_steps:
                r = self.try_step(dict(st), cash, rnd)
                if r in ("bought", "progress"):
                    self.panic_pending -= 1
                    return True
        self.saving_for_threat = False   # surplus() may spend unless set again below
        try:
            r = self._threat_tick(cash, rnd)
        except Exception:   # a bug in the checks must not stop the game: the plan goes on
            log.exception("threat check failed - carrying on with the plan")
            r = None
        if r is not None:
            return r
        # plan steps put aside after refused spots (the hero), once their pause is over
        for st in list(self.deferred):
            r = self.try_step(st, cash, rnd)
            if r in ("bought", "done"):
                self.deferred.remove(st)
            if r == "bought":
                return True
        while self.idx < len(self.plan):
            st = self.plan[self.idx]
            r = self.try_step(st, cash, rnd)
            if r in ("done", "skip", "bought"):
                self.idx += 1
                if r == "bought":
                    return True
                continue
            self.waiting = f"plan step {self.idx} {st} -> {r} ({self.g.fail_reason})"
            return r == "progress"  # waiting for cash / round, or mid-upgrade
        for st in self.fill:
            if self.try_step(st, cash, rnd) in ("bought", "progress"):
                return True
        self.waiting = "plan and fill exhausted"
        return False

    def surplus(self, cash, rnd):
        """Cash is piling up while the plan waits: buy damage anyway.

        1. next tier on an existing tower's own path (biggest investment first),
           respecting crosspaths, tower XP locks and the mode's tower filter
        2. another copy of the strategy's main tower
        Never violates constraints (kind_allowed) and never sells. Never
        spends cash that the last tick() held back for a threat's answer:
        that money is being saved for a bloon the defence cannot pop yet."""
        self.now_round = rnd
        if cash is None or getattr(self, "saving_for_threat", False):
            return False
        # An XP build (strategies/generated: `xp_target`) puts surplus into the
        # tower it levels up first - tower XP follows invested cash - and only
        # then into helpers, side paths or the opener.
        target = self.strat.get("xp_target") if isinstance(getattr(self, "strat", None), dict) else None
        for p, t, cost in self.upgrade_choices(first=target):
            if cost > cash:
                continue
            r = self.try_step({"do": "upgrade", "id": p.tid, "to": "-".join(map(str, t))}, cash, rnd)
            if r in ("bought", "progress"):
                log.info("surplus: upgraded %s -> %s", p.tid, p.crosspath)
                return True
        main = target if target and self._allowed(target) else self._main_kind()
        if main and cash >= self.g.price(main):
            r = self.try_step({"do": "place", "kind": main, "role": "dps", "segment": [0.2, 1.0]}, cash, rnd)
            if r == "bought":
                log.info("surplus: placed another %s", main)
                return True
        return False

    def upgrade_choices(self, first=None, past_plan=False):
        """Every next tier the towers standing may take, as (tower, tiers
        after it, price): crosspath rules (two paths at most, one past tier
        2), tower XP locks, paths the panel showed closed (capped), and the
        crosspath the plan wants for the tower (_planned_cap). Biggest
        investment first, `first` (an XP target kind) before the rest, and
        each tower's furthest path first - the order surplus() buys in.

        past_plan: a tower's leading path (its highest tier) may go past
        the plan's crosspath - the cap is there to keep a tower from being
        turned onto another path, and more of the same path does not
        (reinforce.py: Water Park Hard reached round 63 with every tower at
        its planned crosspath and $24k unspent)."""
        towers = sorted((p for p in self.g.towers.values() if p.kind != "hero"),
                        key=lambda p: (p.kind != first, -p.spent))
        family = PRICE_FAMILY.get(self.mode, "hard")
        unread = getattr(self, "unread_until", {})
        for p in towers:
            if not self._reachable(p):
                continue          # under a closed pane this round
            for path in sorted(range(3), key=lambda i: -p.tiers[i]):
                if (p.tid, path + 1) in self.capped or p.tiers[path] >= 5:
                    continue
                if time.time() < unread.get((p.tid, path + 1), 0):
                    continue      # its price was just unreadable: tried again later
                t = list(p.tiers)
                t[path] += 1
                if sum(x > 0 for x in t) > 2 or sum(x > 2 for x in t) > 1:
                    continue
                cap = self._planned_cap(p)
                leading = p.tiers[path] > 0 and p.tiers[path] == max(p.tiers)
                if cap is not None and t[path] > cap[path] and not (past_plan and leading):
                    continue  # past the crosspath the plan wants for this tower
                if self.account and t[path] > self.account.upgrades(p.kind)[path] and t[path] > 2:
                    continue  # known XP-locked beyond tier 2
                yield p, t, T.upgrade_cost(p.kind, path + 1, t[path], family)

    def _planned_cap(self, p):
        """The crosspath the plan wants this tower to end at (its upgrade steps
        by id, else by kind, over plan, fill and answers; the highest tier
        per path), or None when the plan never upgrades it. Surplus cash must
        not push a tower past it: on Enchanted Glade, Party Parade and Last
        Resort, 4-0-2 ninjas became 0-0-4 and 3-0-2 Super Monkeys 0-2-3,
        losing the attack the plan was built around."""
        if not hasattr(self, "_plan_caps"):
            by_id, by_kind = {}, {}
            steps = list(self.plan) + list(self.strat.get("fill") or [])                 + [a for v in (self.strat.get("answers") or {}).values() for a in v]
            for st in steps:
                if st.get("do") != "upgrade" or not st.get("to"):
                    continue
                try:
                    tiers = parse_cross(st["to"])
                except Exception:
                    continue
                key, table = (st["id"], by_id) if st.get("id") else (st.get("kind"), by_kind)
                if key is None:
                    continue
                old = table.get(key, (0, 0, 0))
                table[key] = tuple(max(a, b) for a, b in zip(old, tiers))
            self._plan_caps = (by_id, by_kind)
        by_id, by_kind = self._plan_caps
        return by_id.get(p.tid) or by_kind.get(p.kind)

    def _main_kind(self):
        counts = {}
        for st in self.plan:
            k = st.get("kind")
            if st.get("do") == "place" and k and k != "hero" and self._allowed(k):
                counts[k] = counts.get(k, 0) + 1
        return max(counts, key=counts.get) if counts else None

    def _allowed(self, kind):
        f = getattr(self, "kind_allowed", None)
        try:
            return f(kind) if f else True
        except TypeError:
            return True

    def defended(self):
        """At least one real tower (not just the hero) is on the map. A lone
        hero leaked 20 lives on Logs when the first tower's spot was refused;
        the rule is never to start a round without a real defence.

        Only verified towers count (Placed.verified: placed with proof, and
        not doubtful after a failed selection): a tower the game never placed
        must not let a round start."""
        return any(p.kind != "hero" and getattr(p, "verified", True)
                   for p in self.g.towers.values())
