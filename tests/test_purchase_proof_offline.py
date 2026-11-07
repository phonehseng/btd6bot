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
        self.clicks, self.keys, self.moves = [], [], []

    def click(self, x, y):
        self.clicks.append((x, y))

    def move(self, x, y, **k):
        self.moves.append((x, y))

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
    g.in_game = lambda f=None: True        # the match HUD is up (Game.screen_ok)
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
    g.path_costs = lambda p, f=None: [("cash", T.upgrade_cost("dart", i, 1, "medium")) for i in (1, 2, 3)]
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
    assert g.holds == ["ninja", "ninja"], \
        "a probe refusal keeps the hold; a refused click picks the tower up again"
    assert g.refused_spots == [a, b]
    assert g.inp.clicks == [b, c], "the probe-refused spot is never clicked"


def test_refused_click_then_failed_pick_up_stops():
    """Encrypted Impoppable: after a refused click the tower is picked up
    again; if that fails, place() stops instead of clicking a stale preview."""
    a, b = (0.10, 0.10), (0.20, 0.20)
    g = make_game(click_refused=(a,))
    picks = iter([True, False])
    g.hold = lambda kind, tries=3: next(picks)
    assert g.place("n1", "ninja", *a, more_spots=[b]) is None
    assert g.fail_reason == "hold" and g.inp.clicks == [a]


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


def test_blank_price_on_a_path_the_tiers_allow_is_read_again():
    """s1, a Super Monkey just placed (0-0-0), showed no price on path 1 and
    lost that path for the game (Bazaar Hard): it is a misread until it
    repeats in separate attempts."""
    import btd6bot.game as G
    g = upgrade_game([(None, None), ("cash", 1620), ("cash", 3240)])
    p = Placed("s1", "super", 0.12, 0.79, tiers=[0, 0, 0])
    for _ in range(G.CLOSED_AFTER_MISSES - 1):
        assert g.upgrade(p, 1) is False and g.fail_reason == "unread"
        assert ("s1", 1) not in g.closed and not path_clicks(g, p)
    assert g.upgrade(p, 1) is False and g.fail_reason == "capped"
    assert ("s1", 1) in g.closed


def test_blank_price_is_read_again_with_the_cursor_off_the_panel():
    """Peninsula Medium: path 1 read blank right after a click (the cursor's
    tooltip on the button), and that path was lost for the game. The second
    read is made with the cursor moved off the panel, and when it shows the
    price the path stays open and nothing is held back."""
    g = upgrade_game([])
    g.path_costs = scripted([[(None, None), ("cash", 1620), ("cash", 3240)],
                             [("cash", 2200), ("cash", 1620), ("cash", 3240)]])
    p = Placed("sb3", "sub", 0.12, 0.79, tiers=[1, 0, 4])
    g.upgrade(p, 1)
    assert g.fail_reason not in ("unread", "capped") and ("sb3", 1) not in g.closed
    box = g.panel(p)["box"]
    assert g.inp.moves and not any(box[0] <= x <= box[2] for x, _ in g.inp.moves), \
        "the re-read happens with the cursor beside the panel, not on it"


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


def test_closed_path_reveals_a_tier_the_bot_never_saw():
    """High Finance Magic Monkeys Only (2026-11-05): wizard2 was counted
    0-2-0 while its path 1 showed PATH CLOSED - the Intense Magic click had
    been judged "not bought" (Monkey Sense costs the same $325, so the
    button could not prove it, and round income hid the cash drop). Two
    paths in use close the third, so path 3 must hold a tier: once the
    blank reads make the path closed for good, the count is corrected."""
    import btd6bot.game as G
    g = upgrade_game([(None, None), ("cash", T.upgrade_cost("wizard", 2, 3, "hard")),
                      ("cash", T.upgrade_cost("wizard", 3, 1, "hard"))], difficulty="hard")
    p = Placed("wizard2", "wizard", 0.44, 0.71, tiers=[0, 2, 0])
    for _ in range(G.CLOSED_AFTER_MISSES - 1):
        assert g.upgrade(p, 1) is False and g.fail_reason == "unread" and p.tiers == [0, 2, 0]
    assert g.upgrade(p, 1) is False and g.fail_reason == "capped"
    assert ("wizard2", 1) in g.closed and p.tiers == [0, 2, 1], p.tiers
    assert not path_clicks(g, p) and not g.inp.keys
    # a path closed with both other paths counted (or none of them) says nothing new
    q = Placed("w3", "wizard", 0.44, 0.71, tiers=[0, 2, 1])
    assert not g._closed_path_hides_a_tier(q, 1) and q.tiers == [0, 2, 1]
    r = Placed("w4", "wizard", 0.44, 0.71, tiers=[0, 0, 0])
    assert not g._closed_path_hides_a_tier(r, 1) and r.tiers == [0, 0, 0]


