"""Offline: the towers the shop gives away are read and placed.

Monkey Knowledge makes the first Dart Monkey (Bonus Monkey!) and the first
Glue Gunner of a game free; their shop tiles then say "Free". Dark Dungeons,
Flooded Valley and Muddy Puddles Impoppable (2026-11-11 16:50-17:08) were
each lost in round 6 or 7 with the free dart still in the shop.

Fixtures (stills of those games, 960x600):
  shop_free_darkdungeons.jpg   dart and glue "Free", sniper $400
  shop_free_floodedvalley.jpg  the same, first military tower a third off
  shop_priced_quad.jpg         Deflation: every tile shows a price

Run: python tests/test_free_opener_offline.py"""
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as N

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import game as G  # noqa: E402
from btd6bot import match as M  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.strategy import Executor, rules  # noqa: E402
from btd6bot.vision import Vision  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def _free_kinds(name):
    """What Game.read_free_kinds makes of one still: the same region, read at
    twice the size because the stills are half as wide as the live screen."""
    img = cv2.imread(str(FIX / name))
    words = Vision(None).read(G.Game.SHOP_LABELS, img=img, scale=2.0)
    return G.free_kinds_in_shop(words, G.Game.SHOP_LABEL_X, G.Game.SHOP_LABEL_Y0,
                                G.Game.SHOP_LABEL_DY, G.Game.SHOP_ROWS)


def test_free_tiles_are_read_from_the_stills():
    assert _free_kinds("shop_free_darkdungeons.jpg") == {"dart", "glue"}
    assert _free_kinds("shop_free_floodedvalley.jpg") == {"dart", "glue"}
    assert _free_kinds("shop_priced_quad.jpg") == set()


def test_words_off_the_label_grid_are_ignored():
    x_left, x_right = G.Game.SHOP_LABEL_X
    y0, dy, rows = G.Game.SHOP_LABEL_Y0, G.Game.SHOP_LABEL_DY, G.Game.SHOP_ROWS

    def read(*words):
        return G.free_kinds_in_shop([N(text=t, x=x, y=y) for t, x, y in words],
                                    G.Game.SHOP_LABEL_X, y0, dy, rows)
    assert read(("FRee", x_right, y0)) == {"dart"}
    assert read(("Free", x_left, y0)) == set()                  # the hero's tile
    assert read(("$330", x_left, y0 + dy)) == set()             # a price
    assert read(("Free", x_left, y0 + rows * dy)) == set()      # below the rows in view
    assert read(("Free", 0.5, y0)) == set()                     # on the map, not in the shop


def test_a_free_kind_costs_nothing_until_one_is_placed():
    g = G.Game.__new__(G.Game)
    g.difficulty, g.learned_cost, g.free_kinds = "hard", {}, {"dart"}
    assert g.price("dart") == 0
    assert g.price("tack") == T.tower_cost("tack", "hard")
    g.free_kinds.discard("dart")            # what place() does once it stands
    assert g.price("dart") == T.tower_cost("dart", "hard")


def _match(mode, free, strat=None, forbidden=()):
    """A Match with what _place_free_openers reads; every step asked of the
    executor is noted in m.asked and answered "done"."""
    m = M.Match.__new__(M.Match)
    m.asked = []

    @contextmanager
    def why(*_):
        yield

    def try_step(step, cash, rnd):
        m.asked.append(step)
        return "done"
    m.ex = N(rules=rules(mode), strat=strat or {"id": "x"}, CHEAP_OPENERS=Executor.CHEAP_OPENERS,
             kind_allowed=lambda k: k not in forbidden, why=why, try_step=try_step)
    m.g = N(towers={}, read_free_kinds=lambda: set(free), cash_stable=lambda: 440,
            fail_reason=None)
    return m


def test_one_life_game_places_the_free_dart_at_the_entrance():
    m = _match("impoppable", {"dart", "glue"})
    assert m._place_free_openers(6) == ["dart"]     # the glue pops nothing: left alone
    (step,) = m.asked
    assert step["kind"] == "dart" and step["segment"] == [0.05, 0.45]


def test_no_free_tower_where_it_does_not_belong():
    assert _match("hard", {"dart"})._place_free_openers(1) == []            # lives to spare
    assert _match("impoppable", set())._place_free_openers(6) == []         # nothing free
    assert _match("impoppable", {"dart"}, forbidden=("dart",))._place_free_openers(6) == []
    assert _match("impoppable", {"dart"}, strat={"starter": "none"})._place_free_openers(6) == []
    assert _match("impoppable", {"dart"}, strat={"achievement": "x"})._place_free_openers(6) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
