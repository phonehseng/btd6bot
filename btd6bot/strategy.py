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
    rejects other maps when map_name is passed;
  * `extends: <map build id>` marks a plan that is a proven map build plus
    extra steps (extends_problems checks the claim; the planner then judges
    it as that map's own build).

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
import contextlib
import logging
import math
import re
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

from . import clicktime as CT
from . import reinforce as RF
from . import threats as TH
from . import towers as T

log = logging.getLogger("strategy")
STRAT_DIR = Path(__file__).resolve().parents[1] / "strategies"
ACH_DIR = STRAT_DIR / "achievements"
# Executor.waiting once a tick found nothing left to buy in the plan or fill
# (Match.setup lets surplus() spend a no-income bank only after this).
PLAN_EXHAUSTED = "plan and fill exhausted"

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
    # spike 2-3: MOAB SHREDR (x-3-x, extra MOAB-class damage; towers.py); without
    # it the Unsung Monkeys build (2-3-0 spikes) never passed coverage
    "moab": [("bomb", 2, 3), ("boomerang", 1, 4), ("tack", 1, 4), ("sniper", 1, 3), ("heli", 1, 3),
             ("dart", 3, 4), ("ninja", 3, 3), ("super", 0, 0), ("spike", 3, 3), ("spike", 2, 3),
             ("druid", 2, 4),
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
    # Apopalypse is won at round 60 (the Apopalypse Mod's EndRound,
    # data/game_model/difficulties.json; btd6bot/apopalypse.py), not 100 -
    # that is the Survivor achievement, in freeplay. With 100 here a Fast
    # Track game was planned from round 25 (optimize_builds.fast_track_start:
    # a quarter of the rounds); the game starts it at round 15.
    "apopalypse":    {"start_round": 1, "end_round": 60, "lives": 150, "continuous": True},
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


def _income_upgrades():
    """{(tower, path, tier)}: every upgrade tier whose own note in towers.py
    is about cash (it names "income" or "cash"; a note ending in "?" is
    unconfirmed and left out). Executor._is_income asks whether a target's
    top tier on a path is one of them.

    A tier-5 capstone whose note leads with another effect is not income:
    Spirit of the Forest ("vines, income") is bought for its vines, and its
    cash is only a side effect. Tiers above an income tier are judged by
    their own notes too: Elite Sniper, Special Poperations, Bloon Master
    Alchemist and Monkeyopolis do damage or other work in CHIMPS, where the
    income tiers below them pay nothing (the path is bought through them).

    It used to be only Merchantman and Bloon Trap, so CHIMPS (no income) and
    Deflation (no cash at all) could still buy Supply Drop snipers, Support
    Chinooks, Lead to Gold alchemists, Jungle's Bounty druids and Monkey
    Town villages - tiers that pay nothing there - with cash the defence
    needed. Then, for a while, every tier from the first income tier up
    counted, and CHIMPS refused Elite Sniper, Special Poperations, Bloon
    Master Alchemist and Spirit of the Forest (the druid's MOAB answer in
    ANSWERS is "path 2 tier 4 or more"; a 0-4-x druid stays income, its
    tier-5 is bought through it)."""
    word = re.compile(r"\b(income|cash)\b", re.IGNORECASE)
    found = set()
    for kind, facts in T.TOWERS.items():
        for path, ups in enumerate(facts["upgrades"], start=1):
            for up in ups:
                note = (up.get("notes") or "").strip()
                if note.endswith("?") or not word.search(note):
                    continue
                lead = note.split(",")[0]
                if up["tier"] == 5 and not word.search(lead):
                    continue  # a capstone bought for its first effect
                found.add((kind, path, up["tier"]))
    return found


# income tiers (tower, path, tier): Merchantman to Trade Empire buccaneers,
# Bloon Trap engineers, Supply Drop snipers, Support Chinooks, Lead/Rubber
# to Gold alchemists, Jungle's Bounty druids, Monkey Town/City villages,
# farm upgrades
INCOME_UPGRADES = _income_upgrades()


def _village_keystones():
    """{(path, tier): name} of the village tiers a one-life plan never sets
    aside (Executor._keep_waiting), from towers.py: the discount tiers (their
    note says "discount": Monkey Business, Monkey Commerce) and the Monkey
    Intelligence Bureau, which lets every tower near it pop every bloon."""
    out = {}
    for path, ups in enumerate(T.TOWERS["village"]["upgrades"], start=1):
        for up in ups:
            discount = (up.get("notes") or "").strip().lower() == "discount"
            if discount or up["name"] == "Monkey Intelligence Bureau":
                out[(path, up["tier"])] = up["name"]
    return out


VILLAGE_KEYSTONES = _village_keystones()

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
             "modes",      # only in these game modes (Executor._step_allowed), e.g. [half_cash]
             "at",         # exact spot [fx, fy] (screen fractions) from a map's own build
             "lane",       # "blimp": score only the track blimps ride (Executor.pick_spots)
             "obstacle"}   # do: clear - the removable obstacle's name in the map file
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


# Refused spots are learned onto the map for every later game (MapModel.refuse,
# a 3x3 square each). A long run of refused CLICKS (spots the probe passed)
# that places nothing points at the game, not the ground: on Sunset Gulch
# Medium (2026-11-02) the hero was "refused" at 10 spots in 8 s, then a sniper
# was accepted beside them. Learned refusals had grown from 765 to 2,444 of the
# map's 4,326 legal cells; the bot found 4 usable cells, placed one sniper and
# lost at round 53 with $54,839 it could not spend.
SUSPECT_CLICK_STREAK = 4


def refusals_are_trusted(click_refusals, placed):
    """False when the refusals of one Game.place call should not be learned
    for the map: SUSPECT_CLICK_STREAK or more refused clicks and no tower
    placed. They are still avoided for the rest of the game."""
    return placed or click_refusals < SUSPECT_CLICK_STREAK


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
    for where, st in _all_steps(strat):
        for m in st.get("modes") or ():
            if m not in MODE_RULES:
                probs.append(f"unknown mode {m} in a step's modes [{where}]")
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
    # `starter: {kind, at}`: the tower Match adds beside a lone opener in a
    # one-life game (match.Match._starter_spec)
    starter = strat.get("starter")
    if starter is not None and starter != "none":   # none: no starter at all (match.Match._no_starter)
        if not isinstance(starter, dict) or set(starter) - {"kind", "at"}:
            probs.append("starter: must be {kind: <tower>, at: [fx, fy]} or none")
        elif starter.get("kind") not in T.TOWERS:
            probs.append(f"starter: unknown tower {starter.get('kind')}")
        elif starter.get("at") is not None and not (
                isinstance(starter["at"], (list, tuple)) and len(starter["at"]) == 2
                and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in starter["at"])):
            probs.append(f"starter: bad spot {starter['at']!r} (two screen fractions)")
    placed = {}
    for where, st in _all_steps(strat):
        if st.get("do") == "place" and st.get("id"):
            placed[st["id"]] = st.get("kind")
    merged = {}
    allowed = set(c["allowed_towers"]) if c.get("allowed_towers") is not None else None
    forbidden = set(c.get("forbidden_towers") or ())
    for where, st in _all_steps(strat):
        do = st.get("do")
        if do not in ("place", "upgrade", "target", "sell", "clear"):
            probs.append(f"{where}: unknown step {do!r}")
            continue
        if do == "clear":
            if not st.get("obstacle"):
                probs.append(f"{where}: clear without obstacle")
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
            reasons += extends_problems(d, out)
            d["bot_ready"] = not reasons
            d["bot_ready_reasons"] = reasons
            mp = d.get("map")
            if mp and d["bot_ready"]:
                p = dict(d.get("planner") or {})
                p.setdefault("maps", [mp])
                d["planner"] = p
            out[d["id"]] = d
    return out


# An achievement plan that `extends` a map's proven build must keep that
# build's plan as its own first steps; it may leave off at most this many of
# the proven plan's LAST steps (whose cash then pays for the achievement's
# extra steps). ach_axis_of_havoc drops candyfalls_chimps' last two steps
# (the exit Spike Factory) for its tier-5 snipers.
EXTENDS_MAX_DROPPED = 3


