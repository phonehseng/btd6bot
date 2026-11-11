"""The blimp check buys nothing for a later blimp round while the blimp round
being played is rated under 1 by the damage model.

Mesa Impoppable (2026-11-11 10:26-10:46, chimps_ninja_sun; loss case
20261111_104642_Mesa_impoppable): round 78 (72 camo ceramics in 1.2 s behind
a few MOABs) started rated 0.26 with $4,895 and one life. The blimp check
read round 78's own blimps at 7.5x - fine - looked past it, found round 80's
ZOMG at 1.6x of the 2.5x one-life bar and spent $4,556 of that cash on a bare
heli and Ace tiers "toward round 80", then saved the next $11,437 "for blimp
damage before round 80". Reinforcing, which judges purchases on the round in
danger, was left with a few hundred dollars, and round 78 took the one life
with the money in the bank. A ZOMG answer for round 80 is worth nothing if
round 78 ends the game.

That game ran without Executor._held_round_weak (written for Bazaar Half
Cash's round 78 the same morning): a blimp round that passes the blimp sum
but is rated under 1 is reported as it is, and the check does not look past
it. This test holds that rule on the lost game's own board, so the cash of
such a round stays with the plan and with reinforcing.

Offline on Mesa's geometry with the round-78 board of the log's purchase
lines (tools/rate_board.py board_from_log, stop 10:45:42).
Run: python tests/test_ramp_lost_round_first_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from btd6bot import dps_model as D                      # noqa: E402
from btd6bot import mapgeom as G                        # noqa: E402
from btd6bot import strategy as S                       # noqa: E402
from btd6bot import threats as TH                       # noqa: E402
import test_reinforce_budget_offline as SETUP           # noqa: E402  (MapModel, LAYOUTS, SIM)

MAP, MODE, BUILD = "Mesa", "impoppable", "chimps_ninja_sun"
RND, ZOMG_ROUND, CASH = 78, 80, 4_895
BOARD_78 = [
    ("n1", "ninja", "4-0-2", 0.12, 0.794), ("starter", "dart", "0-1-1", 0.569, 0.768),
    ("hero", "hero", "0-0-0", 0.489, 0.504), ("n2", "ninja", "2-0-4", 0.585, 0.513),
    ("a1", "alchemist", "3-2-0", 0.243, 0.836), ("ninja1", "ninja", "2-0-0", 0.58, 0.24),
    ("ninja2", "ninja", "0-0-0", 0.665, 0.129), ("ninja3", "ninja", "2-0-4", 0.59, 0.334),
    ("dart1", "dart", "4-2-0", 0.436, 0.334), ("dart2", "dart", "0-2-4", 0.393, 0.428),
    ("ans_blimps_ace", "ace", "1-3-0", 0.184, 0.751), ("ans_blimps_ace2", "ace", "2-3-0", 0.216, 0.905),
    ("ans_blimps_sniper", "sniper", "4-0-2", 0.339, 0.572), ("v1", "village", "2-0-2", 0.142, 0.862),
    ("s1", "super", "2-0-2", 0.035, 0.683), ("ans_blimps_ace3", "ace", "1-1-0", 0.238, 0.342),
    ("sniper1", "sniper", "2-0-4", 0.548, 0.368), ("dart3", "dart", "0-2-4", 0.516, 0.402),
    ("sniper2", "sniper", "3-2-0", 0.612, 0.385), ("super2", "super", "2-2-0", 0.783, 0.624),
    ("super3", "super", "2-3-0", 0.436, 0.138), ("sniper3", "sniper", "2-2-0", 0.628, 0.334),
    ("ans_blimps_super", "super", "1-2-0", 0.291, 0.845), ("ans_blimps_super2", "super", "0-0-0", 0.307, 0.257),
    ("ans_blimps_sniper2", "sniper", "2-0-3", 0.35, 0.215), ("ans_blimps_sniper3", "sniper", "2-0-3", 0.168, 0.428),
    ("ans_blimps_bomb", "bomb", "0-0-0", 0.377, 0.513), ("ac1", "ace", "0-0-0", 0.323, 0.146),
]


def _setup():
    """The round-78 executor: the board standing, the plan waiting at the
    Sun Avatar step (s1 -> 3-0-2), $4,895 in hand."""
    m = G.apply(SETUP.MapModel(MAP, SETUP.LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SETUP.SIM.CashGame(MODE, "obyn", m)
    g.cash, g.round = CASH, RND
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SETUP.SIM.full_account())
    for tid, kind, cross, x, y in BOARD_78:
        g.towers[tid] = SETUP.SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex.idx = next(i for i, st in enumerate(ex.plan) if st.get("do") == "upgrade" and st.get("id") == "s1")
    ex._init_threats()
    ex.cash_seen = CASH
    return ex


def _ready():
    return D.available() and TH.available()


def test_the_board_reads_as_it_did_live():
    """Round 78 is rated far under 1 (0.26 live) although its own blimps
    pass the blimp sum (7.5x live), and round 80's ZOMG reads short of the
    one-life bar (1.6x live)."""
    if not _ready():
        return
    ex = _setup()
    assert ex.margin_now(RND) < ex.LIKELY_LOST, ex.margin_now(RND)
    now, zomg = ex.blimp_load(RND), ex.blimp_load(ZOMG_ROUND)
    assert ex.blimp_ratio(now) >= ex.ramp_bar(now), ex.blimp_ratio(now)
    assert ex.blimp_ratio(zomg) < ex.ramp_bar(zomg), ex.blimp_ratio(zomg)
    print(f"round {RND} rated {ex.margin_now(RND):.2f}, its blimps {ex.blimp_ratio(now):.1f}x; "
          f"round {ZOMG_ROUND} reads {ex.blimp_ratio(zomg):.1f}x")


def test_the_blimp_check_does_not_look_past_the_round_in_danger():
    """The blimp check reports round 78, not the short round 80 behind it."""
    if not _ready():
        return
    ex = _setup()
    ramp = ex._ramp_due(RND)
    assert ramp and ramp[0] == RND, ramp and ramp[0]


def test_the_cash_stays_for_the_round_in_danger():
    """The threat tick neither buys for round 80 nor holds cash for it: the
    $4,895 is left to what reinforcing finds for round 78."""
    if not _ready():
        return
    ex = _setup()
    ex.saving_for_threat = False
    assert ex._threat_tick(CASH, RND) is None
    assert not ex.g.bought, ex.g.bought
    assert not ex.saving_for_threat and not getattr(ex, "held_cash", 0.0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
