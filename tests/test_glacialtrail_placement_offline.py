"""Glacial Trail placement: a big tower's refusal no longer takes the ground
from every tower, and blocked cells inside walls are not probed.

Glacial Trail Medium (2026-11-09 19:12-19:19, primary_core, lost round 40,
main logs/bot.log): the map has two patches of ground beside the track -
Floor2 by the first loop and Floor4 by the second (data/map_geometry/
glacialtrail.json; the snowfield between them is the "Wall" area and is
refused). Quincy was refused twice on Floor2 (cells (28,55) and (24,56)). The
map learned that for Quincy alone ("land@quincy", placement.refusal_layer),
but Executor._note_refused also blocked the cells round both spots for this
game for every tower, which took all of Floor2. After b1 stood on Floor4 the
tack, dart, glue, bomb and boomerang steps and the camo answers found "no spot
(... none reaches enough track ...)": 7 plan steps and 12 answers were given
up and the game was lost at round 40 with a boomerang and a sniper standing.
Each step was offered one spot, a probe of a cell the map file marks blocked;
all ten probes were refused, most of them inside the icicle and wall areas
that block sight round the loops.

Checked on the map's game geometry (no learned refusals, so the test does not
depend on data/maps/glacialtrail.npz):
  * after Quincy's two refusals on Floor2 a dart and a ninja are still offered
    Floor2; a dart's own refusal there still keeps the cell from the ninja;
  * no probe is offered inside an unplaceable sight blocker on Glacial Trail,
    and every probe the game ever accepted on Water Park lies outside one.
Run: python tests/test_glacialtrail_placement_offline.py"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import mapgeom as G             # noqa: E402
from btd6bot import strategy as S            # noqa: E402
from btd6bot.layout import LAYOUTS           # noqa: E402
from btd6bot.maplearn import MapModel        # noqa: E402

MAP = "Glacial Trail"
HERO_SPOT = (0.120, 0.828)          # Quincy on the bottom-left ice floe (Ice1), as live
B1_SPOT = (0.713, 0.666)            # b1 on Floor4, as live
QUINCY_REFUSED = ((28, 55), (24, 56))   # 19:12:27-28, learned as land@quincy
FLOOR2 = (26, 55)                   # centre of Floor2's legal cells for a small tower


def _model():
    """A fresh model from the game geometry: the executor's refusals are
    learned into it, so it must not be simulate_threats' shared one."""
    return G.apply(MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))


def _executor():
    m = _model()
    g = SIM.CashGame("medium", "quincy", m)
    g.cash = 10_000
    ex = S.Executor(g, m, S.load_all()["primary_core"], "medium", SIM.full_account())
    g.towers["hero"] = SIM.Placed("hero", "hero", *HERO_SPOT)
    g.towers["b1"] = SIM.Placed("b1", "boomerang", *B1_SPOT)
    return ex, g, m


def _refuse(ex, g, kind, cells):
    """What Executor.place does after Game.place came back with these cells refused."""
    spots = [(cx, cy, 1.0) for cx, cy in cells]
    fracs = [ex.m.cell_to_frac(cx, cy) for cx, cy in cells]
    g.refused_spots, g.click_refusals = list(fracs), len(fracs)
    ex._note_refused(kind, ("test", kind), spots, fracs, placed=True)


def _near_floor2(spots):
    return [s for s in spots if abs(s[0] - FLOOR2[0]) <= 4 and abs(s[1] - FLOOR2[1]) <= 3]


def test_a_heros_refusal_leaves_floor2_to_small_towers():
    ex, g, m = _executor()
    _refuse(ex, g, "hero", QUINCY_REFUSED)
    assert m.refused_mask("land@quincy")[55, 28], "the refusal is learned for Quincy"
    assert not m.refused_mask("land")[55, 28], "and not for every tower"
    for kind in ("dart", "ninja", "tack"):
        step = {"do": "place", "id": "x", "kind": kind, "role": "dps", "segment": [0.0, 0.6]}
        spots = ex.pick_spots(kind, step, n=S.Executor.SPOTS_PER_HOLD)
        assert _near_floor2(spots), (kind, spots)
    # the hero itself is kept off the cells it was refused at this game
    hero = ex._blocked_for("hero")
    assert all(hero[cy, cx] for cx, cy in QUINCY_REFUSED)


def test_a_small_towers_refusal_still_blocks_every_tower():
    ex, g, m = _executor()
    dart = {"do": "place", "id": "d", "kind": "dart", "role": "dps", "segment": [0.0, 0.6]}
    cells = [(cx, cy) for cx, cy, _ in _near_floor2(ex.pick_spots("dart", dart, n=S.Executor.SPOTS_PER_HOLD))]
    assert cells
    _refuse(ex, g, "dart", cells)
    for kind in ("dart", "ninja"):
        blocked = ex._blocked_for(kind)
        assert all(blocked[cy, cx] for cx, cy in cells), kind


def test_no_probe_inside_walls_and_icicles():
    ex, g, m = _executor()
    solid = G.grids_for(m)["solid_blockers"]
    assert solid.any()
    for kind in ("tack", "dart", "glue", "bomb", "boomerang", "ninja", "desperado", "wizard"):
        probe = ex._probe_spot(kind, ex._legal_cells(kind))
        if probe is not None:
            cx, cy, _ = probe
            assert not solid[cy, cx], (kind, probe)


def test_accepted_probes_lie_outside_solid_blockers():
    """Water Park's accepted probes (data/maps/waterpark.npz, tracked): the
    gate would not have stopped any of them."""
    pf = LAYOUTS["16:10"]["playfield"]
    m = MapModel.load("Water Park", pf)
    accepted = [v for k, v in m.accepted.items()]
    if not accepted or not any(a.any() for a in accepted):
        return      # nothing learned in this checkout
    m = G.apply(m, G.load("Water Park"))
    solid = G.grids_for(m)["solid_blockers"]
    for a in accepted:
        assert not (a & solid).any()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