def extends_problems(strat, loaded):
    """Why an achievement plan's `extends: <map build id>` does not hold
    (empty list: it holds). loaded: the strategies loaded so far (the map
    builds are loaded before the achievement plans).

    `extends` says "this plan is that map build, proven in play, plus extra
    steps bought with its surplus cash"; the planner then judges it as the
    map's own build (planner.is_own_map_build), which matters in CHIMPS: an
    untested achievement plan is otherwise held just under the CHIMPS bar.
    So the claim is checked here rather than trusted: the base must be a
    bot-ready map build (strategies/maps or strategies/optimized) for the same
    map, cover every mode of this plan, and its plan steps must open this
    plan unchanged, in order, but for at most EXTENDS_MAX_DROPPED of its last
    steps."""
    base_id = strat.get("extends")
    if not base_id:
        return []
    base = loaded.get(base_id)
    if base is None:
        return [f"extends {base_id!r}, which is not a loaded strategy"]
    probs = []
    if base.get("source") not in ("maps", "optimized") or not base.get("bot_ready"):
        probs.append(f"extends {base_id!r}, which is not a bot-ready map build")
    if base.get("map") != strat.get("map"):
        probs.append(f"extends {base_id!r}, a build for {base.get('map')!r}, not {strat.get('map')!r}")
    missing = set(strat.get("modes") or ()) - set(base.get("modes") or ())
    if missing:
        probs.append(f"extends {base_id!r}, which does not play {sorted(missing)}")
    own, proven = strat.get("plan") or [], base.get("plan") or []
    kept = 0
    while kept < min(len(own), len(proven)) and own[kept] == proven[kept]:
        kept += 1
    if len(proven) - kept > EXTENDS_MAX_DROPPED:
        probs.append(f"extends {base_id!r} but keeps only its first {kept} of {len(proven)} plan steps")
    return probs


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
        self.no_removals = bool(self.rules.get("no_removables") or c.get("no_removables"))
        # obstacles bought this game, by their map id (mapgeom.removables):
        # names repeat - High Finance has eleven obstacles all called
        # "Removable" - so a name cannot say which one went
        self.removed = []
        self.removal_fails = {}     # obstacle id -> failed attempts
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
        # last round the ground under a new tower must last, besides the
        # game's end; set by the match on maps with path phases (Erosion:
        # the end of the current phase, mapgeom.phase_end). None: whole game.
        self.ground_horizon = None
        self.counter = {}
        self.capped = set()          # (tid, path) that turned out locked
        self.unread_until = {}       # (tid, path) -> time: its price was not read, try later
        self.failed_spots = set()
        self.panic_pending = 0
        self.unanswerable = set()
        self.hold_fails = {}       # kind -> times the hotkey would not pick it up while others did
        self.blind_hold_fails = 0  # pick-ups that failed before any tower stood (_note_hold_failure)
        # Refused spots are counted per step under a key that survives copying
        # (_step_key): panic and answer steps run from fresh dict copies, so a
        # count keyed by id(step) never added up and they retried forever.
        self.step_spot_fails = {}  # step key -> spots refused in a row for that step
        self.dead_steps = set()    # step keys given up for this game (no spot accepted)
        # ... of those, the ones the game itself refused at least one spot for
        # (placement trouble); a step given up after 0 refused spots found no
        # legal spot in reach on the bot's own map data: the build does not
        # fit the map, the ground is not at fault (runner._note_placement)
        self.refused_dead_steps = set()
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
        """True when target (tiers per path) ends on an income tier on some
        path (INCOME_UPGRADES), or the kind is an income tower. A target past
        the income tiers (an 0-0-5 alchemist) is judged by its own tier."""
        if kind in INCOME_TOWERS:
            return True
        return any((kind, path, target[path - 1]) in INCOME_UPGRADES for path in (1, 2, 3))

    def _income_pays_nothing(self):
        """True where an income tier earns nothing: CHIMPS and `no_income_towers`
        (no income allowed) and Deflation (no cash comes in at all). Only the
        executor's own choices (upgrade_choices: surplus and reinforcing)
        skip income tiers in Deflation; its plan steps stay as written."""
        rules_ = getattr(self, "rules", None) or {}
        return bool(getattr(self, "no_income", False) or rules_.get("income") is False)

    def _step_allowed(self, step):
        """Is this plan/fill/panic step played in this game? A step with
        `modes: [...]` is played only in those modes: hard_ninja_alch_sun's
        round-63 Druids and Bomb Shooter are a Half Cash fix (2026-11-09) and
        in Hard and Double HP, where the Dartships already stand by round 63,
        they only delayed the rest of the plan."""
        only = step.get("modes")
        if only and self.mode not in only:
            return False
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
            # Ground a moving platform covers (Sanctuary) is there only in
            # some rounds: a refusal says where the platform was not then.
            # Learned, 944 such cells took half of Sanctuary's ground.
            ground = mapgeom.platform_ground(self.m)
            if ground is not None and 0 <= cy < ground.shape[0] and 0 <= cx < ground.shape[1] \
                    and ground[cy, cx]:
                log.info("spot (%d,%d) on platform ground refused - not learned (the platform "
                         "stands elsewhere this round)", cx, cy)
                return
        except Exception:
            pass
        # an amphibious tower refused here stands neither on land nor on water;
        # a big tower's refusal is kept for its kind only (placement.refusal_layer)
        from .placement import refusal_layer
        hero = self.g.hero if kind == "hero" else None
        layers = [refusal_layer(surface, kind, hero)
                  for surface in (("land", "water") if cls == "land_or_water" else (cls,))]
        for layer in layers:
            refuse(layer, cx, cy)
        log.info("learned: %s spot (%d,%d) is not placeable on this map", "/".join(layers), cx, cy)
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

    PANIC_TARGET = (2, 0, 0)   # a panic tower grows to here when the build says nothing

    def _panic_target(self, kind):
        """Crosspath a panic tower of `kind` grows toward: the build's planner
        tiers for the kind (`planner.towers`), else the first fill upgrade of
        the kind, else PANIC_TARGET (two tiers on the main path)."""
        tiers = ((self.strat.get("planner") or {}).get("towers") or {}).get(kind)
        if not tiers:
            for st in self.strat.get("fill") or []:
                if st.get("do") == "upgrade" and st.get("kind") == kind and st.get("to"):
                    tiers = parse_cross(st["to"])
                    break
        return tuple(int(t) for t in tiers) if tiers else self.PANIC_TARGET

    def _panic_grow(self, step):
        """A panic `place` step while a tower of its kind stands below the
        panic target becomes that tower's next upgrade; otherwise the step
        is returned as it is.

        Every leak used to buy another bare tower: Dark Dungeons Military
        Only (2026-11-05, lost round 50) placed nine 0-0-0 snipers at $330
        this way, each worth 2 damage every 1.6 s against a ceramic rush,
        while the plan's snipers stood at 1-2-0 - and $8-12k sat idle. The
        same cash grows the newest standing tower of the kind along the
        build's own crosspath (reinforce.grow_standing's rule for bought
        towers, applied to panic buying): a 1-2-0 sniper becomes the
        2-2-0 Large Calibre the build wants before any new one is placed.
        The newest tower comes first because it is the one the last leak
        put near the exit."""
        kind = step.get("kind")
        if step.get("do") != "place" or not kind or kind == "hero":
            return step
        target = self._panic_target(kind)
        for p in reversed(list(self.g.towers.values())):
            if p.kind != kind:
                continue
            nxt = self._next_path(p, target)
            if nxt is None:
                continue      # at the target, or grown another way
            to = list(p.tiers)
            to[nxt[0] - 1] += 1
            return {"do": "upgrade", "id": p.tid, "to": "-".join(map(str, to))}
        return step

    def _build_ids(self):
        """The ids the build's own steps name (plan, fill and answers): the
        ids a later step can wait for. Computed once per game."""
        if not hasattr(self, "_reserved_ids"):
            steps = list(self.plan) + list(self.strat.get("fill") or []) \
                + [a for v in (self.strat.get("answers") or {}).values() for a in v]
            self._reserved_ids = {st["id"] for st in steps if st.get("id")}
        return self._reserved_ids

    def _new_tid(self, kind):
        """An id for a tower placed without one (surplus, fills, answers):
        never one the board or the build already uses - a surplus "sub1"
        made the plan's own sub1 look placed, so it was never built and its
        upgrades went to the other tower."""
        reserved = self._build_ids()
        while True:
            self.counter[kind] = self.counter.get(kind, 0) + 1
            tid = f"{kind}{self.counter[kind]}"
            if tid not in reserved and tid not in self.g.towers:
                return tid

    def _range_cells(self, kind):
        if kind == "hero":
            rng = T.HEROES.get(self.g.hero, {}).get("range") or 40
        else:
            rng = T.TOWERS[kind].get("range") or 400
        return self.m.radius_cells(rng, self.g.s.width)

    def _covered(self):
        """Grid of how well placed damage towers already cover each cell
        (0 = not at all, 1 = by the strongest tower on the board).

        A tower's cover is the cash in it (price + upgrades) against the
        most-invested damage tower's: a bare 0-0-0 dart beside two 2-0-2
        ninjas covers its lane barely at all. With plain 0/1 cover, on
        Firing Range ABR (2026-11-04) the fast-track opener dart made the
        right lane look defended, so the second ninja, the alchemist and the
        village all went to the left lane; the right lane leaked 74 lives in
        rounds 23-24. The hero counts by its own price the same way (see
        _tower_cover).

        On maps whose bloon paths split, a cell also counts as covered as
        far as its lane is (see _lane_cover): bloons passing it meet every
        tower along their own lane, so a lane already shot at elsewhere
        needs the next tower less than a lane nobody guards."""
        grid = self._tower_cover()
        lane = self._lane_cover(grid)
        return grid if lane is None else 1.0 - (1.0 - grid) * (1.0 - lane)

    # How much a lane's defence (relative to the best-defended lane) counts
    # as cover on its cells: 0.5 makes the best-guarded lane's own track
    # half as wanted; lanes defended alike all get the same factor, so
    # balanced lanes keep the plain per-cell ranking.
    LANE_COVER_WEIGHT = 0.5

    def _lane_cover(self, cover):
        """Grid: for each track cell, how well its bloon path is defended
        against the best-defended path (mean tower cover over the path's
        cells, 0..1, times LANE_COVER_WEIGHT); a cell shared by several
        paths takes the least-defended one, since a tower there guards that
        lane too. On Firing Range both paths share the top rows and split
        into the left and right lanes. None on maps without geometry, with a
        single path, or with no cover yet (it would change nothing)."""
        from . import mapgeom
        try:
            grids = mapgeom.grids_for(self.m, removed=tuple(self.removed))
        except Exception:
            return None
        masks = (grids or {}).get("path_masks") or []
        if len(masks) < 2 or any(mask.shape != cover.shape for mask in masks):
            return None
        shares = [float(cover[mask].mean()) for mask in masks]
        best = max(shares)
        if best <= 0:
            return None
        lane = np.full(cover.shape, np.inf, np.float32)
        for mask, share in zip(masks, shares):
            lane[mask] = np.minimum(lane[mask], self.LANE_COVER_WEIGHT * share / best)
        lane[np.isinf(lane)] = 0.0
        return lane

    def _tower_cover(self):
        """The cover grid of the towers alone (see _covered).

        The hero is valued at its placement price (towers.HEROES 'cost'),
        like a tower with no upgrades. It used to count in full, as if it
        were the strongest tower on the board: on Party Parade Medium
        (2026-11-04, fast track from round 15) Quincy stood in the left
        lane, so that lane looked as defended as the right one with its
        0-2-2 bomb, and a2, b1 and the village all went right. Bloons split
        between the two lanes, and the left one leaked 90 lives by round 31.
        A hero with no known price still counts in full."""
        import cv2
        from .towerxp import invested
        family = PRICE_FAMILY.get(self.mode, "hard")
        poppers = [p for p in self.g.towers.values()
                   if p.kind not in ("village", "alchemist", "farm")]   # support towers do not pop
        cash = {p.tid: sum(invested([p], family).values()) for p in poppers}
        hero_price = T.HEROES.get(self.g.hero, {}).get("cost") if self.g.hero else None
        for p in poppers:
            if p.kind == "hero" and hero_price:
                cash[p.tid] = hero_price
        top = max((c for c in cash.values() if c > 0), default=0)
        grid = np.zeros(self.m.heat.shape, np.float32)
        for p in poppers:
            unpriced_hero = p.kind == "hero" and not cash[p.tid]
            strength = 1.0 if unpriced_hero or top <= 0 else min(1.0, cash[p.tid] / top)
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            r = int(round(min(self._range_cells(p.kind), 60)))
            disc = np.zeros_like(grid)
            cv2.circle(disc, (int(cx), int(cy)), max(1, r), strength, -1)
            np.maximum(grid, disc, out=grid)
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
        only = self._blimp_lane() if step.get("lane") == "blimp" and role != "support" else None
        if only is not None:
            # the blimps' own route is already a part of the track: the
            # progress window would cut it further (Workshop's chute route
            # starts at 55% of the belt), so the whole route counts
            seg = (0.0, 1.0)
        if role == "support" and step.get("near"):
            ids = [i for i in step["near"] if i in self.g.towers]
            if ids:
                xs = [self.g.towers[i].x for i in ids]
                ys = [self.g.towers[i].y for i in ids]
                near = self.m.frac_to_cell(sum(xs) / len(xs), sum(ys) / len(ys))
                near_r = step.get("near_radius", 9)
        # Where this tower fits (_legal_cells); a tower that needs no track
        # in reach also leaves the scarce ground near it to those that do
        from . import placement as PL
        hero = self.g.hero if kind == "hero" else None
        valid = self._legal_cells(kind)
        block = self._keep_off_scarce(kind, valid, self.blocked)
        far = self._far_from_at(step, block.shape)
        if far is not None:
            # a step with a researched spot falls back to cells round that
            # spot, never to the best spot by role anywhere on the map
            block = block | far
        room = self._no_buffer_room(step, valid)
        if room is not None:
            block = block | room
        covered = None if role == "support" else self._covered()
        if role == "far":
            cover = -self.m.score_spots(rc, seg, self._occupied(), placement=placement,
                                        extra_block=block, valid=valid)
            cover[cover >= 1] = -1  # still exclude blocked/occupied
        else:
            cover = self.m.score_spots(rc, seg, self._occupied(), near=near, near_radius=near_r,
                                       placement=placement, extra_block=block,
                                       covered=covered, valid=valid,
                                       **({"only": only} if only is not None else {}))
        cands = self.m.best_spots(cover, n=30 if valid is not None else 12)
        if only is not None and not cands:
            # no legal cell reaches the blimps' route: the whole track is
            # still better than setting the answer aside
            log.info("%s: no legal spot reaches the blimp route - scoring the whole track", kind)
            return self.pick_spots(kind, {k: v for k, v in step.items() if k != "lane"}, n)
        if valid is not None and role not in ("support", "far") and PL.needs_sight(kind, hero):
            # count only the track this spot can actually see past walls/blockers
            weight = (self.m.spot_weight(seg, covered) if only is None
                      else self.m.spot_weight(seg, covered, only))
            cands = [(cx, cy, PL.visible_cover(self.m, cx, cy, rc, weight)) for cx, cy, _ in cands]
        edge = self._edge_band()
        lane = None if covered is None else self._lane_cover(self._tower_cover())
        ranked = sorted(((cx, cy, sc * self._experience_factor(kind, cx, cy, rc, lane)
                          * (self.EDGE_PENALTY if edge is not None and edge[cy, cx] else 1.0))
                         for cx, cy, sc in cands), key=lambda t: -t[2])
        # the build's researched spot comes first, then its neighbours
        out = self._at_spots(step, valid, n)
        exact = out[0] if out else None
        if role in ("dps", "exit"):
            floor = self._reach_floor(kind, valid)
            best = self._best_legal_reach(kind, valid)
            if best is not None and best < 1.0 and exact is None:
                # No legal cell reaches the track at all: offering the best-
                # scored cell anyway puts a tower where it never pops a bloon.
                # Glacial Trail Medium (2026-11-05, loss case
                # 20261105_021907): the map's learned refusals had eaten the
                # few land cells near the track, so every ninja and the
                # alchemist went to a ledge 35-47 cells from it, and round 15
                # leaked 100 lives. Without a spot the step is set aside and
                # the cash can go to global-range towers (_any_legal_spot
                # logs the dead end). A blocked cell worth probing is still
                # tried: the game may accept it.
                probe = self._probe_spot(kind, valid)
                log.info("%s: no legal spot reaches the track (%d legal cells) - none offered%s",
                         kind, int(valid.sum()), " beyond one probe" if probe else "")
                return [probe] if probe is not None else []
        elif role == "support" and kind not in self.BUFFERS and kind not in ("farm", "spike"):
            # a damage tower placed beside the towers it supports must still
            # reach the track sell_useless asks of it: on Cargo Double HP a
            # Super Monkey "near v1" reached 0 track cells and was sold and
            # bought again every round from 69 to 75 ($16k-$30k idle each time)
            floor = self._reach_floor(kind, valid, self.SELL_REACH_SHARE)
        else:
            floor = None
        if step.get("at") and len(out) < n:
            # the close neighbourhood is nearly used up: the next ring out
            # keeps the tower with its group (see AT_WIDE_CELLS)
            reach = self._reach(kind) if floor is not None else None
            gap = self.AT_SPOT_GAP_CELLS ** 2
            for x, y, sc in self._at_spots(step, valid, n * 3, radius=self.AT_WIDE_CELLS):
                if len(out) >= n:
                    break
                if any((x - ox) ** 2 + (y - oy) ** 2 < gap for ox, oy, _ in out):
                    continue
                if reach is not None and reach[y, x] < floor:
                    continue    # it would only graze the track
                out.append((x, y, sc))
        if len(out) >= n:
            return out      # the researched spot's neighbourhood fills the pick-up
        # (a probe goes wherever the most track is: not for a step with a researched spot)
        # (nor for a blimp answer: the probe looks at all of the track)
        probe = (self._probe_spot(kind, valid) if role in ("dps", "exit") and far is None
                 and only is None else None)
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

    def _experience_factor(self, kind, cx, cy, rc, lane):
        """The learned score multiplier of a spot (maplearn.spot_factor),
        with its bonus shrunk as far as the spot's lane is already guarded.

        A spot earns its bonus (x1.25) by popping well above the median in
        past games - which a spot in the only defended lane always does,
        since every bloon passes it. On Firing Range ABR that bonus on the
        left lane (where n1 and the hero stand) outweighed the lane rule:
        the two lanes scored 207 and 211 before it, 263 and 215 after, and
        n2 went left again while the right lane had only a bare dart - the
        board that leaked 74 lives on 2026-11-04 (tests/test_lane_cover_
        offline.py). So the bonus counts in full on a lane nobody guards
        and not at all on the best-guarded lane (lane cover LANE_COVER_
        WEIGHT). A penalty (a spot where this tower barely pops) always
        counts in full: that is about the spot, not the lane."""
        from . import mapgeom
        from .maplearn import spot_factor
        f = spot_factor(self.m, kind, cx, cy)
        if f <= 1.0 or lane is None:
            return f
        # the spot's lane: mean lane cover over the bloon-path cells in its
        # range (the path masks _lane_cover used; the learned track heat is
        # wider and would count lane-less cells as unguarded)
        masks = mapgeom.grids_for(self.m, removed=tuple(self.removed))["path_masks"]
        on_path = np.logical_or.reduce(masks)
        H, W = lane.shape
        y0, y1 = max(0, int(cy - rc)), min(H, int(cy + rc) + 1)
        x0, x1 = max(0, int(cx - rc)), min(W, int(cx + rc) + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        near = (xx - cx) ** 2 + (yy - cy) ** 2 <= rc * rc
        cells = lane[y0:y1, x0:x1][near & on_path[y0:y1, x0:x1]]
        if not cells.size:
            return f
        guarded = min(1.0, float(cells.mean()) / self.LANE_COVER_WEIGHT)
        return 1.0 + (f - 1.0) * (1.0 - guarded)

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
            out.append(self.m.frac_to_cell(*self._at_now(at)))
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
            if tier == 5 and self._tier5_taken(p, i + 1):
                continue      # another tower of this kind holds that tier 5
            cost = (T.upgrade_cost(p.kind, i + 1, tier, PRICE_FAMILY.get(self.mode, "hard"))
                    if p.kind != "hero" else 0)
            if best is None or cost < best[1]:
                best = (i + 1, cost)
        return best

    def _unread_pause(self, p, target):
        """Is a path p still needs for `target` held back only for now
        (unread_until: its price was just unreadable, Game._path_closed)?

        _next_path leaves such a path out for a few seconds, and when it was
        the only path left the upgrade step came back "skip" - the plan
        moved past it for good. Alpine Run CHIMPS (2026-11-07 10:30-10:33):
        r1 -> 5-0-2 (Glaive Lord, $35,100), r2 -> 0-2-5 and s1 -> 5-2-0 were
        each passed over that way at the start of a round, the plan then
        counted as done, plan_first let go, and reinforce spent $37k on
        snipers with the Glaive Lord nearly paid for. Such a step waits."""
        if any(c > t for c, t in zip(p.tiers, target)):
            return False
        now = time.time()
        pauses = getattr(self, "unread_until", {})
        return any(p.tiers[i] < target[i] and (p.tid, i + 1) not in self.capped
                   and now < pauses.get((p.tid, i + 1), 0)
                   for i in range(3))

    def _tier5_taken(self, p, path):
        """Does another tower of p's kind already hold tier 5 of `path`
        (1-3)? The game allows one of each tier-5 upgrade on the map at a
        time: the button then shows "MAX UPGRADES" instead of a price, which
        reads as a blank panel, and a click there buys nothing.

        Spice Islands Impoppable (2026-11-05): sb1 bought Pre-emptive Strike
        (2-0-5) at round 88, and from then to round 98 the plan's sb2 and
        reinforce's sub2 asked for the same tier - every try a blank panel
        and a "noeffect" back-off - while $37k-119k sat idle on a one-life
        game. A step that asks for a taken tier 5 cannot complete: _next_path
        and upgrade_choices leave that path out."""
        return any(q.kind == p.kind and q.tid != p.tid and q.tiers[path - 1] >= 5
                   for q in self.g.towers.values())

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
    PLATFORM_SELECT_SPARE = 2   # ... more for a tower riding a moving platform

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
            return self._pane_now()
        return None

    # How long one reading of the open pane off the screen is trusted (s):
    # long enough for the clicks of one pick-up, short of a round change.
    PANE_READ_S = 0.5

    def _pane_now(self):
        """The round to judge Covered Garden's panes by: one whose open pane
        is the one the screen shows (mapgeom.pane_open_on_screen, read from a
        fresh frame at most every PANE_READ_S), else - when the screen does
        not say clearly, or offline - the bot's own round.

        The bot's round goes stale while a tower's side panel covers the HUD
        counter: on 2026-11-07 (20:37:21-20:38:33) it still believed round
        17, and clicked the shut bottom-left pane some 40 times while the
        top-left one was open. The screen is what the game will accept."""
        from . import mapgeom
        rnd = getattr(self, "now_round", None)
        now = time.time()
        cached = getattr(self, "_pane_read", None)
        if cached is None or now - cached[0] > self.PANE_READ_S:
            index = None
            fresh = getattr(self.g, "fresh", None)
            if fresh is not None:
                try:
                    index = mapgeom.pane_open_on_screen(self.m, fresh())
                except Exception:
                    index = None
            cached = self._pane_read = (now, index)
        index = cached[1]
        if index is None:
            return rnd
        seen = mapgeom.round_for_open_pane(self.m, index, rnd)
        if seen != rnd and getattr(self, "_pane_stale_logged", None) != (rnd, index):
            self._pane_stale_logged = (rnd, index)
            log.info("panes: the screen shows pane %d open - judging panes as in round %s "
                     "(the bot's round is %s)", index, seen, rnd)
        return seen

    def _pane_shut(self, step):
        """True when a place step's researched spot (`at`) lies under a
        cycling pane (Covered Garden) that is shut now - as the screen shows
        it (_pane_now), the round only when the screen is unclear. Placed now,
        the spot search would move the tower off the garden ground the build
        was made for; it waits for its pane's round instead."""
        at = step.get("at")
        if not at or len(at) != 2:
            return False
        from . import mapgeom
        try:
            pane, _ = mapgeom.pane_at(self.m, float(at[0]), float(at[1]), None)
            if pane is None:
                return False
            return not mapgeom.pane_at(self.m, float(at[0]), float(at[1]), self._pane_now())[1]
        except Exception:
            return False

    # How long one reading of the platforms off the screen is trusted (s).
    PLATFORM_READ_S = 0.5

    def _pose_round(self):
        """On maps whose ground moves on platforms (Sanctuary): the last
        round STARTED, whose layout the platforms stand in (mapgeom.
        platform_state). None elsewhere, so other maps keep their grids.

        The HUD shows the next round as soon as one ends, but the platforms
        only move when it starts: before Play (a Fast Track game waiting at
        round 15 stands as in round 14) and between rounds they stand as in
        the round before the HUD's. The match says whether a round is
        running (play_running, from the Play button); the screen has the
        last word when it clearly shows one of the neighbouring layouts
        (mapgeom.platform_round_on_screen, read at most every
        PLATFORM_READ_S).

        Sanctuary (2026-11-09): with the platforms held in the scene's pose
        the bot clicked water - 85 refused spots and 107 given-up steps in
        one Reverse game, lost at round 52."""
        from . import mapgeom
        rnd = getattr(self, "now_round", None)
        try:
            if rnd is None or not mapgeom.has_platforms(self.m):
                return None
        except Exception:
            return None
        guess = rnd if getattr(self, "play_running", None) is not False else rnd - 1
        now = time.time()
        cached = getattr(self, "_platform_read", None)
        if cached is None or now - cached[0] > self.PLATFORM_READ_S or cached[1] != guess:
            seen = None
            fresh = getattr(self.g, "fresh", None)
            if fresh is not None:
                try:
                    seen = mapgeom.platform_round_on_screen(self.m, fresh(), [guess, guess - 1, guess + 1])
                except Exception:
                    seen = None
            cached = self._platform_read = (now, guess, seen)
        seen = cached[2]
        if seen is not None and seen != guess:
            if getattr(self, "_platform_seen_logged", None) != (guess, seen):
                self._platform_seen_logged = (guess, seen)
                log.info("platforms: the screen shows them as in round %d (expected round %d)", seen, guess)
            guess = seen
        last = getattr(self, "_pose_seen", None)
        if last != guess:
            self._pose_seen = guess
            if last is not None:
                self._platforms_moved()
        return guess

    def _platforms_moved(self):
        """The platforms moved: spots refused or avoided on their ground
        were judged in the old layout, so they are tried again. (Towers'
        own footprints come from their current spots, carried by the
        match: carried.CarriedTowers.)"""
        from . import mapgeom
        ground = mapgeom.platform_ground(self.m)
        if ground is None:
            return
        h, w = ground.shape
        self.failed_spots = {k for k in self.failed_spots
                             if not (0 <= k[2] < h and 0 <= k[1] < w and ground[k[2], k[1]])}
        self.blocked &= ~ground
        for p in self.g.towers.values():
            self._block(*self.m.frac_to_cell(p.x, p.y), 3)

    def _on_platform(self, p):
        """True when tower p stands on a moving platform's ground."""
        from . import mapgeom
        try:
            ground = mapgeom.platform_ground(self.m)
        except Exception:
            return False
        if ground is None:
            return False
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
        return 0 <= cy < ground.shape[0] and 0 <= cx < ground.shape[1] and bool(ground[cy, cx])

    def _at_now(self, at):
        """A build's exact spot (`at`, written as the map stands in the
        scene) where it is now: on a moving platform (Sanctuary) it moves
        with the platform (mapgeom.carry_spot); elsewhere it stays."""
        rnd = self._pose_round()
        if rnd is None:
            return float(at[0]), float(at[1])
        from . import mapgeom
        try:
            return mapgeom.carry_spot(self.m, float(at[0]), float(at[1]), None, rnd)
        except Exception:
            return float(at[0]), float(at[1])

    def _reachable(self, p):
        """False while a closed pane covers tower p: a click there hits the
        glass, so it cannot be upgraded or sold this round."""
        from . import mapgeom
        try:
            if mapgeom.pane_at(self.m, p.x, p.y, None)[0] is None:
                return True          # open ground: no screen read needed
            return mapgeom.pane_at(self.m, p.x, p.y, self._pane_now())[1]
        except Exception:
            return True

    @contextmanager
    def why(self, source, reason=None, **detail):
        """Say why the purchases and sales made inside this block are made.

        Game.place, Game.upgrade and Game.sell write g.why to the game journal
        with each event (journal.py), so a lost game shows which part of the
        bot spent the money - the plan, a threat's answer, panic buying,
        reinforcing - and for what. Blocks nest: the innermost reason is the
        one written, and the outer one comes back when the block ends.

            with self.why("answer", "threat camo due"):
                self.try_step(step, cash, rnd)

        Test fakes may have no game, or refuse new attributes: then nothing
        is recorded and the block just runs.
        """
        game = getattr(self, "g", None)
        before = getattr(game, "why", None)
        try:
            setattr(game, "why", {"source": source, "reason": reason, **detail})
        except (AttributeError, TypeError):
            pass
        try:
            yield
        finally:
            try:
                setattr(game, "why", before)
            except (AttributeError, TypeError):
                pass

    def try_step(self, step, cash, rnd):
        """Returns 'done', 'wait', 'skip', 'bought' or 'progress'.

        g.fail_reason is cleared first: many "wait" answers below (a round
        gate, too little cash) never call the game, and a reason left over
        from the step before would be read as this step's. On Dark Dungeons
        Military Only (2026-11-04) the heli placement failed with "spot", the
        next step - `s1 -> 2-2-0, round: 18`, only waiting for its round - was
        set aside as "blocked (spot)", and s1 never became the planned 4-2-0."""
        self.g.fail_reason = None
        if rnd is not None and step.get("round") and rnd < step["round"]:
            return "wait"
        do = step["do"]
        if do == "place":
            return self._try_place(step, cash)
        if do == "clear":
            return self._try_clear(step, cash)
        if do == "upgrade":
            r = self._redirect_dead_upgrade(step, cash, rnd)
            if r is not None:
                return r          # the tower pops nothing: a fresh one is placed for the step
            target = parse_cross(step["to"])
            targets = self._resolve_targets(step)
            if self.no_income:
                targets = [p for p in targets if not self._is_income(p.kind, target)]
            for p in targets:
                nxt = self._next_path(p, target)
                if nxt is None:
                    continue
                if not self._reachable(p):
                    self.g.fail_reason = "pane"
                    return "wait"     # under a closed pane: set aside until its round
                path, cost = nxt
                # a panel that asked more than the price table is believed
                cost = max(cost, self.panel_price.get((p.tid, path, p.tiers[path - 1] + 1), 0))
                if cash is None or cash < cost:
                    self.wait_cost = cost
                    return "wait"
                # under a click budget the panel stays open for the next tiers
                # toward the target (_chain_tiers), when the cash covers one more
                chain = CT.time_limited(self) and self._more_tiers_after(p, path, target, cash - cost)
                if chain:
                    self.g.hold_panel = p.tid
                try:
                    t0 = time.monotonic()
                    if self.g.upgrade(p, path):
                        CT.note(self, "upgrade", time.monotonic() - t0)
                        if self.account and p.kind != "hero":
                            self.account.note_bought(p.kind, path, p.tiers[path - 1])
                        self._aim(p)       # a heli reaching 2xx can now pursue
                        if chain:
                            self._chain_tiers(p, target, cash - cost)
                        return "progress" if self._next_path(p, target) else "bought"
                    self._upgrade_failed(p, path, cash)
                    return "wait"
                finally:
                    if chain:
                        self._release_panel()
            reached = [p for p in targets if all(c >= t for c, t in zip(p.tiers, target))]
            if reached:
                return "done"
            if any(self._unread_pause(p, target) for p in targets):
                return "wait"     # only a short read pause stands in the way: not given up
            return "skip"
        if do == "target":
            for p in self._resolve_targets(step):
                self.g.target(p, step["mode"])
            return "done"
        if do == "sell":
            if self.no_sell:
                return "skip"
            targets = self._resolve_targets(step)
            if any(not self._reachable(p) for p in targets):
                self.g.fail_reason = "pane"
                return "wait"         # under a closed pane: set aside until its round
            with self.why("plan_sell", f"the plan sells {step.get('id') or step.get('kind')}"):
                for p in targets:
                    self.g.sell(p)
            return "bought"
        return "skip"

    def _more_tiers_after(self, p, path, target, cash_left):
        """Would a tier on `path` leave p short of `target` with a next tier
        that `cash_left` covers? Then its panel is worth keeping open."""
        after = list(p.tiers)
        after[path - 1] += 1
        nxt = self._next_path(SimpleNamespace(tid=p.tid, kind=p.kind, tiers=after), target)
        return nxt is not None and nxt[1] <= cash_left

    def _chain_tiers(self, p, target, cash_left):
        """Under a click budget (clicktime.time_limited), after a tier of p
        went through: buy the next tiers toward `target` from the panel still
        open (Game.hold_panel), up to clicktime.CHAIN_MAX_TIERS in all, while
        `cash_left` covers them.

        Mesa Apopalypse (2026-11-09): n3 went 0-0-0 -> 4-0-2 one tier per
        tick, each re-selecting the tower and passing through the whole match
        loop - about 3.5 s a tier, a tier a round - while $14k waited. From
        the open panel a tier takes about 1.1 s. Each tier is still checked
        as any other (Game._upgrade: the panel's owner, its prices, the
        verdict); the first that does not go through ends the run."""
        for _ in range(CT.CHAIN_MAX_TIERS - 1):
            nxt = self._next_path(p, target)
            if nxt is None:
                return
            path, cost = nxt
            cost = max(cost, self.panel_price.get((p.tid, path, p.tiers[path - 1] + 1), 0))
            if cash_left < cost:
                return
            t0 = time.monotonic()
            if not self.g.upgrade(p, path):
                self._upgrade_failed(p, path, cash_left)
                return
            CT.note(self, "chained", time.monotonic() - t0)
            if self.account and p.kind != "hero":
                self.account.note_bought(p.kind, path, p.tiers[path - 1])
            self._aim(p)
            cash_left -= cost

    def _release_panel(self):
        """Close the panel kept open for a run of tiers (Game.release_panel);
        a game without one (offline fakes) just stops holding it."""
        release = getattr(self.g, "release_panel", None)
        if callable(release):
            release()
        else:
            self.g.hold_panel = None

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
        if self.place_held_back(step):
            return "skip"
        if self._pane_shut(step):
            # its researched spot is under a closed pane: the step is set aside
            # (_set_aside_blocked) until that pane's round, its later steps
            # wait behind it, and the rest of the plan goes on
            self.g.fail_reason = "pane"
            return "wait"
        price = self.g.price(kind)
        if cash is None or cash < price:
            self.wait_cost = price
            return "wait"
        if kind in self.BUFFERS and not self._damage_towers():
            return self._defer(step, key, self.BUFFER_RETRY_S)   # nothing to buff yet
        spots = self._spots_widening(kind, step)
        if not spots:
            return self._out_of_spots(step, key)
        fracs = [self.m.cell_to_frac(cx, cy) for cx, cy, _ in spots]
        tid = step.get("id") or self._new_tid(kind)
        t0 = time.monotonic()
        placed = self.g.place(tid, kind, *fracs[0], more_spots=fracs[1:])
        if placed:
            CT.note(self, "place", time.monotonic() - t0)
        self._note_refused(kind, key, spots, fracs, placed=bool(placed))
        if placed:
            p = self.g.towers[tid]
            if getattr(self, "now_round", None) is not None:
                # the round it was bought in: its freeze phase on Glacial
                # Trail (forecast._phases) and its pop grace (sell_useless)
                p.placed_round = self.now_round
            self._learn_probe(kind, p)
            self._learn_accepted(kind, p)
            self.purchased += 1
            self.hold_fails.pop(kind, None)
            # refusals count in a row: a fill or panic step that keeps finding
            # spots between refusals must not be given up
            self.step_spot_fails.pop(key, None)
            self._block(*self.m.frac_to_cell(p.x, p.y), 3)
            if step.get("target"):
                self.g.target(p, step["target"])
            else:
                self._aim(p)
            return "bought"
        reason = self.g.fail_reason
        if reason == "hold":
            self._note_hold_failure(kind)
        elif reason in ("spot", "click") and self.step_spot_fails.get(key, 0) >= self.SPOT_LIMIT:
            return self._out_of_spots(step, key)
        elif reason == "unverified":
            self._avoid_unverified(kind)
        return "wait"

    def place_held_back(self, step):
        """True when a `place` step would be skipped without a single click:
        it was given up for this game (no spot accepted), it is pausing
        before its next try (the hero), or its tower cannot be picked up
        at all (6 failed pick-ups: locked, mode-restricted or unbound).

        Callers that offer purchases (reinforce.options) ask this first.
        Water Park ABR (2026-11-04) offered "another sniper" after that
        step had been given up: every try returned 'skip' at once, the
        model kept rating it the best purchase, and for three minutes
        (rounds 35-47, defence rated 0.06-0.15) nothing else was bought."""
        key = self._step_key(step)
        if key in self.dead_steps or time.time() < self.retry_at.get(key, 0):
            return True
        return self.hold_fails.get(step.get("kind"), 0) >= self.HOLD_BAN

    # Failed pick-ups of a kind after which it is not asked for again this
    # game: its hotkey does not pick it up (the mode or the save restricts it).
    HOLD_BAN = 6

    def _note_hold_failure(self, kind):
        """A pick-up of `kind` failed (Game.hold). It counts against the kind
        only once some tower has been placed this game, when the hotkeys are
        known to work; before that the failures are the game's, not the
        kind's. Cargo Impoppable (2026-11-05): the mode's intro box
        ("Impoppable will test your Bloon popping skills ... OK") covered the
        match for 45 s, the ninja failed six pick-ups behind it and was
        banned for the game - the build's core, its alchemist and its village
        (placed "near" it) were never bought, and round 94 was lost with
        $15,655 idle."""
        if self.purchased:
            self.hold_fails[kind] = self.hold_fails.get(kind, 0) + 1
            if self.hold_fails[kind] == self.HOLD_BAN:
                log.warning("%s: its hotkey would not pick it up %d times while other towers "
                            "were placed - not asked for again this game", kind, self.HOLD_BAN)
            return
        self.blind_hold_fails += 1
        if self.blind_hold_fails == self.HOLD_BAN:
            log.warning("%d pick-ups failed before any tower stood - the hotkeys are not "
                        "answering (a box over the match?); no kind is blamed", self.HOLD_BAN)

    def _note_refused(self, kind, key, spots, fracs, placed=False):
        """Learn every spot the last Game.place call found refused: never
        again in this game (failed_spots, blocked) nor on this map (refused
        layer), and count it against the step. A run of refused clicks that
        placed nothing is kept for this game only (see refusals_are_trusted)."""
        persist = refusals_are_trusted(getattr(self.g, "click_refusals", 0), placed)
        if not persist:
            log.warning("%s: %d clicks in a row refused and nothing placed - more likely the "
                        "game than the ground; not learned for this map", kind, self.g.click_refusals)
        for spot in getattr(self.g, "refused_spots", None) or ():
            if spot not in fracs:
                continue
            cx, cy, _ = spots[fracs.index(spot)]
            self.failed_spots.add((kind, cx, cy))
            self._block(cx, cy, 2)
            if persist:
                self._learn_blocked(kind, cx, cy)
            self.step_spot_fails[key] = self.step_spot_fails.get(key, 0) + 1

    # A support tower placed "near" others (an alchemist next to the ninja it
    # buffs) may find no free cell inside near_radius; then the radius grows
    # by these factors, and finally the step is placed by its role alone.
    # (Lost Crevasse Hard: the alchemist and the village were given up at
    # once - "after 0 refused spots" - and the game was played without them.)
    NEAR_WIDENING = (1.5, 2.2)

    AT_SEARCH_CELLS = 6   # an `at` spot taken (or refused) moves to the nearest legal cell this close
    # Past AT_SEARCH_CELLS a step with an `at` is still placed by role, but
    # only within this many cells of its spot (_far_from_at); only when
    # nothing that close is legal does _spots_widening drop the spot.
    AT_FALLBACK_CELLS = 15
    # Cells between the spots offered round an `at` in one pick-up: the
    # neighbours of a refused cell are usually refused too (pick_spots keeps
    # its own candidates this far apart for the same reason).
    AT_SPOT_GAP_CELLS = 3
    # When the cells within AT_SEARCH_CELLS of an `at` spot are all refused
    # or taken, the next ring out (this far) is offered before any spot
    # chosen by role alone, as long as it still reaches the track: a build's
    # towers are laid out as a group (a village's reach, a shared lane), and
    # the best spot by role is often across the map. Alpine Run CHIMPS
    # (2026-11-07): r3's spot and its one legal neighbour were refused and r3
    # was built at the far side of the map, away from the village it needed.
    AT_WIDE_CELLS = 18

    # A damage tower must reach at least this share of the track that the
    # best legal spot for it on this map reaches - its range (the grey circle
    # while placing) has to cover the route, not graze it. The owner, of
    # Water Park: "some of these tack shooters barely even touch the route".
    MIN_REACH_SHARE = 0.45
    # Placed damage towers reaching less than this share are sold (outside
    # no-sell modes, never while lives fall): their cash goes into towers
    # that pop bloons.
    SELL_REACH_SHARE = 0.25
    # ... but only when the kind has somewhere better to stand: when its
    # best legal spot reaches fewer track cells than this, the track the
    # bot paints right now is simply out of the kind's reach, and a sale
    # buys nothing back. Erosion Reverse (2026-11-08): bloons take one lane
    # at a time and the track is painted for the current lane only; with it
    # far from the bottom-left water the subs "reached -0 of best 0 track
    # cells", and sb1, sb2 and sb3 ($2,505, $3,240 and $5,990 of upgrades)
    # were sold at rounds 26, 39 and 42 - the build's whole lead and
    # ceramic answer for its lane. The game was lost at round 47.
    SELL_MIN_BEST_CELLS = 10.0

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

    def _buff_spots(self, kind, step=None):
        """Legal cells where a buffer reaches the most damage towers (at least
        one), best first; [] when no damage tower stands yet.

        A step with a researched spot (`at`, from a map's own build) keeps
        that spot first as long as a buffer there reaches a damage tower:
        Castle Revenge Hard's alchemists and Dark Castle's village have
        exact spots but no `near`, and were moved to wherever the most
        towers happened to stand."""
        from . import placement as PL
        if not self._damage_towers():
            return []
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        valid = PL.valid_spots(self.m, kind, None, placed, where={"land"} if self.land_only else None,
                               now_round=self._pane_round(), removed=tuple(self.removed),
                               pose_round=self._pose_round())
        if valid is None:
            return []
        # the researched spot and its neighbours first, where they buff something
        out = [c for c in (self._at_spots(step, valid, self.SPOTS_PER_HOLD) if step else [])
               if self._buffed(kind, c[0], c[1]) >= 1]
        if len(out) >= self.SPOTS_PER_HOLD:
            return out
        ys, xs = np.nonzero(valid & ~self.blocked)
        scored = sorted(((self._buffed(kind, x, y), x, y) for x, y in zip(xs.tolist(), ys.tolist())
                         if (kind, x, y) not in self.failed_spots), reverse=True)
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
    ZERO_POP_READS = 2     # pop reads of 0, rounds apart, before it counts as dead (one misread is not proof)
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
        if self._pose_round() is not None:
            # Sanctuary: off the platforms there is nothing to stand on, and
            # the platforms' ground is followed round by round - the six
            # probes of 2026-11-09 were all refused (water)
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

    def _learn_accepted(self, kind, p):
        """The tower stands: the ground under it is placeable, so any refusal
        learned there in an earlier game was wrong and is forgotten
        (MapModel.unrefuse). Without this a wrong refusal lived forever."""
        unrefuse = getattr(self.m, "unrefuse", None)
        if unrefuse is None or kind == "hero":
            return
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
        surface = "water" if T.TOWERS.get(kind, {}).get("placement") == "water" else "land"
        n = unrefuse(surface, cx, cy)
        from .placement import refusal_layer
        own = refusal_layer(surface, kind)
        if own != surface:
            n += unrefuse(own, cx, cy)
        if n:
            log.info("learned: %s stands at (%d,%d) - forgot %d refused cells there", kind, cx, cy, n)

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

    def track_changed(self):
        """The model's track was repainted mid-game (mapgeom.repaint_track:
        a new path phase): forget what was worked out from the old one."""
        self.__dict__.pop("_reach_cache", None)
        self._mask_cache = None

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

    def _best_legal_reach(self, kind, valid):
        """Track cells the best legal cell for a `kind` tower reaches, or
        None when the question does not apply (global range, no track or no
        legal ground known)."""
        if kind == "hero" or T.TOWERS.get(kind, {}).get("range") is None:
            return None
        reach = self._reach(kind)
        if reach is None or valid is None or not valid.any():
            return None
        return float(reach[valid].max())

    def _reach_floor(self, kind, valid, share=None):
        """The least track a `kind` tower must reach here (`share` of the best
        legal spot's reach, MIN_REACH_SHARE by default), or None when it does
        not apply (global range, no track or no legal ground known)."""
        best = self._best_legal_reach(kind, valid)
        if best is None:
            return None
        share = self.MIN_REACH_SHARE if share is None else share
        return share * best if best > 0 else None

    def _legal_cells(self, kind):
        """Bool grid of the cells where a `kind` tower's centre may go now,
        from the game's own map geometry: its footprint on allowed ground,
        clear of track, obstacles and the towers already placed. None on
        maps without geometry (the old grid checks then apply).

        The game's last round is passed on: ground that only changes later
        (Erosion's ice melts after round 54) is usable in a shorter game.
        On maps with path phases the ground only has to last until the
        current phase ends (ground_horizon): each phase's track is in reach
        only from ice that melts with it, and the towers lost then are put
        back beside the next path (ground_lost). The hero still asks for
        ground that lasts the whole game: it is placed once."""
        from . import placement as PL
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        last = self.rules.get("end_round")
        if self.ground_horizon is not None and kind != "hero":
            last = self.ground_horizon if last is None else min(last, self.ground_horizon)
        return PL.valid_spots(self.m, kind, self.g.hero if kind == "hero" else None, placed,
                              where={"land"} if self.land_only else None,
                              last_round=last, now_round=self._pane_round(), pose_round=self._pose_round(),
                              removed=tuple(self.removed))

    # Global-range kinds whose attack still stays round the spot they stand
    # on: the Monkey Ace flies its figure-eight about its own spot, so it is
    # not sent away from the track by the scarce-ground rule.
    GLOBAL_BUT_LOCAL = frozenset({"ace"})
    # Short-range towers the scarce-ground rule keeps room for beyond the
    # plan's own place steps: threat answers and reinforce placements.
    SCARCE_ROOM_SPARE = 4

    def _needs_no_reach(self, kind):
        """True for a tower that pops bloons wherever it stands (global
        range, GLOBAL_BUT_LOCAL excepted): it can give its spot near the
        track to a tower that cannot."""
        return (kind != "hero" and kind in T.TOWERS and T.TOWERS[kind].get("range") is None
                and kind not in self.GLOBAL_BUT_LOCAL)

    def _short_range_kinds(self):
        """The kinds of the towers still to come that need the track in
        reach: one entry per remaining plan place step of a land damage
        kind with a range (the count is what the ground must hold). With no
        such step left, every such kind the game allows, once each, so the
        ground is still kept for answers and reinforce buys."""
        def ranged(kind):
            spec = T.TOWERS.get(kind) or {}
            return (spec.get("range") is not None and kind not in self.BUFFERS
                    and (spec.get("placement") or "land") != "water" and self.kind_allowed(kind))
        plan = getattr(self, "plan", None) or []
        idx = getattr(self, "idx", 0) or 0
        steps = [st.get("kind") for st in plan[idx:]
                 if st.get("do") == "place" and st.get("role", "dps") != "support"
                 and ranged(st.get("kind"))]
        return steps or [k for k in T.TOWERS if k != "farm" and ranged(k)]

    def _scarce_ground(self):
        """Bool grid of the cells where the shortest-range tower still to
        come reaches the track (at least _reach_floor of it), when that
        ground is scarce; else None.

        Scarce means fewer such towers still fit on it - its legal cells
        over the cells one tower's footprint takes in a tight (hexagonal)
        packing - than there are short-range towers still to come
        (_short_range_kinds), plus SCARCE_ROOM_SPARE.

        Cargo Impoppable (2026-11-05, case 20261105_075327): the main deck
        lies about 23 units below the rail, so only a walkway and a pier
        corner reach the track for a short-range tower. The hero, a super,
        a desperado and a bomb filled the walkway by round 6, and at round
        56 a sniper - which needs no track in reach - took the pier corner,
        the last cell a dart could use. From then on every land kind logged
        "no legal spot reaches the track", and round 94 was lost with $15k
        idle."""
        from . import placement as PL
        kinds = self._short_range_kinds()
        if not kinds:
            return None
        short = min(set(kinds), key=lambda k: T.TOWERS[k]["range"])
        reach = self._reach(short)
        valid = self._legal_cells(short)
        floor = self._reach_floor(short, valid)
        if reach is None or valid is None or floor is None:
            return None
        ground = reach >= floor
        across = 2 * PL.footprint_radius(short) / PL.units_per_cell(self.m)   # cells between two centres
        room = int((valid & ground).sum()) / max(1.0, across * across * math.sqrt(3) / 2)
        if room >= len(kinds) + self.SCARCE_ROOM_SPARE:
            return None
        return ground

    def _keep_off_scarce(self, kind, valid, block):
        """`block` with the scarce ground (_scarce_ground) added for a tower
        that needs no track in reach, as long as that still leaves the tower
        a legal cell; `block` itself otherwise."""
        if valid is None or not self._needs_no_reach(kind):
            return block
        scarce = self._scarce_ground()
        if scarce is None or not (valid & ~scarce & ~block).any():
            return block
        logged = self.__dict__.setdefault("_scarce_logged", set())
        if kind not in logged:
            logged.add(kind)
            log.info("%s: needs no track in reach - kept off the %d legal cells near the track that "
                     "short-range towers still need", kind, int((valid & scarce).sum()))
        return block | scarce

    def _reaches_nothing(self, kind):
        """True when no legal cell for a new `kind` tower has the track in
        range now: an answer is then better bought as a kind that fits (a
        sub or a buccaneer on water) than as a tower that is never placed.
        False when it cannot be told (global range, no map geometry)."""
        if getattr(self, "m", None) is None or getattr(self, "g", None) is None:
            return False
        best = self._best_legal_reach(kind, self._legal_cells(kind))
        return best is not None and best < 1.0

    def _sole_answer(self, p):
        """The name of a bloon property (lead, camo, purple ...) that only
        tower p pops on this board, or None. Such a tower is never sold for
        reading no pops: on Flooded Valley Military Only (2026-11-04) the
        3-2-0 sniper - the only lead popper - read 0 pops twice and was sold
        one round before the round-28 leads, which then cost 113 lives. The
        threat check bought a bare 1-0-0 sniper back too late to stop them."""
        if not TH.available():
            return None
        # support auras count as reaching every tower here (in_range None):
        # the question is only who can pop the property at all
        towers = self._towers()
        others = {q.tid for q in towers if q.tid != p.tid}
        for name in dict.fromkeys(t for _, t in THREATS):
            sig = TH.sig_from_name(name)
            if sig is None:
                continue          # a strength threat, not a property one
            if TH.covers(towers, sig)[0] and not TH.covers(towers, sig, poppers=others)[0]:
                return name
        return None

    def sell_useless(self, rnd, lives_dropped=False):
        """Sell one placed damage tower whose range reaches almost no track
        (less than SELL_REACH_SHARE of the best legal spot's reach). Not in
        no-sell modes (CHIMPS) - there only the pop counts are read, so a
        dead tower's plan upgrades can move (_redirect_dead_upgrade) - not
        while lives are falling, never the last real tower. Returns True
        when one was sold.

        Nor for reach when no legal spot of the kind reaches the track
        painted now (SELL_MIN_BEST_CELLS: a path-phase map's idle lane).

        Nor while the defence is in trouble (_sale_blocked): lives fell in
        one of the last SELL_CALM_ROUNDS rounds, or the damage model rates a
        round of the look-ahead under reinforce.WEAK_MARGIN. Bazaar Reverse
        (2026-11-05) sold bomb1, bomb4 and a3 for "not a single pop" at
        rounds 41-48 while rounds 50-56 were rated 0.34-0.44, and lost
        round 51: a misread pop count, or a tower waiting for bloons on its
        stretch, is no reason to thin a defence that is already short."""
        if lives_dropped:
            self.note_lives_dropped(rnd)
        if lives_dropped or getattr(self, "_sold_round", None) == rnd:
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
        #    slide", where the map file put the second route). The pop count
        #    is read in no-sell modes too: nothing is sold there, but the
        #    plan's upgrades for such a tower move to a fresh one
        #    (_redirect_dead_upgrade)
        for p in towers:
            if p.kind in self.BUFFERS or p.kind in ("farm", "spike"):
                continue
            if rnd - p.placed_round < self.POP_GRACE_ROUNDS or (getattr(p, "pops", 0) or 0) > 0:
                continue                    # too new to judge, or proven to pop: no more clicks
            if getattr(p, "pops_round", -1) < rnd - 2:
                if self.g.select(p):        # its panel shows the pop count (Game._read_pops)
                    self.g.deselect(p)
                    p.pops_round = rnd
                    # two reads of 0, rounds apart, before a sale: one misread is not proof
                    p.zero_reads = getattr(p, "zero_reads", 0) + 1 if getattr(p, "pops", None) == 0 else 0
                break                       # one panel read per round at most
            if self._dead(p):
                if self.no_sell:
                    continue                # CHIMPS: it stays; its plan steps go elsewhere
                return self._sell_and_avoid(p, rnd, f"not a single pop in {rnd - p.placed_round} rounds")
        if self.no_sell:
            return False
        # 2. a buffer with no damage tower in its radius;
        # 3. a damage tower whose range barely reaches the track
        for p in towers:
            if p.kind in self.BUFFERS:
                cx, cy = self.m.frac_to_cell(p.x, p.y)
                if len(self._damage_towers()) >= 2 and self._buffed(p.kind, cx, cy) == 0:
                    return self._sell_and_avoid(p, rnd, "nothing in its radius to buff")
                continue
            if p.kind in ("farm", "spike") or T.TOWERS.get(p.kind, {}).get("range") is None:
                continue   # income, exit and global-range towers stay
            if self._map_wide_now(p):
                continue   # an Advanced Intel sub shoots what the others see, wherever it stands
            if self._on_platform(p):
                continue   # it rides a moving platform: what it reaches changes every round
            reach = self._reach(p.kind)
            valid = PL.valid_spots(self.m, p.kind, removed=tuple(self.removed))
            if reach is None or valid is None or not valid.any():
                continue
            best = float(reach[valid].max())
            if best < self.SELL_MIN_BEST_CELLS:
                continue   # no spot of this kind reaches today's track: nowhere better to go
            cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
            if reach[cy, cx] < self.SELL_REACH_SHARE * best:
                return self._sell_and_avoid(p, rnd, f"reaches {reach[cy, cx]:.0f} of best "
                                                    f"{best:.0f} track cells")
        return False

    @staticmethod
    def _map_wide_now(p):
        """Does tower p, at its current crosspath, work map-wide in the damage
        model (dps_model.profile(...).is_global)? A sub with Advanced Intel
        (2-x-x) shoots any bloon another tower sees, so its own range says
        nothing about its worth: Erosion Reverse sold three of them."""
        try:
            from . import dps_model as D
            prof = D.profile(p.kind, tuple(int(t) for t in p.tiers))
            return bool(prof is not None and prof.is_global)
        except Exception:
            return False

    # Cells around a sold tower's spot that its kind may not use again this game.
    SOLD_SPOT_CELLS = 3

    def _sell_and_avoid(self, p, rnd, reason=""):
        """Sell p, and keep its kind off that spot (and the cells around it)
        for the rest of the game. Every way of choosing a spot skips
        failed_spots, so a tower sold as useless is never bought again in
        the same place: on Cargo Double HP a Super Monkey was sold and
        placed back every round from 69 to 75, on Glacial Trail Medium a
        camo-answer Mermonkey within the same round.

        reason: why sell_useless sells it, for the log and the journal.
        Returns False without selling while _sale_blocked(rnd)."""
        blocked = self._sale_blocked(rnd)
        if blocked:
            log.info("keeping %s (%s, $%d spent) although %s: %s", p.tid, p.kind,
                     getattr(p, "spent", 0), reason, blocked)
            self._sold_round = rnd      # judged for this round: no more looks until the next
            return False
        log.warning("selling %s (%s, $%d spent): %s", p.tid, p.kind, getattr(p, "spent", 0), reason)
        self._sold_round = rnd
        self._avoid_spot(p)
        with self.why("sell_useless", reason, tower=p.tid, spent=getattr(p, "spent", 0)):
            return bool(self.g.sell(p))

    def _avoid_spot(self, p):
        """Keep p's kind off its spot (and SOLD_SPOT_CELLS around it) for the
        rest of the game: every way of choosing a spot skips failed_spots."""
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
        r = self.SOLD_SPOT_CELLS
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    self.failed_spots.add((p.kind, cx + dx, cy + dy))

    def _dead(self, p):
        """Is p a damage tower that has popped nothing since it was placed, by
        sell_useless's rule: ZERO_POP_READS reads of 0 from its panel, rounds
        apart, once it had POP_GRACE_ROUNDS to prove itself? Never the only
        tower that pops a bloon property (_sole_answer, said once)."""
        if p.kind in self.BUFFERS or p.kind in ("farm", "spike", "hero"):
            return False
        if getattr(p, "zero_reads", 0) < self.ZERO_POP_READS or getattr(p, "pops", 0) != 0:
            return False
        needed = self._sole_answer(p)
        if needed:
            note = ("sole-answer", p.tid)
            if note not in self._notes():
                self.noted.add(note)
                log.info("keeping %s (%s) with no pops read: the only tower that pops %s",
                         p.tid, p.kind, needed)
            return False
        return True

    def _redirect_dead_upgrade(self, step, cash, rnd):
        """A plan upgrade for a tower that pops nothing (_dead) goes to a fresh
        tower of its kind instead: the dead one is renamed out of the step's
        id (its spot is avoided from now on), a `place` step for the id is
        kept in self.redirected and tried in its place until a tower stands
        under the id again - then this and every later step for the id lands
        on the new tower. Returns try_step's result for the placement, or
        None when the step is not one to redirect. While the stand-in is not
        placed, _first_step_cost and _sim_step price the step as that
        placement (plus the tiers), so the waiting plan step's claim
        (plan_claim) and an answer's hold (_steps_cost) count the right sum.

        Ancient Portal Impoppable (2026-11-05): n2, a ninja placed at round 6
        on the walled left lane that bloons never use (the saved map model
        still painted it as track), read 0 pops from round 40 to the loss at
        94. The plan upgraded it to 2-0-4 Sticky Bomb all the same ($10,920
        on the tower in all) and the strategy's MOAB, BFB and ZOMG answers
        all named it; sell_useless could not sell it because the look-ahead
        of a one-life game is never calm (_sale_blocked). A plan upgrade never
        asked whether its tower pops anything. In no-sell modes (CHIMPS) the
        dead tower stays, but the upgrades move all the same."""
        tid = step.get("id")
        if not tid:
            return None
        redirected = getattr(self, "redirected", None)
        if redirected is None:
            redirected = self.redirected = {}
        p = self.g.towers.get(tid)
        if p is not None:
            if not self._dead(p):
                return None
            if self._planned_spot_kept(p, tid):
                return None
            if getattr(p, "renamed_dead", False) or tid not in self._build_ids():
                # No build step waits for this id, so there is nothing to
                # place anew - and a tower that pops nothing gets no upgrade.
                # The fill expands "upgrade every wizard" to one step per
                # standing wizard, named by its current id, and that id is
                # either a surplus/fill tower's own or the fresh name a dead
                # tower was given here. Water Park Magic Monkeys Only
                # (2026-11-05, lost round 63): each pass over the fill renamed
                # the same dead wizards and ninjas once more (wizard68 ->
                # wizard72 -> ... -> wizard103, 130 renames), stamped another
                # avoided disc around them and tried a placement that found no
                # spot - 111 steps "given up", and the game ended as a
                # placement defeat.
                return "skip"
            new = self._new_tid(p.kind)
            self.g.towers[new] = self.g.towers.pop(tid)
            p.tid = new
            p.renamed_dead = True       # renamed once: never again under its new name
            self._rekey_tower(tid, new)
            self._avoid_spot(p)
            place = next((dict(st) for st in self.plan if st.get("do") == "place" and st.get("id") == tid),
                         {"do": "place", "kind": p.kind, "role": "dps"})
            place.pop("at", None)           # the exact spot was the dead one
            place["id"] = tid
            redirected[tid] = place
            log.warning("%s (%s, $%d spent) has not popped a single bloon in %d rounds: its plan "
                        "upgrades go to a fresh %s instead - it is %s from now on, the plan places %s anew",
                        tid, p.kind, getattr(p, "spent", 0), (rnd or 0) - getattr(p, "placed_round", rnd or 0),
                        p.kind, new, tid)
        elif tid not in redirected:
            return None
        # the journal keeps the reason of whoever asked for the upgrade (the
        # plan, an answer, surplus): only a bare call names the plan
        outer = getattr(self.g, "why", None)
        with (contextlib.nullcontext() if outer else
              self.why("plan", f"placing {tid} anew for its upgrade", step=dict(redirected[tid]))):
            r = self._try_place(redirected[tid], cash)
        if tid in self.g.towers:
            redirected.pop(tid, None)
            # The stand-in stands, but the upgrade step is not done: it must
            # keep its place and take the new tower to its target over the
            # next ticks. "bought" moves the plan past the step; "progress"
            # counts as a purchase and keeps it. Lost Crevasse CHIMPS
            # (2026-11-07 18:29): the dead r1's step "r1 -> 5-0-2" placed a
            # fresh r1, the placement's "bought" passed the step, and the new
            # r1 stood at 0-0-0 to the round-95 loss - the Glaive Lord was
            # never bought. A "done" (the id already stood) goes on to the
            # plain upgrade (None).
            if r == "bought":
                return "progress"
            if r == "done":
                return None
        return r

    def _planned_spot_kept(self, p, tid):
        """Does a plan_first build keep tower `tid` although its pop count
        reads 0? Yes when the build's own place step for it names an exact
        spot (`at`) and the tower stands there: a hand-written build's spots
        were checked against the track, and the zero has been wrong three
        times in one evening. Spring Spring CHIMPS (2026-11-07 19:38): r1, a
        4-0-2 boomerang on a spot reaching both lanes, read 0 pops nine
        rounds after placement and its Glaive Lord step went to a fresh
        0-0-0 boomerang; Lost Crevasse (18:29) and Spring Spring (17:12)
        lost their Glaive Lords the same way. The tower keeps its upgrades;
        the zero is logged once (Game._read_pops saves the crop)."""
        if not self.plan_first():
            return False
        place = next((st for st in self.plan if st.get("do") == "place" and st.get("id") == tid), None)
        at = place.get("at") if place else None
        if not at or len(at) != 2:
            return False
        if abs(p.x - float(at[0])) > 0.05 or abs(p.y - float(at[1])) > 0.05:
            return False            # it stands elsewhere (a refused spot moved it): the rule applies
        note = ("planned-zero", tid)
        if note not in self._notes():
            self.noted.add(note)
            log.warning("%s (%s) reads 0 pops but stands on the build's own spot %s - kept, "
                        "its upgrades stay with it", tid, p.kind, at)
        return True

    def _rekey_tower(self, old, new):
        """Move the per-tower state keyed by a tower's id from `old` to `new`
        when the tower is renamed, so that the fresh tower that takes the old
        id starts clean: the executor's closed paths (capped), panel prices,
        failed clicks and unread prices, and the game's own closed paths
        (Game.closed, never clicked again once seen closed, and the blank
        reads that lead there, Game._closed_misses) - n2 2-0-4 had its middle
        path closed; a fresh n2 must not inherit that."""
        game = getattr(self, "g", None)
        for keys in (getattr(self, "capped", None), getattr(game, "closed", None)):
            for k in [k for k in (keys or ()) if k and k[0] == old]:
                keys.discard(k)
                keys.add((new,) + tuple(k[1:]))
        for d in (getattr(self, "panel_price", None), getattr(self, "upgrade_fails", None),
                  getattr(self, "unread_until", None), getattr(game, "_closed_misses", None)):
            for k in [k for k in (d or {}) if k and k[0] == old]:
                d[(new,) + tuple(k[1:])] = d.pop(k)

    # Rounds after a loss of lives in which nothing is sold as useless.
    SELL_CALM_ROUNDS = 3

    def note_lives_dropped(self, rnd):
        """Remember that lives fell in round rnd (tick and sell_useless call
        this): selling waits SELL_CALM_ROUNDS rounds after the last drop."""
        if rnd is None:
            return
        drops = getattr(self, "drop_rounds", None)
        if drops is None:
            drops = self.drop_rounds = []
        if not drops or drops[-1] != rnd:
            drops.append(rnd)
            del drops[:-self.SELL_CALM_ROUNDS]     # only the last few count

    def lives_fell_lately(self, rnd, rounds=None):
        """True when lives fell in round rnd or in one of the `rounds` - 1
        before it (SELL_CALM_ROUNDS by default)."""
        if rnd is None:
            return False
        rounds = self.SELL_CALM_ROUNDS if rounds is None else rounds
        return any(0 <= rnd - r < rounds for r in getattr(self, "drop_rounds", ()))

    def _sale_blocked(self, rnd):
        """Why no tower may be sold as useless now, or None: lives fell
        lately, or the damage model rates a round of the look-ahead (the
        rounds reinforce.py rates) under reinforce.WEAK_MARGIN. Without a
        forecast only the lives count."""
        if self.lives_fell_lately(rnd):
            return f"lives fell in the last {self.SELL_CALM_ROUNDS} rounds"
        worst = self.lookahead_worst(rnd)
        if worst is not None and worst[0] < RF.WEAK_MARGIN:
            return f"the damage model rates round {worst[1]} at {worst[0]:.2f}"
        return None

    def _at_spots(self, step, valid, n, radius=None):
        """Up to n cells round a step's exact spot (`at`), nearest first and
        at least AT_SPOT_GAP_CELLS apart, all within AT_SEARCH_CELLS of it;
        [] when the step has no `at` or nothing close is legal. Each scores
        1e9 so a ranking keeps them ahead of spots chosen by role.

        The cells after the first are what Game.place tries next while it
        still holds the tower. Lotus Island CHIMPS (2026-11-05, loss case
        20261105_171203): the game refused the click on b3's spot by the
        bay, the next spot offered was the best by role alone, and the
        carrier was built at the far north end of the map, outside the MIB
        village and the brew; round 95 (camo lead DDTs) was lost. A refused
        researched spot now moves a few cells, not across the map.

        `radius` (cells) widens the search; pick_spots uses AT_WIDE_CELLS
        when the close neighbourhood is used up."""
        at = step.get("at")
        if not at or len(at) != 2:
            return []
        cx, cy = (int(round(v)) for v in self.m.frac_to_cell(*self._at_now(at)))
        h, w = self.blocked.shape
        r = radius or self.AT_SEARCH_CELLS
        near = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if dx * dx + dy * dy > r * r:
                    continue    # a circle, not the square's corners
                if not (0 <= x < w and 0 <= y < h) or self.blocked[y, x]:
                    continue
                if valid is not None and not valid[y, x]:
                    continue
                if (step.get("kind"), x, y) in self.failed_spots:
                    continue
                near.append((dx * dx + dy * dy, x, y))
        out = []
        gap = self.AT_SPOT_GAP_CELLS ** 2
        for _, x, y in sorted(near):
            if any((x - ox) ** 2 + (y - oy) ** 2 < gap for ox, oy, _ in out):
                continue
            out.append((x, y, 1e9))
            if len(out) >= n:
                break
        return out

    def _far_from_at(self, step, shape):
        """bool grid of the cells farther than AT_FALLBACK_CELLS from the
        step's researched spot (`at`), for pick_spots to block; None when
        the step has no `at`.

        Alpine Run CHIMPS (2026-11-07 07:46): r3's spot (0.302, 0.785) and
        the one neighbour _at_spots found legal were both refused, and the
        third spot of the same pick-up was the best by role on the whole map:
        the boomerang stood at (0.639, 0.351), across the map from the
        cluster round the village. The village, placed near r1-r3, then
        followed it to (0.505, 0.521) and buffed nothing well; round 40's
        first MOAB leaked. The role ranking now only looks round the spot."""
        at = step.get("at") if step else None
        if not at or len(at) != 2:
            return None
        cx, cy = self.m.frac_to_cell(*self._at_now(at))
        yy, xx = np.ogrid[0:shape[0], 0:shape[1]]
        return (xx - cx) ** 2 + (yy - cy) ** 2 > self.AT_FALLBACK_CELLS ** 2

    # A tower a later buffer step stands "near" goes where that buffer can
    # stand within this share of its range: the rest of the radius is left
    # for the towers that gather round the buffer afterwards.
    BUFFER_ROOM_SHARE = 0.75

    def _no_buffer_room(self, step, valid):
        """Bool grid of the cells where this step's tower would leave no
        legal ground for a buffer (village, alchemist) the plan places
        `near` it later, within BUFFER_ROOM_SHARE of the buffer's range;
        None when no such buffer step waits, the step has a researched spot
        (`at`), there is no geometry, or every legal cell would be blocked.

        Mesa ABR (2026-11-09, loss case 20261109_120238): s1, a sniper,
        stood on the central mesa top where the nearest legal village cell
        was 21.6 cells away (village range 21.05). v1 "near s1" found no
        spot and was given up, the camo answer put the Radar village by the
        ninjas instead, and round 27's 250 camo bloons walked past four
        snipers that could not see them."""
        tid = step.get("id")
        if not tid or step.get("at") or valid is None:
            return None
        buffers = {st.get("kind") for st in list(getattr(self, "plan", None) or ())
                   if st.get("do") == "place" and st.get("kind") in self.BUFFERS
                   and tid in (st.get("near") or ()) and st.get("id") not in self.g.towers}
        if not buffers:
            return None
        import cv2
        from . import placement as PL
        upc = PL.units_per_cell(self.m)
        own = PL.footprint_radius(step.get("kind")) / upc if upc else 0.0
        block = np.zeros(valid.shape, bool)
        for kind in sorted(buffers):
            ground = self._legal_cells(kind)
            if ground is None or not ground.any():
                continue
            # the buffer's ground must lie in a ring round the cell: beyond
            # both footprints (the tower itself takes the ground under it -
            # on Mesa that was all the village ground near s1) and within
            # the share of the buffer's range
            inner = own + (PL.footprint_radius(kind) / upc if upc else 0.0)
            outer = max(inner + 1.0, self.BUFFER_ROOM_SHARE * self._range_cells(kind))
            r = int(np.ceil(outer))
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            d2 = xx * xx + yy * yy
            ring = ((d2 >= inner * inner) & (d2 <= outer * outer)).astype(np.float32)
            room = cv2.filter2D(ground.astype(np.float32), -1, ring, borderType=cv2.BORDER_CONSTANT)
            block |= room < 0.5
        if not (valid & ~block).any():
            return None      # no cell keeps room: placing the tower comes first
        return block

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
          4. a researched spot (`at`) is dropped: until then the search stays
             within AT_FALLBACK_CELLS of it (_far_from_at);
          5. a global-range tower (sniper, mortar, ...) takes any legal spot.
        A buffer (village, alchemist) never relaxes into a spot chosen by
        role alone: it goes next to the most damage towers (_buff_spots).
        Each relaxation that finds spots is logged; a real dead end logs how
        much legal ground there was, so the cause shows in the log."""
        if kind in self.BUFFERS and not any(i in self.g.towers for i in step.get("near") or ()):
            # none of the towers it was meant to buff stands (Water Park: a
            # lone village buffing nothing)
            return self._buff_spots(kind, step)
        spots = self.pick_spots(kind, step, n=self.SPOTS_PER_HOLD)
        if spots:
            return spots
        label = step.get("id", kind)
        if kind in self.BUFFERS:
            # A buffer whose own spot failed goes where it buffs the most
            # damage towers, before its `near` circle is widened: that circle
            # is centred on the average position of the towers it names, and
            # when one of them was pushed elsewhere the average lies between
            # the groups. Alpine Run CHIMPS (2026-11-07, loss case
            # 20261107_075148): r3 was refused by the village's spot and stood
            # across the map, the widened circle put the village midway, it
            # buffed no boomerang, and $5k of its upgrades bought nothing
            # before round 40's MOAB leaked.
            spots = self._buff_spots(kind, step)
            if spots:
                log.info("%s: no spot near %s - placed where it buffs the most towers",
                         label, step.get("near") or "its towers")
                return spots
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
        if step.get("at") and not buffer:
            at = step["at"]
            step = {k: v for k, v in step.items() if k != "at"}
            tries.append((step, f"nothing legal within {self.AT_FALLBACK_CELLS} cells of its spot "
                                f"{list(at)} - placing it by role anywhere"))
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
        valid = self._legal_cells(kind)
        if valid is None:
            return []
        legal = int(valid.sum())
        if kind == "hero" or T.TOWERS.get(kind, {}).get("range", 0) is not None:
            # pick_spots ranks the best-covering legal cells and then drops the
            # ones in failed_spots (refused, or around a sold or dead tower),
            # under the reach floor (MIN_REACH_SHARE of the best legal reach)
            # or reserved for a later step: on a crowded board those filters,
            # not the track's distance, are usually what is left
            log.info("%s: no spot found (%d legal cells; none reaches enough track outside the "
                     "refused, avoided and reserved cells - %d avoided for this kind)",
                     kind, legal, sum(1 for k in self.failed_spots if k[0] == kind))
            return []
        # cells are walked top row first, so without this a sniper takes the
        # scarce ground near the top of the map (Cargo's pier corner)
        block = self._keep_off_scarce(kind, valid, self.blocked)
        ys, xs = np.nonzero(valid)
        out = []
        for cx, cy in zip(xs.tolist(), ys.tolist()):
            if (kind, cx, cy) in self.failed_spots or block[cy, cx]:
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
            if self.step_spot_fails.get(key, 0) > 0:
                self.refused_dead_steps.add(key)
            log.warning("giving up on step %s for this game after %d refused spots",
                        step, self.step_spot_fails.get(key, 0))
        return "skip"

    def given_up_counts(self):
        """{"plan": place steps of the build itself given up this game,
        "other": the rest - threat answers (each threat tries a new tower of
        every allowed kind, ans_<threat>_<kind>, and gives up each kind
        that finds no spot without a click), panic and reinforce fills}.
        Counted together, one Sanctuary game reported 145 "plan steps given
        up" of which 12 were the build's own (2026-11-09)."""
        plan_ids = {s.get("id") for s in getattr(self, "plan", None) or () if s.get("id")}
        plan = sum(1 for key in self.dead_steps if key[3] is not None and key[3] in plan_ids)
        return {"plan": plan, "other": len(self.dead_steps) - plan}

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
            fails = self.upgrade_fails.get((p.tid, path), 0) + 1
            if reason == "noeffect" and (getattr(self, "rules", None) or {}).get("one_life"):
                # With one life only real clicks count: Game.upgrade answers
                # "noeffect" without clicking while it holds a retry back, and
                # four such answers in four ticks closed the village discount
                # path for the game (Castle Revenge Impoppable, see
                # _set_aside_blocked).
                clicks = self._noeffect_clicks(p.tid, path)
                if clicks is not None:
                    fails = clicks
            self.upgrade_fails[(p.tid, path)] = fails
            if fails >= 4:
                self.capped.add((p.tid, path))  # give up on it this game only

    def _noeffect_clicks(self, tid, path):
        """How many times Game.upgrade really clicked (tid, path) without the
        tier being bought, from the retry book it keeps (Game._retry_at:
        (until, reason, tries)); None when the game keeps no such book."""
        book = getattr(self.g, "_retry_at", None)
        if not isinstance(book, dict):
            return None
        held = book.get((tid, path))
        return held[2] if held and held[1] == "noeffect" else 0

    def _forget_if_missing(self, p):
        """Selecting p failed. MAX_SELECT_FAILS failures in a row mean it is
        not on the map (a purchase the game never made: on Ancient Portal a
        phantom ninja failed 8 selections of ~3 s each). Forget it, so that
        defended() stops counting it and a plan tower gets placed again.
        `purchased` keeps counting it: if it does exist after all, a tower
        cap must still include it. Returns True when it was forgotten.

        Not on maps that freeze towers (dps_model.TOWER_FREEZE): there a
        tower encased in ice cannot be selected for two rounds, and failed
        selections say nothing about whether it exists. Glacial Trail Medium
        (loss case 20261107_011729): every tower went up in the Fast Track
        round 15, so all of them froze together in round 25; the dart opener
        failed two selections, was forgotten as "not on the map", and its
        place step was queued again with no spot left - while it stood there
        frozen. It thaws on its own and is selected again then.

        A tower on a moving platform (Sanctuary) gets PLATFORM_SELECT_SPARE
        more tries: its spot follows the platform (carried.py), but a click
        in the second the platforms slide at a round's start misses."""
        limit = self.MAX_SELECT_FAILS + (self.PLATFORM_SELECT_SPARE if self._on_platform(p) else 0)
        if p.kind == "hero" or getattr(p, "select_fails", 0) < limit:
            return False
        from . import dps_model as D   # imported here, like the other model uses in this file
        if D.tower_uptime(getattr(self.m, "name", "")) < 1.0:
            if p.select_fails == self.MAX_SELECT_FAILS:   # say it once per streak
                log.info("%s (%s) could not be selected %d times in a row - this map freezes "
                         "towers, so it is kept until it thaws", p.tid, p.kind, p.select_fails)
            return False
        self.g.towers.pop(p.tid, None)
        log.warning("%s (%s) could not be selected %d times in a row - not on the map; forgotten",
                    p.tid, p.kind, p.select_fails)
        step = next((s for s in self.plan[:self.idx]
                     if s.get("do") == "place" and s.get("id") == p.tid), None)
        if step is not None:
            self.plan.insert(self.idx, dict(step))   # placed again before its upgrades
        return True

    def ground_lost(self, lost):
        """The map destroyed the ground under some towers (Erosion's ice
        melts after rounds 18, 36, 54 and 72, and the game removes every tower
        that stood on it). Forget those towers and queue their plan steps
        again - the place step and the upgrades already made - so the same
        build goes back up beside the new path, on ground that lasts until
        the new phase ends (ground_horizon). Towers the plan did not name
        (threat answers, reinforcements) are just forgotten: the damage
        model asks for them again if the defence needs them.

        `lost`: bool grid of the destroyed cells (mapgeom.lost_ground).
        Returns the ids of the forgotten towers."""
        if lost is None:
            return []
        h, w = lost.shape
        gone = []
        for tid, p in list(self.g.towers.items()):
            if p.kind == "hero":
                continue   # placed on whole-game ground (_legal_cells)
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            if 0 <= cy < h and 0 <= cx < w and lost[cy, cx]:
                self.g.towers.pop(tid, None)
                gone.append(tid)
        if not gone:
            return gone
        redo = [dict(s) for s in self.plan[:self.idx]
                if s.get("id") in gone and s.get("do") in ("place", "upgrade")]
        self.plan[self.idx:self.idx] = redo
        log.warning("the map destroyed the ground under %s - forgotten; %d plan steps queued "
                    "again to rebuild them", ", ".join(gone), len(redo))
        self.track_changed()
        return gone

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
    RAMP_OK_LETHAL = 1.4     # ... when the round's blimps leaking would end the game (ramp_bar)
    RAMP_PANIC = 0.4         # below this, the round before, buy blimp damage even mid-plan
    # The damage model's margin at which a blimp round counts as held, whatever
    # the blimp check says: the bar every map build is checked against (the
    # defence still holds at half strength).
    RAMP_MODEL_SAFE = 2.0
    DEFAULT_TRACK = 600.0    # world units of track when the map geometry is unknown

    def ramp_bar(self, load):
        """The blimp-check bar for a round: RAMP_OK_LETHAL when the lives its
        blimps would cost if they got through (load["leak"], from
        threats.round_blimp_load) are at least the mode's lives (MODE_RULES),
        else RAMP_OK.

        The blimp check is a rough estimate of damage in reach against HP, and
        at 1.0x it has no slack. Mushroom Grotto Double HP (2026-11-05) passed
        round 40's MOAB at 1.1x, so surplus spent the cash the plan's Maim MOAB
        sniper needed on other tiers, and the MOAB took all 100 lives at once.
        A MOAB with its children is 616 lives - more than any mode starts
        with - so for such a round the check wants a margin, and the plan's
        blimp step keeps its cash (plan_hold) until the margin is there."""
        lives = (self.rules or {}).get("lives")
        leak = (load or {}).get("leak")
        if lives and leak and leak >= lives:
            return self.RAMP_OK_LETHAL
        return self.RAMP_OK

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
        coverage, so it is not assumed to stand in any village's range.

        A tower is in range when its centre is inside the support tower's
        buff radius at its current crosspath, the damage model's rule
        (dps_model.buff_covers). This used to add about a footprint (two
        cells) to the base range: on Frozen Over CHIMPS (2026-11-05, lost at
        round 56) a Radar Scanner 49.3 units from an Aircraft Carrier
        (radius 48) counted as giving it camo, and it did not."""
        towers = self._towers()
        near = set(self._near_ids())
        pos = {p.tid: self.m.frac_to_cell(p.x, p.y) for p in towers}
        reach = {p.tid: self._buff_cells(p) for p in towers}

        def in_range(aura_tid, tid):
            if aura_tid == "__new__":
                return tid in near
            if tid == "__new__" or aura_tid not in pos or tid not in pos:
                return False
            (ax, ay), (bx, by) = pos[aura_tid], pos[tid]
            return (ax - bx) ** 2 + (ay - by) ** 2 <= reach[aura_tid] ** 2
        return in_range

    def _buff_cells(self, p):
        """Grid cells a placed tower's support buffs reach: the largest buff
        radius of its crosspath in the damage model (a buff without a radius
        of its own reaches the tower's range, as dps_model.station_for reads
        it), or its base range when the model has no buffs for it."""
        from . import dps_model as D
        prof = D.profile(p.kind, tuple(p.tiers)) if p.kind != "hero" else None
        radii = [b.get("radius") or prof.range for b in prof.buffs if not b.get("global")] if prof else []
        if not radii:
            return self._range_cells(p.kind)
        return self.m.radius_cells(max(radii), self.g.s.width)

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
        if self.hold_fails.get(kind, 0) >= self.HOLD_BAN:
            return False          # the hotkey would not pick it up this game
        if TH.tower_facts(kind).get("needs_aim"):
            return False          # Mortar/Dartling must be aimed; the bot does not aim
        if (T.TOWERS[kind].get("placement") or "land") == "water" and not self._map_has_water():
            return False
        if self._reaches_nothing(kind):
            return False          # no legal cell in reach of the track: a kind that fits answers instead
        return True

    # threat names (threats.py's older strength threats and the blimp ramp's
    # "blimps") that mean MOAB-class bloons; signatures say it with "blimp"
    BLIMP_THREATS = ("blimps", "moab", "bfb", "zomg", "ddt", "bad")

    @classmethod
    def _is_blimp_need(cls, need):
        """True when the answer for `need` is there to pop MOAB-class bloons."""
        if need in cls.BLIMP_THREATS:
            return True
        sig = TH.sig_from_name(need)
        return sig is not None and "blimp" in sig

    def _blimp_lane(self):
        """Bool grid of the track blimps ride on this map (mapgeom.blimp_track),
        or None when they ride all of it or the map has no geometry."""
        from . import mapgeom
        try:
            grids = mapgeom.grids_for(self.m, removed=tuple(self.removed))
        except Exception:                      # geometry is a help, never a must
            log.debug("blimp lane: no geometry grids", exc_info=True)
            return None
        return (grids or {}).get("blimp_track")

    def _new_tower_option(self, need, kind, cost, tiers):
        """An answer option that places a new tower and upgrades it."""
        tid = f"ans_{need.replace('+', '_')}_{kind}"
        place = {"do": "place", "id": tid, "kind": kind}
        if kind == "village":
            place.update(role="support", near=self._near_ids(), near_radius=8)
        else:
            place.update(role="dps", segment=[0.0, 0.7])
            if self._is_blimp_need(need):
                place["lane"] = "blimp"     # stand where the blimps pass (pick_spots)
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
        sim = {p.tid: (p.kind, list(p.tiers)) for p in self._towers()}
        cost = 0
        for n, st in enumerate(self.plan[self.idx:] if steps is None else steps):
            if st.get("round") and st["round"] >= due_round:
                break                       # the plan waits past the threat
            add = self._sim_step(st, sim, n)
            if add is None:
                continue
            cost += add
            if cost > budget:
                return None
            if TH.covers([(t, k, tuple(v)) for t, (k, v) in sim.items()], sig)[0]:
                return cost
        return None

    def _sim_step(self, st, sim, n):
        """What step st costs on the simulated board sim ({tid: (kind,
        tiers)}), which it updates; None for a step that buys nothing (a
        sale, a hero, a kind the mode forbids, a malformed target). n numbers
        placements without an id."""
        fam = PRICE_FAMILY.get(self.mode, "hard")
        do, kind = st.get("do"), st.get("kind")
        if do == "clear":
            r = self._named_obstacle(st.get("obstacle"))
            if r is None:
                return None
            return 0 if r["id"] in self.removed else r["cost"]
        if do == "place" and kind not in (None, "hero") and self.kind_allowed(kind):
            tid = st.get("id") or f"__plan{n}"
            if tid in sim:
                return 0
            sim[tid] = (kind, [0, 0, 0])
            return T.tower_cost(kind, fam)
        if do == "upgrade" and st.get("to"):
            try:
                want = parse_cross(st["to"])
            except ValueError:
                return None
            cost = 0
            pending = getattr(self, "redirected", {}).get(st.get("id"))
            if pending and st["id"] not in sim:
                # a dead tower's upgrade (_redirect_dead_upgrade): the fresh
                # tower it goes to is paid for first
                sim[st["id"]] = (pending["kind"], [0, 0, 0])
                cost += T.tower_cost(pending["kind"], fam)
            ids = [st["id"]] if st.get("id") in sim else \
                [t for t, (k, _) in sim.items() if k == kind and not st.get("id")]
            for tid in ids:
                k, have = sim[tid]
                new = [max(h, min(w, c)) for h, w, c in zip(have, want, self._caps(k))]
                cost += sum(T.upgrade_cost(k, i + 1, t, fam)
                            for i in range(3) for t in range(have[i] + 1, new[i] + 1))
                sim[tid] = (k, new)
            return cost
        return None

    def _steps_cost(self, steps, what="the answer"):
        """What the answer steps cost in all, from the board as it stands
        (the whole answer, not only its next tier: _hold_for keeps the part
        of it income cannot rebuild in time).

        A step that cannot be priced (a sale, a hero, a kind the mode
        forbids, a malformed target - _sim_step) is left out and said so
        once; the rest is priced. None when no step could be priced: the
        caller holds for its next tier instead (_wait_total), never for an
        unknown amount."""
        sim = {p.tid: (p.kind, list(p.tiers)) for p in self._towers()}
        priced, unpriced = [], []
        for n, st in enumerate(steps):
            cost = self._sim_step(st, sim, n)
            (unpriced if cost is None else priced).append(st if cost is None else cost)
        if unpriced:
            note = ("unpriced-steps", what, len(unpriced))
            if note not in self._notes():
                self.noted.add(note)
                log.info("%s: %d of %d steps cannot be priced (%s) - holding for the %d priced "
                         "ones ($%d)", what, len(unpriced), len(steps), unpriced, len(priced), sum(priced))
        return sum(priced) if priced else None

    def _wait_total(self, total):
        """Set self.wait_total after a step answered 'wait': the whole answer
        when it could be priced, else its next tier (self.wait_cost) - never
        None, which _hold_for would have to hold all the cash for."""
        self.wait_total = total if total is not None else getattr(self, "wait_cost", None)
        return "wait"

    def answer_threat(self, threat, cash, rnd):
        """Buy toward the answer of one due threat. Returns 'bought', 'wait'
        (saving for it), 'plan' (the plan's own next steps cover it in time:
        carry on with the plan), 'defer' (the only answer left cannot be paid
        by the threat's round: carry on, try again next tick) or 'none'
        (nothing applicable).

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
        """Try answer steps in order: 'bought', 'wait' or 'none'. On 'wait',
        self.wait_total is what this step and the ones after it cost."""
        steps = [st for st in steps or () if self._step_allowed(st)]
        for i, st in enumerate(steps):
            with self.why("threat", f"answer {threat}", step=dict(st)):
                r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("threat %s: bought toward answer %s", threat, st)
                return "bought"
            if r == "wait":
                return self._wait_total(self._steps_cost(steps[i:], f"the {threat} answer"))
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
            with self.why("threat_gap", opt["desc"], threat=threat):
                r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("threat %s (round %d): bought %s %s - cheapest answer: %s ($%d in all)",
                            threat, due_round, st["do"], st.get("kind") or st.get("id"),
                            opt["desc"], opt["cost"])
                return "bought"
            if r == "wait":
                if opt["cost"] > self._cash_by(max(due_round, rnd + self.MIN_LEAD), rnd):
                    # Midnight Mansion Primary Only (case 20261104_195037):
                    # the cheap camo answers had no legal spot, so the next
                    # option was a $27,625 Boomerang tier 5 and the bot held
                    # $4,248 for it from round 24 while camo leaked. An answer
                    # the income cannot pay by its round (or within MIN_LEAD
                    # rounds when it is due already) does not hold the cash;
                    # it is tried again on the next tick.
                    if ("defer", threat) not in self.noted:
                        self.noted.add(("defer", threat))
                        log.warning("threat %s (round %d): the only answer left, %s ($%d), cannot "
                                    "be paid by then - not holding cash for it", threat, due_round,
                                    opt["desc"], opt["cost"])
                    return "defer"
                self.wait_note = f"saving ${opt['cost']} for the {threat} answer ({opt['desc']})"
                return self._wait_total(opt["cost"])
        return "none"

    def _cash_by(self, due_round, rnd):
        """Cash expected in hand at the start of due_round: the cash seen now
        plus the income of the rounds in between, of which only 1/LEAD_MARGIN
        is counted (as in _lead_rounds)."""
        return self.cash_seen + self.income_until(due_round, rnd)

    def income_until(self, due_round, rnd):
        """The income counted on between round rnd and the start of due_round:
        the round set's cash for those rounds, times income_mult, of which
        only 1/LEAD_MARGIN is counted (as in _cash_by). 0 when it cannot be
        known. Reinforce.py asks this how much of a held amount income can
        rebuild in time (reinforce.release)."""
        if rnd is None or due_round is None or due_round <= rnd:
            return 0.0
        if not hasattr(self, "round_set"):
            if not TH.available() or not hasattr(self, "mode"):
                return 0.0
            self._init_threats()
        income = sum(TH.round_cash(self.round_set, r) * self.income_mult for r in range(rnd, due_round))
        return income / self.LEAD_MARGIN

    # -- the damage model's view, for the executor's own decisions -------------------
    def _forecast(self):
        """The damage model (forecast.RoundForecast) for this map and mode, or
        None. Match keeps its own for reinforcing; the executor builds the
        same one on first use (the map's track loads once), unless one was
        handed to it as self.forecast."""
        fc = getattr(self, "forecast", None)
        if fc is None:
            name = getattr(getattr(self, "m", None), "name", None)
            if not name:
                return None
            from .forecast import RoundForecast
            fc = RoundForecast(name, getattr(self, "mode", None), getattr(self.m, "sight", None),
                               (getattr(self.m, "sight_height", None), getattr(self.m, "ground_height", None)))
            self.forecast = fc
        return fc

    def _board_key(self):
        """What the forecast's answers depend on: every tower and its tiers."""
        return tuple(sorted((p.tid, p.kind, tuple(p.tiers)) for p in self.g.towers.values()))

    def _rated(self, what, rnd, rate):
        """rate(forecast, towers), cached per round and board (one rating of a
        round takes about 70 ms, and tick() runs many times a round)."""
        fc = self._forecast()
        if fc is None or rnd is None:
            return None
        cache = getattr(self, "_rated_cache", None)
        if cache is None:
            cache = self._rated_cache = {}
        key = (rnd, self._board_key())
        if what not in cache or cache[what][0] != key:
            try:
                value = rate(fc, list(self.g.towers.values()))
            except Exception:    # a forecast must never cost a game
                log.exception("forecast for %s failed", what)
                value = None
            cache[what] = (key, value)
        return cache[what][1]

    def margin_now(self, rnd):
        """The lower of the damage model's margins for round rnd (the round
        being played) and the next one, or None when it cannot rate them."""
        end = (getattr(self, "rules", None) or {}).get("end_round", 80)
        rounds = [r for r in (rnd, (rnd or 0) + 1) if r <= end]
        worst = self._rated("now", rnd, lambda fc, towers: fc.worst(towers, rounds))
        return None if worst is None else worst[0]

    def lookahead_worst(self, rnd):
        """(margin, round) for the weakest round of reinforce.py's look-ahead
        (rnd and the rounds after it), or None."""
        end = (getattr(self, "rules", None) or {}).get("end_round", 80)
        rounds = RF.lookahead_rounds(rnd, end)
        return self._rated("ahead", rnd, lambda fc, towers: fc.worst(towers, rounds))

    def weak_now(self, rnd):
        """Is the round being played (or the next one) in danger? True when
        the damage model rates either under reinforce.WEAK_MARGIN, or the
        blimp check rates the defence under RAMP_OK for a blimp round among
        them. Cash is then not held for anything further away than
        FAR_ROUNDS (_threat_tick) or for a dearer purchase (reinforce.py)."""
        m = self.margin_now(rnd)
        if m is not None and m < RF.WEAK_MARGIN:
            return True
        try:
            ramp = self._ramp_due(rnd)
        except Exception:     # the blimp check is optional here
            ramp = None
        return bool(ramp and ramp[0] <= rnd + 1 and ramp[2] < self.ramp_bar(ramp[1]))

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

    def _ramp_lead(self):
        """How many rounds ahead the blimp check looks: MIN_LEAD
        (MIN_LEAD_ONE_LIFE with one life), stretched by how much slower the
        mode's income saves up for blimp damage (income_mult: Half Cash pays
        half, so twice the rounds), never past MAX_LEAD.

        Another Brick, X Factor and Pat's Pond Half Cash (2026-11-06, all
        Fast Track starts at round 22) were each lost to round 40's first
        MOAB. The check first looked at round 40 from round 37, read the
        defence at 0.1-0.3x of the 1.4x wanted, and three rounds of half
        income could not pay for the strategy's MOAB answer ($2,430) on
        top of the rounds in between; the cash had gone to nearer rounds the
        damage model called weak, which all passed without a leak."""
        lead = self.MIN_LEAD_ONE_LIFE if self.rules.get("one_life") else self.MIN_LEAD
        mult = getattr(self, "income_mult", 1.0)
        if 0.0 < mult < 1.0:
            lead = math.ceil(lead / mult)
        return min(self.MAX_LEAD, lead)

    def blimp_load(self, R):
        """The blimp load round R asks the defence to pop: the round's own
        (threats.round_blimp_load), or under continuous sends (Apopalypse)
        the summed load of the rounds whose blimps share the track with
        R's (threats.continuous_blimp_load). None when R has no blimps."""
        double_hp = bool(self.rules.get("tough_moabs"))
        if self.rules.get("continuous"):
            return TH.continuous_blimp_load(self.round_set, R, self._track_length(),
                                            end_round=self.window[1], double_hp=double_hp)
        return TH.round_blimp_load(self.round_set, R, double_hp=double_hp)

    def _ramp_due(self, rnd):
        """(round, load, ratio) for the next blimp round within _ramp_lead()
        rounds, or None. Logs the estimate once per blimp round."""
        if rnd is None or self.no_answers or not TH.available():
            return None
        lead = self._ramp_lead()
        for R in range(max(rnd, self.window[0]), min(rnd + lead, self.window[1]) + 1):
            load = self.blimp_load(R)
            if not load:
                continue
            ratio = self.blimp_ratio(load)
            bar = self.ramp_bar(load)
            if ("ramp", R) not in self.noted:
                self.noted.add(("ramp", R))
                shared = load.get("rounds") or [R]
                with_others = (f" (with the blimps of rounds {shared[1]}-{shared[-1]} on the track"
                               " at the same time)" if len(shared) > 1 else "")
                log.info("blimp check round %d: %.0f blimp HP%s, %.0f units of track; the defence "
                         "deals about %.1fx that in reach%s", R, load["hp"], with_others,
                         self._track_length(), ratio,
                         "" if ratio >= bar else f" - short of the {bar:.1f}x wanted")
            if ratio < bar and self._model_holds(R, rnd, ratio, bar):
                continue
            return R, load, ratio
        return None

    def model_bar(self, ratio, bar):
        """The damage-model rating needed to overrule a blimp check that reads
        `ratio` against its bar `bar`.

        RAMP_MODEL_SAFE when the check is only just short, growing with the
        square root of how far short it is (bar / ratio). The model and the
        check fail in different ways, so the further they disagree the more
        sure the model must be. Calibrated on the cases the two were seen to
        disagree:
          - CHIMPS map builds (2026-11-05): check 0.17x of 1.4x, model 16 -
            the model was right; sqrt(8.2) * 2.0 = 5.7, so it still gives way.
          - Dark Castle Impoppable (2026-11-06): check 0.2x of 1.4x, model
            2.18 - the MOAB leaked; the bar is 5.3, so the check now stands.
          - Mushroom Grotto Reverse (2026-11-06): check 0.6x, model 2.28 -
            the MOAB leaked; the bar is about 3.1, so the check stands."""
        shortfall = bar / max(ratio, 0.01)
        return self.RAMP_MODEL_SAFE * max(1.0, shortfall) ** 0.5

    def _model_holds(self, R, rnd, ratio=None, bar=None):
        """True when the damage model rates blimp round R at model_bar(ratio,
        bar) or more (RAMP_MODEL_SAFE when no reading is given) on the board
        as it stands: the blimp check then gives way.

        The blimp check is a rough sum (counters.json blimp_dps) that gives
        villages and alchemists no credit, rates a 4-2-0 buccaneer like a
        4-0-0, has no tier-5 entry for it and treats Carrier planes as short
        range. On the CHIMPS map builds of 2026-11-05 it rated rounds 75-99
        at 0.17-1.0x of its 1.4x one-life bar where the damage model gave 16,
        so it bought loose aces, snipers and helis every round and the plan's
        last big step (a $28k Carrier Flagship, a $21.6k Sun Avatar on End Of
        The Road, lost at round 76) was never afforded. Where the model is
        unsure (under RAMP_MODEL_SAFE, or no rating) the blimp check stands:
        on Cargo Impoppable it rightly called round 94 short while the model
        gave 0.66."""
        rated = self._rated(f"blimp{R}", rnd, lambda fc, towers: fc.worst(towers, [R]))
        need = self.RAMP_MODEL_SAFE if ratio is None or bar is None else self.model_bar(ratio, bar)
        if not rated or rated[0] is None or rated[0] < need:
            if rated and rated[0] is not None and rated[0] >= self.RAMP_MODEL_SAFE \
                    and ("ramp_stands", R) not in self.noted:
                self.noted.add(("ramp_stands", R))
                log.info("blimp check round %d: the damage model rates it %.2f, under the %.1f "
                         "needed to overrule a %.1fx reading - the blimp check stands",
                         R, rated[0], need, ratio)
            return False
        if ("ramp_model", R) not in self.noted:
            self.noted.add(("ramp_model", R))
            log.info("blimp check round %d: the damage model rates it %.2f - the blimp check gives way",
                     R, rated[0])
        return True

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
        next (two rounds ahead with one life, where it is not waited for even
        when the plan is not stuck; then, unless the plan's next step is itself blimp damage, the
        most blimp damage per dollar is bought; when the defence is far short,
        RAMP_PANIC, even that step waits). When the plan's next step is itself blimp
        damage that can be paid before round R, "plan_hold": the plan goes on
        and its cash is kept for it."""
        cls = max((g["bloon"] for g in TH.round_groups(self.round_set, R)
                   if TH.bloons().get(g["bloon"], {}).get("class") == "blimp"),
                  key=TH.blimp_hp, default=None)
        why = f"blimp ramp round {R} ratio {ratio:.1f}"
        own = [st for st in (self.strat.get("answers") or {}).get(cls) or () if self._step_allowed(st)]
        for i, st in enumerate(own):
            with self.why("ramp", why, step=dict(st)):
                r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d: bought toward answer %s", R, st)
                return "bought"
            if r == "wait":
                return self._wait_total(self._steps_cost(own[i:], f"the {cls} answer"))
        # what can be paid before round R: cash now + the rounds in between
        money = self.cash_seen + sum(TH.round_cash(self.round_set, r) * self.income_mult
                                     for r in range(rnd, R))
        # The last rounds in which the plan may still take its turn. With one
        # life (Impoppable, CHIMPS) any blimp that gets through loses the game,
        # so the plan gets its last turn two rounds before the blimps and is
        # never trusted to "come good" in the round before. Spring Spring
        # Impoppable (2026-11-04): round 40's MOAB was rated 0.5x from round
        # 37; the plan's next step was a ninja 2-0-4 (Sticky Bomb, MOAB damage
        # in towers.py - Bloon Sabotage is 0-4-0) and it saved $5,672 for it
        # through rounds 38-40 while the MOAB walked out - the plan was not
        # "stuck", so it kept its turn.
        one_life = bool(self.rules.get("one_life"))
        last_call = R - 2 if one_life else R - 1
        # What is missing to reach the bar, in blimp HP the defence should
        # be able to deal in reach (also used to pick a purchase below).
        short = (self.ramp_bar(load) - ratio) * load["hp"]
        if self.idx < len(self.plan) and not (rnd >= last_call and ratio < self.RAMP_PANIC) \
                and not self._plan_step_too_weak(self.plan[self.idx], load, ratio, short):
            cost = self._plan_ramp_cost(self.plan[self.idx], load)
            if cost is not None and cost <= money:
                # the plan's next step is itself blimp damage it can pay for in
                # time: keep the cash for it (Match's idle spending must not eat it)
                return "plan_hold"
            if rnd < last_call or not (one_life or self._plan_stuck(self.plan[self.idx])):
                return "plan"
            # The round before the blimps, still short, and the plan is stuck
            # (steps set aside, or its next placement already refused this
            # game): it gets no more turns. Spillway Medium (2026-11-04) was
            # rated 0.8x for round 40's MOAB from round 37; the plan's next
            # steps were helis whose spots the game refused 30 times over
            # rounds 37-39, and the MOAB leaked all 150 lives with $7,519 in
            # the bank.
        if self.plan_first():
            return "plan"     # the build's plan is its blimp ramp (plan_first)
        # Only buys that matter: the cheapest one closing the whole shortfall,
        # else the most damage per dollar among those adding at least a tenth of
        # it. If nothing fits, save for the cheapest that closes it.
        opts = self._dps_options(load)
        closing = sorted((o for o in opts if o["gain"] >= short), key=lambda o: o["cost"])
        fits = [o for o in closing if o["cost"] <= money] or \
            [o for o in opts if o["cost"] <= money and o["gain"] >= 0.1 * short]
        for opt in fits or (closing or sorted(opts, key=lambda o: o["cost"]))[:1]:
            with self.why("ramp", why, option=opt["desc"]):
                r = self.try_step(dict(opt["steps"][0]), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d (%.1fx): bought toward %s ($%d)", R, ratio,
                            opt["desc"], opt["cost"])
                return "bought"
            if r == "wait":
                return self._wait_total(opt.get("cost"))
        return "none"

    def _plan_stuck(self, st):
        """Is the plan unlikely to deliver its next step soon? True when
        steps were set aside this game (their spot or click failed), or when
        st places a tower kind whose spots the game already refused."""
        if self.deferred:
            return True
        return st.get("do") == "place" and any(k == st.get("kind") for k, _x, _y in self.failed_spots)

    # A plan step must close at least this share of the blimp shortfall to
    # keep its turn while the defence is far short (under RAMP_PANIC).
    RAMP_PLAN_SHARE = 0.5

    def _plan_step_too_weak(self, st, load, ratio, short):
        """Should the plan lose its turn to the blimp check? True when the
        defence is far short of the blimp round (ratio under RAMP_PANIC)
        and the plan's next step st adds some blimp damage, but less than
        RAMP_PLAN_SHARE of the shortfall `short` (blimp HP). The most blimp
        damage per dollar is then bought (or saved for) at once, instead of
        holding the cash for that step.

        A step that adds no blimp damage at all is left to the rules before
        (it gets no plan_hold, and the plan loses its turn the round before
        if it is stuck): taking every such turn away under RAMP_PANIC made
        the Ascent Easy build end its game two plan steps short in the
        threat simulation (tests/test_map_hints_offline.py).

        #Ouch Double HP (2026-11-07, case 20261107_015342): from round 37 the
        blimp check rated round 40's 400-HP MOAB at 0.2x of the 1.4x wanted.
        The plan's next step, n1 -> 4-0-2 (Bloonjitsu, $2,970), adds a little
        MOAB damage, so it counted as "the plan's blimp step" and the firm
        blimp hold kept all the cash for it through rounds 37-38; then the
        next step (a ninja 2-0-4) was held for the same way. The real answer
        (a sniper and an ace) only started at round 39 and the MOAB took all
        100 lives at round 40. Cargo and Pat's Pond Half Cash (2026-11-06)
        lost round 40 the same way at 0.1x. A step that adds a fraction of
        what is missing is not the answer, however long it is waited for."""
        if ratio >= self.RAMP_PANIC or short <= 0:
            return False
        gain = self._plan_ramp_gain(st, load)
        return 0 < gain < self.RAMP_PLAN_SHARE * short

    def _plan_ramp_gain(self, st, load):
        """The blimp damage in reach (threats.blimp_capacity, in blimp HP)
        that plan step st adds: 0 for anything but an upgrade of a standing
        tower that raises it (a placement is not counted - where it lands is
        not known before it is placed)."""
        if st.get("do") != "upgrade" or not st.get("to"):
            return 0.0
        p = self.g.towers.get(st.get("id"))
        if p is None:
            return 0.0
        target = [max(a, b) for a, b in zip(p.tiers, parse_cross(st["to"]))]
        if target == list(p.tiers):
            return 0.0
        track, rng, reach = self._track_length(), self._range_units, self._reach_fn()
        return max(0.0, TH.blimp_capacity([(p.tid, p.kind, target)], load, track, rng, reach) -
                   TH.blimp_capacity([p], load, track, rng, reach))

    def _plan_ramp_cost(self, st, load):
        """What plan step st costs when it upgrades a standing tower to more
        blimp damage (threats.blimp_capacity); None for any other step.

        Spillway ABR (2026-11-04): from round 37 the blimp check called round
        40's MOAB short (0.3x) and the plan's next steps led to a Maim MOAB
        sniper (s1 -> 4-2-0, $6,805 on Hard). The ramp was left to the plan,
        but nothing held the cash for it and nothing checked it could be paid
        in time: idle spending bought a ninja and two snipers while the plan
        waited, $3,616 was all there was when round 40 came, and the MOAB
        leaked. A placement is not counted: where it lands, and so what it
        reaches, is not known before it is placed."""
        if self._plan_ramp_gain(st, load) <= 0:
            return None
        p = self.g.towers[st["id"]]       # _plan_ramp_gain found it standing
        target = [max(a, b) for a, b in zip(p.tiers, parse_cross(st["to"]))]
        fam = PRICE_FAMILY.get(self.mode, "hard")
        return sum(T.upgrade_cost(p.kind, i + 1, k, fam)
                   for i in range(3) for k in range(p.tiers[i] + 1, target[i] + 1))

    # A threat or blimp round further away than this holds only the cash income
    # cannot rebuild before it while the round being played is weak (_hold_for).
    FAR_ROUNDS = 2

    def _threat_tick(self, cash, rnd):
        """The threat part of tick(): True (bought), False (holding cash for an
        answer) or None (nothing to do: go on with the plan - possibly with
        part of the cash kept back, self.held_cash, see _hold_for)."""
        if not hasattr(self, "calendar"):
            self._init_threats()
        self.cash_seen = cash
        # an answer due now beats every plan step
        for threat in self.due_threats(rnd):
            self.wait_note = None
            self.wait_cost = self.wait_total = None
            if self._defer_far_answer(threat, rnd):
                continue      # a nearer weak round comes first: the cash goes there
            with self.why("answer", f"threat {threat} due"):
                r = self.answer_threat(threat, cash, rnd)
            if r == "bought":
                return True
            if r == "wait" and self.rules.get("income") is not False:
                # a property gap has no round of its own: its answer is held
                # for until it stands (_hold_for), a strength threat for its round
                due = self._threat_round(threat, rnd) if self._strength_threat(threat) else None
                if self._hold_for(due, self.wait_total, rnd, f"the {threat} answer",
                                  threat_answer=True) is None:
                    continue  # the round being played is weak: only part of the cash is held
                # (`waiting` is Match's idle line: set only when the cash is
                # held in full - after a partial hold the plan goes on and says
                # what it waits for)
                self.waiting = self.wait_note or f"saving for {threat} answer"
                return False  # hold cash for the answer
            # (no income, Deflation: saving cannot make the answer affordable
            # later - the money is better spent on the rest of the defence)
            if r in ("plan", "defer"):
                continue      # the plan's own next steps cover it in time, or
                              # the only answer left is out of reach for now
            log.warning("threat %s: nothing applicable to buy - not holding the plan for it", threat)
            self.unanswerable.add(threat)  # nothing applicable; don't block the plan
        ramp = self._ramp_due(rnd)
        if ramp and ramp[2] < self.ramp_bar(ramp[1]):
            self.wait_cost = self.wait_total = None
            with self.why("ramp", f"blimp damage short before round {ramp[0]}", ratio=round(ramp[2], 3)):
                r = self._answer_ramp(*ramp, cash, rnd)
            if r == "bought":
                return True
            if r == "wait" and self.rules.get("income") is not False:
                held = self._hold_for(ramp[0], self.wait_total, rnd, "blimp damage")
                if held is False:
                    self.waiting = f"saving for blimp damage before round {ramp[0]}"
                return held
            if r == "plan_hold" and self.rules.get("income") is not False:
                # the plan goes on (its next step is the blimp damage), but the
                # cash is kept for it: surplus() and reinforcing hold off
                cost = self._plan_ramp_cost(self.plan[self.idx], ramp[1]) if self.idx < len(self.plan) else None
                self._hold_for(ramp[0], cost, rnd, f"plan step {self.idx}")
        return None

    def _defer_far_answer(self, threat, rnd):
        """Should the answer to a strength threat more than FAR_ROUNDS away
        wait, because a nearer round is in danger? True when the round being
        played is weak (weak_now, or lives fell this round) or the damage
        model's weakest round ahead comes before the threat and is rated
        under reinforce.WEAK_MARGIN. The answer is then not bought this tick;
        only the part of its cost that income cannot rebuild before the
        threat's round is kept back (self.held_cash), and the rest goes to the
        nearer round through the plan, the blimp check and reinforcing. Once
        the threat is FAR_ROUNDS away or nearer, it is answered as before.

        Lotus Island CHIMPS (2026-11-05): from round 86 the model rated round
        95 at 0.38, and at round 93 reinforcing found that the Aircraft Carrier
        path of a buccaneer ($13,555) would lift it to 0.99. It bought the
        first tier; then, at round 94, the round-100 BAD answer (s1 -> 5-2-0,
        $34,560) took the whole bank, round 95 started with $492, and its
        bloons leaked through with the game's one life. The hold rule
        (_hold_for) had already said only $6,368 needed keeping for the BAD -
        it limited what was held, not what was bought."""
        if not self._strength_threat(threat):
            return False          # a property gap: nothing on the map pops it yet
        due = self._threat_round(threat, rnd)
        if rnd is None or due - rnd <= self.FAR_ROUNDS:
            return False
        if self._firm_blimp_hold(due, rnd):
            return False          # a game-ending blimp round: answered and held as usual
        reason = None
        weak_now = self.lives_fell_lately(rnd, 1) or self.weak_now(rnd)
        if weak_now:
            reason = f"round {rnd} is weak"
        else:
            worst = self.lookahead_worst(rnd)
            if worst is not None and worst[1] is not None and worst[1] < due \
                    and worst[0] < RF.WEAK_MARGIN:
                reason = f"round {worst[1]} is rated {worst[0]:.2f}"
        if reason is None:
            return False
        steps = (self.strat.get("answers") or {}).get(threat)
        if steps is None:
            steps = self._generic_answer(threat)
        steps = [st for st in steps or () if self._step_allowed(st)]
        cost = self._steps_cost(steps, f"the {threat} answer") if steps else None
        if cost is None:
            # an answer of unknown cost: how much to keep back cannot be
            # said, so it goes the usual way (answer_threat, then _hold_for)
            return False
        keep = self._far_keep(cost, due, rnd, weak_now, f"the {threat} answer")
        self.held_cash = getattr(self, "held_cash", 0.0) + keep
        note = ("defer-far", threat, rnd)
        if note not in self._notes():
            self.noted.add(note)
            log.warning("threat %s (round %d) waits: %s first - holding only $%d of its $%.0f, "
                        "the rest goes to the nearer round", threat, due, reason, keep, cost)
        return True

    def _far_keep(self, cost, due_round, rnd, weak_now, what):
        """What a hold for `what` (costing `cost`, needed by due_round, more
        than FAR_ROUNDS away) keeps back: the part of its cost the income
        until due_round cannot rebuild (income_until).

        While the round being played is weak (`weak_now`: the damage model
        rates it or the next one weak, or lives fell), it keeps nothing when
        even all the cash in hand (cash_seen) and that income cannot pay it
        before due_round (reinforce.payable_by): holding cannot bring it in
        time, and every dollar held is one the round at hand cannot use.
        Skates CHIMPS (2026-11-07) lost round 75 twice that way: the zomg
        answer of round 80 (Carpet of Spikes + Spirit of the Forest,
        $87,370) waited for round 75, rated a crisis, "holding only $72,894"
        - more than the $21,595-26,196 in the bank - so reinforce, let in by
        the plan_first crisis exception (Executor.plan_first), was handed $0
        and said "nothing $0 buys helps round 75". The plan step's own claim
        was not the block: reinforce.best already lets go of a step that
        cannot be paid before the round in danger (plan_claim_in_crisis).
        An answer income can still deliver in time keeps its part as before
        (Lotus Island's round-100 BAD answer, $6,368 of $34,560), and so does
        any hold while the round being played is not weak; with plan_first
        the released cash still goes only to the plan, its answers and a
        crisis purchase for the round at hand - Cracked's off-plan buys for
        rounds far ahead stay forbidden. Unknown cash: kept as before."""
        keep = max(0.0, cost - self.income_until(due_round, rnd))
        cash = getattr(self, "cash_seen", None)
        if weak_now and keep and cash is not None and RF.payable_by(self, cost, cash, due_round, rnd) is False:
            note = ("far-unpayable", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak and %s ($%.0f) cannot be paid before round %d from $%d and "
                            "the income until then - nothing is held for it", rnd, what, cost, due_round, cash)
            return 0.0
        return keep

    def _firm_blimp_hold(self, due_round, rnd):
        """Should a hold for due_round stay whole although the round being
        played is rated weak? True when all of these are so:

        - due_round is still ahead and is the blimp round the blimp check
          looks at (_ramp_due), rated under RAMP_PANIC: its blimps would
          end the game, and nothing nearer can make up for missing them;
        - no lives have fallen this game (drop_rounds is empty), so the
          weak rating of the nearer rounds is the damage model's alone;
        - the mode has lives to spare and pays income (not one-life
          CHIMPS/Impoppable, where a weak round is lost with its one life,
          and not Deflation, where holding cannot grow the bank).

        Bloonarius Prime Half Cash (2026-11-06, case 20261106_144410) saw
        round 40's MOAB at 0.1x from round 34, yet every round 34-37 said
        "round N is weak: holding only $0-680 ... income rebuilds the rest"
        and reinforcing spent the rest on dart and ninja tiers for those
        rounds. The same promise was made each round, so the income meant to
        rebuild the answer was spent too. Rounds 34-38, rated 0.3-0.8, passed
        with no life lost; round 40 started with $270 and the MOAB took all
        100 lives. A weak round costs a few lives at worst - lives fall, the
        hold turns partial again at the next look - while a missed MOAB is
        616 lives."""
        if due_round is None or rnd is None or due_round <= rnd:
            return False
        rules = getattr(self, "rules", None) or {}
        if rules.get("one_life") or rules.get("income") is False:
            return False
        if getattr(self, "drop_rounds", None):
            return False
        try:
            ramp = self._ramp_due(rnd)
        except Exception:     # the blimp check is optional here
            return False
        return bool(ramp and ramp[0] == due_round and ramp[2] < self.RAMP_PANIC)

    def _strength_threat(self, threat):
        """True for a strength threat (a tier must stand: ceramics, MOAB
        class, the rush ...), False for a property the defence cannot pop
        at all yet (those go to _answer_gap and always hold their cash)."""
        sig = TH.sig_from_name(threat) if TH.available() else None
        return sig is None or self._covers(sig)[0]

    def _threat_round(self, threat, rnd):
        """The round a strength threat first comes in this mode (THREATS,
        shifted for ABR, never before the first round played); rnd when it
        is not in the table."""
        shift = self.rules.get("threat_shift", {})
        r = next((shift.get(t, r) for r, t in THREATS if t == threat), None)
        return rnd if r is None else max(r, self.rules.get("start_round", 1))

    def _hold_for(self, due_round, cost, rnd, what, threat_answer=False):
        """Keep cash for `what`, which costs `cost` and is needed by due_round.
        Returns False when all of it is held (saving_for_threat: Match spends
        nothing else), None when only self.held_cash is.

        While the round being played is in danger (weak_now, or lives fell
        this round) and `what` is more than FAR_ROUNDS rounds away, only the
        part of its cost income cannot rebuild before due_round is held
        (income_until); the plan, surplus() and reinforcing may spend the
        rest on the round at hand. Chutes Impoppable (2026-11-04) idled with
        $16,972 "saving for bad answer" from round 94 - the BAD of round 100
        is due six rounds ahead with one life - while rounds 94-96 were
        rated 0.21-0.33, and lost round 96 with the cash in the bank.

        cost is the whole answer (self.wait_total), not only its next tier
        (self.wait_cost): a $40,000 BAD answer whose next tier is $3,000
        would otherwise hold about nothing. When the whole answer could not
        be priced (None) the next tier stands in for it; when neither is
        known, the cash is held only while the round being played is not
        weak - a hold of unknown size in a weak round starves the round at
        hand for a purchase nobody can name.

        A hold for a round already being played (due_round <= rnd) holds
        nothing while that round is weak: no income arrives before its
        bloons, so an answer the cash is short of now cannot come for them,
        and whatever the cash buys now is the only thing that fights them.
        Ancient Portal Impoppable (2026-11-05) held all $17,562 "for blimp
        damage before round 94", rated 0.45, while round 94's BFBs and ZOMGs
        were already walking, and lost there with the cash in the bank. In a
        safe round the hold stands as before: a strength threat is due
        through the round after its first (due_threats, r + 1), its answer
        is still wanted for the rounds that follow (round 41's MOABs come
        after round 40's), and nothing presses for the cash. due_round None
        is an answer with no round of its own (a property gap: the defence
        cannot pop the bloon at all), held as before.

        threat_answer marks a hold for a strength threat's answer
        (_threat_tick): only such a hold is released by
        _near_hold_too_late while weak rounds come before its round."""
        rnd = rnd or 0
        weak = self.lives_fell_lately(rnd, 1) or self.weak_now(rnd)
        if due_round is not None and due_round <= rnd and weak:
            note = ("playing-hold", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak and %s %s: no income arrives before this round's "
                            "bloons - nothing is held for it, the cash goes to this round", rnd, what,
                            "is for this round's bloons" if due_round == rnd else f"was due by round {due_round}")
            return None
        if cost is None:
            cost = getattr(self, "wait_cost", None)   # the next tier at least
        if cost is None and weak:
            note = ("unpriced-hold", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak and the cost of %s is not known: nothing is held "
                            "for it, the cash goes to this round", rnd, what)
            return None
        if weak and self._firm_blimp_hold(due_round, rnd):
            note = ("firm-hold", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak in the damage model only (no lives lost this game), but "
                            "round %d's blimps would end the game: all the cash is held for %s", rnd,
                            due_round, what)
            self.firm_hold = True        # Match keeps reinforcing off it, even in a crisis round
            self.saving_for_threat = True
            return False
        if cost is not None and due_round is not None and due_round - rnd > self.FAR_ROUNDS and weak:
            keep = self._far_keep(cost, due_round, rnd, True, what)
            self.held_cash = getattr(self, "held_cash", 0.0) + keep
            note = ("weak-hold", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak: holding only $%d for %s (round %d, $%s) - income "
                            "rebuilds the rest by then; the rest of the cash goes to this round",
                            rnd, keep, what, due_round, f"{cost:.0f}")
            return None
        # Only a threat answer (threat_answer=True, from _threat_tick) gives
        # way here. A blimp-damage hold from the blimp check (_answer_ramp)
        # is for the very rounds that make this one weak, and has its own
        # too-dear rule there: releasing it let idle spending eat the cash
        # of Spillway ABR's Maim MOAB step (test_plan_blimp_step_keeps_its_cash).
        if weak and threat_answer and self._near_hold_too_late(due_round, cost, rnd):
            note = ("near-too-late", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is weak and %s ($%.0f, round %d) cannot be paid before round %d "
                            "starts from $%d - nothing is held for it, the cash goes to the weak rounds "
                            "first", rnd, what, cost, due_round, rnd + 1, self.cash_seen)
            return None
        self.saving_for_threat = True
        return False

    def _near_hold_too_late(self, due_round, cost, rnd):
        """Is a hold for a round at most FAR_ROUNDS away pointless for the
        weak round(s) before it? True when the cash in hand (cash_seen) and
        this round's income cannot pay `cost` before round rnd + 1 starts
        (income_until(rnd + 1, rnd)). weak_now covers rnd and rnd + 1, so
        the danger comes before the money: a full hold would leave the weak
        rounds with nothing, and the answer would still not be there for
        them. Unknown cash or cost: False (hold as before).

        Spring Spring CHIMPS (2026-11-07, case 20261107_225718): from round
        98 (rated 1.18, round 99 at 1.04) all the cash was held "for the bad
        answer" of round 100 ($34,560) - two rounds away, so the far-round
        rule (_far_keep) no longer applied. The plan's Cripple MOAB sniper
        was never bought, round 99 started with $32,973 in the bank and its
        bloons took the one life. Far holds keep their own rule; a safe
        round still holds in full."""
        cash = getattr(self, "cash_seen", None)
        if cash is None or cost is None or due_round is None or rnd is None:
            return False
        if not rnd < due_round <= rnd + self.FAR_ROUNDS:
            return False
        return cash + self.income_until(rnd + 1, rnd) < cost

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
        if step.get("do") == "clear":
            r = self._named_obstacle(step.get("obstacle"))
            return float("inf") if r is None else (0 if r["id"] in self.removed else r["cost"])
        p = self.g.towers.get(step.get("id"))
        if p is None:
            pending = getattr(self, "redirected", {}).get(step.get("id"))
            if pending:      # a dead tower's upgrade: a fresh tower is placed for it first
                return self.g.price(pending["kind"])
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

    # A leak buys at least PANIC_MIN_BUYS panic steps, and one more for every
    # PANIC_CASH_PER_BUY of cash in hand, up to PANIC_MAX_BUYS.
    PANIC_MIN_BUYS = 2
    PANIC_CASH_PER_BUY = 2000
    PANIC_MAX_BUYS = 8

    def _panic_buys(self, cash):
        """How many panic steps a leak buys, given the cash in hand.

        It was always two. Erosion Reverse (2026-11-08): round 44 cost 28 of
        60 lives with $14,850 in hand; the two panic buys spent $1,750, the
        damage model (which had rated round 44 at 3.79) saw nothing to
        reinforce, and round 47 was lost with $19,964 unspent. A leak in a
        round the model called safe means the model is wrong about this
        board, so the bank goes into the build's panic towers. Past the
        first PANIC_MIN_BUYS they alternate with the plan (tick)."""
        try:
            extra = int(max(0.0, float(cash)) // self.PANIC_CASH_PER_BUY)
        except (TypeError, ValueError):
            extra = 0
        return max(self.PANIC_MIN_BUYS, min(self.PANIC_MAX_BUYS, extra))

    def tick(self, cash, rnd, lives_dropped=False):
        """Do at most one action. Returns True if something was bought."""
        self.now_round = rnd
        if cash is None:
            return False  # never act on an unreadable cash value
        self.wait_cost = self.wait_total = None
        self.tick_no = getattr(self, "tick_no", 0) + 1     # _set_aside_blocked counts ticks
        self._recheck_doubtful()
        if lives_dropped:
            self.panic_pending = self._panic_buys(cash)
            self.panic_bought = 0          # buys made for this leak so far
            self.note_lives_dropped(rnd)
        # the first PANIC_MIN_BUYS go at once; the extra ones the bank pays
        # for take every other tick, so the plan and the threat checks keep
        # their turn while lives keep falling
        if self.panic_pending and (getattr(self, "panic_bought", 0) < self.PANIC_MIN_BUYS
                                   or self.tick_no % 2 == 0):
            for st in self.panic_steps:
                with self.why("panic", "lives dropped"):
                    # a standing tower of the kind grows before another is bought
                    r = self.try_step(self._panic_grow(dict(st)), cash, rnd)
                if r in ("bought", "progress"):
                    self.panic_pending -= 1
                    self.panic_bought = getattr(self, "panic_bought", 0) + 1
                    return True
        self.saving_for_threat = False   # surplus() may spend unless set again below
        self.firm_hold = False           # set by _hold_for for a game-ending blimp round
        self.held_cash = 0.0             # part of the cash kept for a far threat (_hold_for)
        try:
            r = self._threat_tick(cash, rnd)
        except Exception:   # a bug in the checks must not stop the game: the plan goes on
            log.exception("threat check failed - carrying on with the plan")
            r = None
        if r is not None:
            return r
        if self.held_cash:
            # what the plan may spend: the cash less what a far threat keeps
            cash = max(0, cash - self.held_cash)
        hold = getattr(self, "reinforce_hold", 0) or 0
        if hold and not lives_dropped:
            # Reinforce is saving for the one purchase the model says holds
            # the weakest round ahead (Match._reinforce_hold). Ancient Portal
            # Impoppable (2026-11-05): four seconds after "saving for upgrade
            # ace2 -> 2-4-0 ($19200) - round 98 goes 0.84 -> 1.01" the plan
            # spent $10,760 taking sniper3 to 4-0-2, which moved round 98 by
            # 0.05; round 98 started with $16,190, rated 0.90, and was lost.
            # The plan's steps get only what the saving does not need.
            cash = max(0, cash - hold)
        # plan steps put aside after refused spots (the hero), once their pause is over
        waiting_ids = set()     # towers whose earlier set-aside step is not done yet
        for st in list(self.deferred):
            tid = st.get("id")
            if tid and tid in waiting_ids:
                continue        # a tower's set-aside steps go in plan order (_set_aside_blocked)
            with self.why("deferred", "a plan step set aside earlier", step=dict(st)):
                r = self.try_step(st, cash, rnd)
            if r in ("bought", "done"):
                self.deferred.remove(st)
            elif tid:
                waiting_ids.add(tid)
            if r == "bought":
                return True
        if CT.time_limited(self) and not self.deferred:
            # under a click budget a later plan step may come first (_quicker_step)
            ahead = self._quicker_step(cash, rnd)
            if ahead is not None:
                j, why = ahead
                st = self.plan[j]
                with self.why("plan", f"plan step {j} before step {self.idx}: {why}",
                              step_idx=j, step=dict(st)):
                    r = self.try_step(st, cash, rnd)
                if r in ("bought", "progress"):
                    log.info("plan step %d %s comes before step %d: %s", j, st, self.idx, why)
                    return True
        while self.idx < len(self.plan):
            st = self.plan[self.idx]
            if self._waits_for_set_aside_place(st):
                # its tower's placement was set aside: it waits with it
                self.deferred.append(st)
                self.idx += 1
                continue
            with self.why("plan", f"plan step {self.idx}", step_idx=self.idx, step=dict(st)):
                r = self.try_step(st, cash, rnd)
            if r in ("done", "skip", "bought"):
                self.idx += 1
                if r == "bought":
                    return True
                continue
            if r == "wait" and self._set_aside_blocked(st):
                continue
            self.waiting = f"plan step {self.idx} {st} -> {r} ({self.g.fail_reason})"
            return r == "progress"  # waiting for cash / round, or mid-upgrade
        for st in self.fill:
            with self.why("fill", "the plan is done: fill step", step=dict(st)):
                r = self.try_step(st, cash, rnd)
            if r in ("bought", "progress"):
                return True
        self.waiting = PLAN_EXHAUSTED
        return False

    def _plan_bundles(self, rnd):
        """The plan steps of clicktime.PLAN_WINDOW from the current one, as
        {tower id: [(index, step), ...]} in plan order, cut at the first step
        that is not a placement or an upgrade of a named tower, or that
        waits for a later round: steps past such a step keep their order."""
        bundles = {}
        for i in range(self.idx, min(len(self.plan), self.idx + CT.PLAN_WINDOW)):
            st = self.plan[i]
            if (st.get("do") not in ("place", "upgrade") or not st.get("id")
                    or (st.get("round") and (rnd is None or rnd < st["round"]))):
                break
            bundles.setdefault(st["id"], []).append((i, st))
        return bundles

    def _bundle_after(self, steps, now, spot):
        """(board after, cost, seconds) once the plan `steps` of one tower
        are done, from the board `now` - or None when they cannot be rated
        (an upgrade of a tower not standing, a target the tower has passed).
        spot: (fx, fy) for a tower the steps place."""
        family = PRICE_FAMILY.get(self.mode, "hard")
        tid = steps[0][1]["id"]
        p = self.g.towers.get(tid)
        kind = p.kind if p is not None else steps[0][1].get("kind")
        tiers = tuple(p.tiers) if p is not None else None
        cost = 0.0
        for _, st in steps:
            if st["do"] == "place":
                if p is not None or spot is None or tiers is not None or kind is None:
                    return None
                cost += self.g.price(kind) or 0.0
                tiers = (0, 0, 0)
            else:
                if tiers is None:
                    return None
                target = tuple(parse_cross(st["to"]))
                if any(c > t for c, t in zip(tiers, target)):
                    return None
                cost += T.total_cost(kind, target, family) - T.total_cost(kind, tiers, family)
                tiers = target
        if p is not None:
            after = [SimpleNamespace(**{**vars(t), "tiers": tiers}) if t.tid == tid else t for t in now]
        else:
            after = now + [SimpleNamespace(tid=tid, kind=kind, tiers=tiers, x=spot[0], y=spot[1])]
        return after, cost, CT.board_seconds(self, now, after)

    def _quicker_step(self, cash, rnd):
        """(index, why) of a later plan step to buy before the current one,
        or None. Only under a click budget (clicktime.time_limited).

        Mesa Apopalypse (2026-11-09, lost at round 59): from round 45 the plan
        was at "place n3", then "n3 -> 4-0-2" (a placement and six tiers,
        $5.4k), then "n2 -> 2-0-4" ($5,000, one tier). Rounds came every
        3-4 s and a purchase took one of them, so n3 grew a tier a round for
        seven rounds while the bank went $5k -> $17k and n2's Sticky Bomb -
        one click - waited behind it.

        Within clicktime.PLAN_WINDOW steps, each tower's steps form one
        bundle (its placement and its upgrades: what it is rated by). A
        bundle of a tower already standing, made of upgrades, may come
        - when the cash pays for it and the current bundle both, now -
        before the current step's bundle when it
        saves more lives (the damage model at half strength, as reinforce.py
        rates purchases, over the round being played, the next and the
        weakest of the look-ahead) per share of the cash and of the seconds
        left before that round (clicktime.effort). Its first step is bought
        now; the plan reaches it later as "done". The rest of the plan keeps
        its order.

        Rated once per board and round (Executor._rated), and only when such
        a bundle exists."""
        if self.idx >= len(self.plan) or cash is None or rnd is None:
            return None
        bundles = self._plan_bundles(rnd)
        current = self.plan[self.idx].get("id")
        if len(bundles) < 2 or current not in bundles:
            return None
        ahead = [tid for tid, steps in bundles.items()
                 if tid != current and tid in self.g.towers
                 and all(st["do"] == "upgrade" for _, st in steps)]
        if not ahead:
            return None
        worst = self.lookahead_worst(rnd)
        if worst is None:
            return None
        end = (getattr(self, "rules", None) or {}).get("end_round", 80)
        rounds = sorted({r for r in (rnd, rnd + 1, worst[1]) if r <= end})
        if not rounds:
            return None
        budget = CT.time_left(self, rnd, rounds[-1])

        def rate(fc, towers):
            now = RF.board(self)
            half = 1.0 / RF.TARGET_MARGIN
            base = fc.leaks(now, rounds, half)
            if not base:
                return None                    # nothing leaks: the order does not matter
            spot = None
            first = self.plan[self.idx]
            if first["do"] == "place" and not self.at_tower_cap():
                spots = self.pick_spots(first["kind"], first, n=1)
                spot = self.m.cell_to_frac(spots[0][0], spots[0][1]) if spots else None
            out = {}
            for tid in [current] + ahead:
                done = self._bundle_after(bundles[tid], now, spot if tid == current else None)
                if done is None:
                    continue
                after, cost, secs = done
                leak = fc.leaks(after, rounds, half)
                if leak is not None:
                    out[tid] = (base - leak, cost, secs)
            return out

        rated = self._rated("quicker", rnd, rate)
        if not rated or current not in rated:
            return None

        def value(tid):
            saved, cost, secs = rated[tid]
            return saved / CT.effort(cost, secs, cash, budget)
        mine, best = value(current), None
        for tid in ahead:
            if tid not in rated:
                continue
            saved, cost, secs = rated[tid]
            # only a bank that pays for both: then the order is a question of
            # time alone, and the step put first takes no cash the current
            # one needs. With less, the Park Path build (tests/
            # test_apopalypse_offline.py) lost rounds 16-34 in the check:
            # early upgrades pulled ahead delayed placements the model,
            # rating standard rounds, undervalued against Apopalypse's.
            if saved < RF.MIN_SAVED or cost + rated[current][1] > cash:
                continue
            v = value(tid)
            if v > mine and (best is None or v > best[0]):
                best = (v, tid)
        if best is None:
            return None
        tid = best[1]
        saved, cost, secs = rated[tid]
        c_saved, c_cost, c_secs = rated[current]
        why = (f"{tid}'s steps save {saved:.0f} lives for ${cost:.0f} in about {secs:.0f} s of "
               f"clicking, {current}'s {c_saved:.0f} for ${c_cost:.0f} in about {c_secs:.0f} s "
               f"(${cash:.0f} in hand, about {budget or 0:.0f} s to round {rounds[-1]})")
        return bundles[tid][0][0], why

    def plan_exhausted(self):
        """True once the last tick found nothing left in the plan or fill."""
        return getattr(self, "waiting", None) == PLAN_EXHAUSTED

    def _set_aside_blocked(self, st):
        """Put plan step st aside (self.deferred, retried every tick) when
        waiting on it would strand cash; returns True when it did.

        Two kinds of mode cannot afford to wait on a step that more cash will
        not unblock:
        - no income (Deflation, `buy_all_upfront`): every dollar must be spent
          before the first round - Cracked Deflation started round 31 with
          $14,060 unspent behind an exit spike that had nowhere to go;
        - continuous sends (Apopalypse, `continuous`): the bloons never stop
          for the plan - Polyphemus (2026-10-27) waited on `su1 -> 3-0-2`
          (the click had no effect) and then on an exit spike with 8 refused
          spots while $2k grew to $15k, and lost 285 lives in one wave.
        A step with no legal spot ("spot") is set aside in both, and so is a
        step on a tower or researched spot under a shut pane ("pane": Covered
        Garden's glass opens over one garden quarter per round, so the step
        can go through only every fourth round); an upgrade
        whose click did nothing ("noeffect") or whose price could not be read
        ("unread") only while rounds keep coming, where one attempt is all
        the time there is (Game.upgrade already holds such a retry back for
        30 s and more).

        Rounds keep coming in every mode the bot plays, not just Apopalypse:
        it starts each round as soon as the last one ends (holding Play only
        briefly, Match._hold_round), so a step stuck on something
        more cash will not fix strands cash there too. Spillway Medium
        (2026-11-03) waited on "sb3 -> 2-0-4 (unread)" in round 38 with
        $2,013 in hand, and two rounds later a MOAB its own blimp check had
        called short went through. So the rule now holds
        everywhere except no-income modes, which buy everything before round
        one and only need the "spot" case.

        A set-aside placement's later steps for the same tower stay in the
        plan, at their own places: when the plan reaches one while the tower
        is still not placed, it is set aside too (_waits_for_set_aside_place)
        rather than skipped for good (no such tower yet), and tick() tries a
        tower's set-aside steps one at a time, in plan order.

        They used to be taken out of the plan at once and tried every tick
        side by side. Alpine Run CHIMPS (2026-11-07 07:48): v1's spot was
        refused, "v1 -> 0-2-0" and "v1 -> 4-2-0" (plan step 20) went aside
        with it, and once v1 stood the 4-2-0 step bought Bigger Radius,
        Jungle Drums and Primary Training ($2,915) while 0-2-0 waited for
        Radar Scanner - all ahead of plan step 15, r1's MOAR Glaives, which
        was bought only by the blimp check in round 36; round 40's MOAB
        leaked."""
        reason = self.g.fail_reason
        if self.rules.get("buy_all_upfront"):
            blocking = ("spot", "pane")
        else:
            blocking = ("spot", "noeffect", "unread", "pane")
        if reason not in blocking:
            return False
        if reason == "noeffect" and self._keep_waiting(st):
            return False
        log.info("plan step %d %s is blocked (%s) - set aside, the plan goes on", self.idx, st, reason)
        self.deferred.append(st)
        self.idx += 1
        return True

    def _waits_for_set_aside_place(self, st):
        """True when plan step st works on a tower (its `id`) that does not
        stand yet because its placement is in self.deferred: st then waits
        behind that placement instead of being skipped (see
        _set_aside_blocked)."""
        tid = st.get("id")
        if not tid or st.get("do") == "place":
            return False
        if not any(d.get("do") == "place" and d.get("id") == tid for d in self.deferred):
            return False
        return tid not in self.g.towers

    # One-life games give a standing plan tower's upgrade this many clicks that
    # did nothing, on separate ticks, before it is set aside.
    NOEFFECT_TRIES_ONE_LIFE = 3

    def _keep_waiting(self, st):
        """Should the plan keep waiting on upgrade step st although its click
        had no effect? Only in one-life games (Impoppable, CHIMPS) and only
        for a tower of the plan that stands:
          * a village step that buys the discount or the Monkey Intelligence
            Bureau (VILLAGE_KEYSTONES) is never set aside;
          * any other is set aside after NOEFFECT_TRIES_ONE_LIFE clicks that
            did nothing, on separate ticks. Each try re-reads the panel and
            corrects the tower's tiers from its prices first (Game._upgrade
            -> Game._resync_tiers), so a miscounted tier cannot fail twice.
        Castle Revenge Impoppable (2026-11-04): "upgrade v1 path 3 not bought
        (panel [1800,300,600], cash 766)", and the next tick set "v1 to 2-0-2"
        aside after that one click. The discount was never bought, and the
        game was lost at round 78."""
        if not self.rules.get("one_life") or st.get("do") != "upgrade" or not st.get("to"):
            return False
        p = self.g.towers.get(st.get("id"))
        if p is None or p.kind == "hero":
            return False
        try:
            target = parse_cross(st["to"])
        except (KeyError, ValueError):
            return False
        if p.kind == "village":
            buys = [VILLAGE_KEYSTONES[k] for k in VILLAGE_KEYSTONES
                    if target[k[0] - 1] >= k[1] > p.tiers[k[0] - 1]]
            if buys:
                if ("keystone", self.idx) not in self._notes():
                    self._notes().add(("keystone", self.idx))
                    log.warning("plan step %d %s: the click had no effect, but %s is never set aside "
                                "in a one-life game - trying again", self.idx, st, buys[0])
                return True
        key = (p.tid, st["to"])
        ticks = self.__dict__.setdefault("noeffect_ticks", {}).setdefault(key, set())
        ticks.add(getattr(self, "tick_no", 0))
        nxt = self._next_path(p, target)
        clicks = self._noeffect_clicks(p.tid, nxt[0]) if nxt else None
        tries = len(ticks) if clicks is None else min(clicks, len(ticks))
        if tries < self.NOEFFECT_TRIES_ONE_LIFE:
            if ("noeffect", key, tries) not in self._notes():     # once per try, not per tick
                self._notes().add(("noeffect", key, tries))
                log.info("plan step %d %s: click without effect %d of %d - kept in the plan", self.idx,
                         st, tries, self.NOEFFECT_TRIES_ONE_LIFE)
            return True
        return False

    def _notes(self):
        """The set of things already logged once (shared with the threat checks)."""
        if not hasattr(self, "noted"):
            self.noted = set()
        return self.noted

    def plan_claim(self, cash, rnd):
        """What the plan step waiting for cash (reinforce.waiting_plan_step:
        the current step costs more than `cash`) keeps out of surplus()'s
        hands: (dollars kept, step index, step, its cost, crisis) or None when
        no step waits or the step holds nothing.

        Reinforce.best has left the cash to such a step since Castle Revenge
        and Haunted (094f8de), but surplus() never looked at it. Ancient
        Portal Impoppable (2026-11-05, lost at round 94 with $17,562 in hand)
        reached plan step 25, Perma-Spike (sp1 2-0-5, $36,000), at round 63
        and never bought it: every few seconds reinforce said "the cash stays
        for plan step sp1 2-0-5" and surplus spent the same cash on ninja and
        sniper tiers the model never rated - $64,844 of them over 31 rounds.
        With the step as the bank's floor it was affordable at round 75.

        The step keeps:
          * its whole cost when it has no `round` of its own - the plan wants
            it as soon as the cash is there;
          * cost less the income until its `round` (reinforce.release) when it
            has one - the rest is spare until then;
          * in a crisis of the round being played (weak_now) only what income
            cannot rebuild by the step's round or the next one, as
            reinforce.best keeps - and the rest goes only to a purchase that
            lifts the round being played (_lifts_now);
          * nothing when it cannot be paid, from the cash and the income until
            then (reinforce.payable_by), before the round it must stand for:
            the next round in a crisis of the round being played (what the
            crisis rule pays it by), else the weakest look-ahead round under
            WEAK_MARGIN. Quad ABR kept $10-20k for a Glaive Lord no income
            could pay before the round-63 rush (7919935); and in round 94 of
            Ancient Portal itself, rated 0.45 with $17,562 against the $36,000
            step, the crisis rule alone keeps $35,000 - the whole bank - for a
            step no income can pay before round 95. The round being played is
            never the round to pay it by: no income arrives before its bloons,
            and a step short of cash now is for the rounds after it;
          * nothing where no income comes (Deflation): saving cannot make the
            step affordable later, as _threat_tick says of its answers.

        In a one-life mode (Impoppable, CHIMPS) the step always has its
        claim: it is the author's answer to the rounds that end the game, and
        a leak is the game. With lives to spare the plan is a guide - surplus's
        tiers between its steps are what keeps the Easy and XP builds of the
        threat simulation (tools/simulate_threats.py) on budget - so there the
        step claims the bank only while Match is reinforcing (`lookahead_weak`,
        set by the match loop before surplus runs: the damage model rates a
        look-ahead round under WEAK_MARGIN), the same state in which reinforce
        leaves the cash to it (094f8de, Haunted Half Cash); the simulation,
        which has no match loop, never sets it and is unchanged. Reinforce
        leaving the cash is not enough on its own: Workshop Medium (2026-11-05)
        said "the cash stays for plan step b1 4-0-2 ($2,000)" from round 16
        to 39, surplus spent that cash on nine extra 3-0-2 boomerangs ($1,681
        each) the model rated at nothing, and round 40's MOAB took all 150
        lives with the MOAB Press never bought."""
        if self.rules.get("income") is False:
            return None
        if not self.rules.get("one_life") and not getattr(self, "lookahead_weak", False):
            return None
        wait = RF.waiting_plan_step(self, cash)
        if wait is None:
            return None
        rnd = rnd or 0
        worst = self.lookahead_worst(rnd)
        step, cost = wait
        idx = getattr(self, "idx", None)
        due = step.get("round")
        crisis = self.weak_now(rnd)
        # the round the step must be paid before to keep anything: the next
        # one in a crisis (the crisis rule pays it by then), else the weakest
        # look-ahead round under WEAK_MARGIN - and never the round being
        # played, which no income reaches
        pay_by = None
        if crisis:
            pay_by = rnd + 1
        elif worst is not None and worst[0] < RF.WEAK_MARGIN:
            pay_by = max(worst[1], rnd + 1)
        if pay_by is not None and RF.payable_by(self, cost, cash, pay_by, rnd) is False:
            note = ("surplus-unpayable", idx, pay_by)
            if note not in self._notes():
                self.noted.add(note)
                log.info("surplus: plan step %s %s ($%d) cannot be paid before round %d (%s) from $%d "
                         "and the income until then - it keeps nothing", idx, step, cost, pay_by,
                         f"round {rnd} is weak" if crisis else f"rated {worst[0]:.2f}", cash)
            return None
        if crisis:
            keep = RF.release(self, cost, due or rnd + 1, rnd)
        elif due:
            keep = RF.release(self, cost, due, rnd)
        else:
            keep = cost
        note = ("surplus-claim", idx, bool(crisis))
        if note not in self._notes():
            self.noted.add(note)
            by = due or (rnd + 1 if crisis else None)
            log.info("surplus: $%d kept for plan step %s %s: $%d, %s%s", keep, idx, step, cost,
                     f"income pays ${cost - keep:.0f} by round {by}" if by else "no round: all of it until it is bought",
                     f"; round {rnd} is weak: the rest goes to what lifts it" if crisis else "")
        return keep, idx, step, cost, crisis

    def _lifts_now(self, step, cost, rnd):
        """Does the purchase `step` (one tier, or a placement) lift the round
        being played, judged as reinforce.lift judges a crisis purchase: the
        lowest of the round being played, the next and the weakest look-ahead
        round moves by MIN_LIFT or more? False when it does not or cannot be
        rated (no forecast, no spot): a purchase nobody can rate does not
        spend the cash a plan step is waiting for."""
        fc = self._forecast()
        if fc is None or rnd is None:
            return False
        option = RF.plan_option(self, step, cost)
        if option is None:
            return False
        worst = self.lookahead_worst(rnd)
        before, after = RF.lift(fc, RF.board(self), option.towers, rnd, worst[1] if worst else rnd, True)
        return (after or 0.0) - (before or 0.0) >= RF.MIN_LIFT

    def plan_first(self):
        """True while a `plan_first: true` build still has plan steps left:
        then the plan owns the bank, and nothing off the plan - reinforce,
        the blimp check's own buys, surplus() - spends it. Threat answers
        (the build's `answers`) still may.

        The damage model picks those off-plan buys, and in CHIMPS it has been
        wrong about which round is weak. Cracked CHIMPS (2026-11-07), built
        from a community guide, lost round 95 that way: at round 69 reinforce
        spent $16k on an Elite Defender the plan never asked for, which put
        the Carrier Flagship off from round 72 to 82, and then about $30k
        went to ten tier-1/2 snipers and three aces while the plan's Glaive
        Lord was never bought. A hand-written build from a proven strategy
        says so with this flag; once its plan is done the usual spending
        comes back.

        There is no crisis exception. One was tried (Match let reinforce
        spend in a crisis of the round being played, after Skates CHIMPS
        lost round 75 twice) and taken out the same morning: on Alpine Run
        CHIMPS (2026-11-07 08:38) the damage model called round after round
        a crisis, reinforce spent the plan's cash on snipers each time, and
        the Glaive Lord ($35,100) was never bought. Skates' real cause was
        a far threat's hold taking the whole bank (_far_keep says why, and
        now lets it go).

        The one narrow exception is plan_first_yields: a waiting step that
        cannot be paid before a near round rated under YIELD_MARGIN lets
        reinforce spend for that round (Moon Landing CHIMPS, 2026-11-09)."""
        strat = getattr(self, "strat", None)
        if not (isinstance(strat, dict) and strat.get("plan_first")):
            return False
        return getattr(self, "idx", 0) < len(getattr(self, "plan", None) or [])

    # plan_first_yields: how weak and how near a round must be for a plan_first
    # build's unreachable plan step to give way to reinforcing
    YIELD_MARGIN = RF.CRISIS_MARGIN   # rated under this: a crisis round (forecast.py)
    YIELD_ROUNDS = 4                  # at most this many rounds after the one being played
    YIELD_FLOOR = 0.10                # rated at most this in a mode with lives: no bloon depth needed

    def plan_first_yields(self, cash, rnd, deep=True):
        """Does a plan_first build's plan let reinforce spend this tick? True
        only when all of these hold:

          * plan_first() is on and its current step waits for cash
            (reinforce.waiting_plan_step: it costs more than `cash`);
          * the damage model's weakest look-ahead round (lookahead_worst) is
            rated under YIELD_MARGIN and comes at most YIELD_ROUNDS after the
            round being played;
          * the step cannot be paid before that round (the next one, when it
            is the round being played) from `cash` and the income until then
            (reinforce.payable_by False);
          * `deep` (Match: the last round's bloons got far along the route),
            or the mode has lives (not one_life) and the weak round is rated
            YIELD_FLOOR or less (see the last paragraph).

        Then waiting cannot bring the step in time for the round the game is
        at stake in, and the cash it waits for is better spent on what lifts
        that round - reinforce.best picks it, and lets go of the step by the
        same payable_by test (plan_keeps_claim). Moon Landing CHIMPS
        (2026-11-09) lost round 59 that way: from round 50 the model rated
        it 0.10, the next step was the Archmage (w1 5-0-2, $46,925), and
        "idle with $9388: plan step 20 w1 5-0-2 -> wait" was the last line
        before the defeat. Spring Spring CHIMPS lost round 99 with $16k
        idle for an unaffordable Cripple MOAB (2026-11-08).

        Narrow on purpose (Executor.plan_first: the crisis exception that
        let reinforce spend in any crisis of the round being played was
        taken out after Alpine Run CHIMPS, 2026-11-07, spent its Glaive
        Lord's cash on snipers for rounds rated 0.59-0.99 that all passed).
        A step income can still deliver before the weak round keeps all of
        its cash; a weak round rated over YIELD_MARGIN, or further off than
        YIELD_ROUNDS, does not count; unknown income (payable_by None) or no
        rating means the plan keeps the cash.

        The bloon depth cannot see a round that kills in one go. X Factor
        Half Cash (2026-11-09, hard_ninja_alch_sun) lost all 78 lives to
        round 78's 72 camo ceramics at once (each leaked ceramic costs 104
        lives): no life was lost from round 36 to 77, the bloons never got
        past 81% of the route, yet the model rated round 78 at 0.06 from
        round 69 on, and the bot idled with $11-17k for plan step h1 4-2-0
        ($21,600) that income could not bring before round 79. A Radar
        Scanner village ($3,725) beside the Dartship lifts round 78 to 0.62
        in the model and was affordable from round 74 (radar_option offers
        it). So in a mode with lives a weak round rated at the model's floor
        lets the step yield without the depth. Not in CHIMPS: there the won
        games rated rounds at 0.06-0.10 often (Cracked rounds 52-58 with
        $15-26k waiting for its Glaive Lord, End Of The Road, Spice Islands,
        Adora's Temple) and their plan cash stays behind the depth. In the
        Half Cash wins of 2026-11-08/09 (Adora's Temple, Spillway) the floor
        rule fires only in rounds 23-37 with under $650 in hand; Spillway's
        win held round 78 rated 0.14 with the same build, hence the 0.10."""
        if cash is None or rnd is None or not self.plan_first():
            return False
        rules = getattr(self, "rules", None) or {}
        if rules.get("income") is False:
            return False          # no income: saving is all the step has
        wait = RF.waiting_plan_step(self, cash)
        if wait is None:
            return False
        worst = self.lookahead_worst(rnd)
        if worst is None or worst[0] is None or worst[1] is None:
            return False
        margin, weak = worst
        if margin >= self.YIELD_MARGIN or weak - rnd > self.YIELD_ROUNDS:
            return False
        if not deep and (rules.get("one_life") or margin > self.YIELD_FLOOR):
            return False          # shallow bloons: only a floor rating in a mode with lives counts
        step, cost = wait
        pay_by = max(weak, rnd + 1)   # the round being played: no income reaches it
        if RF.payable_by(self, cost, cash, pay_by, rnd) is not False:
            return False
        note = ("plan-first-yields", getattr(self, "idx", None), weak)
        if note not in self._notes():
            self.noted.add(note)
            log.warning("plan_first: plan step %s ($%.0f) cannot be paid before round %d from $%d and the "
                        "income until then, and the damage model rates round %d at %.2f - reinforce may "
                        "spend for that round", step, cost, pay_by, cash, weak, margin)
        return True

    def surplus(self, cash, rnd):
        """Cash is piling up while the plan waits: buy damage anyway.

        1. next tier on an existing tower's own path (biggest investment first),
           respecting crosspaths, tower XP locks and the mode's tower filter
        2. another copy of the strategy's main tower
        Never violates constraints (kind_allowed) and never sells. Never
        spends cash that the last tick() held back for a threat's answer:
        that money is being saved for a bloon the defence cannot pop yet.
        Nor the cash a plan step is waiting for (plan_claim): what is left
        above its claim is spare, and in a crisis of the round being played
        only a purchase that lifts that round may have it."""
        self.now_round = rnd
        if cash is None or getattr(self, "saving_for_threat", False) or self.plan_first():
            return False
        if getattr(self, "held_cash", 0):
            # part of the cash kept for a far threat while this round is weak (_hold_for)
            cash = max(0, cash - self.held_cash)
        claim = self.plan_claim(cash, rnd)
        rated = False     # only purchases that lift the round being played
        if claim:
            cash = max(0, cash - claim[0])
            rated = claim[4]
        # An XP build (strategies/generated: `xp_target`) puts surplus into the
        # tower it levels up first - tower XP follows invested cash - and only
        # then into helpers, side paths or the opener.
        target = self.strat.get("xp_target") if isinstance(getattr(self, "strat", None), dict) else None
        # with no income the plan's crosspath caps would strand cash: the
        # leading path may go further (as reinforce.py does)
        for p, t, cost in self.upgrade_choices(first=target, past_plan=bool(self.rules.get("buy_all_upfront"))):
            if cost > cash:
                continue
            to = "-".join(map(str, t))
            step = {"do": "upgrade", "id": p.tid, "to": to}
            if rated and not self._lifts_now(step, cost, rnd):
                continue
            with self.why("surplus", f"spare cash: {p.tid} -> {to}"):
                r = self.try_step(step, cash, rnd)
            if r in ("bought", "progress"):
                log.info("surplus: upgraded %s -> %s", p.tid, p.crosspath)
                return True
        main = target if target and self._allowed(target) else self._main_kind()
        if main and not rated and self.clear_obstacle(cash, main):
            return True       # (an obstacle cleared lifts no round by itself)
        if main and cash >= self.g.price(main):
            step = {"do": "place", "kind": main, "role": "dps", "segment": [0.2, 1.0]}
            if rated and not self._lifts_now(step, self.g.price(main), rnd):
                return False
            with self.why("surplus", f"spare cash: another {main}"):
                r = self.try_step(step, cash, rnd)
            if r == "bought":
                log.info("surplus: placed another %s", main)
                return True
        return False

    # -- towers that aim at the mouse --------------------------------------
    # The Heli Pilot ("Follow Touch") and the Dartling Gunner aim at the mouse
    # by default - and the bot's mouse is all over the screen, placing and
    # upgrading. A heli is set to Lock in Place where it was placed (spot
    # picking chose that spot for its coverage), and to Pursuit, which chases
    # the bloons, once it has 2xx (the upgrade that unlocks Pursuit). A
    # strategy that sets a tower's targeting itself keeps it. Dartlings keep
    # Follow Touch: the match parks the cursor on the busiest stretch of track
    # while the bot is idle (Match._park_cursor).
    HELI_PURSUIT_TIER = 2

    def _explicit_target(self, p):
        """Does the plan set this tower's targeting itself?"""
        return any(st.get("do") == "target" and st.get("id") == p.tid for st in self.plan + self.fill)

    def _aim(self, p):
        """Set a heli's targeting so it stops following the mouse."""
        if p.kind != "heli" or self._explicit_target(p):
            return
        want = "pursuit" if p.tiers[0] >= self.HELI_PURSUIT_TIER else "lock"
        if getattr(p, "aim", None) in (want, "failed " + want):
            return
        try:
            ok = self.g.target(p, want)
        except Exception:          # targeting is a nicety: never cost a game over it
            log.exception("setting %s's targeting failed", p.tid)
            ok = False
        p.aim = want if ok else "failed " + want
        if ok:
            log.info("%s targeting: %s (no longer follows the mouse)", p.tid, "Pursuit" if want == "pursuit" else "Lock in Place")
        else:
            log.warning("%s: could not find the %s targeting - left as it was", p.tid, want)

    # -- removable obstacles ----------------------------------------------
    # Obstacles a player pays to remove with the round's cash (Peninsula's
    # kelp, Dark Castle's trees, Quad's trusses...): the ground under them
    # becomes land or water for more towers. The map file lists them, their
    # price and where to click (mapgeom.removables); placement counts the
    # freed ground once one is bought (valid_spots(removed=...)).
    REMOVAL_MIN_CELLS = 4       # it must free at least this much legal ground for the tower
    REMOVAL_TRIES = 2           # attempts per obstacle before it is left alone for the game

    def _obstacles(self):
        """This map's obstacles that can be bought now, not yet removed.

        Obstacles whose area is simply deleted ("uncovered": the ground
        beneath shows) count too: clear_obstacle measures the room each one
        frees with valid_spots(removed=...), which models what lies beneath.
        Leaving them out cost Mushroom Grotto ABR (2026-11-04): its main
        mushroom ($400) frees ~1,050 ninja cells on a map with 165, and the
        game was lost at round 63 with $34k in the bank and no spot left."""
        if getattr(self, "_obstacle_list", None) is None:
            from . import mapgeom
            name = getattr(self.m, "name", "") or ""
            name = name[:-len(" reverse")] if name.endswith(" reverse") else name
            try:
                self._obstacle_list = [r for r in mapgeom.removables(name, self.m.playfield)
                                       if r["available"] and r.get("frac")]
            except Exception:       # a map-file problem must never cost a game
                self._obstacle_list = []
        return [r for r in self._obstacle_list
                if r["id"] not in self.removed and self.removal_fails.get(r["id"], 0) < self.REMOVAL_TRIES]

    def _named_obstacle(self, name):
        """The removable obstacle a `do: clear` step names (by the map file's
        name or id), removed or not; None when the map has no such one."""
        if not name:
            return None
        self._obstacles()          # loads the map's list once
        return next((r for r in getattr(self, "_obstacle_list", None) or []
                     if name in (r.get("name"), r.get("id"))), None)

    def _try_clear(self, step, cash):
        """A build's `do: clear, obstacle: <name>` step: pay to remove that
        obstacle as soon as the cash covers its price - 'done' once it is
        gone, 'wait' while the cash is short, 'bought' when it was just
        removed, 'skip' when the map has no such obstacle or the removal
        failed REMOVAL_TRIES times.

        Removal used to be surplus spending only (clear_obstacle), when a
        tower kind had run out of ground. A build that stands on what lies
        beneath an obstacle needs it at a set point of its plan: the
        Cracked CHIMPS strategy (bloon.games, 2026-11-07) clears the central
        rock for the pond under it before its first buccaneer."""
        r = self._named_obstacle(step.get("obstacle"))
        if r is None or not r.get("frac"):
            log.warning("clear step %s: no such removable obstacle on this map - skipped", step)
            return "skip"
        if r["id"] in self.removed:
            return "done"
        if self.removal_fails.get(r["id"], 0) >= self.REMOVAL_TRIES:
            return "skip"
        if cash is None or cash < r["cost"]:
            return "wait"
        log.info("clearing obstacle %s ($%s) for the plan", r["name"], r["cost"])
        if self.g.remove_obstacle(*r["frac"], r["cost"], name=r["name"]):
            self.removed.append(r["id"])
            return "bought"
        self.removal_fails[r["id"]] = self.removal_fails.get(r["id"], 0) + 1
        return "wait"

    def clear_obstacle(self, cash, kind):
        """Surplus spending: when the cash covers an obstacle's price and the
        next tower too, buy the removal that frees the most legal ground for
        `kind`. Returns True when one was bought."""
        if self.no_removals or not kind:
            return False
        affordable = [r for r in self._obstacles() if cash >= r["cost"] + self.g.price(kind)]
        if not affordable:
            return False
        from . import placement as PL
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        where = {"land"} if self.land_only else None
        base = PL.valid_spots(self.m, kind, None, placed, where=where, removed=tuple(self.removed))
        if base is None:
            return False
        best, gain = None, 0
        for r in affordable:
            # by id: on High Finance every "Removable" by name meant the same
            # one (a $350 strip at the top edge freeing nothing), so no
            # obstacle was ever bought while the defence had 36 legal cells
            after = PL.valid_spots(self.m, kind, None, placed, where=where, removed=tuple(self.removed) + (r["id"],))
            g = int((after & ~base).sum()) if after is not None else 0
            if g > gain:
                best, gain = r, g
        if best is None or gain < self.REMOVAL_MIN_CELLS:
            return False
        log.info("clearing obstacle %s ($%s): frees %d legal cells for %s", best["name"], best["cost"], gain, kind)
        if self.g.remove_obstacle(*best["frac"], best["cost"], name=best["name"]):
            self.removed.append(best["id"])
            return True
        self.removal_fails[best["id"]] = self.removal_fails.get(best["id"], 0) + 1
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
        its planned crosspath and $24k unspent). A tower whose leading path
        is past tier 2 may also take its side path up to tier 2 (_side_path_ok):
        that cannot turn it onto another path. Income tiers are left out
        where income pays nothing (_income_pays_nothing)."""
        towers = sorted((p for p in self.g.towers.values() if p.kind != "hero"),
                        key=lambda p: (p.kind != first, -p.spent))
        family = PRICE_FAMILY.get(self.mode, "hard")
        no_pay = self._income_pays_nothing()
        for p in towers:
            if not self._reachable(p):
                continue          # under a closed pane this round
            for path in sorted(range(3), key=lambda i: -p.tiers[i]):
                if p.tiers[path] >= 5 or self.path_blocked(p, path + 1):
                    continue
                t = list(p.tiers)
                t[path] += 1
                if sum(x > 0 for x in t) > 2 or sum(x > 2 for x in t) > 1:
                    continue
                cap = self._planned_cap(p)
                leading = p.tiers[path] > 0 and p.tiers[path] == max(p.tiers)
                if leading and cap is not None and t[path] > 2 and any(
                        cap[i] > 2 for i in range(3) if i != path):
                    # the plan's main path is another one: tier 3 here would
                    # shut it out for good. Dark Dungeons Military (2026-11-04):
                    # s1 stood at 1-2-0 on its way to 4-2-0, reinforce bought
                    # 1-3-0, and the planned Maim MOAB could never be bought.
                    leading = False
                if (cap is not None and t[path] > cap[path]
                        and not (past_plan and (leading or self._side_path_ok(p, path, cap)))):
                    continue  # past the crosspath the plan wants for this tower
                if self.account and t[path] > self.account.upgrades(p.kind)[path] and t[path] > 2:
                    continue  # known XP-locked beyond tier 2
                if no_pay and self._is_income(p.kind, t):
                    continue  # an income tier where income pays nothing (INCOME_UPGRADES)
                yield p, t, T.upgrade_cost(p.kind, path + 1, t[path], family)

    def path_blocked(self, p, path):
        """Would asking for the next tier of `path` (1-3) on tower p buy
        nothing right now? Yes when the path is capped for the game (an XP
        lock, a panel that showed it closed or maxed, four clicks without
        effect), its price was just unreadable (unread_until), another
        tower holds its tier 5 (_tier5_taken), or Game.upgrade still holds
        a retry back for it (Game._retry_at: a click with no effect is tried
        again after 30 s, then 60, 120 ... and until then the game answers
        without clicking).

        The one gate for every list of upgrades on offer: upgrade_choices
        (surplus and reinforce) and the grown ladder reinforce rates a
        standing tower at (reinforce.grown_from). The ladder used to walk
        the price table alone, so on High Finance Magic Monkeys Only
        (2026-11-05) it asked for wizard2's capped paths thirty times over
        rounds 49-54 - "did not go through (skip)" every two seconds, with
        no other purchase tried - while $3k grew to $24k and round 58 was
        rated 0.13."""
        if (p.tid, path) in self.capped:
            return True
        if time.time() < getattr(self, "unread_until", {}).get((p.tid, path), 0):
            return True
        if p.tiers[path - 1] + 1 == 5 and self._tier5_taken(p, path):
            return True
        held = (getattr(self.g, "_retry_at", None) or {}).get((p.tid, path))
        return bool(held) and time.time() < held[0]

    @staticmethod
    def _side_path_ok(p, path, cap):
        """May reinforcing (past_plan) buy the next tier of `path`, a path
        other than the tower's leading one, beyond the plan's crosspath?

        Yes when the leading path is past tier 2 - the crosspath rule then
        keeps every other path at 2 or below, so the tower's main attack
        cannot change - and `path` is the only side path the tower uses or
        the plan wants (taking a different one would shut out the plan's
        own side path: only two paths may be bought).

        Cornfield Medium (2026-11-03, solo_ace): one ace fitted on the map,
        the plan saved for its $42,500 5-2-0, and the opener sniper stood at
        its planned 4-1-0. Reinforcing found nothing it was allowed to buy
        while $4k-25k sat idle, although 4-2-0 ($450) lifted the weakest
        round of the look-ahead from 0.71 to 0.87 in the damage model."""
        lead = max(range(3), key=lambda i: p.tiers[i])
        if path == lead or p.tiers[lead] <= 2 or p.tiers[path] >= 2:
            return False
        others = [i for i in range(3) if i not in (lead, path)]
        return all(p.tiers[i] == 0 and cap[i] == 0 for i in others)

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
        must not let a round start.

        A build whose opening is its hero (`hero_opens: true` in the file)
        counts the placed hero: the Cracked CHIMPS strategy opens with Quincy
        alone on $650 (2026-11-07), and the bot refused round 6 with the hero
        standing as the plan wanted."""
        strat = getattr(self, "strat", None)
        hero_opens = isinstance(strat, dict) and bool(strat.get("hero_opens"))
        return any((p.kind != "hero" or hero_opens) and getattr(p, "verified", True)
                   for p in self.g.towers.values())