def test_discounted_price_of_the_believed_tier_corrects_nothing():
    """A village-discounted price of the tier the bot already expects leaves the count alone."""
    g = upgrade_game([("cash", int(0.9 * 10260)), (None, None), (None, None)], cash=50000)
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[3, 0, 2])
    g.upgrade(p, 1)
    assert p.tiers == [3, 0, 2] and g.fail_reason != "drift"


def test_discounted_price_corrects_a_drifted_count():
    """Skates ABR (2026-11-03): the opener dart showed $15,390 on path 1 -
    Ultra-Juggernaut's $16,200 on Hard less a village's 5% - while the bot
    believed 2-0-0. The discounted price still names tier 5, so it is 4-0-0."""
    g = upgrade_game([("cash", 15390), (None, None), (None, None)], cash=50000)
    p = Placed("opener", "dart", 0.2, 0.2, tiers=[2, 0, 0])
    assert g.upgrade(p, 1) is False and g.fail_reason == "drift"
    assert p.tiers == [4, 0, 0] and not path_clicks(g, p)


def test_seventeen_percent_off_still_names_the_tier():
    """Polyphemus Impoppable (2026-11-04): every button near the full
    discount village was 17% under the table - Sun Avatar's tier at $19,920
    for $24,000, the MIB at $7,470 for $9,000 - one more than the villages'
    15%. No tier matched, so the drift check never fired; the bot believed
    the MIB village v2 was 0-0-0 while the game showed its 0-2-0 panel."""
    g = upgrade_game([("cash", 400), ("cash", 7470), ("cash", 500)], cash=50000, difficulty="impoppable")
    p = Placed("v2", "village", 0.75, 0.27, tiers=[0, 0, 0])
    assert g.upgrade(p, 1) is False and g.fail_reason == "drift"
    assert p.tiers == [0, 2, 0] and not path_clicks(g, p)
    g = upgrade_game([("cash", 19920), (None, None), ("cash", 1195)], cash=50000, difficulty="impoppable")
    p = Placed("s1", "super", 0.69, 0.27, tiers=[2, 0, 1])
    g.upgrade(p, 1)
    assert p.tiers == [2, 0, 1] and g.fail_reason != "drift", "the expected tiers, 17% off, change nothing"


def test_discounted_next_price_proves_the_purchase():
    """After a click the button shows the next tier's price, discounted by a
    village; that alone proves the purchase, even when round income hides the
    cash drop. Before, the verdict was "same", the hotkey bought a second tier
    and the bot believed neither."""
    g = upgrade_game([])
    g.cash_stable = scripted([22000, 22900])      # income outran the $1,850 spent
    g.path_costs = scripted([[("cash", 345), ("cash", 110), ("cash", 95)],
                             [("cash", 1850), ("cash", 110), ("cash", 95)]])
    p = Placed("opener", "dart", 0.2, 0.2, tiers=[2, 0, 0])
    assert g.upgrade(p, 1) is True
    assert p.tiers == [3, 0, 0] and not g.inp.keys, "no hotkey: one tier bought, one tier counted"


def test_equal_tier_prices_are_judged_by_cash():
    """Ninja path 1 costs $380 for tier 1 and tier 2 on Hard: after a click
    that bought tier 1 the button still shows $380. Ancient Portal ABR
    (2026-11-04) took that as "same", the hotkey bought tier 2 as well and
    the bot believed neither. The cash drop of one price decides instead."""
    g = upgrade_game([])
    g.cash_stable = scripted([9000, 8620])
    g.path_costs = scripted([[("cash", 380), ("cash", 270), ("cash", 485)],
                             [("cash", 380), ("cash", 270), ("cash", 485)]])
    p = Placed("n1", "ninja", 0.2, 0.2, tiers=[0, 0, 1])
    assert g.upgrade(p, 1) is True
    assert p.tiers == [1, 0, 1] and not g.inp.keys, "no hotkey: one tier bought, one tier counted"


