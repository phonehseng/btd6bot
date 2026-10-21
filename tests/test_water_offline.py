"""Offline tests for the water placement scan (scanner.scan_water + MapModel
water helpers). A fake game answers probe() from a synthetic ground-truth map.
Run: python tests/test_water_offline.py (also collectable by pytest).
Never touches the game, mouse or keyboard."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from btd6bot import maplearn as ML  # noqa: E402
from btd6bot.maplearn import GRID, MapModel  # noqa: E402
from btd6bot.scanner import scan_placement, scan_water  # noqa: E402

W, H = GRID
STEP = 5
LAND, WATER, TRACK, ROCK = 0, 1, 2, 3
PRICES = {"dart": 200, "sub": 325}


def ground_truth():
    g = np.full((H, W), LAND, np.uint8)
    g[50:56, :] = TRACK            # thin track band across the map
    g[70:101, 20:71] = WATER       # big lake
    g[20:28, 110:151] = WATER      # thin river: looks like track to track_guess
    g[15:31, 20:41] = ROCK         # land-blocked scenery that is not water either
    return g


class FakeScreen:
    def __init__(self, covered=()):
        self.covered = set(covered)  # lattice points hidden behind another window

    def owns_point(self, fx, fy):
        return (int(fx * W), int(fy * H)) not in self.covered


class FakeGame:
    """probe() answers from the ground truth for the tower currently held."""

    def __init__(self, truth, cash=1000, drop_after=None, covered=()):
        self.truth = truth
        self.s = FakeScreen(covered)
        self.cash = cash
        self.held = None
        self.probes = []           # (kind, cx, cy)
        self.holds = 0
        self.drop_after = drop_after  # drop the tower after this many probes

    def fresh(self):
        return None

    def cash_stable(self):
        return self.cash

    def price(self, kind):
        return PRICES[kind]

    def hold(self, kind):
        self.held = None
        if self.cash < PRICES[kind]:
            return False            # the game will not let us pick it up
        self.held = kind
        self.holds += 1
        return True

    def is_holding(self):
        return self.held is not None

    def cancel_hold(self):
        self.held = None

    def probe(self, fx, fy, baseline=None, settle=0.06):
        cx, cy = int(fx * W), int(fy * H)
        if self.held is None:
            return True             # no tower -> no red circle -> reads "ok"
        self.probes.append((self.held, cx, cy))
        if self.drop_after is not None and len(self.probes) >= self.drop_after:
            self.drop_after = None
            self.held = None        # e.g. a stray click dropped the tower
        t = self.truth[cy, cx]
        return bool(t == LAND) if self.held == "dart" else bool(t == WATER)


def lattice():
    return [(cx, cy) for cy in range(STEP // 2, H, STEP) for cx in range(STEP // 2, W, STEP)]


def land_scanned_model(truth):
    m = MapModel("synthetic water", (0.0, 0.0, 1.0, 1.0))
    g = FakeGame(truth)
    assert scan_placement(g, m, "dart", "land", step=STEP)
    assert m.scanned("land")
    return m


def learn_track(m, truth):
    """Pretend bloons were traced along the real track."""
    m.heat[truth == TRACK] = 50.0
    m.rounds_traced = 3


def check_grid(m, truth, probed):
    """Every probed lattice point is recorded correctly; land-ok -> 2."""
    land = m.scan["land"]
    water = m.scan["water"]
    for cx, cy in probed:
        assert water[cy, cx] == (1 if truth[cy, cx] == WATER else 2), (cx, cy)
    assert (water[land == 1] == 2).all(), "land-placeable cells must be non-water"
    # nothing land-placeable may ever be offered to a water tower
    assert not (m.water_cells() & (land == 1)).any()


# --------------------------------------------------------------------- tests

def test_probes_only_land_blocked_off_track():
    truth = ground_truth()
    m = land_scanned_model(truth)
    land = m.scan["land"]
    g = FakeGame(truth)
    done = scan_water(g, m, "sub", step=STEP)
    assert done
    pts = [(cx, cy) for k, cx, cy in g.probes]
    assert all(k == "sub" for k, _, _ in g.probes)
    assert len(pts) == len(set(pts)), "a point was probed twice"
    guess = m.track_estimate()
    hits = {p for p in pts if truth[p[1], p[0]] == WATER}
    for cx, cy in pts:
        assert land[cy, cx] == 2, f"probed land-placeable cell {(cx, cy)}"
        if guess[cy, cx]:
            # only allowed as a flood-fill neighbour of a water hit
            assert any(abs(cx - hx) + abs(cy - hy) == STEP for hx, hy in hits), (cx, cy)
    # never probes the real track except where it touches water
    for cx, cy in pts:
        if truth[cy, cx] == TRACK:
            assert any(abs(cx - hx) + abs(cy - hy) == STEP for hx, hy in hits)
    # cheap: far fewer probes than a full sweep
    assert len(pts) < 0.35 * len(lattice()), (len(pts), len(lattice()))
    check_grid(m, truth, pts)
    # the lake is found in full (flood fill recovers the rim the guess swallowed)
    lake_pts = [(cx, cy) for cx, cy in lattice() if truth[cy, cx] == WATER and cx < 100]
    assert all(m.scan["water"][cy, cx] == 1 for cx, cy in lake_pts)
    assert m.has_water()


def test_learned_track_finds_thin_river_incrementally():
    truth = ground_truth()
    m = land_scanned_model(truth)
    scan_water(FakeGame(truth), m, "sub", step=STEP)
    river_pts = [(cx, cy) for cx, cy in lattice() if truth[cy, cx] == WATER and cx >= 100]
    assert river_pts
    # the river looks like track before any bloon has been seen
    missed = [p for p in river_pts if m.scan["water"][p[1], p[0]] != 1]
    assert missed, "synthetic river should be swallowed by track_guess"
    learn_track(m, truth)
    assert m.water_pending(STEP) > 0
    g2 = FakeGame(truth)
    assert scan_water(g2, m, "sub", step=STEP)
    pts2 = [(cx, cy) for _, cx, cy in g2.probes]
    assert pts2 and len(pts2) < 0.2 * len(lattice()), "second pass must only fill gaps"
    track = m.track_mask()
    hits = {p for p in pts2 if truth[p[1], p[0]] == WATER}
    for cx, cy in pts2:
        assert m.scan["land"][cy, cx] == 2
        if track[cy, cx]:
            assert any(abs(cx - hx) + abs(cy - hy) == STEP for hx, hy in hits)
    assert all(m.scan["water"][cy, cx] == 1 for cx, cy in river_pts)
    assert m.water_pending(STEP) == 0
    # a third call has nothing to do and does not even pick the tower up
    g3 = FakeGame(truth)
    assert scan_water(g3, m, "sub", step=STEP) and not g3.probes and g3.holds == 0


def test_unaffordable_sub_returns_false():
    truth = ground_truth()
    m = land_scanned_model(truth)
    g = FakeGame(truth, cash=100)
    assert scan_water(g, m, "sub", step=STEP) is False
    assert not g.probes and "water" not in m.scan
    assert not m.water_scanned()


def test_hold_failure_returns_false():
    truth = ground_truth()
    m = land_scanned_model(truth)
    g = FakeGame(truth)
    g.hold = lambda kind: False  # e.g. hotkey did nothing
    assert scan_water(g, m, "sub", step=STEP) is False
    assert "water" not in m.scan


def test_needs_land_scan():
    m = MapModel("synthetic water", (0.0, 0.0, 1.0, 1.0))
    g = FakeGame(ground_truth())
    assert scan_water(g, m) is False and not g.probes


def test_dropped_tower_does_not_fake_water():
    truth = ground_truth()
    m = land_scanned_model(truth)
    g = FakeGame(truth, drop_after=10)
    assert scan_water(g, m, "sub", step=STEP)
    assert g.holds == 2
    ref = land_scanned_model(truth)
    scan_water(FakeGame(truth), ref, "sub", step=STEP)
    assert (m.scan["water"] == ref.scan["water"]).all()


def test_covered_points_stay_unknown_and_retry():
    truth = ground_truth()
    m = land_scanned_model(truth)
    cov = (32, 77)  # a lake point behind an overlay window
    assert truth[cov[1], cov[0]] == WATER
    assert scan_water(FakeGame(truth, covered=[cov]), m, "sub", step=STEP) is False
    assert m.scan["water"][cov[1], cov[0]] == 0
    assert m.blocked("water")[cov[1], cov[0]], "unknown must be blocked for water"
    g2 = FakeGame(truth)
    assert scan_water(g2, m, "sub", step=STEP)
    assert [(cx, cy) for _, cx, cy in g2.probes] == [cov]
    assert m.scan["water"][cov[1], cov[0]] == 1


def test_blocked_semantics():
    truth = ground_truth()
    m = MapModel("synthetic water", (0.0, 0.0, 1.0, 1.0))
    assert not m.blocked("water").any() and not m.has_water()
    m = land_scanned_model(truth)
    land = m.scan["land"]
    # no water scan yet: land-placeable cells are already known not to be water
    assert (m.blocked("water") == (land == 1)).all()
    assert (m.blocked("land") == (land == 2)).all()
    scan_water(FakeGame(truth), m, "sub", step=STEP)
    bw = m.blocked("water")
    assert (bw == (m.scan["water"] != 1)).all()
    assert (m.water_cells() == ~bw).all()
    assert m.scanned("water")
    # land semantics unchanged by the water scan
    assert (m.blocked("land") == (land == 2)).all()
    # score_spots for water only offers water cells
    cover = m.score_spots(20, placement="water")
    assert (cover[bw] == -1).all()
    assert (cover > 0).any()


def test_no_water_map():
    truth = ground_truth()
    truth[truth == WATER] = ROCK
    m = land_scanned_model(truth)
    assert scan_water(FakeGame(truth), m, "sub", step=STEP)
    assert m.water_scanned() and not m.has_water() and not m.water_cells().any()
    assert m.blocked("water").all()


def test_save_load_roundtrip_and_old_files(tmp_dir=None):
    import tempfile
    truth = ground_truth()
    old = ML.DATA
    with tempfile.TemporaryDirectory() as d:
        ML.DATA = Path(d)
        try:
            m = land_scanned_model(truth)
            scan_water(FakeGame(truth), m, "sub", step=STEP)
            assert m.save()
            m2 = MapModel.load(m.name, m.playfield)
            assert set(m2.scan) == {"land", "water"}
            assert (m2.scan["water"] == m.scan["water"]).all()
            assert m2.has_water() and (m2.blocked("water") == m.blocked("water")).all()
        finally:
            ML.DATA = old
    # existing saved maps (land scan only) still load and behave as before
    for f in sorted(old.glob("*.npz")):
        if f.name.endswith(".tmp.npz"):
            continue
        d = np.load(f, allow_pickle=False)
        if "scan_land" not in d.files:
            continue
        mm = MapModel("x", (0.0, 0.0, 1.0, 1.0))
        mm.scan["land"] = d["scan_land"]
        mm.heat = d["heat"]
        assert not mm.water_scanned() and not mm.has_water()
        assert (mm.blocked("land") == (d["scan_land"] == 2)).all()
        assert (mm.blocked("water") == (d["scan_land"] == 1)).all()
        mm.water_pending()  # runs on real data


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
