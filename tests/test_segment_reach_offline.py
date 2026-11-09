"""A track segment no legal spot reaches is dropped, not placed by noise.

Firing Range ABR (loss case 20261104_035430): the opener dart's
`segment [0.05, 0.45]` is the top rows of the map, which no land cell
reaches. Every spot scored close to 0 for that segment, yet pick_spots
still returned them, so the ranking was noise. Now
Executor._segment_out_of_reach compares the segment's best score with the
best score on the whole track; under SEGMENT_REACH_SHARE, pick_spots
offers nothing and _spots_widening drops the segment.
Run: python tests/test_segment_reach_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402

PLAYFIELD = L.get(1920, 1200)["playfield"]
OPENER = {"do": "place", "id": "opener", "kind": "dart", "role": "dps",
          "segment": [0.05, 0.45]}


def _executor(map_name):
    """An Executor on the real learned map with an empty board, or None
    when the map is not learned on this machine."""
    m = MapModel.load(map_name, PLAYFIELD)
    if not m.known():
        return None
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), m, plan, "hard", F.full_account())
    ex.g.towers = {}
    ex.__dict__["_probed"] = {("dart", -1, -1)}     # no probe spot in the way
    return ex


def _share(ex, step):
    """The segment's best score over the whole track's best, as the
    executor sees it for this step (None when nothing reaches any track)."""
    kind = step["kind"]
    rc = min(ex._range_cells(kind), 60)
    valid = ex._legal_cells(kind)
    block = ex._keep_off_scarce(kind, valid, ex.blocked)
    covered = ex._covered()
    seg = ex.m.score_spots(rc, tuple(step["segment"]), ex._occupied(), extra_block=block,
                           covered=covered, valid=valid)
    whole = ex.m.score_spots(rc, (0.0, 1.0), ex._occupied(), extra_block=block,
                             covered=covered, valid=valid)
    return None if whole.max() <= 0 else max(0.0, float(seg.max())) / float(whole.max())


def test_reachable_segments_still_place():
    """On ordinary maps the opener's early segment is in reach: the rule
    must not fire and pick_spots still returns spots for it."""
    for name in ("Monkey Meadow", "Logs", "Cubism", "Spillway"):
        ex = _executor(name)
        if ex is None:
            continue
        share = _share(ex, OPENER)
        assert share is None or share >= ex.SEGMENT_REACH_SHARE, (name, share)
        assert ex.pick_spots("dart", dict(OPENER), n=3), name


def test_unreachable_segment_offers_nothing():
    """A segment whose best legal spot covers almost none of its track gives
    no spots, and the widened search (segment dropped) does."""
    found = False
    for name in ("Firing Range", "Monkey Meadow", "Logs", "Cubism"):
        ex = _executor(name)
        if ex is None:
            continue
        # the last sliver of track before the exit: tiny on every map, so
        # only spots grazing it would score at all
        for seg in ([0.05, 0.45], [0.995, 1.0]):
            step = dict(OPENER, segment=seg)
            share = _share(ex, step)
            if share is None or share >= ex.SEGMENT_REACH_SHARE:
                continue
            found = True
            assert ex.pick_spots("dart", dict(step), n=3) == [], (name, seg, share)
            spots = ex._spots_widening("dart", dict(step))
            assert spots, (name, seg, "the widened search found nothing")
    if not found:
        print("(no learned map here has an out-of-reach segment - nothing to check)")


def test_steps_with_their_own_rules_are_not_judged():
    """A researched spot, the exit role and the whole track never count as
    out of reach, whatever the scores."""
    ex = _executor("Monkey Meadow") or _executor("Logs")
    if ex is None:
        return
    import numpy as np
    zero = np.zeros((2, 2), np.float32)
    args = ("dart", None, zero, 10, "land", None, None, None)
    def judge(step, role="dps", only=None):
        kind, _, cover, rc, placement, block, covered, valid = args
        return ex._segment_out_of_reach(kind, step, role, only, cover, rc, placement,
                                        block, covered, valid)
    assert not judge(dict(OPENER, at=[0.5, 0.5]))
    assert not judge(OPENER, role="exit")
    assert not judge(OPENER, only=np.ones((2, 2), bool))
    assert not judge(dict(OPENER, segment=[0.0, 1.0]))
    assert not judge({k: v for k, v in OPENER.items() if k != "segment"})


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
