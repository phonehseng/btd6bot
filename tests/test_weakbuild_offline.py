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


def test_the_same_unchanged_build_is_benched_longer_each_time():
    """Cargo Deflation was built and left at 0.63 on three days running
    (2026-11-06..08): each repeat of the same build doubles the bench."""
    from btd6bot.runner import weak_bench_hours, WEAK_BENCH_MAX_HOURS
    rec = None
    seen = []
    for _ in range(5):
        hours, rec = weak_bench_hours(rec, "solo_dartling", "abc")
        seen.append(hours)
    assert seen == [24, 48, 96, WEAK_BENCH_MAX_HOURS, WEAK_BENCH_MAX_HOURS]


def test_an_edited_or_different_build_starts_again_at_a_day():
    from btd6bot.runner import weak_bench_hours, build_fingerprint
    a = {"id": "solo_dartling", "plan": [{"do": "place", "tower": "dartling"}]}
    b = {"id": "solo_dartling", "plan": [{"do": "place", "tower": "sniper"}]}
    assert build_fingerprint(a) != build_fingerprint(b)
    assert build_fingerprint(a) == build_fingerprint(dict(a))
    _, rec = weak_bench_hours(None, "solo_dartling", build_fingerprint(a))
    _, rec = weak_bench_hours(rec, "solo_dartling", build_fingerprint(a))
    assert rec["n"] == 2
    assert weak_bench_hours(rec, "solo_dartling", build_fingerprint(b))[0] == 24
    assert weak_bench_hours(rec, "solo_sniper", build_fingerprint(a))[0] == 24


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
