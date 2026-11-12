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

Also 2026-11-12: Covered Garden (loss 20261112_014133, round 63) had its late
answers' towers under the cycling panes and its supports without room by
their village; it now has its own plan on the pane-free ground. Sunset Gulch
and Mesa got map builds after their general-build losses (ground used up by
reinforce buys; no MOAB answer by round 40). Spillway got one after
chimps_ninja_sun's round 98 (loss 20261112_041202: ten off-plan towers, the
exit spike factory given up, blimp check 0.2-0.8x from round 91).

Late game (2026-11-12, damage model phase 2): Sunken Columns, Sunset Gulch,
Firing Range, Quad, Bloonarius Prime, Mesa, Covered Garden and Peninsula
keep their plans up to round 30-35 and then take tools/optimize_builds.py's
greedy purchases, saving for one tier-5 carry (Super Mines, Flying Fortress
or Wizard Lord Phoenix); the ace builds have Etienne for his map-wide camo.

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
        "midnightmansion": "Midnight Mansion", "sunsetgulch": "Sunset Gulch", "mesa": "Mesa",
        "spillway": "Spillway"}


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


def test_covered_garden_stands_off_the_panes():
    """Every pinned tower of the Covered Garden build, its late-game carry
    (the Wizard Lord Phoenix) among them, is on ground no cycling pane
    covers."""
    from btd6bot import mapgeom as G
    _, d = _build("coveredgarden")
    pinner = pin_spots.Pinner("Covered Garden", "impoppable")
    steps = {st["id"]: st for st in d["plan"] + d.get("fill", []) if st["do"] == "place" and st.get("at")}
    for tid, st in steps.items():
        assert G.pane_at(pinner.model, *st["at"], None)[0] is None, (tid, st["at"])
    assert any(st["kind"] == "wizard" and "carry" in tid for tid, st in steps.items()), sorted(steps)


def test_the_moab_answer_comes_before_the_alchemist():
    """Mesa lost at round 40 with the blimp check at 0.4-0.9: n2's Sticky
    Bomb (2-0-4) is bought before a1 in every ninja-led Impoppable plan."""
    for map_id in ("mesa", "sunsetgulch", "coveredgarden", "quad", "bloonariusprime", "firingrange", "midnightmansion",
                   "spillway"):
        _, d = _build(map_id)
        order = [(st["do"], st.get("id"), str(st.get("to"))) for st in d["plan"]]
        # Covered Garden's late-game plan (2026-11-12) buys no alchemist at all
        alchemist = order.index(("place", "a1", "None")) if ("place", "a1", "None") in order else len(order)
        assert order.index(("upgrade", "n2", "2-0-4")) < alchemist, map_id


def _bought_before(d, rnd):
    """The plan steps the executor has bought before round ``rnd``: in
    order, each once the cash allows, on Impoppable's income with the main
    account's Double Cash (no Fast Track there), as the late game was
    rated."""
    import optimize_builds as O
    from btd6bot import towers as T
    econ = O.economy("impoppable", {"double_cash": True})
    tiers, cash, out, steps = {}, econ.start_cash, [], list(d["plan"])
    for r in range(econ.start_round, rnd):
        while steps:
            st = steps[0]
            if st["do"] == "place":
                cost = (T.hero_cost(d["hero"], econ.family) if st["kind"] == "hero"
                        else T.tower_cost(st["kind"], econ.family))
            elif st["do"] == "upgrade":
                kind, have = tiers[st["id"]]
                cost = O.upgrade_cost(kind, have, O.parse_cross(st["to"]), econ.family)
            else:
                cost = 0.0
            if cost > cash:
                break
            cash -= cost
            if st["do"] == "place":
                tiers[st["id"]] = (st["kind"], (0, 0, 0))
            elif st["do"] == "upgrade":
                tiers[st["id"]] = (tiers[st["id"]][0], O.parse_cross(st["to"]))
            out.append(steps.pop(0))
        cash += econ.income(r)
    return out


