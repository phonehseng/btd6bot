"""A build with a water-only tower is not offered on a map where that tower
has no legal cell in reach of the track (map fit 0.0 from both ends).

Sanctuary Medium (2026-11-05, loss case 20261105_031041): the planner played
the four-sub military_sub_sniper_water at p=0.49 although the fountain basin
cannot hold a sub's footprint; every sub step was given up and the snipers
alone lost round 53. Offline: planner._strategy_fits on a made-up fit table.
Run: python tests/test_water_fit_gate_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapfit  # noqa: E402
from btd6bot import planner as P  # noqa: E402

TABLE = {
    "Basin Map": {"stamp": "x", "towers": {
        "sub": {"early": 0.0, "late": 0.0},        # no cell reaches the track
        "buccaneer": {"early": 0.0, "late": 0.0},
        "ninja": {"early": 0.0, "late": 0.0},      # land towers are only scaled, never gated
        "sniper": {"early": 1.0, "late": 1.0}}},
    "Lake Map": {"stamp": "x", "towers": {
        "sub": {"early": 0.9, "late": 0.4},
        "sniper": {"early": 1.0, "late": 1.0}}},
    "One End Map": {"stamp": "x", "towers": {
        "sub": {"early": 0.0, "late": 0.3}}},      # reachable from the far end only
}


def _with_table(fn):
    saved = mapfit.load
    mapfit.load = lambda: TABLE
    try:
        fn()
    finally:
        mapfit.load = saved


def _spec(**towers):
    return P.StrategySpec(id="t", towers=towers, modes=("medium",),
                          base_success={"medium": 0.8}, dps_kinds=tuple(towers))


def test_water_build_is_gated_where_no_sub_fits():
    def check():
        water = _spec(sub=(4, 0, 4), sniper=(4, 2, 0))
        land = _spec(ninja=(4, 0, 2), sniper=(4, 2, 0))
        assert not P._strategy_fits(water, "Basin Map", "intermediate", "medium")
        assert P._strategy_fits(water, "Lake Map", "intermediate", "medium")
        assert P._strategy_fits(water, "One End Map", "intermediate", "medium")
        assert P._strategy_fits(water, "Unknown Map", "intermediate", "medium")   # not measured
        # a land build on the same map is still only scaled by map_fit_factor
        assert P._strategy_fits(land, "Basin Map", "intermediate", "medium")
        assert P._water_towers_have_no_spot(_spec(buccaneer=(0, 2, 4)), "Basin Map")
    _with_table(check)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
