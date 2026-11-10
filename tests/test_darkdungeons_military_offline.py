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
  own flight circle (dps_model.STRICT_OWN_REACH).

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


def test_rounds_hold_to_60_with_map_wide_aces():
    margins, bought, total = replay_margins(strict=False)
    assert bought == total, (bought, total)
    weak = {r: round(m, 2) for r, m in margins.items() if m < FLOOR}
    assert not weak, weak


def test_rounds_hold_to_60_with_aces_on_their_own_circle():
    margins, _, _ = replay_margins(strict=True)
    weak = {r: round(m, 2) for r, m in margins.items() if m < FLOOR}
    assert not weak, weak


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
