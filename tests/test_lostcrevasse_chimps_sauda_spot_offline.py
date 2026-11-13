"""Lost Crevasse CHIMPS: Sauda opens at the guide's spot, both routes in front of her.

Why
---
The guide build opens with Sauda alone at round 6 (OneEyedDeacon: "top
middle, as high as possible"). The opening search had moved her inside the
left loop, (0.227, 0.47), where the damage model rated round 6 at 1.08
against 0.76 at the guide's spot. On 2026-11-13 07:27 she stood there and
the game was lost eleven seconds after Play: one red got out, 22 pops on
the counter (case 20261113_073019_LostCrevasse_chimps).

Sauda fights with swords, one way at a time. Inside the loop the first
route winds round her and the second passes on her other side, so the
bloons in reach are spread over more than half a turn. At the top middle
both routes enter side by side and stay in front of her. The model counts
the route in reach and not which way she faces, so it cannot choose between
the two spots; the guide's spot is taken as written.

Since 2026-11-13 11:25 she no longer opens alone: she lost round 6 at the
guide's spot too (case 20261113_111449_LostCrevasse_chimps), and the build
buys her at round 13, after a live-proven opening
(tests/test_lostcrevasse_chimps_proven_opening_offline.py). Her spot is
still the guide's.

Checked here:
  * the build's Sauda stands in the guide's area (top middle), on a cell
    that is legal for her and that the game never refused;
  * both routes pass within a sword's reach of her there;
  * the route in reach is spread over at most FRONT_DEGREES around her,
    and over more than that around the lost spot.

Run: python tests/test_lostcrevasse_chimps_sauda_spot_offline.py (no game)."""
import logging
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
import pin_spots  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

BUILD = ROOT / "strategies" / "maps" / "lostcrevasse_chimps_guide.yaml"
LOST_SPOT = (0.227, 0.47)       # where Sauda stood in the lost game (its journal)
# The guide's "top middle, as high as possible", in screen fractions.
GUIDE_AREA = {"x": (0.35, 0.55), "y": (0.0, 0.2)}
SWORD_REACH = 23.0              # Sauda's range in world units (BTD6: 23)
FRONT_DEGREES = 150.0           # the widest spread of route she can face at once


@lru_cache(maxsize=None)
def _pinner():
    return pin_spots.Pinner("Lost Crevasse", "chimps", hero="sauda")


def _sauda_spot():
    """Where the build places Sauda, in screen fractions."""
    d = yaml.safe_load(BUILD.read_text(encoding="utf-8"))
    assert d["hero"] == "sauda", d["hero"]
    step = next(st for st in d["plan"] if st["do"] == "place" and st["kind"] == "hero")
    return tuple(step["at"])


def _bearings(at):
    """One list per route: the bearings (degrees) from a tower at ``at`` to
    the route's hittable points within SWORD_REACH of it."""
    pin = _pinner()
    x, z = pin.world(pin.model.frac_to_cell(*at))
    out = []
    for path in pin.setup.track.paths:
        pts = path["xyz"][path["hittable"]]
        near = pts[np.hypot(pts[:, 0] - x, pts[:, 1] - z) <= SWORD_REACH]
        out.append([math.degrees(math.atan2(pz - z, px - x)) % 360 for px, pz in near[:, :2]])
    return out


def spread(at):
    """Degrees of the smallest arc around ``at`` that holds every route
    point in reach: a full turn less the widest empty gap."""
    angles = sorted(a for route in _bearings(at) for a in route)
    if not angles:
        return 0.0
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 360 - angles[-1]]
    return 360 - max(gaps)


def test_sauda_stands_at_the_guides_top_middle():
    x, y = _sauda_spot()
    assert GUIDE_AREA["x"][0] <= x <= GUIDE_AREA["x"][1], x
    assert GUIDE_AREA["y"][0] <= y <= GUIDE_AREA["y"][1], y


def test_her_cell_is_legal_and_never_refused():
    pin = _pinner()
    cx, cy = pin.model.frac_to_cell(*_sauda_spot())
    assert pin.legal("hero", "sauda")[cy, cx], (cx, cy)
    assert pin_spots.never_refused(pin.model, "hero", (cx, cy), "sauda"), (cx, cy)


def test_both_routes_pass_within_her_reach():
    reached = [len(route) for route in _bearings(_sauda_spot())]
    assert len(reached) == 2 and all(reached), reached


def test_the_routes_are_in_front_of_her_and_were_around_the_lost_spot():
    assert spread(_sauda_spot()) <= FRONT_DEGREES, spread(_sauda_spot())
    assert spread(LOST_SPOT) > FRONT_DEGREES, spread(LOST_SPOT)


if __name__ == "__main__":
    import inspect
    O.lower_priority()
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as exc:
                fails += 1
                print("FAIL", name, exc)
    sys.exit(1 if fails else 0)
