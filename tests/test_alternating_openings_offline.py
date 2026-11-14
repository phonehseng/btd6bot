"""Guide builds on maps whose rounds take turns on several lanes: the opening
reaches every lane its first rounds use, and those rounds hold on each lane.

Why
---
Some maps send each round down one of several lanes in turn (an
AlternateRoundSplitter: Water Park, Luminous Cove, Bazaar, Enchanted Glade,
Muddy Puddles; Erosion's 18-round phases; Bloonarius Prime's prime rounds
by a RuleSplitter). The damage model has one scenario per lane
(dps_model.Track.scenarios) and rates each round on its own
(Track.scenarios_in).

On 2026-11-12 two CHIMPS guide builds lost their one life early with the
opening beside one lane only:
  * Water Park (20:23, journal 20261112_202347_WaterPark_chimps): the dart
    (0.334, 0.828) and the boomerang (0.190, 0.726) had the slide between
    them and the second lane; round 6 came down it, nothing popped
    (tower_xp empty) and the game ended 12 s into the round. Rated on that
    lane, rounds 6-11 sat at the model's 0.06 floor.
  * Luminous Cove (16:04 and 16:40): the dart reached the right exit only;
    rounds 6 and 8 left by the left one. 31fd747 moved it.

tools/pin_spots.py had scored every spot by the route it covers over the
whole map. It now puts first the spots that reach every lane of the rounds
the tower must hold (Pinner.by_lanes, hold_window), seen as the live
forecast sees them (heights and all: MapSetup.use_live_sight).

Checked here, for every CHIMPS guide build (strategies/maps/*chimps*.yaml)
and every Impoppable map build (*_impoppable.yaml) on such a map:
  * each round from the mode's first through OPENING_ROUNDS later finds,
    on each lane the map data sends it down, a damage tower bought by then
    with MIN_LANE_UNITS of route in sight and range there (the lost Water
    Park spots fail it);
  * rounds 6-20, each played on every lane in turn on the board the plan
    has bought by then (optimize_builds.lane_margins), rate on their own
    lane no worse than LANE_SHARE of the round's best lane, or at least
    HOLDS: a round may be weak everywhere (the early-round margins of the
    won Beginner builds dip to 0.75), but not on one lane alone.

The Impoppable builds belong to another session: those that fail are kept
in IMPOPPABLE_KNOWN with what they need, and the test fails only when a
build outside that list fails, or one in it starts passing (then drop it
from the list).

Run: python tests/test_alternating_openings_offline.py (no game; several
minutes: each build is replayed once per lane)."""
import logging
import sys
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
import pin_spots  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

MAPS_DIR = ROOT / "strategies" / "maps"
# Rounds rated on every lane, from the mode's first (CHIMPS and Impoppable: 6-20).
RATED_ROUNDS = 15
# A round's own lane may rate this share of its best lane's margin at worst ...
LANE_SHARE = 0.5
# ... unless it rates at least HOLDS there: the early rounds of the won Beginner
# CHIMPS builds (Cracked, Carved, Hedge, Skates) dip to 0.75-0.9 in the model.
HOLDS = 0.7
# The spots of the lost Water Park game (journal 20261112_202347): the dart
# as planned, the boomerang where the game took it after refusing 0.206.
LOST_WATERPARK = {"x1": ("dart", (0.334, 0.828)), "r1": ("boomerang", (0.190, 0.726))}
# Impoppable map builds that fail a lane, with what they need (another
# session owns them; see the module docstring).
IMPOPPABLE_KNOWN = {
    # (muddypuddles_impoppable left this list on 2026-11-13: sky506 on the
    # right lanes 2979/2982 is now bought before sky504/sky505 on the left.)
}


def _alternating(path):
    """Is the build's map one whose rounds take turns on several lanes?"""
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    return len(_track(d["map"]).scenarios) > 1


@lru_cache(maxsize=None)
def _track(map_name):
    return D.Track(map_name)


