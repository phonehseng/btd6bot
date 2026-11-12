"""The Druid of the Jungle's vine digests its bloon before the next grab
(docs/model_fix_plan.md item 13).

Its cooldown is the larger of 2.6 s and 1.4 s + (sqrt(lives the bloon
costs) + 1, + 2 for a lead) / 4: 4.2 s on a ceramic, 3.35 s on a lead or a
rainbow, 2.85 on a zebra (fandom:Druid_of_the_Jungle; docs/model_audit_
magic.md finding 11). 1.4 s is the game model's destroyAfterPopTime.

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _vine():
    return next(s for s in D.profile("druid", (1, 3, 0)).sources if s.name == "JungleVine>Collidable")


def test_digest_times_match_the_wiki():
    vine = _vine()
    assert vine.digest == 1.4                       # the export's destroyAfterPopTime
    for bloon, seconds in (("Red", 1.9), ("Zebra", 2.85), ("Lead", 3.35), ("Rainbow", 3.36), ("Ceramic", 4.2)):
        assert math.isclose(D._digest_time(vine, D.layer(bloon)), seconds, abs_tol=0.01), bloon


def test_grabs_a_second_by_bloon():
    """0.38 grabs a second (2.6 s) up to a zebra's 2.85 s digest; 0.24 on
    ceramics; the brambles come with the grabs."""
    vine = _vine()
    bramble = next(s for s in D.profile("druid", (1, 3, 0)).sources if s.name == "JungleVine>Projectile")
    assert bramble.digest == vine.digest
    st = D.Station("d", "druid", (1, 3, 0), [D.Zone(0.0, 400.0)], [vine], 0.0)
    rates = D._Rates(st)
    red = rates.subtree("Red", 1.0, 1e-3, 0, 0.0)[0]
    assert math.isclose(1.0 / red, 1 / 2.6, rel_tol=1e-3)
    ceramic = rates.get("Ceramic", 1.0, 1e-3, 0)
    kills = ceramic[0] * ceramic[2] / D.layer("Ceramic").hp
    assert math.isclose(kills, 1.0 / D._digest_time(vine, D.layer("Ceramic")), rel_tol=1e-6)
    assert 0.23 < kills < 0.25


def test_switch_off_grabs_at_the_plain_rate():
    saved = D.DIGEST_RATING
    try:
        D.DIGEST_RATING = False
        D.profile.cache_clear()
        assert _vine().digest == 0.0
    finally:
        D.DIGEST_RATING = saved
        D.profile.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
