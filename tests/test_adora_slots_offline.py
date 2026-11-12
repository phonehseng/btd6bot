"""Adora's ability keys: which hotkeys the planner may press once Blood
Sacrifice may be on the bar (abilities.AbilityPlanner.unsafe_keys).

Blood Sacrifice arms on its key and then destroys the next tower clicked, so
the planner must never press a key it may sit on. The bar orders abilities
by when they came (hero abilities at their level-up, tower abilities when
bought), so its key depends on the hero's level - only estimated - and on
the tower abilities bought around it. These tests check the window against a
simulated "true" bar for many random games, and the simple boards by hand.

Run: python tests/test_adora_slots_offline.py. No game, no screen.
"""
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import abilities as A  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.strategy import MODE_RULES  # noqa: E402

HARD = MODE_RULES["hard"]
HERO = N(tid="hero", kind="hero", tiers=[0, 0, 0])


def planner(placed=6):
    pl = A.AbilityPlanner("adora", HARD)
    pl.update_towers([HERO], placed)
    return pl


def presses(pl, rnd, seconds=400):
    """Every key decide() presses over `seconds` real seconds of round rnd,
    with emergencies and a crisis mixed in."""
    out = set()
    for i in range(seconds):
        out |= set(pl.decide(1000.0 * rnd + i, rnd, True, lives_dropped=(i % 9 == 0), crisis=(i % 2 == 0)))
    return out


def test_levels_and_cooldowns_match_the_game_model():
    """Long Arm of Light at 3, Blood Sacrifice at 7, Ball of Light at 10
    (data/game_model/heroes.json; fandom:Adora_(BTD6) agrees), with the
    game's cooldowns 45, 30 and 60 s."""
    game = json.loads((ROOT / "data" / "game_model" / "heroes.json").read_text(encoding="utf-8"))["adora"]
    exported = [(a["level"], a["name"].replace("The ", ""), a["cooldown"]) for a in game["abilities"]]
    ours = [(a["level"], a["name"], a["cooldown_s"]) for a in T.HEROES["adora"]["abilities"]]
    assert exported == ours, (exported, ours)
    assert [a["name"] for a in T.HEROES["adora"]["abilities"] if a["name"] in A.DESTRUCTIVE_ABILITIES] \
        == ["Blood Sacrifice"]


def test_adora_alone_holds_key_two_only():
    pl = planner()
    assert pl.unsafe_keys(20) == set()               # level 7 not possible yet
    assert presses(pl, 20) == {1}                    # Long Arm of Light
    late = 80
    assert pl.slot_window("Blood Sacrifice", late) == (2, 2)
    assert pl.unsafe_keys(late) == {2}
    assert presses(pl, late) == {1, 3}               # Long Arm of Light and Ball of Light


def test_a_tower_ability_well_before_or_after_level_7_keeps_the_window_one_key():
    pl = planner()
    dart = N(tid="d1", kind="dartling", tiers=[0, 4, 0])
    pl.update_towers([HERO, dart], 15)               # long before level 7 (round 31 at the earliest)
    assert pl.slot_window("Blood Sacrifice", 60) == (3, 3)
    sab = N(tid="n1", kind="ninja", tiers=[0, 4, 0])
    pl.update_towers([HERO, dart, sab], 60)          # long after (round 45 at the latest)
    assert pl.slot_window("Blood Sacrifice", 80) == (3, 3)
    keys = dict((n, k) for k, n, *_ in pl.hotkeys(80))
    assert keys["hero:Blood Sacrifice"] == 3 and pl.unsafe_keys(80) == {3}


