"""Shots that are alternatives are no longer counted as if all of them fire.

docs/model_audit_military.md (M4, M5, M8, M12) and docs/model_audit_primary.md
(F9, F11) found the damage model adding up things the game does one OR the
other of:

  * Sub Airburst (x-x-2+): the dart bursts into splits when it hits
    (exhaust) or when it flies out (expire), never both; both were counted.
    The dart itself is "1 impact" (maxPierce 1), not pierce 2.
  * Buccaneer rear shots ("Weapon Secondary"): fired only when bloons are
    in a 90-degree cone behind the boat; counted at the full rate.
  * Spectre's barrage alternates dart and shell; Recursive Cluster replaces
    every second bomb: the replaced shots were counted on top.
  * A submerged sub (3-x-x+) cannot throw darts; they were counted beside
    the pulse.
  * Frag Bombs' frags (pierce 2, +1 pierce used per hit): one hit each.

Each check pins the corrected number of the audit's example tower, derived
from data/game_model/attacks.json.
Run: python tests/test_alternative_shots_offline.py (also collectable by pytest).
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _sources(kind, tiers, name=None):
    out = D.profile(kind, tiers).sources
    return [s for s in out if name is None or s.name == name]


def _weapon(kind, tiers, attack="Attack", index=0):
    a = next(a for a in D.crosspath(kind, tiers)["attacks"] if a["name"] == attack)
    return a["weapons"][index]


def test_sub_airburst_bursts_once_per_dart():
    """2-0-4: 3 splits per dart (one burst), the dart one impact."""
    w = _weapon("sub", (2, 0, 4))
    darts = w["count"] / w["rate"]                                  # 3.98/s
    splits = _sources("sub", (2, 0, 4), "Attack>AirburstSplit")
    assert len(splits) == 1, splits                                  # was two (exhaust + expire)
    assert abs(splits[0].shots - 3 * darts) < 1e-6, splits[0].shots
    dart = _sources("sub", (2, 0, 4), "Attack>Projectile")[0]
    assert dart.pierce == w["projectile"]["max_pierce"] == 1.0


def _fake_track(lanes):
    """A Track stand-in with straight horizontal lanes at these z values."""
    xs = np.arange(-300.0, 300.0, D.TRACK_STEP)
    paths = []
    for z in lanes:
        xyz = np.stack([xs, np.full_like(xs, z), np.zeros_like(xs)], axis=1)
        dist = np.arange(len(xs)) * D.TRACK_STEP
        paths.append({"xyz": xyz, "hittable": np.ones(len(xs), bool), "dist": dist, "length": float(dist[-1])})
    t = D.Track.__new__(D.Track)
    t.paths = paths
    return t


def test_buccaneer_rear_shot_needs_track_behind_the_boat():
    """A boat 30 units off one straight lane sees it across +-65 degrees:
    nothing is ever in the cone behind it. Between two lanes it always is."""
    fov = _weapon("buccaneer", (2, 0, 2), index=1)["target_fov"]       # 90
    rng = D.crosspath("buccaneer", (2, 0, 2))["range"]                   # 71
    assert D.Track.behind_share(_fake_track([30.0]), 0.0, 0.0, rng, fov) == 0.0
    assert D.Track.behind_share(_fake_track([30.0, -30.0]), 0.0, 0.0, rng, fov) == 1.0


def test_shoreline_boat_loses_its_rear_darts():
    tr = _fake_track([30.0])
    tr.reverse, tr.uptime = False, 1.0
    t = D.Placed("b", "buccaneer", (2, 0, 2), 0.0, 0.0)
    st = D.station_for(t, [t], tr)
    w = _weapon("buccaneer", (2, 0, 2))
    assert [s.name for s in st.sources] == ["Attack>Projectile"]
    assert abs(st.sources[0].shots - w["count"] / w["rate"]) < 1e-9     # 2.67/s, was 2 x 2.67


def test_spectre_alternates_dart_and_shell():
    """0-2-4: one barrage shot every 0.06 s, every second one a shell."""
    w = _weapon("ace", (0, 2, 4), "SpectreAttack")
    every = w["alternate"]["every"]
    darts = _sources("ace", (0, 2, 4), "SpectreAttack>SpectreDartProjectile")[0]
    shells = _sources("ace", (0, 2, 4), "SpectreAttack>BombExplosion")[0]
    assert abs(darts.shots - (1 / w["rate"]) * (1 - 1 / every)) < 1e-6   # 8.33, was 16.67
    assert abs(shells.shots - (1 / w["rate"]) / every) < 1e-6            # 8.33


def test_recursive_cluster_replaces_every_second_bomb():
    """0-0-4: 0.33 normal bombs and 0.33 recursive bombs a second."""
    w = _weapon("bomb", (0, 0, 4))
    first = [s for s in _sources("bomb", (0, 0, 4)) if s.name == "Attack>Explosion" and s.pierce == 22.0]
    assert len(first) == 1 and abs(first[0].shots - 0.5 / w["rate"]) < 1e-9, first   # was 0.67


def test_submerged_sub_throws_no_darts():
    for tiers in ((3, 0, 0), (4, 0, 2), (4, 2, 0), (5, 0, 0)):
        names = {s.name for s in _sources("sub", tiers)}
        assert not any(n.startswith("Attack>") for n in names), (tiers, names)
    assert {s.name for s in _sources("sub", (4, 0, 2))} == {"SubmergedAttack_SubmergeAttack>Pulse"}


def test_frags_hit_once_each():
    frag = _sources("bomb", (0, 0, 2), "Attack>Frag")[0]
    assert frag.pierce == 2.0 and frag.pierce_cost == {"": 1.0}
    hits = D._hit_rate(frag, D.layer("Red"), 5.0, None)          # a packed crowd
    assert abs(hits - frag.shots * 1.0) < 1e-9, hits               # one hit per frag, was two
    big = _sources("bomb", (3, 0, 2), "Attack>Frag")[0]            # 3-0-2: cost 0, pierce 3 stands
    assert big.pierce_cost == {} and D._hit_rate(big, D.layer("Red"), 5.0, None) > 2.9 * big.shots


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
