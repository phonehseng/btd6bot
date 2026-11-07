"""Builds in strategies/maps and strategies/optimized are re-read between
games (no game needed).

Before (2026-11-07): a new Frozen Over CHIMPS build was merged at 04:37 and a
NEXT file asked for Frozen Over CHIMPS at 04:43. Those folders are left out of
the bot's restart check (they are written in batches), so the bot - loaded at
03:27 - still held the OLD build in memory, played it, and lost at round 95.
Now Bot._reload_batch_builds re-reads every strategy when those folders change.
Run: python tests/test_batch_reload_offline.py"""
import logging
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import runner as R  # noqa: E402

logging.getLogger("runner").setLevel(logging.CRITICAL)

OLD = {"frozenover_chimps": {"id": "frozenover_chimps", "hero": "admiral_brickell"}}
NEW = {"frozenover_chimps": {"id": "frozenover_chimps", "hero": "etienne", "plan_first": True}}


def bare_bot(strats, stamp):
    """A Bot with only what _reload_batch_builds touches (no screen, no input)."""
    bot = object.__new__(R.Bot)
    bot.strats = dict(strats)
    bot._batch_stamp = stamp
    return bot


def test_unchanged_folders_keep_the_loaded_builds():
    bot = bare_bot(OLD, 100.0)
    with mock.patch.object(R, "_batch_stamp", return_value=100.0), \
            mock.patch.object(R, "load_all", side_effect=AssertionError("must not reload")):
        assert bot._reload_batch_builds() is False
    assert bot.strats == OLD


def test_a_changed_map_build_is_played_from_the_new_file():
    bot = bare_bot(OLD, 100.0)
    with mock.patch.object(R, "_batch_stamp", return_value=200.0), \
            mock.patch.object(R, "load_all", return_value=dict(NEW)):
        assert bot._reload_batch_builds() is True
    assert bot.strats["frozenover_chimps"]["hero"] == "etienne"
    assert bot._batch_stamp == 200.0


def test_a_half_written_file_keeps_the_old_builds_and_retries():
    bot = bare_bot(OLD, 100.0)
    with mock.patch.object(R, "_batch_stamp", return_value=200.0), \
            mock.patch.object(R, "load_all", side_effect=ValueError("bad yaml")):
        assert bot._reload_batch_builds() is False
    assert bot.strats == OLD
    assert bot._batch_stamp == 100.0      # not moved on: the next check tries again


def test_the_batch_stamp_sees_the_map_builds_folder():
    # the real folders: strategies/maps holds the CHIMPS map builds
    assert R._batch_stamp() > 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK")
