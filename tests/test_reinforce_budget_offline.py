"""A reinforce look, and the surplus rating after it, keep to their time
budget (reinforce.LOOK_BUDGET_S) on a large late-game board, and still
choose what an unbounded look chooses.

X Factor Impoppable (2026-11-10 20:18-21:13, chimps_ninja_sun, one life;
journal logs/journal/20261110_201801_XFactor_impoppable.jsonl) took 55.5
minutes, 73 of them stalls of the match loop of 16-77 s ("match loop was
held up N s (M s of it in reinforce)", ~2,500 s in all); "the 6 s look
budget ran out while rating growth paths" was logged 28 times, yet the
looks ran on for 16-48 s. Offline on the round-85 board below (37 towers,
$10,067), one look took 21-37 s: the budget only bounded grow(), and the
purchases' leak ratings (10 s), strongest() (14 s) and
plan_claim_in_crisis() after it ran unbounded. One-life surplus (06317a3)
then asked up to six margins per affordable upgrade (126 for one call,
105 s offline); the live game had 24 stalls "in surplus" from 17:13.

Now every stage of a look stops at the budget and the look answers "busy";
the forecast remembers its ratings (forecast._memo), so the next look goes
on where the last stopped and finally picks what an unbounded look picks.

Offline on X Factor's game geometry (data/map_geometry), towers at the spots
the journal recorded. Slow (about two minutes): every rating that late is
0.3-0.7 s.
Run: python tests/test_reinforce_budget_offline.py"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import dps_model as D           # noqa: E402
from btd6bot import mapgeom as G             # noqa: E402
from btd6bot import reinforce as R           # noqa: E402
from btd6bot import strategy as S            # noqa: E402
from btd6bot.forecast import RoundForecast   # noqa: E402
from btd6bot.layout import LAYOUTS           # noqa: E402
from btd6bot.maplearn import MapModel        # noqa: E402

MAP, MODE, RND, CASH, END = "X Factor", "impoppable", 85, 10_067, 100
# One rating cannot be interrupted: a late leak count over the look-ahead,
# or a surplus option's three margins, takes up to 2-3 s. A look stops at
# the first check past its budget.
SLACK_S = 3.0
# the round-85 board of the live game: (tid, kind, crosspath, x, y)
BOARD = [
    ("n1", "ninja", "4-0-2", 0.2592, 0.1806),
    ("hero", "hero", "0-0-0", 0.147, 0.7598),
    ("n2", "ninja", "2-0-4", 0.5905, 0.1635),
    ("a1", "alchemist", "3-2-0", 0.3821, 0.1976),
    ("v1", "village", "2-0-2", 0.3073, 0.1976),
    ("ans_blimps_ace", "ace", "4-2-0", 0.179, 0.5213),
    ("ace2", "ace", "4-0-1", 0.7294, 0.5213),
    ("ace3", "ace", "2-3-0", 0.6065, 0.5213),
    ("ace4", "ace", "2-3-0", 0.35, 0.8024),
    ("ace5", "ace", "2-3-0", 0.6974, 0.4276),
    ("s1", "super", "2-0-2", 0.3393, 0.1124),
    ("ace6", "ace", "2-0-3", 0.1309, 0.4446),
    ("ace7", "ace", "2-0-3", 0.1309, 0.598),
    ("super2", "super", "0-2-3", 0.7187, 0.7172),
    ("ninja1", "ninja", "2-0-2", 0.6012, 0.8791),
    ("ace8", "ace", "4-1-0", 0.5157, 0.8961),
    ("super3", "super", "0-1-0", 0.2699, 0.8961),
    ("ace9", "ace", "4-0-1", 0.6867, 0.6065),
    ("ace10", "ace", "4-1-0", 0.4622, 0.2317),
    ("ace11", "ace", "2-0-3", 0.7294, 0.3339),
    ("ace12", "ace", "4-1-0", 0.4462, 0.1209),
    ("super4", "super", "2-2-0", 0.2164, 0.615),
    ("ninja2", "ninja", "3-2-0", 0.5745, 0.8365),
    ("ace13", "ace", "0-2-1", 0.1095, 0.3424),
    ("ninja3", "ninja", "4-0-2", 0.5531, 0.1976),
    ("ninja4", "ninja", "3-2-0", 0.163, 0.6746),
    ("ninja5", "ninja", "0-2-4", 0.5798, 0.1124),
    ("ace14", "ace", "0-2-3", 0.0347, 0.828),
    ("ninja6", "ninja", "4-0-2", 0.1095, 0.7428),
    ("ninja7", "ninja", "1-0-0", 0.6546, 0.368),
    ("ans_blimps_sniper", "sniper", "0-2-4", 0.2752, 0.4957),
    ("sniper1", "sniper", "0-2-3", 0.5851, 0.4446),
    ("sniper2", "sniper", "0-2-2", 0.6706, 0.5213),
    ("sniper3", "sniper", "0-2-2", 0.2485, 0.5298),
    ("sniper4", "sniper", "3-2-0", 0.1042, 0.5128),
    ("sniper5", "sniper", "0-2-3", 0.7668, 0.4617),
    ("sniper6", "sniper", "0-2-4", 0.3981, 0.2657),
]
PLAN_STEP = 16       # the live game waited on plan step 16 (s1 -> 3-0-2, $24,000) from round 80


def _setup():
    """(executor, forecast) for the round-85 board, the forecast's track
    loaded (as in the live game, where the match rated rounds before)."""
    m = G.apply(MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SIM.CashGame(MODE, "obyn", m)
    g.cash = CASH
    ex = S.Executor(g, m, S.load_all()["chimps_ninja_sun"], MODE, SIM.full_account())
    for tid, kind, cross, x, y in BOARD:
        g.towers[tid] = SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = PLAN_STEP
    fc = RoundForecast(MAP, MODE, getattr(m, "sight", None),
                       (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    fc.margin(R.board(ex), RND)
    return ex, fc


def _answer(status, found):
    return status, (found[0].what if found else None)


def _unbounded(fn):
    saved = R.LOOK_BUDGET_S
    R.LOOK_BUDGET_S = 1e9
    try:
        return fn()
    finally:
        R.LOOK_BUDGET_S = saved


def test_a_late_look_keeps_to_its_budget_and_chooses_as_an_unbounded_one():
    if not D.available():
        return
    ex, fc = _setup()
    t0 = time.monotonic()
    want = _unbounded(lambda: _answer(*R.best(ex, fc, CASH, RND, END, lives=1)))
    unbounded_s = time.monotonic() - t0
    assert want[0] == "buy", want
    assert unbounded_s > R.LOOK_BUDGET_S + SLACK_S, f"the case needs the budget ({unbounded_s:.1f} s)"

    ex, fc = _setup()          # a fresh forecast: nothing remembered
    looks = []
    for _ in range(12):
        t0 = time.monotonic()
        got = _answer(*R.best(ex, fc, CASH, RND, END, lives=1))
        looks.append(time.monotonic() - t0)
        assert looks[-1] <= R.LOOK_BUDGET_S + SLACK_S, (looks, got)
        if got[0] != "busy":
            break
    assert len(looks) > 1, looks
    assert got == want, (got, want, looks)
    # the board unchanged, the next look is answered from what was rated
    t0 = time.monotonic()
    again = _answer(*R.best(ex, fc, CASH, RND, END, lives=1))
    assert again == want and time.monotonic() - t0 < 1.0, (again, time.monotonic() - t0)
    print(f"unbounded {unbounded_s:.1f} s; bounded looks {', '.join(f'{s:.1f}' for s in looks)} s")


def test_one_life_surplus_keeps_to_its_budget():
    if not D.available():
        return
    ex, fc = _setup()
    ex.forecast = fc              # Match hands its forecast to the executor
    ex.lookahead_weak = True
    # the match rates the look-ahead at the start of every round (_rate_ahead)
    fc.margins(list(ex.g.towers.values()), R.lookahead_rounds(RND, END))
    calls = []
    for _ in range(15):
        t0 = time.monotonic()
        bought = ex.surplus(CASH, RND)
        calls.append(time.monotonic() - t0)
        assert calls[-1] <= R.LOOK_BUDGET_S + SLACK_S, calls
        if bought or calls[-1] < 0.5:
            break
    assert len(calls) > 1 and calls[-1] < 0.5, calls
    # once everything is rated an unbounded call answers the same at once
    t0 = time.monotonic()
    assert _unbounded(lambda: ex.surplus(CASH, RND)) == bought
    assert time.monotonic() - t0 < 1.0
    print(f"surplus calls {', '.join(f'{s:.1f}' for s in calls)} s")


def test_a_look_with_no_time_still_gets_there():
    """A look whose budget is gone before it starts still rates one new
    thing (LookBudget: no cut before progress), so the looks never stall
    and - never made to settle - end where an unbounded look does. Made to
    settle (MAX_BUSY_LOOKS), the same looks answer on pass MAX_BUSY_LOOKS + 1.
    Pat's Pond Hard, the weak board of test_reinforce_offline."""
    if not D.available():
        return
    from test_reinforce_offline import Ex, forecast, weak_board
    ex = Ex(weak_board())
    want = _unbounded(lambda: _answer(*R.best(ex, forecast(ex), 5000, 40, 80)))
    saved = R.LOOK_BUDGET_S, R.MAX_BUSY_LOOKS
    try:
        R.LOOK_BUDGET_S = 0.0
        R.MAX_BUSY_LOOKS = 10 ** 6         # never settle: the memo alone gets there
        fc = forecast(ex)
        for n in range(1, 400):
            got = _answer(*R.best(ex, fc, 5000, 40, 80))
            if got[0] != "busy":
                break
        assert n > 1 and got == want, (n, got, want)
        R.MAX_BUSY_LOOKS = saved[1]
        fc = forecast(ex)
        for n in range(1, 400):
            got = _answer(*R.best(ex, fc, 5000, 40, 80))
            if got[0] != "busy":
                break
        assert n <= R.MAX_BUSY_LOOKS + 1 and got[0] in ("buy", "wait", "save"), (n, got)
    finally:
        R.LOOK_BUDGET_S, R.MAX_BUSY_LOOKS = saved


