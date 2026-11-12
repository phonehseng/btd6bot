"""Map builds for the Impoppable maps the general builds keep losing (2026-11-11).

On Quad, Covered Garden, Sunken Columns, Bloonarius Prime, Peninsula,
Firing Range and Midnight Mansion, chimps_ninja_sun reached rounds 59-98 and
lost with its plan steps given up on refused spots and most of its cash in
off-plan buys. tools/pin_spots.py wrote each map its own copy: an exact legal
spot per tower and plan_first, marked untested at the map builds' lowest
base_success. planner.first_trial lets such a build play its first game on
a map/mode that hopeless() would otherwise skip.

The spots' legality in plan order, coverage and the threat simulation are
checked for every map build in tests/test_map_hints_offline.py.

Run: python tests/test_impoppable_map_builds_offline.py"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pin_spots  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402

MAPS = {"quad": "Quad", "coveredgarden": "Covered Garden", "sunkencolumns": "Sunken Columns",
        "bloonariusprime": "Bloonarius Prime", "peninsula": "Peninsula", "firingrange": "Firing Range",
        "midnightmansion": "Midnight Mansion"}


def _build(map_id):
    path = ROOT / "strategies" / "maps" / f"{map_id}_impoppable.yaml"
    return path.read_text(encoding="utf-8"), yaml.safe_load(path.read_text(encoding="utf-8"))


def test_each_map_has_its_untested_plan_first_build():
    for map_id, name in MAPS.items():
        text, d = _build(map_id)
        assert "UNTESTED" in text, map_id
        assert d["map"] == name and d["modes"] == ["impoppable"], map_id
        assert d["plan_first"] is True, map_id
        assert d["planner"]["base_success"] == {"impoppable": pin_spots.UNTESTED_SUCCESS}, map_id
        assert d["planner"]["maps"] == [name], map_id
        placed = [st for st in d["plan"] if st["do"] == "place" and st["kind"] != "hero" and st.get("role") != "exit"]
        assert sum(1 for st in placed if st.get("at")) >= len(placed) * 0.6, (map_id, "most towers pinned")


def test_midnight_mansion_uses_only_towers_that_fit():
    """No village, super, ace, heli or spike factory has a legal cell there."""
    _, d = _build("midnightmansion")
    kinds = {st["kind"] for st in d["plan"] + d.get("fill", []) if st["do"] == "place"}
    assert not kinds & {"village", "super", "ace", "heli", "spike"}, kinds


def test_answers_place_planned_towers_at_their_plan_spots():
    for map_id in MAPS:
        _, d = _build(map_id)
        spots = {st["id"]: st["at"] for st in d["plan"] if st["do"] == "place" and st.get("at")}
        for steps in (d.get("answers") or {}).values():
            for st in steps:
                if st["do"] == "place" and st.get("id") in spots:
                    assert st.get("at") == spots[st["id"]], (map_id, st)


def _spec(sid, maps=None):
    return P.StrategySpec.from_any({"id": sid, "towers": {}, "modes": ["impoppable"],
                                    "base_success": {"impoppable": 0.5}, "maps": maps})


def test_a_maps_own_build_gets_one_first_trial():
    acc = AccountState()
    own = _spec("quad_impoppable", ["Quad"])
    general = _spec("chimps_ninja_sun")
    assert P.first_trial(acc, own, "Quad", "impoppable")
    assert not P.first_trial(acc, general, "Quad", "impoppable")
    acc.record_result("Quad", "impoppable", "quad_impoppable", False, round_reached=95)
    assert not P.first_trial(acc, own, "Quad", "impoppable")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
