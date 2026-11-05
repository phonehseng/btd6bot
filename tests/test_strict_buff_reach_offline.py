"""Support buffs reach a tower only when its centre is inside the buff
radius, and Aircraft Carrier planes get a circling plane's share of the
track - the damage model must not rate a board like Frozen Over's round 56
as safe.

Frozen Over CHIMPS (2026-11-05 14:34) was lost at round 56 (40 camo
rainbows). The village's planned spot was refused, so the Radar Scanner
(radius 48) stood 49.3 units from buccaneer b1, an Aircraft Carrier. The
model added b1's footprint radius (8) to the buff radius, gave b1 camo and
counted its planes at full rate on the whole track: round 56 rated 16. In
the recording the carrier did not shoot the camo pinks beside it.

Offline, against data/game_model/attacks.json and Frozen Over's geometry.
Run: python tests/test_strict_buff_reach_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

# The board at round 56, as the game stood (screen fractions).
BOARD_56 = {
    "t1": ("tack", (2, 0, 3), 0.3447, 0.5043),
    "t2": ("tack", (0, 0, 2), 0.3019, 0.6235),
    "s1": ("sniper", (4, 2, 0), 0.7989, 0.8791),
    "b1": ("buccaneer", (4, 2, 0), 0.4836, 0.4702),
    "sb1": ("sub", (2, 0, 3), 0.4409, 0.4872),
    "sniper1": ("sniper", (0, 1, 0), 0.5210, 0.3424),
    "v1": ("village", (1, 2, 0), 0.5531, 0.2828),
    "b2": ("buccaneer", (3, 2, 0), 0.4676, 0.5383),
}
SAFE = 2.0          # the bar the CHIMPS builds are gated on


def _board(**moved):
    """The round-56 board as towers; moved: {tid: (x, y)} new spots."""
    return [NS(tid=tid, kind=kind, tiers=tiers, x=moved.get(tid, (x, y))[0], y=moved.get(tid, (x, y))[1])
            for tid, (kind, tiers, x, y) in BOARD_56.items()]


def _forecast():
    from btd6bot.forecast import RoundForecast
    fc = RoundForecast("Frozen Over", "chimps")
    return fc if fc._ready() else None


def test_buff_covers_the_centre_only():
    village = NS(x=0.0, z=0.0)
    assert D.buff_covers(village, NS(x=47.9, z=0.0), 48.0)
    assert not D.buff_covers(village, NS(x=48.1, z=0.0), 48.0)
    # a carrier's footprint (8) no longer stretches the radius
    assert not D.buff_covers(village, NS(x=0.0, z=49.3), 48.0)


def test_carrier_planes_circle_like_other_planes():
    """The planes' attacks get AIR_PATTERN_EFFICIENCY; their MOAB-only
    missiles and an engineer's sentries keep their full rate."""
    plane = NS(get={"global": True}.get)
    sentry = NS(get={"range": 45.0, "lifespan": 25.0}.get)
    darts = {"name": "Attack", "range": 9999999.0}
    missile = {"name": "Anti-MoabMissile", "only_tags": ["Moabs"]}
    assert D._plane_share(plane, darts) == D.AIR_PATTERN_EFFICIENCY
    assert D._plane_share(plane, missile) == 1.0
    assert D._plane_share(sentry, darts) == 1.0
    # in the exported carrier: its map-wide plane sources fire at the share
    carrier = D.crosspath("buccaneer", (4, 2, 0))
    planes = [t for a in carrier["attacks"] for w in a.get("weapons", [])
              for t in (w.get("projectile") or {}).get("subtowers", [])]
    assert planes and all(t.get("global") for t in planes)


def test_frozen_over_round_56_board_is_not_safe():
    fc = _forecast()
    if fc is None:
        print("skip: no map geometry")
        return
    margin = fc.margin(_board(), 56)
    assert margin < SAFE, margin
    b1 = [s for s in fc.stations(_board()) if s.tid == "b1"][0]
    assert not all(s.camo for s in b1.sources), "49.3 units from a radius-48 Radar Scanner: no camo"


def test_a_tower_whose_centre_is_inside_still_gets_the_buff():
    """The village moved to 80% of its distance from b1 (about 39 units):
    the carrier's centre is inside the Radar Scanner and every source sees camo."""
    fc = _forecast()
    if fc is None:
        print("skip: no map geometry")
        return
    bx, by = BOARD_56["b1"][2:]
    vx, vy = BOARD_56["v1"][2:]
    near = (bx + 0.8 * (vx - bx), by + 0.8 * (vy - by))
    board = _board(v1=near)
    b1 = [t for t in board if t.tid == "b1"][0]
    v1 = [t for t in board if t.tid == "v1"][0]
    w = fc.track.frac_to_world
    (x1, z1, _), (x2, z2, _) = w(b1.x, b1.y), w(v1.x, v1.y)
    assert D.buff_covers(NS(x=x2, z=z2), NS(x=x1, z=z1), D.profile("village", (1, 2, 0)).range)
    station = [s for s in fc.stations(board) if s.tid == "b1"][0]
    assert all(s.camo for s in station.sources)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
