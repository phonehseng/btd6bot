"""Refused spots and towers that are not there, for strategy.Executor and the
map model (no game needed).

Covers the log audit of 2026-10-22:
  * a fill or panic step whose spots keep being refused is given up for the
    game once (516 refused-spot probes and 136 "giving up" lines in one log:
    fill steps re-ran every tick, panic copies never added up their failures);
  * the hero is never given up: it is retried later at the next-best spots;
  * a tower that fails two selections in a row is forgotten and its plan step
    queued again; defended() only counts verified towers;
  * spots the game refused survive re-applying the map geometry and a
    save/load (MapModel.refused), and placement.valid_spots respects them.
Run: python tests/test_refused_spots_offline.py"""
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import maplearn, mapgeom, placement  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot.game import Placed  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

logging.getLogger("strategy").setLevel(logging.ERROR)
PF = LAYOUTS["16:10"]["playfield"]


class FakeScreen:
    width = 1920


class SpotGame:
    """Accepts a spot unless `refuses(kind)` says the game refuses that kind
    anywhere. Mirrors Game.place's contract: several spots per pick-up, every
    refused one listed in refused_spots."""

    def __init__(self, refuses=lambda kind: True, hero="quincy"):
        self.refuses = refuses
        self.hero = hero
        self.towers = {}
        self.s = FakeScreen()
        self.fail_reason = self.locked_seen = self.last_spot = None
        self.refused_spots = []
        self.holds = []          # one entry per pick-up
        self.select_ok = True

    def price(self, kind):
        return 100

    def place(self, tid, kind, fx, fy, check_valid=True, more_spots=()):
        self.holds.append(kind)
        self.refused_spots = []
        for spot in [(fx, fy), *more_spots]:
            if self.refuses(kind):
                self.refused_spots.append(spot)
                continue
            self.towers[tid] = Placed(tid, kind, *spot)
            return self.towers[tid]
        self.fail_reason = "spot"
        return None

    def select(self, p):
        if self.select_ok:
            p.verified, p.select_fails = True, 0
            return True
        p.verified, p.select_fails = False, p.select_fails + 1
        return False

    def deselect(self, p):
        pass

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        if not self.select(p):
            self.fail_reason = "select"
            return False
        p.tiers[path - 1] += 1
        return True

    def target(self, p, mode):
        return True


