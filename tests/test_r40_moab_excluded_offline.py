"""double_hp_sniper_sun is not offered on Workshop or #Ouch.

Both games (2026-11-09) were Fast Track starts at round 22 that reached
round 40 with 100 lives and lost them all to its first MOAB: Workshop ABR
(fortified MOAB; blimp check 0.0x at round 37, $4,219 unspent) and #Ouch
Double HP (400 HP MOAB; check 0.9x, $2,502 unspent).

The replay (tools/simulate_threats.simulate on the learned map with the
Fast Track + Double Cash economy) tried the build as it is, with a Sticky
Bomb (n2 2-0-4), Deadly Precision (s1 3-2-0) or a MOAB Mauler bomb moved
before Shinobi Tactics, and with the blimp check looking 6 or 9 rounds
ahead instead of 3. Round 40's blimp ratio stayed 0.02-0.05x on Workshop
and 0.9-1.1x on #Ouch, under the 1.4x the check wants, so neither map gets
this build; the planner picks another one or another game.
Run: python tests/test_r40_moab_excluded_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

BUILD = "double_hp_sniper_sun"
MAPS = ("Workshop", "#Ouch")


def _spec():
    """The build's planner spec, as runner.planner_specs builds it."""
    s = S.load_all()[BUILD]
    return PL.StrategySpec.from_any(dict(s, id=BUILD, **(s.get("planner") or {})))


def test_the_build_excludes_both_maps():
    spec = _spec()
    for name in MAPS:
        assert name in spec.excluded_maps, name


def test_the_build_is_not_offered_there():
    from btd6bot.account import AccountState
    spec = _spec()
    for name in MAPS:
        category = AccountState().map_category(name)
        for mode in ("abr", "double_hp"):
            assert not PL._strategy_fits(spec, name, category, mode), (name, mode)


def test_other_maps_still_get_it():
    from btd6bot.account import AccountState
    spec = _spec()
    category = AccountState().map_category("Hedge")
    assert PL._strategy_fits(spec, "Hedge", category, "abr")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
