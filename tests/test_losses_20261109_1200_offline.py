"""Last Resort Primary Only (primary_core, round 15, 2026-11-09 12:02, loss
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