def test_equal_tier_prices_with_income_press_no_hotkey():
    """Rake Impoppable (2026-11-04): ninja path 1 asks $420 for tier 1 and
    tier 2, so the button cannot move; the round's income lifted the cash
    past the price. That was taken as "same" and the hotkey bought tier 2
    too (0-0-1 -> 2-0-1). Now it is "unknown": no hotkey, tried again later."""
    g = upgrade_game([], difficulty="impoppable")
    g.cash_stable = scripted([10665, 10900])
    g.path_costs = scripted([[("cash", 420), ("cash", 300), ("cash", 540)],
                             [("cash", 420), ("cash", 300), ("cash", 540)]])
    p = Placed("ninja4", "ninja", 0.63, 0.3, tiers=[0, 0, 1])
    assert g.upgrade(p, 1) is False and g.fail_reason == "noeffect"
    assert p.tiers == [0, 0, 1] and not g.inp.keys, "no hotkey, so no second tier"


def test_button_showing_a_later_tier_proves_the_purchase():
    """Rake Impoppable: the bot believed ninja1 1-0-1 (really 2-0-1). The
    click bought tier 3 and the button jumped to Bloonjitsu's $3,300, two
    tiers past what the bot expected; income hid the cash drop, the
    verdict said "same" and the hotkey bought Bloonjitsu as well."""
    g = upgrade_game([], difficulty="impoppable")
    g.cash_stable = scripted([20000, 20400])
    g.path_costs = scripted([[("cash", 420), (None, None), ("cash", 450)],
                             [("cash", 3300), (None, None), ("cash", 450)]])
    p = Placed("ninja1", "ninja", 0.67, 0.79, tiers=[1, 0, 1])
    assert g.upgrade(p, 1) is True and not g.inp.keys


def test_price_above_cash_clicks_nothing():
    g = upgrade_game([("cash", 10260), (None, None), (None, None)], cash=5000)
    p = Placed("sp1", "spike", 0.06, 0.63, tiers=[3, 0, 2])
    assert g.upgrade(p, 1) is False and g.fail_reason == "cash"
    assert g.last_price == 10260 and not path_clicks(g, p) and not g.inp.keys


# -- roster probe ------------------------------------------------------------------------
# -- whose panel is it? (Alpine Run CHIMPS, 2026-11-07) ---------------------------------
def alpine_game(panel, cash=(456,), drops=(None,)):
    """Alpine Run CHIMPS: r1 (boomerang 3-0-2, the panel in
    logs/closed_misread.png) stands at 0.505,0.700; every click near it
    opens `panel`."""
    g = make_game(difficulty="hard", cash=cash, drops=drops, selectable=True)
    g.path_costs = scripted(panel) if isinstance(panel[0], list) else (lambda p, f=None: list(panel))
    g._reread_clear = lambda p: g.path_costs(p)
    g.towers["r1"] = Placed("r1", "boomerang", 0.505, 0.700, tiers=[3, 0, 2])
    return g


R1_PANEL = [("cash", T.upgrade_cost("boomerang", 1, 4, "hard")), (None, None), (None, None)]


def test_placement_is_not_confirmed_by_a_neighbours_panel():
    """08:42:48: r2's cash proof failed ("cash 456 -> 1") and the click at
    its spot opened r1's 3-0-2 panel ($2,160 M.O.A.R. Glaives); r2 was
    recorded although r3's $340 came out of the same $456."""
    assert R1_PANEL[0] == ("cash", 2160)
    g = alpine_game(R1_PANEL)
    assert g.place("r2", "boomerang", 0.473, 0.760) is None
    assert g.fail_reason == "unverified" and "r2" not in g.towers


def test_placement_is_not_confirmed_by_an_upgraded_strangers_panel():
    """A panel asking for a tier past 1 is no new tower's, known neighbour or not."""
    g = alpine_game(R1_PANEL)
    del g.towers["r1"]
    assert g.place("r2", "boomerang", 0.473, 0.760) is None and g.fail_reason == "unverified"


def test_placement_is_not_confirmed_by_a_heros_panel():
    """08:58:54: boomerang1 at 0.350,0.794 was "confirmed" by a panel with no
    price on any path (Quincy's, 0.06 above); its first upgrade then read
    [blank, blank, blank]. A blank panel that does not name the kind is no proof."""
    g = alpine_game([(None, None)] * 3)
    g._panel_names = lambda p: False
    assert g.place("boomerang1", "boomerang", 0.350, 0.794) is None
    assert g.fail_reason == "unverified"
    g = alpine_game([(None, None)] * 3)
    g._panel_names = lambda p: True     # its own title, prices unreadable (free tiers?)
    assert g.place("boomerang1", "boomerang", 0.350, 0.794) is not None


