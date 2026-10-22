"""Offline checks for towerxp.TowerXpCounter: each completed round's tower XP
is split between tower types by invested cash, with the map's difficulty and
Monkey Education multipliers, and every round is paid once.
Run: python tests/test_towerxp_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import towers as T  # noqa: E402
from btd6bot.account import CATEGORY_XP_MULT, MAPS, round_xp  # noqa: E402
from btd6bot.towerxp import EDUCATION_MULT, TowerXpCounter, invested  # noqa: E402


def _map_in(category):
    return next(m for m, c in MAPS.items() if c == category)


def test_one_tower_type_gets_the_whole_round():
    c = TowerXpCounter(_map_in("beginner"))
    c.round_end(10, [N(kind="tack", tiers=(2, 0, 0)), N(kind="hero", tiers=(0, 0, 0))])
    assert c.rounded() == {"tack": round(round_xp(10))}


def test_split_by_invested_cash_and_multipliers():
    towers = [N(kind="tack", tiers=(0, 0, 0)), N(kind="ninja", tiers=(2, 0, 2))]
    cash = invested(towers)
    c = TowerXpCounter(_map_in("expert"), mk_unlocked=["Monkey Education"])
    c.round_end(30, towers)
    xp = round_xp(30) * CATEGORY_XP_MULT["expert"] * EDUCATION_MULT
    assert abs(c.totals["ninja"] - xp * cash["ninja"] / sum(cash.values())) < 1e-6
    assert abs(sum(c.totals.values()) - xp) < 1e-6


def test_each_round_is_paid_once_and_reverse_maps_count():
    c = TowerXpCounter(_map_in("advanced") + " reverse")
    tack = [N(kind="tack", tiers=(0, 0, 0))]
    c.round_end(20, tack)
    c.round_end(20, tack)
    assert c.rounded() == {"tack": round(round_xp(20) * CATEGORY_XP_MULT["advanced"])}


def test_invested_counts_every_tier_bought():
    cash = invested([N(kind="dart", tiers=(0, 2, 0))])
    assert cash["dart"] == T.tower_cost("dart") + T.upgrade_cost("dart", 2, 1) + T.upgrade_cost("dart", 2, 2)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
