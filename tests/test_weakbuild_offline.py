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


def test_an_edited_damage_model_starts_again_at_a_day():
    """The verdict is the model's: the same build left under an edited model
    is a first leave again, and the record names the model it was left by."""
    from btd6bot.runner import weak_bench_hours
    _, rec = weak_bench_hours(None, "solo_dart", "abc", model="m1")
    hours, rec = weak_bench_hours(rec, "solo_dart", "abc", model="m1")
    assert (hours, rec["n"], rec["model"]) == (48, 2, "m1")
    hours, rec = weak_bench_hours(rec, "solo_dart", "abc", model="m2")
    assert (hours, rec["n"], rec["model"]) == (24, 1, "m2")


def test_the_model_fingerprint_follows_the_model_files():
    """Only the modules the verdict is computed by count, and any edit to
    one of them changes the fingerprint."""
    import tempfile
    from btd6bot.runner import model_fingerprint, WEAK_VERDICT_MODULES
    package = Path(__file__).resolve().parents[1] / "btd6bot"
    assert all((package / name).exists() for name in WEAK_VERDICT_MODULES)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in WEAK_VERDICT_MODULES:
            (tmp / name).write_text("x = 1\n", encoding="utf-8")
        before = model_fingerprint(tmp)
        (tmp / "runner.py").write_text("y = 2\n", encoding="utf-8")     # not the model
        assert model_fingerprint(tmp) == before
        (tmp / WEAK_VERDICT_MODULES[0]).write_text("x = 2\n", encoding="utf-8")
        assert model_fingerprint(tmp) != before


HOUR = 3600
# 2026-11-12 01:56: what the three Deflation benches looked like (left at
# 17:05-17:15 the evening before, 48 h each, by a record without a model).
LEFT_AT = 1_000_000.0
WEAK_RECORDS = {"Erosion|deflation": {"n": 2, "build": ["solo_dart", "939b0b1351ff"]}}
WEAK_REASONS = {"Erosion|deflation": {"why": "solo_dart rated 0.06, left 2x", "since": LEFT_AT}}
WEAK_BENCHES = {"Erosion|deflation": LEFT_AT + 48 * HOUR}


def test_a_weak_bench_from_an_older_model_is_named_for_lifting():
    """Party Parade Deflation: `solo_dart` left at 0.06 on 2026-11-11 11:19,
    rated 1.20 and won at 01:50 after the model was corrected. The other
    maps left at 0.06 by the old model get their second look too."""
    from btd6bot.runner import outdated_weak_benches, WEAK_RECHECK_AFTER_H
    late = LEFT_AT + WEAK_RECHECK_AFTER_H * HOUR
    assert outdated_weak_benches(WEAK_RECORDS, WEAK_REASONS, WEAK_BENCHES, "m2", late) \
        == ["Erosion|deflation"]
    # too soon after it was left: a day of model edits is not a visit per edit
    assert outdated_weak_benches(WEAK_RECORDS, WEAK_REASONS, WEAK_BENCHES, "m2", late - 1) == []


def test_a_weak_bench_under_the_same_model_or_another_bench_stays():
    from btd6bot.runner import outdated_weak_benches
    late = LEFT_AT + 40 * HOUR
    same_model = {"Erosion|deflation": dict(WEAK_RECORDS["Erosion|deflation"], model="m2")}
    assert outdated_weak_benches(same_model, WEAK_REASONS, WEAK_BENCHES, "m2", late) == []
    # played and lost since: that bench is the defeat's, not the weak build's
    lost = {"Erosion|deflation": {"why": "defeat", "since": LEFT_AT}}
    assert outdated_weak_benches(WEAK_RECORDS, lost, WEAK_BENCHES, "m2", late) == []
    # the bench ran out by itself
    assert outdated_weak_benches(WEAK_RECORDS, WEAK_REASONS, {}, "m2", late) == []


def test_the_bot_lifts_the_bench_and_forgets_the_old_verdict():
    """Bot._lift_outdated_weak_benches on temporary files: the outdated weak
    bench goes, the record with it, and a bench set for a defeat stays."""
    import json
    import tempfile
    import time
    from unittest import mock
    from btd6bot import runner as R
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        now = time.time()
        benches = {"Erosion|deflation": now + 30 * HOUR, "Quad|impoppable": now + 5 * HOUR}
        reasons = {"Erosion|deflation": {"why": "solo_dart rated 0.06, left 2x", "since": now - 10 * HOUR},
                   "Quad|impoppable": {"why": "defeat", "since": now - 7 * HOUR}}
        (tmp / "bench.json").write_text(json.dumps(benches), encoding="utf-8")
        (tmp / "why.json").write_text(json.dumps(reasons), encoding="utf-8")
        (tmp / "weak.json").write_text(json.dumps(WEAK_RECORDS), encoding="utf-8")
        bot = R.Bot.__new__(R.Bot)
        bot._bench_file = lambda: tmp / "bench.json"
        bot._bench_why_file = lambda: tmp / "why.json"
        bot._weak_file = lambda: tmp / "weak.json"
        with mock.patch.object(R.log, "warning"):
            assert bot._lift_outdated_weak_benches() == ["Erosion|deflation"]
            assert bot._lift_outdated_weak_benches() == []          # nothing left to lift
        assert list(json.loads((tmp / "bench.json").read_text(encoding="utf-8"))) == ["Quad|impoppable"]
        assert json.loads((tmp / "weak.json").read_text(encoding="utf-8")) == {}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
