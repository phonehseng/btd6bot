"""Offline checks for the loss circuit breaker (safety.py), on temporary
state and results files. Run: python tests/test_safety_offline.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import safety  # noqa: E402


def _play(outcomes, folder):
    """Feed games through the breaker as the runner does."""
    results = folder / "results.jsonl"
    for o in outcomes:
        with open(results, "a", encoding="utf-8") as f:
            f.write(json.dumps({"outcome": o}) + "\n")
        safety.after_game(o)


def _with_files(fn):
    saved = safety.STATE_FILE, safety.RESULTS_FILE
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        safety.STATE_FILE, safety.RESULTS_FILE = folder / "safe.json", folder / "results.jsonl"
        try:
            fn(folder)
        finally:
            safety.STATE_FILE, safety.RESULTS_FILE = saved


def test_trips_after_three_of_six_lost():
    def check(folder):
        _play(["victory", "defeat", "victory", "defeat"], folder)
        assert not safety.active()
        _play(["defeat"], folder)
        assert safety.active()
    _with_files(check)


def test_needs_a_win_streak_to_leave():
    def check(folder):
        _play(["defeat"] * 3, folder)
        assert safety.active()
        _play(["victory"] * (safety.BASE_EXIT_WINS - 1) + ["defeat"], folder)
        assert safety.active()                     # the streak was broken
        _play(["victory"] * safety.BASE_EXIT_WINS, folder)
        assert not safety.active()
    _with_files(check)


def test_abandoned_games_are_not_losses():
    def check(folder):
        _play(["abandoned"] * 6, folder)
        assert not safety.active()
    _with_files(check)


def test_clean_days_forgive_trips_while_safe():
    """Four trips, the last one and the last defeat 2.5 days ago: two trips
    are forgiven, so 16 wins (not 64) end safe mode."""
    def check(folder):
        now = 2_000_000_000.0
        quiet = now - 2.5 * safety.FORGIVE_AFTER
        (folder / "results.jsonl").write_text(
            json.dumps({"t": quiet - 60, "outcome": "defeat"}) + "\n"
            + json.dumps({"t": quiet + 60, "outcome": "victory"}) + "\n", encoding="utf-8")
        state = {"on": True, "streak": 0, "trips": 4, "last_trip": quiet}
        assert safety.exit_wins(state, now=quiet + 1) == 64
        assert safety.effective_trips(state, now) == 2
        assert safety.exit_wins(state, now) == 2 * safety.BASE_EXIT_WINS
        # a fresh defeat restarts the clean-day count
        with open(folder / "results.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": now - 10, "outcome": "defeat"}) + "\n")
        assert safety.exit_wins(state, now) == 64
        # never below one trip
        assert safety.effective_trips(state, now + 30 * safety.FORGIVE_AFTER) == 1
    _with_files(check)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
