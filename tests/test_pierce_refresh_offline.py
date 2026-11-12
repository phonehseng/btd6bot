"""Lingering patches whose pierce comes back (docs/model_fix_plan.md item 11).

Wall of Fire (10 pierce every 0.15 s for 4.5 s) and the Druid of the
Jungle's brambles (20 pierce every 0.3 s for 4.5 s) got one load of pierce
and a fixed count of hits: Wall of Fire 10 where the game gives it up to
300 in a dense stream, a bramble 15 even on a lone bloon that crosses its
2-unit circle in three ticks (docs/model_audit_magic.md finding 4,
fandom:Wall_of_Fire, fandom:Druid_of_the_Jungle). Carpet of Spikes' own
Spike Storm every 15 s is counted with the abilities (item 8,
tests/test_ability_uptime_offline.py).

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _source(kind, tiers, name):
    return next(s for s in D.profile(kind, tiers).sources if name in s.name)


def test_patches_carry_their_refresh():
    wall = _source("wizard", (0, 2, 0), "Wall of Fire")
    assert (wall.refresh, wall.life, wall.patch_radius, wall.pierce) == (0.15, 4.5, 15.0, 10.0)
    bramble = _source("druid", (1, 3, 0), "JungleVine>Projectile")
    assert (bramble.refresh, bramble.life, bramble.patch_radius, bramble.pierce) == (0.3, 4.5, 2.0, 20.0)
    # a moving projectile is no patch
    assert _source("dart", (0, 0, 0), "Attack").refresh == 0.0


def test_wall_of_fire_fills_its_300_hits_in_a_crowd():
    wall = _source("wizard", (0, 2, 0), "Wall of Fire")
    red = D.layer("Red")
    assert math.isclose(D._patch_hits(wall, red, 1.0), 10 * 4.5 / 0.15)          # 300
    # a lone red crosses the 15-unit wall (46 units with both radii) at 25
    # units a second in 1.84 s: 13 ticks of 0.15 s
    lone = D._patch_hits(wall, red, 0.0)
    assert lone == math.ceil(2 * (15 + red.radius) / red.speed / 0.15)
    assert 10 < lone < 15


def test_a_bramble_on_a_lone_bloon_ticks_three_times():
    bramble = _source("druid", (1, 3, 0), "JungleVine>Projectile")
    red = D.layer("Red")
    assert D._patch_hits(bramble, red, 0.0) == math.ceil(2 * (2 + red.radius) / red.speed / 0.3) == 3
    # in a dense stream the bloons crossing it in 4.5 s give it far more
    assert D._patch_hits(bramble, red, 0.2) > 15 * 4
    assert D._patch_hits(bramble, red, 10.0) == 20 * 4.5 / 0.3


def test_switch_off_reads_patches_as_before():
    saved = D.REFRESH_RATING
    try:
        D.REFRESH_RATING = False
        D.profile.cache_clear()
        assert _source("wizard", (0, 2, 0), "Wall of Fire").refresh == 0.0
    finally:
        D.REFRESH_RATING = saved
        D.profile.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