def test_sunken_columns_answers_round_59_camo_lead():
    """Round 59's camo lead bloons (the threat simulation found round 59
    uncovered on 2026-11-12): the towers the plan has bought before round
    59 answer them by themselves, without the build's answers."""
    from btd6bot import strategy as S
    _, d = _build("sunkencolumns")
    early = dict(d, plan=_bought_before(d, 59), answers={})
    _, missing = S.coverage(early, "impoppable")
    assert "camo_lead" not in missing, missing


def test_late_game_carries_answer_the_last_blimps():
    """The late-game rework (2026-11-12, damage model phase 2): each map's
    plan carries one tier-5 tower, saved for by a stated round, and its
    ZOMG and BAD answers name a tower the plan buys anyway, so the executor
    is never sent after a second one."""
    from btd6bot import strategy as S
    for map_id in ("sunkencolumns", "sunsetgulch", "firingrange", "quad", "bloonariusprime", "mesa",
                   "coveredgarden"):
        _, d = _build(map_id)
        ids = {st["id"] for st in d["plan"] if st.get("id")}
        carry = [st for st in d["plan"] if st["do"] == "upgrade" and "carry" in st["id"] and "5" in st["to"]]
        assert carry, map_id
        assert S.coverage(d, "impoppable")[0], (map_id, S.coverage(d, "impoppable"))
        for threat in ("zomg", "bad"):
            if map_id == "coveredgarden" and threat == "bad":
                # its carry (a Wizard Lord Phoenix) is no BAD answer and no
                # bomb fits the pane-free ground: a Cripple MOAB sniper is
                assert [st["kind"] for st in d["answers"][threat] if st["do"] == "place"] == ["sniper"]
                continue
            assert all(st["id"] in ids for st in d["answers"][threat]), (map_id, threat)


def test_a_tower_is_pinned_on_its_part_of_the_route():
    """Mesa (2026-11-12): n1, `segment: [0.0, 0.5]`, was pinned by its cover
    of the whole route at the far end, and the one-life game was lost at
    round 9. Its pin covers at least as much of the first half as the
    whole-route pin does, and is among the best for that half (with the
    refusals learned by 2026-11-12 13:00 the two pins are the same cell)."""
    pinner = pin_spots.Pinner("Mesa", "impoppable")
    first = pinner.pin("a", "ninja", segment=(0.0, 0.5))
    pinner.placed.pop()
    anywhere = pinner.pin("b", "ninja")
    pinner.placed.pop()
    cover = lambda at: pinner.segment_cover("ninja", pinner.model.frac_to_cell(*at), (0.0, 0.5))
    assert cover(first) >= cover(anywhere), (first, anywhere)
    ranked = pinner.candidates("ninja", pinner.legal("ninja"), segment=(0.0, 0.5))
    best = max(pinner.segment_cover("ninja", c, (0.0, 0.5)) for c in ranked)
    assert cover(first) >= pin_spots.PROVEN_SCORE_SHARE * best, (cover(first), best)
    _, d = _build("mesa")
    n1 = next(st for st in d["plan"] if st.get("id") == "n1")
    assert n1["at"] == first


def test_a_buffer_takes_the_cell_with_room_round_it():
    """Pinner.pin gives a village the cell with the most legal room inside
    its range among the candidates it weighs."""
    pinner = pin_spots.Pinner("Monkey Meadow", "impoppable")
    cands = pinner.candidates("village", pinner.legal("village"))
    weighed = cands[::max(1, len(cands) // pin_spots.BUFFER_TRIES)]
    most = max(pinner.room("village", c) for c in weighed)
    assert pinner.pin("v1", "village") is not None
    pinner.placed.pop()     # its room as the pin weighed it, without itself
    assert pinner.room("village", pinner.cells["v1"]) == most


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
