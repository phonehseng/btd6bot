"""At the margin floor a plan step no longer keeps the cash against a
purchase that saves lives (reinforce.floor_pick_outsaves, backlog 39b).

The damage model's margin search floors at 1/16 (dps_model.MARGIN_FLOOR).
Once the weakest round sits there every purchase reads "0.06 -> 0.06", so
the MIN_LIFT rule of reinforce.plan_keeps_claim let the waiting plan step
keep the bank whatever the purchase would save: Dark Dungeons Magic
Monkeys Only (2026-11-05) held cash that way 14 times before the loss.
At the floor the lives the model expects to lose (forecast.leaks) still
move with every purchase, so they decide instead.

Offline, with a fake forecast whose leak falls with the board's tier total.
Run: python tests/test_floor_lift_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import dps_model as D       # noqa: E402
from btd6bot import reinforce as RF      # noqa: E402


class FloorForecast:
    """Every round at `margin`; each tier on the board saves `per_tier` of
    the 100 lives the round would cost, and dart tiers save `dart_tier`."""

    def __init__(self, margin, per_tier=1.0, dart_tier=None):
        self.m = margin
        self.per_tier = per_tier
        self.dart_tier = per_tier if dart_tier is None else dart_tier

    def margin(self, towers, rnd):
        return self.m

    def leaks(self, towers, rounds, strength, per_round=False):
        saved = sum(sum(t.tiers) * (self.dart_tier if t.kind == "dart" else self.per_tier) for t in towers)
        return max(0.0, 100.0 - saved) * len(rounds)


def executor():
    """A board of one ninja (2-0-0, the plan wants 4-0-0) and one dart."""
    towers = {"n1": SimpleNamespace(tid="n1", kind="ninja", tiers=(2, 0, 0), x=0.3, y=0.3),
              "d1": SimpleNamespace(tid="d1", kind="dart", tiers=(0, 0, 0), x=0.5, y=0.5)}
    return SimpleNamespace(g=SimpleNamespace(towers=towers),
                           _next_path=lambda p, target: (1,))   # path 1 comes next


def pick_with_dart_tiers(ex, n):
    """The purchase: the dart upgraded n tiers (path 2)."""
    after = [SimpleNamespace(**{**vars(t), "tiers": (0, n, 0)}) if t.tid == "d1" else t for t in RF.board(ex)]
    return RF.Option(f"upgrade d1 -> 0-{n}-0", 500.0, {"do": "upgrade", "id": "d1", "to": f"0-{n}-0"}, after)


STEP = {"do": "upgrade", "id": "n1", "to": "4-0-0"}


def keeps(forecast, pick):
    return RF.plan_keeps_claim(forecast, executor(), STEP, 3000.0, 1000.0, 70, 75, True, pick, 0.0)


def test_floor_is_the_search_bound():
    assert D.at_floor(D.MARGIN_FLOOR)
    assert not D.at_floor(0.1)
    assert not D.at_floor(None)


def test_above_floor_the_min_lift_rule_stands():
    """A purchase that moves no margin above the floor never outbids the step."""
    ex = executor()
    assert keeps(FloorForecast(0.5), pick_with_dart_tiers(ex, 3))


def test_at_floor_a_pick_saving_more_lives_comes_first():
    """The dart's three tiers (3 x 5 lives) beat the ninja's one tier (1 life)."""
    ex = executor()
    assert not keeps(FloorForecast(D.MARGIN_FLOOR, per_tier=1.0, dart_tier=5.0), pick_with_dart_tiers(ex, 3))


def test_at_floor_the_step_keeps_its_claim_when_it_saves_more():
    """The ninja's tier (10 lives) beats one dart tier (1 life)."""
    ex = executor()
    assert keeps(FloorForecast(D.MARGIN_FLOOR, per_tier=10.0, dart_tier=1.0), pick_with_dart_tiers(ex, 1))


def test_at_floor_a_pick_saving_too_little_does_not_outbid():
    """Under MIN_SAVED lives the step keeps the cash even at the floor."""
    ex = executor()
    tiny = RF.MIN_SAVED / 10
    assert keeps(FloorForecast(D.MARGIN_FLOOR, per_tier=0.0, dart_tier=tiny), pick_with_dart_tiers(ex, 1))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK")
