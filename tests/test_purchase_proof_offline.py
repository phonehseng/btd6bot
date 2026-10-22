"""Game.place / Game.upgrade / Game.probe_roster without the game: every screen
read and click is replaced by a script, so these tests check the decisions only.

Covers the log audit of 2026-10-22:
  * phantom purchases ("placement of ninja assumed ... cash 374 -> 407") are not
    recorded; a purchase needs a cash drop of about its price, or a selection;
  * observed prices are only learned within 0.7x-1.3x of the price table;
  * a refused spot keeps the tower held and the next spot is probed;
  * the upgrade panel: a closed path is never clicked, a price above the cash
    clicks nothing, and next-tier prices correct a drifted tier count
    (Spike Factory sp1 really 3-0-2 while the bot believed 2-0-2);
  * the roster probe only probes the towers asked for and stops after 3 failures.
Run: python tests/test_purchase_proof_offline.py"""
import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import game as G  # noqa: E402
from btd6bot import layout as L  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.game import Game, Placed  # noqa: E402

logging.getLogger("game").setLevel(logging.ERROR)
# no real waiting: the module's sleeps return at once, its clock still runs
G.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)


class FakeInput:
    def __init__(self):
        self.clicks, self.keys = [], []

    def click(self, x, y):
        self.clicks.append((x, y))

    def move(self, *a, **k):
        pass

    def press(self, key):
        self.keys.append(key)


def scripted(values):
    """A function returning the given values in turn, then the last one forever."""
    values = list(values)

    def read(*a, **k):
        return values.pop(0) if len(values) > 1 else values[0]
    return read


def make_game(difficulty="medium", cash=(1000,), drops=(None,), selectable=False,
              bad_spots=(), click_refused=()):
    """A Game whose screen is a script.
    cash: what cash_stable() returns in turn; drops: what cash() returns in turn
    (the reads watched for a purchase); selectable: whether a tower is found when
    clicked; bad_spots: spots the probe sees red; click_refused: spots where the
    game keeps the tower on the cursor after the click."""
    g = Game(screen=None, inp=FakeInput(), layout=L.get(1920, 1200), difficulty=difficulty)
    g.CASH_PROOF_S = 0.05
    g.cash_stable = scripted(cash)
    g.cash = scripted(drops)
    g.holds = []

    def hold(kind, tries=3):
        g.holds.append(kind)
        return True
    g.hold = hold
    g.cancel_hold = lambda: None
    g.fresh = lambda: None
    g.probe = lambda fx, fy, baseline=None, settle=0.06: (fx, fy) not in bad_spots
    g.is_holding = lambda: bool(g.inp.clicks) and g.inp.clicks[-1] in click_refused
    g.selects = 0

    def select(p):
        g.selects += 1
        return selectable
    g.select = select
    g.deselect = lambda p: None
    return g


# -- prices ---------------------------------------------------------------------------
def test_learned_prices_stay_near_the_price_table():
    g = make_game()
    table = T.tower_cost("ninja", "medium")                  # $400
    assert not g.learn_price("ninja", 0, 0, int(0.6 * table))  # a misread: ignored
    assert g.price("ninja") == table
    assert g.learn_price("ninja", 0, 0, 290)                 # in the band (0.725x)
    assert g.learn_price("ninja", 0, 0, 380)
    assert g.learn_price("ninja", 0, 0, 300)                 # lower again: income noise
    assert g.price("ninja") == 380, "the highest plausible observation is kept"
    g.learned_cost[("ninja", 0, 0)] = 100                    # however it got there ...
    assert g.price("ninja") == int(0.7 * table), "... the price used stays in the band"


def test_prices_follow_the_difficulty():
    g = make_game(difficulty="hard")
    assert g.table_price("spike", 1, 4) == T.upgrade_cost("spike", 1, 4, "hard") == 10260


# -- placing --------------------------------------------------------------------------
def test_phantom_purchase_is_not_recorded():
    """Ancient Portal: ninja 'placed' while the cash went 374 -> 407."""
    g = make_game(cash=(374,), drops=(407,), selectable=False)
    g.learned_cost[("ninja", 0, 0)] = 290    # the bad price that let it try
    assert g.place("n2", "ninja", 0.12, 0.73) is None
    assert g.fail_reason == "unverified"
    assert "n2" not in g.towers
    assert g.selects == 1, "looked for the tower on the map before giving up"


def test_purchase_proven_by_cash_drop():
    g = make_game(cash=(1000,), drops=(1000, 1000, 600))
    p = g.place("n1", "ninja", 0.5, 0.25)
    assert p is not None and g.towers["n1"] is p and p.verified
    assert p.spent == 400 and g.learned_cost[("ninja", 0, 0)] == 400
    assert g.selects == 0, "the cash proved it: no selection needed"


