"""Offline tests for the researched map hints and the map-specific strategies.

data/map_strategy_hints.json holds, per map, what community guides do there
(docs/map_strategies.md has the findings and sources): preferred towers per
mode, towers to avoid, removable obstacles worth buying, and spot lists in
buy order. strategies/maps/<map>_<mode>.yaml are builds for maps that no
general strategy handles, with exact spots (`at: [fx, fy]`, screen fractions
of the 1920x1200 window).

Checked here:
  * the hints load, name real maps, towers, heroes, modes and removables;
  * every hinted spot is a legal spot for its tower on the map's geometry
    (placement.valid_spots on a MapModel filled by mapgeom.apply), in build
    order - each spot given the towers placed before it - for the longest
    game the build serves;
  * every map strategy loads, is valid and bot-ready (apart from the `at` step
    key the executor does not read yet), is usable and covers every threat in
    each mode it lists on a fully unlocked account, passes the offline threat
    simulation (tools/simulate_threats.py: real prices and income, no bloon
    the defence cannot pop), and every `at` is legal in plan order.

Run: python tests/test_map_hints_offline.py (also collectable by pytest).
Never touches the game, mouse or keyboard."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import mapgeom as G  # noqa: E402
from btd6bot import placement as PL  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.account import MAPS, canonical_map  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

import simulate_threats as SIM  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)
for _name in ("strategy", "threats", "planner", "mapfit", "mapgeom", "placement"):
    logging.getLogger(_name).setLevel(logging.ERROR)

HINTS_FILE = ROOT / "data" / "map_strategy_hints.json"
MAP_STRAT_DIR = S.STRAT_DIR / "maps"
PLAYFIELD = LAYOUTS["16:10"]["playfield"]
LANE_TYPES = {"single", "simultaneous", "alternating", "rotating", "merging"}
BUY = {"recommended", "optional", "never"}
# Towers that buff or earn instead of popping: their spot need not reach the track.
SUPPORT = {"alchemist", "village", "farm"}

_MODELS = {}


def hints():
    return json.loads(HINTS_FILE.read_text(encoding="utf-8"))


def model(map_name):
    """A MapModel filled from the map's game geometry (as mapfit does)."""
    if map_name not in _MODELS:
        geom = G.load(map_name)
        assert geom is not None, f"{map_name}: no geometry"
        m = MapModel(map_name, PLAYFIELD)
        G.apply(m, geom)
        _MODELS[map_name] = m
    return _MODELS[map_name]


def illegal_spots(map_name, spots, last_round):
    """Spots [(kind, hero, (fx, fy))] that are not legal, placed in order."""
    m = model(map_name)
    placed, bad = [], []
    for kind, hero, (fx, fy) in spots:
        ok = PL.valid_spots(m, kind, hero, placed, last_round=last_round)
        cx, cy = m.frac_to_cell(fx, fy)
        inside = 0 <= cy < ok.shape[0] and 0 <= cx < ok.shape[1]
        if not (inside and ok[cy, cx]):
            bad.append((kind, hero, (fx, fy)))
        placed.append((cx, cy, kind, hero))
    return bad


def longest(modes):
    return max(S.MODE_RULES[m]["end_round"] for m in modes)


