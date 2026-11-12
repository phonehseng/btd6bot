"""Reinforce rates Glacial Trail boards with each tower's placement round.

On Glacial Trail every tower sits in ice for two rounds in ten, counted from
the round it was bought in (dps_model.frozen_in), and the forecast rates a
round with only the towers awake in it - but only when every tower's
placement round is known (forecast._phase_groups); otherwise it falls back
to the average uptime. reinforce.board() dropped the placement round, and
the towers a purchase would add had none, so every purchase reinforce
weighed was rated at the average uptime, blind to a defence that freezes
whole (dynamic-map audit 2026-11-12, item 8).

The board is the one of the Glacial Trail Reverse loss of 2026-11-11
(case 20261111_172115_GlacialTrail_reverse, see test_freeze_clash_offline):
the Spike Factory and the first druid bought in round 15, the second druid
in round 17, so in rounds 24-25 (and 44-45) only the second druid is awake.

Checked:
  * reinforce.board() carries every tower's placement round;
  * a new tower on offer is placed in the round being played (now_round);
  * rated from reinforce's records, round 24 is rated exactly as it is from
    the executor's own towers - the frozen spike and druid left out: at the
    floor, where the average uptime rated it 1.18, a safe round.
Run: python tests/test_reinforce_freeze_rounds_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import dps_model as D           # noqa: E402
from btd6bot import reinforce as RF          # noqa: E402
from btd6bot import strategy as S            # noqa: E402
from btd6bot.forecast import RoundForecast   # noqa: E402

# (id, kind, spot, round bought, cash in it)
BOARD = (("dr1", "druid", (0.158, 0.879), 15, 2050),
         ("sp1", "spike", (0.719, 0.649), 15, 12550),
         ("dr2", "druid", (0.729, 0.274), 17, 2050))
NOW = 20


def _executor():
    m = SIM.map_model("Glacial Trail", learned=False)
    g = SIM.CashGame("medium", "quincy", m)
    ex = S.Executor(g, m, S.load_all()["glacialtrail_medium"], "medium", SIM.full_account())
    for tid, kind, (x, y), bought, spent in BOARD:
        p = SIM.Placed(tid, kind, x, y)
        p.placed_round, p.spent = bought, spent
        g.towers[tid] = p
    ex.now_round = NOW
    return ex


def test_board_records_carry_placement_rounds():
    ex = _executor()
    assert {t.tid: t.placed_round for t in RF.board(ex)} == {tid: r for tid, _, _, r, _ in BOARD}
    new = RF.new_tower(ex, "_new_druid", "druid", 0.5, 0.5)
    assert new.placed_round == NOW and new.tiers == (0, 0, 0)


def test_new_options_are_placed_this_round():
    ex = _executor()
    placed = [o for o in RF.options(ex, 100_000, kinds={"druid"}) if o.step.get("do") == "place"]
    assert placed, "no druid placement offered"
    for o in placed:
        new = [t for t in o.towers if t.tid.startswith("_new_")]
        assert [t.placed_round for t in new] == [NOW], o.name
        assert all(t.placed_round is not None for t in o.towers), o.name


def test_reinforce_rates_the_frozen_round_exactly():
    """Round 24 freezes dr1 and sp1 (placed in 15: frozen 24-25); from
    reinforce's records it is rated with dr2 alone, as from the executor's
    towers, and not at the average uptime of the whole board."""
    ex = _executor()
    assert D.frozen_in("Glacial Trail", 15, 24) and not D.frozen_in("Glacial Trail", 17, 24)
    fc = RoundForecast("Glacial Trail", "medium")
    records = RF.board(ex)
    exact = fc.margin(records, 24)
    assert exact == fc.margin(list(ex.g.towers.values()), 24)
    assert D.at_floor(exact), "dr2 alone cannot hold round 24"
    blind = [S.SimpleNamespace(**{**vars(t), "placed_round": None}) for t in records]
    assert fc.margin(blind, 24) > 1.0, "the average uptime hides the frozen round"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
