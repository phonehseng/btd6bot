"""The blimp ramp buys its best option when the bank was built for it.

Sunken Columns Impoppable (2026-11-11 21:30, chimps_sub_druid_water, loss
case 20261111_213224): rounds 96 and 98 were rated 0.4x and 0.2x, the best
purchase per dollar was a bomb to 0-5-0 ($31,200) with $34-36k in hand,
and since it added under a tenth of what was missing the ramp bought
nothing; round 98 took the life with $35,730 banked. Such a buy now goes
ahead when the blimps are at most two rounds off, the cash in hand pays for
it and it takes at least half that cash - not a drip of small buys (the
Workshop case, test_nothing_is_bought_when_nothing_matters)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import strategy as S  # noqa: E402


def _ex():
    return S.Executor.__new__(S.Executor)


def test_a_big_affordable_buy_before_the_blimps_goes_ahead():
    assert _ex()._idle_cash_buys({"cost": 31_200}, 34_519, 96, 96)
    assert _ex()._idle_cash_buys({"cost": 31_200}, 35_730, 96, 98)


def test_small_far_or_unaffordable_buys_wait():
    ex = _ex()
    assert not ex._idle_cash_buys({"cost": 2_946}, 9_000, 38, 40), "a small buy is a drip"
    assert not ex._idle_cash_buys({"cost": 31_200}, 34_519, 90, 96), "the blimps are far off"
    assert not ex._idle_cash_buys({"cost": 38_400}, 22_096, 93, 93), "not affordable now"


if __name__ == "__main__":
    test_a_big_affordable_buy_before_the_blimps_goes_ahead()
    test_small_far_or_unaffordable_buys_wait()
    print("all tests passed")