# Water Park Impoppable (2026-11-11 02:26:38, round 88; journal
# logs/journal/20261111_020150_WaterPark_impoppable.jsonl, strategy
# chimps_sub_druid_water): the board as the log's purchase lines leave it
# (tools/rate_board.py board_from_log). From 02:26:47 to 02:27:54 ten looks
# in a row answered "busy" (nine "while rating growth paths") while the bank
# grew from $7,934 to $19,583, and none chose anything; the game was lost
# on round 91.
WP_MAP, WP_RND, WP_CASH, WP_INCOME_PER_PASS = "Water Park", 88, 7_934, 1_600
WP_BOARD = [
    ("sb1", "sub", "2-0-4", 0.676, 0.47), ("dr", "dart", "0-2-4", 0.216, 0.232),
    ("sb2", "sub", "2-0-4", 0.291, 0.896), ("hero", "hero", "0-0-0", 0.083, 0.428),
    ("druid1", "druid", "0-1-1", 0.355, 0.845), ("sub1", "sub", "0-2-1", 0.419, 0.913),
    ("dart2", "dart", "2-0-5", 0.532, 0.589), ("a1", "alchemist", "4-2-0", 0.377, 0.47),
    ("druid2", "druid", "2-0-4", 0.778, 0.649), ("druid3", "druid", "2-0-4", 0.617, 0.462),
    ("dr2", "dart", "2-0-4", 0.489, 0.589), ("ans_blimps_ace", "ace", "3-2-0", 0.355, 0.394),
    ("d3", "druid", "2-0-4", 0.745, 0.3), ("v1", "village", "2-3-0", 0.708, 0.913),
    ("bm1", "bomb", "2-0-3", 0.676, 0.836), ("sp1", "spike", "2-0-5", 0.532, 0.428),
    ("d4", "druid", "2-0-4", 0.585, 0.419), ("d5", "druid", "0-0-0", 0.473, 0.436),
    ("d6", "druid", "0-0-0", 0.19, 0.726), ("ace1", "ace", "3-1-0", 0.478, 0.351),
    ("druid5", "druid", "0-3-2", 0.82, 0.453), ("druid6", "druid", "0-3-2", 0.265, 0.462),
    ("a2", "alchemist", "4-2-0", 0.558, 0.376), ("sub2", "sub", "2-0-4", 0.665, 0.172),
    ("sub3", "sub", "2-0-4", 0.772, 0.394), ("spike1", "spike", "2-0-4", 0.088, 0.521),
    ("spike2", "spike", "2-0-4", 0.623, 0.922), ("ans_blimps_sniper", "sniper", "5-0-0", 0.457, 0.274),
]


