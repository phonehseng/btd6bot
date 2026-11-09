"""hard_ninja_alch_sun no longer plays Pat's Pond.

The general land build lost all three Pat's Pond Half Cash games it played,
picked as a last resort: 2026-11-06 round 40, 2026-11-08 round 40 and
2026-11-09 round 47 (loss case 20261109_110224_PatsPond_half_cash). In the
last one the damage model rated round 40 at 2.3 with two Heli Pilots placed,
yet a single MOAB leaked 33 lives, and rounds 44-47 leaked the rest. Pat's
Pond is two opposite lanes round a pond meeting at two far-apart junctions;
the build places its towers by track coverage on land between them. Every
medal won on the map came from a water or map build instead.

So the build lists Pat's Pond in planner.excluded_maps, and the planner no
longer offers it there in any mode. The map's own builds keep their maps.
Run: python tests/test_patspond_half_cash_excluded_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

MAP = "Pat's Pond"
BUILD = "hard_ninja_alch_sun"


def _specs():
    """Planner specs of every strategy except the achievement plans, as
    runner.planner_specs builds them."""
    return {sid: PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))
            for sid, s in S.load_all().items() if not s.get("achievement")}


def test_the_build_excludes_pats_pond():
    assert MAP in _specs()[BUILD].excluded_maps


def test_the_build_is_not_offered_for_pats_pond_half_cash():
    from btd6bot.account import AccountState
    category = AccountState().map_category(MAP)
    spec = _specs()[BUILD]
    assert not PL._strategy_fits(spec, MAP, category, "half_cash")


def test_the_build_still_plays_half_cash_elsewhere():
    from btd6bot.account import AccountState
    spec = _specs()[BUILD]
    category = AccountState().map_category("Chutes")
    assert PL._strategy_fits(spec, "Chutes", category, "half_cash")


def test_the_map_build_keeps_pats_pond():
    spec = _specs()["patspond_hard"]
    assert spec.maps == frozenset({MAP}) and MAP not in spec.excluded_maps


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
