"""A game the last bot started and never finished counts as a defeat at the
next start, and is benched (Runner._settle_unfinished_game).

Cargo Double HP (2026-11-03): lost at 17:02 while the bot hung on the
defeat screen; the supervisor restarted it at 17:20, nothing was written
down, and the planner chose Cargo Double HP again and lost it at 17:30.
A game the owner stopped (STOP) is only forgotten, not counted.
Offline: temporary files, a fake account. Run: python tests/test_unfinished_game_offline.py"""
import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import progress, safety  # noqa: E402
from btd6bot import runner as R       # noqa: E402

logging.getLogger("runner").setLevel(logging.CRITICAL)


class FakeAccount:
    def __init__(self):
        self.results = []

    def record_result(self, map_name, mode, strategy, won):
        self.results.append((map_name, mode, strategy, won))

    def save(self):
        pass


def settle(game):
    """Run _settle_unfinished_game with `game` (a dict or None) as the file
    left by the last bot; returns (bot, results.jsonl rows, file still there)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        game_file, results = tmp / "game.json", tmp / "results.jsonl"
        if game is not None:
            game_file.write_text(json.dumps(game), encoding="utf-8")
        bot = R.Bot.__new__(R.Bot)
        bot.account = FakeAccount()
        bot.benches = {}
        bot.bench = lambda m, mode, hours, why="": bot.benches.update({(m, mode): hours})
        with mock.patch.object(R, "GAME_FILE", game_file), \
                mock.patch.object(progress, "RESULTS_FILE", results), \
                mock.patch.object(safety, "STATE_FILE", tmp / "safe.json"), \
                mock.patch.object(safety, "RESULTS_FILE", results), \
                mock.patch("btd6bot.status.set_focus", lambda *_: None):
            bot._settle_unfinished_game()
        rows = [json.loads(x) for x in results.read_text(encoding="utf-8").splitlines()] \
            if results.exists() else []
        return bot, rows, game_file.exists()


CARGO = {"map": "Cargo", "mode": "double_hp", "strategy": "double_hp_sniper_sun", "t": 0}


def test_a_crashed_game_is_a_benched_defeat():
    bot, rows, left = settle(CARGO)
    assert bot.account.results == [("Cargo", "double_hp", "double_hp_sniper_sun", False)]
    assert bot.benches == {("Cargo", "double_hp"): 12}
    assert [r["outcome"] for r in rows] == ["defeat"]
    assert not left


def test_a_game_the_owner_stopped_is_not_counted():
    bot, rows, left = settle(dict(CARGO, stopped=True))
    assert bot.account.results == [] and bot.benches == {} and rows == []
    assert not left


def test_nothing_to_do_without_an_unfinished_game():
    bot, rows, _ = settle(None)
    assert bot.account.results == [] and bot.benches == {} and rows == []


def test_a_game_left_before_play_is_not_a_defeat_after_a_reload():
    """Quad Deflation (2026-11-09 13:40): the finished no-income build rated
    round 33 at 0.06, so the bot left before Play (WeakBuild). It reloaded a
    minute later and the new bot recorded that game as a crashed defeat,
    because the in-progress note was still there. Leaving clears it."""
    from types import SimpleNamespace
    from btd6bot.match import WeakBuild
    plan = SimpleNamespace(map="Quad", mode_key="deflation", strategy_id="solo_buccaneer")
    with tempfile.TemporaryDirectory() as tmp:
        game_file = Path(tmp) / "game.json"
        bot = R.Bot.__new__(R.Bot)
        bot.benches = {}
        bot.bench = lambda m, mode, hours, why="": bot.benches.update({(m, mode): hours})
        bot.strats = {}                                   # build_fingerprint of an unknown build
        bot._weak_file = lambda: Path(tmp) / "x.weak.json"  # not the account's real record
        with mock.patch.object(R, "GAME_FILE", game_file), \
                mock.patch("btd6bot.status.set_focus", lambda *_: None):
            R._note_game_started(plan)
            assert game_file.exists()
            bot._left_before_play(plan, WeakBuild(0.06, 33))
            assert not game_file.exists()
            assert R._game_in_progress() is None      # a reloaded bot finds nothing to settle
    assert bot.benches == {("Quad", "deflation"): 24}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
