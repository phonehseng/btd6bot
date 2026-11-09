"""Apopalypse build after the two 2026-11-09 losses (Sunken Columns r33,
Sunset Gulch r56).

Sunset Gulch r56: a flood of small bloons from popped blimps crossed the
bridge to the exit, where only an unupgraded dart stood, and 88 lives went
in one round with $4.6-6.1k unspent. The exit Spike Factory was the plan's
second-to-last step, behind about $30k of super monkey. It is now placed
(2-0-2) right after the second Full Auto Rifle sniper, and only its 2-0-4
MOAB tier stays at the end.

Sunken Columns r33: the map's land is pools and narrow hex columns; the
first ninja popped nothing for 15 rounds and the damage model rated the
opening board 0.37-0.59 at rounds 17-18. The build is excluded there.

Run: python tests/test_apopalypse_exit_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

SID = "apopalypse_ninja_sniper"


def _plan():
    """The build's plan steps, in order."""
    return S.load_all()[SID]["plan"]


def _index(plan, **match):
    """Index of the first plan step whose fields equal `match`."""
    for i, step in enumerate(plan):
        if all(step.get(k) == v for k, v in match.items()):
            return i
    raise AssertionError(f"no plan step {match}")


def test_exit_spikes_come_before_the_maim_moab_tier():
    plan = _plan()
    place = _index(plan, do="place", id="sp1")
    assert plan[place]["role"] == "exit"
    assert place < _index(plan, do="upgrade", id="sp1", to="2-0-2")
    assert _index(plan, do="upgrade", id="sp1", to="2-0-2") < _index(plan, do="upgrade", id="s1", to="4-2-0")
    # the dear MOAB tier of the spikes stays last, after the super monkey
    assert _index(plan, do="upgrade", id="su1", to="3-0-2") < _index(plan, do="upgrade", id="sp1", to="2-0-4")
    # sp1 is placed exactly once
    assert sum(1 for s in plan if s.get("do") == "place" and s.get("id") == "sp1") == 1


def test_sunken_columns_is_excluded():
    s = dict(S.load_all()[SID], id=SID)
    spec = PL.StrategySpec.from_any(dict(s, **(s.get("planner") or {})))
    assert {"Sunken Columns", "Tricky Tracks"} <= set(spec.excluded_maps)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