def test_a_tower_ability_bought_around_level_7_widens_the_window():
    pl = planner()
    first, last = A.unlock_round("adora", 6, 7, A.SLOT_XP_OPTIMISM), A.unlock_round("adora", 6, 7, A.SLOT_XP_PESSIMISM)
    dart = N(tid="d1", kind="dartling", tiers=[0, 4, 0])
    pl.update_towers([HERO, dart], (first + last) // 2)
    assert pl.slot_window("Blood Sacrifice", 80) == (2, 3)
    assert pl.unsafe_keys(80) == {2, 3}
    assert 2 not in presses(pl, 80) and 3 not in presses(pl, 80)


def test_export_only_abilities_count_as_maybe_slots():
    """A Dark Knight (super 0-0-3) has Darkshift in the game export but not
    in TOWER_ABILITIES: it may hold a slot before Blood Sacrifice."""
    assert A.exported_ability_count("super", (0, 0, 3)) == 1
    pl = planner()
    pl.update_towers([HERO, N(tid="s1", kind="super", tiers=[0, 0, 3])], 10)
    assert pl.slot_window("Blood Sacrifice", 80) == (2, 3)


def test_a_tier_5_ability_may_keep_its_tier_4_slot():
    """MOAB Assassin bought before level 7, MOAB Eliminator after: the
    Eliminator may sit where the Assassin was (before Blood Sacrifice) or at
    the end, so both keys are held."""
    pl = planner()
    pl.update_towers([HERO, N(tid="b1", kind="bomb", tiers=[0, 4, 0])], 15)
    pl.update_towers([HERO, N(tid="b1", kind="bomb", tiers=[0, 5, 0])], 70)
    assert pl.slot_window("Blood Sacrifice", 80) == (2, 3)


def test_a_sold_tower_frees_its_slot():
    pl = planner()
    dart = N(tid="d1", kind="dartling", tiers=[0, 4, 0])
    pl.update_towers([HERO, dart], 15)
    assert pl.slot_window("Blood Sacrifice", 60) == (3, 3)
    pl.update_towers([HERO], 61)
    assert pl.slot_window("Blood Sacrifice", 61) == (2, 2)


def test_other_heroes_are_untouched():
    pl = A.AbilityPlanner("quincy", HARD)
    pl.update_towers([N(tid="hero", kind="hero", tiers=[0, 0, 0])], 1)
    assert pl.unsafe_keys(90) == set() and pl.destructive_possible(90) is None


# -- against a simulated true bar --------------------------------------------------

def true_bar(placed, factor, buys, rnd):
    """The bar as the game would have it in round rnd: names in order.
    The hero's levels come at the end of a round with XP x factor; a tower's
    abilities at its buy round + u. Identical tower abilities share the
    slot of the first. A tier-5 upgrade keeps its tier-4 slot or takes a new
    one (`in_place`); abilities only the export lists show or not
    (`shows`)."""
    slots = {}
    for ab in T.HEROES["adora"]["abilities"]:
        if A.estimate_hero_level("adora", placed, rnd, factor) >= ab["level"]:
            slots["hero:" + ab["name"]] = A.unlock_round("adora", placed, ab["level"], factor) - 0.01
    for b in buys:
        if b["round"] > rnd or (b["sold"] is not None and b["sold"] <= rnd):
            continue
        t = b["round"] + b["u"]
        tiers = b["tiers"]
        if b["upgrade"] is not None and b["upgrade"] <= rnd:
            tiers = b["tiers5"]
            if not b["in_place"]:
                t = b["upgrade"] + b["u"]
        names = A.tower_abilities(b["kind"], tiers)
        extra = max(0, (A.exported_ability_count(b["kind"], tiers) or 0) - len(names))
        if b["shows"]:
            names = names + [f"{b['tid']}:extra{i}" for i in range(extra)]
        for n in names:
            slots[n] = min(slots.get(n, t), t)
    return [n for n, _ in sorted(slots.items(), key=lambda kv: kv[1])]


def board(buys, rnd):
    out = [HERO]
    for b in buys:
        if b["round"] > rnd or (b["sold"] is not None and b["sold"] <= rnd):
            continue
        tiers = b["tiers5"] if b["upgrade"] is not None and b["upgrade"] <= rnd else b["tiers"]
        out.append(N(tid=b["tid"], kind=b["kind"], tiers=list(tiers)))
    return out


CHOICES = [("dartling", (0, 4, 0), (0, 5, 0)), ("bomb", (0, 4, 0), (0, 5, 0)),
           ("ninja", (0, 4, 0), (0, 5, 0)), ("super", (0, 0, 3), (0, 0, 4)),
           ("heli", (0, 4, 0), (0, 5, 0)), ("tack", (0, 4, 0), (0, 5, 0)),
           ("sniper", (0, 4, 0), (0, 5, 0)), ("desperado", (0, 3, 0), (0, 4, 0))]


def test_the_window_always_holds_the_true_key():
    """3,000 random games: true XP factor 1.0-1.62 (Beginner to Expert with
    every hero XP knowledge), towers with abilities bought, upgraded and
    sold at random rounds. Every round the key Blood Sacrifice really has
    must be in unsafe_keys."""
    rng = random.Random(7)
    for game in range(3000):
        placed = rng.randint(1, 40)
        factor = rng.uniform(1.0, 1.62)
        buys = []
        for i in range(rng.randint(0, 4)):
            kind, t4, t5 = rng.choice(CHOICES)
            r = rng.randint(placed, 95)
            buys.append({"tid": f"t{i}", "kind": kind, "tiers": t4, "tiers5": t5, "round": r,
                         "u": rng.random(), "shows": rng.random() < 0.5,
                         "upgrade": rng.choice([None, r + rng.randint(1, 20)]), "in_place": rng.random() < 0.5,
                         "sold": rng.choice([None, None, r + rng.randint(1, 30)])})
        pl = A.AbilityPlanner("adora", HARD)
        for rnd in range(placed, 101):
            pl.update_towers(board(buys, rnd), rnd)
            bar = true_bar(placed, factor, buys, rnd)
            if "hero:Blood Sacrifice" in bar:
                key = bar.index("hero:Blood Sacrifice") + 1
                assert key in pl.unsafe_keys(rnd), (game, rnd, bar, pl.unsafe_keys(rnd), buys)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, repr(e)[:600])
    sys.exit(1 if failed else 0)
