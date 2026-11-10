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


def test_a_fixed_lives_mode_never_believes_a_read_above_its_count():
    """Ancient Portal Impoppable (2026-11-05): the OCR read 11 for the one
    life in 29 of 65 reads. With one fixed life a read above 1 is a misread
    and the last trusted count stands - even when the game opens with it."""
    t = LivesTracker(1, fixed=True)
    assert t.max_lives == 1
    assert feed(t, [11, 11, 11, 11, 11]) == 0 and t.confirmed is None
    t.update(1)
    assert t.confirmed == 1
    assert feed(t, [11, 1, 11, 11, 1, 11, 11, 11]) == 0 and t.confirmed == 1
    assert t.update(0) == 0 and feed(t, [0, 0]) == 1, "the one life lost is still a leak"
    # modes that can gain lives keep their room for bonus lives
    assert LivesTracker(100).max_lives == 225 and LivesTracker(1).max_lives == 27


def test_rise_needs_reads_in_a_row():
    t = LivesTracker(150)
    t.update(15)
    feed(t, [150, 150, 15, 150, 150])      # a normal read in between restarts the vote
    assert t.confirmed == 15


def test_round_line_names_a_misread_beside_the_confirmed_count():
    """Party Parade Hard (2026-11-05) logged "lives 1001" for twelve rounds
    while the tracker held 100: the round line now shows the confirmed count
    and keeps the raw read only as a note."""
    from btd6bot.match import _misread_note
    t = LivesTracker(100)
    feed(t, [100, 1001, 1001])
    assert t.confirmed == 100
    assert _misread_note(1001, t.confirmed) == " (read 1001)"
    assert _misread_note(100, 100) == "" and _misread_note(None, 100) == ""


def test_a_vote_never_lifts_lives_above_the_start():
    """Last Resort Medium (2026-11-10): 21 lives were read as 218 four times
    in a row and the vote took it. A correction stops at the start count;
    a wrong low first read is still corrected up to it."""
    t = LivesTracker(150)
    feed(t, [150, 150, 143, 143, 143, 21, 21, 21])
    assert t.confirmed == 21
    feed(t, [218] * 8)
    assert t.confirmed == 21, t.confirmed
    t = LivesTracker(150)
    t.update(15)
    feed(t, [150] * 5)
    assert t.confirmed == 150


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
