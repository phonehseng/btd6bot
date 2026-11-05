"""A tower that is the defence's only answer to a bloon property is kept.

Flooded Valley Military Only (2026-11-04, military_sub_sniper_water): the
3-2-0 sniper s1 was the only tower that popped lead. Its pop count read 0
twice, so sell_useless sold it at round 27; the round-28 leads cost 113
lives. Offline: on that board, s1 is the sole lead (and camo) answer; a
second sniper that pops both makes it an ordinary tower again.
Run: python tests/test_sole_answer_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import strategy as S             # noqa: E402
from btd6bot import threats as TH             # noqa: E402


def placed(tid, kind, tiers, x=0.5, y=0.5):
    p = F.Placed(tid, kind, x, y)
    p.tiers = list(tiers)
    return p


def board():
    """The towers standing when s1 was sold (from game.log)."""
    return {"sb1": placed("sb1", "sub", (2, 0, 3)),
            "sb2": placed("sb2", "sub", (2, 0, 3)),
            "sub1": placed("sub1", "sub", (1, 0, 0)),
            "s1": placed("s1", "sniper", (3, 2, 0)),
            "hero": placed("hero", "hero", (0, 0, 0))}


def executor(towers):
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(F.FakeGame(), F.FakeModel(), plan, "military_only", F.full_account())
    ex.g.towers = towers
    return ex


def test_the_only_lead_popper_is_its_sole_answer():
    if not TH.available():
        return                      # no game model on this machine
    ex = executor(board())
    assert ex._sole_answer(ex.g.towers["s1"]) in ("camo", "lead")   # it popped both alone
    assert ex._sole_answer(ex.g.towers["sub1"]) is None     # other subs do its job


def test_a_second_lead_popper_frees_it():
    if not TH.available():
        return
    towers = board()
    towers["s2"] = placed("s2", "sniper", (1, 1, 0))   # pops lead, sees camo
    ex = executor(towers)
    assert ex._sole_answer(ex.g.towers["s1"]) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
