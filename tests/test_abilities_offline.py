"""AbilityPlanner logic. Run: python tests/test_abilities_offline.py
(also collectable by pytest). Does not touch the game."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btd6bot import abilities as A  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.strategy import MODE_RULES  # noqa: E402


@dataclass
class P:
    tid: str
    kind: str
    tiers: list = field(default_factory=lambda: [0, 0, 0])


HERO = P("hero1", "hero")


def run(pl, towers, rnd, in_round, t0, t1, step=1.0, dropped_at=()):
    """Call decide every `step` real seconds; returns [(t, keys)] with presses."""
    out = []
    t = t0
    while t < t1:
        pl.update_towers(towers, rnd)
        keys = pl.decide(t, rnd, in_round, lives_dropped=t in dropped_at)
        if keys:
            out.append((t, keys))
        t += step
    return out


# ------------------------------------------------------------------ data

def test_tower_ability_table_matches_towers():
    names = {u["name"] for t in T.TOWERS.values() for p in t["upgrades"] for u in p}
    assert set(A.TOWER_ABILITIES) <= names
    assert ("bomb", 2, 4) in A.TOWER_ABILITY_AT
    for cd, use in A.TOWER_ABILITIES.values():
        assert use in ("on_cooldown", "moab", "save", "never") and cd > 0


def test_tower_abilities_highest_per_path():
    assert A.tower_abilities("bomb", [0, 4, 0]) == ["MOAB Assassin"]
    assert A.tower_abilities("bomb", [0, 5, 0]) == ["MOAB Eliminator"]
    assert A.tower_abilities("bomb", [0, 3, 0]) == []
    assert A.tower_abilities("farm", [0, 5, 0]) == ["IMF Loan", "Monkey-Nomics"]
    assert A.tower_abilities("bomb", [5, 0, 0]) == []  # Bomb Blitz is passive


def test_hero_abilities_have_policies():
    for h in T.HEROES.values():
        levels = [a["level"] for a in h["abilities"]]
        assert levels == sorted(levels)
        for a in h["abilities"]:
            assert a["use"] in ("on_cooldown", "moab", "save", "never")


# ------------------------------------------------------------------ hero level

def test_hero_level_estimate_ranges():
    # placed round 1, 1.0x hero: L3 within rounds ~5-9, L10 well before round 70
    assert 5 <= A.unlock_round("quincy", 1, 3, A.HERO_XP_OPTIMISM) <= 9
    assert 5 <= A.unlock_round("quincy", 1, 3) <= 9
    assert A.unlock_round("quincy", 1, 10, A.HERO_XP_OPTIMISM) <= 50
    assert A.unlock_round("quincy", 1, 10) < 70
    # pessimistic never earlier than central, central never earlier than optimistic
    for hero in ("quincy", "churchill", "ezili"):
        for lvl in (3, 7, 10):
            o = A.unlock_round(hero, 1, lvl, A.HERO_XP_OPTIMISM)
            c = A.unlock_round(hero, 1, lvl)
            p = A.unlock_round(hero, 1, lvl, A.HERO_XP_PESSIMISM)
            assert o <= c <= p
    # slower heroes level slower
    assert A.unlock_round("churchill", 1, 10) > A.unlock_round("quincy", 1, 10)
    # a late placement (deflation, round 31) levels fast
    assert A.unlock_round("quincy", 31, 3) <= 33
    # no XP before the first round ends
    assert A.estimate_hero_level("quincy", 3, 3) == 1
    assert A.hero_xp(None, 10) == 0


def test_level_monotonic():
    prev = 1
    for r in range(1, 101):
        lvl = A.estimate_hero_level("quincy", 1, r)
        assert lvl >= prev
        prev = lvl
    assert prev == 20 or prev >= 19


# ------------------------------------------------------------------ moab rounds

def test_moab_rounds():
    assert not A.is_moab_round(30)
    assert not A.is_moab_round(None)
    assert not A.is_moab_round(39)  # first MOAB is round 40 (data/rounds.json)
    assert A.is_moab_round(40) and A.is_moab_round(41) and A.is_moab_round(63)
    assert A.is_moab_round(40, MODE_RULES["easy"])


# ------------------------------------------------------------------ decide()

def test_no_hero_no_presses():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    assert run(pl, [], 10, True, 0, 30) == []


def test_locked_hero_ability_not_pressed():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    pl.update_towers([HERO], 1)
    assert run(pl, [HERO], 2, True, 0, 60) == []


def test_on_cooldown_only_in_rounds_and_respects_cooldown():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    pl.update_towers([HERO], 1)
    # between rounds: nothing
    assert run(pl, [HERO], 20, False, 0, 30) == []
    # round 20: L3 certain (Rapid Shot, 60 s at 1x = 30 s real at 2x)
    presses = run(pl, [HERO], 20, True, 100, 200)
    times = [t for t, k in presses]
    assert all(k == [1] for _, k in presses)
    assert times[0] == 100
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps and all(g >= 30 for g in gaps), gaps
    assert all(g <= 31 for g in gaps), gaps


def test_cooldown_frozen_between_rounds():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    pl.update_towers([HERO], 1)
    assert run(pl, [HERO], 20, True, 0, 1) == [(0, [1])]
    # 25 real s in round (50 game s of 60), then a long break, then 4 s more
    run(pl, [HERO], 20, True, 1, 25)
    assert run(pl, [HERO], 21, False, 25, 300) == []
    presses = run(pl, [HERO], 21, True, 300, 320)
    assert presses and presses[0][0] >= 305  # needed ~5 more in-round seconds


def test_uncertain_level_retries_often():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    pl.update_towers([HERO], 1)
    # round 7: optimistically L3, not certainly -> retry every RETRY_GAME_S/2 real s
    presses = run(pl, [HERO], 7, True, 0, 60)
    times = [t for t, _ in presses]
    assert len(times) >= 5
    assert max(b - a for a, b in zip(times, times[1:])) <= A.RETRY_GAME_S / 2 + 1


def test_moab_ability_waits_for_moab_round():
    pl = A.AbilityPlanner("churchill", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    # round 30: Armor Piercing Shells (L3, moab) unlocked, but not a MOAB round
    assert run(pl, [HERO], 30, True, 0, 60) == []
    # round 40: fires a few seconds in, not at the very start
    presses = run(pl, [HERO], 40, True, 100, 160)
    assert presses and presses[0][1] == [1]
    assert 100 + A.MOAB_DELAY_S <= presses[0][0] <= 100 + A.MOAB_DELAY_S + 1


def test_never_and_save_only_in_emergency():
    pl = A.AbilityPlanner("dan_dmonke", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    assert run(pl, [HERO], 79, True, 0, 60) == []  # all 'never'/'save'
    out = run(pl, [HERO], 79, True, 60, 62, dropped_at=(61.0,))
    assert out == [(61.0, [3])]  # Rabble Rouser (save) is the 3rd slot; never-slots skipped


def test_emergency_fires_everything_once_ready_or_not():
    pl = A.AbilityPlanner("churchill", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    run(pl, [HERO], 75, True, 0, 30)  # MOAB round: both already fired once
    keys = pl.decide(31.0, 75, True, lives_dropped=True)
    assert sorted(keys) == [1, 2]  # L3 + L10 by round 75 (optimistic)
    assert all(r == "emergency" for _, _, r in pl.last_fired)


def test_emergency_presses_do_not_reset_the_cooldown_clock():
    pl = A.AbilityPlanner("quincy", MODE_RULES["easy"])
    pl.update_towers([HERO], 1)
    assert pl.decide(0.0, 30, True) == [1]          # Rapid Shot, on cooldown use
    # lives fall twice a second for 5 s: pressed at most every EMERGENCY_REPEAT_S
    presses = [t for t in [x / 2 for x in range(1, 11)]
               if pl.decide(t, 30, True, lives_dropped=True)]
    assert len(presses) <= 5 / A.EMERGENCY_REPEAT_S + 1
    # the cooldown still counts from the first (real) press at t=0: Rapid
    # Shot (60 s at 1x, 2x speed) is pressed again after 30 real seconds
    out = run(pl, [HERO], 30, True, 6.0, 40.0)
    assert out and out[0][0] <= 31.0


def test_crisis_round_fires_everything_after_a_short_delay():
    pl = A.AbilityPlanner("churchill", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    # round 30 is no MOAB round: Armor Piercing Shells (moab use) waits ...
    assert pl.decide(0.0, 30, True) == []
    # ... unless the round is forecast to leak
    assert pl.decide(1.0, 30, True, crisis=True) == []      # bloons not out yet
    keys = pl.decide(A.MOAB_DELAY_S + 0.5, 30, True, crisis=True)
    assert keys == [1] and pl.last_fired[0][2] == "crisis round"
    assert pl.decide(A.MOAB_DELAY_S + 1.5, 30, True, crisis=True) == []   # cooldown respected


def test_emergency_skips_never():
    pl = A.AbilityPlanner("ezili", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    keys = pl.decide(0.0, 90, True, lives_dropped=True)
    names = {n for _, n, _ in pl.last_fired}
    assert "hero:Sacrificial Totem" not in names
    assert keys == [1, 2]


def test_tower_ability_slots_order():
    """Tower ability bought before the hero's first unlock takes hotkey 1."""
    pl = A.AbilityPlanner("churchill", MODE_RULES["hard"])
    bomb = P("bomb1", "bomb", [0, 4, 0])
    pl.update_towers([HERO], 3)
    pl.decide(0, 3, True)
    pl.update_towers([HERO, bomb], 5)
    pl.decide(1, 5, True)
    hk = {name: k for k, name, *_ in pl.hotkeys(40)}
    assert hk["MOAB Assassin"] == 1
    assert hk["hero:Armor Piercing Shells"] == 2
    # selling the bomb frees hotkey 1 for the hero
    pl.update_towers([HERO], 41)
    hk = {name: k for k, name, *_ in pl.hotkeys(41)}
    assert hk["hero:Armor Piercing Shells"] == 1


