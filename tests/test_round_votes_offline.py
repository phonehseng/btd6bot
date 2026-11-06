"""Round tracking catches up with a game that moved on (no game needed).

Geared Medium (2026-11-03): ticks of 10-15 s of refused placement clicks let
the game run more than two rounds between two HUD readings. Readings only
counted as agreeing when identical, every reading was different, and the
tracked round stayed at 23 while the game was lost at round 40.
  * steadily rising readings that the elapsed time explains are adopted
    after RoundVotes.PLAUSIBLE_VOTES readings;
  * a misread far ahead ('11' -> '711') still needs BIG_VOTES identical reads;
  * a small backwards correction still needs SMALL_VOTES.
Run: python tests/test_round_votes_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.match import RoundVotes  # noqa: E402


def test_rising_reads_are_adopted():
    v = RoundVotes()
    # the Geared game: tracked round 23, readings 12 s apart, game 2-3 rounds on each time
    results = [v.vote(r, 23, t) for r, t in ((26, 12), (28, 24), (31, 36))]
    assert results == [False, False, True], results
    print("ok rising readings catch up after", RoundVotes.PLAUSIBLE_VOTES, "reads")


def test_ocr_misread_needs_many_votes():
    v = RoundVotes()
    # '11' read as '711' a few seconds after round 11 began: not plausible
    for _ in range(RoundVotes.BIG_VOTES - 1):
        assert not v.vote(711, 11, 5.0)
    assert v.vote(711, 11, 5.0)
    print("ok a far misread needs", RoundVotes.BIG_VOTES, "agreeing reads")


def test_small_backwards_correction():
    v = RoundVotes()
    for _ in range(RoundVotes.SMALL_VOTES - 1):
        assert not v.vote(20, 22, 30.0)
    assert v.vote(20, 22, 30.0)
    print("ok a backwards correction needs", RoundVotes.SMALL_VOTES, "reads")


def test_jumping_reads_restart_the_count():
    v = RoundVotes()
    assert not v.vote(30, 23, 40.0)
    assert not v.vote(25, 23, 40.0)   # went backwards: a new candidate
    assert not v.vote(26, 23, 40.0)
    assert v.vote(27, 23, 40.0)
    print("ok a reading that goes backwards restarts the count")


def test_continuous_rounds_catch_up():
    # Party Parade Apopalypse (2026-11-06): tracked round 49, the game two
    # rounds further every 3 s. With the 3 s floor the third reading (7
    # rounds on after 12 s) looks implausible and would need BIG_VOTES reads
    reads = ((52, 6.0), (54, 9.0), (56, 12.0))
    standard = RoundVotes()
    assert [standard.vote(r, 49, t) for r, t in reads] == [False, False, False]
    continuous = RoundVotes(continuous=True)
    assert [continuous.vote(r, 49, t) for r, t in reads] == [False, False, True]
    # a far misread is still not plausible under continuous sends
    v = RoundVotes(continuous=True)
    assert not any(v.vote(711, 49, 5.0) for _ in range(RoundVotes.BIG_VOTES - 1))
    print("ok under continuous sends fast rounds are caught up with")


def test_first_read_is_taken():
    assert RoundVotes().vote(15, None, 0.0)
    print("ok with no round tracked yet the first reading is taken")


if __name__ == "__main__":
    test_rising_reads_are_adopted()
    test_ocr_misread_needs_many_votes()
    test_small_backwards_correction()
    test_jumping_reads_restart_the_count()
    test_continuous_rounds_catch_up()
    test_first_read_is_taken()
    print("ALL OK")
