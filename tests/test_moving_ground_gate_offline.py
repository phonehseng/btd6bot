"""On a map with moving ground, a build is not offered when a quarter or
more of its cost goes to land towers that have no legal cell in reach of
the track (map fit 0.0 from both ends).

Geared Medium (2026-11-05, loss case 20261105_192400): the last resort
played hard_ninja_alch_sniper at p=0.37. Short-range towers keep off the
turning gears, so the dart opener, every ninja, the alchemist and the hero
were given up within a second and one sniper lost round 18 with 104 lives.
Offline: planner._strategy_fits on a made-up fit table.
Run: python tests/test_moving_ground_gate_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import mapfit  # noqa: E402
from btd6bot import planner as P  # noqa: E402

NOWHERE = {"early": 0.0, "late": 0.0}
EVERYWHERE = {"early": 1.0, "late": 1.0}
TABLE = {
    # Geared: only global-range towers reach the track from the gears
    "Gear Map": {"stamp": "x", "mechanics": ["rotating_area"], "towers": {
        "ninja": NOWHERE, "alchemist": NOWHERE, "village": NOWHERE, "boomerang": NOWHERE,
        "sniper": EVERYWHERE, "heli": EVERYWHERE}},
    # the same fits on ground that stands still: reinforce buys make up for
    # given-up towers there (High Finance Double HP, won with no supers)
    "Still Map": {"stamp": "x", "mechanics": ["removable"], "towers": {
        "ninja": NOWHERE, "alchemist": NOWHERE, "village": NOWHERE, "boomerang": NOWHERE,
        "sniper": EVERYWHERE, "heli": EVERYWHERE}},
}


def _with_table(fn):
    saved = mapfit.load
    mapfit.load = lambda: TABLE
    try:
        fn()
    finally:
        mapfit.load = saved


def _spec(cost, **towers):
    return P.StrategySpec(id="t", towers=towers, modes=("medium",), base_success={"medium": 0.8},
                          dps_kinds=tuple(towers), cost_share=cost)


def test_build_standing_nowhere_on_moving_ground_is_gated():
    def check():
        # hard_ninja_alch_sniper's shares: ninjas 42%, alchemist 20%, snipers 37%
        ninja_build = _spec({"ninja": 25600, "alchemist": 12250, "sniper": 22400},
                            ninja=(4, 0, 2), alchemist=(4, 2, 0), sniper=(4, 2, 0))
        assert not P._strategy_fits(ninja_build, "Gear Map", "advanced", "medium")
        # a global-range build still fits, so the map stays open
        heli_build = _spec({"sniper": 25100, "heli": 49700}, sniper=(4, 2, 0), heli=(4, 2, 0))
        assert P._strategy_fits(heli_build, "Gear Map", "advanced", "medium")
        # ground that stands still is not gated (map_fit_factor scales p instead)
        assert P._strategy_fits(ninja_build, "Still Map", "advanced", "medium")
    _with_table(check)


def test_buffers_and_small_shares_are_not_counted():
    def check():
        # a village (a buffer: its value is the towers around it) is left out
        snipers_and_village = _spec({"sniper": 70000, "village": 30000}, sniper=(2, 0, 4), village=(2, 3, 0))
        assert not P._land_towers_have_no_spot(snipers_and_village, "Gear Map")
        # under NO_SPOT_SHARE_MAX of the cost on ground-bound towers is allowed
        small = _spec({"sniper": 80000, "boomerang": 20000}, sniper=(2, 0, 4), boomerang=(3, 0, 2))
        assert not P._land_towers_have_no_spot(small, "Gear Map")
        big = _spec({"sniper": 70000, "boomerang": 30000}, sniper=(2, 0, 4), boomerang=(3, 0, 2))
        assert P._land_towers_have_no_spot(big, "Gear Map")
        # maps the table does not know keep the benefit of the doubt
        assert not P._land_towers_have_no_spot(big, "Unknown Map")
    _with_table(check)


def test_build_with_no_tower_in_reach_is_gated_on_any_map():
    """Flooded Valley Primary Only (2026-11-10 10:06): primary_core's tack,
    dart, bomb and boomerang all have map fit 0.0 behind the dam; it lost 200
    lives by round 11. On still ground a build is gated only when none of
    its towers reaches the track."""
    table = dict(TABLE)
    table["Dam Map"] = {"stamp": "x", "mechanics": ["removable"], "towers": {
        "tack": NOWHERE, "dart": NOWHERE, "bomb": NOWHERE, "boomerang": NOWHERE,
        "ice": {"early": 0.59, "late": 0.59}, "sub": EVERYWHERE}}
    saved = mapfit.load
    mapfit.load = lambda: table
    try:
        primary_core = _spec({"tack": 3000, "dart": 2000, "bomb": 4000, "boomerang": 3000},
                             tack=(2, 0, 4), dart=(0, 2, 3), bomb=(0, 3, 2), boomerang=(3, 0, 2))
        assert not P._strategy_fits(primary_core, "Dam Map", "expert", "medium")
        # one tower that does reach keeps the build (solo_ice reached round 26)
        ice_and_dart = _spec({"ice": 9000, "dart": 1000}, ice=(0, 2, 4), dart=(0, 0, 2))
        assert P._strategy_fits(ice_and_dart, "Dam Map", "expert", "medium")
        # a reachable water tower keeps a build whose land towers are cut off
        sub_and_dart = _spec({"sub": 9000, "dart": 1000}, sub=(2, 0, 4), dart=(0, 0, 2))
        assert not P._land_towers_have_no_spot(sub_and_dart, "Dam Map")
        # "Still Map" keeps its snipers in reach: the ninja build stays open
        ninja_build = _spec({"ninja": 25600, "sniper": 22400}, ninja=(4, 0, 2), sniper=(4, 2, 0))
        assert not P._land_towers_have_no_spot(ninja_build, "Still Map")
    finally:
        mapfit.load = saved


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
