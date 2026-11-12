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
# camo ceramics (51) or camo leads (59; ABR 30) - those need "strong camo"
CAMO_LEAD_BULK = 5      # camo leads in one round that make it a strong-camo round


def _first_bulk_camo_lead(rounds):
    """The first round (data/rounds.json's per-round groups) that sends at
    least CAMO_LEAD_BULK camo leads, or None.

    ABR's first camo lead comes alone on round 24, and dating the
    strong-camo threat by first appearance made every ABR opening (a Fast
    Track start at round 22) buy a Radar Scanner village for it, though a
    ninja with acid pops one camo lead: Pat's Pond and Bloody Puddles ABR
    (2026-11-10) spent $3.7-4.3k of a $5k opening on it and lost rounds
    30 and 23. The bulk comes on ABR round 30 (9) and 59 (50); standard
    rounds start at 59 (50) either way."""
    found = []
    for r, v in rounds.items():
        n = sum(g.get("count", 0) for g in v.get("groups", [])
                if g.get("camo") and str(g.get("bloon", "")).lower().startswith("lead"))
        if n >= CAMO_LEAD_BULK:
            found.append(int(r))
    return min(found) if found else None


try:
    import json as _json
    from pathlib import Path as _Path
    _rounds = _json.loads((_Path(__file__).resolve().parents[1] / "data" / "rounds.json")
                          .read_text(encoding="utf-8"))
    _fa = _rounds["first_appearance"]
    _STD["camo_ceramic"], _ABR["camo_ceramic"] = _fa["standard"]["camo_ceramic"], _fa["abr"]["camo_ceramic"]
    _STD["camo_lead"], _ABR["camo_lead"] = (_first_bulk_camo_lead(_rounds[k]) or _fa[k]["camo_lead"]
                                            for k in ("standard", "abr"))
except (OSError, ValueError, KeyError):
    _STD.update(camo_ceramic=51, camo_lead=59)
    _ABR.update(camo_ceramic=51, camo_lead=30)
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
    # druid 2-3: Druid of the Jungle - its vines take whole non-MOAB bloons
    # anywhere on the map (bazaar_half_cash's round-63 answer, 2026-11-09)
    "rush": [("tack", 1, 4), ("bomb", 3, 3), ("ninja", 1, 4), ("super", 0, 0), ("wizard", 2, 3),
             ("dartling", 0, 0), ("boomerang", 1, 3), ("ice", 3, 3), ("druid", 2, 3)],
    "zomg": [("tack", 1, 5), ("bomb", 2, 4), ("sniper", 1, 4), ("super", 1, 3), ("heli", 1, 4), ("spike", 3, 4),
             ("boomerang", 1, 5), ("druid", 2, 4), ("ninja", 3, 4)],
    "ddt": [("sniper", 1, 4), ("bomb", 2, 4), ("heli", 1, 4), ("super", 1, 3), ("spike", 3, 4),
            ("ninja", 3, 4), ("boomerang", 1, 4), ("dart", 3, 4)],
    # spike 5-x-x Super Mines and ace x-x-5 Flying Fortress: the damage model
    # (phase 2, 2026-11-12) rates one Super Mines alone at 2-9 on Impoppable
    # rounds 95-100 on Sunset Gulch, Sunken Columns and Bloonarius Prime, and
    # a Flying Fortress (with Etienne's camo) at 2.4-10 on Firing Range; the
    # late-game Impoppable map builds carry one of them (an answer to the
    # BAD answers the ZOMGs inside it too).
    "bad": [("super", 1, 4), ("bomb", 2, 5), ("sniper", 1, 5), ("ninja", 3, 5), ("spike", 3, 5), ("spike", 1, 5),
            ("ace", 3, 5)],
}
ANSWERS["zomg"] += [a for a in ANSWERS["bad"] if a not in ANSWERS["zomg"]]


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
             "not_maps",   # skipped on these maps (Executor._step_allowed), e.g. [Covered Garden]
             "at",         # exact spot [fx, fy] (screen fractions) from a map's own build
             "lane",       # "blimp": score only the track blimps ride (Executor.pick_spots)
             "obstacle",   # do: clear - the removable obstacle's name in the map file
             "name",       # do: ability - the ability (TARGETED_ABILITIES)
             "when",       # do: ability - {round, hero_level_min, hero_level_max, min_margin}
             "min_value"}  # do: ability - the target's least worth (table price of its tiers)
# min_margin: the damage model must rate every round left (the one being
# played to the mode's last) at least this high on the board without the
# target, or the step waits (Executor._sacrifice_margin).
ABILITY_WHEN_KEYS = {"round", "hero_level_min", "hero_level_max", "min_margin"}


def _targeted_abilities():
    """{ability name: {"hero", "level"}} for the abilities a `do: ability`
    step may press: a hero ability that is pressed and then given a tower
    with a click (Executor._try_ability, Game.targeted_ability). The hero
    and the unlock level come from towers.HEROES."""
    out = {}
    for hero, h in T.HEROES.items():
        for ab in h.get("abilities", []):
            if ab["name"] in ("Blood Sacrifice",):
                out[ab["name"]] = {"hero": hero, "level": ab["level"]}
    return out


TARGETED_ABILITIES = _targeted_abilities()
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
        for m in st.get("not_maps") or ():
            try:
                from .account import canonical_map
                canonical_map(m)
            except KeyError:
                probs.append(f"not_maps: {m!r} is not a real map [{where}]")
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
        if do not in ("place", "upgrade", "target", "sell", "clear", "ability"):
            probs.append(f"{where}: unknown step {do!r}")
            continue
        if do == "ability":
            probs += _ability_problems(strat, where, st, placed)
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


