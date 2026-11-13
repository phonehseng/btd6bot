"""Haunted CHIMPS: no idle rounds between the Eliminator and Cripple MOAB (2026-11-13).

Loss case 20261113_060245_Haunted_chimps: round 92 (50 fortified MOABs and
4 ZOMGs) was lost with $12,451 unspent. The MOAB Eliminator had been bought
at round 87 and the plan's next step, Cripple MOAB, costs $34,560: five
rounds of saving while the live forecast rated round 92 under 1.0, and
plan_first buys nothing off the plan.

The build now buys a Sticky Bomb ninja (2-0-4) by the right-hand exit
before the bomb and a second one by the left-hand exit after the
Eliminator; the wizard, the plan's last step, is left out so that Cripple
MOAB stays affordable by round 100.

Checked here:
  * the order of those steps, one ninja on each side of the stairs, and
    that no step asks for the wizard;
  * replayed as the executor buys (optimize_builds.replay_plan, CHIMPS
    cash, live sight), rounds 90-94 rate above 1.0 and every round from 90
    to 97 rates above the same plan with the lost game's ending.

Legal spots and the plan's cost by round 100 are checked for every guide
build in test_chimps_intermediate_guides_offline.py.

Run: python tests/test_haunted_chimps_sticky_ninjas_offline.py (no game)."""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402

BUILD = ROOT / "strategies" / "maps" / "haunted_chimps.yaml"
STICKY_BOMB = "2-0-4"
# what the lost game still had to buy after the Eliminator
OLD_ENDING = [
    {"do": "upgrade", "id": "s1", "to": "5-1-0"},
    {"do": "place", "id": "w1", "kind": "wizard", "role": "dps", "at": [0.238, 0.606]},
    {"do": "upgrade", "id": "w1", "to": "4-2-0"},
]
HELD = tuple(range(90, 95))      # rounds the new plan must rate above 1.0
BETTER = tuple(range(90, 98))    # rounds it must rate above the lost game's plan
STAIRS_X = 0.42                  # the stairs' screen fraction: the boat's pond lies on it


def _build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def _upgrade(plan, tower, tiers):
    """Position of the step that takes `tower` to `tiers`."""
    return next(i for i, st in enumerate(plan) if st.get("id") == tower and st.get("to") == tiers)


def _place(plan, tower):
    """Position of the step that places `tower`."""
    return next(i for i, st in enumerate(plan) if st["do"] == "place" and st["id"] == tower)


def _lost_games_plan(d):
    """The same build as the lost game played it: no ninjas, and after the
    Eliminator Cripple MOAB, then the wizard."""
    old = copy.deepcopy(d)
    steps = [st for st in d["plan"] if st.get("id") not in ("n1", "n2")]
    old["plan"] = copy.deepcopy(steps[:1 + _upgrade(steps, "e1", "0-5-0")]) + copy.deepcopy(OLD_ENDING)
    return old


def test_a_sticky_bomb_ninja_stands_on_each_side_before_cripple_moab():
    d = _build()
    plan = d["plan"]
    assert _upgrade(plan, "s1", "4-1-0") < _place(plan, "n1") < _upgrade(plan, "n1", STICKY_BOMB) < _place(plan, "e1")
    assert (_upgrade(plan, "e1", "0-5-0") < _place(plan, "n2") < _upgrade(plan, "n2", STICKY_BOMB)
            < _upgrade(plan, "s1", "5-1-0"))
    right, left = plan[_place(plan, "n1")], plan[_place(plan, "n2")]
    assert right["kind"] == left["kind"] == "ninja"
    assert left["at"][0] < STAIRS_X < right["at"][0]
    assert not any(st.get("kind") == "wizard" for st in plan)
    assert d["planner"]["towers"]["ninja"] == [2, 0, 4]
    assert "wizard" not in d["planner"]["towers"]


def test_rounds_90_to_97_rate_above_the_lost_games_plan():
    d = _build()
    new = O.replay_plan(d, rounds=BETTER, live_sight=True)
    old = O.replay_plan(_lost_games_plan(d), rounds=BETTER, live_sight=True)
    for rnd in HELD:
        assert new[rnd] > 1.0, (rnd, new[rnd])
    for rnd in BETTER:
        assert new[rnd] > old[rnd], (rnd, old[rnd], new[rnd])


if __name__ == "__main__":
    import inspect
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", fname, repr(e)[:600])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