def test_purchase_proven_by_selection_when_cash_is_unreadable():
    g = make_game(cash=(1000,), drops=(None,), selectable=True)
    p = g.place("d1", "dart", 0.3, 0.3)
    assert p is not None and p.verified and g.selects == 1
    assert p.spent == g.price("dart")


def test_cash_rising_by_a_price_is_no_proof():
    """Cash going UP by about a price must not count (the sign matters)."""
    g = make_game(cash=(1000,), drops=(1400,), selectable=False)
    assert g.place("n1", "ninja", 0.5, 0.5) is None and g.fail_reason == "unverified"


def test_refused_spot_keeps_the_tower_held():
    a, b, c = (0.10, 0.10), (0.20, 0.20), (0.30, 0.30)
    g = make_game(drops=(600,), bad_spots=(a,), click_refused=(b,))
    p = g.place("n1", "ninja", *a, more_spots=[b, c])
    assert p is not None and (p.x, p.y) == c
    assert g.holds == ["ninja"], "one pick-up for all three spots"
    assert g.refused_spots == [a, b]
    assert g.inp.clicks == [b, c], "the probe-refused spot is never clicked"


def test_every_spot_refused():
    a, b = (0.10, 0.10), (0.20, 0.20)
    g = make_game(bad_spots=(a, b))
    assert g.place("n1", "ninja", *a, more_spots=[b]) is None
    assert g.fail_reason == "spot" and g.refused_spots == [a, b] and not g.inp.clicks


# -- upgrade panel ---------------------------------------------------------------------
def upgrade_game(panel, cash=5000, difficulty="hard"):
    g = make_game(difficulty=difficulty, cash=(cash,), selectable=True)
    g.path_costs = lambda p, f=None: list(panel)
    return g


def path_clicks(g, p):
    buttons = set(g.panel(p)["paths"])
    return [c for c in g.inp.clicks if c in buttons]


def test_closed_path_is_capped_without_clicking():
    """sp1 3-0-2: path 3 shows no price; it was clicked 3 times in the log."""
    g = upgrade_game([("cash", 10260), (None, None), (None, None)])
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[3, 0, 2])
    assert g.upgrade(p, 3) is False and g.fail_reason == "capped"
    assert ("sp1", 3) in g.closed and not path_clicks(g, p) and not g.inp.keys
    selects = g.selects
    assert g.upgrade(p, 3) is False and g.fail_reason == "capped"
    assert g.selects == selects, "a known closed path is not even selected again"


def test_unreadable_panel_caps_nothing():
    g = upgrade_game([(None, None)] * 3)
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[0, 0, 0])
    g.upgrade(p, 1)
    assert not g.closed, "a panel still sliding in shows no price on any path"


def test_drifted_tier_count_is_corrected_from_the_panel():
    """The bot believed 2-0-2; path 1 asks $10,260 = tier 4 on Hard, so it is 3-0-2."""
    g = upgrade_game([("cash", 10260), (None, None), (None, None)])
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[2, 0, 2])
    assert g.upgrade(p, 1) is False and g.fail_reason == "drift"
    assert p.tiers == [3, 0, 2] and not path_clicks(g, p)


def test_discounted_price_corrects_nothing():
    """A price that matches no tier (a village discount) leaves the count alone."""
    g = upgrade_game([("cash", int(0.9 * 10260)), (None, None), (None, None)], cash=50000)
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[3, 0, 2])
    g.upgrade(p, 1)
    assert p.tiers == [3, 0, 2] and g.fail_reason != "drift"


def test_price_above_cash_clicks_nothing():
    g = upgrade_game([("cash", 10260), (None, None), (None, None)], cash=5000)
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[3, 0, 2])
    assert g.upgrade(p, 1) is False and g.fail_reason == "cash"
    assert g.last_price == 10260 and not path_clicks(g, p) and not g.inp.keys


# -- roster probe ------------------------------------------------------------------------
def test_roster_probe_only_probes_the_towers_asked_for():
    g = make_game(cash=(100000,))
    out = g.probe_roster(["dart", "ninja"])
    assert set(out) == {"dart", "ninja"} and all(out.values())
    assert g.holds == ["dart", "ninja"]


def test_roster_probe_stops_after_three_failures():
    g = make_game(cash=(100000,))

    def dead_hotkey(kind, tries=3):
        g.holds.append(kind)
        return False
    g.hold = dead_hotkey
    out = g.probe_roster()
    assert len(g.holds) == Game.PROBE_MAX_FAILS == 3 and not any(out.values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
