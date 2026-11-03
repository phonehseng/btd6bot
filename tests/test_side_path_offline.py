"""Reinforcing may buy a tower's side path up to tier 2 past the plan's
crosspath, once its leading path is past tier 2 (Executor._side_path_ok).

Cornfield Medium (2026-11-03, solo_ace) was lost with $25k idle: one ace
fitted on the map, the plan saved for its $42,500 5-2-0, and the opener
sniper stood at its planned 4-1-0, so reinforce had nothing it was allowed
to buy - although 4-2-0 ($450) lifted the weakest round ahead from 0.71 to
0.87 in the damage model. Offline: the executor with a fake game.
Run: python tests/test_side_path_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import strategy as S             # noqa: E402


def executor(sniper_cap, tiers):
    """An executor whose plan upgrades o1 (a sniper) to `sniper_cap` and
    a1 (an ace) to 4-2-0, with o1 standing at `tiers`."""
    plan = {"id": "t", "name": "t", "hero": None,
            "plan": [{"do": "place", "id": "o1", "kind": "sniper", "role": "dps"},
                     {"do": "place", "id": "a1", "kind": "ace", "role": "dps"},
                     {"do": "upgrade", "id": "o1", "to": sniper_cap},
                     {"do": "upgrade", "id": "a1", "to": "4-2-0"}]}
    g = F.FakeGame()
    ex = S.Executor(g, F.FakeModel(), plan, "medium", F.full_account())
    o1 = F.Placed("o1", "sniper", 0.40, 0.48)
    o1.tiers = list(tiers)
    a1 = F.Placed("a1", "ace", 0.41, 0.56)
    a1.tiers = [4, 2, 0]
    o1.spent, a1.spent = 5000, 6000     # upgrade_choices sorts by cash invested
    g.towers = {"o1": o1, "a1": a1}
    return ex


def offered(ex, past_plan):
    return {(p.tid, tuple(t)) for p, t, _ in ex.upgrade_choices(past_plan=past_plan)}


def test_cornfield_sniper_may_take_its_side_path():
    ex = executor("4-1-0", [4, 1, 0])
    assert ("o1", (4, 2, 0)) in offered(ex, past_plan=True)
    # the plan's own spending still stops at the planned crosspath
    assert ("o1", (4, 2, 0)) not in offered(ex, past_plan=False)


def test_never_a_side_path_the_plan_does_not_use():
    # the plan wants 4-0-1: buying path 2 would shut out path 3 for good
    ex = executor("4-0-1", [4, 0, 0])
    got = offered(ex, past_plan=True)
    assert ("o1", (4, 1, 0)) not in got
    assert ("o1", (5, 0, 0)) in got          # the leading path may still grow


def test_no_side_path_before_the_main_path_is_set():
    # at 2-1-0 a side tier could still make path 2 the leading one
    ex = executor("2-1-0", [2, 1, 0])
    assert ("o1", (2, 2, 0)) not in offered(ex, past_plan=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
