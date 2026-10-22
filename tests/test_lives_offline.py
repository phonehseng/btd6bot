"""match.LivesTracker: the confirmed lives count from noisy HUD reads (no game).

Before: a read more than +50 above the confirmed count was always ignored, so
one wrong LOW value, once confirmed, made every true read "too high" for the
rest of the game and leaks (panic buying) were never noticed again.
Run: python tests/test_lives_offline.py"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.match import LivesTracker  # noqa: E402

logging.getLogger("match").setLevel(logging.ERROR)


def feed(tracker, reads):
    """Total lives lost over the reads."""
    return sum(tracker.update(r) for r in reads)


def test_leaks_are_counted():
    t = LivesTracker(150)
    feed(t, [150, 150, 150])
    assert feed(t, [140, 140, 140]) == 10 and t.confirmed == 140


def test_one_flicker_is_not_a_leak():
    t = LivesTracker(150)
    feed(t, [121, 121, 120, 121, 121])
    assert t.confirmed == 121


def test_wrong_low_first_read_is_corrected():
    """A first read of 15 for 150 used to stick for the whole game."""
    t = LivesTracker(150)
    t.update(15)
    assert t.confirmed == 15
    feed(t, [150] * LivesTracker.RISE_VOTES)
    assert t.confirmed == 150
    assert feed(t, [130, 130, 130]) == 20, "leaks are seen again after the correction"


def test_one_high_misread_is_ignored():
    t = LivesTracker(150)
    feed(t, [150, 150])
    assert feed(t, [150 + 60, 150, 150]) == 0 and t.confirmed == 150


def test_steady_impossible_read_is_never_believed():
    """Easy's 200 was read as '2001' for a whole game."""
    t = LivesTracker(200)
    feed(t, [200, 200])
    feed(t, [2001] * 20)
    assert t.confirmed == 200


def test_impossible_first_read_is_ignored():
    t = LivesTracker(200)
    assert t.update(2001) == 0 and t.confirmed is None
    t.update(200)
    assert t.confirmed == 200 and feed(t, [200] * 5) == 0


def test_rise_needs_reads_in_a_row():
    t = LivesTracker(150)
    t.update(15)
    feed(t, [150, 150, 15, 150, 150])      # a normal read in between restarts the vote
    assert t.confirmed == 15


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
