"""A tower's reach counts each track cell as the share of rounds that use it.

Last Resort sends every round along the top straight and then round by round
down one of four routes (big loop, medium loop, small loop, straight across:
mapgeom.path_round_shares gives each a quarter). Spots have been scored with
those shares since 2026-11-10 (MapModel.track_weight), but the reach floor
(Executor.MIN_REACH_SHARE: a spot must reach 45% of what the best legal spot
reaches) still counted every track cell alike. A ninja beside the big loop
has 282 cells in range, the one legal patch left beside the top straight
126, so that patch - the best-scored spot on the map - was dropped as "its
range only grazes the track" and the ninjas, the alchemist and the darts all
stood by the big loop, out of reach on three rounds in four.

Every game the bot lost on Last Resort ended on a small-loop or straight
round; the two of 2026-11-12 are cases 20261112_111354_LastResort_
primary_only (round 32, a 0-2-4 dart with $2,901 in it "has not popped a
single bloon in 17 rounds") and 20261112_111733_LastResort_abr (rounds 27
and 28 took all 100 lives while two ninjas and an alchemist stood by the big
loop's bottom row).

The tests place on the map's own geometry (no learned file), so they do not
change with the games the bot plays. The live game has refused nearly all
the ground the map file allows beside the straight (473 refused land cells
in data/maps/lastresort.npz on 2026-11-12; only the top of the left strip is
left, 19 ninja cells), so the two placement tests refuse that ground here
as well (_like_the_live_map).
Run: python tests/test_reach_round_share_offline.py"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as ST  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

MAP = "Last Resort"
N1 = {"do": "place", "id": "n1", "kind": "ninja", "role": "dps", "segment": [0.0, 0.5]}


# The left strip of land outside the big loop: grid columns left of the big
# loop's left column of track (the loop's leftmost track cell is at column 21).
LEFT_STRIP_COLUMNS = 16
# ... and the first grid row of that strip the live game still accepts: the
# rows above it (21-23, nearest the straight) are refused in the live file,
# which leaves cell (4, 24) as the strip's best - where the hero stood in
# both games of 2026-11-12 (0.024, 0.266-0.283).
LIVE_STRIP_TOP_ROW = 24
# ... and the last grid column the live map leaves a ninja there in reach of
# the straight (the columns towards the big loop's left side are refused).
# At (4, 24) a ninja has 126 track cells in range, counted alike; the floor
# was 126.9.
LIVE_STRIP_LAST_COLUMN = 4


def _executor(map_name=MAP, fresh=False):
    """An Executor on the map's geometry with an empty board, as the offline
    replay builds it (simulate_threats.simulate). fresh: on a model of its
    own, for a test that changes it."""
    if fresh:
        ST._MAP_MODELS.pop((map_name, False), None)
    model = ST.map_model(map_name)
    if fresh:
        ST._MAP_MODELS.pop((map_name, False), None)      # the next caller gets an unchanged one
    game = ST.CashGame("hard", "obyn", model)
    game.cash, game.round = 9700, 22
    return S.Executor(game, model, S.load_all()["abr_ninja_alch"], "abr", ST.full_account()), model


def _every_round_cells(model, cx, cy, range_cells):
    """Track cells every round's bloons pass (round share 1) within range of a cell."""
    every = model.track_weight() >= 0.99
    yy, xx = np.mgrid[0:every.shape[0], 0:every.shape[1]]
    return int((every & ((xx - cx) ** 2 + (yy - cy) ** 2 <= range_cells ** 2)).sum())


def _like_the_live_map():
    """(executor, model, cells) with the ground beside the straight refused
    everywhere but on the left strip, as the live game refused it; cells:
    the legal ninja cells left in reach of the straight, [(cx, cy)]."""
    ex, model = _executor(fresh=True)
    rc = ex._range_cells("ninja")
    ys, xs = np.nonzero(ex._legal_cells("ninja"))
    for cy, cx in zip(ys, xs):
        beside = _every_round_cells(model, cx, cy, rc) > 0
        if (cx > LIVE_STRIP_LAST_COLUMN and beside) or (cx < LEFT_STRIP_COLUMNS and cy < LIVE_STRIP_TOP_ROW):
            model.refuse("land", int(cx), int(cy), r=0)
    ex, _ = _executor_on(model)
    ys, xs = np.nonzero(ex._legal_cells("ninja"))
    return ex, model, [(cx, cy) for cy, cx in zip(ys, xs) if _every_round_cells(model, cx, cy, rc) > 0]


def _executor_on(model):
    """A new Executor (its legal-ground and reach caches empty) on `model`."""
    game = ST.CashGame("hard", "obyn", model)
    game.cash, game.round = 9700, 22
    return S.Executor(game, model, S.load_all()["abr_ninja_alch"], "abr", ST.full_account()), model


def test_reach_weights_cells_by_their_share_of_the_rounds():
    ex, model = _executor()
    share = model.round_share()
    assert share is not None, "Last Resort's routes take turns: the model must say so"
    reach = ex._reach("ninja")
    plain = (model.t_cnt > 0).astype(np.float32)
    # a cell in the middle of the big loop's bottom row has only quarter-share track in range
    ys, xs = np.nonzero((plain > 0) & (share < 0.3))
    cy, cx = int(ys.max()), int(xs[ys == ys.max()].mean())      # on the bottom row
    r = int(round(ex._range_cells("ninja")))
    yy, xx = np.mgrid[0:plain.shape[0], 0:plain.shape[1]]
    disc = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    assert reach[cy, cx] < 0.6 * plain[disc].sum(), (reach[cy, cx], plain[disc].sum())


def test_a_spot_beside_the_shared_straight_passes_the_reach_floor():
    ex, model, beside = _like_the_live_map()
    assert beside and all(cx < LEFT_STRIP_COLUMNS for cx, _ in beside), \
        "the left strip has legal ninja ground in reach of the top straight"
    reach, floor = ex._reach("ninja"), ex._reach_floor("ninja", ex._legal_cells("ninja"))
    assert any(reach[cy, cx] >= floor for cx, cy in beside), \
        f"every spot beside the straight is under the floor {floor:.0f}"


def test_the_first_ninja_stands_where_every_round_passes():
    ex, model, _ = _like_the_live_map()
    valid = ex._legal_cells("ninja")
    # the live game refuses the probes of blocked ground: the first legal spot counts
    legal = [(cx, cy) for cx, cy, _ in ex.pick_spots("ninja", N1, 4) if valid[cy, cx]]
    assert legal, "no legal spot offered for the first ninja"
    cx, cy = legal[0]
    assert _every_round_cells(model, cx, cy, ex._range_cells("ninja")) > 0, \
        f"n1 at cell ({cx},{cy}) reaches no track that every round uses"


def test_maps_whose_routes_all_run_every_round_count_cells_as_before():
    ex, model = _executor("Monkey Meadow")
    assert model.round_share() is None
    reach = ex._reach("ninja")
    plain = (model.t_cnt > 0).astype(np.float32)
    assert ex._round_share_grid(plain) is None
    assert float(reach.max()) <= float(plain.sum()) and float(reach.max()) > 0
    assert float(reach.max()) == float(int(reach.max())), "whole cells: no weighting applied"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