def test_placement_confirmed_by_a_new_towers_panel():
    fresh = [("cash", T.upgrade_cost("boomerang", i, 1, "hard")) for i in (1, 2, 3)]
    g = alpine_game(fresh)
    p = g.place("r2", "boomerang", 0.473, 0.760)
    assert p is not None and g.towers["r2"] is p and p.tiers == [0, 0, 0]


def test_neighbours_panel_does_not_correct_the_tower():
    """08:46:04 "r2 is really 3-0-0, not 0-0-0" and 08:50:07 "r2 is really
    4-0-0" were r1's panel. Now r2 keeps its tiers, nothing is clicked, and
    two such panels in a row count as two failed selections - the executor
    then forgets r2 and places it again (Executor._forget_if_missing)."""
    g = alpine_game(R1_PANEL, cash=(5000,))
    r2 = Placed("r2", "boomerang", 0.473, 0.760)
    g.towers["r2"] = r2
    for n in (1, 2):
        assert g.upgrade(r2, 3) is False and g.fail_reason == "select"
        assert r2.tiers == [0, 0, 0] and not path_clicks(g, r2) and not g.inp.keys
        assert ("r2", 3) not in g.closed and r2.select_fails == n and not r2.verified
    assert g.towers["r1"].tiers == [3, 0, 2]


def test_neighbours_panel_far_away_is_not_blamed():
    """Only a tower within reach of the click can own the panel: a drifted
    count is still corrected when the tower that fits stands across the map."""
    g = alpine_game(R1_PANEL, cash=(5000,))
    g.towers["r1"].x, g.towers["r1"].y = 0.10, 0.10
    r2 = Placed("r2", "boomerang", 0.473, 0.760)
    g.upgrade(r2, 1)
    assert g.fail_reason == "drift" and r2.tiers == [3, 0, 0]


def test_one_missed_tier_stays_the_towers_own():
    """r2 counted 3-0-2 showing $2,160 (tier 4) while r1 3-0-2 sits beside it:
    one missed purchase on r2 explains it as well, so r2's own count wins."""
    g = alpine_game(R1_PANEL, cash=(500,))
    r2 = Placed("r2", "boomerang", 0.473, 0.760, tiers=[2, 0, 2])
    g.upgrade(r2, 1)
    assert g.fail_reason == "drift" and r2.tiers == [3, 0, 2]


def test_blank_other_path_does_not_explain_a_closed_path():
    """08:49:07: r3, counted 0-0-2, read [blank, blank, $1,405]; three blank
    reads of path 2 made it "1-0-2". Path 1 at 1 would be open and show a
    price - it was blank too, so the tiers stay."""
    import btd6bot.game as G
    g = upgrade_game([(None, None), (None, None), ("cash", T.upgrade_cost("boomerang", 3, 3, "hard"))])
    p = Placed("r3", "boomerang", 0.542, 0.811, tiers=[0, 0, 2])
    for _ in range(G.CLOSED_AFTER_MISSES):
        g.upgrade(p, 2)
    assert p.tiers == [0, 0, 2], p.tiers


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



def _pops_read(panel, tiers, kind="boomerang", text="0"):
    """Game._read_pops on a scripted panel: (pops after the read)."""
    g = upgrade_game(panel)
    saved_crop, saved_rec = G.crop, G.rec_text
    G.crop = lambda f, reg: None
    G.rec_text = lambda img: (text, 0.9)
    Game._pops_crop_saved = True
    try:
        p = Placed("r1", kind, 0.5, 0.7)
        p.tiers = list(tiers)
        g._read_pops(p)
        return getattr(p, "pops", None)
    finally:
        G.crop, G.rec_text = saved_crop, saved_rec


def test_a_zero_pop_count_counts_only_from_the_towers_own_panel():
    """Spring Spring CHIMPS (2026-11-07): r1, a 4-0-2 boomerang, read 0 pops
    from a panel that was not its own and lost its Glaive Lord step."""
    glaive_lord = T.upgrade_cost("boomerang", 1, 5, "hard")
    own = [("cash", glaive_lord), (None, None), (None, None)]
    assert _pops_read(own, [4, 0, 2]) == 0, "its own panel: the 0 stands"
    foreign = [("cash", 99999), ("cash", 12345), (None, None)]
    assert _pops_read(foreign, [4, 0, 2]) is None, "a panel that is not its own: count unknown"
    blank = [(None, None)] * 3
    assert _pops_read(blank, [4, 0, 2]) is None, "an unreadable panel proves nothing"
    assert _pops_read(foreign, [4, 0, 2], text="671") == 671, "a count above 0 is read as before"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