def water_park_setup(board=WP_BOARD, rnd=WP_RND, cash=WP_CASH):
    """(executor, forecast) for a Water Park Impoppable board with the
    plan used up, the forecast's track loaded."""
    m = G.apply(MapModel(WP_MAP, LAYOUTS["16:10"]["playfield"]), G.load(WP_MAP))
    g = SIM.CashGame("impoppable", "obyn", m)
    g.cash = cash
    g.round = rnd
    ex = S.Executor(g, m, S.load_all()["chimps_sub_druid_water"], "impoppable", SIM.full_account())
    for tid, kind, cross, x, y in board:
        g.towers[tid] = SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = len(ex.plan)
    fc = RoundForecast(WP_MAP, "impoppable", getattr(m, "sight", None),
                       (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    fc.margin(R.board(ex), rnd)
    return ex, fc


def test_a_late_look_finishes_while_the_bank_grows():
    """Looks on the round-88 Water Park board, $1,600 more in the bank at
    every pass, answer within MAX_BUSY_LOOKS + 1 passes, each within its
    budget. Before, every pass rated the growth paths of its own cash (new
    boards each time), and ten passes in a row offline answered "busy" as
    in the live game."""
    if not D.available():
        return
    ex, fc = water_park_setup()
    cash, looks = WP_CASH, []
    for _ in range(12):
        t0 = time.monotonic()
        status, found = R.best(ex, fc, cash, WP_RND, END, lives=1)
        looks.append(time.monotonic() - t0)
        assert looks[-1] <= R.LOOK_BUDGET_S + SLACK_S, looks
        if status != "busy":
            break
        assert ex.look_pin.cash == WP_CASH, ex.look_pin       # the look keeps its cash
        cash += WP_INCOME_PER_PASS
    assert status == "buy", (status, looks)
    assert len(looks) <= R.MAX_BUSY_LOOKS + 1, looks
    assert found[0].cost <= WP_CASH, found[0]
    assert ex.look_pin is None                                # done: the next look starts afresh
    print(f"Water Park round 88: {found[0].what} after {len(looks)} passes "
          f"({', '.join(f'{s:.1f}' for s in looks)} s)")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
