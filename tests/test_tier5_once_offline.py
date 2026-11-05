"""The game allows one of each tier-5 upgrade on the map at a time, so a
tier 5 another tower of the same kind already holds is never asked for
(Executor._tier5_taken): the plan step skips it and reinforcing does not
offer it.

Spice Islands Impoppable (2026-11-05): sb1 bought Pre-emptive Strike
(2-0-5) at round 88; the plan's sb2 and reinforce's sub2 then tried the
same tier for ten rounds - the button read "MAX UPGRADES", a blank panel to
the bot - while $37k-119k sat idle on a one-life game. Offline: the
executor with a fake game.
Run: python tests/test_tier5_once_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import strategy as S             # noqa: E402


def executor(sb1_tiers, sb2_tiers):
    """Two subs the plan takes to 2-0-5 each, standing at the given tiers."""
    plan = {"id": "t", "name": "t", "hero": None,
            "plan": [{"do": "place", "id": "sb1", "kind": "sub", "role": "dps"},
                     {"do": "place", "id": "sb2", "kind": "sub", "role": "dps"},
                     {"do": "upgrade", "id": "sb1", "to": "2-0-5"},
                     {"do": "upgrade", "id": "sb2", "to": "2-0-5"}]}
    g = F.FakeGame()
    ex = S.Executor(g, F.FakeModel(), plan, "impoppable", F.full_account())
    sb1 = F.Placed("sb1", "sub", 0.37, 0.41)
    sb2 = F.Placed("sb2", "sub", 0.63, 0.40)
    sb1.tiers, sb2.tiers = list(sb1_tiers), list(sb2_tiers)
    sb1.spent, sb2.spent = 9000, 6000
    g.towers = {"sb1": sb1, "sb2": sb2}
    return ex


def offered(ex):
    return {(p.tid, tuple(t)) for p, t, _ in ex.upgrade_choices(past_plan=True)}


def test_a_taken_tier_5_is_not_asked_for():
    ex = executor([2, 0, 5], [2, 0, 4])
    sb2 = ex.g.towers["sb2"]
    assert ex._tier5_taken(sb2, 3) and not ex._tier5_taken(sb2, 1)
    # the tower holding it is not in its own way
    assert not ex._tier5_taken(ex.g.towers["sb1"], 3)
    assert ex._next_path(sb2, (2, 0, 5)) is None          # nothing left to buy toward it
    assert ("sb2", (2, 0, 5)) not in offered(ex)
    # the plan step for sb2 is skipped, not tried every tick
    assert ex.try_step({"do": "upgrade", "id": "sb2", "to": "2-0-5"}, 100_000, 90) == "skip"


def test_a_free_tier_5_is_still_bought():
    ex = executor([2, 0, 4], [2, 0, 4])
    sb2 = ex.g.towers["sb2"]
    assert not ex._tier5_taken(sb2, 3)
    assert ex._next_path(sb2, (2, 0, 5)) is not None and ex._next_path(sb2, (2, 0, 5))[0] == 3
    assert ("sb2", (2, 0, 5)) in offered(ex) and ("sb1", (2, 0, 5)) in offered(ex)


def test_another_kind_does_not_count():
    ex = executor([2, 0, 5], [2, 0, 4])
    ex.g.towers["sb1"].kind = "buccaneer"
    assert not ex._tier5_taken(ex.g.towers["sb2"], 3)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
