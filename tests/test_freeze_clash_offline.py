"""Freezing maps: a new tower is not bought into the round that freezes it
together with most of the defence.

Glacial Trail Reverse (2026-11-11 17:15-17:20, glacialtrail_medium, lost
round 45, loss case 20261111_172115_GlacialTrail_reverse): every tower on the
map sits in ice for two rounds in ten, counted from the round it was bought
in (dps_model.frozen_in). The Spike Factory and the first druid were bought
in round 15 (frozen 44-45), the second druid in round 17 (frozen 46-47). The
plan reached the heli in round 36, so the heli was frozen in 45-46: round 45
was left to one Druid of the Jungle and cost the last 142 lives. The Medium
game won with the same build (2026-11-10 19:43) bought the heli in round 37.

Checked on that board (Executor._freeze_clash):
  * in round 36 the heli is held, in round 37 it is bought;
  * in round 35 it is held too, and after two rounds of waiting it is let go;
  * the Fast Track opening is not held: the Spike Factory is still bought in
    the round of the first druid, as the build plans it;
  * on a map without a freeze nothing is ever held.
Run: python tests/test_freeze_clash_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import strategy as S            # noqa: E402

HELI = {"do": "place", "id": "h1", "kind": "heli", "role": "dps", "at": [0.767, 0.112]}
HELI_PRICE = 1500
# the board of the lost game at round 36: (id, kind, spot, round bought, cash in it)
BOARD = (("dr1", "druid", (0.158, 0.879), 15, 2050),
         ("sp1", "spike", (0.719, 0.649), 15, 12550),
         ("dr2", "druid", (0.729, 0.274), 17, 2050))


def _executor(map_name="Glacial Trail", board=BOARD):
    m = SIM.map_model(map_name, learned=False)
    g = SIM.CashGame("medium", "quincy", m)
    ex = S.Executor(g, m, S.load_all()["glacialtrail_medium"], "medium", SIM.full_account())
    for tid, kind, (x, y), bought, spent in board:
        p = SIM.Placed(tid, kind, x, y)
        p.placed_round, p.spent = bought, spent
        g.towers[tid] = p
    return ex


def _held(ex, rnd, step=HELI, price=HELI_PRICE):
    ex.now_round = rnd
    return ex._freeze_clash(step, step["kind"], price)


def test_heli_waits_for_the_round_that_freezes_it_apart():
    ex = _executor()
    assert ex._awake_share(36) < 0.2, "round 45: only dr2 is awake"
    assert ex._awake_share(37) > 0.8, "rounds 46-47: sp1 and dr1 are awake"
    assert _held(ex, 36), "bought in 36 it is frozen in round 45 with sp1 and dr1"
    assert not _held(ex, 37), "bought in 37 it is frozen with dr2 only"


def test_a_hold_ends_after_the_freeze_length():
    ex = _executor()
    assert _held(ex, 35) and _held(ex, 36)
    assert not _held(ex, 37)
    # and a step is never held longer, whatever the board says then
    ex = _executor()
    assert _held(ex, 35)
    for p in ex.g.towers.values():
        p.placed_round = 15 if p.tid != "dr2" else 18     # make round 37 look bad too
    assert not _held(ex, 37), "two rounds waited: the tower is bought"


def test_the_opening_is_bought_together():
    ex = _executor(board=BOARD[:1])
    spike = {"do": "place", "id": "sp1", "kind": "spike", "role": "dps", "at": [0.719, 0.649]}
    assert not _held(ex, 15, spike, 850), "sp1 joins dr1 in the opening round"
    assert not _held(_executor(board=()), 15, spike, 850), "nothing stands yet"


def test_no_hold_on_a_map_without_a_freeze():
    ex = _executor("Monkey Meadow")
    assert all(not _held(ex, rnd) for rnd in range(30, 42))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK")
