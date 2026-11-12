"""Each attack of a tower works in its own reach, not the tower's largest.

A station used to give all of a tower's sources one zone, as wide as the
tower's largest reach (docs/model_audit_primary.md F4):

  * Glaive Lord (5-0-0 / 5-0-2): the orbiting glaives sweep a 30-unit circle
    ("30 unbuffable range", fandom:Glaive_Lord_(BTD6)) and were credited
    over the 43-unit throwing circle (57.2 at x-x-2): about 1.4-1.7x;
  * Desperado 0-3-x: the 40-unit pistol over the 80-unit rifle circle.

Now each attack keeps its own radius (dps_model._zone_radius) and a tower
with several reaches is one station per reach (_local_stations). The
corrected zones are the track inside each attack's own circle.
Run: python tests/test_per_attack_reach_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

SPOT = (-100.0, 35.0)      # 16 units off Monkey Meadow's first lane


def _stations(kind, tiers, placed_extra=()):
    tr = D.Track("Monkey Meadow")
    t = D.Placed("x", kind, tiers, *SPOT)
    st = D.station_for(t, [t, *placed_extra], tr)
    return tr, D.with_parts([st])


def _covered(tr, radius):
    return sum(z.length for z in tr.zones(*SPOT, radius) if z is not None)


def _station_with(stations, name):
    return next(s for s in stations if any(x.name == name for x in s.sources))


def test_glaive_orbit_covers_its_own_circle():
    for tiers in ((5, 0, 0), (5, 0, 2)):
        tr, stations = _stations("boomerang", tiers)
        orbit = _station_with(stations, "OrbitAttack>OrbitingGlaive")
        own = D.profile("boomerang", tiers).own_radius                    # 30
        assert [x.name for x in orbit.sources] == ["OrbitAttack>OrbitingGlaive"]
        assert abs(sum(z.length for z in orbit.zones if z) - _covered(tr, own)) < 1e-6
        throw = _station_with(stations, "Attack>Projectile")
        rng = D.crosspath("boomerang", tiers)["range"]                     # 43 / 57.2
        assert abs(sum(z.length for z in throw.zones if z) - _covered(tr, rng)) < 1e-6
        assert _covered(tr, own) < _covered(tr, rng)


def test_glaive_orbit_ignores_range_buffs():
    """A village's range buff widens the throws, not the orbit."""
    village = D.Placed("v", "village", (1, 0, 0), SPOT[0] + 5.0, SPOT[1])
    assert any(b["kind"] == "range" for b in D.profile("village", (1, 0, 0)).buffs)
    tr, stations = _stations("boomerang", (5, 0, 0), [village])
    orbit = _station_with(stations, "OrbitAttack>OrbitingGlaive")
    assert abs(sum(z.length for z in orbit.zones if z) - _covered(tr, 30.0)) < 1e-6


def test_desperado_pistol_covers_its_own_range():
    tr, stations = _stations("desperado", (0, 3, 0))
    pistol = _station_with(stations, "Attack>Projectile")
    rifle = _station_with(stations, "AttackRifle>Projectile")
    ranges = {a["name"]: a["range"] for a in D.crosspath("desperado", (0, 3, 0))["attacks"]}
    assert ranges == {"Attack": 40.0, "AttackRifle": 80.0}, ranges
    assert abs(sum(z.length for z in pistol.zones if z) - _covered(tr, 40.0)) < 1e-6   # 73.6 units
    assert abs(sum(z.length for z in rifle.zones if z) - _covered(tr, 80.0)) < 1e-6    # 335.5 units


def test_one_reach_towers_keep_one_station():
    for kind, tiers in (("dart", (0, 0, 0)), ("tack", (0, 0, 4)), ("spike", (0, 0, 0))):
        _, stations = _stations(kind, tiers)
        assert len(stations) == 1, (kind, tiers)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
