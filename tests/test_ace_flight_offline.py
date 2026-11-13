"""The Monkey Ace's flight (docs/model_audit_military.md M8; the owner's
notes, 2026-11-12).

From x-x-3 (Neva-Miss Targeting, kept by Spectre and Flying Fortress) the
Ace's darts home in on bloons anywhere: map-wide, full rate, no circling
plane's x0.4. What does not home keeps the flight's coverage: the
Spectre's shells (the share of the map's track near the flight circle),
bombs and pineapples (along the circle), darts below x-x-3. The circle is
the export's 40 around the runway (the game's Circle is 80; kept at 40
after a Bomber Ace calibration case), or 90 around the map centre from
x-x-2 (Centered Path), so where the runway stands no longer matters then.

All offline: no game, no game files.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _board(tiers, x, z):
    return [D.Placed("a", "ace", tiers, x, z), D.Placed("v", "village", (0, 2, 0), x + 10.0, z + 10.0)]


def test_neva_miss_darts_are_map_wide():
    for tiers, placement in (((0, 0, 2), "air"), ((0, 0, 3), "global"), ((2, 0, 4), "global")):
        darts = next(s for s in D.profile("ace", tiers).sources if s.name == "Attack>MainProjectile")
        assert darts.placement == placement, tiers
    assert D.profile("ace", (0, 0, 0)).pattern_radius == (D.ACE_CIRCLE_RADIUS or 40.0)
    assert D.profile("ace", (0, 0, 2)).pattern_radius == D.ACE_CENTERED_RADIUS


def test_spectre_shells_alternate_and_stay_near_the_plane():
    srcs = D.profile("ace", (2, 0, 4)).sources
    darts = next(s for s in srcs if s.name == "SpectreAttack>SpectreDartProjectile")
    shells = next(s for s in srcs if s.name == "SpectreAttack>BombExplosion")
    assert darts.shots == shells.shots                        # they alternate, half each
    assert shells.near_plane and not darts.near_plane


def test_spectre_on_a_spread_out_map_does_not_depend_on_its_runway():
    """Quad's four lanes are spread over the map: a Spectre (2-0-4) with a
    Radar Scanner holds round 50 on Hard with a clear margin wherever its
    runway stands, since from Centered Path it circles the map centre."""
    tr = D.Track("Quad")
    a = D.round_margin(D.stations_for(_board((2, 0, 4), -120.0, -90.0), tr), "hard", 50, tr)
    b = D.round_margin(D.stations_for(_board((2, 0, 4), 120.0, 90.0), tr), "hard", 50, tr)
    assert abs(a - b) <= 0.02 * max(a, b), (a, b)
    assert a >= 2.0, a


def test_spectre_shell_share_follows_the_map():
    """The shells' share of a map's track: what lies within the flight
    circle plus range of the map centre - different per map."""
    p = D.profile("ace", (2, 0, 4))
    shares = {}
    for name in ("Quad", "Monkey Meadow", "Logs"):
        tr = D.Track(name)
        t = D.Placed("a", "ace", (2, 0, 4), 0.0, 0.0)
        shares[name] = D._near_plane_share(t, p, lambda r: r, tr)
    assert all(0.0 < v <= 1.0 for v in shares.values())
    assert len({round(v, 2) for v in shares.values()}) == 3, shares


def test_flying_fortress_with_rapid_fire_carries_hard_dark_castle():
    """The owner: a 2-0-5 Ace with a camo village carries most of a game on
    its own on Medium and Hard. Pinned on Dark Castle (Expert), Hard: rounds
    63-90 hold with a clear margin. Rounds 95 and 98 rate under 1.0: the
    model leaks R95's camo regrow rainbows and ceramics and its camo DDTs
    (pierce-limited among 500 purples and 250 fortified leads) and R98's
    fortified BFBs and MOABs, with only about 205 units of hittable track
    on the castle map.

    Round 85 rated 2.20 until 93c2d83 (2026-11-12, few blimps are few: a
    zone holds no more than the group sent down it, and a projectile's
    pierce reaches only the blimps within its reach); 1.59 since: the
    planes' pierce no longer counts on spaced-out blimps beyond its reach.
    Round 90 fell from 5.72 to 2.16 the same way and still holds the 2.0.
    No live game pins this board; the floor is today's number less a
    little."""
    tr = D.Track("Dark Castle")
    st = D.stations_for(_board((2, 0, 5), 100.0, 60.0), tr)
    for rnd, floor in ((63, 2.0), (76, 2.0), (85, 1.5), (90, 2.0)):
        assert D.round_margin(st, "hard", rnd, tr) >= floor, rnd


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
