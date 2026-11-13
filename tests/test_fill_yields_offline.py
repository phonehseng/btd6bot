"""The fill gives way to reinforce while a round ahead is rated under 1.0.

Ravine Double HP (2026-11-12 22:10, hard_ninja_alch_sun, loss case
20261112_222133_Ravine_double_hp): from round 55 the damage model rated
round 64 (six MOABs and three fortified MOABs at double HP) at 0.53-0.59.
The plan was done at round 57; the fill (ninjas near the village, to
4-0-2; a spike factory) ran before reinforce on every tick and spent $11.8k
in rounds 57-62 on towers that moved round 64 by 0.00-0.02. Round 64 took
all 100 lives. Executor._fill_yields now lets the fill wait while the
look-ahead holds a round under FILL_YIELD_MARGIN, in a live game (Match
sets reinforce_live), so the match's reinforce picks for that round.

Run: python tests/test_fill_yields_offline.py"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from btd6bot import strategy as S  # noqa: E402

import simulate_threats as SIM  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

PLAN = [{"do": "place", "id": "n1", "kind": "ninja", "role": "dps"}]
FILL = [{"do": "place", "kind": "ninja", "role": "dps", "max": 5}]


def executor(worst, live=True):
    g = SIM.CashGame(S.PRICE_FAMILY.get("double_hp", "hard"))
    strat = {"id": "t", "hero": "quincy", "plan": PLAN, "fill": FILL, "modes": ["double_hp"]}
    ex = S.Executor(g, SIM.OpenModel(), strat, "double_hp", SIM.full_account())
    ex.lookahead_worst = lambda rnd: worst
    ex._threat_tick = lambda cash, rnd: None     # the threat answers are not under test
    if live:
        ex.reinforce_live = True
    g.cash = 100000
    return g, ex


def _ninjas(g):
    return sum(1 for p in g.towers.values() if p.kind == "ninja")


def _run(g, ex, ticks=20):
    for _ in range(ticks):
        ex.tick(g.cash, 57)


def test_the_fill_waits_while_a_round_ahead_is_rated_under_one():
    g, ex = executor((0.53, 64))
    _run(g, ex)
    assert _ninjas(g) == 1, g.towers          # the plan's n1 only
    assert ex.waiting.startswith("fill yields to reinforce"), ex.waiting
    assert "round 64" in ex.waiting


def test_the_fill_buys_when_the_look_ahead_holds():
    g, ex = executor((1.3, 64))
    _run(g, ex)
    assert _ninjas(g) > 1, g.towers


def test_the_fill_buys_without_a_rating():
    g, ex = executor(None)
    _run(g, ex)
    assert _ninjas(g) > 1, g.towers


def test_offline_replays_keep_the_fill():
    # no reinforce runs after an offline tick (tools/simulate_threats)
    g, ex = executor((0.53, 64), live=False)
    _run(g, ex)
    assert _ninjas(g) > 1, g.towers


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
