"""Super Maelstrom re-checked against the wiki (docs/model_fix_plan.md
phase 2b, item C).

Phase 2 credited the ability by its uptime and raised a 0-5-0 tack about
x2.67. Its numbers are the wiki's (fandom:Super_Maelstrom): 4 blades every
0.045 s for 9 s on a 20 s cooldown, 300 pierce, 2 damage (+8 Ceramic), no
camo - 40 blades a second on average. What was wrong is where they reach:
"Full Map Range" (range 999) is the rotating spray's targeting; the blades
themselves fly 150 units a second for 2 s, 300 units from the tack.

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def test_super_maelstrom_numbers_match_the_wiki():
    blades = next(s for s in D.profile("tack", (0, 5, 0)).sources if s.ability == "Super Maelstrom")
    assert math.isclose(blades.shots, 4 / 0.045 * 9 / 20)
    assert (blades.pierce, blades.damage) == (300.0, 2.0)
    assert blades.bonus == {"Ceramic": {"mult": 1.0, "add": 8.0}}
    assert not blades.camo and "lead" in blades.immune


def test_maelstrom_blades_reach_their_flight_only():
    for tiers in ((0, 5, 0), (0, 4, 0)):
        blades = next(s for s in D.profile("tack", tiers).sources if s.ability)
        assert blades.zone_radius == 300.0, tiers          # 150 units/s x 2 s, not range 999
    plain = next(s for s in D.profile("tack", (0, 5, 0)).sources if not s.ability)
    assert plain.zone_radius == 46.0                       # the passive keeps its range


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
