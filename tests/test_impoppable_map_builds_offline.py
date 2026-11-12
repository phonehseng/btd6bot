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

2026-11-12: Sunken Columns' sb1 was pinned on water the live game had
refused for a sub (the worktree's data/maps copy held no refusals); the step
was set aside and the one-life game lost at round 6. pin_spots now reads the
live map file and never pins a refused cell; the tests below hold it to that.

Run: python tests/test_impoppable_map_builds_offline.py"""
import sys
from pathlib import Path

import numpy as np
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


class _Model:
    """The parts of a MapModel the refusal and proof checks read."""

    def __init__(self, shape=(20, 30)):
        self.heat = np.zeros(shape)
        self.refused, self.accepted, self.spot_stats = {}, {}, {}

    def refused_mask(self, layer):
        return self.refused.get(layer, np.zeros(self.heat.shape, bool))

    def accepted_mask(self, surface):
        return self.accepted.get(surface, np.zeros(self.heat.shape, bool))


def test_a_cell_refused_for_the_kind_is_never_pinned():
    m = _Model()
    m.refused["water@sub"] = np.zeros(m.heat.shape, bool)
    m.refused["water@sub"][5, 7] = True          # refused for a sub only
    m.refused["land"] = np.zeros(m.heat.shape, bool)
    m.refused["land"][2, 3] = True               # bad ground for every land tower
    assert not pin_spots.never_refused(m, "sub", (7, 5))
    assert pin_spots.never_refused(m, "sub", (8, 5))
    assert not pin_spots.never_refused(m, "ninja", (3, 2))
    assert pin_spots.never_refused(m, "ninja", (7, 5)), "a sub's own layer says nothing to a ninja"


def test_cells_a_kind_stood_on_count_as_proven():
    m = _Model()
    m.spot_stats["sub|2|1"] = [1.0, 1]           # a sub stood in the 4x4 bucket at cells x 8-11, y 4-7
    m.accepted["water"] = np.zeros(m.heat.shape, bool)
    m.accepted["water"][0, 0] = True
    proven = pin_spots.proven_cells(m, "sub")
    assert proven[4, 8] and proven[7, 11] and proven[0, 0]
    assert not proven[8, 8] and not pin_spots.proven_cells(m, "ninja")[4, 8]


def test_the_live_map_files_are_read():
    """A worktree's data/maps is git's copy (Sunken Columns held no refusals
    there); the pins come from the main checkout's, which the bot writes."""
    live = pin_spots.live_maps_dir()
    assert live.name == "maps" and live.parent.name == "data" and live.is_dir()


def test_no_pinned_spot_is_refused_in_the_live_map_file():
    from btd6bot import layout as L
    from btd6bot import maplearn as ML
    playfield = L.LAYOUTS["16:10"]["playfield"]
    saved = ML.DATA
    ML.DATA = pin_spots.live_maps_dir()
    try:
        for map_id, name in MAPS.items():
            _, d = _build(map_id)
            model = ML.MapModel.load(name, playfield)
            for st in d["plan"]:
                if st.get("at"):
                    cell = model.frac_to_cell(*st["at"])
                    assert pin_spots.never_refused(model, st["kind"], cell), (map_id, st["id"], st["at"])
    finally:
        ML.DATA = saved


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