class GridModel:
    """Every cell is equally good unless blocked; records learned refusals."""
    W, H = 100, 60

    def __init__(self):
        self.heat = np.zeros((self.H, self.W), np.float32)
        self.refusals = []
        self.scan = {}

    def frac_to_cell(self, x, y):
        return int(x * self.W), int(y * self.H)

    def cell_to_frac(self, cx, cy):
        return (cx + 0.5) / self.W, (cy + 0.5) / self.H

    def radius_cells(self, rng, width):
        return 5

    def refuse(self, surface, cx, cy, r=1):
        self.refusals.append((surface, cx, cy))

    def score_spots(self, rc, seg, occupied, near=None, near_radius=None, placement="land",
                    extra_block=None, covered=None, valid=None):
        cover = np.ones((self.H, self.W), np.float32)
        if extra_block is not None:
            cover[extra_block] = 0
        return cover

    def best_spots(self, cover, n=12):
        idx = np.argsort(-cover, axis=None, kind="stable")[:n * 6]
        return [(int(i % self.W), int(i // self.W), float(cover.flat[i])) for i in idx
                if cover.flat[i] > 0][:n]


# The give-up logic is tested with small limits the little test grid can
# fill (the real ones, Executor.SPOTS_PER_HOLD / SPOT_LIMIT, are larger).
PER_HOLD, LIMIT = 4, 12


def executor(game, strat, mode="easy"):
    ex = S.Executor(game, GridModel(), dict({"id": "t", "modes": [mode]}, **strat), mode)
    ex.SPOTS_PER_HOLD, ex.SPOT_LIMIT = PER_HOLD, LIMIT
    return ex


def test_fill_step_is_given_up_once():
    g = SpotGame()
    ex = executor(g, {"plan": [], "fill": [{"do": "place", "kind": "tack", "role": "dps"}]})
    for _ in range(10):
        ex.tick(10000, 5)
    holds = LIMIT // PER_HOLD
    assert len(g.holds) == holds, g.holds
    assert len(ex.m.refusals) == LIMIT, "every refused spot is learned"
    assert len(ex.dead_steps) == 1


def test_panic_copies_add_up():
    """Panic steps run as fresh dict copies; their failures must still add up."""
    g = SpotGame()
    ex = executor(g, {"plan": [], "panic": [{"do": "place", "kind": "tack", "role": "dps"}]})
    for _ in range(10):
        ex.tick(10000, 5, lives_dropped=True)
    assert len(g.holds) == LIMIT // PER_HOLD, g.holds


def test_a_placement_resets_the_refusal_count():
    """A panic/fill step that still finds spots between refusals stays alive."""
    refusals = iter([True] * 8 + [False] + [True] * 100)    # one spot accepted, after 8
    g = SpotGame(refuses=lambda kind: next(refusals))
    ex = executor(g, {"plan": [], "fill": [{"do": "place", "kind": "tack", "role": "dps"}]})
    for _ in range(10):
        ex.tick(10000, 5)
    holds = LIMIT // PER_HOLD
    assert len(g.holds) == 3 + holds and ex.dead_steps, g.holds


def test_refused_spots_are_not_offered_again():
    g = SpotGame()
    ex = executor(g, {"plan": [], "fill": [{"do": "place", "kind": "tack", "role": "dps"}]})
    for _ in range(3):
        ex.tick(10000, 5)
    cells = [(cx, cy) for _, cx, cy in ex.m.refusals]
    assert len(cells) == len(set(cells)), "a refused spot was probed twice"


def test_hero_is_retried_after_refusals():
    """Tree Stump: the hero was skipped for the whole game after 4 refusals."""
    hero_ok = {"now": False}
    g = SpotGame(refuses=lambda kind: kind == "hero" and not hero_ok["now"])
    ex = executor(g, {"plan": [{"do": "place", "id": "hero", "kind": "hero", "role": "dps"},
                               {"do": "place", "id": "d1", "kind": "dart", "role": "dps"}]})
    ex.HERO_RETRY_S = 0.0
    for _ in range(4):
        ex.tick(10000, 1)
    assert "d1" in g.towers, "the rest of the plan goes on meanwhile"
    assert "hero" not in g.towers and ex.deferred
    first = LIMIT // PER_HOLD
    assert g.holds.count("hero") == first + 1, "later tries are one pick-up each"
    hero_ok["now"] = True        # e.g. the next-best spots are fine
    for _ in range(2):
        ex.tick(10000, 1)
    assert "hero" in g.towers and not ex.deferred


def test_phantom_tower_is_forgotten_and_placed_again():
    """Ancient Portal: n2 failed 8 selections of ~3 s each."""
    g = SpotGame(refuses=lambda kind: False)
    ex = executor(g, {"plan": [{"do": "place", "id": "d1", "kind": "dart", "role": "dps"},
                               {"do": "upgrade", "id": "d1", "to": "1-0-0"}]})
    ex.tick(10000, 1)                         # places d1
    phantom = g.towers["d1"]
    g.select_ok = False                       # ... but it is not really there
    ex.tick(10000, 1)                         # the upgrade cannot select it
    assert g.towers["d1"] is phantom and not ex.defended(), "doubtful after one failed selection"
    ex.tick(10000, 1)                         # fails again: forgotten, placed anew
    assert g.towers["d1"] is not phantom and g.holds == ["dart", "dart"]
    g.select_ok = True
    for _ in range(3):
        ex.tick(10000, 1)
    assert g.towers["d1"].tiers == [1, 0, 0], "placed again, then upgraded"


def test_doubtful_tower_is_rechecked_before_rounds():
    g = SpotGame(refuses=lambda kind: False)
    ex = executor(g, {"plan": []})
    g.towers["t1"] = Placed("t1", "tack", 0.3, 0.3, verified=False, select_fails=1)
    g.towers["hero"] = Placed("hero", "hero", 0.5, 0.5)
    assert not ex.defended(), "the hero alone, plus a doubtful tower, is no defence"
    g.select_ok = True
    ex.tick(10000, 1)
    assert ex.defended() and g.towers["t1"].verified


def _geometry_model(name="Logs"):
    geom = mapgeom.load(name)
    if geom is None:
        return None, None
    return mapgeom.apply(MapModel(name, PF), geom), geom


def test_refusals_survive_geometry_and_saving():
    m, geom = _geometry_model()
    if m is None:
        return                                  # no extracted geometry on this machine
    valid = placement.valid_spots(m, "dart")
    cy, cx = [int(v[len(v) // 2]) for v in np.nonzero(valid)]
    m.refuse("land", cx, cy)
    assert not placement.valid_spots(m, "dart")[cy, cx]
    assert m.blocked("land")[cy, cx]
    mapgeom.apply(m, geom)                      # what runner._use_geometry does on a revisit
    assert not placement.valid_spots(m, "dart")[cy, cx], "re-applied geometry forgot it"
    with tempfile.TemporaryDirectory() as tmp:
        saved = maplearn.DATA
        maplearn.DATA = Path(tmp)
        try:
            assert m.save()
            back = MapModel.load(m.name, PF)
        finally:
            maplearn.DATA = saved
    assert back.refused_mask("land")[cy, cx] and not back.refused_mask("water").any()


def test_many_refusals_do_not_erase_the_footprint_room():
    """Sunset Gulch / Easy: ~100 learned refusals (3x3 patches) left no legal
    cell at all, because refused cells were treated as walls in the footprint
    check. They are single cells the game said no to: only they go."""
    m, _ = _geometry_model()
    if m is None:
        return
    before = int(placement.valid_spots(m, "sniper").sum())
    for cy in range(2, m.heat.shape[0] - 2, 4):
        for cx in range(2, m.heat.shape[1] - 2, 4):
            m.refuse("land", cx, cy)
    after = placement.valid_spots(m, "sniper")
    assert after.sum() > before * 0.4, (before, int(after.sum()))
    assert not after[2, 2], "the refused cells themselves are still excluded"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
