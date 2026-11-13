"""Dark Dungeons Military Only (strategies/maps/darkdungeons_military_only.yaml).

Six general builds lost this map/mode (2026-11-04..10). The walls between
its rooms block sight, and three bloon lanes run at once, so the build puts
snipers on the floor of every room. These checks hold it to that:

* every lane - the three bloon lanes and both MOAB lanes - is seen by some
  sniper of the plan (line of sight through the walls, no height bonus);
* replayed as the executor buys (in order, as cash allows) on the account's
  economy (Fast Track start at round 15, Double Cash income), every round
  15-60 pops at full strength in the damage model: margin >= 1.0 both with
  map-wide aces (the live forecast's reading) and with aces held to their
  own flight circle (dps_model.STRICT_OWN_REACH) - except rounds 40 and 60
  (KNOWN_SHORT), which the build does NOT hold.

Rounds 40 and 60 bring one blimp. The model used to put half of it on each
of the two MOAB lanes; since 2026-11-11 it sends it whole down either lane
and counts the worse (dps_model._undivided). On the top lane the build
still holds (1.04 and 1.02); on the middle lane it rates 0.70 and 0.67 with
aces on their own circle: the snipers shoot the blimp down, but one rainbow
(round 40) and eleven rainbows with two or three ceramics (round 60) of what
comes out of it get past the lane's end, where nothing with an area attack
stands. The build's one live game (2026-11-10 16:42) was lost in round 50.
Until the build is reworked (docs/backlog.md item 90) these checks hold the
two rounds to what they rate today, so a change that makes them worse still
fails here.

Run: python tests/test_darkdungeons_military_offline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402

BUILD = ROOT / "strategies" / "maps" / "darkdungeons_military_only.yaml"
MODE = "military_only"
# the replay's start: Fast Track's round 15 with the optimizer's cautious cash
# (optimize_builds.fast_track_start: 90% of the skipped rounds' income)
BOOSTS = {"double_cash": True, "fast_track": True}
FLOOR = 1.0
# The lone-blimp rounds the build does not hold (module docstring) and the
# least they may rate: a little under today's 0.70 / 0.67 (aces on their own
# circle) and 0.73 / 0.81 (map-wide aces).
KNOWN_SHORT = {40: 0.65, 60: 0.62}
# Phase 1 of docs/model_fix_plan.md (2026-11-12) rates the build lower: its
# Bomber Aces' bombs fall under the plane only while it is over the track
# (no longer on the whole map), its buccaneers' rear shots need track behind
# them, and the map-wide reading of the aces is now the same as the strict
# one. Rounds 50-54 and 60 rate 0.84, 0.74, 0.98, 0.91 and 0.52 (the build's
# one live game was lost in round 50); they are held a little under that.
KNOWN_SHORT.update({50: 0.8, 52: 0.7, 53: 0.93, 54: 0.87, 60: 0.48})
# Since 93c2d83 (2026-11-12, few blimps are few: a zone holds no more than
# the group sent down it, a projectile's pierce counts only the blimps
# within its reach) round 40's lone MOAB rates 0.39 (0.70 before): the
# snipers' pierce no longer counts on blimps that are not there. Rounds 53
# and 54 now hold (1.0 or more, 0.98 and 0.91 before; 52 0.74 -> 0.82, 60
# 0.52 -> 0.58), so they leave KNOWN_SHORT as
# test_the_lone_blimp_rounds_are_still_short asks. The build won this map
# live on 2026-11-12 11:46 (round 60, round 40 held); round 40's floor is
# today's number less a little.
KNOWN_SHORT[40] = 0.35
del KNOWN_SHORT[53], KNOWN_SHORT[54]

_SETUP = {}


def setup():
    if "s" not in _SETUP:
        s = O.MapSetup("Dark Dungeons", MODE)
        _SETUP["s"] = s
        _SETUP["sight"] = D.sight_test(s.model.sight, s.track)
    return _SETUP["s"], _SETUP["sight"]


def plan():
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


def placed_at(st, s):
    sp = s.cell_spot(s.model.frac_to_cell(*st["at"]))
    return sp.x, sp.z


def test_every_lane_is_seen_by_a_sniper():
    s, sight = setup()
    seen = [0.0] * len(s.track.paths)
    for st in plan()["plan"]:
        if st.get("do") == "place" and st.get("kind") == "sniper":
            x, z = placed_at(st, s)
            t = D.Placed(st["id"], "sniper", (0, 0, 0), x, z)
            station = D.station_for(t, [t], s.track, sight=sight)
            for i, zone in enumerate(station.zones if station else ()):
                if zone:
                    seen[i] = max(seen[i], zone.length)
    names = [p["name"] for p in s.track.paths]
    # 100 world units: about a third of a lane, in sight from one spot
    assert all(v >= 100 for v in seen), dict(zip(names, seen))


def replay_margins(strict):
    s, sight = setup()
    econ = O.economy(MODE, BOOSTS)
    p = plan()
    steps = [st for st in p["plan"] if st.get("do") in ("place", "upgrade")]
    towers, cash, i, out = {}, econ.start_cash, 0, {}
    for rnd in range(econ.start_round, econ.end_round + 1):
        while i < len(steps):
            st = steps[i]
            if st["do"] == "place" and st["kind"] == "hero":
                cost = T.hero_cost(p["hero"], econ.family)
            elif st["do"] == "place":
                cost = T.tower_cost(st["kind"], econ.family)
            else:
                kind, tiers, x, z = towers[st["id"]]
                new = tuple(int(c) for c in str(st["to"]).split("-"))
                cost = O.upgrade_cost(kind, tiers, new, econ.family)
            if cost > cash:
                break
            cash -= cost
            if st["do"] == "place" and st["kind"] != "hero":
                towers[st["id"]] = (st["kind"], (0, 0, 0)) + placed_at(st, s)
            elif st["do"] == "upgrade":
                towers[st["id"]] = (kind, new, x, z)
            i += 1
        placed = [D.Placed(tid, k, tiers, x, z) for tid, (k, tiers, x, z) in towers.items()]
        stations = D.stations_for(placed, s.track, sight, strict=strict)
        out[rnd] = D.round_margin(stations, MODE, rnd, s.track)
        cash += econ.income(rnd)
    return out, i, len(steps)


def _weak_rounds(margins):
    """The rounds rated under their floor: FLOOR, or the KNOWN_SHORT value
    for a round the build is known not to hold."""
    return {r: round(m, 2) for r, m in margins.items() if m < KNOWN_SHORT.get(r, FLOOR)}


def test_rounds_hold_to_60_with_map_wide_aces():
    margins, bought, total = replay_margins(strict=False)
    assert bought == total, (bought, total)
    assert not _weak_rounds(margins), _weak_rounds(margins)


def test_rounds_hold_to_60_with_aces_on_their_own_circle():
    margins, _, _ = replay_margins(strict=True)
    assert not _weak_rounds(margins), _weak_rounds(margins)


def test_the_lone_blimp_rounds_are_still_short():
    """Rounds 40 and 60 rate under 1.0 on this build (KNOWN_SHORT). When a
    reworked build holds them this fails: take the round out of KNOWN_SHORT
    then, so the checks above ask FLOOR of it again."""
    margins, _, _ = replay_margins(strict=True)
    held = [r for r in KNOWN_SHORT if margins[r] >= FLOOR]
    assert not held, held


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e)[:600])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
