"""Offline checks for the Double Cash / Fast Track reader and its effect on
the planner's win chances. Run: python tests/test_boosts_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import boosts as B  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402

W, H = 1920, 1200
CHECK_BGR = (5, 254, 122)   # the check mark's green, measured on a recording


def _screen(*on):
    """A dark frame with green check marks on the named toggles."""
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (90, 60, 30)
    for name in on:
        fx, fy = B.TOGGLES[name]
        x, y = int(fx * W), int(fy * H)
        img[y - 8:y + 8, x - 8:x + 8] = CHECK_BGR
    return img


def test_read_toggles():
    assert B.read(_screen()) == {"double_cash": False, "fast_track": False}
    assert B.read(_screen("double_cash")) == {"double_cash": True, "fast_track": False}
    assert B.read(_screen("double_cash", "fast_track")) == {"double_cash": True, "fast_track": True}


def test_where_double_cash_pays():
    on = {"double_cash": True}
    assert B.double_cash_applies(on, "hard") and B.double_cash_applies(on, "impoppable")
    assert not B.double_cash_applies(on, "chimps")       # switched off by the game
    assert not B.double_cash_applies(on, "deflation")    # no pop income to double
    assert not B.double_cash_applies({}, "hard")


def test_double_cash_cuts_the_loss_chance():
    acc = AccountState()
    acc.apply_level(60)
    s = P.EXAMPLE_STRATEGIES[0]
    mode = next(m for m in ("hard", "medium", "easy") if m in s.modes)
    plain = P.prior_win_probability(acc, s, "Monkey Meadow", mode)
    acc.boosts = {"double_cash": True}
    boosted = P.prior_win_probability(acc, s, "Monkey Meadow", mode)
    assert boosted > plain
    expected = 1 - (1 - plain) * P.DOUBLE_CASH_LOSS_FACTOR
    assert abs(boosted - min(0.98, expected)) < 1e-9, (plain, boosted)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
