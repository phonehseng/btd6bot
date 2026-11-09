"""Model ceilings from the losses of 2026-11-09 12:00-13:00.

Last Resort Primary Only (primary_core, round 15, 2026-11-09 12:02, loss
case 20261109_120615): the second loss there, with a second build (solo_bomb
lost round 20 on 2026-11-04). The live damage model rated every round from
10 to 15 at 0.06, and tools/optimize_builds.py finds no Primary Only build
safe past round 1 (worst margin 0.09; the same with the $1,000 frozen pool
removed, which frees the central ground): bloons take one of four loops by
round, and no primary tower covers them all. data/model_ceiling.json said
0.33 from the first research; it now says 0.09, so the game ranks under
every last resort whose research comes closer to holding.
Run: python tests/test_losses_20261109_1200_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402


def test_last_resort_primary_only_ceiling():
    assert PL.model_ceiling("Last Resort", "primary_only") <= 0.1
    # capped well under the 0.11 it was picked at
    assert PL.ceiling_cap(0.9, "Last Resort", "primary_only") < 0.04
    # its other modes keep their own numbers (Medium's build holds)
    assert PL.model_ceiling("Last Resort", "deflation") > 1.5


def test_workshop_medium_ceiling():
    """Workshop Medium (hard_ninja_alch_sun, round 40, 2026-11-09 12:55,
    loss case 20261109_125609): the fourth loss there with a fourth build,
    three of them at round 40's MOAB, which drops from a hidden chute onto
    the last third of the belt (the blimp check: 21 units of track in
    reach, 0.1x of the damage wanted). tools/optimize_builds.py Workshop
    medium: no safe build (worst margin 0.15, unsafe rounds 28-41 and
    49-60), so the ceiling was set to 0.15.

    Since f87a9b8 (2026-11-09 14:05) the map has its own build,
    strategies/maps/workshop_medium.yaml, whose towers stand in the two
    pockets that see the chute's stretch; its worst round is rated 2.54
    and data/model_ceiling.json carries that number. So the ceiling no
    longer holds the game down, and Military Only (Medium with fewer
    towers) inherits it as before."""
    from btd6bot import strategy as S
    assert "workshop_medium" in S.load_all()       # the build the number comes from
    assert PL.model_ceiling("Workshop", "medium") >= 2.0
    assert PL.model_ceiling("Workshop", "military_only") == PL.model_ceiling("Workshop", "medium")
    assert PL.ceiling_cap(0.9, "Workshop", "medium") == 0.9


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
