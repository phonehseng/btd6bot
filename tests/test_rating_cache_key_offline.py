"""The executor's rating cache follows each tower's spot and placement round.

Executor._rated keeps one rating per round and board (Executor._board_key).
The key held each tower's id, kind and tiers only, so a rating outlived a
change of the board under it (dynamic-map audit 2026-11-12, item 19):
Sanctuary's platforms carry towers to new spots after the margin is
cached, and a Glacial Trail tower sold and bought again in the same round
of play freezes on its new placement round.

The board is Glacial Trail's from test_freeze_clash_offline.
Run: python tests/test_rating_cache_key_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from test_reinforce_freeze_rounds_offline import NOW, _executor   # noqa: E402


def test_rating_cache_follows_spots_and_placement_rounds():
    """An unchanged board is rated once a round; a tower moved or bought
    again is rated anew."""
    ex = _executor()
    key = ex._board_key()
    ex.g.towers["dr2"].placed_round = 19          # sold and bought again
    assert ex._board_key() != key
    key = ex._board_key()
    ex.g.towers["dr2"].x += 0.05                  # carried along by a platform
    assert ex._board_key() != key
    calls = []
    ex._rated("probe", NOW, lambda fc, towers: calls.append(1))
    ex._rated("probe", NOW, lambda fc, towers: calls.append(1))
    assert len(calls) == 1, "an unchanged board is rated once"
    ex.g.towers["dr2"].y += 0.05
    ex._rated("probe", NOW, lambda fc, towers: calls.append(1))
    assert len(calls) == 2, "a moved tower is rated again"



if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
