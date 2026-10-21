"""Planner simulation + invariants. Run: python tests/test_planner.py
(also collectable by pytest). Does not touch the game."""

from __future__ import annotations

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


def simulate(n_games: int, seed: int = 1, verbose_first: int = 40,
             idle_stop: int = 150) -> tuple[AccountState, list[str]]:
    rng = random.Random(seed)
    acc = AccountState()
    acc.HISTORY_LIMIT = 10 ** 6  # keep the whole run for the order checks
    strategies = {s.id: s for s in P.EXAMPLE_STRATEGIES}
    log: list[str] = []
    phase = None
    minutes_total = 0.0
    idle = 0  # consecutive games without a new medal while nothing is left to try
    for g in range(n_games):
        _settle(acc, log)
        plan = P.next_game(acc, strategies.values())
        assert plan is not None, "no plan for account"
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
        idle = idle + 1 if plan.phase in ("FARM", "LAST", "DONE") and not (won and plan.first_time) else 0
        if idle >= idle_stop:
            log.append(f"== nothing feasible left for {idle} games: stopping after {g + 1} games")
            break
    games = sum(st["wins"] + st["losses"] for st in acc.strategy_stats.values())
    losses = sum(st["losses"] for st in acc.strategy_stats.values())
    hard = sum(1 for d in acc.medals.values() if d.get("hard"))
    log.append(f"== end: games={acc.games_played} L{acc.player_level} MM={acc.monkey_money} "
               f"medals={acc.medal_count()}/{len(acc.all_goals())} uniq={acc.unique_map_wins()} "
               f"hard={hard} losses={losses}/{games} ~{minutes_total / 60:.0f} h")
    return acc, log


