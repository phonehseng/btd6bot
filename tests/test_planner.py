"""Planner simulation + invariants. Run: python tests/test_planner.py
(also collectable by pytest). Does not touch the game."""

from __future__ import annotations

import logging
import math
import os
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btd6bot import planner as P  # noqa: E402
from btd6bot.account import (  # noqa: E402
    EXCLUDED_MAPS, EXCLUDED_MODES, GIFT_BOX_TOWERS, MAPS, MODES, AccountState,
    level_for_xp, rounds_xp, xp_for_level,
)

# Tests must not depend on which tracks data/maps happens to hold right now.
P.DEFAULT_CONFIG.maps_dir = None
# ... nor on the live achievement catalog/scan (tests pass their own).
P.DEFAULT_CONFIG.achievements_path = None
P.DEFAULT_CONFIG.achievements_state_path = None
# Paragon focus off by default; the paragon tests switch it on with a config
# that points at the (static) tower XP price table.
P.DEFAULT_CONFIG.tower_xp_path = None
PARAGON_CFG = P.PlannerConfig(maps_dir=None, achievements_path=None,
                              achievements_state_path=None, tower_xp_path=str(P.TOWER_XP_FILE))


# --------------------------------------------------------------- simulation

def _settle(acc: AccountState, log: list[str]) -> None:
    """What the runner does between games: tower picks, upgrades, MK."""
    while acc.pending_tower_choices:
        cat = acc.pending_tower_choices[0]
        tower, why = P.choose_tower_unlock(cat, acc)
        if tower is None:
            acc.pending_tower_choices.pop(0)
            continue
        acc.unlock_tower(tower)
        log.append(f"  L{acc.player_level} unlock {cat}: {tower} ({why[0]})")
    steps, _ = P.choose_upgrade_unlocks(acc)
    for s in steps:
        if s.affordable:
            acc.unlock_upgrade(s.tower, s.path, s.tier, cost=s.est_cost)
    picks, _ = P.choose_mk(acc)
    while acc.mk_points > 0 and picks:
        acc.unlock_mk(picks.pop(0).name)


def _check_plan(acc: AccountState, plan: P.GamePlan, strategies: dict) -> None:
    assert plan.map in MAPS and plan.map not in EXCLUDED_MAPS, plan.map
    assert plan.mode_key in MODES and plan.mode_key not in EXCLUDED_MODES, plan.mode_key
    assert acc.map_unlocked(plan.map), f"planned locked map {plan.map}"
    assert acc.mode_unlocked(plan.map, plan.mode_key), f"planned locked mode {plan.map}/{plan.mode_key}"
    s = strategies[plan.strategy_id]
    ok, why = P._strategy_available(s, acc)
    assert ok, f"unavailable strategy {s.id}: {why}"
    assert P._strategy_fits(s, plan.map, acc.map_category(plan.map), plan.mode_key)
    mi = MODES[plan.mode_key]
    assert (plan.difficulty, plan.mode) == (mi.difficulty, mi.ui_mode)
    if plan.mode_key == "chimps":
        assert plan.p_win >= P.DEFAULT_CONFIG.min_p_chimps * 0.999, plan
    if plan.hero is not None:
        assert plan.hero in acc.unlocked_heroes


def simulate(n_games: int, seed: int = 1, verbose_first: int = 40
             ) -> tuple[AccountState, list[str]]:
    rng = random.Random(seed)
    acc = AccountState()
    acc.HISTORY_LIMIT = 10 ** 6  # keep the whole run for the order checks
    strategies = {s.id: s for s in P.EXAMPLE_STRATEGIES}
    log: list[str] = []
    phase = None
    minutes_total = 0.0
    for g in range(n_games):
        _settle(acc, log)
        plan = P.next_game(acc, strategies.values())
        if plan is None:  # no winnable first-time medal left: the runner would idle
            log.append(f"== nothing left to play after {g} games")
            break
        assert not acc.has_medal(plan.map, plan.mode_key), f"replay planned: {plan.reason}"
        _check_plan(acc, plan, strategies)
        if plan.phase != phase:
            log.append(f"== game {g + 1}: phase {plan.phase} ({P.PHASES.get(plan.phase, '')}) "
                       f"L{acc.player_level} uniq={acc.unique_map_wins()} medals={acc.medal_count()}")
            phase = plan.phase
        s = strategies[plan.strategy_id]
        cat = acc.map_category(plan.map)
        # "reality" = the planner's prior (declared rate x map x readiness)
        p_true = P.prior_win_probability(acc, s, plan.map, plan.mode_key)
        won = rng.random() < p_true
        xp = P.game_xp(plan.mode_key, cat) if won else P.game_xp(plan.mode_key, cat, fail_frac=0.6)
        mm = P.estimate_mm(acc, plan.map, plan.mode_key)[0] if won else 0
        mins = MODES[plan.mode_key].minutes if won else MODES[plan.mode_key].minutes * 0.6
        scan = 0.0 if plan.map in acc.map_stats else P.DEFAULT_CONFIG.first_visit_minutes
        minutes_total += mins + 1 + scan
        if g < verbose_first:
            log.append(f"{g + 1:3d} L{acc.player_level:<3d} {plan.phase:4s} {plan.map:<20.20s} "
                       f"{plan.mode_key:<13s} {plan.strategy_id:<22s} hero={plan.hero or '-':<13s} "
                       f"p={plan.p_win:.2f} {'WIN ' if won else 'loss'} | {plan.reason[:110]}")
        acc.record_result(plan.map, plan.mode_key, plan.strategy_id, won,
                          round_reached=None, minutes=mins, xp_gained=xp, mm_gained=int(mm),
                          tower_xp_gained=P.split_tower_xp(s, xp), hero=plan.hero)
        if not acc.remaining_goals():
            log.append(f"== ALL MEDALS after {g + 1} games, ~{minutes_total / 60:.0f} h, L{acc.player_level}")
            break
    games = sum(st["wins"] + st["losses"] for st in acc.strategy_stats.values())
    losses = sum(st["losses"] for st in acc.strategy_stats.values())
    hard = sum(1 for d in acc.medals.values() if d.get("hard"))
    log.append(f"== end: games={acc.games_played} L{acc.player_level} MM={acc.monkey_money} "
               f"medals={acc.medal_count()}/{len(acc.all_goals())} uniq={acc.unique_map_wins()} "
               f"hard={hard} losses={losses}/{games} ~{minutes_total / 60:.0f} h")
    return acc, log


# -------------------------------------------------------------------- tests


def _hard_first(fn):
    """Run a test of the Hard-tier logic (sub-mode chains, learned tracks
    first, ...) with the Hard-first tier order: the default warm-up order
    (Easy, Medium, then Hard) would put Easy medals ahead of it."""
    import functools

    @functools.wraps(fn)
    def run(*a, **kw):
        saved = P.TIERS
        P.TIERS = P.TIERS_HARD_FIRST
        try:
            return fn(*a, **kw)
        finally:
            P.TIERS = saved
    return run


def test_xp_tables():
    assert rounds_xp(1, 40) == 21_400
    assert rounds_xp(31, 60) == 45_950
    assert rounds_xp(1, 60) == 56_950
    assert rounds_xp(3, 80) == 126_150
    assert rounds_xp(6, 100) == 231_150
    assert xp_for_level(10) == 19_850 and xp_for_level(30) == 274_000
    assert level_for_xp(19_849) == 9 and level_for_xp(19_850) == 10


