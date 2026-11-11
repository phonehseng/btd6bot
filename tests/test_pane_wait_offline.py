"""A plan tower with no spot under the open pane waits for the next pane.

Covered Garden Impoppable (2026-11-11 12:52, chimps_ninja_sun): only a
quarter of the garden takes towers in any one round. n1, the build's first
ninja, found "no spot" four seconds into round 6 under the pane that had just
opened and was given up for the whole game; the alchemist and the discount
village that name it (`near: [n1]`) went astray or were given up after it.
Under the pane of a later round the same search has its best spots.

Offline: the executor on the map's real geometry with a fake game; the spot
search is made to come back empty under chosen panes.
Run: python tests/test_pane_wait_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L, mapgeom       # noqa: E402
from btd6bot import strategy as S              # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

PF = L.get(1920, 1200)["playfield"]
MAP = "Covered Garden"
CASH = 5000


def executor(empty_panes, map_name=MAP):
    """chimps_ninja_sun in Impoppable on the map's own geometry. The spot
    search finds nothing while one of `empty_panes` is open (every search on
    a map without panes when `empty_panes` is None); `ex.searches` counts the
    searches made. None when the map file is not there."""
    geom = mapgeom.load(map_name)
    if geom is None:
        return None
    model = mapgeom.apply(MapModel(map_name, PF), geom)
    ex = S.Executor(F.FakeGame(hero="obyn"), model, S.load_all()["chimps_ninja_sun"], "impoppable",
                    F.full_account())
    real, ex.searches = ex._spots_widening, 0

    def search(kind, step):
        ex.searches += 1
        pane = ex._open_pane()
        if empty_panes is None or (pane is not None and pane[0] in empty_panes):
            return []
        return real(kind, step)

    ex._spots_widening = search
    # The one probe of a doubtful spot per kind is spent beforehand: on this
    # map it goes onto ground under a shut pane (docs/backlog.md 77), which
    # the fake game would accept and the real one refuses.
    ex.__dict__.setdefault("_probed", set()).add(("ninja", -1, -1))
    return ex


def pane_in(ex, rnd):
    """The pane open in round `rnd` (offline the round decides)."""
    cycle = mapgeom.grids_for(ex.m)["panes"][0][0]
    return mapgeom.pane_open(cycle, rnd)


def n1_step(ex):
    return next(st for st in ex.plan if st.get("do") == "place" and st.get("id") == "n1")


def look(ex, step, rnd):
    """One look at `step` in round `rnd`, its pause over."""
    ex.retry_at.clear()
    ex.now_round = rnd
    return ex.try_step(step, CASH, rnd)


def test_the_map_has_four_panes_and_other_maps_none():
    ex = executor(())
    if ex is None:
        print("skip: no Covered Garden geometry")
        return
    ex.now_round = 6
    assert ex._open_pane() == (pane_in(ex, 6), 4)
    other = executor((), "Monkey Meadow")
    if other is not None:
        other.now_round = 6
        assert other._open_pane() is None


def test_a_plan_tower_with_no_spot_waits_and_stands_under_the_next_pane():
    probe = executor(())
    if probe is None:
        return
    ex = executor({pane_in(probe, 6)})
    n1 = n1_step(ex)
    key = ex._step_key(n1)
    assert look(ex, n1, 6) == "skip"
    assert key not in ex.dead_steps, "set aside, not given up"
    assert n1 in ex.deferred and ex.searches == 1
    # the same pane is not searched again, however often the step is looked at
    for _ in range(5):
        assert look(ex, n1, 6) == "skip"
    assert ex.searches == 1 and key not in ex.dead_steps
    # the next round opens another pane: the tower stands, on ground open now
    assert look(ex, n1, 7) == "bought"
    p = ex.g.towers["n1"]
    assert mapgeom.pane_at(ex.m, p.x, p.y, 7)[1], "placed on ground that is open in round 7"
    assert key not in ex.pane_empty


def test_a_tower_no_pane_has_ground_for_is_given_up_after_one_cycle():
    ex = executor({0, 1, 2, 3})
    if ex is None:
        return
    n1 = n1_step(ex)
    key = ex._step_key(n1)
    for rnd in (6, 7, 8):
        assert look(ex, n1, rnd) == "skip"
        assert key not in ex.dead_steps, rnd
    assert look(ex, n1, 9) == "skip"
    assert key in ex.dead_steps, "all four panes tried"
    assert ex.searches == 4


def test_fill_and_answer_steps_are_given_up_as_before():
    """They are offered again every tick by whoever runs them; a wait of
    their own would only fill the deferred list."""
    ex = executor({0, 1, 2, 3})
    if ex is None:
        return
    answer = {"do": "place", "id": "ans_blimps_bomb", "kind": "bomb", "role": "dps", "segment": [0.0, 0.7]}
    assert look(ex, dict(answer), 6) == "skip"
    assert ex._step_key(answer) in ex.dead_steps and not ex.deferred


def test_on_a_map_without_panes_the_step_is_given_up_at_once():
    ex = executor(None, "Monkey Meadow")
    if ex is None:
        return
    ex.no_removals = True
    n1 = n1_step(ex)
    assert look(ex, n1, 6) == "skip"
    assert ex._step_key(n1) in ex.dead_steps and not ex.pane_empty


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
