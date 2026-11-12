"""Board income and village discounts (btd6bot/economy.py,
docs/model_fix_plan.md item 15): Benjamin's Cyber Cash, farms, the mode
rules that switch income off, Monkey Village discounts, and their use in
the build optimizer and in the executor's cash projections.

Run: python tests/test_economy_offline.py. No game, no screen.
"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import economy as E  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402

RULES = S.MODE_RULES


def tw(kind, tiers, x=0.0, z=0.0, tid=None):
    return N(tid=tid or kind, kind=kind, tiers=tuple(tiers), spot=N(x=x, z=z), spent=0.0)


def test_benjamin_cyber_cash_by_level():
    """$90 at level 1 up to $5,000 from 17 (the game model's export)."""
    got = {lvl: E.hero_income("benjamin", lvl) for lvl in (1, 2, 7, 8, 10, 11, 14, 15, 16, 17, 20)}
    assert got == {1: 90, 2: 140, 7: 140, 8: 250, 10: 250, 11: 1000, 14: 1000, 15: 2500,
                   16: 2500, 17: 5000, 20: 5000}, got
    assert E.hero_income("quincy", 20) == 0 and E.hero_income("benjamin", None) == 0


def test_mode_rules_switch_income_off_or_halve_it():
    board = [tw("farm", (0, 0, 3))]
    full = E.board_income(board, RULES["impoppable"], "benjamin", 11)
    assert full == 320 + 1000
    assert E.board_income(board, RULES["half_cash"], "benjamin", 11) == full / 2
    assert E.board_income(board, RULES["chimps"], "benjamin", 20) == 0       # no_income_towers
    assert E.board_income(board, RULES["deflation"], "benjamin", 20) == 0    # no income at all


def test_farms_pay_what_the_bot_collects():
    assert E.tower_income("farm", (0, 0, 0)) == 80 * E.BANANA_COLLECTED    # bananas on the ground
    assert E.tower_income("farm", (0, 0, 3)) == 320                          # Marketplace: paid straight
    assert E.tower_income("farm", (0, 0, 5)) == 4000 + 1120                  # Monkey Wall Street
    assert E.tower_income("farm", (0, 3, 0)) == 0                            # a bank the bot never empties
    assert E.tower_income("buccaneer", (0, 0, 3)) == 200                     # Merchantman


def test_bank_hack_raises_a_withdrawn_bank():
    saved = E.BOT_WITHDRAWS_BANKS
    try:
        E.BOT_WITHDRAWS_BANKS = True
        plain = E.tower_income("farm", (0, 3, 0))
        hacked5 = E.tower_income("farm", (0, 3, 0), "benjamin", 5)
        hacked9 = E.tower_income("farm", (0, 3, 0), "benjamin", 9)
        assert 0 < plain < hacked5 < hacked9
        assert E.tower_income("farm", (0, 3, 0), "quincy", 20) == plain
    finally:
        E.BOT_WITHDRAWS_BANKS = saved


def test_village_discounts():
    assert abs(E.village_discount((0, 0, 1)) - 0.10) < 1e-9
    assert abs(E.village_discount((0, 0, 2)) - 0.15) < 1e-9
    assert E.village_discount((2, 0, 0)) == 0
    near, far = tw("village", (0, 0, 2), 10.0, 0.0), tw("village", (0, 0, 1), 500.0, 0.0)
    assert abs(E.discount_at(0.0, 0.0, [near, far]) - 0.15) < 1e-9
    assert E.discount_at(0.0, 0.0, [far]) == 0
    assert E.discounted(1000, 3, 0.15) == 850 and E.discounted(1000, 4, 0.15) == 1000


def test_optimizer_prices_with_the_village_and_counts_board_cash():
    import optimize_builds as O
    fam = "hard"
    village = tw("village", (0, 0, 2), 10.0, 0.0, "v1")
    ninja = tw("ninja", (0, 0, 0), 0.0, 0.0, "n1")
    plain = O.place_cost("ninja", (2, 0, 2), fam, ninja.spot, [])
    cheap = O.place_cost("ninja", (2, 0, 2), fam, ninja.spot, [village])
    assert abs(cheap - 0.85 * plain) < 1e-6, (plain, cheap)
    # tier 4 is not discounted
    t4 = T.upgrade_cost("ninja", 1, 4, fam)
    assert abs(O.upgrade_cost("ninja", (3, 0, 0), (4, 0, 0), fam, 0.15) - t4) < 1e-6
    # a village does not discount itself
    assert O.spot_discount(village.spot, [village], own=village) == 0
    # Benjamin's cash in a long income mode, none in CHIMPS
    assert O.hero_cash("benjamin", "Monkey Meadow", "impoppable", placed_round=6) > 40000
    assert O.hero_cash("benjamin", "Monkey Meadow", "chimps", placed_round=6) == 0
    assert O.hero_cash("quincy", "Monkey Meadow", "impoppable", placed_round=6) == 0
    assert O.board_cash("impoppable", [ninja], "benjamin", 17) == 5000


def _executor(hero, towers, mode="impoppable", hero_round=6):
    ex = N(round_set="standard", income_mult=1.0, rules=RULES[mode],
           g=N(hero=hero, towers={t.tid: t for t in towers}), abil=N(hero_round=hero_round),
           m=N(name="Monkey Meadow"), account=None, LEAD_MARGIN=S.Executor.LEAD_MARGIN)
    ex._hero_level_estimate = lambda r: S.Executor._hero_level_estimate(ex, r)
    ex.round_income = lambda r: S.Executor.round_income(ex, r)
    ex.income_until = lambda due, r: S.Executor.income_until(ex, due, r)
    return ex


def test_executor_projects_benjamins_cash():
    """income_until (what reinforce.payable_by asks) and the threat lead
    times count Benjamin's pay at his estimated level."""
    from btd6bot import threats as TH
    hero = N(tid="hero", kind="hero", tiers=(0, 0, 0))
    ben = _executor("benjamin", [hero])
    quincy = _executor("quincy", [hero])
    assert quincy.round_income(80) == TH.round_cash("standard", 80)
    level = ben._hero_level_estimate(80)
    assert ben.round_income(80) == TH.round_cash("standard", 80) + E.hero_income("benjamin", level)
    more = ben.income_until(90, 80) - quincy.income_until(90, 80)
    assert more > 0
    from btd6bot.reinforce import payable_by
    need = TH.round_cash("standard", 80) / S.Executor.LEAD_MARGIN + 1.0
    assert payable_by(ben, need, 0.0, 81, 80) and not payable_by(quincy, need, 0.0, 81, 80)
    chimps = _executor("benjamin", [hero], mode="chimps")
    assert chimps.round_income(80) == TH.round_cash("standard", 80)


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
