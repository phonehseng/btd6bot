"""chimps_ninja_sun does not play Erosion or Muddy Puddles.

Erosion (Advanced): the ice between the lanes melts in steps, and the game
sells every tower standing on it. chimps_ninja_sun places its towers by role
beside the lane in use, so each melt takes the whole defence and the plan is
bought again from its first step (Executor.ground_lost). With one life that
rebuild has to hold at once, and it never did - three Impoppable games, each
lost within six rounds of a melt:

  * lost 2026-11-11 04:52 in round 40 and 16:34 in round 54;
  * lost 2026-11-12 06:44 in round 40 (loss case
    20261112_064445_Erosion_impoppable): six towers sold after round 16,
    seven after round 34; the rebuilt board was rated 0.06 for rounds 35
    and 36, Sticky Bomb (n2 2-0-4, $6,000) was bought a second time only in
    round 39, and round 40 was rated 0.82 when the MOAB took the life.

Muddy Puddles (Expert): four short lanes. The build opens with one ninja
beside one of them and lost Impoppable four times out of four: round 7 twice
on 2026-11-11, round 76 the same day, and round 22 on 2026-11-12 07:29 (loss
case 20261112_072956_MuddyPuddles_impoppable: bloons 84-100% along the route
in 11 of rounds 6-21, seven of rounds 7-21 rated under 1, round 22 at 0.45).

Both maps' medals came from their own builds (strategies/maps/erosion_*.yaml
on the ground that lasts the whole game, muddypuddles_*.yaml). So the
general build lists both in planner.excluded_maps and the planner offers it
no game there; the Impoppable map builds are backlog 100 and 101.

Run: python tests/test_chimps_ninja_sun_excluded_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

# map -> some of the map's own builds, which must keep it
OWN_BUILDS = {
    "Erosion": ("erosion_easy", "erosion_military_only"),
    "Muddy Puddles": ("muddypuddles_easy", "muddypuddles_medium", "muddypuddles_military_only"),
}


def _spec(sid):
    """The planner's spec of a strategy, as runner.planner_specs builds it."""
    s = S.load_all()[sid]
    return PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))


def test_the_general_impoppable_build_excludes_both_maps():
    excluded = _spec("chimps_ninja_sun").excluded_maps
    for map_name in OWN_BUILDS:
        assert map_name in excluded, map_name


def test_the_maps_own_builds_still_name_them():
    """The exclusion is the general build's alone."""
    for map_name, builds in OWN_BUILDS.items():
        for sid in builds:
            spec = _spec(sid)
            assert map_name in spec.maps and map_name not in spec.excluded_maps, sid


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
