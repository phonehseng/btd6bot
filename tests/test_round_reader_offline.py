"""The round reader prefers the counter's own shape, and a round stuck while
the game runs is reported with what the reader saw.

Water Park Impoppable (2026-11-11 02:26-02:28): the tracked round stayed 88
for 79 s while the game played on to round 91 and lost, the counter in plain
view, and nothing showed what the reader saw.
Run: python tests/test_round_reader_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import hud as H, match as M  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402


def test_counter_shape_wins_over_digits():
    h = H.Hud(LAYOUTS["16:10"])
    h.total_rounds = 100
    texts = iter(["33", "89/100"])          # the first place reads stray digits
    real = H.rec_text
    H.rec_text = lambda img: (next(texts), 0.9)
    try:
        assert h.round(np.zeros((1200, 1920, 3), np.uint8)) == 89
        assert h.last_round_texts == ["33", "89/100"]
    finally:
        H.rec_text = real


def test_stuck_round_is_reported_once_a_minute():
    m = M.Match.__new__(M.Match)
    m._in_round, m._t_round_change = True, 0.0
    m.g = N(hud=N(last_round_texts=["88/100", ""], layout=LAYOUTS["16:10"]))
    logs = []
    real = M.log.warning
    M.log.warning = lambda *a: logs.append(a)
    import btd6bot.vision as V
    real_save = V.save
    V.save = lambda img, path: None
    try:
        frame = np.zeros((1200, 1920, 3), np.uint8)
        m._report_stuck_round(frame, 88, 88, 30.0)
        assert not logs, "under STUCK_ROUND_S: nothing"
        m._report_stuck_round(frame, 88, 88, 50.0)
        assert len(logs) == 1
        m._report_stuck_round(frame, 88, 88, 80.0)
        assert len(logs) == 1, "at most once a STUCK_REPORT_EVERY"
    finally:
        M.log.warning, V.save = real, real_save


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
