"""Offline: a no-income (Deflation) build that the damage model says would
lose is left before Play instead of being played to a defeat (match.py).
Run: python tests/test_weakbuild_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import match as M  # noqa: E402
from btd6bot.strategy import rules  # noqa: E402


def test_weak_deflation_build_is_not_started():
    """Dark Path Deflation (2026-11-02): the finished build rated round 40
    at 0.48 and lost at round 35. Sulfur Springs Deflation won at 0.89."""
    defl = rules("deflation")
    assert defl.get("buy_all_upfront")
    assert M.too_weak_to_start((0.48, 40), defl)
    assert not M.too_weak_to_start((0.89, 40), defl)


def test_modes_with_income_and_unrated_builds_are_played_as_before():
    """With income the bot can still reinforce after Play, and a build the
    model cannot rate (no track data) is not refused."""
    assert not M.too_weak_to_start((0.1, 40), rules("hard"))
    assert not M.too_weak_to_start(None, rules("deflation"))


def test_weak_build_message_names_the_round_and_rating():
    e = M.WeakBuild(0.48, 40)
    assert isinstance(e, RuntimeError)
    assert e.margin == 0.48 and e.round == 40
    assert "round 40" in str(e) and "0.48" in str(e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
