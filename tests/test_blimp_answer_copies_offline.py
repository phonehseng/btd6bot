"""The blimp check finishes the tower it placed before it places another.

Workshop Impoppable (2026-11-11 08:23, chimps_ninja_sun; journal
20261111_082329_Workshop_impoppable.jsonl): from round 35 the blimp check
read round 40's MOAB at 0.0x of the 2.5x wanted. Within seven seconds it
placed three bombs, each "bought toward new bomb 0-3-0 ($2430)", and
upgraded none of them; in rounds 38 and 39 two bare supers followed. $6,750
went into five towers without an upgrade - more than the Sticky Bomb
($6,000) the plan could not pay - and the MOAB took the one life.

Why: _dps_options rates a tower standing by the track inside its range
(next to none on Workshop's belts) but a new tower by a credit of about
2.5 x its range, since its spot is not known yet. The bare bomb's upgrade
was worth nothing in reach and a fresh bomb always looked better.

Now the towers the check placed are heard first (_copy_speaks_against): no
new copy while one of them is below the tiers wanted, and none when a
finished copy deals under a quarter of the credit from where it stands.
Run: python tests/test_blimp_answer_copies_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import mapgeom as G             # noqa: E402
from btd6bot import strategy as S            # noqa: E402
from btd6bot import threats as TH            # noqa: E402
from btd6bot.layout import LAYOUTS           # noqa: E402
from btd6bot.maplearn import MapModel        # noqa: E402

MAP, MODE, BUILD, RND, BLIMP_ROUND = "Workshop", "impoppable", "chimps_ninja_sun", 35, 40
# the live board when the check first bought (bot.log 08:23-08:29), then its first bomb
BOARD = [
    ("n1", "ninja", "3-0-2", 0.355, 0.453), ("starter", "dart", "3-2-0", 0.077, 0.598),
    ("n2", "ninja", "2-0-3", 0.516, 0.453), ("a1", "alchemist", "2-2-0", 0.478, 0.453),
    ("ninja1", "ninja", "3-0-2", 0.804, 0.598), ("dart1", "dart", "2-0-3", 0.831, 0.632),
    ("ninja2", "ninja", "2-0-0", 0.794, 0.649), ("dart2", "dart", "0-2-3", 0.318, 0.453),
]
FIRST_BOMB = ("ans_blimps_bomb", "bomb", "0-0-0", 0.617, 0.368)


def _executor(board):
    """An executor of the build on the map with `board` standing."""
    m = G.apply(MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SIM.CashGame(MODE, "obyn", m)
    g.round = RND
    ex = S.Executor(g, m, S.load_all()[BUILD], MODE, SIM.full_account())
    for tid, kind, cross, x, y in board:
        g.towers[tid] = SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    ex._init_threats()      # the round set and threat table, as Match does at the game's start
    return ex


def _new(ex, kind):
    """The check's new-tower options of one kind: [(description, tower id)]."""
    load = ex.blimp_load(BLIMP_ROUND)
    return [(o["desc"], o["steps"][0]["id"]) for o in ex._dps_options(load) if o["desc"].startswith(f"new {kind}")]


def test_the_ids_of_a_needs_copies_come_from_one_place():
    ex = _executor(BOARD)
    ids = ex._answer_copy_ids("blimps", "bomb")
    assert ids == ["ans_blimps_bomb", "ans_blimps_bomb2", "ans_blimps_bomb3"], ids
    assert len(ids) == ex.ANSWER_COPIES
    assert ex._new_tower_option("blimps", "bomb", 1000, (0, 3, 0))["steps"][0]["id"] == ids[0]


def test_no_second_bomb_while_the_first_is_bare():
    """With the first bomb standing at 0-0-0, no upgraded new bomb is
    offered: live, two more followed for $900 and none was upgraded."""
    if not TH.available():
        return
    ex = _executor(BOARD + [FIRST_BOMB])
    upgraded = [d for d, _ in _new(ex, "bomb") if not d.endswith("0-0-0")]
    assert not upgraded, upgraded


def test_an_unfinished_copy_speaks_against_and_a_finished_one_in_reach_does_not():
    """The rule itself, with the reach of the copy given by hand."""
    if not TH.available():
        return
    ex = _executor(BOARD + [FIRST_BOMB])
    load = ex.blimp_load(BLIMP_ROUND)
    track, rng = ex._track_length(), ex._range_units
    credit = TH.blimp_capacity([("__new__", "bomb", (0, 3, 0))], load, track, rng)
    assert credit > 0

    def in_reach(tid, kind):
        """As much track as a new tower is credited with."""
        return 2.5 * rng(kind)

    def out_of_reach(tid, kind):
        return 0.0

    # bare: another 0-3-0 is refused wherever it stands
    assert ex._copy_speaks_against("bomb", (0, 3, 0), credit, load, track, rng, in_reach)
    # finished and in reach: a second one may come
    ex.g.towers["ans_blimps_bomb"].tiers = [0, 3, 0]
    assert not ex._copy_speaks_against("bomb", (0, 3, 0), credit, load, track, rng, in_reach)
    # finished but with no track in its range: this map's spots do not carry that kind
    assert ex._copy_speaks_against("bomb", (0, 3, 0), credit, load, track, rng, out_of_reach)
    # a kind the check has not placed yet is never spoken against
    assert not ex._copy_speaks_against("ace", (3, 0, 0), credit, load, track, rng, out_of_reach)


def test_a_first_copy_is_still_offered():
    """Nothing placed yet: the check may still buy its first bomb."""
    if not TH.available():
        return
    ex = _executor(BOARD)
    news = _new(ex, "bomb")
    assert news and all(tid == "ans_blimps_bomb" for _, tid in news), news


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
