"""Mortar and Dartling rated at a fixed aim point (docs/model_fix_plan.md
item 14, docs/model_audit_military.md M2).

They used to be rated zero. Now profile() gives their attacks the placement
"point", and a station covers the track around the aim: a Placed tower's
own `aim`, or the track point with the most track around it (aim_point,
picked the way Match._park_point picks where the cursor rests). A Mortar
needs an explicit aim until the bot sets reticles (AIM_MORTARS_BY_DEFAULT).

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _off_track(track):
    pts = track.paths[0]["xyz"]
    p = pts[len(pts) // 2]
    return float(p[0]) + 40.0, float(p[1]) + 40.0


def test_mortar_profile_has_point_sources():
    p = D.profile("mortar", (0, 0, 0))
    assert p.aim == "point" and p.sources and all(s.placement == "point" for s in p.sources)
    assert p.aim_radius == 18.0 + 20.0                       # deviation + blast radius
    assert D.profile("mortar", (0, 0, 1)).aim_radius == 8.0 + 20.0   # Increased Accuracy


def test_mortar_is_rated_at_its_aim():
    tr = D.Track("Monkey Meadow")
    x, z = _off_track(tr)
    aim = D.aim_point(tr, D.profile("mortar", (0, 0, 0)).aim_radius)
    aimed = D.Placed("m", "mortar", (0, 0, 0), x, z, aim)
    assert D.round_margin(D.stations_for([aimed], tr), "medium", 10, tr) > 0.5
    unaimed = D.Placed("m", "mortar", (0, 0, 0), x, z)
    if not D.AIM_MORTARS_BY_DEFAULT:
        assert D.stations_for([unaimed], tr) == []


def test_dartling_fires_at_the_busiest_track():
    tr = D.Track("Monkey Meadow")
    x, z = _off_track(tr)
    gun = D.Placed("g", "dartling", (0, 0, 0), x, z)
    st, = D.stations_for([gun], tr)
    assert st.zones[0] is not None and D.round_margin([st], "medium", 10, tr) > 0.1
    # the station's track lies around the aim point, not around the tower
    aim = D.aim_point(tr, 2 * D.DARTLING_MIN_AIM)
    import math as m
    radius = max(D.DARTLING_MIN_AIM, m.hypot(aim[0] - x, aim[1] - z) * m.tan(m.radians(23.0 / 2)))
    there = tr.zones(aim[0], aim[1], radius)[0]
    assert m.isclose(st.zones[0].entry, there.entry) and m.isclose(st.zones[0].length, there.length)


def test_aim_point_is_on_dense_track():
    tr = D.Track("Monkey Meadow")
    ax, az = D.aim_point(tr, 30.0)
    pts = tr.paths[0]["xyz"]
    assert min(math.hypot(float(p[0]) - ax, float(p[1]) - az) for p in pts) <= D.TRACK_STEP * 1.5
    assert D._deviation_share(28.0, 18.0) < 1.0 and D._deviation_share(28.0, 0.0) == 1.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