def map_strategies():
    """{id: strategy} of strategies/maps/*.yaml, read as load_all reads files."""
    out = {}
    for f in sorted(MAP_STRAT_DIR.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert isinstance(d, dict), f.name
        d.setdefault("id", f.stem)
        assert d["id"] == f.stem, (f.name, d["id"])
        out[d["id"]] = d
    return out


def readiness_with_at(strat):
    """strategy.readiness, with `at` (an exact spot) accepted as a step key."""
    saved = S.STEP_KEYS
    S.STEP_KEYS = set(saved) | {"at"}
    try:
        return S.readiness(strat)
    finally:
        S.STEP_KEYS = saved


# -- the hints file --------------------------------------------------------------------

def test_hints_load():
    d = hints()
    assert d["version"] == 1 and d["maps"]
    for name, h in d["maps"].items():
        assert canonical_map(name) == name, name
        assert h["category"] == MAPS[name], name
        assert h["insight"] and h["lane_type"] in LANE_TYPES, name
        assert h["sources"] and all(u.startswith("http") for u in h["sources"]), name
        builds = h["builds"]
        assert builds and sum(1 for b in builds if b.get("default")) == 1, name
        claimed = []
        for b in builds:
            assert b["modes"], (name, b["id"])
            for m in b["modes"]:
                assert m in S.MODE_RULES, (name, b["id"], m)
            claimed += b["modes"]
            assert b["last_round"] == longest(b["modes"]), (name, b["id"])
            assert b.get("hero") is None or b["hero"] in T.HEROES, (name, b["hero"])
            assert b["source"].startswith("http"), (name, b["id"])
            for s in b["spots"]:
                assert s["tower"] in T.TOWERS or (s["tower"] == "hero" and s["hero"] in T.HEROES), (name, s)
                fx, fy = s["at"]
                x0, y0, x1, y1 = PLAYFIELD
                assert x0 <= fx <= x1 and y0 <= fy <= y1, (name, s)
            assert b["towers"] == list(dict.fromkeys(s["tower"] for s in b["spots"] if s["tower"] != "hero"))
        assert len(claimed) == len(set(claimed)), (name, "a mode served by two builds")
        for a in h["avoid"]:
            assert a["tower"] in T.TOWERS and a["why"], (name, a)
            for m in a.get("modes") or []:
                assert m in S.MODE_RULES, (name, a)
        names = {r["name"] for r in G.removables(name, PLAYFIELD)}
        for r in h.get("removables", []):
            assert r["name"] in names, (name, r["name"])
            assert r["buy"] in BUY and r["why"] and r["source"].startswith("http"), (name, r)
        for sid in h.get("strategies", []):
            assert (MAP_STRAT_DIR / f"{sid}.yaml").is_file(), (name, sid)


def test_every_lost_and_expert_map_has_hints():
    """The maps the bot lost and every Advanced/Expert map are covered."""
    have = set(hints()["maps"])
    lost = {"Luminous Cove", "Castle Revenge", "Dark Path", "Last Resort", "Pat's Pond", "Party Parade",
            "Enchanted Glade", "Covered Garden", "Ancient Portal", "Bloonarius Prime"}
    assert lost <= have, lost - have
    hard_maps = {m for m, cat in MAPS.items() if cat in ("advanced", "expert") and G.load(m) is not None}
    assert hard_maps <= have, hard_maps - have


def test_every_spot_is_legal_for_its_tower():
    for name, h in hints()["maps"].items():
        for b in h["builds"]:
            spots = [(s["tower"], s.get("hero"), tuple(s["at"])) for s in b["spots"]]
            bad = illegal_spots(name, spots, b["last_round"])
            assert not bad, (name, b["id"], bad)


def test_damage_spots_reach_the_track():
    """A hinted damage tower with a finite range has track within its range
    (line of sight left out: some spots see over walls the model cannot judge)."""
    import numpy as np
    for name, h in hints()["maps"].items():
        m = model(name)
        track = m.t_cnt > 0
        hh, ww = track.shape
        yy, xx = np.mgrid[0:hh, 0:ww]
        for b in h["builds"]:
            for s in b["spots"]:
                rng = PL.reach_units(s["tower"], s.get("hero"))
                if s["tower"] in SUPPORT or s["tower"] == "hero" or not rng:
                    continue
                cx, cy = m.frac_to_cell(*s["at"])
                rc = rng / PL.units_per_cell(m)
                near = track & ((xx - cx) ** 2 + (yy - cy) ** 2 <= rc * rc)
                assert near.any(), (name, b["id"], s)


# -- map strategies ----------------------------------------------------------------------

def test_map_strategies_load_valid_and_ready():
    strats = map_strategies()
    assert strats
    general = S.load_all()
    pinned = {sid: name for name, h in hints()["maps"].items() for sid in h.get("strategies", [])}
    for sid, s in strats.items():
        assert canonical_map(s["map"]) == s["map"], sid
        assert s["planner"].get("maps") == [s["map"]], sid
        # builds listed in data/map_strategy_hints.json must be listed under
        # their own map; the per-group research builds are not listed there
        assert sid not in pinned or pinned[sid] == s["map"], (sid, "listed under another map's hints")
        assert S.validate(s) == [], (sid, S.validate(s))
        assert readiness_with_at(s) == [], (sid, readiness_with_at(s))
        assert set(s["planner"]["base_success"]) == set(s["modes"]), sid
        assert sid not in general or general[sid].get("map") == s["map"], (sid, "id clash")
        for mode in s["modes"]:
            assert mode in S.MODE_RULES, (sid, mode)
            # conservative: below the hand-tested strategies of the same difficulty
            assert 0.5 <= s["planner"]["base_success"][mode] <= 0.85, (sid, mode)


def test_map_strategies_usable_and_covered():
    acct = SIM.full_account()
    for sid, s in map_strategies().items():
        s = dict(s, bot_ready=True)
        for mode in s["modes"]:
            ok, why = S.usable(s, mode, acct, map_name=s["map"])
            assert ok, (sid, mode, why)
            ok, why = S.usable(s, mode, acct, map_name="Monkey Meadow")
            assert not ok, (sid, "usable on another map")
            ok, missing = S.coverage(s, mode, acct)
            assert ok, (sid, mode, missing)


def test_map_strategy_spots_are_legal():
    """Every `at` in plan/fill order is a legal spot for its tower; an answer
    step that re-places a planned tower uses that tower's own spot."""
    for sid, s in map_strategies().items():
        hero = s.get("hero")
        spots, where = [], {}
        for st in (s.get("plan") or []) + (s.get("fill") or []):
            if st.get("do") == "place" and st.get("at"):
                kind = st["kind"]
                spots.append((kind, hero if kind == "hero" else None, tuple(st["at"])))
                where[st.get("id")] = tuple(st["at"])
        bad = illegal_spots(s["map"], spots, longest(s["modes"]))
        assert not bad, (sid, bad)
        for steps in (s.get("answers") or {}).values():
            for st in steps:
                if st.get("do") == "place" and st.get("at"):
                    if st.get("id") in where:
                        # re-placing a planned tower: at that tower's own spot
                        assert where[st["id"]] == tuple(st["at"]), (sid, st)
                    else:
                        # a tower of the answer's own: a legal spot
                        kind = st["kind"]
                        one = [(kind, hero if kind == "hero" else None, tuple(st["at"]))]
                        assert not illegal_spots(s["map"], one, longest(s["modes"])), (sid, st)


def test_map_strategies_pass_the_threat_simulation():
    """No round brings a bloon the defence cannot pop, with the real prices
    and the game's base income (no Double Cash), in every listed mode."""
    for sid, s in map_strategies().items():
        for mode in s["modes"]:
            r = SIM.simulate(dict(s, bot_ready=True), mode)
            assert not r["gaps"], (sid, mode, r["gaps"][:3])
            done, total = (int(x) for x in r["plan_done"].split("/"))
            if S.MODE_FAMILY[mode] == "easy":
                # Deflation: everything is bought with the starting cash
                assert done == total or (done == total - 1 and s["plan"][-1]["kind"] == "hero"), \
                    (sid, mode, r["plan_done"])


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