def _ability_problems(strat, where, st, placed):
    """Problems of one `do: ability` step (validate): a known targeted
    ability of the strategy's own hero, given a placed, non-hero tower,
    only in the plan (an answer or fill step would fire it at any time)."""
    probs = []
    spec = TARGETED_ABILITIES.get(st.get("name"))
    if spec is None:
        return [f"{where}: unknown targeted ability {st.get('name')!r} "
                f"(known: {', '.join(sorted(TARGETED_ABILITIES))})"]
    hero = constraints(strat).get("required_hero") or strat.get("hero")
    if hero != spec["hero"]:
        probs.append(f"{where}: {st['name']} is {spec['hero']}'s ability, the strategy's hero is {hero}")
    if not where.startswith("plan"):
        probs.append(f"{where}: an ability step belongs in the plan")
    tgt = st.get("target")
    if not tgt or tgt not in placed:
        probs.append(f"{where}: ability target {tgt!r} is never placed")
    elif placed[tgt] == "hero":
        probs.append(f"{where}: ability target {tgt!r} is the hero")
    when = st.get("when") or {}
    if not isinstance(when, dict) or set(when) - ABILITY_WHEN_KEYS:
        probs.append(f"{where}: ability `when` takes only {sorted(ABILITY_WHEN_KEYS)}")
    elif when.get("hero_level_min") is not None and when["hero_level_min"] < spec["level"]:
        probs.append(f"{where}: hero_level_min {when['hero_level_min']} is below "
                     f"{st['name']}'s unlock level {spec['level']}")
    if isinstance(when, dict) and when.get("min_margin") is not None and \
            not (isinstance(when["min_margin"], (int, float)) and when["min_margin"] > 0):
        probs.append(f"{where}: min_margin must be a positive number (a damage-model margin)")
    if st.get("min_value") is not None and not (isinstance(st["min_value"], int) and st["min_value"] > 0):
        probs.append(f"{where}: min_value must be a positive whole number of dollars")
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
        # an ability step's `target` is the tower it is given, not a targeting mode
        tmode = st.get("target") if st.get("do") != "ability" else None
        for tm in (tmode, st.get("mode") if st.get("do") == "target" else None):
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
        # plan placements with no ground, waiting for an obstacle to be
        # bought (_clear_for_place): step key -> (the obstacles gone when it
        # was chosen, the obstacle's entry or None when none helps)
        self.clear_wait = {}
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
        self.pane_empty = {}       # step key -> open panes that left its tower no spot (_wait_for_next_pane)
        self.retry_at = {}         # step key -> time before which it is not retried
        self.hero_misses = 0       # times the hero ran out of accepted spots
        self.learned_blocks = 0
        self.upgrade_fails = {}    # (tid, path) -> non-XP failures this game
        self.panel_price = {}      # (tid, path, tier) -> price the panel asked (above table)
        self.last_try = 0.0
        # `do: ability` steps (_try_ability): the match's AbilityPlanner
        # (Match sets it: its hotkey order and the hero's placement round),
        # presses made per step, and the round the hero was placed in
        self.abil = None
        self.ability_tries = {}
        self.hero_round = None
        self.blocked = np.zeros(model.heat.shape, bool)  # this game's no-go cells
        self.layer_blocked = {}   # refusal layer -> no-go cells for that layer's towers only
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
        they only delayed the rest of the plan.

        A step with `not_maps: [...]` is skipped on those maps: a tower kind
        that has no ground there. Covered Garden Apopalypse (2026-11-09, lost
        round 45 with apopalypse_ninja_sniper) spent 15 s of round 45 on seven
        refused clicks for the exit spike - the panes leave a spike nowhere
        that reaches the track (data/map_fit.json: spike 0.17 early, 0.0
        late) - while the MOABs came; apopalypse_apache_spikes skips its
        spikes there and its fill buys helis instead."""
        only = step.get("modes")
        if only and self.mode not in only:
            return False
        if step.get("not_maps") and self._on_map(step["not_maps"]):
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

    def _on_map(self, maps):
        """Is this game's map one of `maps` (names compared canonically)?"""
        from .account import canonical_map
        here = getattr(self.m, "name", None)
        if not here:
            return False
        here = canonical_map(here)
        return any(canonical_map(m) == here for m in maps)

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
            # Ground a gear turns over (Geared) changes with each turn: a
            # refusal there, learned, would bar the cell in every pose for
            # every later game (audit 2026-11-12: gear ground eroded).
            ground = mapgeom.rotor_ground(self.m)
            if ground is not None and 0 <= cy < ground.shape[0] and 0 <= cx < ground.shape[1]                     and ground[cy, cx]:
                log.info("spot (%d,%d) on a gear refused - not learned (the gear turns)", cx, cy)
                return
        except Exception:
            pass
        layers = self._refusal_layers(kind)
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

    def _refusal_layers(self, kind):
        """The MapModel.refused layers a refusal of `kind` is learned in: an
        amphibious tower refused somewhere stands neither on land nor on
        water; a big tower's refusal is kept for its kind only
        (placement.refusal_layer, "land@quincy"), a small one's in the
        surface's shared layer ("land")."""
        from .placement import refusal_layer
        if kind == "hero":
            cls = T.HEROES.get(self.g.hero, {}).get("placement") or "land"
        else:
            cls = T.TOWERS.get(kind, {}).get("placement") or "land"
        hero = self.g.hero if kind == "hero" else None
        return [refusal_layer(surface, kind, hero)
                for surface in (("land", "water") if cls == "land_or_water" else (cls,))]

    def _block(self, cx, cy, r, layer=None):
        """Mark the cells within r of (cx, cy) as no-go for this game: for
        every tower (layer None), or only for the towers whose refusals are
        learned in `layer` (a big tower's own layer, _block_refused)."""
        if layer is None:
            grid = self.blocked
        else:
            layers = self.__dict__.setdefault("layer_blocked", {})
            grid = layers.setdefault(layer, np.zeros(self.blocked.shape, bool))
        h, w = grid.shape
        grid[max(0, cy - r):min(h, cy + r + 1), max(0, cx - r):min(w, cx + r + 1)] = True

    def _block_refused(self, kind, cx, cy, r=2):
        """A `kind` tower was refused at (cx, cy): keep the cells round it
        from being offered again this game - to every tower when the refusal
        says the ground is bad (a small tower's, the shared layer), to this
        tower's own kind only when it says its footprint did not fit (a big
        tower's own layer, as the map learns it: _learn_blocked).

        Glacial Trail Medium (2026-11-09 19:12): Quincy was refused twice on
        Floor2, one of the map's two patches of ground beside the track. The
        map learned it for Quincy alone ("land@quincy"), but the game's block
        took the whole patch from every tower: the tack, the dart, the glue
        and later the camo answers found no spot that reached the track, 7
        plan steps and 12 answers were given up, and round 40 was lost with a
        lone boomerang and a sniper standing."""
        layers = self._refusal_layers(kind)
        own = [layer for layer in layers if "@" in layer]
        if not own:
            self._block(cx, cy, r)
            return
        for layer in own:
            self._block(cx, cy, r, layer=layer)

    def _blocked_for(self, kind):
        """This game's no-go cells for a new `kind` tower: the shared ones
        plus those blocked for its own refusal layer (_block_refused)."""
        blocked = getattr(self, "layer_blocked", None) or {}
        own = [blocked[layer] for layer in self._refusal_layers(kind) if layer in blocked]
        if not own:
            return self.blocked
        return self.blocked | np.logical_or.reduce(own)

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

    def _lane_grids(self):
        """The map's grids as the lane code reads them: with the bloon paths
        of the round being played only (mapgeom.grids_for with now_round
        leaves the idle phase paths out of path_masks, as the match's
        repaint_track leaves them out of the track).

        Without the round all six of Erosion's phase paths counted as lanes,
        five of them empty for the first 13 rounds, so open_lanes() >= 2
        held on every board and the match opened with a sniper every game
        (audit 2026-11-12)."""
        from . import mapgeom
        return mapgeom.grids_for(self.m, removed=tuple(self.removed),
                                 now_round=getattr(self, "now_round", None))

    def _lane_cover(self, cover):
        """Grid: for each track cell, how well its bloon path is defended
        against the best-defended path (mean tower cover over the path's
        cells, 0..1, times LANE_COVER_WEIGHT); a cell shared by several
        paths takes the least-defended one, since a tower there guards that
        lane too. On Firing Range both paths share the top rows and split
        into the left and right lanes. None on maps without geometry, with a
        single path, or with no cover yet (it would change nothing)."""
        try:
            grids = self._lane_grids()
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

    # A bloon path counts as open while the placed damage towers cover under
    # this share of what they cover of the best-guarded path.
    OPEN_LANE_SHARE = 0.1

    def open_lanes(self):
        """How many of the map's bloon paths the placed damage towers leave
        unguarded (mean tower cover under OPEN_LANE_SHARE of the best-guarded
        path's). 0 on maps without geometry, with a single path, or with no
        tower standing yet.

        Spillway Impoppable (2026-11-11 15:41, lost in round 7): bloons come
        down four lanes, and n1 in the top-left corner covered three of the
        five paths (0.18, 0.13, 0.18) and nothing of the other two."""
        cover = self._tower_cover()
        try:
            grids = self._lane_grids()
        except Exception:
            return 0
        masks = (grids or {}).get("path_masks") or []
        if len(masks) < 2 or any(mask.shape != cover.shape for mask in masks):
            return 0
        shares = [float(cover[mask].mean()) for mask in masks]
        best = max(shares)
        if best <= 0:
            return 0
        return sum(1 for share in shares if share < self.OPEN_LANE_SHARE * best)

    def _tower_cover(self):
        """The cover grid of the towers alone (see _covered).

        The hero is valued at its placement price (towers.HEROES 'cost'),
        like a tower with no upgrades. It used to count in full, as if it
        were the strongest tower on the board: on Party Parade Medium
        (2026-11-04, fast track from round 15) Quincy stood in the left
        lane, so that lane looked as defended as the right one with its
        0-2-2 bomb, and a2, b1 and the village all went right. Bloons split
        between the two lanes, and the left one leaked 90 lives by round 31.
        A hero with no known price still counts in full.

        Towers that pop wherever they stand (_needs_no_reach: heli, sniper,
        mortar, dartling) are left out: they cover every cell alike, so they
        say nothing about where the next tower is needed. Counted as a disc
        round the spot they stand on, a heli bought early (hard_ninja_alch_sun
        in Half Cash since 2026-11-09: 3-0-0, $4.6k, right after n1) was the
        most-invested tower, so the ninjas after it counted for a fraction of
        their cost and n2 went to n1's lane: on Mesa both ninjas, the hero
        and both villages ended up on the left lane, and the replay rated
        round 78 at 0.71 against 1.43 with the same towers spread over both
        lanes (X Factor 0.52 -> 1.09, Dark Castle 0.62 -> 0.76)."""
        import cv2
        from .towerxp import invested
        family = PRICE_FAMILY.get(self.mode, "hard")
        poppers = [p for p in self.g.towers.values()
                   if p.kind not in ("village", "alchemist", "farm")   # support towers do not pop
                   and not self._needs_no_reach(p.kind)]
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

    def peek_spots(self, kind, step, n=1):
        """pick_spots for a placement that is only being rated, not bought:
        the same spots, but the one probe per kind and game (_probe_spot) is
        not spent and not logged - it stays for the pick-up that clicks it.

        Infernal Impoppable (2026-11-10, chimps_ninja_sun, lost round 78):
        one look of reinforce.new_kind_options at 16:13:05 rated a placement
        of 13 tower kinds and so "probed" all 13 without a single click, and
        from round 63 every look offered only "another mermonkey" (the last
        free legal cell): the sniper and the sub had no free legal cell left
        but a probe each, which their first rating had used up. That day's
        log shows 40 of 81 probes offered with no placement attempt of the
        kind following them. Reinforce rates every placement it offers, at
        every look (options, radar_option, plan_option, save_target), and
        the match's bundle ordering rates the plan's next placement, so any
        game with blocked cells worth probing lost its probes this way."""
        self._peeking = True
        try:
            return self.pick_spots(kind, step, n)
        finally:
            self._peeking = False

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
        block = self._keep_off_scarce(kind, valid, self._blocked_for(kind))
        far = self._far_from_at(step, block.shape)
        if far is not None:
            # a step with a researched spot falls back to cells round that
            # spot, never to the best spot by role anywhere on the map
            block = block | far
        room = self._no_buffer_room(step, valid)
        if room is not None:
            block = block | room
        covered = None if role == "support" else self._covered()
        if role == "dps" and only is None and not step.get("at"):
            seg = self._segment_in_reach(kind, seg, rc, placement, block, covered, valid)
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
            sight = self._round_sight()
            cands = [(cx, cy, PL.visible_cover(self.m, cx, cy, rc, weight, sight)) for cx, cy, _ in cands]
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
            best = self._best_legal_reach(kind, valid)
            if best is not None and best < 1.0 and exact is None:
                # No legal cell reaches the track, so there is no floor to
                # hold a spot against (_reach_floor answers None) and any
                # cell would pass. Covered Garden Impoppable (2026-11-11,
                # loss case 20261111_194816): with one pane open the Super
                # Monkey "near v1" had 32 legal cells, none in reach of the
                # track; "placing by role only" put it in the corner at
                # (9,11), where it reached 0 track cells, and the plan then
                # spent $10,440 on its upgrades while rounds 55-63 were
                # rated 0.25-0.52. Like a dps step, it gets no spot: the
                # step waits for ground that reaches (another pane) or is
                # given up, and the cash goes to towers that pop.
                log.info("%s: no legal spot reaches the track (%d legal cells) - none offered "
                         "for a support step either", kind, int(valid.sum()))
                return []
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
        reserved = self._reserved_cells(step, kind)

        def kept_free(cx, cy, spots):
            """Is (cx, cy) inside the gap of a spot a later step needs?"""
            return any((cx - rx) ** 2 + (cy - ry) ** 2 < gap ** 2 for rx, ry, gap in spots)

        if probe is not None and not kept_free(probe[0], probe[1], reserved):
            out.append(probe)       # tried first; a refusal costs ~0.1 s and is learned
        # The later steps' spots are kept free by a whole footprint; only on
        # a board where that leaves this tower no spot at all does the flat
        # RESERVED_CELLS distance of old apply (a one-life opener that is
        # not placed loses the game at once).
        flat = [(rx, ry, RESERVED_CELLS) for rx, ry, _ in reserved]
        for spots in (reserved, flat):
            for cx, cy, score in ranked:
                if (kind, cx, cy) in self.failed_spots:
                    continue
                if floor is not None and self._reach(kind)[cy, cx] < floor:
                    continue  # its range only grazes the track (see MIN_REACH_SHARE)
                if kept_free(cx, cy, spots):
                    continue  # a later step of the build places a tower right here
                if any((cx - ox) ** 2 + (cy - oy) ** 2 < 9 for ox, oy, _ in out):
                    continue
                out.append((cx, cy, score))
                if len(out) >= n:
                    break
            if out or not reserved:
                break
        return out

    # A step's progress window (`segment`) is kept only while some legal spot
    # covers at least this share of what the best legal spot covers of the
    # whole track; under it the window is out of the tower's reach.
    SEGMENT_REACH_SHARE = 0.1

    def _segment_in_reach(self, kind, seg, rc, placement, block, covered, valid):
        """The step's progress window, or the whole track (0.0, 1.0) when no
        legal spot reaches the window.

        Firing Range Impoppable (2026-11-11, lost in round 6 at 03:18 and
        again at 15:14): the track's first half is the three lanes along the
        top, and the only ground - the field under the barbed wire - lies
        more than a ninja's range below them. Every legal spot scored 0.0 for
        n1's window [0.0, 0.5] and for the starter dart's [0.05, 0.45], and
        with all scores alike the ranking said nothing: both towers went to
        the left exit lane, and the bloons of the other path walked down the
        right lane untouched. Scored on the whole track, the same starter
        goes to the right lane, because the lane n1 guards counts as covered
        (_lane_cover). (Backlog 22, first seen in case 20261104_035430.)"""
        whole = (0.0, 1.0)
        if tuple(seg) == whole:
            return seg
        occupied = self._occupied()

        def best(segment):
            cover = self.m.score_spots(rc, segment, occupied, placement=placement,
                                       extra_block=block, covered=covered, valid=valid)
            return float(cover.max())

        best_whole = best(whole)
        if best_whole <= 0 or best(seg) >= self.SEGMENT_REACH_SHARE * best_whole:
            return seg
        if not getattr(self, "_peeking", False):
            log.info("%s: no legal spot reaches the track's %.0f-%.0f%% part - "
                     "scoring the whole track", kind, 100 * seg[0], 100 * seg[1])
        return whole

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
        from .maplearn import spot_factor
        f = spot_factor(self.m, kind, cx, cy)
        if f <= 1.0 or lane is None:
            return f
        # the spot's lane: mean lane cover over the bloon-path cells in its
        # range (the path masks _lane_cover used; the learned track heat is
        # wider and would count lane-less cells as unguarded)
        masks = self._lane_grids()["path_masks"]
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

    def _reserved_cells(self, step, kind=None):
        """(cx, cy, gap) for each exact spot (`at`) the build's later place
        steps still need: the spot's cell and how many cells a `kind` tower
        placed now must keep from it. A tower placed by role must leave
        them free: on Ravine Easy the hero, placed by role, sat beside two
        planned bomb spots, and those bombs went to the far side of the map.

        The gap is the two footprints side by side (the game's own radii,
        placement.footprint_radius), and never under RESERVED_CELLS. With
        RESERVED_CELLS alone a big tower's spot was not kept: on Sunset
        Gulch Impoppable (2026-11-12, case 20261112_050436) the one-life
        opener's tack and the free dart stood 4.1 and 4.5 cells from s1's
        spot - outside the 4 reserved cells, inside a Super Monkey's
        footprint. s1 found "nothing legal within 15 cells of its spot",
        went by role to the exit, where it did not pop one bloon in 53
        rounds ($13,440), and the game was lost to round 88's blimps."""
        from . import placement as PL
        out = []
        strat = getattr(self, "strat", None) or {}
        try:
            upc = PL.units_per_cell(self.m)
            own = PL.footprint_radius(kind, self.g.hero if kind == "hero" else None) if kind else 0.0
        except Exception:    # a map model without a playfield (test fakes): the plain distance
            upc, own = None, 0.0
        for st in list(getattr(self, "plan", None) or []) + list(strat.get("fill") or []):
            at = st.get("at")
            if st.get("do") != "place" or not at or st is step or st.get("id") == step.get("id"):
                continue
            if st.get("id") in self.g.towers:
                continue    # placed already
            gap = RESERVED_CELLS
            if upc and st.get("kind"):
                theirs = PL.footprint_radius(st["kind"], self.g.hero if st["kind"] == "hero" else None)
                gap = max(gap, (own + theirs) / upc)
            out.append((*self.m.frac_to_cell(*self._at_now(at)), gap))
        return out

    @staticmethod
    def _widened(p, target):
        """The target crosspath with the tiers p already has on other paths
        kept, when the game allows both together (legal_cross); else the
        target as written.

        A plan step "b1 to 0-5-0" whose bomb had been given a $300 top tier
        by reinforce (1-4-0) used to read as "the tower went another way":
        the step was skipped for good. Firing Range Impoppable (2026-11-11
        20:27, loss case 20261111_202920): that skip lost the $31,200 MOAB
        Eliminator, the build's DDT answer, and round 95's DDTs took the
        life. 1-4-0 can still become 1-5-0, so the step now aims there."""
        merged = tuple(max(c, t) for c, t in zip(p.tiers, target))
        return merged if legal_cross(merged) else tuple(target)

    def _next_path(self, p, target):
        """Cheapest next tier that moves p toward target crosspath."""
        target = self._widened(p, target)
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
        target = self._widened(p, target)
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
    # Freezing maps (_freeze_clash): a new tower is held back while less than
    # this share of the defence's cash would be awake in a round it is frozen ...
    FREEZE_AWAKE_SHARE = 0.5
    # ... but only a tower that costs less than this share of the cash already
    # standing: an opening cannot wait for its second tower, a built defence can.
    FREEZE_HOLD_PRICE_SHARE = 0.25

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

    def _ground_round(self):
        """The round to judge a new tower's ground by: on maps whose panes
        open in turn (Covered Garden) the round whose pane the screen shows
        (_pane_round), elsewhere the bot's own round (None before the first
        round is read: then every change of the game is planned for).

        Ground that opens or melts by this round takes towers. Until
        2026-11-12 only Covered Garden passed a round: One Two Tree's opened
        land plots were never used (dart cells 1,869 in round 1 and 3,187
        by round 80 with the round) and neither was Erosion's water from
        melted ice (sub cells 302 against 2,865 by round 40)."""
        pane = self._pane_round()
        return pane if pane is not None else getattr(self, "now_round", None)

    def _round_sight(self):
        """(blockers, heights) of line of sight in the round being played,
        from mapgeom.grids_for with the round (_ground_round): blockers gone
        by now - One Two Tree's opened plots, Cargo's centre trucks after
        the first MOAB - no longer hide the track. None (the model's
        whole-game grids) before the first round or without geometry."""
        rnd = self._ground_round()
        if rnd is None:
            return None
        from . import mapgeom
        try:
            grids = mapgeom.grids_for(self.m, removed=tuple(self.removed), now_round=rnd,
                                      pose_round=self._pose_round())
        except Exception:      # geometry is optional: never let it stop a game
            return None
        if not grids or grids["sight"].shape != getattr(self.m.sight, "shape", None):
            return None
        return grids["sight"], grids["sight_height"]

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
        self._ground_moved(mapgeom.platform_ground(self.m))

    def gears_turned(self):
        """Geared's gears turned (the match calls this after carried.
        CarriedTowers turned the towers' spots): spots refused or avoided
        on gear ground were judged in the old pose, so they are tried
        again, and the footprints are blocked where the towers stand now.
        Before, `blocked` and `failed_spots` kept every old judgement, and
        the gear ground left for new towers shrank all game (audit
        2026-11-12)."""
        from . import mapgeom
        try:
            self._ground_moved(mapgeom.rotor_ground(self.m))
        except Exception:
            log.exception("forgetting refusals on the gears failed - carrying on")

    def _ground_moved(self, ground):
        """Forget the refusals and blocks judged on `ground` (bool grid of
        moving ground, None: nothing to do) and block each tower's footprint
        where it stands now."""
        if ground is None:
            return
        h, w = ground.shape
        self.failed_spots = {k for k in self.failed_spots
                             if not (0 <= k[2] < h and 0 <= k[1] < w and ground[k[2], k[1]])}
        self.blocked &= ~ground
        for grid in (getattr(self, "layer_blocked", None) or {}).values():
            grid &= ~ground
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
            r = self._try_place(step, cash)
            if r == "bought" and step.get("kind") == "hero" and getattr(self, "hero_round", None) is None:
                self.hero_round = rnd      # the hero's level estimate counts from here
            return r
        if do == "ability":
            return self._try_ability(step, rnd)
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

    # `do: ability` (Blood Sacrifice): seconds between presses when a key
    # armed nothing (the next try takes the next candidate key), seconds
    # before the hero's level is looked at again when it is too low, and
    # presses before the step is given up for the game.
    ABILITY_RETRY_S = 5.0
    ABILITY_LEVEL_RECHECK_S = 10.0
    ABILITY_MAX_TRIES = 12

    def _try_ability(self, step, rnd):
        """One attempt at a `do: ability` step, e.g.
            {do: ability, name: Blood Sacrifice, target: d1, min_value: 72795,
             when: {round: 76, hero_level_min: 7, hero_level_max: 10}}
        Presses the hero's ability and gives it the target tower
        (Game.targeted_ability). Returns try_step's results: "done" once
        the target is gone, "wait" while its round, the hero's level, the
        round being played or a retry pause stands in the way, "skip" when
        it can never go right this game (no target, the target worth less
        than min_value, the hero past hero_level_max, the tries used up, or
        a press whose outcome the screen did not show)."""
        name = step.get("name")
        spec = TARGETED_ABILITIES.get(name)
        if spec is None:
            log.warning("ability step %s: unknown ability", step)
            return "skip"
        when = step.get("when") or {}
        if when.get("round") and (rnd is None or rnd < when["round"]):
            return "wait"
        p = self.g.towers.get(step.get("target"))
        if p is None or p.kind == "hero":
            log.warning("ability step %s: target %s is not standing - given up", name, step.get("target"))
            return "skip"
        if getattr(self.g, "hero", None) != spec["hero"]:
            log.warning("ability step %s: the hero is %s, not %s - given up", name,
                        getattr(self.g, "hero", None), spec["hero"])
            return "skip"
        hero = next((h for h in self.g.towers.values() if h.kind == "hero"), None)
        if hero is None:
            self.g.fail_reason = "hero"
            return "wait"
        value = T.total_cost(p.kind, p.tiers, PRICE_FAMILY.get(self.mode, "hard"))
        if step.get("min_value") and value < step["min_value"]:
            log.warning("ability step %s: %s (%s %s) is worth $%s, under the $%s it needs - given up",
                        name, p.tid, p.kind, p.crosspath, value, step["min_value"])
            return "skip"
        if getattr(self, "play_running", None) is False:
            return "wait"          # only while a round plays: the achievement counts a round's levels
        key = self._step_key(step)
        if time.time() < self.retry_at.get(key, 0):
            return "wait"
        tries = self.ability_tries.get(key, 0)
        if tries >= self.ABILITY_MAX_TRIES:
            log.warning("ability step %s: %d presses armed nothing - given up", name, tries)
            return "skip"
        if when.get("min_margin"):
            worst = self._sacrifice_margin(p, rnd)
            if worst is None or worst[0] < when["min_margin"]:
                if self._margin_wait_logged != rnd:
                    self._margin_wait_logged = rnd
                    log.info("ability step %s: waits - without %s the damage model rates %s, under %s",
                             name, p.tid, "nothing" if worst is None else
                             f"round {worst[1]} at {worst[0]:.2f}", when["min_margin"])
                self.g.fail_reason = "margin"
                return "wait"
        level, how = self._hero_level_now(hero, rnd)
        lo = max(spec["level"], when.get("hero_level_min") or 0)
        hi = when.get("hero_level_max")
        if level is None or level < lo:
            self.retry_at[key] = time.time() + self.ABILITY_LEVEL_RECHECK_S
            self.g.fail_reason = "hero_level"
            return "wait"
        if hi and level > hi:
            log.warning("ability step %s: the hero is level %s (%s), over %s - given up", name, level, how, hi)
            return "skip"
        keys = self._ability_keys(name, rnd)
        if not keys:
            log.warning("ability step %s: no hotkey may be pressed for it - given up", name)
            return "skip"
        k = keys[tries % len(keys)]
        self.ability_tries[key] = tries + 1
        with self.why("plan_ability", f"{name} on {p.tid} ({p.kind} {p.crosspath}, ${value}): "
                                      f"hero level {level} ({how}), key {k}"):
            r = self.g.targeted_ability(k, p)
        if r == "done":
            after, how_after = self._hero_level_now(hero, rnd)
            log.info("%s: %s given up, hero level %s (%s) -> %s (%s)", name, p.tid, level, how,
                     after, how_after)
            return "done"
        if r == "unclear":
            log.error("ability step %s: the screen did not show what key %s did with %s - given up "
                      "(see logs/ability_%s_*.png)", name, k, p.tid, p.tid)
            return "skip"
        self.retry_at[key] = time.time() + self.ABILITY_RETRY_S
        return "wait"

    _margin_wait_logged = None      # the round whose margin wait was logged (_try_ability)

    def _sacrifice_margin(self, p, rnd):
        """(lowest margin, its round) the damage model gives the board
        without tower p over every round left - the one being played to the
        mode's last - or None when it cannot rate them. A sacrifice may only
        take a tower the rest of the game does without: on Logs Hard
        (2026-11-09) Blood Sacrifice took the M.A.D. 8 s into round 76,
        rated 0.81 with it, and the ceramics it was shooting at the exit
        leaked 0.3 s later - 100 lives."""
        if rnd is None:
            return None
        end = (getattr(self, "rules", None) or {}).get("end_round", 80)
        rounds = list(range(rnd, end + 1))
        return self._rated(f"without:{p.tid}", rnd, lambda fc, towers: fc.worst(
            [t for t in towers if t.tid != p.tid], rounds))

    def _hero_level_now(self, hero, rnd):
        """(level, "panel" | "estimate") for the placed hero: read off its
        panel when the game can (Game.hero_level), else estimated from the
        rounds since it was placed (abilities.estimate_hero_level, with the
        map's difficulty and the account's Monkey Knowledge XP bonuses:
        abilities.hero_xp_multiplier). (None, ...) when neither."""
        read = getattr(self.g, "hero_level", None)
        if callable(read):
            lvl = read(hero)
            if lvl is not None:
                return lvl, "panel"
        from .abilities import estimate_hero_level, hero_xp_multiplier
        from .match import xp_knowledge
        placed = getattr(self.abil, "hero_round", None) or getattr(self, "hero_round", None)
        if placed is None or rnd is None:
            return None, "unknown"
        factor = hero_xp_multiplier(getattr(getattr(self, "m", None), "name", None),
                                    xp_knowledge(getattr(self, "account", None), getattr(self, "rules", None)))
        return estimate_hero_level(getattr(self.g, "hero", None), placed, rnd, factor), "estimate"

    def _ability_keys(self, name, rnd):
        """Hotkeys to try for hero ability `name`, best guess first
        (AbilityPlanner.key_candidates); [1] without a planner (offline)."""
        if self.abil is None:
            return [1]
        return self.abil.key_candidates(name, rnd)

    def _release_panel(self):
        """Close the panel kept open for a run of tiers (Game.release_panel);
        a game without one (offline fakes) just stops holding it."""
        release = getattr(self.g, "release_panel", None)
        if callable(release):
            release()
        else:
            self.g.hold_panel = None

    def _awake_share(self, placed_round):
        """The smallest share of the standing defence's cash that is awake in
        a round a tower placed in `placed_round` would first be frozen in
        (the hero is left out, as in the forecast's phases). 1.0 on a map
        without a freeze or with no tower standing."""
        from . import dps_model as D
        name = getattr(self.m, "name", "")
        off, cycle = D._freeze_cycle(name)
        built = [p for p in self.g.towers.values()
                 if p.kind != "hero" and getattr(p, "placed_round", None) is not None]
        total = sum(max(getattr(p, "spent", 0) or 0, 1) for p in built)
        if not off or not total:
            return 1.0
        first = placed_round + D.FREEZE_FIRST_OFFSET
        return min(sum(max(getattr(p, "spent", 0) or 0, 1) for p in built
                       if not D.frozen_in(name, p.placed_round, r)) / total
                   for r in range(first, first + off))

    def _freeze_clash(self, step, kind, price):
        """True while placing this tower should wait a round or two, because
        bought now it would sit in ice together with most of the defence.

        On a freezing map (dps_model.TOWER_FREEZE) every tower is frozen for
        two rounds in ten, counted from the round it was bought in. Glacial
        Trail Reverse (2026-11-11, loss case 20261111_172115): the Spike
        Factory and the first druid were bought in round 15 (frozen 44-45),
        the second druid in 17 (frozen 46-47). The heli's turn came in round
        36, which froze it in 45-46: round 45 was left to one Druid of the
        Jungle, was rated 0.06 from round 36 on, and lost all 142 lives. The
        Medium game won with the same build the day before (2026-11-10 19:43)
        happened to reach the heli in round 37 - frozen 46-47, round 45 rated
        1.41.

        So the tower waits when
          * less than FREEZE_AWAKE_SHARE of the cash in the standing towers
            would be awake in one of its frozen rounds,
          * one of the next rounds (as many as the freeze lasts) does better,
          * and it is a small part of the defence (FREEZE_HOLD_PRICE_SHARE):
            a Fast Track opening is still bought together, as its build
            planned it.
        A step is held for as many rounds as the freeze lasts at most."""
        rnd = getattr(self, "now_round", None)
        if rnd is None or kind == "hero":
            return False
        from . import dps_model as D
        off, _ = D._freeze_cycle(getattr(self.m, "name", ""))
        if not off:
            return False
        standing = sum(getattr(p, "spent", 0) or 0 for p in self.g.towers.values() if p.kind != "hero")
        if price >= self.FREEZE_HOLD_PRICE_SHARE * standing:
            return False
        held = self.__dict__.setdefault("_freeze_held", {})   # step -> the round its hold began
        key = step.get("id") or kind
        waited = rnd - held.get(key, rnd)
        if waited >= off:
            return False          # it has waited as long as a freeze lasts
        now = self._awake_share(rnd)
        if now >= self.FREEZE_AWAKE_SHARE:
            return False
        better = max(self._awake_share(rnd + k) for k in range(1, off - waited + 1))
        if better <= now:
            return False
        held.setdefault(key, rnd)
        if self.__dict__.get("_freeze_said") != (key, rnd):
            self._freeze_said = (key, rnd)
            log.info("%s: bought in round %d it would be frozen while only %.0f%% of the defence's cash "
                     "is awake - held for a later round (%.0f%% then)", key, rnd, 100 * now, 100 * better)
        return True

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
        if self._freeze_clash(step, kind, price):
            return "wait"         # a round or two later it freezes apart from the others
        if kind in self.BUFFERS and not self._damage_towers():
            return self._defer(step, key, self.BUFFER_RETRY_S)   # nothing to buff yet
        if self._pane_already_empty(key):
            return self._defer(step, key, self.PANE_RETRY_S)   # same pane, same answer
        spots = self._spots_widening(kind, step)
        if not spots:
            # a plan tower with no ground is first given the ground under a
            # removable obstacle, when the map sells one that helps; on a map
            # with cycling panes it waits for the next pane's ground
            r = self._clear_for_place(step, key, kind, cash)
            if r is None:
                r = self._wait_for_next_pane(step, key, kind)
            return self._out_of_spots(step, key) if r is None else r
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
            getattr(self, "pane_empty", {}).pop(key, None)
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

    # A plan placement with no spot under the open pane looks again this often
    # (s): a pane stays open for a whole round, and the look is one screen read.
    PANE_RETRY_S = 5.0

    def _open_pane(self):
        """(index of the pane open now, number of panes) on a map whose panes
        open in turn (Covered Garden), judged as _pane_now judges it - by the
        screen first. None on every other map."""
        rnd = self._pane_round()
        if rnd is None:
            return None
        from . import mapgeom
        try:
            cycle = mapgeom.grids_for(self.m)["panes"][0][0]
            return mapgeom.pane_open(cycle, rnd), len(cycle["areas"])
        except Exception:
            return None

    def _pane_already_empty(self, key):
        """True when this step's spot search already came back empty under
        the pane that is open now (_wait_for_next_pane): nothing is searched
        again until another pane opens."""
        tried = getattr(self, "pane_empty", {}).get(key)
        if not tried:
            return False
        pane = self._open_pane()
        return pane is not None and pane[0] in tried and len(tried) < pane[1]

    def _wait_for_next_pane(self, step, key, kind):
        """A plan placement found no spot at all on a map with cycling panes:
        the step is set aside (self.deferred, the plan goes on) and tried
        again under each of the other panes, one round apart. Returns None
        when this is not a case for it, or when every pane has been tried -
        the step is then given up as before.

        Covered Garden Impoppable (2026-11-11 12:52, chimps_ninja_sun): only
        a quarter of the garden takes towers in any one round. n1, the build's first ninja, had one click refused before
        round 6 and was looked at again four seconds into the round, under
        the next pane: "no spot found (677 legal cells ...)" and it was given
        up for the game - under the pane of two rounds later the same search
        has its best spots. The alchemist, named `near: [n1]`, then went to
        the far side of the map beside a reinforce dart, the discount village
        v1 (`near: [n1, a1]`) was given up the same way at round 26 - every
        later tier, the $24,000 Sun Avatar among them, was paid without its
        15% discount - and from round 66 on the model rated the board
        0.3-0.6 with purchases that moved it by 0.01; round 93 was lost.

        Only the build's own towers wait: fills, answers and panic steps are
        offered again every tick by whoever runs them, and the hero has its
        own retry (_out_of_spots)."""
        if kind == "hero" or step.get("id") not in self._plan_place_ids():
            return None
        pane = self._open_pane()
        if pane is None:
            return None
        index, count = pane
        tried = self.__dict__.setdefault("pane_empty", {}).setdefault(key, set())
        tried.add(index)
        if len(tried) >= count:
            return None             # no pane has ground for it: given up
        log.info("%s: no spot under pane %d - set aside until another pane opens (%d of %d panes tried)",
                 step.get("id"), index, len(tried), count)
        return self._defer(step, key, self.PANE_RETRY_S)

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
            self._block_refused(kind, cx, cy)
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

    def _damage_towers_ids(self):
        return [tid for tid, p in self.g.towers.items()
                if p.kind != "hero" and p.kind not in self.BUFFERS and p.kind != "farm"]

    def _buffed(self, kind, cx, cy, towers=None):
        """How many damage towers (or of `towers`) a `kind` buffer at cell
        (cx, cy) has in range."""
        r2 = self._range_cells(kind) ** 2
        n = 0
        for p in self._damage_towers() if towers is None else towers:
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
        towers happened to stand.

        The ground is _legal_cells', so a buffer stands where the damage
        towers may stand this round, down to the current path phase's ice
        (ground_horizon). Erosion (audit 2026-11-12): asked for ground that
        lasts the whole game (80 rounds), a village had 85 cells, against
        3,114 for the round-1 phase; the damage
        towers stand on the phase's ice, far out of a buffer's reach from
        those few cells."""
        if not self._damage_towers():
            return []
        valid = self._legal_cells(kind)
        if valid is None:
            return []
        # the researched spot and its neighbours first, where they buff something
        out = [c for c in (self._at_spots(step, valid, self.SPOTS_PER_HOLD) if step else [])
               if self._buffed(kind, c[0], c[1]) >= 1]
        if len(out) >= self.SPOTS_PER_HOLD:
            return out
        # The damage towers the step names (`near`) come first: a cell that
        # buffs one of them beats one that buffs more of the others. #Ouch
        # Apopalypse (2026-11-09 12:17): a1 "near n1" found no spot within
        # its near radius, went where it buffed the most towers - n2 and the
        # opener on the right - and the left lane, held by n1 alone without
        # the alchemist's lead and damage, leaked 119 lives in a second.
        damage = set(self._damage_towers_ids())
        named = [self.g.towers[i] for i in (step or {}).get("near") or () if i in damage]
        ys, xs = np.nonzero(valid & ~self._blocked_for(kind))
        scored = sorted(((self._buffed(kind, x, y, named) if named else 0, self._buffed(kind, x, y), x, y)
                         for x, y in zip(xs.tolist(), ys.tolist())
                         if (kind, x, y) not in self.failed_spots), reverse=True)
        if named and scored and scored[0][0] < 1:
            log.info("%s: no spot buffs %s - placed where it buffs the most towers",
                     kind, step.get("near"))
        for _, n, x, y in scored:
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
        cand = ~valid & ~on_track & ~refused & ~self._blocked_for(kind) & (reach > self.PROBE_GAIN * best_legal)
        solid = self._solid_blockers(valid.shape)
        if solid is not None:
            cand &= ~solid
        under = self._pane_ground_for(kind, cand.shape)
        if under is not None:
            cand &= ~under          # not onto the glass either (_off_panes)
        ys, xs = np.nonzero(cand)
        for i in np.argsort(-reach[ys, xs])[:50]:
            cx, cy = int(xs[i]), int(ys[i])
            if (kind, cx, cy) in self.failed_spots:
                continue
            if getattr(self, "_peeking", False):
                return (cx, cy, 2e9)    # only rated (peek_spots): the probe stays unspent
            probed.add((kind, cx, cy))
            log.info("%s: probing a spot the map file marks blocked (reaches %.0f track cells, "
                     "the best legal one %.0f)", kind, reach[cy, cx], best_legal)
            return (cx, cy, 2e9)
        return None

    def _solid_blockers(self, shape):
        """Bool grid of the cells an unplaceable sight blocker of the map's
        geometry decides (mapgeom.placement_grids "solid_blockers": walls,
        icicles, rocks), which are never probed; None without geometry.

        Every probe the game accepted on 11 maps (data/maps accepted layers,
        2026-11-09: Water Park's circle, Bazaar, Cargo, Ravine ...) lay on
        land or on an unplaceable area that does not block sight. On Glacial
        Trail Medium (2026-11-09 19:12) all ten probes were refused, most of
        them inside the icicle and wall blockers round the loops: ~1.5 s
        each, and the only spot some of the steps were offered."""
        try:
            from . import mapgeom
            grids = mapgeom.grids_for(self.m)
        except Exception:
            return None
        solid = grids.get("solid_blockers") if grids else None
        return solid if solid is not None and solid.shape == shape else None

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
        in range (computed once per kind and game).

        On a map whose routes take turns round by round a cell counts as the
        share of the rounds that pass it (MapModel.round_share), the weight
        the spots are scored with (MapModel.track_weight). Counted alike,
        the reach floor threw the best spot away: on Last Resort a ninja
        beside the big loop has 282 track cells in range, all of them used
        one round in four, and the one legal patch left beside the top
        straight that every route runs along has 126 - under the floor of
        126.9 (MIN_REACH_SHARE), "its range only grazes the track", although
        it is the best-scored spot on the map. So no general
        build stood a short-range tower there, and every game lost on that
        map ended on a small-loop or straight round (2026-11-12 11:13 and
        11:17, cases 20261112_111354_LastResort_primary_only and
        20261112_111733_LastResort_abr: rounds 32 and 27-28)."""
        cache = self.__dict__.setdefault("_reach_cache", {})
        if kind not in cache:
            import cv2
            cnt = getattr(self.m, "t_cnt", None)
            track = (cnt > 0).astype(np.float32) if isinstance(cnt, np.ndarray) else None
            share = self._round_share_grid(track)
            if share is not None:
                track = track * share
            if track is None:
                cache[kind] = None
            else:
                r = max(1, int(round(min(self._range_cells(kind), 60))))
                disc = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
                cv2.circle(disc, (r, r), r, 1.0, -1)
                cache[kind] = cv2.filter2D(track, -1, disc, borderType=cv2.BORDER_CONSTANT)
        return cache[kind]

    def _round_share_grid(self, track):
        """The map's round shares (MapModel.round_share: for each cell the
        share of the rounds whose bloons pass it) when they fit the `track`
        grid, else None - every route carries every round, the model has no
        geometry (test models), or there is no track grid to weight."""
        if track is None:
            return None
        share_of = getattr(self.m, "round_share", None)
        try:
            share = share_of() if share_of else None
        except Exception:      # a map-file problem must never stop placement
            return None
        if not isinstance(share, np.ndarray) or share.shape != track.shape:
            return None
        return share

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
        ground that lasts the whole game: it is placed once.

        So does a tower that pops bloons wherever it stands
        (_needs_no_reach: sniper, heli, mortar ...), while such ground is
        left: it needs no ice beside the live path. Erosion Impoppable
        (2026-11-11, case 20261111_163453): four snipers and the blimp
        answer's sniper stood on the phase's ice and went with it after
        round 52, with ten more towers; round 53 began with $409 and the
        game was lost in round 54. Only with no lasting cell free does such
        a tower take the phase's ground like the others."""
        from . import placement as PL
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        whole_game = self.rules.get("end_round")
        horizons = [whole_game]
        if self.ground_horizon is not None and kind != "hero":
            phase = self.ground_horizon if whole_game is None else min(whole_game, self.ground_horizon)
            horizons = [whole_game, phase] if self._needs_no_reach(kind) else [phase]
        grid = None
        for last in horizons:
            grid = PL.valid_spots(self.m, kind, self.g.hero if kind == "hero" else None, placed,
                                  where={"land"} if self.land_only else None,
                                  last_round=last, now_round=self._ground_round(),
                                  pose_round=self._pose_round(), removed=tuple(self.removed))
            if grid is None or grid.any():
                break
        return self._off_panes(kind, grid)

    def _off_panes(self, kind, grid):
        """On a map with cycling panes (Covered Garden), keep a tower that
        pops bloons wherever it stands (_needs_no_reach: heli, sniper) off
        the ground under the panes while open ground is left for it.

        A tower under a pane can be upgraded only in its pane's rounds, one
        in four (_reachable). Covered Garden Apopalypse (2026-11-09, lost
        round 45): s1 stood on the open pane and its 2-2-0 step was "blocked
        (pane)" and set aside, and in the offline replay of
        apopalypse_apache_spikes all three helis went onto garden ground,
        the Apache tier ($8,500) waited for a round with both the pane open
        and the cash in hand, and the rounds 41-50 board had none. A heli
        flies to the bloons and a sniper shoots map-wide, so the ground
        under the glass is worth nothing more to them; short-range towers
        keep it (the garden is where their track is)."""
        if grid is None:
            return grid
        under = self._pane_ground_for(kind, grid.shape)
        if under is None:
            return grid
        off = grid & ~under
        return off if off.any() else grid

    def _pane_ground_for(self, kind, shape):
        """The ground under the panes (mapgeom.pane_ground) when `kind` is
        to be kept off it (_off_panes), else None."""
        if not self._needs_no_reach(kind) or self._pane_round() is None:
            return None
        from . import mapgeom
        try:
            under = mapgeom.pane_ground(self.m)
        except Exception:
            return None
        return under if under is not None and under.shape == shape else None

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
                if not self._reachable(p):
                    continue                # under a shut pane: read in its own pane's round
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
        Returns False without selling while _sale_blocked(rnd), or while a
        shut pane covers p (Covered Garden, _reachable): the click would hit
        the glass. The spot is avoided only once the sale went through: a
        sale that never happened left the spot barred for a tower that still
        stood on it (audit 2026-11-12)."""
        if not self._reachable(p):
            log.info("keeping %s (%s) for now although %s: a shut pane covers it", p.tid, p.kind, reason)
            return False
        blocked = self._sale_blocked(rnd)
        if blocked:
            log.info("keeping %s (%s, $%d spent) although %s: %s", p.tid, p.kind,
                     getattr(p, "spent", 0), reason, blocked)
            self._sold_round = rnd      # judged for this round: no more looks until the next
            return False
        log.warning("selling %s (%s, $%d spent): %s", p.tid, p.kind, getattr(p, "spent", 0), reason)
        self._sold_round = rnd
        with self.why("sell_useless", reason, tower=p.tid, spent=getattr(p, "spent", 0)):
            sold = bool(self.g.sell(p))
        if sold:
            self._avoid_spot(p)
        return sold

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
        blocked = self._blocked_for(step.get("kind")) if step.get("kind") else self.blocked
        h, w = blocked.shape
        r = radius or self.AT_SEARCH_CELLS
        near = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if dx * dx + dy * dy > r * r:
                    continue    # a circle, not the square's corners
                if not (0 <= x < w and 0 <= y < h) or blocked[y, x]:
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
        block = self._keep_off_scarce(kind, valid, self._blocked_for(kind))
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
        in the second the platforms slide at a round's start misses.

        Nor a tower on ground a cycling pane covers (Covered Garden), while
        its pane is shut (_reachable): a click there hits the glass. Audit
        2026-11-12: the pop-count read, sell_useless and _recheck_doubtful
        clicked such towers, and two failures forgot a standing tower and
        queued its purchase again."""
        melt = getattr(self, "melt_check", None)   # Match._melt_check: ground melted early
        if melt is not None and p.kind != "hero" and melt(p):
            return True
        if not self._reachable(p):
            return False   # Covered Garden: the glass over it, not its absence, failed the click
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
        self._rebuild_steps = redo      # see rebuild_pending
        log.warning("the map destroyed the ground under %s - forgotten; %d plan steps queued "
                    "again to rebuild them", ", ".join(gone), len(redo))
        self.track_changed()
        return gone

    def rebuild_pending(self):
        """True while plan steps queued again by ground_lost are still ahead
        in the plan: the map took the defence and it is not back up yet.
        The match keeps Play waiting longer for such a rebuild
        (Match._hold_for_crisis). A step that was bought, given up or set
        aside is behind the plan's index and no longer counts."""
        ahead = self.plan[self.idx:]
        left = [s for s in getattr(self, "_rebuild_steps", ()) if any(s is q for q in ahead)]
        self._rebuild_steps = left
        return bool(left)

    def _recheck_doubtful(self):
        """When no verified tower is left (defended() False) but one of them is
        only doubtful (its last selection failed), select it again: it either
        shows up (verified again) or, failing twice, is forgotten. Rounds do
        not start while defended() is False, so this must not wait."""
        if self.defended():
            return
        for p in list(self.g.towers.values()):
            if p.kind != "hero" and not getattr(p, "verified", True):
                if not self._reachable(p):
                    # its failed select was a click on shut glass (Covered
                    # Garden): that proves nothing, and no round would start
                    # to open the pane while it stays doubtful
                    log.info("%s (%s) stands under a shut pane - counted as standing", p.tid, p.kind)
                    p.verified = True
                    continue
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
    FIRST_BLIMP_LEAD_FACTOR = 2  # the game's first blimp round is checked this much earlier ...
    FIRST_BLIMP_HOPELESS = 0.3   # ... when the damage model rates it under this
    FIRST_BLIMP_SHORT_START = 20 # ... and the game started fewer rounds than this before it
                                 # (Fast Track: round 22 -> 40 is 18; a round-3 Hard start is 37)
    LEAD_MARGIN = 1.25       # count on only 80 % of the income still to come
    PLAN_FIRST_FACTOR = 1.5  # follow the plan when it covers the threat for <= 1.5x ...
    PLAN_FIRST_SLACK = 300   # ... (or <= $300 more than) the cheapest answer
    HOLD_MAX_S = 30.0        # longest wait between rounds to buy an affordable answer
    RAMP_OK = 1.0            # blimp damage in reach / blimp HP a round brings
    RAMP_OK_LETHAL = 1.4     # ... when the round's blimps leaking would end the game (ramp_bar)
    RAMP_OK_ONE_LIFE = 2.5   # ... with one life (Impoppable, CHIMPS): any blimp through ends it
    RAMP_PANIC = 0.4         # below this, the round before, buy blimp damage even mid-plan
    # The damage model's margin at which a blimp round counts as held, whatever
    # the blimp check says: the bar every map build is checked against (the
    # defence still holds at half strength).
    RAMP_MODEL_SAFE = 2.0
    DEFAULT_TRACK = 600.0    # world units of track when the map geometry is unknown

    def ramp_bar(self, load):
        """The blimp-check bar for a round: RAMP_OK_ONE_LIFE in a one-life
        mode, else RAMP_OK_LETHAL when the lives its
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
        if (self.rules or {}).get("one_life") and leak:
            # Bloonarius Prime Impoppable (2026-11-10 17:04): round 75's seven
            # BFBs were checked at 2.0x, over the 1.4x bar, so nothing was
            # bought for them, and one got through. With one life the check's
            # roughness has no lives to absorb it; the damage model can still
            # overrule the check when it is sure (_model_holds).
            return max(self.RAMP_OK_LETHAL, self.RAMP_OK_ONE_LIFE)
        if lives and leak and leak >= lives:
            return self.RAMP_OK_LETHAL
        return self.RAMP_OK

    def _init_threats(self):
        """Set up the threat checks (on first use, so that every Executor gets
        them however it was built)."""
        self.round_set = TH.set_for_mode(self.mode)
        self.window = (self.rules.get("start_round", 1), self.rules.get("end_round", 80))
        self.calendar = TH.calendar(self.round_set, *self.window) if TH.available() else {}
        self.__dict__.pop("_first_blimp", None)   # _first_blimp_round() works it out again
        self.latched = {}     # threat -> round it is being answered for (stays due until covered)
        self.noted = set()     # what was already logged, so that each line appears once
        self.opt_cache = {}    # answer options per (threat, towers on the map)
        self.hold_since = {}   # round -> when Play was first held for it
        self.cash_seen = 0
        self.targets, self.kind_targets = self._upgrade_targets(self.strat)
        self.track_len = None
        # income the threat calendar plans with (Double Cash left out; the
        # board's own income - Benjamin, farms - is added by round_income)
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

    def _radar_near_ids(self):
        """Where a Radar Scanner village goes: beside the (up to) three
        biggest towers that do not see camo on their own
        (dps_model.detects_camo) - the towers its sight is for. When every
        tower sees camo already, the biggest towers as for any village.

        The biggest towers alone can be the wrong place: in the Logs ABR
        replay of double_hp_sniper_sun the camo-lead answer came at round 27
        with a ninja, a map-wide Night Vision sniper and a second ninja as
        the three biggest - all three see camo - and the village went
        between them, a third of the map from the dart and the alchemist it
        was bought for. The dart (later a 5-2-0 Juggernaut under that
        village's Primary Mentoring) stood outside it and round 63 was rated
        0.63 instead of 2.5 (tests/test_abr_double_hp_sniper_sun_offline.py)."""
        from . import dps_model as D
        blind = sorted((p for p in self._towers()
                        if p.kind in T.TOWERS and p.kind not in ("village", "farm")
                        and not D.detects_camo(p.kind, tuple(p.tiers))),
                       key=lambda p: -getattr(p, "spent", 0))
        return [p.tid for p in blind[:3]] or self._near_ids()

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
        """threats.covers for the towers on the map: (ok, how / what is missing).

        Only towers that reach the track count as poppers (_track_poppers);
        support towers still lend their buffs to those in their range."""
        reaching = self._track_poppers()
        if reaching is not None:
            poppers = reaching if poppers is None else set(poppers) & reaching
        return TH.covers(self._towers(), sig, self._range_fn(), poppers)

    def _track_poppers(self):
        """Ids of the towers whose own attacks reach the track, or None when
        that cannot be told (no learned map, offline fixtures).

        A tower that can pop a bloon but stands where no bloon passes is no
        answer to it. Peninsula Impoppable (2026-11-12 00:18, loss case
        20261112_001915): the only lead popper was an alchemist placed "where
        it buffs the most towers", out of reach of the track; the threat check
        still said "lead (round 28): covered by a1 (alchemist 0-0-0: acid)",
        so no lead answer was bought, the damage model rated round 28 at 0.06
        for five rounds, and its six leads took the life. Global and income
        towers, spikes and towers on moving ground count as reaching."""
        try:
            towers = self._towers()
            out = set()
            for p in towers:
                if p.kind in ("farm", "spike", "hero") or T.TOWERS.get(p.kind, {}).get("range") is None \
                        or self._map_wide_now(p) or self._on_platform(p):
                    out.add(p.tid)
                    continue
                reach = self._reach(p.kind)
                if reach is None:
                    return None
                cx, cy = (int(round(v)) for v in self.m.frac_to_cell(p.x, p.y))
                if 0 <= cy < reach.shape[0] and 0 <= cx < reach.shape[1] and reach[cy, cx] > 0:
                    out.add(p.tid)
            return out
        except Exception:
            return None

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
            income += self.round_income(r)
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

    ANSWER_COPIES = 3        # new towers of one kind an answer need may place (_new_tower_option)
    # The least a blimp-ramp purchase that does not close the shortfall must
    # add, as a share of the blimp HP still missing (_answer_ramp)
    RAMP_MIN_GAIN_SHARE = 0.1
    # A finished copy must deal at least this share of what a new copy is
    # credited with before the blimp check places another (_copy_speaks_against)
    COPY_MIN_SHARE = 0.25

    def _answer_copy_ids(self, need, kind):
        """The ids of the towers of one kind placed for one answer need, in
        the order _new_tower_option hands them out."""
        base = f"ans_{need.replace('+', '_')}_{kind}"
        return [base] + [f"{base}{n}" for n in range(2, self.ANSWER_COPIES + 1)]

    def _copy_speaks_against(self, kind, tiers, credited, load, track, rng, reach):
        """Do the towers the blimp check already placed say that another
        `kind` at `tiers` is not worth buying? `credited` is the blimp damage
        _dps_options gives a new one - on about 2.5 x its range of track,
        since nobody knows its spot yet.

        Yes when a copy standing has not reached those tiers (finishing it
        is the same purchase without a second base price, and _dps_options
        offers that upgrade whenever it adds damage in reach), or when a
        copy that has them deals under COPY_MIN_SHARE of the credit from
        where it stands: this map's spots do not give that kind the reach
        the credit assumes.

        Workshop Impoppable (2026-11-11 08:23, chimps_ninja_sun): the check
        read round 40's MOAB at 0.0x from round 35. It placed three bombs
        within seven seconds, each "toward new bomb 0-3-0", and upgraded
        none - a bomb standing was rated by the track in its reach (next to
        none on Workshop's belts), a new one by the usual credit, so the new
        one always won. Two bare supers followed: $6,750 on five towers
        without an upgrade, more than the Sticky Bomb the plan was $6,000
        short of, and the MOAB took the one life."""
        for tid in self._answer_copy_ids("blimps", kind):
            p = self.g.towers.get(tid)
            if p is None or p.kind != kind:
                continue
            if any(have < want for have, want in zip(p.tiers, tiers)):
                return True
            dealt = TH.blimp_capacity([(tid, kind, list(p.tiers))], load, track, rng, reach)
            if dealt < self.COPY_MIN_SHARE * credited:
                return True
        return False

    def _new_tower_option(self, need, kind, cost, tiers):
        """An answer option that places a new tower and upgrades it.

        Its id is ans_<need>_<kind>, numbered from 2 when a tower of that
        id already stands. A taken id made the placement answer "done"
        without a click (_try_place), so a second tower of a kind was never
        bought for a need: Water Park Impoppable (2026-11-11, round 84)
        held $33,782 while the blimp check read round 84 at 0.7x of 2.5x,
        and its pick, "new ace 4-0-0", was ans_blimps_ace - the ace placed
        for an earlier blimp round. The ramp bought nothing that round.

        At most ANSWER_COPIES towers of a kind are placed for one need;
        past that there is no option (None). Numbered without a limit, the
        same round-84 board took nine fresh 3-0-0 aces in a row offline
        (the blimp check's best damage per dollar, each counted in full)
        until no legal ace spot was left on the map; past the limit the
        upgrades of the towers standing come next instead."""
        towers = getattr(getattr(self, "g", None), "towers", None) or {}
        tid = next((t for t in self._answer_copy_ids(need, kind) if t not in towers), None)
        if tid is None:
            return None
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
                opt = self._new_tower_option(need, kind, *best) if best is not None else None
                if opt is not None:
                    opts.append(opt)
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

    def round_income(self, r):
        """Cash round r is counted on to bring: the round set's cash times
        income_mult, plus what the board pays besides pops
        (economy.board_income under this mode's rules: Benjamin's Cyber
        Cash at his estimated level in round r, farms, Merchantmen). The
        board is taken as it stands now; the hero's level is the estimate
        only (never a panel read, which would click). Nothing extra in
        CHIMPS and Deflation."""
        cash = TH.round_cash(self.round_set, r) * self.income_mult
        towers = list(getattr(getattr(self, "g", None), "towers", {}).values())
        if not towers:
            return cash
        from .economy import board_income
        hero = getattr(self.g, "hero", None) if any(t.kind == "hero" for t in towers) else None
        level = self._hero_level_estimate(r) if hero else None
        try:
            return cash + board_income(towers, getattr(self, "rules", None), hero, level)
        except Exception:        # never let a projection end a game
            log.exception("board income failed - counting the round's own cash only")
            return cash

    def _hero_level_estimate(self, rnd):
        """The placed hero's level in round rnd by the estimate alone (the
        estimate branch of _hero_level_now), or None."""
        from .abilities import estimate_hero_level, hero_xp_multiplier
        from .match import xp_knowledge
        placed = getattr(getattr(self, "abil", None), "hero_round", None) or getattr(self, "hero_round", None)
        if placed is None or rnd is None:
            return None
        factor = hero_xp_multiplier(getattr(getattr(self, "m", None), "name", None),
                                    xp_knowledge(getattr(self, "account", None), getattr(self, "rules", None)))
        return estimate_hero_level(getattr(self.g, "hero", None), placed, rnd, factor)

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
        income = sum(self.round_income(r) for r in range(rnd, due_round))
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
            from .match import xp_knowledge
            fc = RoundForecast(name, getattr(self, "mode", None), getattr(self.m, "sight", None),
                               (getattr(self.m, "sight_height", None), getattr(self.m, "ground_height", None)),
                               hero=getattr(getattr(self, "g", None), "hero", None),
                               knowledge=xp_knowledge(getattr(self, "account", None), getattr(self, "rules", None)))
            self.forecast = fc
        return fc

    def _board_key(self):
        """What the forecast's answers depend on: every tower, its tiers, its
        spot and its placement round.

        Kind and tiers alone kept a rating after the board changed under it:
        Sanctuary's platforms carry towers to new spots, and a Glacial Trail
        tower sold and bought again in the same spot freezes on its new
        placement round (dynamic-map audit 2026-11-12, item 19)."""
        return tuple(sorted((p.tid, p.kind, tuple(p.tiers), p.x, p.y, getattr(p, "placed_round", None))
                            for p in self.g.towers.values()))

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

    def near_worst(self, rnd, horizon):
        """(margin, round) for the weakest of rounds rnd..rnd+horizon of
        reinforce.py's look-ahead, or None.

        lookahead_worst names the weakest round of the whole look-ahead,
        which may lie past a rule's horizon while a nearer round is weak too:
        Quad Impoppable (2026-11-12 00:13, loss case 20261112_001344) rated
        round 63's ceramic rush 0.59 and round 70 0.46; plan_first_yields
        looked only at round 70, nine rounds off, and kept $7,167 for the
        Ground Zero ac1 2-4-0 ($19,200) while round 63 took the life."""
        end = (getattr(self, "rules", None) or {}).get("end_round", 80)
        rounds = [r for r in RF.lookahead_rounds(rnd, end) if r - rnd <= horizon]
        if not rounds:
            return None
        return self._rated(("near", horizon), rnd, lambda fc, towers: fc.worst(towers, rounds))

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
        rnd = getattr(self, "now_round", None)
        cached = getattr(self, "_mask_cache", None)
        if cached is None or now - cached[0] > self.TRACK_MASK_TTL_S or cached[2] != rnd:
            mask = None
            try:
                f = getattr(self.m, "track_mask", None)
                mask = f() if f else None
            except Exception:      # a half-learned model must not stop the game
                mask = None
            if mask is not None and int(mask.sum()) < 30:
                mask = None
            live = self._live_track_cells(mask) if mask is not None else None
            cached = self._mask_cache = (now, mask, rnd, live)
        mask, total = cached[1], cached[3]
        if mask is None:
            return None
        ys, xs = np.nonzero(mask)
        per_cell = self._track_length() / total      # world units of track per cell

        def reach(tid, kind):
            p = self.g.towers.get(tid)
            if p is None or p.kind != kind:
                return None
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            r = self._range_cells(kind)
            return float(((xs - cx) ** 2 + (ys - cy) ** 2 <= r * r).sum()) * per_cell
        return reach

    def _live_track_cells(self, mask):
        """How many cells of the track mask stand for the paths bloons take
        in the round being played: the cells _reach_fn spreads one path's
        length (_track_length) over.

        During a path phase's lead-in (mapgeom.PHASE_LEAD) the track is
        painted for the next phase's path as well. Spread over both, a cell
        counted half its length, and every tower's blimp reach was halved
        in Erosion rounds 14-18, 32-36, 50-54 and 68-72, so blimp damage
        the defence had was bought again (audit 2026-11-12). The mask is
        scaled by the share of the painted paths' cells (mapgeom.path_masks,
        drawn alike for both) that the round's own paths take. Outside a
        lead-in, or without geometry, every cell of the mask counts."""
        total = int(mask.sum())
        rnd = getattr(self, "now_round", None)
        if rnd is None:
            return total
        from . import mapgeom
        try:
            geom = mapgeom.load(self.m.name)
            if not geom:
                return total
            painted = mapgeom.idle_phase_paths(geom, rnd)
            now = mapgeom.idle_phase_paths(geom, rnd, lead=0)
            if now == painted:
                return total
            proj = mapgeom.Projection(self.m.playfield)
            live = mapgeom.path_masks(geom, proj, now)
            drawn = mapgeom.path_masks(geom, proj, painted)
        except Exception:      # geometry is optional: never let it stop a game
            return total
        if not live or not drawn:
            return total
        share = np.logical_or.reduce(live).sum() / max(1, np.logical_or.reduce(drawn).sum())
        return max(30, int(round(total * min(1.0, float(share)))))

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

    def _first_blimp_round(self):
        """The first round of this game's window that brings blimps, or None.
        Worked out once from the round set (blimp_load) and kept."""
        if not hasattr(self, "_first_blimp"):
            self._first_blimp = next((R for R in range(self.window[0], self.window[1] + 1)
                                      if self.blimp_load(R)), None)
        return self._first_blimp

    def _ramp_lead_for(self, R):
        """How many rounds ahead the blimp check looks at blimp round R:
        _ramp_lead(), but FIRST_BLIMP_LEAD_FACTOR times that for the game's
        first blimp round (never past MAX_LEAD).

        Ravine Magic Only and Pat's Pond ABR (2026-11-10, both Fast Track
        starts at round 22) were lost to round 40's first MOAB. Nothing on
        the map had ever had to pop a blimp, so the defence read 0.1x of the
        1.4x wanted - but the check first looked from round 37. On Ravine the
        damage model had rated round 40 at 0.06 since round 31 while surplus
        cash went to more ninjas and wizards; on Pat's Pond the Ace for the
        MOAB came at round 38-39 and $2,675 was still in hand when it leaked.
        The first blimp round needs a whole MOAB answer bought from nothing,
        so it is looked at as early as Half Cash looks at every blimp round -
        but only after a short start (Fast Track, FIRST_BLIMP_SHORT_START):
        from round 3 the build has 37 rounds to grow into blimp damage, and
        looking early there cost the bomb solo build its round-40 margin in
        the build simulation (0.97 of the 1.0 blimp damage wanted)."""
        lead = self._ramp_lead()
        if R == self._first_blimp_round() and R - self.window[0] < self.FIRST_BLIMP_SHORT_START:
            lead = min(self.MAX_LEAD, lead * self.FIRST_BLIMP_LEAD_FACTOR)
        return lead

    def _far_blimp_round_hopeless(self, R, rnd):
        """True when the damage model rates blimp round R under
        FIRST_BLIMP_HOPELESS on the board as it stands - the condition for the
        blimp check to look at the first blimp round earlier than usual.

        Looking early unconditionally held cash from round 34 in the Ship
        Capture Half Cash simulation and left round 34 itself rated 0.38. The
        two lost games had the model rating round 40 at 0.06 (Ravine) and 0.15
        (Pat's Pond) for six rounds or more: only a defence that the model
        already calls hopeless against the first blimps holds cash early."""
        rated = self._rated(f"blimp{R}", rnd, lambda fc, towers: fc.worst(towers, [R]))
        return bool(rated) and rated[0] is not None and rated[0] < self.FIRST_BLIMP_HOPELESS

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
        """(round, load, ratio) for the first blimp round within _ramp_lead()
        rounds that the defence is short for, else the first blimp round
        there (ratio at the bar or above), or None. Logs the estimate once
        per blimp round.

        A round the defence holds no longer hides the ones behind it.
        Spillway Impoppable (2026-11-10 15:43): on round 79 the check looked
        at round 79's blimps (2.2x, fine) and stopped there; round 80's ZOMG
        (1.1x of 1.4x) was first seen when round 80 began, the cash was held
        for the plan's $24,000 Sun Avatar, and the ZOMG took the one life
        with $18,870 in hand."""
        if rnd is None or self.no_answers or not TH.available():
            return None
        # the widest lead any round may get bounds the scan; each blimp round
        # is then checked only if it is within its own lead (_ramp_lead_for)
        widest = min(self.MAX_LEAD, self._ramp_lead() * self.FIRST_BLIMP_LEAD_FACTOR)
        first = None
        for R in range(max(rnd, self.window[0]), min(rnd + widest, self.window[1]) + 1):
            load = self.blimp_load(R)
            if not load or R - rnd > self._ramp_lead_for(R):
                continue
            if R - rnd > self._ramp_lead() and not self._far_blimp_round_hopeless(R, rnd):
                continue      # early look: only when the damage model agrees it is lost
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
            if ratio < bar:
                return R, load, ratio
            if first is None:
                first = (R, load, ratio)      # held: reported only if no later round is short
                if self._held_round_weak(R, rnd):
                    return first              # it does not really hold: no looking past it
        return first

    def _held_round_weak(self, R, rnd):
        """True when blimp round R passes the blimp check but the damage model
        rates it under 1 on the board as it stands - the round is weak for
        reasons the blimp sum does not see (its non-blimp bloons, reach).

        _ramp_due then reports R and does not look past it: a later short
        round would draw the cash forward and leave R weaker still. Bazaar
        Half Cash (build replay, 2026-11-10): from 358c86c the check skipped
        held round 78 for the short rounds 79-80 and the ace bought for round
        78 stayed at 3-0-0; round 78 fell from 0.53 to 0.39 in the model.
        With no rating (no forecast) the round counts as holding, as before."""
        rated = self._rated(f"blimp{R}", rnd, lambda fc, towers: fc.worst(towers, [R]))
        return bool(rated) and rated[0] is not None and rated[0] < 1.0

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
        path), or a new tower at such a crosspath - unless the towers this
        check placed before speak against another one (_copy_speaks_against)."""
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
                    if gain > 0 and self._copy_speaks_against(kind, t, gain, load, track, rng, reach):
                        continue
                    opt =self._new_tower_option("blimps", kind, T.total_cost(kind, t, fam), t) \
                        if gain > 0 else None
                    if opt is not None:
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
        RAMP_PANIC, even that step waits; with one life the plan also loses its
        turn at once when its next step cannot be paid before round R,
        _plan_step_out_of_reach). When the plan's next step is itself blimp
        damage that can be paid before round R, "plan_hold": the plan goes on
        and its cash is kept for it."""
        cls = max((g["bloon"] for g in TH.round_groups(self.round_set, R)
                   if TH.bloons().get(g["bloon"], {}).get("class") == "blimp"),
                  key=TH.blimp_hp, default=None)
        why = f"blimp ramp round {R} ratio {ratio:.1f}"
        own = [st for st in (self.strat.get("answers") or {}).get(cls) or () if self._step_allowed(st)]
        # what can be paid before round R: cash now + the rounds in between
        money = self.cash_seen + sum(self.round_income(r) for r in range(rnd, R))
        total = self._steps_cost(own, f"the {cls} answer") if own else None
        if total is not None and total > money:
            # The strategy's own answer cannot be finished before the blimps:
            # buying it tier by tier only spends what a cheaper purchase that
            # does stand by round R needs. Sunset Gulch Impoppable (2026-11-10
            # 15:13): the MOAB answer was "n2 -> 2-0-4", n2 had just been found
            # to pop nothing (_redirect_dead_upgrade), so the answer became a
            # fresh ninja to 2-0-4 (~$10.8k); the ramp bought it to 2-0-3 for
            # $4,830 at round 39 while the ace it had placed for round 40 stood
            # at 0-0-0, and the MOAB took the one life with $4,321 in hand.
            note = ("ramp-own-unaffordable", cls, R)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("blimp ramp round %d: the %s answer ($%d) cannot be paid before it "
                            "($%d) - buying blimp damage that can", R, cls, total, money)
            own = []
        for i, st in enumerate(own):
            with self.why("ramp", why, step=dict(st)):
                r = self.try_step(dict(st), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d: bought toward answer %s", R, st)
                return "bought"
            if r == "wait":
                return self._wait_total(self._steps_cost(own[i:], f"the {cls} answer"))
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
            if (rnd < last_call or not (one_life or self._plan_stuck(self.plan[self.idx]))) \
                    and not (one_life and self._plan_step_out_of_reach(self.plan[self.idx], money, R)):
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
        # it (RAMP_MIN_GAIN_SHARE). If nothing fits, save for the cheapest that
        # closes it, else buy the cheapest option that is worth its price
        # (_worth_ramping) - and when none is, buy nothing here.
        #
        # Workshop Impoppable (2026-11-11 17:30, chimps_ninja_sun, loss case
        # 20261111_173206): round 40's MOAB needed 496 more blimp HP in reach
        # and no option gave over 51 of it (the MOAB's own stretch of track is
        # 21 units long, and a tower standing reaches about 3 of them). The
        # fallback then was "the cheapest option of all": a bomb, a $2,946
        # Super Monkey, a dart, an alchemist, a boomerang, an ace and an
        # engineer were placed in rounds 37-39, each of another kind (so
        # _copy_speaks_against had nothing to say), none upgraded - $5,724
        # that left the reading at 0.1x, while the damage model had its own
        # purchases for round 40 waiting. That cash now stays with the plan
        # and with reinforce.
        opts = self._dps_options(load)
        closing = sorted((o for o in opts if o["gain"] >= short), key=lambda o: o["cost"])
        fits = [o for o in closing if o["cost"] <= money] or             [o for o in opts if o["cost"] <= money and o["gain"] >= self.RAMP_MIN_GAIN_SHARE * short]
        rest = closing or sorted((o for o in opts if self._worth_ramping(o, money, short)),
                                 key=lambda o: o["cost"])
        if not fits and not rest and opts:
            best = max(opts, key=lambda o: o["gain"] / max(o["cost"], 1))
            if self._idle_cash_buys(best, cash, rnd, R):
                # The cash has piled up for this one buy and nothing else
                # uses it: the most blimp damage per dollar beats nothing.
                # Sunken Columns Impoppable (2026-11-11 21:30, loss case
                # 20261111_213224): round 96 and 98 were rated 0.4x and 0.2x,
                # the best purchase was a bomb to 0-5-0 ($31,200) with $34-36k
                # in hand, and "nothing matters" left it unbought while the
                # hold dribbled the cash into sub tiers; round 98 took the life
                # with $35,730 in the bank.
                fits = [best]
        if not fits and not rest and opts and ("ramp-nothing-matters", R) not in self.noted:
            self.noted.add(("ramp-nothing-matters", R))
            best = max(opts, key=lambda o: o["gain"] / max(o["cost"], 1))
            log.warning("blimp ramp round %d (%.1fx): %.0f blimp HP are missing and the best purchase "
                        "per dollar (%s, $%d) adds %.0f - all the cash before that round would not "
                        "add a tenth at that rate, so nothing is bought for it here",
                        R, ratio, short, best["desc"], best["cost"], best["gain"])
        for opt in fits or rest[:1]:
            with self.why("ramp", why, option=opt["desc"]):
                r = self.try_step(dict(opt["steps"][0]), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("blimp ramp round %d (%.1fx): bought toward %s ($%d)", R, ratio,
                            opt["desc"], opt["cost"])
                return "bought"
            if r == "wait":
                return self._wait_total(opt.get("cost"))
        return "none"

    # A buy is "what the cash piled up for" when it takes at least this share
    # of the cash in hand: one decisive purchase, not a drip of small ones
    # (the Workshop case in _answer_ramp: six new kinds, $5,724, no effect).
    IDLE_BUY_CASH_SHARE = 0.5

    def _idle_cash_buys(self, opt, cash, rnd, R):
        """Should the ramp buy `opt` (its most blimp damage per dollar) although
        it adds under a tenth of what is missing? Yes when the blimp round is
        at most two rounds off (nothing left to save for), the cash in hand
        pays for it now, and it takes at least IDLE_BUY_CASH_SHARE of that
        cash - a single big upgrade the bank was built for."""
        cost = opt.get("cost") or 0
        return R - rnd <= 2 and 0 < cost <= cash and cost >= self.IDLE_BUY_CASH_SHARE * cash

    def _worth_ramping(self, opt, money, short):
        """Is a blimp-damage option that neither closes the shortfall nor
        adds a tenth of it by itself still worth starting? Yes when all the
        cash that comes before the blimp round (`money`), spent at this
        option's damage per dollar, would add RAMP_MIN_GAIN_SHARE of the
        blimp HP missing (`short`).

        Water Park Impoppable round 84 (tests/test_idle_blimp_damage_offline):
        47,263 HP missing, $33,782 in hand; a 3-0-0 ace adds 3,502 for $3,360
        - 7% by itself, but ten of its kind of purchase are affordable: worth
        it. Workshop Impoppable round 40 (2026-11-11 17:30): 496 HP missing,
        about $5,500 before the round; a 0-3-0 bomb adds 16 for $2,430 - the
        whole cash at that rate adds 36, under the 50 that would be a tenth:
        not worth it."""
        return opt["gain"] / max(opt["cost"], 1) * money >= self.RAMP_MIN_GAIN_SHARE * short

    def _plan_step_out_of_reach(self, st, money, R):
        """Can plan step st not be bought before blimp round R? True when
        its next purchase (_first_step_cost: the placement, or the next tier
        of the upgrade) costs more than `money`, the cash in hand plus the
        whole income of the rounds before R. With one life such a step loses
        its turn to the blimp check at once (_answer_ramp), not only two
        rounds before the blimps: waiting for it buys nothing before round R
        whatever happens.

        Party Parade Impoppable (2026-11-10 21:29, chimps_ninja_sun, case
        20261110_214932): from round 70 the blimp check read round 75's
        seven BFBs at 1.3x of the 2.5x wanted. The plan's next step was the
        Sun Avatar (s1 -> 3-0-2, $24,000) with $5,157 in hand, out of reach
        before round 79 by reinforce's own count, yet the ramp answered
        "plan" through rounds 70-72. Reinforce spent those rounds' $17k on
        Super Monkey tiers the damage model rated "0.63 -> 0.63" for rounds
        76-79, and from round 73 two rounds of cash could add about 2,700 of
        the 11,900 blimp HP still missing. Round 75 took the one life.

        A step the executor cannot price (its tower is gone) is not counted
        out of reach: the plan keeps its turn as before."""
        try:
            cost = self._first_step_cost(st)
        except Exception:
            return False
        if cost is None or cost == float("inf"):
            return False
        if cost > money and ("ramp-plan-unreachable", R) not in self.noted:
            self.noted.add(("ramp-plan-unreachable", R))
            log.warning("blimp ramp round %d: plan step %s ($%d) cannot be paid before it ($%d) - "
                        "the plan gives its turn to blimp damage", R, st, cost, money)
        return cost > money

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

    def _plan_step_is_held_answer(self):
        """Is the plan's next step itself a step of a threat answer the cash
        is being held for (strategy `answers`)? Then the held cash is for this
        very purchase and must not be kept from it.

        Spillway Impoppable (2026-11-12 07:21, loss case 20261112_072317):
        the plan waited on b1 0-5-0 ($31,200), the MOAB Eliminator that is
        also the build's BAD answer; the BAD hold kept $12-20k back, the plan
        step saw only the rest and logged "idle with $37123: plan step 29 b1
        0-5-0 -> wait" for two rounds; it was bought only at round 98, which
        took the life with the rounds before it rated 0.33-0.58."""
        if self.idx >= len(self.plan or ()):
            return False
        step = self.plan[self.idx]
        key = (step.get("do"), step.get("id"), step.get("to"))
        for steps in (self.strat.get("answers") or {}).values():
            for st in steps or ():
                if (st.get("do"), st.get("id"), st.get("to")) == key:
                    return True
        return False

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
        # before the far-round rule: Enchanted Glade Impoppable (2026-11-11,
        # case 20261111_093749_EnchantedGlade_impoppable) held $26,200 of $37,320 for round 100 three
        # rounds ahead while round 98 was rated 0.43, and the plan's $24,000
        # Sun Avatar waited until the game was lost
        # every hold, a blimp-damage one too: Mesa Impoppable (2026-11-11,
        # case 20261111_104642_Mesa_impoppable) kept $11,437 "for blimp damage before round
        # 80" through round 78, rated 0.26, and lost round 78
        if weak and self._likely_lost_first(due_round, rnd):
            note = ("lost-first", what, rnd)
            if note not in self._notes():
                self.noted.add(note)
                log.warning("round %d is rated likely lost with one life: nothing is held for %s "
                            "(round %d) - it is worthless if this round ends the game; the cash "
                            "goes to this round", rnd, what, due_round)
            return None
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

    LIKELY_LOST = 0.5    # a damage-model margin under this: the round is probably lost

    def _likely_lost_first(self, due_round, rnd):
        """Is a hold for a later round pointless because a nearer one is
        probably lost? True in a one-life mode when due_round is still ahead
        and the damage model rates the round being played or the next one
        (margin_now) under LIKELY_LOST: an answer for round 100 buys nothing
        if round 98 takes the only life, so the cash goes to round 98.
        Unrated rounds: False (the older rules decide).

        Chutes Impoppable (2026-11-11, case 20261111_04*): round 98 was
        rated 0.29 while all $26,245 was held "for the bad answer" of round
        100 ($31,200) - the cash plus round 98's income could have paid it,
        so _near_hold_too_late let the hold stand. Reinforcing saw $530,
        the plan's ac2 2-4-0 ($19,200) waited, and round 98 was lost with
        the money in the bank."""
        if due_round is None or rnd is None or due_round <= rnd:
            return False
        if not (getattr(self, "rules", None) or {}).get("one_life"):
            return False
        m = self.margin_now(rnd)
        return m is not None and m < self.LIKELY_LOST

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
                    steps.append({"do": "place", "kind": "village", "role": "support",
                                  "near": self._radar_near_ids(), "near_radius": 8})
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
        if self.held_cash and not self._plan_step_is_held_answer():
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
            if r in ("bought", "progress"):
                # cash was spent ("progress": a tier on the way, or the
                # obstacle its tower needs is gone): the next tick reads it anew
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
            if r == "wait" and self._only_free_steps_left():
                # an ability step waiting for its round, level or margin costs
                # nothing: the fill builds the defence meanwhile
                ability_wait = f"plan step {self.idx} {st} -> {r} ({self.g.fail_reason})"
                break
            self.waiting = f"plan step {self.idx} {st} -> {r} ({self.g.fail_reason})"
            return r == "progress"  # waiting for cash / round, or mid-upgrade
        else:
            ability_wait = None
        for st in self.fill:
            with self.why("fill", "the plan is done: fill step", step=dict(st)):
                r = self.try_step(st, cash, rnd)
            if r in ("bought", "progress"):
                return True
        if ability_wait is None and self._idle_blimp_damage(cash, rnd):
            return True
        self.waiting = ability_wait or PLAN_EXHAUSTED
        return False

    def _idle_blimp_damage(self, cash, rnd):
        """With one life, once the plan and the fill are used up, put idle
        cash into blimp damage for the first blimp round within MAX_LEAD
        that the blimp check reads short of its bar (ramp_bar) - whatever
        the damage model says about that round. True when one step was
        bought.

        `cash` is what tick() may spend: what a far threat holds (held_cash)
        and what reinforce is saving for (reinforce_hold) are already off
        it, so this is the cash the next rounds do not need.

        The damage model may overrule the blimp check (_model_holds) and
        the ramp looks only _ramp_lead() rounds ahead; late in one-life
        games the model overrated blimp rounds again and again. Water Park
        Impoppable (2026-11-11, chimps_sub_druid_water): rounds 84-87 began
        with $33,782 / $40,501 / $47,132 / $47,640 while the check read the
        blimp rounds ahead at 0.4-1.1x of 2.5x and the model rated them
        2.1-3.75 (round 86's rating overruled the check). Little was
        bought until round 87, when the ramp put $41k into a sniper 5-0-0
        too late; round 88's 8 BFBs, 18 MOABs and 2 ZOMGs, then rounds
        89-91, ended the game. With the plan done there is nothing else the
        idle cash is kept for.

        The purchase is chosen as the ramp chooses (_answer_ramp), among
        those the cash pays for in full: the cheapest that closes the
        round's whole shortfall, else the most blimp damage per dollar
        among those adding at least a tenth of it (_dps_options). Nothing
        smaller is bought - the cash stays for reinforce and surplus."""
        if not (self.rules or {}).get("one_life") or self.no_answers or not TH.available():
            return False
        if rnd is None or cash is None or cash <= 0:
            return False
        if not hasattr(self, "calendar"):
            self._init_threats()
        found = None
        for R in range(max(rnd, self.window[0]), min(rnd + self.MAX_LEAD, self.window[1]) + 1):
            load = self.blimp_load(R)
            if not load:
                continue
            ratio = self.blimp_ratio(load)
            if ratio < self.ramp_bar(load):
                found = (R, load, ratio)
                break
        if found is None:
            return False
        R, load, ratio = found
        short = (self.ramp_bar(load) - ratio) * load["hp"]
        opts = [o for o in self._dps_options(load) if o["cost"] <= cash]
        closing = sorted((o for o in opts if o["gain"] >= short), key=lambda o: o["cost"])
        for opt in closing or [o for o in opts if o["gain"] >= 0.1 * short]:
            why = f"idle cash: blimp damage for round {R} ratio {ratio:.1f}"
            with self.why("ramp", why, option=opt["desc"]):
                r = self.try_step(dict(opt["steps"][0]), cash, rnd)
            if r in ("bought", "progress"):
                log.warning("idle cash, plan done: round %d's blimps read %.1fx of the %.1fx wanted - "
                            "bought toward %s ($%d)", R, ratio, self.ramp_bar(load), opt["desc"],
                            opt["cost"])
                return True
        return False

    def _only_free_steps_left(self):
        """True when every plan step from the current one is a `do: ability`
        step: they cost nothing, so neither plan_first nor the plan's wait
        holds the cash for them. Kali Maaaaaaaa on Logs Hard (2026-11-09):
        the sacrifice step waited from round 74 and nothing else was bought
        - rounds 76 and 78 were rated 0.81 and 0.58 with $10k in hand."""
        rest = (getattr(self, "plan", None) or [])[getattr(self, "idx", 0):]
        return bool(rest) and all(st.get("do") == "ability" for st in rest)

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
            # placed this round: on Glacial Trail it freezes on its own phase (reinforce.new_tower)
            after = now + [SimpleNamespace(tid=tid, kind=kind, tiers=tiers, x=spot[0], y=spot[1],
                                           placed_round=getattr(self, "now_round", None))]
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
                spots = self.peek_spots(first["kind"], first, n=1)    # rated only: no probe spent
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

    # buy_plan_step_behind: at most this many later plan steps are tried in one
    # call (a refused step costs clicks, and the round does not wait)
    BEHIND_TRIES = 2

    def plan_step_out_of_reach(self, cash, rnd):
        """(step, cost, round) when the plan's current step waits for cash it
        cannot get in time: it costs more than `cash`
        (reinforce.waiting_plan_step) and cannot be paid before the weakest
        round of the look-ahead (lookahead_worst; the next round when that
        is the one being played) from `cash` and the income until then
        (reinforce.payable_by False). None otherwise - also when the income
        or the rating is unknown, as in reinforce.plan_keeps_claim, whose
        "it holds no cash" is this same test."""
        if cash is None or rnd is None:
            return None
        wait = RF.waiting_plan_step(self, cash)
        if wait is None:
            return None
        worst = self.lookahead_worst(rnd)
        if worst is None or worst[1] is None:
            return None
        due = max(worst[1], rnd + 1)      # the round being played: no income reaches it
        step, cost = wait
        if RF.payable_by(self, cost, cash, due, rnd) is not False:
            return None
        return step, cost, due

    def buy_plan_step_behind(self, cash, rnd):
        """With one life, buy the first later plan step the cash pays for
        while the current step is out of reach (plan_step_out_of_reach).
        True when one was bought.

        Reinforce.buy_best asks this before it spends on a purchase the
        damage model rates as lifting nothing, and when it found nothing to
        buy at all. A purchase the model does rate as lifting the weakest
        round still comes first: this only takes the place of spending the
        model sees no use in, and of an idle bank.

        Enchanted Glade Impoppable (2026-11-11, chimps_ninja_sun, case
        20261111_093749, lost round 98): plan step 16, s1 -> 3-0-2 (the
        $24,000 Sun Avatar), waited from about round 40 to the defeat. It
        could never be paid before the weak round ahead, so it "held no
        cash" 45 times and reinforce spent each round's income - 16 of its
        65 purchases rated "0.06 -> 0.06" and the like. The fifteen plan
        steps behind the Sun Avatar (the MIB village, both Ground Zero aces,
        the exit spikes, the Sabotage ninja, the Eliminator bomb), most of
        them cheaper than a round of reinforcing, were never reached. Mesa
        Impoppable lost round 78 the same day behind the same step, 15 of 40
        reinforce purchases moving nothing (backlog 75).

        A later step qualifies when it is a placement or an upgrade that
          * does not wait for a later round (its `round`),
          * works on a tower that stands (an upgrade), or places one that
            does not stand yet while the tower cap has room,
          * does not wait behind a placement set aside
            (_waits_for_set_aside_place), and
          * costs at most `cash` now (_first_step_cost: the placement, or
            the upgrade's next tier).
        The plan keeps its order otherwise: the stalled step stays the
        current one and is bought as soon as it can be, and the plan reaches
        the step bought here later as "done" (or goes on with its tiers)."""
        if not (getattr(self, "rules", None) or {}).get("one_life"):
            return False
        stalled = self.plan_step_out_of_reach(cash, rnd)
        if stalled is None:
            return False
        step, cost, due = stalled
        tries = 0
        for j in range(self.idx + 1, len(self.plan)):
            st = self.plan[j]
            if st.get("do") not in ("place", "upgrade"):
                continue
            if st.get("round") and rnd < st["round"]:
                continue
            if self._waits_for_set_aside_place(st):
                continue
            standing = st.get("id") in self.g.towers
            if (st["do"] == "upgrade") != standing or (st["do"] == "place" and self.at_tower_cap()):
                continue
            try:
                price = self._first_step_cost(st)
            except Exception:       # a step the executor cannot price is left to the plan
                continue
            if price is None or price > cash:
                continue
            with self.why("plan", f"plan step {j} while step {self.idx} is out of reach",
                          step_idx=j, step=dict(st)):
                r = self.try_step(st, cash, rnd)
            if r in ("bought", "progress"):
                log.warning("plan step %d %s ($%d) cannot be paid before round %d from $%d and the income "
                            "until then - plan step %d %s ($%d) is bought meanwhile",
                            self.idx, step, cost, due, cash, j, st, price)
                return True
            tries += 1
            if tries >= self.BEHIND_TRIES:
                break
        return False

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
        # steps that cost nothing (a waiting `do: ability`) hold no cash
        return (getattr(self, "idx", 0) < len(getattr(self, "plan", None) or [])
                and not self._only_free_steps_left())

    # plan_first_yields: how weak and how near a round must be for a plan_first
    # build's unreachable plan step to give way to reinforcing
    YIELD_MARGIN = RF.CRISIS_MARGIN   # rated under this: a crisis round (forecast.py)
    YIELD_ROUNDS = 4                  # at most this many rounds after the one being played
    # under continuous sends (Apopalypse) a round passes every 3-4 s, so four
    # rounds are ~15 s: look as far as the match's own look-ahead window
    # (10 rounds, "rounds 30-39: the damage model rates round 39 ...")
    CONTINUOUS_YIELD_ROUNDS = 10
    YIELD_FLOOR = 0.12                # rated at most this in a mode with lives: no bloon depth needed

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
            YIELD_FLOOR or less (see the last paragraph), or some of the
            cash of plan steps given up for want of a spot is left
            (given_up_credit, Sanctuary Half Cash 2026-11-09).

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
        win held round 78 rated 0.14 with the same build, so the floor stays
        under that. It was 0.10 until Dark Castle Half Cash (2026-11-09 13:21,
        same build) lost round 78 rated 0.11: after the Dartship came at round
        75 the plan waited for h1 4-2-0 ($21,600) with $4.8-9.6k in hand, out
        of reach before round 78, and 0.11 missed the old floor by 0.01. The
        floor is now 0.12, still clear of Spillway's 0.14.

        Under continuous sends (rules `continuous`, Apopalypse) both clocks
        are counted in rounds that last 3-4 s. The weak round may be up to
        CONTINUOUS_YIELD_ROUNDS away, and the step must be payable within
        reinforce.CONTINUOUS_SAVE_ROUNDS rounds - the same test reinforce
        puts on its own savings there. Sanctuary Apopalypse (2026-11-10
        03:00, apopalypse_apache_spikes) held $11.8-15.9k for h3 4-2-0
        through rounds 30-33 while the model rated round 39 at 0.37-0.38
        (8-9 rounds off) and bloons reached 91-93 % of the route; round 33
        then cost 109 lives. With four rounds of horizon the rule never
        looked that far."""
        if cash is None or rnd is None or not self.plan_first():
            return False
        rules = getattr(self, "rules", None) or {}
        if rules.get("income") is False:
            return False          # no income: saving is all the step has
        wait = RF.waiting_plan_step(self, cash)
        if wait is None:
            return False
        continuous = bool(rules.get("continuous"))
        horizon = self.CONTINUOUS_YIELD_ROUNDS if continuous else self.YIELD_ROUNDS
        # the weakest round within reach of the rule, not of the whole look-ahead
        worst = self.near_worst(rnd, horizon)
        if worst is None or worst[0] is None or worst[1] is None:
            return False
        margin, weak = worst
        if margin >= self.YIELD_MARGIN or weak - rnd > horizon:
            return False
        credit = 0
        # One life: a round rated at the floor counts without the depth only
        # when it is the next one - it may kill in one go, as Midnight Mansion
        # Impoppable's round 63 did (2026-11-12 00:36, loss case
        # 20261112_003659: rated 0.06 from round 60, the bloons of rounds 60-61
        # at 73-79%, $8-18k held for sn1 5-2-0 at $38,400, nothing bought).
        # Floor ratings are often survived (235 of 251 such rounds in the
        # one-life journals, mostly on Erosion and Midnight Mansion, whose
        # ratings were too low), so further-off ones still wait for the depth.
        floor_next = bool(rules.get("one_life")) and margin <= self.YIELD_FLOOR and weak - rnd <= 1
        if not deep and not floor_next and (rules.get("one_life") or margin > self.YIELD_FLOOR):
            # shallow bloons: only a floor rating in a mode with lives counts -
            # or cash the plan meant to spend on steps it had to give up
            credit = self.given_up_credit()
            if credit <= 0:
                return False
        step, cost = wait
        pay_by = max(weak, rnd + 1)   # the round being played: no income reaches it
        if continuous:
            # back-to-back rounds: a saving longer than a few rounds is not one
            pay_by = min(pay_by, rnd + RF.CONTINUOUS_SAVE_ROUNDS)
        if RF.payable_by(self, cost, cash, pay_by, rnd) is not False:
            return False
        note = ("plan-first-yields", getattr(self, "idx", None), weak)
        if note not in self._notes():
            self.noted.add(note)
            log.warning("plan_first: plan step %s ($%.0f) cannot be paid before round %d from $%d and the "
                        "income until then, and the damage model rates round %d at %.2f - reinforce may "
                        "spend for that round%s", step, cost, pay_by, cash, weak, margin,
                        f" (up to ${credit:.0f} of given-up plan steps)" if credit else "")
        return True

    def given_up_plan_cost(self):
        """What the build's own plan steps before the current one would have
        cost, had their tower not been given up: each `place` step of the
        plan given up for this game (dead_steps, no spot accepted) and the
        plan's upgrades of that id, priced like an answer (_sim_step from an
        empty board). An id that stands on the board after all (placed later,
        or a stand-in from _redirect_dead_upgrade) is not counted.

        This is cash the plan meant to have spent by now. Its timing - when
        the next big step comes, and what defends the rounds before it - was
        written with those towers in it; without them the bank piles up
        toward the big step while the rounds they were meant to carry come
        unguarded (backlog 70, Sanctuary Half Cash)."""
        dead = getattr(self, "dead_steps", None)
        plan = getattr(self, "plan", None) or []
        if not dead or not plan:
            return 0
        towers = getattr(self.g, "towers", {}) or {}
        pending = getattr(self, "redirected", {}) or {}
        ids = {key[3] for key in dead
               if key[0] == "place" and key[3] and key[3] not in towers and key[3] not in pending}
        sim, cost = {}, 0
        for n, st in enumerate(plan[:getattr(self, "idx", 0)]):
            if st.get("id") in ids and st.get("do") in ("place", "upgrade"):
                cost += self._sim_step(st, sim, n) or 0
        return cost

    def given_up_credit(self):
        """given_up_plan_cost less what reinforce has bought for a plan_first
        build since (yield_spent, counted in reinforce.buy_best): how much of
        the given-up steps' cash plan_first_yields may still let reinforce
        spend while the bloons are shallow.

        Sanctuary Half Cash (2026-11-09 22:23, hard_ninja_alch_sun, won but
        lost 69 lives at rounds 63-64): the platforms left no spot for v1, v2
        (Radar Scanner), d2 (druid 0-3-2) and h3 (heli 3-2-0), so the plan
        went straight on to h1 4-2-0 ($21,600) and idled with $2-21k from
        round 52 to 63 while every round was rated 0.15-0.52. The bloons
        stayed at 82-86% of the route, under PLAN_YIELD_DEPTH, and no round
        was rated at YIELD_FLOOR, so the cash never moved until round 63 cost
        65 lives. The given-up towers' share of the bank was never the
        Dartship's to wait for. Capped by what they would have cost, so the
        big step is late by no more than the plan itself had planned to
        spend before it."""
        return self.given_up_plan_cost() - (getattr(self, "yield_spent", 0) or 0)

    def surplus(self, cash, rnd, deadline=None):
        """Cash is piling up while the plan waits: buy damage anyway.

        1. next tier on an existing tower's own path (biggest investment first),
           respecting crosspaths, tower XP locks and the mode's tower filter
        2. another copy of the strategy's main tower
        Never violates constraints (kind_allowed) and never sells. Never
        spends cash that the last tick() held back for a threat's answer:
        that money is being saved for a bloon the defence cannot pop yet.
        Nor the cash a plan step is waiting for (plan_claim): what is left
        above its claim is spare, and in a crisis of the round being played
        only a purchase that lifts that round may have it.

        Rating what lifts the round (_lifts_now) stops at `deadline` (a
        time.monotonic(); default reinforce.LOOK_BUDGET_S from now), and
        nothing is bought then. Each rating is up to six damage-model
        margins: on X Factor Impoppable (2026-11-10, one life, round 85, 37
        towers, 20 affordable upgrades none of which lifted the round) one
        call asked 126 margins and took 105 s offline, and the live game
        logged 24 loop stalls of 11-61 s "in surplus" from 17:13, the first
        game after one-life surplus began asking _lifts_now (06317a3). The
        forecast remembers its ratings (forecast._memo), so the next call
        on the same board goes on where this one stopped and buys what it
        would have bought."""
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
        if not rated and (getattr(self, "rules", None) or {}).get("one_life"):
            # With one life, while the look-ahead is weak, spare cash buys
            # only what lifts it. Infernal Impoppable (2026-11-10): with rounds 71-78 rated
            # 0.26-0.83, surplus put $19,200 and $28,600 into ace1 2-4-0 and
            # 2-5-0, which the model rated as no lift at all, while mermonkey1
            # 5-2-0 ($27,600) would have taken round 76 from 0.36 to 1.28;
            # round 78 took the one life with $11k left.
            worst = self.lookahead_worst(rnd)
            rated = bool(worst and worst[0] is not None and worst[0] < RF.WEAK_MARGIN)
        # An XP build (strategies/generated: `xp_target`) puts surplus into the
        # tower it levels up first - tower XP follows invested cash - and only
        # then into helpers, side paths or the opener.
        target = self.strat.get("xp_target") if isinstance(getattr(self, "strat", None), dict) else None
        if deadline is None:
            deadline = RF.look_deadline()
        # with no income the plan's crosspath caps would strand cash: the
        # leading path may go further (as reinforce.py does)
        for p, t, cost in self.upgrade_choices(first=target, past_plan=bool(self.rules.get("buy_all_upfront"))):
            if cost > cash:
                continue
            to = "-".join(map(str, t))
            step = {"do": "upgrade", "id": p.tid, "to": to}
            if rated and RF._past(deadline):
                self._surplus_out_of_time()
                return False
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
            if rated and RF._past(deadline):
                self._surplus_out_of_time()
                return False
            if rated and not self._lifts_now(step, self.g.price(main), rnd):
                return False
            with self.why("surplus", f"spare cash: another {main}"):
                r = self.try_step(step, cash, rnd)
            if r == "bought":
                log.info("surplus: placed another %s", main)
                return True
        return False

    def _surplus_out_of_time(self):
        """Say, once a round, that surplus stopped rating at its deadline."""
        note = ("surplus_budget", getattr(self, "now_round", None))
        if note in self.noted:
            return
        self.noted.add(note)
        log.info("surplus: the %.0f s budget ran out while rating what lifts round %s - "
                 "going on at the next look", RF.LOOK_BUDGET_S, getattr(self, "now_round", None))

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

    # Fixed aim points for the towers that shoot at a spot rather than at
    # bloons (docs/model_fix_plan.md item 14): a Mortar's reticle, and a
    # Dartling set to Locked. Both go to the densest track point, the one
    # the cursor is parked on (match.densest_track_point), so the model can
    # credit them at one known point. OFF until checked in game, because
    # neither flow has been seen live:
    #   MORTAR_AIM: that a placed Mortar's panel shows "Set Target" in the
    #     targeting row, and that clicking it and then the map moves the
    #     reticle there (Game.set_target_point; frames in logs/aim_*.png);
    #     also whether a new Mortar has a default reticle at all.
    #   DARTLING_LOCK: that a Dartling's targeting cycles to "Locked" with
    #     the targeting arrows, and whether Locked then takes its point from
    #     a Set Target button (as the Mortar's) or from where the cursor was.
    #     The default after placement (Follow Touch per this code, Locked at
    #     the map centre per a Fandom version note) is also unconfirmed.
    MORTAR_AIM = False
    DARTLING_LOCK = False

    def _aim_point(self):
        """The fixed aim point for a Mortar or a locked Dartling: the
        densest track point (match.densest_track_point), or None."""
        from .match import densest_track_point
        try:
            return densest_track_point(self.m)
        except Exception:
            log.exception("aim point failed")
            return None

    def _aim_fixed(self, p):
        """Give a Mortar its reticle, or lock a Dartling on the aim point,
        once per tower (MORTAR_AIM / DARTLING_LOCK). p.aim becomes "point",
        or "failed point" so it is not tried on every upgrade."""
        if getattr(p, "aim", None) in ("point", "failed point"):
            return
        point = self._aim_point()
        if point is None:
            return
        try:
            ok = True
            if p.kind == "dartling":
                ok = self.g.target(p, "lock")
            ok = ok and self.g.set_target_point(p, *point)
        except Exception:          # aiming is a nicety: never cost a game over it
            log.exception("setting %s's aim point failed", p.tid)
            ok = False
        p.aim = "point" if ok else "failed point"
        (log.info if ok else log.warning)("%s aim point %s: %s", p.tid, point, "set" if ok else "not set")

    def _explicit_target(self, p):
        """Does the plan set this tower's targeting itself?"""
        return any(st.get("do") == "target" and st.get("id") == p.tid for st in self.plan + self.fill)

    def _aim(self, p):
        """Set a heli's targeting so it stops following the mouse; give a
        Mortar or a Dartling its fixed aim point when MORTAR_AIM /
        DARTLING_LOCK are on."""
        if self._explicit_target(p):
            return
        if (p.kind == "mortar" and self.MORTAR_AIM) or (p.kind == "dartling" and self.DARTLING_LOCK):
            self._aim_fixed(p)
            return
        if p.kind != "heli":
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
                                # (more when it has more points to click: _removal_tries)

    def _removal_tries(self, r):
        """How many failed attempts obstacle r gets before it is left alone
        for the game: REMOVAL_TRIES, or one per click point when the map
        gives it more of them (mapgeom.removables "click_fracs")."""
        return max(self.REMOVAL_TRIES, len(r.get("click_fracs") or ()))

    def _buy_removal(self, r):
        """Click obstacle r and pay for its removal (Game.remove_obstacle).
        True when it is gone - it is then listed in self.removed and the
        steps given up for want of ground come back (_ground_cleared). A
        failed attempt is counted, and the next one clicks the obstacle's
        next point: the middle of its outline first, then the others the
        map gives (mapgeom._other_click_points).

        Mushroom Grotto Impoppable (2026-11-11, lost at round 93): both
        attempts on the main mushroom clicked the middle of its outline,
        the foot of the stalk, where the game opens no removal box."""
        fails = self.removal_fails.get(r["id"], 0)
        points = r.get("click_fracs") or [r["frac"]]
        fx, fy = points[fails % len(points)]
        if self.g.remove_obstacle(fx, fy, r["cost"], name=r["name"]):
            self.removed.append(r["id"])
            self._ground_cleared()
            return True
        self.removal_fails[r["id"]] = fails + 1
        return False

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
                if r["id"] not in self.removed and self.removal_fails.get(r["id"], 0) < self._removal_tries(r)]

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
        if self.removal_fails.get(r["id"], 0) >= self._removal_tries(r):
            return "skip"
        if cash is None or cash < r["cost"]:
            return "wait"
        log.info("clearing obstacle %s ($%s) for the plan", r["name"], r["cost"])
        return "bought" if self._buy_removal(r) else "wait"

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
        return self._buy_removal(best)

    # A plan placement waiting for an obstacle (_clear_for_place) looks again
    # this often (s): the cash for the removal comes in meanwhile.
    CLEAR_RETRY_S = 5.0
    # ... and tries at most this many obstacles, the ones that free the most
    # ground for its tower: each trial is a full spot search (~0.25 s each on
    # High Finance, which has fifteen obstacles).
    CLEAR_TRIALS = 6

    def _plan_place_ids(self):
        """The ids of the towers the build's plan places (once per game)."""
        if not hasattr(self, "_plan_place_id_set"):
            self._plan_place_id_set = {st["id"] for st in getattr(self, "plan", None) or ()
                                       if st.get("do") == "place" and st.get("id")}
        return self._plan_place_id_set

    def _clear_for_place(self, step, key, kind, cash):
        """A plan placement found no spot at all (_spots_widening): when a
        removable obstacle would give it one, the step is not given up. It is
        set aside (self.deferred, the plan goes on) until the cash covers the
        obstacle and the tower, then the obstacle is bought ('progress') and
        the next tick places the tower on the freed ground. Returns None when
        this is not a case for it - the step is then given up as before.

        High Finance Impoppable (2026-11-11 08:31, chimps_ninja_sun, loss
        case 20261111_090319): nearly all of the map's land lies under
        fifteen removable plazas. Its geometry gives a ninja 36 legal cells
        and a village, a Super Monkey or an ace none; after n1, the opener,
        the hero and n2 no kind had a cell left. The alchemist was given up
        at round 14 and at round 35 both villages, the Sun Avatar, both
        Ground Zero aces, the Sabotage ninja, the MOAB Eliminator bomb and
        the exit spikes went the same way in one second ("0 legal cells",
        "after 0 refused spots") - the whole build from round 35 on. Only
        surplus ever bought obstacles (clear_obstacle, for "another ninja",
        from round 50); by then the plan was past those steps, the cash went
        into twelve bare ninjas and what reinforce could rate, and round 95
        was lost at 0.35. The game of 2026-11-10 (round 98) ran the same way.

        Which obstacle: the one whose ground gives the step its best spot
        (_obstacle_for_place), chosen once per state of the map and kept in
        self.clear_wait. While one step waits for its obstacle, the others
        with no ground wait behind it without a search of their own - the
        freed plaza usually has room for them too - and no more than one
        search is made per tick, so a run of such steps (thirteen at once
        above) cannot hold the match loop up."""
        if getattr(self, "no_removals", True) or kind == "hero":
            return None             # the hero has its own retry (_out_of_spots)
        if step.get("id") not in self._plan_place_ids():
            return None             # fills, answers and panic steps run every tick anyway
        gone = tuple(self.removed)
        entry = self.clear_wait.get(key)
        if entry is None or entry[0] != gone:
            behind = any(k != key and rem == gone and r is not None
                         for k, (rem, r) in self.clear_wait.items())
            tick = getattr(self, "tick_no", None)
            if behind or (tick is not None and getattr(self, "_clear_search_tick", None) == tick):
                if not self._obstacles():
                    return None
                return self._defer(step, key, self.CLEAR_RETRY_S)
            self._clear_search_tick = tick
            entry = self.clear_wait[key] = (gone, self._obstacle_for_place(kind, step))
        choice = entry[1]
        if choice is None or self.removal_fails.get(choice["id"], 0) >= self._removal_tries(choice):
            self.clear_wait.pop(key, None)
            return None
        need = choice["cost"] + self.g.price(kind)
        if cash is None or cash < need:
            noted = self.__dict__.setdefault("_clear_noted", set())
            if key not in noted:
                noted.add(key)
                log.info("%s: no ground for it - set aside until $%d buys obstacle %s ($%d) and the tower",
                         step.get("id"), need, choice["name"], choice["cost"])
            return self._defer(step, key, self.CLEAR_RETRY_S)
        log.info("clearing obstacle %s ($%s) for plan step %s: no ground for its %s without it",
                 choice["name"], choice["cost"], step.get("id"), kind)
        self.clear_wait.pop(key, None)
        if self._buy_removal(choice):
            self._defer(step, key, 0)   # stays in line: placed at the next tick
            return "progress"
        return self._defer(step, key, self.CLEAR_RETRY_S)

    def _obstacle_for_place(self, kind, step):
        """The removable obstacle whose ground gives place step `step` its
        best spot, or None when none gives it one. Tried: the CLEAR_TRIALS
        obstacles that free the most legal ground for `kind`, each by
        searching for the step's spots as if it were gone. An obstacle that
        satisfies the step as written (its `near`, its segment) comes before
        one that only fits a relaxed search; then the better spot, then the
        lower price."""
        from . import placement as PL
        placed = [(*self.m.frac_to_cell(p.x, p.y), p.kind, self.g.hero if p.kind == "hero" else None)
                  for p in self.g.towers.values()]
        where = {"land"} if self.land_only else None
        gone = tuple(self.removed)
        base = PL.valid_spots(self.m, kind, None, placed, where=where, removed=gone)
        if base is None:
            return None
        gains = []
        for r in self._obstacles():
            after = PL.valid_spots(self.m, kind, None, placed, where=where, removed=gone + (r["id"],))
            gain = int((after & ~base).sum()) if after is not None else 0
            if gain >= self.REMOVAL_MIN_CELLS:
                gains.append((gain, r))
        gains.sort(key=lambda t: -t[0])
        best, best_rank = None, None
        level = log.level
        log.setLevel(logging.WARNING)       # the trial searches' dead ends are not the game's
        try:
            for _, r in gains[:self.CLEAR_TRIALS]:
                self.removed.append(r["id"])
                try:
                    strict = self.pick_spots(kind, step, n=1)
                    spots = strict or self._spots_widening(kind, step)
                finally:
                    self.removed.pop()
                if not spots:
                    continue
                rank = (bool(strict), spots[0][2], -r["cost"])
                if best_rank is None or rank > best_rank:
                    best, best_rank = r, rank
        finally:
            log.setLevel(level)
        return best

    def _ground_cleared(self):
        """An obstacle was just bought: place steps given up because the
        map had no ground for them (no spot the game refused, see
        refused_dead_steps) get another look. Plan steps go back in line
        (self.deferred) unless their tower stands by now; fill, panic and
        answer steps are simply offered again by whoever runs them.

        High Finance Impoppable (2026-11-11): the blimp answers' ace and
        sniper were given up at round 35 with 0 legal cells; from round 50
        surplus cleared seven plazas (892 legal ninja cells), and the blimp
        check still could not ask for either."""
        dead = getattr(self, "dead_steps", None)
        if not dead:
            return
        refused = getattr(self, "refused_dead_steps", ())
        back = {k for k in dead if k not in refused and k[0] == "place"}
        if not back:
            return
        self.dead_steps -= back
        towers = getattr(self.g, "towers", {}) or {}
        plan = getattr(self, "plan", None) or ()
        passed = plan[:getattr(self, "idx", 0)]
        waiting = {self._step_key(st) for st in self.deferred}
        for st in plan:
            k = self._step_key(st)
            if k in back and k not in waiting and st.get("id") and st["id"] not in towers:
                self.deferred.append(st)
                waiting.add(k)
                # The plan skipped this tower's upgrades when it came to them
                # with no such tower: they go in line behind the placement
                # (tick() takes a tower's set-aside steps in plan order). The
                # replay of the lost game put v1 back as a bare village.
                self.deferred.extend(up for up in passed if up.get("do") == "upgrade"
                                     and up.get("id") == st["id"] and up not in self.deferred)
        log.info("an obstacle is gone: %d place steps given up for want of ground are tried again", len(back))

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
        where income pays nothing (_income_pays_nothing).

        A tower that pops nothing (_dead) is offered no tier at all. When the
        defence is short, sell_useless keeps such a tower standing
        (_sale_blocked), and until 2026-11-09 surplus and reinforce went on
        buying tiers for it: the bot logs of 2026-11-05 to 11-09 show about
        170 tiers ($388k) bought for towers already logged as "keeping ...
        although not a single pop" - e.g. Water Park ABR's boomerang1, 58
        rounds at a spot no bloon passed. That cash belongs on towers that
        pop (plan upgrades for a dead tower move to a fresh one, see
        _redirect_dead_upgrade)."""
        towers = sorted((p for p in self.g.towers.values() if p.kind != "hero" and not self._dead(p)),
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