def test_mode_unlocks_and_categories():
    acc = AccountState()
    assert acc.mode_unlocked("Monkey Meadow", "easy")
    assert acc.mode_unlocked("Monkey Meadow", "hard")
    assert not acc.mode_unlocked("Monkey Meadow", "deflation")
    assert not acc.mode_unlocked("Monkey Meadow", "chimps")
    assert not acc.map_unlocked("Infernal")
    assert not acc.map_unlocked("Blons") and not acc.map_unlocked("Protect The Yacht")
    acc.record_result("Monkey Meadow", "easy", "x", True)
    assert acc.mode_unlocked("Monkey Meadow", "primary_only")
    acc.record_result("monkey meadow", "primary_only", "x", True)
    assert acc.mode_unlocked("Monkey Meadow", "deflation")
    assert not acc.mode_unlocked("Monkey Meadow", "boss")
    for m in list(MAPS)[:5]:
        acc.record_result(m, "easy", "x", True)
    assert acc.unique_map_wins() == 5 and acc.category_unlocked("intermediate")
    assert not acc.category_unlocked("advanced")


def test_apply_level_rewards():
    acc = AccountState()
    ev = acc.apply_level(30)
    assert {"quincy", "gwendolin", "striker_jones", "obyn"} <= acc.unlocked_heroes
    assert acc.monkey_money == 250, acc.monkey_money
    assert acc.pending_tower_choices.count("primary") == 5
    assert acc.pending_tower_choices.count("military") == 6
    assert acc.pending_tower_choices.count("magic") == 5
    assert acc.pending_tower_choices.count("support") == 4
    assert acc.mk_points == 1 and ev


def test_tower_unlock_order():
    acc = AccountState()
    acc.apply_level(26)
    picks: dict[str, list[str]] = {}
    while acc.pending_tower_choices:
        cat = acc.pending_tower_choices[0]
        t, why = P.choose_tower_unlock(cat, acc)
        assert t not in GIFT_BOX_TOWERS and why
        acc.unlock_tower(t)
        picks.setdefault(cat, []).append(t)
    for cat, order in picks.items():
        assert order == P.TOWER_UNLOCK_PRIORITY[cat][: len(order)], (cat, order)
    # with an explicit on-screen offer the priority still wins
    acc2 = AccountState()
    t, _ = P.choose_tower_unlock("primary", acc2, options=["Ice Monkey", "Tack Shooter", "Bomb Shooter"])
    assert t == "bomb", t
    return picks


def test_upgrade_unlocks_sequential():
    acc = AccountState()
    acc.unlocked_towers |= {"sniper", "alchemist", "village"}
    acc.tower_xp = {"sniper": 50_000, "dart": 300}
    steps, why = P.choose_upgrade_unlocks(acc)
    assert steps and why
    seen: dict[tuple[str, int], int] = {}
    for s in steps:
        prev = seen.get((s.tower, s.path), acc.upgrades(s.tower)[s.path])
        assert s.tier == prev + 1, s
        seen[(s.tower, s.path)] = s.tier
    assert any(s.tower == "sniper" and s.affordable for s in steps)
    assert not any(s.tower == "alchemist" and s.affordable for s in steps)


def test_mk():
    acc = AccountState()
    picks, why = P.choose_mk(acc)
    assert picks[0].name == P.MO_MONKEY_MONEY and why
    acc.unlock_mk(P.MO_MONKEY_MONEY)
    picks, _ = P.choose_mk(acc)
    assert picks[0].name != P.MO_MONKEY_MONEY


def test_learning_avoids_failing_strategy():
    acc = AccountState()
    s = P.strategy_by_id("dart_quincy")
    p0 = P.win_probability(acc, s, "Monkey Meadow", "easy")[0]
    for _ in range(6):
        acc.record_result("Monkey Meadow", "easy", "dart_quincy", False)
    p1 = P.win_probability(acc, s, "Monkey Meadow", "easy")[0]
    assert p1 < p0 and p1 < P.p_threshold("easy"), (p0, p1)
    # the losing (map, mode, strategy) is no longer offered at all
    _, _, cands = P.rank_games(acc)
    assert not [c for c in cands if (c.map, c.mode, c.s.id) == ("Monkey Meadow", "easy", "dart_quincy")]


def test_save_load_roundtrip():
    acc, _ = simulate(15, seed=3, verbose_first=0)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "account.json"
        acc.save(p)
        acc2 = AccountState.load(p)
        assert acc2.to_dict()["medals"] == acc.to_dict()["medals"]
        assert acc2.unlocked_towers == acc.unlocked_towers
        assert acc2.strategy_stats == acc.strategy_stats
        assert not [f for f in os.listdir(d) if f.endswith(".tmp")]


def test_fresh_account_first_40():
    acc, log = simulate(40, seed=7, verbose_first=40)
    print("\n".join(log))
    assert acc.unique_map_wins() >= 5


def _medal_order(acc: AccountState) -> list[tuple[str, str]]:
    """(map, mode) of every medal in the order the simulation earned them."""
    got: set[tuple[str, str]] = set()
    order = []
    for h in acc.history:
        k = (h["map"], h["mode"])
        if h["won"] and k not in got:
            got.add(k)
            order.append(k)
    return order


