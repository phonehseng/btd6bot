"""With every open medal benched, the bot plays a game it lost over an hour
ago again instead of idling (Bot._retry_benched).

Owner, 2026-11-11: "dont let it idle this long" - from 13:57 the bot napped
in 30-minute steps with all 37 open map/mode pairs benched for 12 h."""
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import runner as R  # noqa: E402


def bare(benches, reasons):
    tmp = Path(tempfile.mkdtemp())
    r = R.Bot.__new__(R.Bot)
    r.bad = set()
    r._bench_file = lambda: tmp / "b.json"
    r._bench_why_file = lambda: tmp / "w.json"
    (tmp / "b.json").write_text(json.dumps(benches))
    (tmp / "w.json").write_text(json.dumps(reasons))
    return r


def cand(m, mode="impoppable"):
    return SimpleNamespace(map=m, mode=mode)


def test_the_loss_longest_ago_is_retried():
    now = time.time()
    r = bare({"A|impoppable": now + 11.5 * 3600, "B|impoppable": now + 9 * 3600,
              "C|impoppable": now + 6 * 3600},
             {"A|impoppable": {"why": "defeat", "since": now - 0.5 * 3600},
              "B|impoppable": {"why": "defeat", "since": now - 3 * 3600},
              "C|impoppable": {"why": "defeat", "since": now - 6 * 3600}})
    got = r._retry_benched([cand("A"), cand("B"), cand("C")])
    assert got.map == "C", got


def test_a_loss_under_an_hour_ago_and_error_benches_wait():
    now = time.time()
    r = bare({"A|impoppable": now + 11.5 * 3600, "B|impoppable": now + 5 * 3600},
             {"A|impoppable": {"why": "defeat", "since": now - 0.5 * 3600},
              "B|impoppable": {"why": "error twice: x", "since": now - 1.5 * 3600}})
    assert r._retry_benched([cand("A"), cand("B")]) is None


def test_old_benches_without_a_reason_count_as_losses():
    now = time.time()
    r = bare({"A|impoppable": now + 2 * 3600}, {})   # set 10 h ago (12 h bench)
    assert r._retry_benched([cand("A")]).map == "A"


def test_the_nap_ends_when_the_first_retry_is_due():
    # 2026-11-11 22:25: nothing ready, two losses 0.8 and 0.9 h old - the
    # bot napped its fixed 30 minutes past both
    now = time.time()
    r = bare({"A|impoppable": now + 11.1 * 3600, "B|reverse": now + 11.2 * 3600,
              "C|deflation": now + 40 * 3600},
             {"A|impoppable": {"why": "defeat", "since": now - 0.9 * 3600},
              "B|reverse": {"why": "defeat", "since": now - 0.8 * 3600},
              "C|deflation": {"why": "solo_dart rated 0.06, left 2x", "since": now - 5 * 3600}})
    assert r._retry_benched([cand("A"), cand("B", "reverse"), cand("C", "deflation")]) is None
    assert 0.1 * 3600 - 5 < r.idle_seconds() < 0.1 * 3600 + 5, r.idle_seconds()
    # a retry seconds away still naps the minimum; none due at all, the full nap
    r._retry_due_in = 2.0
    assert r.idle_seconds() == R.IDLE_NAP_MIN_S
    r._retry_due_in = None
    assert r.idle_seconds() == R.IDLE_NAP_S
    # only benches that are never retried: the full nap
    assert r._retry_benched([cand("C", "deflation")]) is None
    assert r.idle_seconds() == R.IDLE_NAP_S


def test_a_ready_retry_leaves_no_nap_hint():
    now = time.time()
    r = bare({"A|impoppable": now + 9 * 3600, "B|impoppable": now + 11.5 * 3600},
             {"A|impoppable": {"why": "defeat", "since": now - 3 * 3600},
              "B|impoppable": {"why": "defeat", "since": now - 0.5 * 3600}})
    assert r._retry_benched([cand("A"), cand("B")]).map == "A"
    assert r._retry_due_in is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
