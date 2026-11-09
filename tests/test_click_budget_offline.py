"""Purchases under a click budget (btd6bot/clicktime.py): Apopalypse's rounds
never wait, a purchase takes about one of them, so a large bank is spent by
the seconds each purchase takes, not by its price.

Mesa Apopalypse (2026-11-09, lost at round 59): from round 44 the bank went
$7.7k -> $17.4k while the bot bought $300-$450 single tiers one a round - n3
placed and grown 0-0-1, 1-0-1, 2-0-1 ... tier by tier ahead of n2's $5,000
Sticky Bomb (one click), and reinforce ranking purchases per dollar.

Checked offline, with fakes:
  * clicktime prices a purchase in seconds: a placement, a first tier, and
    tiers bought from a panel left open (cheaper), in runs of
    CHAIN_MAX_TIERS; the running mean of measured clicks; a round's time;
  * reinforce.worth: per dollar where rounds wait for the bot (unchanged),
    per share of cash and seconds under a click budget - with a large bank
    one big tier on a standing tower beats a tower grown tier by tier, and
    with no budget the cheap per-dollar pick stays;
  * reinforce.best picks the other purchase only in a time-limited mode;
  * Executor.try_step buys the next tiers of a path from the panel it keeps
    open (Game.hold_panel) - several tiers in one tick - and closes it after;
    in other modes one tier a tick as before;
  * Executor._quicker_step: with a bank that pays for both, a one-click
    upgrade of a standing tower further on in the plan comes before a
    placement that needs seven clicks; with less cash, in other modes, or
    when the model sees no gain, the plan keeps its order;
  * Game.select reuses a held panel without clicking;
  * tools/simulate_threats.py's click model charges what clicktime says.
Run: python tests/test_click_budget_offline.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import clicktime as CT        # noqa: E402
from btd6bot import reinforce as R         # noqa: E402
from btd6bot import strategy as S          # noqa: E402
from btd6bot.game import Game, Placed      # noqa: E402
import simulate_threats as SIM             # noqa: E402

APOP = N(rules=S.rules("apopalypse"))
MEDIUM = N(rules=S.rules("medium"))


# -- clicktime --------------------------------------------------------------------
def test_seconds_of_a_purchase():
    ex = N(rules=APOP.rules)
    m = CT._measured(ex)
    one = m["upgrade"] + CT.LOOP_S
    assert CT.seconds(ex, 0, [1]) == one
    # tiers from an open panel cost less than separate ones
    assert CT.seconds(ex, 0, [3]) == one + 2 * m["chained"] < 3 * one
    # a long path is bought in runs: each run opens the panel anew
    runs = -(-6 // CT.CHAIN_MAX_TIERS)
    assert abs(CT.seconds(ex, 0, [6]) - (runs * one + (6 - runs) * m["chained"])) < 1e-9
    assert CT.seconds(ex, 1, [0]) == m["place"] + CT.LOOP_S
    # a board change: one placement grown to 4-0-2 and one tier elsewhere
    now = [N(tid="n2", tiers=(2, 0, 3))]
    after = [N(tid="n2", tiers=(2, 0, 4)), N(tid="n3", tiers=(4, 0, 2))]
    assert CT.board_seconds(ex, now, after) == CT.seconds(ex, 1, [1, 6])


def test_measured_clicks_move_the_mean():
    ex = N(rules=APOP.rules)
    CT.note(ex, "upgrade", 3.0)
    assert CT.UPGRADE_S < ex.click_seconds["upgrade"] < 3.0
    before = dict(ex.click_seconds)
    CT.note(ex, "upgrade", 0.01)       # no real purchase is that quick
    CT.note(ex, "upgrade", 60.0)       # a popup, not a click
    assert ex.click_seconds == before


def test_time_left_only_under_continuous_sends():
    assert CT.time_left(MEDIUM, 40, 45) is None
    ex = N(rules=APOP.rules)
    assert CT.time_left(ex, 40, 40) == CT.ROUND_S            # the round being played
    ex.round_seconds = 3.0
    assert CT.time_left(ex, 40, 42) == 9.0
    CT.ENABLED = False
    try:
        assert CT.time_left(ex, 40, 42) is None and not CT.time_limited(ex)
    finally:
        CT.ENABLED = True


# -- reinforce: what a purchase is worth --------------------------------------------
def options():
    """Round 45 of Mesa: n2's Sticky Bomb (one click, $5,000) against a fresh
    ninja grown to 4-0-2 (a placement and six tiers, $5,400) and a $350 tier."""
    now = [N(tid="n2", kind="ninja", tiers=(2, 0, 3), x=0.4, y=0.4)]
    sticky = R.Option("upgrade n2 -> 2-0-4", 5000, {"do": "upgrade", "id": "n2", "to": "2-0-4"},
                      [N(tid="n2", kind="ninja", tiers=(2, 0, 4), x=0.4, y=0.4)])
    fresh = R.Option("another ninja (to grow to 4-0-2)", 5400, {"do": "place", "kind": "ninja"},
                     now + [N(tid="_new_ninja", kind="ninja", tiers=(4, 0, 2), x=0.5, y=0.5)])
    tier = R.Option("upgrade n2 -> 2-1-3", 350, {"do": "upgrade", "id": "n2", "to": "2-1-3"},
                    [N(tid="n2", kind="ninja", tiers=(2, 1, 3), x=0.4, y=0.4)])
    return now, sticky, fresh, tier


def test_worth_per_dollar_without_a_click_budget():
    now, sticky, fresh, tier = options()
    # lives saved: the fresh ninja most, the cheap tier best per dollar
    saved = {sticky.what: 20.0, fresh.what: 30.0, tier.what: 3.0}
    ex = N(rules=MEDIUM.rules)
    w = {o.what: R.worth(ex, o, saved[o.what], 14_000, None, False, now) for o in (sticky, fresh, tier)}
    assert max(w, key=w.get) == tier.what
    # crisis: the most lives
    w = {o.what: R.worth(ex, o, saved[o.what], 14_000, None, True, now) for o in (sticky, fresh, tier)}
    assert max(w, key=w.get) == fresh.what


def test_worth_per_second_with_a_large_bank():
    now, sticky, fresh, tier = options()
    saved = {sticky.what: 20.0, fresh.what: 30.0, tier.what: 3.0}
    ex = N(rules=APOP.rules)
    budget = CT.time_left(ex, 45, 46)                    # two rounds: about 8 s
    w = {o.what: R.worth(ex, o, saved[o.what], 14_000, budget, False, now) for o in (sticky, fresh, tier)}
    assert max(w, key=w.get) == sticky.what, w
    # in a crisis the dollars still do not count, but seven clicks do not fit in 8 s
    w = {o.what: R.worth(ex, o, saved[o.what], 14_000, budget, True, now) for o in (sticky, fresh, tier)}
    assert max(w, key=w.get) == sticky.what, w
    # with plenty of time (the round judged is far off) the fresh tower's lives count again
    far = CT.time_left(ex, 45, 54)
    w = {o.what: R.worth(ex, o, saved[o.what], 14_000, far, True, now) for o in (sticky, fresh, tier)}
    assert max(w, key=w.get) == fresh.what, w


def test_worth_with_little_cash_is_about_dollars():
    now, sticky, fresh, tier = options()
    ex = N(rules=APOP.rules)
    budget = 10 * CT.ROUND_S                               # time is plentiful here
    # $5,100 in hand: the $5,000 tier takes nearly all of it, the $350 one hardly any
    cheap = R.worth(ex, tier, 3.0, 5_100, budget, False, now)
    dear = R.worth(ex, sticky, 20.0, 5_100, budget, False, now)
    roomy_cheap = R.worth(ex, tier, 3.0, 50_000, budget, False, now)
    roomy_dear = R.worth(ex, sticky, 20.0, 50_000, budget, False, now)
    # the dear tier gains more from a larger bank than the cheap one does
    assert roomy_dear / dear > roomy_cheap / cheap


class Toy:
    """A damage model: every round loses lives in proportion to what the
    board lacks; n2's Sticky Bomb (path 3 tier 4) is worth 20 lives a round,
    each ninja tier on a fresh tower 4, round 45 the weakest."""

    def leaks(self, towers, rounds, scale, per_round=False):
        def lost(r):
            gain = sum(20.0 if (t.tid == "n2" and t.tiers[2] >= 4) else 0.0 for t in towers)
            gain += sum(4.0 * sum(t.tiers) for t in towers if t.tid != "n2")
            return max(0.0, 100.0 - gain + (5.0 if r == 45 else 0.0)) * scale
        out = {r: lost(r) for r in rounds}
        return out if per_round else sum(out.values())

    def margin(self, towers, rnd):
        return 1.2 + 0.01 * sum(sum(t.tiers) for t in towers)


class ToyEx:
    """A board of n2 (ninja 2-0-3) with two purchases: the Sticky Bomb, and a
    fresh ninja the look grows to 4-0-2; no plan, no goal."""

    def __init__(self, mode):
        self.mode, self.rules = mode, S.rules(mode)
        self.g = N(towers={"n2": N(tid="n2", kind="ninja", tiers=[2, 0, 3], x=0.4, y=0.4)},
                   price=lambda kind: 400)
        self.m = N(cell_to_frac=lambda cx, cy: (0.5, 0.5))

    def upgrade_choices(self, first=None, past_plan=False):
        yield self.g.towers["n2"], [2, 0, 4], 5000

    def at_tower_cap(self):
        return False

    def _main_kind(self):
        return "ninja"

    def kind_allowed(self, kind):
        return kind == "ninja"

    def pick_spots(self, kind, step, n=1):
        return [(5, 5, 1.0)]


def test_best_switches_only_under_a_click_budget():
    for mode, want in (("medium", "another ninja"), ("apopalypse", "upgrade n2 -> 2-0-4")):
        ex = ToyEx(mode)
        status, found = R.best(ex, Toy(), 14_000, 45, 60)
        assert status == "buy", (mode, status)
        assert found[0].what.startswith(want), (mode, found[0].what)


# -- the executor: tiers from one open panel ---------------------------------------
def executor(mode, plan, cash, towers=()):
    g = SIM.CashGame(S.PRICE_FAMILY[mode])
    g.cash = cash
    for tid, kind, tiers in towers:
        g.towers[tid] = Placed(tid, kind, 0.3 + 0.05 * len(g.towers), 0.3, list(tiers))
    ex = S.Executor(g, SIM.OpenModel(), {"id": "t", "modes": [mode], "plan": plan, "answers": {}}, mode,
                    SIM.full_account())
    ex._threat_tick = lambda cash, rnd: None       # the threat checks are not under test here
    ex.plan = [dict(s) for s in plan]               # no opener
    return g, ex


def test_a_path_is_bought_from_one_open_panel():
    plan = [{"do": "upgrade", "id": "n1", "to": "4-0-2"}]
    g, ex = executor("apopalypse", plan, 20_000, [("n1", "ninja", (0, 0, 0))])
    assert ex.tick(g.cash, 45)
    # one tick: a first tier and CHAIN_MAX_TIERS - 1 more from the open panel
    assert sum(g.towers["n1"].tiers) == CT.CHAIN_MAX_TIERS
    assert g.hold_panel is None                     # closed after the run
    assert abs(g.clock - CT.seconds(None, 0, [CT.CHAIN_MAX_TIERS])) < 1e-9
    assert ex.tick(g.cash, 45) and g.towers["n1"].tiers == [4, 0, 2]
    # elsewhere: one tier a tick, as before
    g, ex = executor("medium", plan, 20_000, [("n1", "ninja", (0, 0, 0))])
    assert ex.tick(g.cash, 45) and sum(g.towers["n1"].tiers) == 1
    assert g.clock == CT.seconds(None, 0, [1])


def test_a_run_stops_where_the_cash_does():
    plan = [{"do": "upgrade", "id": "n1", "to": "4-0-2"}]
    family = S.PRICE_FAMILY["apopalypse"]
    from btd6bot import towers as T
    # the two cheapest tiers on the way (total_cost counts the tower too)
    cash = T.total_cost("ninja", (1, 0, 1), family) - T.total_cost("ninja", (0, 0, 0), family) + 1
    g, ex = executor("apopalypse", plan, cash, [("n1", "ninja", (0, 0, 0))])
    assert ex.tick(g.cash, 45)
    assert g.towers["n1"].tiers == [1, 0, 1] and g.hold_panel is None
    assert ex._next_path(g.towers["n1"], [4, 0, 2])[1] > g.cash


# -- the executor: a quicker plan step first ----------------------------------------
MESA_PLAN = [{"do": "place", "id": "n3", "kind": "ninja", "role": "dps", "segment": [0.5, 1.0]},
             {"do": "upgrade", "id": "n3", "to": "4-0-2"},
             {"do": "upgrade", "id": "n2", "to": "2-0-4"}]


class ToyForecast(Toy):
    def worst(self, towers, rounds, iterations=9):
        return min((self.margin(towers, r), r) for r in rounds) if rounds else None


def test_a_one_click_step_comes_before_a_seven_click_one():
    g, ex = executor("apopalypse", MESA_PLAN, 14_000, [("n2", "ninja", (2, 0, 3))])
    ex.forecast = ToyForecast()
    ex.round_seconds = 4.0
    j, why = ex._quicker_step(14_000, 45)
    assert j == 2 and "n2" in why, why
    assert ex.tick(g.cash, 45)
    assert g.towers["n2"].tiers == [2, 0, 4] and "n3" not in g.towers
    # the plan goes on in its order, and reaches n2's step as done
    while ex.tick(g.cash, 45):
        pass
    assert g.towers["n3"].tiers == [4, 0, 2] and ex.idx == len(ex.plan)


def test_the_plan_keeps_its_order_otherwise():
    # another mode: rounds wait for the bot
    g, ex = executor("medium", MESA_PLAN, 14_000, [("n2", "ninja", (2, 0, 3))])
    ex.forecast = ToyForecast()
    assert ex.tick(g.cash, 45) and "n3" in g.towers and g.towers["n2"].tiers == [2, 0, 3]
    # the cash does not pay for n2's step
    g, ex = executor("apopalypse", MESA_PLAN, 4_000, [("n2", "ninja", (2, 0, 3))])
    ex.forecast = ToyForecast()
    assert ex._quicker_step(4_000, 45) is None
    # it does, but not n3's steps as well: n2 would take cash n3 needs
    g, ex = executor("apopalypse", MESA_PLAN, 7_000, [("n2", "ninja", (2, 0, 3))])
    ex.forecast = ToyForecast()
    assert ex._quicker_step(7_000, 45) is None
    # the model sees nothing leak: no reason to change the order
    g, ex = executor("apopalypse", MESA_PLAN, 14_000, [("n2", "ninja", (2, 0, 3))])
    ex.forecast = N(leaks=lambda towers, rounds, scale, per_round=False: 0.0,
                    worst=lambda towers, rounds, iterations=9: (3.0, rounds[0]))
    assert ex._quicker_step(14_000, 45) is None


# -- the game: a held panel is not clicked again -------------------------------------
def test_select_reuses_a_held_panel():
    g = Game.__new__(Game)
    clicks = []
    g.inp = N(click=lambda x, y: clicks.append((x, y)))
    g.screen_ok = lambda: True
    g.panel_open = lambda p, f=None: True
    g.is_holding = lambda f=None: False
    p = N(tid="n1", x=0.5, y=0.5)
    g.hold_panel = "n1"
    assert g.select(p) and clicks == []
    g.hold_panel = None
    g._open_side = lambda f=None: "upg_left"
    g._read_pops = lambda p: None
    assert g.select(p) and len(clicks) == 1


if __name__ == "__main__":
    import inspect
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
            print("ok", name)
