"""Offline checks for the planner's map fit (mapfit.strategy_fit and
planner.map_fit_factor), on a small made-up table.
Run: python tests/test_mapfit_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapfit  # noqa: E402
from btd6bot import planner as P  # noqa: E402

TABLE = {"Water Map": {"stamp": "x", "towers": {
    "ninja": {"early": 0.3, "late": 0.9},
    "sub": {"early": 0.9, "late": 0.5},
    "sniper": {"early": 1.0, "late": 1.0}}}}


def _with_table(fn):
    saved = mapfit.load
    mapfit.load = lambda: TABLE
    try:
        fn()
    finally:
        mapfit.load = saved


def test_weighted_by_cash():
    def check():
        assert mapfit.strategy_fit("Water Map", ["ninja"]) == 0.3
        # equal weights: (0.3 + 0.9) / 2
        assert abs(mapfit.strategy_fit("Water Map", ["ninja", "sub"]) - 0.6) < 1e-9
        # a plan that puts most of its cash into ninjas fits poorly
        fit = mapfit.strategy_fit("Water Map", ["ninja", "sniper"], weights={"ninja": 3, "sniper": 1})
        assert abs(fit - (3 * 0.3 + 1.0) / 4) < 1e-9
        # Reverse meets the other end of the track first
        assert mapfit.strategy_fit("Water Map", ["ninja"], reverse=True) == 0.9
        assert mapfit.strategy_fit("Unknown Map", ["ninja"]) is None
    _with_table(check)


def test_fit_factor_scales_the_win_chance():
    def check():
        land = P.StrategySpec(id="land", towers={"ninja": (2, 0, 2)}, dps_kinds=("ninja",))
        water = P.StrategySpec(id="water", towers={"sub": (2, 0, 2)}, dps_kinds=("sub",))
        assert P.map_fit_factor(water, "Water Map", "hard") == 1.0
        assert abs(P.map_fit_factor(land, "Water Map", "hard") - 0.3 / P.FULL_FIT) < 1e-9
        assert P.map_fit_factor(land, "Unknown Map", "hard") == 1.0   # not measured: no change
    _with_table(check)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