def builds():
    """{build id: parsed YAML} of the guide and map builds on alternating maps."""
    out = {}
    for path in sorted(MAPS_DIR.glob("*.yaml")):
        if "chimps" not in path.stem and not path.stem.endswith("_impoppable"):
            continue
        if _alternating(path):
            out[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return out


@lru_cache(maxsize=None)
def _pinner(map_name, mode):
    return pin_spots.Pinner(map_name, mode)


def _reach(d, kind, at):
    """Route in sight and range on each lane of the map for ``kind`` at ``at``."""
    pin = _pinner(d["map"], d["modes"][0])
    return pin.lane_cover(kind, pin.model.frac_to_cell(*at))


def _damage(st):
    """Is a place step one for a tower that pops bloons by itself?"""
    return (st.get("do") == "place" and st.get("at") and st["kind"] != "hero"
            and st["kind"] not in S.Executor.BUFFERS)


def opening_gaps(d):
    """[(round, lane)] of the first OPENING_ROUNDS rounds whose lane no damage
    tower bought by then reaches (MIN_LANE_UNITS, live sight)."""
    mode = d["modes"][0]
    steps = d.get("plan") or []
    bought = pin_spots.buy_rounds(steps, mode, d.get("hero"))
    start = O.economy(mode).start_round
    track = _track(d["map"])
    towers = [(bought[i], st) for i, st in enumerate(steps) if i in bought and _damage(st)]
    starter = d.get("starter")
    if isinstance(starter, dict) and starter.get("at"):
        towers.append((start, dict(starter, do="place")))
    reach = {id(st): _reach(d, st["kind"], st["at"]) for _, st in towers}
    gaps = []
    for rnd in range(start, start + pin_spots.OPENING_ROUNDS):
        for k in track.scenarios_in(rnd):
            if not any(r <= rnd and reach[id(st)][k] >= pin_spots.MIN_LANE_UNITS for r, st in towers):
                gaps.append((rnd, track.scenario_paths[k]))
    return gaps


@lru_cache(maxsize=None)
def lane_ratings(sid):
    """(rounds, {lane: {round: margin}}, {round: [its lanes]}) for build ``sid``."""
    d = builds()[sid]
    start = O.economy(d["modes"][0]).start_round
    rounds = range(start, start + RATED_ROUNDS)
    return rounds, O.lane_margins(d, rounds), O.round_lanes(d["map"], rounds)


def lane_failures(sid):
    """[(round, its lane, margin there, best lane's margin)] of the rounds
    whose own lane rates under LANE_SHARE of their best lane and under HOLDS."""
    rounds, lanes, sched = lane_ratings(sid)
    out = []
    for rnd in rounds:
        best = max(m[rnd] for m in lanes.values())
        for key in sched[rnd]:
            own = lanes[key][rnd]
            if own < HOLDS and own < LANE_SHARE * best:
                out.append((rnd, key, own, best))
    return out


def test_the_alternating_maps_are_found():
    found = {d["map"] for d in builds().values()}
    assert {"Water Park", "Luminous Cove", "Bazaar", "Bloonarius Prime"} <= found, found


def test_the_lost_water_park_opening_misses_a_lane():
    d = builds()["waterpark_chimps"]
    for tid, (kind, at) in LOST_WATERPARK.items():
        assert min(_reach(d, kind, at)) < pin_spots.MIN_LANE_UNITS, (tid, _reach(d, kind, at))


def test_every_opening_reaches_the_lanes_of_its_first_rounds():
    bad = {}
    for sid, d in builds().items():
        gaps = opening_gaps(d)
        if gaps:
            bad[sid] = gaps
    unexpected = {sid: g for sid, g in bad.items() if sid not in IMPOPPABLE_KNOWN}
    assert not unexpected, unexpected


def test_rounds_6_to_20_hold_on_every_lane():
    bad = {}
    for sid in builds():
        fails = lane_failures(sid)
        if fails:
            bad[sid] = fails
    unexpected = {sid: f for sid, f in bad.items() if sid not in IMPOPPABLE_KNOWN}
    assert not unexpected, unexpected
    fixed = [sid for sid in IMPOPPABLE_KNOWN if sid not in bad and not opening_gaps(builds()[sid])]
    assert not fixed, f"passes now, drop from IMPOPPABLE_KNOWN: {fixed}"


if __name__ == "__main__":
    import inspect
    O.lower_priority()
    if "--table" in sys.argv:
        # the per-lane ratings of every build, for the report
        for sid in builds():
            rounds, lanes, sched = lane_ratings(sid)
            print(sid)
            for key, m in lanes.items():
                own = [m[r] for r in rounds if key in sched[r]]
                print(f"  lane {key}: worst on its own rounds {min(own) if own else '-'}, "
                      f"worst if every round took it {min(m.values())}")
            print("  opening gaps:", opening_gaps(builds()[sid]), " lane failures:", lane_failures(sid))
        sys.exit(0)
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                print("FAIL", fname, repr(e)[:1500])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
