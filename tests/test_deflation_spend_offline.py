"""Deflation has no income: the bot must spend everything before round 31.
A plan step with no legal spot (Cracked Deflation's exit spike, 2026-10-24,
which left $14,060 unspent) is set aside instead of holding up the rest of
the plan; in modes with income the plan still waits as before.
Offline: the executor with a fake game."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import strategy as S             # noqa: E402


class NoSpotFor(F.FakeGame):
    """A game where one kind of tower finds nowhere to stand."""

    def __init__(self, blocked):
        super().__init__()
        self.blocked = blocked

    def place(self, tid, kind, fx, fy, check_valid=True, more_spots=()):
        if kind == self.blocked:
            self.fail_reason = "spot"
            return False
        return super().place(tid, kind, fx, fy, check_valid, more_spots)


PLAN = {"id": "t", "name": "t", "hero": None,
        "plan": [{"do": "place", "id": "ex", "kind": "spike", "role": "exit"},
                 {"do": "place", "id": "d1", "kind": "dart", "role": "dps"}]}


def placed_after(mode, ticks=6):
    g = NoSpotFor("spike")
    ex = S.Executor(g, F.FakeModel(), dict(PLAN), mode, F.full_account())
    for _ in range(ticks):
        ex.tick(40000, 31 if mode == "deflation" else 1)
    return g.placed, ex


def test_deflation_sets_the_blocked_step_aside():
    placed, ex = placed_after("deflation")
    assert "dart" in placed, placed
    assert any(st.get("id") == "ex" for st in ex.deferred)


def test_modes_with_income_still_wait_for_the_step():
    # (a dart may still come from the threat answers; what matters here is
    # that the plan itself is still held at the blocked step)
    _, ex = placed_after("easy")
    assert "'id': 'ex'" in ex.waiting and "(spot)" in ex.waiting, ex.waiting
    assert not any(st.get("id") == "ex" for st in ex.deferred)


# --- continuous sends (Apopalypse): the bloons never wait for the plan -----

class DeadButton(F.FakeGame):
    """A game where clicks on one tower's upgrades have no effect."""

    def __init__(self, tid):
        super().__init__()
        self.dead = tid

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        self.fail_reason = None
        if p.tid == self.dead:
            self.fail_reason = "noeffect"
            return False
        return super().upgrade(p, path, max_wait, allow_xp_unlock)


def test_apopalypse_sets_a_blocked_place_aside_with_its_upgrades():
    # Polyphemus Apopalypse (2026-10-27) waited on an exit spike with no
    # accepted spot while $15k piled up; its upgrade must travel with it
    plan = {"id": "t", "name": "t", "hero": None,
            "plan": [{"do": "place", "id": "ex", "kind": "spike", "role": "exit"},
                     {"do": "upgrade", "id": "ex", "to": "0-0-2"},
                     {"do": "place", "id": "d1", "kind": "dart", "role": "dps"}]}
    g = NoSpotFor("spike")
    ex = S.Executor(g, F.FakeModel(), plan, "apopalypse", F.full_account())
    for _ in range(6):
        ex.tick(40000, 20)
    assert "dart" in g.placed, g.placed
    assert [st.get("do") for st in ex.deferred if st.get("id") == "ex"] == ["place", "upgrade"], ex.deferred
    assert not any(st.get("id") == "ex" for st in ex.plan[ex.idx:])


def test_apopalypse_sets_a_dead_upgrade_aside_but_easy_waits():
    plan = {"id": "t", "name": "t", "hero": None,
            "plan": [{"do": "place", "id": "su1", "kind": "super", "role": "dps"},
                     {"do": "upgrade", "id": "su1", "to": "1-0-0"},
                     {"do": "place", "id": "d1", "kind": "dart", "role": "dps"}]}
    for mode, sets_aside in (("apopalypse", True), ("easy", False)):
        g = DeadButton("su1")
        ex = S.Executor(g, F.FakeModel(), dict(plan), mode, F.full_account())
        for _ in range(6):
            ex.tick(40000, 20)
        aside = any(st.get("id") == "su1" and st["do"] == "upgrade" for st in ex.deferred)
        assert aside == sets_aside, (mode, ex.deferred, ex.waiting)
        if not sets_aside:
            assert "(noeffect)" in ex.waiting, ex.waiting


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
