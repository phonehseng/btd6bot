"""An Advanced Intel sub (2-x-x) reaches its own circle and the circles of
the other attacking towers - not the whole map.

attacks.json records Advanced Intel as a map-wide reach, and the damage
model gave such a sub the whole track. Two games of 2026-11-08 lost 105
and 143 lives by round 21 with the defence rated 5-16x:

* Spillway Medium (loss case 20261108_171359, water_sub_alch): two 2-0-x
  subs in the side pools and an alchemist, nothing else attacking. The
  walls round the central loop block the pools' sight; 80 greens of round
  18 leaked while the model rated the round 11.3.
* Erosion Reverse (loss case 20261108_193620, erosion_military_only): two
  Intel subs in the bottom-left water and two map-wide snipers; the 80
  greens of round 18 leaked at a rating of 5.0. Had the sub shot along the
  snipers' sight, two 2-0-3 subs would have popped them: map-wide towers
  lend nothing.

Offline, on Monkey Meadow's geometry (committed).
Run: python tests/test_sub_intel_reach_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _setup():
    track = D.Track("Monkey Meadow")

    def placed(tid, kind, tiers, fx, fy):
        x, z = track.frac_to_world(fx, fy)[:2]
        return D.Placed(tid, kind, tiers, x, z)
    return track, placed


def _reach(stations, tid):
    st = next((s for s in stations if s.tid == tid), None)
    return 0.0 if st is None else sum(z.length for z in st.zones if z)


def test_intel_sub_alone_reaches_only_its_own_circle():
    track, placed = _setup()
    sub = placed("sb1", "sub", (2, 0, 3), 0.47, 0.52)
    own = sum(z.length for z in track.zones(sub.x, sub.z, D.profile("sub", (2, 0, 3)).range) if z)
    whole = sum(track.total_length())
    got = _reach(D.stations_for([sub], track), "sb1")
    assert abs(got - own) < 1e-6, (got, own)
    assert got < 0.8 * whole, (got, whole)


def test_a_sniper_lends_no_reach_but_a_dart_lends_its_circle():
    track, placed = _setup()
    sub = placed("sb1", "sub", (2, 0, 3), 0.47, 0.52)
    alone = _reach(D.stations_for([sub], track), "sb1")
    sniper = placed("s1", "sniper", (0, 0, 0), 0.30, 0.42)
    with_sniper = _reach(D.stations_for([sub, sniper], track), "sb1")
    assert abs(with_sniper - alone) < 1e-6, (alone, with_sniper)
    dart = placed("d1", "dart", (0, 0, 0), 0.15, 0.30)
    with_dart = _reach(D.stations_for([sub, dart], track), "sb1")
    assert with_dart > alone, (alone, with_dart)
    # the dart's circle, no more: the union of the two circles
    r_sub = D.profile("sub", (2, 0, 3)).range
    r_dart = D.profile("dart", (0, 0, 0)).range
    union = sum(z.length for z in track.zones(sub.x, sub.z, r_sub, lent=((dart.x, dart.z, r_dart),)) if z)
    assert abs(with_dart - union) < 1e-6, (with_dart, union)


def test_strict_reading_still_limits_the_sub_to_its_own_circle():
    track, placed = _setup()
    sub = placed("sb1", "sub", (2, 0, 3), 0.47, 0.52)
    dart = placed("d1", "dart", (0, 0, 0), 0.15, 0.30)
    alone = _reach(D.stations_for([sub], track), "sb1")
    strict = _reach(D.stations_for([sub, dart], track, strict=True), "sb1")
    assert abs(strict - alone) < 1e-6, (alone, strict)


def test_a_sub_without_intel_is_unchanged():
    track, placed = _setup()
    sub = placed("sb1", "sub", (0, 0, 3), 0.47, 0.52)
    dart = placed("d1", "dart", (0, 0, 0), 0.15, 0.30)
    assert abs(_reach(D.stations_for([sub], track), "sb1")
               - _reach(D.stations_for([sub, dart], track), "sb1")) < 1e-6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
