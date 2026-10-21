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


def simulate(n_games: int, seed: int = 1, verbose_first: int = 40) -> tuple[AccountState, list[str]]:
    rng = random.Random(seed)
    acc = AccountState()
    strategies = {s.id: s for s in P.EXAMPLE_STRATEGIES}
    log: list[str] = []
    phase = None
    minutes_total = 0.0
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
        p_true = P._prior(s, plan.map, cat, plan.mode_key)  # "reality" = prior
        won = rng.random() < p_true
        xp = P.game_xp(plan.mode_key, cat) if won else P.game_xp(plan.mode_key, cat, fail_frac=0.6)
        mm = P.estimate_mm(acc, plan.map, plan.mode_key)[0] if won else 0
        mins = MODES[plan.mode_key].minutes if won else MODES[plan.mode_key].minutes * 0.6
        minutes_total += mins + 1
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
    log.append(f"== end: games={acc.games_played} L{acc.player_level} MM={acc.monkey_money} "
               f"medals={acc.medal_count()}/{len(acc.all_goals())} uniq={acc.unique_map_wins()} "
               f"~{minutes_total / 60:.0f} h")
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


def test_long_run_reaches_everything():
    t0 = time.time()
    acc, log = simulate(4000, seed=11, verbose_first=0)
    print("\n".join(l for l in log if l.startswith("==")))
    print(f"(long sim took {time.time() - t0:.1f}s)")
    assert acc.unique_map_wins() == len([m for m in MAPS if m not in EXCLUDED_MAPS])
    left = acc.remaining_goals()
    # all non-CHIMPS medals must be reachable with the example roster
    assert not [g for g in left if g[1] != "chimps"], left[:10]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    order = ["test_xp_tables", "test_mode_unlocks_and_categories", "test_apply_level_rewards",
             "test_tower_unlock_order", "test_upgrade_unlocks_sequential", "test_mk",
             "test_learning_avoids_failing_strategy", "test_save_load_roundtrip",
             "test_fresh_account_first_40", "test_long_run_reaches_everything"]
    for name in order:
        res = globals()[name]()
        if name == "test_tower_unlock_order":
            print("tower unlock picks:", res)
        print(f"PASS {name}")
    print("all tests passed")
