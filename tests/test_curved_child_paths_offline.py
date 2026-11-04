"""A polyline path whose child carries its own CurvedLineNodes spline -
no game needed.

Spring Spring's three paths are polylines: an entry node, a child named
"Curved" with 21-24 spline nodes looping round the islands, and an exit
node. The reader used to treat every child with children as one Bezier
curve, so those loops shrank to a single arc across the islands and towers
placed beside it popped nothing (Spring Spring ABR, 2026-11-03). Here a
fake scene holds the same layout with the spline nodes on a half circle:
the read track must follow the circle, while a plain Curve child (no spline
component) keeps its Bezier reading.
Run: python tests/test_curved_child_paths_offline.py"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import gamefiles  # noqa: E402

RADIUS = 100.0


class FakeScene:
    """Just enough of gamefiles._Scene for _read_paths: transforms with
    children, game objects, and MonoBehaviours by class."""

    def __init__(self):
        self.transforms, self.go_transform, self.go_name = {}, {}, {}
        self.script, self._trees, self._pos = {}, {}, {}
        self._next = 1

    def _id(self):
        self._next += 1
        return self._next

    def node(self, parent_tid, pos, name="LineNode"):
        """A game object with a transform at world position pos; returns
        (game object id, transform id)."""
        go, tid = self._id(), self._id()
        self.go_name[go] = name
        self.go_transform[go] = tid
        self.transforms[tid] = {"m_GameObject": {"m_PathID": go}, "m_Children": [],
                                "m_Father": {"m_PathID": parent_tid or 0}}
        if parent_tid:
            self.transforms[parent_tid]["m_Children"].append({"m_PathID": tid})
        self._pos[tid] = np.array(pos, float)
        return go, tid

    def component(self, cls, go, **fields):
        pid = self._id()
        self.script[pid] = ("Assets.Scripts.Unity.Map", cls)
        self._trees[pid] = {"m_GameObject": {"m_PathID": go}, **fields}
        return pid

    # the _Scene interface _read_paths uses
    def ids(self, cls):
        return [pid for pid, (_, c) in self.script.items() if c == cls]

    def components(self, cls):
        return [self._trees[pid] for pid in self.ids(cls)]

    def tree(self, pid):
        return self._trees[pid]

    def go_of(self, pid):
        return self._trees[pid]["m_GameObject"]["m_PathID"]

    def world(self, tid):
        return self._pos[tid]


def half_circle(n):
    """n Unity points (x, height, z) on a half circle of RADIUS round the
    origin, from (-R, 0) over (0, R) to (R, 0)."""
    return [(-RADIUS * math.cos(a), 0.0, RADIUS * math.sin(a)) for a in np.linspace(0, math.pi, n)]


def build(child_kind):
    """A polyline path: entry node, a child holding a half circle of nodes
    (with a CurvedLineNodes component when child_kind says so), exit node."""
    sc = FakeScene()
    go, root = sc.node(None, (0, 0, 0), name="Path1")
    sc.component("Path", go, isActive=1, isHidden=0)
    sc.component("PolyLineNodes", go, close=0)
    sc.node(root, (-2 * RADIUS, 0, 0))
    cgo, ctid = sc.node(root, (0, 0, 0), name="Curved")
    if child_kind == "CurvedLineNodes":
        sc.component("CurvedLineNodes", cgo, close=0, samplesPer100Units=100)
    for p in half_circle(9):
        sc.node(ctid, p)
    sc.node(root, (2 * RADIUS, 0, 0))
    return sc


def distance_from_circle(points):
    """Largest gap between the read track's middle part and the circle."""
    pts = np.array([p for p in points if abs(p[0]) < RADIUS * 0.9], float)   # [x, z, height]
    return float(np.abs(np.hypot(pts[:, 0], pts[:, 1]) - RADIUS).max())


def test_spline_child_follows_its_nodes():
    path = gamefiles._read_paths(build("CurvedLineNodes"))[0]
    gap = distance_from_circle(path["points"])
    assert gap < 2.0, f"the spline child strays {gap:.1f} units from its nodes' circle"
    assert len(path["points"]) > 100, "a spline is resampled every unit, not 16 times"


def test_plain_curve_child_stays_bezier():
    # a Bezier through 9 control points on a circle cuts well inside it:
    # that reading is right for a plain Curve child, and must not change
    path = gamefiles._read_paths(build(None))[0]
    assert len(path["points"]) == 2 + 16
    assert distance_from_circle(path["points"]) > 5.0


if __name__ == "__main__":
    test_spline_child_follows_its_nodes()
    test_plain_curve_child_stays_bezier()
    print("curved child paths: OK")
