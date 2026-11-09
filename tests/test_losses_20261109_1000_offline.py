"""The three losses of 2026-11-09 09:40-10:10 each change what the planner offers.

1. Castle Revenge Half Cash (hard_ninja_alch_sun, round 25): the Fast Track
   start (round 22, $4,850 at half cash) bought the whole opening and the
   damage model still rated round 22 at 0.15 and round 24 at 0.06; 93 lives
   went in three rounds. data/model_ceiling.json now records 0.06 for it, as
   for Firing Range Half Cash, so no general build is trusted there.
2. Sunken Columns ABR (double_hp_sniper_sun, round 57): 17 snipers and the
   model still at 0.33-0.65 for rounds 54-57. The build skips the map.
3. Workshop Primary Only (primary_core, round 40): its third loss at the
   first MOAB; towers on the conveyor lanes showed 0 pops for 12-15 rounds.
   The build skips the map.
Run: python tests/test_losses_20261109_1000_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402


def _spec(build):
    """A build's planner spec, as runner.planner_specs builds it."""
    s = S.load_all()[build]
    return PL.StrategySpec.from_any(dict(s, id=build, **(s.get("planner") or {})))


def _fits(build, map_name, mode):
    from btd6bot.account import AccountState
    category = AccountState().map_category(map_name)
    return PL._strategy_fits(_spec(build), map_name, category, mode)


def test_castle_revenge_half_cash_is_capped():
    assert PL.model_ceiling("Castle Revenge", "half_cash") <= 0.1
    # the cap is below every play threshold, so it is only ever a last resort
    assert PL.ceiling_cap(0.9, "Castle Revenge", "half_cash") < 0.1
    # Double HP, which the same build won the same hour, does not inherit the
    # Half Cash number (its own ceiling, if any, comes from the optimizer's
    # builds in strategies/optimized/)
    other = PL.model_ceiling("Castle Revenge", "double_hp")
    assert other is None or other > 0.06


def test_sunken_columns_abr_skips_the_sniper_build():
    assert not _fits("double_hp_sniper_sun", "Sunken Columns", "abr")
    assert _fits("double_hp_sniper_sun", "Hedge", "abr")


def test_workshop_primary_only_skips_primary_core():
    assert not _fits("primary_core", "Workshop", "primary_only")
    assert _fits("primary_core", "Hedge", "primary_only")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
