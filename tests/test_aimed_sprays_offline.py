"""Aimed sprays are not all-around fire (docs/model_fix_plan.md item 10).

A volley that fans out from the shot at its target (Triple Shot, Sun
Avatar, Bloonjitsu, Grandmaster, the Druid's thorns, the Desperado's
shotgun) was read as a Tack Shooter's ring and cut to the share of all
directions that cross the lane - about 40% beside a straight track
(docs/model_audit_magic.md finding 3, primary F8). The export carries each
volley's fan ("spray", tools/export_attacks.py).

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _beside_track(track, offset=15.0, at=0.5):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + offset, float(p[1])


def _main(kind, tiers, name):
    return next(s for s in D.profile(kind, tiers).sources if s.name == name)


def test_the_export_carries_the_fan():
    attacks = D.attacks()["towers"]

    def fan(kind, code, attack):
        a = next(a for a in attacks[kind]["crosspaths"][code]["attacks"] if a["name"] == attack)
        return a["weapons"][0].get("spray")
    assert fan("dart", "030", "Attack") == 30.0            # Triple Shot: 30 degrees in all
    assert fan("super", "300", "Attack") == 30.0           # Sun Avatar
    assert fan("ninja", "400", "Attack") == 45.0           # Bloonjitsu
    assert fan("ninja", "500", "Attack") == 72.0           # Grandmaster
    assert fan("druid", "130", "Attack") == 25.0           # thorns
    assert fan("desperado", "003", "AttackShotgun") == 35.0
    assert fan("tack", "000", "Attack") == 360.0           # a ring


def test_sprays_are_aimed_rings_are_radial():
    for kind, tiers, name, fan in (("dart", (0, 3, 0), "Attack>Projectile", 30.0),
                                   ("super", (3, 0, 0), "Attack>Projectile", 30.0),
                                   ("ninja", (4, 0, 0), "Attack>Projectile", 45.0),
                                   ("ninja", (5, 0, 0), "Attack>Projectile", 72.0),
                                   ("druid", (1, 3, 0), "Attack>BaseProjectile", 25.0),
                                   ("desperado", (0, 0, 3), "AttackShotgun>Projectile", 35.0)):
        s = _main(kind, tiers, name)
        assert not s.radial and s.spray == fan, (kind, tiers)
    tack = _main("tack", (0, 0, 0), "Attack>Projectile")
    assert tack.radial and tack.spray == 0.0


def test_a_sun_avatar_beside_the_track_keeps_its_beams():
    """Beside a straight lane the track spans well under half the circle:
    read as a ring the beams kept that share; aimed, a 30-degree fan hits
    in full."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr, at=0.3)          # beside a straight stretch
    sun = D.Placed("s", "super", (3, 0, 0), x, z)
    st = D.station_for(sun, [sun], tr)
    beams, = [s for s in st.sources if s.name == "Attack>Projectile"]
    zone = st.zones[0]
    assert zone.angular < 0.6
    lay = D.layer("Red")
    aimed = D._hit_rate(beams, lay, 0.2, zone)
    ring = D._hit_rate(D.Source(**{**beams.__dict__, "radial": True, "spray": 0.0}), lay, 0.2, zone)
    assert math.isclose(aimed / ring, 1.0 / zone.angular, rel_tol=1e-6)
    # a fan wider than the track's spread loses the part that misses
    wide = D.Source(**{**beams.__dict__, "spray": 359.0})
    assert math.isclose(D._hit_rate(wide, lay, 0.2, zone), aimed * zone.angular * 360.0 / 359.0, rel_tol=1e-6)


def test_switch_off_reads_volleys_as_before():
    saved = D.SPRAY_RATING
    try:
        D.SPRAY_RATING = False
        D.profile.cache_clear()
        assert _main("dart", (0, 3, 0), "Attack>Projectile").radial
    finally:
        D.SPRAY_RATING = saved
        D.profile.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
