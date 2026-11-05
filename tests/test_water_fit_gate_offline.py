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
    "Moat Map": {"stamp": "x", "towers": {         # Castle Revenge: water for one sub
        "sub": {"early": 0.03, "late": 0.23, "room": 1},
        "sniper": {"early": 1.0, "late": 1.0}}},
}


def _with_table(fn):
    saved = mapfit.load
    mapfit.load = lambda: TABLE
    try:
        fn()
    finally:
        mapfit.load = saved


def _spec(placed=None, **towers):
    return P.StrategySpec(id="t", towers=towers, modes=("medium",),
                          base_success={"medium": 0.8}, dps_kinds=tuple(towers), placed=placed or {})


def test_water_build_is_gated_where_fewer_subs_fit_than_it_places():
    """Castle Revenge Impoppable (2026-11-05, loss case 20261105_063635): a
    two-sub build on a moat with room for one sub gave up its second sub
    and lost round 33 - the plan's sub count is checked against "room"."""
    def check():
        two_subs = _spec(placed={"sub": 2, "druid": 6}, sub=(2, 0, 4), druid=(2, 0, 4))
        one_sub = _spec(placed={"sub": 1, "sniper": 4}, sub=(2, 0, 4), sniper=(4, 2, 0))
        assert not P._strategy_fits(two_subs, "Moat Map", "intermediate", "medium")
        assert P._strategy_fits(one_sub, "Moat Map", "intermediate", "medium")
        # a table measured before "room" was recorded keeps the benefit of the doubt
        assert P._strategy_fits(two_subs, "Lake Map", "intermediate", "medium")
        # a spec without placed counts (an older caller) is not gated by room
        assert P._strategy_fits(_spec(sub=(2, 0, 4)), "Moat Map", "intermediate", "medium")
    _with_table(check)


def test_placed_counts_count_the_plan_only():
    from btd6bot.runner import placed_counts
    strat = {"plan": [{"do": "place", "id": "sb1", "kind": "sub"}, {"do": "place", "id": "hero", "kind": "hero"},
                      {"do": "upgrade", "id": "sb1", "to": "2-0-2"}, {"do": "place", "id": "sb2", "kind": "sub"},
                      {"do": "place", "id": "d1", "kind": "druid"}],
             "fill": [{"do": "place", "kind": "sub"}]}
    assert placed_counts(strat) == {"sub": 2, "druid": 1}


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
