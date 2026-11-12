"""Monkey Ace bombs fall under the plane, not on the whole map.

Pineapples (0-1-x, 0-2-x) and the Bomber Ace / Ground Zero bombs (0-3-x and
up) are an air attack without a range check, so the export marks them
"unbounded": "map" and the damage model credited them at full rate on the
whole track. In the game the bomb falls to the ground under the plane
(FallToGroundModel), and the Bomber Ace weapon fires only while the plane is
over the track (CheckAirUnitOverTrackModel, exported as "over_track_only").
docs/model_audit_military.md, finding M1: the bombs were 91% of a 2-3-0
ace's rating, over-credited 3-10x.

Now (dps_model._drop_parts):
  * a Bomber Ace gets one volley per pass over the track (plus one per
    cooldown the pass lasts), against one per cooldown before;
  * pineapples keep their rate on the part of the flight circle within
    their blast of the track;
  * both hit only the track within their blast of where they fall.

The example tower is a 2-3-0 ace beside Monkey Meadow's first straight
lane (z = 18.9), 30 units off it: its flight circle (radius 40) crosses
that lane twice and reaches no other track.
Run: python tests/test_ace_bombs_under_plane_offline.py (also collectable by pytest).
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

SPOT = (-100.0, 48.9)       # world units: 30 above the lane z = 18.9, x -154 .. -17


def _weapon(code, attack="PineappleBombs"):
    entry = D.crosspath("ace", code)
    a = next(a for a in entry["attacks"] if a["name"] == attack)
    return entry, a["weapons"][0]


def _parts(code, x=SPOT[0], z=SPOT[1]):
    tr = D.Track("Monkey Meadow")
    t = D.Placed("a1", "ace", code, x, z)
    st = D.station_for(t, [t], tr)
    return tr, D.with_parts([st]) if st is not None else []


def test_bomber_ace_is_not_map_wide():
    p = D.profile("ace", (2, 3, 0))
    bombs = [s for s in p.sources if s.name == "PineappleBombs>Explosion"]
    assert len(bombs) == 1 and bombs[0].placement == "drop" and bombs[0].over_track_only
    assert not p.is_global, "the bombs were the only thing that made the ace map-wide"


def test_bomber_ace_fires_once_per_pass_over_the_track():
    """Two passes a lap over the lane, each shorter than the 1.2 s cooldown:
    two volleys per lap of 2*pi*40/60 = 4.19 s, against 3.5 at full rate."""
    entry, w = _weapon((2, 3, 0))
    full = w["count"] / w["rate"]                         # 4 bombs every 1.2 s: 3.33/s
    lap = 2.0 * math.pi * D.profile("ace", (2, 3, 0)).pattern_radius / entry["air_unit"]["speed"]
    expected = full * min(1.0, 2 * w["rate"] / lap)       # 1.91 bombs/s
    _, stations = _parts((2, 3, 0))
    bombs = [s for st in stations for s in st.sources if s.name == "PineappleBombs>Explosion"]
    assert len(bombs) == 1
    assert abs(bombs[0].shots - expected) < 0.02, (bombs[0].shots, expected)
    assert abs(expected - 1.91) < 0.01


def test_bombs_hit_only_track_near_the_flight_circle():
    tr, stations = _parts((2, 3, 0))
    bomb_station = next(st for st in stations if any(s.placement == "drop" for s in st.sources))
    covered = sum(z.length for z in bomb_station.zones if z is not None)
    assert covered < 0.5 * sum(tr.total_length()), covered      # 215 of 886 units


def test_no_bombs_when_the_circle_misses_the_track():
    """60 units off the lane the circle (40) never comes over the track."""
    _, stations = _parts((2, 3, 0), z=SPOT[1] + 30.0)
    assert not any(s.placement == "drop" for st in stations for s in st.sources)


def test_pineapples_keep_their_rate_where_they_land_near_the_track():
    """Pineapples (0-1-0) fall wherever the plane is: the share of the circle
    within the explosion's radius (35) of the lane keeps its rate."""
    entry, w = _weapon((0, 1, 0))
    tr, stations = _parts((0, 1, 0))
    t = D.Placed("a1", "ace", (0, 1, 0), *SPOT)
    circle = D._flight_circle(t, D.profile("ace", (0, 1, 0)).pattern_radius)
    blast = w["projectile"]["spawn"][0]["projectile"]["radius"]
    share = float(tr.near_track(circle, blast).mean())
    bombs = [s for st in stations for s in st.sources if s.name == "PineappleBombs>Explosion"]
    assert len(bombs) == 1 and not bombs[0].over_track_only
    assert abs(bombs[0].shots - w["count"] / w["rate"] * share) < 1e-9
    assert 0.5 < share < 0.8, share


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