def test_long_run_reaches_everything():
    """Regression for the old deadlock (strategies with locked upgrades were
    unplayable, so their towers never earned XP and the run stalled), plus the
    owner's warm-up order (2026-10-22): Easy-family medals first, then
    Medium-family, then Hard and its sub-modes as they become likely.
    (A fresh simulated account stops earlier than with the old Hard-first
    order - it waits once nothing left is winnable - but never replays.)"""
    t0 = time.time()
    acc, log = simulate(6000, seed=11, verbose_first=0)
    print("\n".join(l for l in log if l.startswith("==")))
    print(f"(long sim took {time.time() - t0:.1f}s)")
    all_maps = [m for m in MAPS if m not in EXCLUDED_MAPS]
    assert acc.unique_map_wins() >= 0.8 * len(all_maps), acc.unique_map_wins()
    hard = sum(1 for m in all_maps if acc.has_medal(m, "hard"))
    assert hard >= 25, hard
    # nothing confident is left behind: every unearned medal that is open now
    # is below its p threshold for every strategy
    _, _, cands = P.rank_games(acc, P.EXAMPLE_STRATEGIES)
    left = set(acc.remaining_goals())
    feasible = [(c.map, c.mode, c.s.id, round(c.p, 2)) for c in cands
                if c.first and c.ok and (c.map, c.mode) in left]
    assert not feasible, feasible[:10]
    # losses stay rare (reality = the planner's prior in this simulation)
    games = sum(st["wins"] + st["losses"] for st in acc.strategy_stats.values())
    losses = sum(st["losses"] for st in acc.strategy_stats.values())
    assert losses / games < 0.2, (losses, games)
    # the tier order shows: Hard first (the default since the evening of
    # 2026-10-22) - most Hard medals before most Easy-family ones; with the
    # warm-up order it is the other way round
    order = _medal_order(acc)
    idx = {k: i for i, k in enumerate(order)}
    easy = sorted(i for k, i in idx.items() if k[1] in P.EASY_FAMILY)
    medium = sorted(i for k, i in idx.items() if k[1] in P.MEDIUM_FAMILY)
    hard_idx = sorted(i for k, i in idx.items() if k[1] == "hard")
    assert easy and medium and hard_idx
    if P.TIERS is P.TIERS_WARM_UP:
        assert easy[len(easy) // 2] < medium[len(medium) // 2], (easy[len(easy) // 2], medium[len(medium) // 2])
        assert easy[len(easy) // 2] < hard_idx[len(hard_idx) // 2]
    else:
        assert hard_idx[len(hard_idx) // 2] < easy[len(easy) // 2], (hard_idx[len(hard_idx) // 2], easy[len(easy) // 2])


# ------------------------------------------------------------ durations

def _spec(id="s", modes=("easy", "medium", "hard"), rate=0.95, **kw) -> P.StrategySpec:
    return P.StrategySpec(id=id, towers=kw.pop("towers", {"dart": (0, 0, 0)}),
                          modes=frozenset(modes), base_success={m: rate for m in modes}, **kw)


def test_duration_defaults_and_first_visit_scan():
    acc = AccountState()
    s = _spec()
    cfg = P.DEFAULT_CONFIG
    d = P._Durations(acc, cfg)
    easy, _ = d.game_minutes(s, "Logs", "easy")
    hard, _ = d.game_minutes(s, "Logs", "hard")
    assert 7.0 <= easy <= 8.3, easy                   # observed Easy range at 2x speed
    assert 2.0 <= hard / easy <= 2.4, hard / easy     # Hard (3-80) ~2.2x an Easy game
    # a never-played map pays the one-time placement scan, once
    first = P.expected_minutes(acc, s, "Logs", "easy")
    assert abs(first - (easy + cfg.overhead_minutes + cfg.first_visit_minutes)) < 1e-6
    acc.record_result("Logs", "easy", "s", True, minutes=7.5)
    again = P.expected_minutes(acc, s, "Logs", "easy")
    assert again < first - 2.0, (first, again)


def test_duration_learns_from_observed_games():
    acc = AccountState()
    s = _spec()
    d0 = P._Durations(acc, P.DEFAULT_CONFIG)
    easy0 = d0.game_minutes(s, "Town Center", "easy")[0]
    hard0 = d0.game_minutes(s, "Monkey Meadow", "hard")[0]
    # one slow observation moves the estimate, but only part of the way
    acc.record_result("Town Center", "easy", "s", True, minutes=10.0)
    e1 = P._Durations(acc, P.DEFAULT_CONFIG).game_minutes(s, "Town Center", "easy")[0]
    assert easy0 < e1 < 10.0, (easy0, e1)
    # many consistent observations dominate the prior
    for _ in range(12):
        acc.record_result("Town Center", "easy", "s", True, minutes=10.0)
    d = P._Durations(acc, P.DEFAULT_CONFIG)
    e2 = d.game_minutes(s, "Town Center", "easy")[0]
    assert 9.3 < e2 <= 10.0, e2
    # slow Easy games mean the bot runs slow in general: the Hard estimate follows
    hard2 = d.game_minutes(s, "Monkey Meadow", "hard")[0]
    assert hard2 > hard0 * 1.15, (hard0, hard2)
    # an outlier (stuck game) is clipped rather than taken at face value
    acc2 = AccountState()
    acc2.record_result("Logs", "easy", "s", True, minutes=60.0)
    e3 = P._Durations(acc2, P.DEFAULT_CONFIG).game_minutes(s, "Logs", "easy")[0]
    assert e3 < 1.5 * MODES["easy"].minutes, e3
    # observed Hard durations are used for Hard directly
    acc3 = AccountState()
    for _ in range(6):
        acc3.record_result("Logs", "hard", "s", True, minutes=20.0)
    h3 = P._Durations(acc3, P.DEFAULT_CONFIG).game_minutes(s, "Logs", "hard")[0]
    assert 19.0 < h3 <= 20.0, h3


def test_planner_prefers_faster_games():
    """Same medal value, observed slower map -> lower score."""
    acc = AccountState()
    s = _spec(modes=("easy",), rate=0.97)
    # Easy durations seen on both maps while their medal is still open (a won
    # game would earn the medal and take the map/mode out of the plan)
    for m, mins in (("Logs", 7.0), ("Monkey Meadow", 11.0)):
        acc.map_stats[m] = {"wins": 0, "losses": 0, "avg_minutes": {"easy": mins},
                            "minutes_n": {"easy": 4}}
    _, _, cands = P.rank_games(acc, [s], playable_maps=["Logs", "Monkey Meadow"])
    by = {c.map: c for c in cands if c.mode == "easy"}
    assert by["Logs"].minutes < by["Monkey Meadow"].minutes
    assert by["Logs"].score > by["Monkey Meadow"].score


# ------------------------------------------------------ hard focus / safety

def _hard_ready_account() -> AccountState:
    """L30 account with the full upgrade build for the example roster and the
    first 5 Easy medals (intermediate maps open)."""
    acc = AccountState()
    acc.apply_level(30)
    _settle(acc, [])
    for need in P.STRATEGY_NEEDS:
        for path in range(3):
            if need.crosspath[path]:
                acc.unlock_upgrade(need.tower, path, need.crosspath[path])
    for m in ("Monkey Meadow", "Logs", "Tree Stump", "Town Center", "In The Loop"):
        acc.record_result(m, "easy", "primary_moab", True, minutes=7.5)
    return acc


@_hard_first
def test_hard_medals_preferred_when_reliable():
    acc = _hard_ready_account()
    plan = P.next_game(acc)
    assert plan.phase == "H", plan.reasons
    assert plan.mode_key == "hard" and plan.first_time, plan.reason
    assert plan.p_win >= P.DEFAULT_CONFIG.hard_ready_p, plan
    # keeps going for Hard standard medals as long as reliable ones are open
    for _ in range(8):
        plan = P.next_game(acc)
        assert plan.mode_key == "hard", plan.reason
        acc.record_result(plan.map, "hard", plan.strategy_id, True, minutes=17.0)
    # every Hard tier candidate ranks above every Medium/Easy one
    _, _, cands = P.rank_games(acc)
    pos = {id(c): i for i, c in enumerate(cands)}
    hard = [pos[id(c)] for c in cands if c.tier == "H"]
    other = [pos[id(c)] for c in cands if c.tier in ("M", "E")]
    assert hard and other and max(hard) < min(other)


@_hard_first
def test_hard_submode_chain_after_hard():
    """Once Hard is beaten on a map, its sub-modes outrank Medium/Easy."""
    acc = _hard_ready_account()
    beginner = [m for m in MAPS if MAPS[m] == "beginner"]
    for m in beginner:
        acc.record_result(m, "hard", "primary_moab", True, minutes=17.0)
    plan = P.next_game(acc)
    assert plan.phase in ("H", "HS"), plan.reasons
    assert plan.mode_key in P.HARD_FAMILY, plan.reason
    # walk the ABR chain on Monkey Meadow: each step unlocks the next
    for mode in ("abr", "impoppable"):
        acc.record_result("Monkey Meadow", mode, "late_game_chimps", True, minutes=20.0)
    assert acc.mode_unlocked("Monkey Meadow", "chimps")
    _, _, cands = P.rank_games(acc)
    ch = [c for c in cands if c.map == "Monkey Meadow" and c.mode == "chimps"]
    assert ch and max(c.p for c in ch) >= P.DEFAULT_CONFIG.min_p_chimps
    assert all(c.tier == "HS" for c in ch if c.ok)
    pos = {id(c): i for i, c in enumerate(cands)}
    best_ch = min(pos[id(c)] for c in ch if c.ok)
    assert all(pos[id(c)] > best_ch for c in cands if c.tier in ("M", "E"))


def test_hard_losses_stop_hard_attempts():
    """After the roster loses Hard repeatedly, Hard is no longer 'reliable'."""
    acc = _hard_ready_account()
    for s in P.EXAMPLE_STRATEGIES:
        if "hard" in s.modes:
            for m in ("Monkey Meadow", "Logs", "Tree Stump"):
                for _ in range(3):
                    acc.record_result(m, "hard", s.id, False, minutes=10.0)
    plan = P.next_game(acc)
    assert plan.mode_key != "hard" or plan.p_win >= P.DEFAULT_CONFIG.hard_fallback_p, plan
    ok = plan.p_win >= P.p_threshold(plan.mode_key)
    assert ok or (plan.phase == "HF" and plan.p_win >= P.DEFAULT_CONFIG.hard_fallback_p), plan


def _runner_like_roster(acc: AccountState) -> list[P.StrategySpec]:
    """Shaped like runner.planner_specs output for the YAML roster: full
    upgrade requirements, x0.85 when the hero is not owned, untested Hard+
    priors capped at 0.85."""
    def spec(id, towers, base, hero, owned):
        f = 1.0 if owned else 0.85
        b = {m: min(v * f, 0.85) if m not in ("easy", "primary_only", "medium") else v * f
             for m, v in base.items()}
        return P.StrategySpec(id=id, towers=towers, modes=frozenset(b), base_success=b,
                              heroes=(hero,))
    have = acc.unlocked_heroes
    return [
        spec("starter_tack_dart", {"tack": (0, 0, 0), "dart": (0, 0, 0)},
             {"easy": 0.95, "primary_only": 0.85, "medium": 0.7, "hard": 0.35}, "quincy", True),
        spec("primary_core", {"tack": (3, 0, 0), "boomerang": (2, 0, 2), "bomb": (0, 3, 0),
                              "dart": (0, 0, 2)},
             {"easy": 0.98, "primary_only": 0.95, "medium": 0.93, "hard": 0.8, "abr": 0.7},
             "quincy", True),
        spec("primary_glaive_dart", {"boomerang": (3, 0, 2), "dart": (0, 0, 2)},
             {"easy": 0.97, "primary_only": 0.95, "medium": 0.9}, "quincy", True),
        spec("military_heli_sniper", {"heli": (2, 0, 2), "sniper": (2, 2, 0)},
             {"easy": 0.98, "medium": 0.95, "military_only": 0.92, "hard": 0.85, "abr": 0.8,
              "reverse": 0.92}, "striker_jones", "striker_jones" in have),
        spec("hard_ninja_alch_sniper", {"ninja": (4, 0, 4), "alchemist": (4, 2, 0),
                                        "sniper": (4, 2, 0)},
             {"medium": 0.92, "hard": 0.82}, "obyn", "obyn" in have),
    ]


def _warm_up(fn):
    """Run a test with the warm-up tier order (Easy, Medium, then Hard) and
    easier maps first - the order of the morning of 2026-10-22."""
    import functools

    @functools.wraps(fn)
    def run(*a, **kw):
        saved = P.TIERS, P.HARD_MAPS_FIRST
        P.TIERS, P.HARD_MAPS_FIRST = P.TIERS_WARM_UP, False
        try:
            return fn(*a, **kw)
        finally:
            P.TIERS, P.HARD_MAPS_FIRST = saved
    return run


def _fresh_ish_account():
    """Level ~20, mid roster, Easy medals on six beginner maps."""
    acc = AccountState()
    acc.apply_level(20)
    acc.pending_tower_choices.clear()
    acc.unlocked_towers = {"dart", "boomerang", "bomb", "tack", "ice", "glue", "sniper", "sub",
                           "buccaneer", "mortar", "ace", "heli", "alchemist", "druid", "ninja",
                           "wizard"}
    acc.unlocked_upgrades = {"tack": [4, 0, 2], "dart": [0, 0, 4], "sniper": [3, 2, 0],
                             "heli": [1, 0, 1], "boomerang": [2, 0, 2], "glue": [2, 0, 1],
                             "bomb": [0, 1, 1]}
    for m in ["Monkey Meadow", "In The Loop", "Tree Stump", "Town Center", "Logs", "Alpine Run"]:
        acc.record_result(m, "easy", "primary_core", True, minutes=7.5)
    return acc


def test_map_modes_no_build_holds_are_not_trusted():
    """Party Parade Hard: the best researched build rates 1.33 (data/
    model_ceiling.json) - a general build is capped below every threshold
    until it has won there; maps without a ceiling are untouched."""
    acc = _fresh_ish_account()
    s = _spec(modes=("hard",), rate=0.95)
    assert P.prior_win_probability(acc, s, "Party Parade", "hard") <= P.CEILING_P_CAP
    assert P.prior_win_probability(acc, s, "Logs", "hard") > P.CEILING_P_CAP


def test_optimized_builds_set_the_ceiling():
    """Dark Dungeons Primary Only (2026-10-27): the optimizer's best build
    rated 0.68 and solo_bomb, rated without that number, lost at round 25.
    An optimized build's worst_margin now counts as a ceiling; a better
    researched value for the same map is kept."""
    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp())
    (root / "data").mkdir()
    (root / "data" / "model_ceiling.json").write_text(
        '{"ceilings": {"Logs|*": 2.5}}', encoding="utf-8")
    opt = root / "strategies" / "optimized"
    opt.mkdir(parents=True)
    (opt / "darkdungeons_primary_only.yaml").write_text(
        "map: Dark Dungeons\nmodes: [primary_only]\noptimizer: {worst_margin: 0.68}\n", encoding="utf-8")
    (opt / "logs_easy.yaml").write_text(
        "map: Logs\nmodes: [easy]\noptimizer: {worst_margin: 0.9}\n", encoding="utf-8")
    (opt / "broken.yaml").write_text("map: [unclosed\n", encoding="utf-8")
    ceilings = P._load_ceilings(root)
    assert ceilings["Dark Dungeons|primary_only"] == 0.68
    assert ceilings["Logs|easy"] == 2.5          # research beats the optimizer here
    assert "Dark Dungeons|easy" not in ceilings
    saved = P._CEILINGS
    P._CEILINGS = ceilings
    try:
        acc = _fresh_ish_account()
        s = _spec(modes=("primary_only",), rate=0.95)
        assert P.prior_win_probability(acc, s, "Dark Dungeons", "primary_only") <= P.CEILING_P_CAP
    finally:
        P._CEILINGS = saved


def test_losses_on_a_map_mode_count_against_every_general_build():
    """Last Resort Hard: lost by one general build, the next starts lower;
    a build made for that map keeps its own record."""
    acc = _fresh_ish_account()
    general = _spec(id="g2", modes=("hard",), rate=0.9)
    before = P.prior_win_probability(acc, general, "Ravine", "hard")
    acc.record_result("Ravine", "hard", "g1", False, round_reached=27)
    after = P.prior_win_probability(acc, general, "Ravine", "hard")
    assert abs(after - before * P.MAP_LOSS_FACTOR) < 1e-6, (before, after)
    own = _spec(id="ravine_hard", modes=("hard",), rate=0.9, maps=["Ravine"])
    acc2 = _fresh_ish_account()
    p0 = P.prior_win_probability(acc2, own, "Ravine", "hard")
    acc2.record_result("Ravine", "hard", "g1", False, round_reached=27)
    assert P.prior_win_probability(acc2, own, "Ravine", "hard") == p0


def test_hard_first_by_default():
    """The owner's order (evening of 2026-10-22): Hard medals before the
    Easy and Medium families."""
    acc = _fresh_ish_account()
    plan = P.next_game(acc, _runner_like_roster(acc))
    assert plan.mode_key in P.HARD_FAMILY, (plan.reason, plan.reasons)
    _, _, cands = P.rank_games(acc, _runner_like_roster(acc))
    tiers = [c.tier for c in cands]
    assert tiers == sorted(tiers, key=P.TIERS.index), "tiers out of order"


@_warm_up
def test_fresh_ish_account_warms_up():
    """With the warm-up order the remaining Easy-family medals come first,
    easier maps first."""
    acc = _fresh_ish_account()
    plan = P.next_game(acc, _runner_like_roster(acc))
    assert plan.mode_key in P.EASY_FAMILY, (plan.reason, plan.reasons)
    assert plan.phase == "E", plan.reasons
    _, _, cands = P.rank_games(acc, _runner_like_roster(acc))
    tiers = [c.tier for c in cands]
    assert tiers == sorted(tiers, key=P.TIERS.index), "tiers out of order"


def test_confident_games_first_within_a_tier():
    """A bonus (achievement, Monkey Money) must not put a shaky game ahead of
    a near-certain one in the same tier."""
    acc = _hard_ready_account()
    _, _, cands = P.rank_games(acc)
    for tier in set(c.tier for c in cands):
        ps = [c.p >= P.CONFIDENT_P for c in cands if c.tier == tier]
        assert ps == sorted(ps, reverse=True), (tier, ps)


@_hard_first
def test_learned_tracks_first():
    """data/maps/<slug>.npz marks a learned track: no scan time, and Hard
    medals there go first even though unseen maps carry a unique-win bonus."""
    acc = _hard_ready_account()
    with tempfile.TemporaryDirectory() as d:
        for m in ("Cubism", "Hedge"):
            Path(d, P.map_slug(m) + ".npz").write_bytes(b"")
        cfg = P.PlannerConfig(maps_dir=d, use_game_geometry=False)
        assert P.expected_minutes(acc, P.EXAMPLE_STRATEGIES[2], "Cubism", "hard", cfg) < \
            P.expected_minutes(acc, P.EXAMPLE_STRATEGIES[2], "Carved", "hard", cfg) - 2.0
        _, _, cands = P.rank_games(acc, config=cfg)
        top = cands[0]
        assert top.tier == "H" and top.learned, (top.map, top.notes)
        played = {"Monkey Meadow", "Logs", "Tree Stump", "Town Center", "In The Loop"}
        assert top.map in played | {"Cubism", "Hedge"}, top.map


def test_weak_roster_falls_back_to_easy_with_reason():
    """Nothing Hard >= 0.7: Easy/Medium medals as XP/unlock games, logged."""
    acc = AccountState()
    phase, reasons, cands = P.rank_games(acc)
    assert phase in ("M", "E"), (phase, reasons)
    assert cands[0].mode not in P.HARD_FAMILY
    assert any("no Hard-family medal clears its bar" in r or "no strategy" in r for r in reasons), reasons


def test_never_prefers_low_p():
    acc = AccountState()
    weak = _spec("weak", modes=("easy", "medium", "hard"), rate=0.5)
    good = _spec("good", modes=("easy",), rate=0.95)
    plan = P.next_game(acc, [weak, good])
    assert plan.strategy_id == "good" and plan.p_win >= P.DEFAULT_CONFIG.min_p_new, plan
    _, _, cands = P.rank_games(acc, [weak, good])
    for c in cands:  # only games that clear a bar are offered at all
        assert c.ok == (c.p >= P.p_threshold(c.mode))
        assert c.ok or (c.tier in ("HF", "B") and c.p >= P.DEFAULT_CONFIG.hard_fallback_p)
    assert not any(c.s.id == "weak" for c in cands)
    # nothing confident at all: nothing is played (no "safest loss")
    phase, reasons, cands = P.rank_games(acc, [weak])
    assert not cands and phase == "NONE" and reasons[0].startswith(P.NOTHING_LEFT), reasons
    assert P.next_game(acc, [weak]) is None


def test_missing_upgrades_degrade_instead_of_block():
    acc = AccountState()
    acc.unlocked_towers |= {"boomerang"}
    s = next(x for x in P.EXAMPLE_STRATEGIES if x.id == "dart_boomer")
    assert P._strategy_available(s, acc)[0]
    assert P.build_fraction(s, acc) == 0.0
    easy0 = P.prior_win_probability(acc, s, "Logs", "easy")
    hard0 = P.prior_win_probability(acc, s, "Logs", "hard")
    for path, tier in ((0, 3), (2, 2)):
        acc.unlock_upgrade("boomerang", path, tier)
    acc.unlock_upgrade("dart", 2, 2)
    assert P.build_fraction(s, acc) == 1.0
    easy1 = P.prior_win_probability(acc, s, "Logs", "easy")
    hard1 = P.prior_win_probability(acc, s, "Logs", "hard")
    assert easy0 < easy1 and hard0 < hard1
    assert hard0 / hard1 < easy0 / easy1  # Hard punishes a missing build harder


def test_map_difficulty_matters_less_in_easy():
    s = next(x for x in P.EXAMPLE_STRATEGIES if x.id == "primary_moab")
    easy = P._prior(s, "#Ouch", "expert", "easy") / P._prior(s, "Logs", "beginner", "easy")
    hard = P._prior(s, "#Ouch", "expert", "hard") / P._prior(s, "Logs", "beginner", "hard")
    assert hard < easy < 1.0


# ------------------------------------------------------------ achievements

def _ach(name, desc, kind="game_win_constraint", mode=None, map=None, passive=True,
         category="single_player", strategy=None, difficulty=None):
    return {"name": name, "description": desc, "category": category, "kind": kind,
            "mode": mode, "map": map, "difficulty": difficulty, "passive": passive,
            "strategy": strategy, "bot_feasible": "easy"}


ACH_CATALOG = [
    _ach("Impoppable", "Pop 100,000,000 Bloons", kind="cumulative"),
    _ach("Grasshopper", "Win on 9 different Beginner maps", kind="progression"),
    _ach("War Monkeys", "Win 10 games using only Military monkeys", mode="military_only"),
    _ach("First Monkeys First", "Win 10 games using only Primary monkeys", mode="primary_only"),
    _ach("Abracadabmonkey", "Win 10 games using only Magic monkeys", mode="magic_only",
         strategy="ach_abracadabmonkey"),
    _ach("Bloons Master", "Beat 1 map in CHIMPS mode", mode="chimps", difficulty="impoppable",
         strategy="ach_bloons_master"),
    _ach("Role Reverser", "Win a game in Reverse mode", mode="reverse",
         strategy="ach_role_reverser"),
    _ach("Living on the Edge", "Win any non-CHIMPS game with only 1 life remaining",
         map="Resort", passive=False, strategy="ach_living_on_the_edge"),
    _ach("Boss Slayer", "Defeat a boss", kind="other", category="excluded"),
    _ach("Co-op Champ", "Win a co-op game", kind="other", category="excluded", mode="reverse"),
]


def test_achievement_state_fuzzy_match():
    state = {"cards": {
        ".ruPPABLe": {"desc": "Pop 100,000,000 Bloons", "status": "progress", "progress": 0},
        "Grashopper": {"desc": "Win on9differentBeginnermaps", "status": "progress", "progress": 77},
        "War Monkeys": {"desc": "Win 10 games using only Military monkeys", "status": "collect"},
        "Flrst Monkeys First": {"desc": "x", "status": "progress", "progress": 60},
        "Totally Unrelated": {"desc": "Something else entirely", "status": "complete"},
    }}
    m = P.match_achievement_state(ACH_CATALOG, state)
    assert m["Impoppable"]["status"] == "progress"
    assert m["Grasshopper"]["progress"] == 77
    assert m["War Monkeys"]["status"] == "collect"
    assert m["First Monkeys First"]["progress"] == 60
    assert len(m) == 4, m


def test_wanted_achievements():
    acc = AccountState()
    state = {"cards": {"War Monkeys": {"status": "collect"},
                       "Role Reverser": {"status": "complete"},
                       "First Monkeys First": {"status": "progress", "progress": 60}}}
    goals = {g.name: g for g in P.wanted_achievements(acc, state, ACH_CATALOG)}
    assert "War Monkeys" not in goals and "Role Reverser" not in goals  # done
    assert "Boss Slayer" not in goals and "Co-op Champ" not in goals    # excluded
    assert goals["First Monkeys First"].modes == ("primary_only",)
    assert goals["First Monkeys First"].wins_needed == 10
    assert goals["Bloons Master"].wins_needed == 1 and goals["Bloons Master"].plannable
    assert goals["Living on the Edge"].modes == () and goals["Living on the Edge"].map == "Resort"
    assert P.wanted_achievements(acc, state, None) == []
    # a CHIMPS medal on the account means 'Bloons Master' is done even if the scan lags
    acc.medals["Logs"] = {"chimps": True}
    assert "Bloons Master" not in {g.name for g in P.wanted_achievements(acc, state, ACH_CATALOG)}
    # the real catalog (read only): excluded categories are never wanted
    real = Path(__file__).resolve().parent.parent / "data" / "achievements.json"
    if real.exists():
        import json
        cat = json.loads(real.read_text(encoding="utf-8"))
        names = {g.name for g in P.wanted_achievements(AccountState(), None, cat)}
        excluded = {e["name"] for e in cat if e["category"] != "single_player"}
        assert names and not names & excluded


def test_achievement_bonus_only_on_new_medals():
    """'Abracadabmonkey' (10 Magic Only wins) adds value to a first-time Magic
    Only medal, but never brings back a Magic Only replay."""
    acc = _hard_ready_account()
    for m in ("Monkey Meadow", "Logs"):
        acc.record_result(m, "hard", "magic_core", True, minutes=17.0)
    acc.record_result("Monkey Meadow", "magic_only", "magic_core", True, minutes=17.0)
    ach = (ACH_CATALOG, {"cards": {}})

    def magic(cands, m):
        return [c for c in cands if c.map == m and c.mode == "magic_only"]

    _, reasons, cands = P.rank_games(acc, achievements=ach)
    assert not magic(cands, "Monkey Meadow")       # beaten: never a candidate
    new = magic(cands, "Logs")
    assert new and all("Abracadabmonkey" in c.achievements and c.ach > 0 for c in new)
    assert all(c.tier == "HS" and c.ok for c in new), [(c.tier, c.p) for c in new]
    assert any("achievements:" in r for r in reasons), reasons
    # once complete, the bonus is gone
    done = (ACH_CATALOG, {"cards": {"Abracadabmonkey": {"status": "complete"}}})
    _, _, after = P.rank_games(acc, achievements=done)
    assert not any(c.ach for c in magic(after, "Logs"))


def _reverser(**kw) -> P.StrategySpec:
    d = {"id": "ach_role_reverser", "achievement": "Role Reverser", "map": "Logs",
         "modes": ["reverse"], "towers": {"dart": [0, 0, 0]},
         "base_success": {"reverse": 0.95}}
    d.update(kw)
    return P.StrategySpec.from_any(d)


def test_achievement_strategy_gating():
    acc = AccountState()
    acc.record_result("Logs", "medium", "x", True, minutes=11.0)  # opens Reverse on Logs
    ach = (ACH_CATALOG, {"cards": {}})
    roster = [_spec("plain", modes=("easy",), rate=0.95)]

    def ach_cands(spec, a=ach):
        _, _, cands = P.rank_games(acc, roster + [spec], achievements=a)
        return [c for c in cands if c.s.id == spec.id]

    ready = ach_cands(_reverser(bot_ready=True))
    assert ready and all(c.map == "Logs" and c.mode == "reverse" for c in ready)
    assert all("Role Reverser" in c.achievements and c.ok and c.tier == "M" for c in ready)
    assert not ach_cands(_reverser())                     # readiness unknown
    assert not ach_cands(_reverser(bot_ready=False))      # not ready
    assert not ach_cands(_reverser(bot_ready=True),       # already complete
                         (ACH_CATALOG, {"cards": {"Role Reverser": {"status": "complete"}}}))
    assert not ach_cands(_reverser(bot_ready=True), (None, None))  # no catalog: never
    # never below the win threshold (losses are unacceptable)
    assert not ach_cands(_reverser(bot_ready=True, base_success={"reverse": 0.5}))
    # excluded achievements are never planned, even when marked ready
    assert not ach_cands(_reverser(bot_ready=True, achievement="Co-op Champ"))
    assert not ach_cands(_reverser(bot_ready=True, achievement="Boss Slayer"))
    # an achievement plan that arrives without its tag is never a normal strategy
    assert not ach_cands(_reverser(bot_ready=True, achievement=None))


@_hard_first
def test_achievements_keep_hard_first():
    """With every achievement wanted, a reliable Hard medal still goes first."""
    acc = _hard_ready_account()
    plan = P.next_game(acc, achievements=(ACH_CATALOG, {"cards": {}}))
    assert plan.phase == "H" and plan.mode_key == "hard", plan.reason


# ------------------------------------------------------------ objective

def test_black_border_value_rewards_finishing_maps():
    acc = AccountState()
    cfg = P.DEFAULT_CONFIG
    assert len(P.BB_MODES) == 14
    vals = []
    for k, mode in enumerate(P.BB_MODES[:-1]):
        vals.append(P.black_border_value(acc, "Logs", mode))
        acc.medals.setdefault("Logs", {})[mode] = True
    assert all(b > a for a, b in zip(vals, vals[1:])), vals  # convex: later medals worth more
    last = P.black_border_value(acc, "Logs", "chimps")
    assert last > vals[-1] + cfg.chimps_medal_value * 0.99   # CHIMPS is the prize
    total = sum(vals) + last - cfg.chimps_medal_value
    assert abs(total - cfg.w_bb) < 1.0                       # all 14 medals = one black border
    assert P.black_border_value(acc, "Logs", "easy") == 0.0  # already earned


def test_within_tier_prefers_completing_a_map():
    """Same medal (Magic Only), same strategy, same p/time: the map closer to a
    black border scores higher."""
    acc = _hard_ready_account()
    for mode in ("hard", "primary_only", "deflation", "medium", "military_only",
                 "apopalypse", "reverse", "abr"):
        acc.record_result("Monkey Meadow", mode, "x", True, minutes=MODES[mode].minutes)
    acc.record_result("Logs", "hard", "x", True, minutes=MODES["hard"].minutes)
    _, _, cands = P.rank_games(acc, achievements=(None, None))
    by = {c.map: c for c in cands if c.mode == "magic_only" and c.s.id == "magic_core"}
    mm, logs = by["Monkey Meadow"], by["Logs"]
    assert abs(mm.p - logs.p) < 1e-9 and mm.tier == logs.tier == "HS"
    assert mm.per_hour > logs.per_hour, (mm.notes, logs.notes)


def test_objective_is_points_per_hour():
    acc = _hard_ready_account()
    cfg = P.DEFAULT_CONFIG
    _, _, cands = P.rank_games(acc, achievements=(None, None))
    c = next(c for c in cands if c.first and c.mode == "hard" and c.map == "Logs")
    mm = P.estimate_mm(acc, "Logs", "hard")[0]
    xp_w = cfg.w_xp * (1 + cfg.hard_build_xp_weight * c.build + cfg.paragon_xp_weight * c.paragon)
    v_win = (c.xp_win * xp_w + cfg.w_mm * mm
             + P.black_border_value(acc, "Logs", "hard") + cfg.unlock_value * 2 + c.ach)
    v_loss = c.value_fail - cfg.loss_penalty
    t = c.p * c.minutes + (1 - c.p) * c.fail_minutes
    expect = 60 * (c.p * v_win + (1 - c.p) * v_loss) / t * (1 + cfg.explore_bonus / math.sqrt(c.n + 1))
    assert abs(c.per_hour - expect) / expect < 1e-6, (c.per_hour, expect)
    assert abs(c.per_hour - 60 * c.score) < 1e-6


def test_mm_estimates_and_observed_override():
    acc = AccountState()
    first, is_first, src = P.estimate_mm(acc, "Logs", "hard")
    assert (first, is_first, src) == (200, True, "estimate")
    assert P.estimate_mm(acc, "Dark Castle", "chimps")[0] == 300 * 4    # expert x4
    acc.medals["Logs"] = {"hard": True}
    replay = P.estimate_mm(acc, "Logs", "hard")[0]
    assert replay == first * P.MM_REPEAT_FRAC                          # replays pay much less
    acc.map_stats["Logs"] = {"observed_rewards": {"hard": {"repeat": 55}}}
    assert P.estimate_mm(acc, "Logs", "hard") == (55.0, False, "observed")


def test_xp_favours_expert_and_long_modes():
    assert abs(P.game_xp("hard", "expert") / P.game_xp("hard", "beginner") - 1.3) < 1e-9
    assert P.game_xp("chimps", "beginner") > 1.8 * P.game_xp("hard", "beginner")
    # when equally winnable, a new Impoppable medal beats a new Hard medal on
    # XP per hour (Impoppable opened on Logs, Hard still open on Tree Stump)
    acc = _hard_ready_account()
    for mode in ("hard", "abr"):
        acc.record_result("Logs", mode, "late_game_chimps", True, minutes=MODES[mode].minutes)
    _, _, cands = P.rank_games(acc, achievements=(None, None))
    imp = next(c for c in cands if (c.map, c.mode, c.s.id) == ("Logs", "impoppable", "late_game_chimps"))
    hard = next(c for c in cands if (c.map, c.mode, c.s.id) == ("Tree Stump", "hard", "late_game_chimps"))
    assert imp.xp_win / imp.minutes > hard.xp_win / hard.minutes


# ------------------------------------------------------- never replay

def test_replays_never_chosen():
    """The owner's rule: a beaten map/mode is never a candidate, in any tier
    or fallback - not for XP, MM, nor an achievement it would advance."""
    acc = _hard_ready_account()
    acc.record_result("Monkey Meadow", "hard", "magic_core", True, minutes=17.0)
    acc.record_result("Monkey Meadow", "magic_only", "magic_core", True, minutes=17.0)
    ach = (ACH_CATALOG, {"cards": {}})   # every achievement wanted (rewards replays most)
    _, _, cands = P.rank_games(acc, achievements=ach)
    assert cands and all(c.first for c in cands)
    assert not [(c.map, c.mode) for c in cands if acc.has_medal(c.map, c.mode)]
    # play it forward: every single plan is a medal the account does not have
    for _ in range(40):
        plan = P.next_game(acc, achievements=ach)
        if plan is None:
            break
        assert plan.first_time and not acc.has_medal(plan.map, plan.mode_key), plan.reason
        acc.record_result(plan.map, plan.mode_key, plan.strategy_id, True,
                          minutes=MODES[plan.mode_key].minutes)


class _Records(logging.Handler):
    """Collects log messages (to check the reason the planner logs)."""

    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_none_when_nothing_left():
    """No winnable first-time medal: next_game is None (the runner idles) and
    logs NOTHING_LEFT - both when every open medal is beaten and when the rest
    is below its win-chance bar."""
    rec = _Records()
    P.log.addHandler(rec)
    level = P.log.level
    P.log.setLevel(logging.INFO)   # the reason is logged at INFO
    try:
        # 1) only beginner maps open (the game's category bars say so), all beaten
        acc = AccountState()
        acc.category_progress = {"intermediate": [0, 5], "advanced": [0, 12], "expert": [0, 20]}
        for m in MAPS:
            if MAPS[m] == "beginner":
                acc.medals[m] = {mode: True for mode in MODES}
        phase, reasons, cands = P.rank_games(acc)
        assert not cands and phase == "NONE" and reasons == [P.NOTHING_LEFT], reasons
        assert P.next_game(acc) is None
        assert rec.lines[-1] == P.NOTHING_LEFT, rec.lines
        # 2) medals open, but none winnable yet: the closest one is named
        acc = AccountState()
        weak = _spec("weak", modes=("easy", "medium", "hard"), rate=0.6)
        assert P.next_game(acc, [weak]) is None
        assert rec.lines[-1].startswith(P.NOTHING_LEFT) and "closest:" in rec.lines[-1], rec.lines
    finally:
        P.log.removeHandler(rec)
        P.log.setLevel(level)


# ------------------------------------------------------- paragon focus

def _paragon_account() -> tuple[AccountState, dict]:
    """Ninja 100k XP short of its paragon, Tack 400k short, Sniper's paragon
    read as unlocked, Ice never read, Bomb with enough XP banked."""
    prices = P.load_tower_xp_prices(PARAGON_CFG.tower_xp_path)
    acc = AccountState()
    acc.unlocked_towers |= {"ninja", "tack", "sniper", "ice", "bomb", "alchemist"}
    full = [5, 5, 5]
    acc.unlocked_upgrades = {"dart": full, "ninja": full, "tack": full, "sniper": full,
                             "ice": full, "bomb": [5, 4, 5]}
    acc.paragons = {"dart": True, "ninja": False, "tack": False, "sniper": True}
    acc.tower_xp = {"ninja": prices["ninja"].paragon_xp - 100_000,
                    "tack": prices["tack"].paragon_xp - 400_000,
                    "bomb": prices["bomb"].paragon_xp + 1_000_000}
    return acc, prices


def test_paragon_status_from_account_data():
    acc, prices = _paragon_account()
    # which towers have a paragon comes from the data file, not a list in code
    assert prices["ninja"].paragon and prices["alchemist"].paragon is None
    st = P.paragon_status(acc, PARAGON_CFG)
    assert [g.tower for g in st.focus] == ["ninja", "tack"], st.focus   # closest first
    ninja, tack = st.focus
    assert abs(ninja.remaining_xp - 100_000) < 1 and abs(tack.remaining_xp - 400_000) < 1
    assert ninja.closeness == 1.0                     # within one Hard game's XP
    assert abs(tack.closeness - PARAGON_CFG.paragon_reach_xp / 400_000) < 1e-9
    assert ninja.label == "ninja (needs 100k XP)"
    assert sorted(st.done) == ["dart", "sniper"]
    assert st.banked == ["bomb"]      # its missing tier 5 + paragon are paid for already
    assert st.unknown == ["ice"]      # all upgrades, XP short, paragon never read
    assert "alchemist" not in st.focus + st.banked + st.unknown + st.done
    # missing upgrades count too: a tower without its tier 5s cannot have a paragon
    acc.unlocked_upgrades["ice"] = [5, 5, 4]
    ice = next(g for g in P.paragon_status(acc, PARAGON_CFG).focus if g.tower == "ice")
    assert abs(ice.remaining_xp - (prices["ice"].upgrade_xp[2][4] + prices["ice"].paragon_xp)) < 1


def test_paragon_focus_prefers_closest_tower():
    """Same medal, same p and time: the strategy that feeds the tower closest
    to its paragon wins, and the plan's reason line says so. Finishing one
    paragon beats spreading the same XP. Only in games the planner is sure of."""
    acc, _ = _paragon_account()

    def spec(id, share, rate=0.97):
        return _spec(id, modes=("easy",), rate=rate, towers={t: (0, 0, 0) for t in share},
                     cost_share=share)

    roster = [spec("tack_only", {"tack": 1.0}), spec("ninja_only", {"ninja": 1.0}),
              spec("ninja_tack", {"ninja": 0.5, "tack": 0.5})]
    plan = P.next_game(acc, roster, config=PARAGON_CFG, playable_maps=["Logs"])
    assert plan.strategy_id == "ninja_only", plan.reason
    assert "paragon focus: ninja (needs 100k XP)" in plan.reason, plan.reason
    _, reasons, cands = P.rank_games(acc, roster, config=PARAGON_CFG, playable_maps=["Logs"])
    by = {c.s.id: c for c in cands}
    assert by["ninja_only"].score > by["ninja_tack"].score > by["tack_only"].score
    assert len({round(c.p, 9) for c in cands}) == 1          # the focus never changes p
    assert any(r.startswith("paragon focus (closest first): ninja") for r in reasons), reasons
    # without the price table there is no focus, and the choice is a tie on XP
    _, _, plain = P.rank_games(acc, roster, playable_maps=["Logs"])
    assert all(c.paragon == 0.0 for c in plain)
    # a game below its p bar gets no paragon bonus and is never offered
    risky = spec("ninja_risky", {"ninja": 1.0}, rate=0.6)
    _, _, cands = P.rank_games(acc, [risky], config=PARAGON_CFG, playable_maps=["Logs"])
    assert not cands
    # a playable but not very sure game (threshold <= p < paragon_min_p): no bonus
    shaky = spec("ninja_shaky", {"ninja": 1.0}, rate=0.78)
    _, _, cands = P.rank_games(acc, [shaky], config=PARAGON_CFG, playable_maps=["Logs"])
    assert cands and all(c.ok and c.p < PARAGON_CFG.paragon_min_p and c.paragon == 0.0
                         for c in cands), [(c.p, c.paragon) for c in cands]
    # once the sync reads ninja's paragon as unlocked, the focus moves to tack
    acc.paragons["ninja"] = True
    plan = P.next_game(acc, roster, config=PARAGON_CFG, playable_maps=["Logs"])
    assert plan.strategy_id == "tack_only" and "paragon focus: tack" in plan.reason, plan.reason


def test_invested_cash_follows_the_plan():
    """Tower XP is split by invested cash: the runner gives the planner each
    YAML plan's cash per tower type (heroes excluded)."""
    from btd6bot import strategy as S
    from btd6bot import towers as T
    strat = {"plan": [
        {"do": "place", "id": "hero", "kind": "hero"},
        {"do": "place", "id": "t1", "kind": "tack"},
        {"do": "upgrade", "id": "t1", "to": "2-0-1"},
        {"do": "place", "id": "d1", "kind": "dart"},
        {"do": "place", "kind": "dart"},
        {"do": "upgrade", "kind": "dart", "to": "0-0-2"},   # every placed dart
        {"do": "upgrade", "id": "t1", "to": "2-0-2"},
    ]}
    cash = {"tack": T.total_cost("tack", (2, 0, 2)), "dart": 2 * T.total_cost("dart", (0, 0, 2))}
    assert S.invested_cash(strat) == cash
    assert S.invested_cash({"plan": [{"do": "place", "id": "hero", "kind": "hero"}]}) is None
    # the planner's XP split is the cash split
    spec = P.StrategySpec.from_any({"id": "x", "towers": {"tack": [2, 0, 2]}, "cost_share": cash})
    assert abs(spec.share()["tack"] - cash["tack"] / sum(cash.values())) < 1e-9


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    order = ["test_xp_tables", "test_mode_unlocks_and_categories", "test_apply_level_rewards",
             "test_tower_unlock_order", "test_upgrade_unlocks_sequential", "test_mk",
             "test_learning_avoids_failing_strategy", "test_save_load_roundtrip",
             "test_fresh_account_first_40", "test_duration_defaults_and_first_visit_scan",
             "test_duration_learns_from_observed_games", "test_planner_prefers_faster_games",
             "test_hard_medals_preferred_when_reliable", "test_hard_submode_chain_after_hard",
             "test_hard_losses_stop_hard_attempts", "test_map_modes_no_build_holds_are_not_trusted", "test_optimized_builds_set_the_ceiling", "test_losses_on_a_map_mode_count_against_every_general_build", "test_hard_first_by_default", "test_fresh_ish_account_warms_up", "test_confident_games_first_within_a_tier",
             "test_learned_tracks_first", "test_weak_roster_falls_back_to_easy_with_reason",
             "test_never_prefers_low_p", "test_missing_upgrades_degrade_instead_of_block",
             "test_map_difficulty_matters_less_in_easy", "test_achievement_state_fuzzy_match",
             "test_wanted_achievements", "test_achievement_bonus_only_on_new_medals",
             "test_achievement_strategy_gating", "test_achievements_keep_hard_first",
             "test_black_border_value_rewards_finishing_maps",
             "test_within_tier_prefers_completing_a_map", "test_objective_is_points_per_hour",
             "test_mm_estimates_and_observed_override", "test_xp_favours_expert_and_long_modes",
             "test_replays_never_chosen", "test_none_when_nothing_left",
             "test_paragon_status_from_account_data", "test_paragon_focus_prefers_closest_tower",
             "test_invested_cash_follows_the_plan", "test_long_run_reaches_everything"]
    missing = {t.__name__ for t in tests} - set(order)   # a new test must not be skipped
    assert not missing, f"add these to the order list: {sorted(missing)}"
    for name in order:
        res = globals()[name]()
        if name == "test_tower_unlock_order":
            print("tower unlock picks:", res)
        print(f"PASS {name}")
    print("all tests passed")