def test_tower_abilities_stack_and_never_skipped():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    towers = [P("bomb1", "bomb", [0, 4, 0]), P("bomb2", "bomb", [0, 4, 0]),
              P("sub1", "sub", [0, 4, 0])]
    pl.update_towers(towers, 45)
    slots = pl.hotkeys(45)
    assert [n for _, n, *_ in slots] in (["MOAB Assassin", "First Strike Capability"],
                                         ["First Strike Capability", "MOAB Assassin"])
    pl.decide(0, 45, True)
    keys = pl.decide(5, 45, True)
    fs = next(k for k, n, *_ in slots if n == "First Strike Capability")
    assert fs not in keys
    assert keys == [next(k for k, n, *_ in slots if n == "MOAB Assassin")]


def test_round_start_detected_by_round_change():
    pl = A.AbilityPlanner("churchill", MODE_RULES["hard"])
    pl.update_towers([HERO], 3)
    assert run(pl, [HERO], 30, True, 0, 100) == []
    # round 40 starts without a between-rounds idle read; fires after the delay
    first = run(pl, [HERO], 40, True, 100, 110)
    assert first and first[0][0] >= 100 + A.MOAB_DELAY_S


def test_continuous_mode_always_in_round():
    pl = A.AbilityPlanner("quincy", MODE_RULES["apopalypse"])
    pl.update_towers([HERO], 1)
    assert run(pl, [HERO], 20, False, 0, 2)


def test_max_hotkey():
    pl = A.AbilityPlanner("quincy", MODE_RULES["medium"])
    kinds = [("dart", [0, 4, 0]), ("boomerang", [0, 4, 0]), ("bomb", [0, 4, 0]), ("tack", [0, 0, 4]),
             ("ice", [0, 0, 4]), ("glue", [0, 4, 0]), ("sniper", [0, 4, 0]), ("buccaneer", [0, 4, 0]),
             ("ace", [0, 4, 0]), ("heli", [0, 4, 0]), ("mortar", [0, 4, 0])]
    towers = [P(f"{k}1", k, tiers) for k, tiers in kinds]
    pl.update_towers(towers, 50)
    assert max(k for k, *_ in pl.hotkeys(50)) <= A.MAX_HOTKEY


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if failed else 0)
