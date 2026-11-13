"""Polyphemus CHIMPS: no fifteen idle rounds before Superstorm (2026-11-13).

Loss case 20261113_023838_Polyphemus_chimps: round 82 was lost with $40,362
unspent. The plan had bought the second druid's Ball Lightning by round 67
and then saved for Superstorm; the live forecast rated rounds 78-83 at
0.34-0.77 the whole time and plan_first buys nothing off the plan.

The build now takes the starter dart to Crossbow Master before Superstorm
and leaves the Perma-Spike out (the plan must stay affordable by round 100).

Checked here:
  * the dart's 0-2-5 step stands before Superstorm, Ball Lightning for the
    second druid and the spike factory after it, and no step asks for the
    Perma-Spike;
  * replayed as the executor buys (optimize_builds.replay_plan, CHIMPS
    cash, live sight), rounds 79-88 all rate above 1.0, and above the same
    plan with the lost game's ending.

Run: python tests/test_polyphemus_chimps_late_offline.py (no game)."""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402

BUILD = ROOT / "strategies" / "maps" / "polyphemus_chimps.yaml"
# the ending the lost game played, after the first druid's Ball Lightning
OLD_ENDING = [
    {"do": "place", "id": "p1", "kind": "spike", "role": "dps", "segment": [0.85, 1.0], "at": [0.751, 0.777]},
    {"do": "upgrade", "id": "p1", "to": "2-0-4"},
    {"do": "upgrade", "id": "dr1", "to": "4-0-0"},
    {"do": "upgrade", "id": "d1", "to": "5-0-2"},
    {"do": "upgrade", "id": "p1", "to": "2-0-5"},
]
IDLE_ROUNDS = tuple(range(79, 89))   # the rounds the old ending spent saving
WEAK_BEFORE = (79, 80, 83, 84, 85, 87, 88)   # of those, the ones it rated under 1.0


def _build():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def _index(plan, tower, tiers):
    """Position of the step that takes `tower` to `tiers`."""
    return next(i for i, st in enumerate(plan) if st.get("id") == tower and st.get("to") == tiers)


def test_crossbow_master_comes_before_superstorm():
    d = _build()
    plan = d["plan"]
    storm = _index(plan, "d1", "5-0-2")
    assert _index(plan, "da1", "0-2-5") < storm
    assert _index(plan, "dr1", "3-0-0") < _index(plan, "da1", "0-2-5")
    assert storm < _index(plan, "dr1", "4-0-0")
    assert storm < next(i for i, st in enumerate(plan) if st["do"] == "place" and st["id"] == "p1")
    assert not any(st.get("id") == "p1" and st.get("to") == "2-0-5" for st in plan)
    assert d["planner"]["towers"]["dart"] == [0, 2, 5]
    assert d["planner"]["towers"]["spike"] == [2, 0, 4]


def test_rounds_79_to_88_rate_above_one_and_above_the_old_ending():
    d = _build()
    new = O.replay_plan(d, rounds=IDLE_ROUNDS, live_sight=True)
    old_plan = copy.deepcopy(d)
    cut = 1 + _index(d["plan"], "d1", "4-0-2")
    old_plan["plan"] = copy.deepcopy(d["plan"][:cut]) + copy.deepcopy(OLD_ENDING)
    old = O.replay_plan(old_plan, rounds=IDLE_ROUNDS, live_sight=True)
    for rnd in IDLE_ROUNDS:
        assert new[rnd] > 1.0, (rnd, new[rnd])
    for rnd in WEAK_BEFORE:
        assert old[rnd] < 1.0 < new[rnd], (rnd, old[rnd], new[rnd])


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
