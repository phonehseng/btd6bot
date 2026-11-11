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


def test_fast_track_doubts_half_cash():
    """Fast Track skips the early rounds Half Cash builds its money in
    (Sulfur Springs Half Cash, 2026-11-04: round 22 with $4,420, lost)."""
    acc = AccountState()
    acc.apply_level(60)
    s = P.EXAMPLE_STRATEGIES[0]
    acc.boosts = {"double_cash": True}
    without = P.prior_win_probability(acc, s, "Monkey Meadow", "half_cash")
    acc.boosts = {"double_cash": True, "fast_track": True}
    with_ft = P.prior_win_probability(acc, s, "Monkey Meadow", "half_cash")
    assert with_ft < without, (without, with_ft)
    # other modes are not touched by this factor
    assert P.prior_win_probability(acc, s, "Monkey Meadow", "hard") > with_ft


def test_where_fast_track_games_begin():
    """The Fast Track start round per mode, as the bot's games report it."""
    assert B.fast_track_start("easy") == 10 and B.fast_track_start("primary_only") == 10
    assert B.fast_track_start("medium") == 15 and B.fast_track_start("reverse") == 15
    assert B.fast_track_start("hard") == 22 and B.fast_track_start("abr") == 22
    # Impoppable is played with the toggle off (owner, 2026-11-10: FAST_TRACK_OFF_MODES)
    assert B.fast_track_start("impoppable") is None
    assert B.fast_track_start("chimps") is None       # the game allows no boost there
    assert B.fast_track_start("deflation") is None    # everything is bought before round 31
    assert B.fast_track_start("no_such_mode") is None


def test_fast_track_opening_losses_doubt_the_mode():
    """Losses inside a mode's Fast Track opening (ABR: rounds 22-30, with a
    build bought in one go for a round-1 plan) lower the prior of every build
    in that mode; losses deep in the game are the build's own business."""
    acc = AccountState()
    acc.apply_level(60)
    acc.boosts = {"double_cash": True, "fast_track": True}
    s = next(x for x in P.EXAMPLE_STRATEGIES if "abr" in x.modes)
    clean = P.prior_win_probability(acc, s, "Monkey Meadow", "abr")
    assert P.fast_track_opening_factor(acc, "abr") == 1.0
    # four losses at round 60 on another map: the opening was survived
    for _ in range(4):
        acc.record_result("Logs", "abr", "some_build", False, round_reached=60)
    assert P.fast_track_opening_factor(acc, "abr") == 1.0
    assert abs(P.prior_win_probability(acc, s, "Monkey Meadow", "abr") - clean) < 1e-9
    # four more lost at round 25: 4 of 8 openings lost, shrunk by the pseudo-games
    for _ in range(4):
        acc.record_result("Logs", "abr", "some_build", False, round_reached=25)
    k = P.FAST_TRACK_OPENING_PRIOR_GAMES
    f = P.fast_track_opening_factor(acc, "abr")
    assert abs(f - (8 - 4 + k) / (8 + k)) < 1e-9, f
    doubted = P.prior_win_probability(acc, s, "Monkey Meadow", "abr")
    assert abs(doubted - min(0.98, max(0.01, clean * f))) < 1e-9, (clean, f, doubted)
    # a win at round 80 is another survived opening
    acc.record_result("Logs", "abr", "some_build", True, round_reached=80)
    assert abs(P.fast_track_opening_factor(acc, "abr") - (9 - 4 + k) / (9 + k)) < 1e-9
    # other modes keep their own record; without the boost nothing is doubted
    assert P.fast_track_opening_factor(acc, "hard") == 1.0
    assert P.fast_track_opening_factor(acc, "chimps") == 1.0
    acc.boosts = {"double_cash": True}
    assert P.fast_track_opening_factor(acc, "abr") == 1.0
    assert abs(P.prior_win_probability(acc, s, "Monkey Meadow", "abr") - clean) < 1e-9


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