# -------------------------------------------------------------------- tests

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
    for _ in range(6):
        acc.record_result("Monkey Meadow", "easy", "dart_quincy", False)
    plan = P.next_game(acc)
    assert not (plan.map == "Monkey Meadow" and plan.mode_key == "easy"), plan.reasons


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
    owner's order: Hard first, Hard sub-modes up to CHIMPS, Medium/Easy last."""
    t0 = time.time()
    acc, log = simulate(6000, seed=11, verbose_first=0)
    print("\n".join(l for l in log if l.startswith("==")))
    print(f"(long sim took {time.time() - t0:.1f}s)")
    all_maps = [m for m in MAPS if m not in EXCLUDED_MAPS]
    # the whole roster's upgrade build got unlocked (no tower-XP deadlock)
    for s in P.EXAMPLE_STRATEGIES:
        assert P.build_fraction(s, acc) == 1.0, s.id
    assert acc.unique_map_wins() >= 0.85 * len(all_maps), acc.unique_map_wins()
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
    # progression order: CHIMPS is beaten before most Easy-family medals, and
    # Hard sub-mode medals come before most Medium-family medals
    order = _medal_order(acc)
    idx = {k: i for i, k in enumerate(order)}
    chimps = [i for k, i in idx.items() if k[1] == "chimps"]
    assert chimps, "no CHIMPS medal reached"
    easy = sorted(i for k, i in idx.items() if k[1] in P.EASY_FAMILY)
    medium = sorted(i for k, i in idx.items() if k[1] in P.MEDIUM_FAMILY)
    sub = sorted(i for k, i in idx.items() if k[1] in P.HARD_FAMILY and k[1] != "hard")
    easy_before = sum(1 for i in easy if i < min(chimps))
    assert easy_before < 0.5 * len(easy), (easy_before, len(easy))
    assert sub and medium and sorted(sub)[len(sub) // 2] < sorted(medium)[len(medium) // 2]
    hard_idx = sorted(i for k, i in idx.items() if k[1] == "hard")
    assert hard_idx[len(hard_idx) // 2] < easy[len(easy) // 2]


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
    for m, mins in (("Logs", 7.0), ("Monkey Meadow", 11.0)):
        for _ in range(4):
            acc.record_result(m, "easy", "s", True, minutes=mins)
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
    other = [pos[id(c)] for c in cands if c.tier in ("M", "E", "FARM")]
    assert hard and other and max(hard) < min(other)


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
    ok = plan.p_win >= P.p_threshold(plan.mode_key, plan.first_time)
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


def test_fresh_ish_account_plans_hard():
    """Level ~20, mid roster, Easy medals on six beginner maps: play Hard next
    (on a map whose track is already learned), not more Easy."""
    acc = AccountState()
    acc.apply_level(20)
    acc.pending_tower_choices.clear()
    acc.unlocked_towers = {"dart", "boomerang", "bomb", "tack", "ice", "glue", "sniper", "sub",
                           "buccaneer", "mortar", "ace", "heli", "alchemist", "druid", "ninja",
                           "wizard"}
    acc.unlocked_upgrades = {"tack": [4, 0, 2], "dart": [0, 0, 4], "sniper": [3, 2, 0],
                             "heli": [1, 0, 1], "boomerang": [2, 0, 2], "glue": [2, 0, 1],
                             "bomb": [0, 1, 1]}
    learned = ["Monkey Meadow", "In The Loop", "Tree Stump", "Town Center", "Logs", "Alpine Run"]
    for m in learned:
        acc.record_result(m, "easy", "primary_core", True, minutes=7.5)
    plan = P.next_game(acc, _runner_like_roster(acc))
    assert plan.mode_key in P.HARD_FAMILY, (plan.reason, plan.reasons)
    assert plan.phase in ("H", "HS", "HF"), plan.reasons
    assert plan.map in learned, plan.reason
    assert plan.p_win >= P.DEFAULT_CONFIG.hard_fallback_p, plan


def test_learned_tracks_first():
    """data/maps/<slug>.npz marks a learned track: no scan time, and Hard
    medals there go first even though unseen maps carry a unique-win bonus."""
    acc = _hard_ready_account()
    with tempfile.TemporaryDirectory() as d:
        for m in ("Cubism", "Hedge"):
            Path(d, P.map_slug(m) + ".npz").write_bytes(b"")
        cfg = P.PlannerConfig(maps_dir=d)
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
    assert any("no Hard-family medal reaches" in r or "no strategy" in r for r in reasons), reasons


def test_never_prefers_low_p():
    acc = AccountState()
    weak = _spec("weak", modes=("easy", "medium", "hard"), rate=0.5)
    good = _spec("good", modes=("easy",), rate=0.95)
    plan = P.next_game(acc, [weak, good])
    assert plan.strategy_id == "good" and plan.p_win >= P.DEFAULT_CONFIG.min_p_new, plan
    _, _, cands = P.rank_games(acc, [weak, good])
    seen_bad = False
    for c in cands:  # every allowed candidate ranks above every last-resort one
        if c.tier == "LAST":
            seen_bad = True
        assert not (seen_bad and c.tier != "LAST")
        assert c.ok == (c.p >= P.p_threshold(c.mode, c.first))
        assert c.ok or c.tier in ("HF", "LAST")
    # nothing confident at all: the safest game goes first
    plan = P.next_game(acc, [weak])
    _, _, cands = P.rank_games(acc, [weak])
    assert not any(c.ok for c in cands)
    assert plan.p_win == round(max(c.p for c in cands), 3)


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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    order = ["test_xp_tables", "test_mode_unlocks_and_categories", "test_apply_level_rewards",
             "test_tower_unlock_order", "test_upgrade_unlocks_sequential", "test_mk",
             "test_learning_avoids_failing_strategy", "test_save_load_roundtrip",
             "test_fresh_account_first_40", "test_duration_defaults_and_first_visit_scan",
             "test_duration_learns_from_observed_games", "test_planner_prefers_faster_games",
             "test_hard_medals_preferred_when_reliable", "test_hard_submode_chain_after_hard",
             "test_hard_losses_stop_hard_attempts", "test_fresh_ish_account_plans_hard",
             "test_learned_tracks_first", "test_weak_roster_falls_back_to_easy_with_reason",
             "test_never_prefers_low_p", "test_missing_upgrades_degrade_instead_of_block",
             "test_map_difficulty_matters_less_in_easy", "test_long_run_reaches_everything"]
    for name in order:
        res = globals()[name]()
        if name == "test_tower_unlock_order":
            print("tower unlock picks:", res)
        print(f"PASS {name}")
    print("all tests passed")
