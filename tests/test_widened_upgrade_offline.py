"""An upgrade step keeps the tiers a tower took on another path.

Firing Range Impoppable (2026-11-11 20:27, chimps_ninja_sun, loss case
20261111_202920): reinforce bought b1 a $300 top tier (bomb 1-4-0), and the
plan step "b1 to 0-5-0" - the $31,200 MOAB Eliminator, the build's DDT
answer - read as unreachable and was skipped; round 95's DDTs took the
life. 1-4-0 can still become 1-5-0, so the step now aims there."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import strategy as S  # noqa: E402


def tower(tiers):
    return SimpleNamespace(tid="b1", kind="bomb", tiers=list(tiers))


def test_a_compatible_tier_elsewhere_is_kept():
    assert S.Executor._widened(tower((1, 4, 0)), (0, 5, 0)) == (1, 5, 0)
    assert S.Executor._widened(tower((0, 0, 2)), (0, 5, 0)) == (0, 5, 2)


def test_a_clashing_crosspath_is_left_as_written():
    assert S.Executor._widened(tower((3, 0, 0)), (0, 5, 0)) == (0, 5, 0)
    assert S.Executor._widened(tower((1, 0, 2)), (0, 5, 0)) == (0, 5, 0)


def test_the_step_now_has_a_next_tier():
    ex = S.Executor.__new__(S.Executor)
    ex.capped, ex.unread_until, ex.mode = set(), {}, "impoppable"
    ex._tier5_taken = lambda p, path: False
    nxt = ex._next_path(tower((1, 4, 0)), (0, 5, 0))
    assert nxt is not None and nxt[0] == 2, nxt


if __name__ == "__main__":
    test_a_compatible_tier_elsewhere_is_kept()
    test_a_clashing_crosspath_is_left_as_written()
    test_the_step_now_has_a_next_tier()
    print("all tests passed")
