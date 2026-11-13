"""Quiet Street CHIMPS: the spike factory and Ring of Fire before the sniper tiers (2026-11-13).

Loss case 20261113_062147_QuietStreet_chimps: the guide build held rounds
6-51 on its one life and lost round 52. From round 34 on the bloons came
86-96% along the route in seventeen of nineteen rounds and the live
forecast called ten of them crisis rounds, while the plan bought sniper
tiers and saved for Elite Sniper. No cash stood idle: the order was wrong
for the bot, which plays the guide without its micro.

The build now buys the spike factory with Spiked Balls before the first
Semi-Automatic and the tack's Ring of Fire before the fourth sniper's
Semi-Automatic; the guide buys both in the sixties.

Checked here:
  * the order of those steps;
  * replayed as the executor buys (optimize_builds.replay_plan, CHIMPS
    cash, live sight), the rounds from 40 to 58 that the lost game's order
    rated under 1.0 all rate higher, round 52 above 1.0, and fewer of
    rounds 31-59 rate under 1.0 than before.

Legal spots and the plan's cost by round 100 are checked for every guide
build in test_chimps_intermediate_guides_offline.py.

Run: python tests/test_quietstreet_chimps_midgame_offline.py (no game)."""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402

BUILD = ROOT / "strategies" / "maps" / "quietstreet_chimps.yaml"
MIDGAME = tuple(range(31, 60))
LOST_ROUND = 52
# rounds 40-58 the lost game's order rated under 1.0
WEAK_BEFORE = (40, 45, 50, 52, 53, 54, 57, 58)


def _build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def _upgrade(plan, tower, tiers):
    """Position of the step that takes `tower` to `tiers`."""
    return next(i for i, st in enumerate(plan) if st.get("id") == tower and st.get("to") == tiers)


def _place(plan, tower):
    """Position of the step that places `tower`."""
    return next(i for i, st in enumerate(plan) if st["do"] == "place" and st["id"] == tower)


def _moved_after(plan, picked, anchor):
    """`plan` with the steps at the positions `picked` moved, in order, to
    stand right after the step at position `anchor`."""
    moving = [plan[i] for i in picked]
    out = []
    for i, st in enumerate(plan):
        if i not in picked:
            out.append(st)
        if i == anchor:
            out.extend(moving)
    return out


def _lost_games_plan(d):
    """The same build in the order the lost game played: the spike factory
    after Stronger Stimulant, Ring of Fire after the spike factory."""
    old = copy.deepcopy(d)
    plan = old["plan"]
    spikes = [_place(plan, "p1"), _upgrade(plan, "p1", "3-2-0")]
    plan = _moved_after(plan, spikes, _upgrade(plan, "a1", "4-0-1"))
    plan = _moved_after(plan, [_upgrade(plan, "t1", "4-0-2")], _upgrade(plan, "p1", "3-2-0"))
    old["plan"] = plan
    return old


def test_spike_factory_and_ring_of_fire_come_before_the_sniper_tiers():
    plan = _build()["plan"]
    assert _place(plan, "p1") < _upgrade(plan, "p1", "3-2-0") < _upgrade(plan, "sa", "0-3-2")
    assert _upgrade(plan, "t1", "3-0-2") < _upgrade(plan, "t1", "4-0-2") < _upgrade(plan, "sd", "0-3-2")
    assert _upgrade(plan, "t1", "4-0-2") < _upgrade(plan, "sa", "0-5-2")


def test_the_lost_games_order_is_rebuilt_as_it_was_played():
    old = _lost_games_plan(_build())["plan"]
    assert _upgrade(old, "sa", "0-5-2") < _upgrade(old, "a1", "4-0-1") < _place(old, "p1")
    assert _upgrade(old, "p1", "3-2-0") + 1 == _upgrade(old, "t1", "4-0-2") < _upgrade(old, "sb", "4-2-0")


def test_the_midgame_rates_above_the_lost_games_order():
    d = _build()
    new = O.replay_plan(d, rounds=MIDGAME, live_sight=True)
    old = O.replay_plan(_lost_games_plan(d), rounds=MIDGAME, live_sight=True)
    for rnd in WEAK_BEFORE:
        assert old[rnd] < 1.0 and new[rnd] > old[rnd], (rnd, old[rnd], new[rnd])
    assert new[LOST_ROUND] > 1.0, new[LOST_ROUND]
    assert sum(new[r] < 1.0 for r in MIDGAME) < sum(old[r] < 1.0 for r in MIDGAME)
    assert min(new.values()) > min(old.values())


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
