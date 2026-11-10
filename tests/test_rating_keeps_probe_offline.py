"""Rating a placement does not spend the kind's probe of a blocked cell.

Infernal Impoppable (2026-11-10, chimps_ninja_sun, lost round 78; journal
logs/journal/20261110_160431_Infernal_impoppable.jsonl): from round 63 every
reinforce look logged "nothing $N buys helps round R (...; 1 purchases
tried)" while the bank grew to $11-21k. The board had 14 towers and every one
of them stood at its last crosspath short of tier 5 (the cheapest tier 5, a
Mermonkey 5-2-0, cost $27,600), so no upgrade was affordable; and the map was
full - two free legal cells were left for any land tower. What reinforce
could still offer was a placement of each standing damage kind: the ninja's
had been given up at round 37, the ace had no cell at all, and the sniper
and the sub had nothing but their probe (Executor._probe_spot: one cell the
map file marks blocked, tried once per kind and game because the game may
accept it). The first look that rated them spent those probes without a
click, so every later look offered only "another mermonkey" at the last
free cell. The same day new_kind_options spent 13 kinds' probes in one look
(16:13:05), and 40 of the day's 81 probes were offered with no placement
attempt of the kind after them.

Now reinforce rates placements with Executor.peek_spots, which leaves the
probe for the pick-up that clicks it.

Offline on Infernal's game geometry (data/map_geometry), with the round-72
board of that game at its live spots (no learned refusals, so the test does
not depend on data/maps/infernal.npz).
Run: python tests/test_rating_keeps_probe_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import simulate_threats as SIM               # noqa: E402
from btd6bot import mapgeom as G             # noqa: E402
from btd6bot import reinforce as R           # noqa: E402
from btd6bot import strategy as S            # noqa: E402
from btd6bot.layout import LAYOUTS           # noqa: E402
from btd6bot.maplearn import MapModel        # noqa: E402

MAP = "Infernal"
# the round-72 board of the live game: (tid, kind, crosspath, x, y)
BOARD = [
    ("hero", "hero", "0-0-0", 0.2485, 0.2487),
    ("n2", "ninja", "2-0-4", 0.4195, 0.6576),
    ("ninja1", "ninja", "4-2-0", 0.4355, 0.3594),
    ("ninja2", "ninja", "4-2-0", 0.6225, 0.7513),
    ("ninja3", "ninja", "4-0-2", 0.4088, 0.3254),
    ("ninja4", "ninja", "4-0-2", 0.4409, 0.2998),
    ("ans_blimps_ace", "ace", "4-2-0", 0.0401, 0.5298),
    ("ace1", "ace", "2-4-0", 0.8203, 0.5128),
    ("sn1", "sniper", "4-0-2", 0.0347, 0.4361),
    ("sniper2", "sniper", "4-2-0", 0.8256, 0.5980),
    ("sniper3", "sniper", "4-2-0", 0.0294, 0.6150),
    ("mermonkey1", "mermonkey", "4-2-0", 0.6172, 0.2402),
    ("mermonkey2", "mermonkey", "4-2-0", 0.2592, 0.7513),
    ("sub1", "sub", "4-0-2", 0.2164, 0.7683),
]
CASH = 14_992            # the bank at round 72's start


def _executor():
    m = G.apply(MapModel(MAP, LAYOUTS["16:10"]["playfield"]), G.load(MAP))
    g = SIM.CashGame("impoppable", "obyn", m)
    g.cash = CASH
    ex = S.Executor(g, m, S.load_all()["chimps_ninja_sun"], "impoppable", SIM.full_account())
    for tid, kind, cross, x, y in BOARD:
        g.towers[tid] = SIM.Placed(tid, kind, x, y, tiers=[int(c) for c in cross.split("-")])
    ex.purchased = len(g.towers)
    return ex, g


def _probe_kinds(ex):
    """The placements on offer whose rated spot is a probe (score 2e9)."""
    kinds = []
    for kind in ("ninja", "sub", "mermonkey", "sniper"):
        spots = ex.peek_spots(kind, {"do": "place", "kind": kind, "role": "dps", "segment": [0.2, 1.0]})
        if spots and spots[0][2] >= 1e9:
            kinds.append(kind)
    return kinds


def test_the_case_has_no_affordable_upgrade():
    """The board of the case: every upgrade left is a tier 5 the bank cannot pay."""
    ex, _ = _executor()
    ups = list(ex.upgrade_choices(past_plan=True))
    assert ups and all(max(t) == 5 for _, t, _ in ups), ups
    assert min(c for _, _, c in ups) > CASH


def test_rating_placements_keeps_the_probes():
    ex, _ = _executor()
    probing = _probe_kinds(ex)
    assert probing, "the case's board has kinds whose best spot is a probe"
    first = sorted(o.what for o in R.options(ex, CASH))
    second = sorted(o.what for o in R.options(ex, CASH))
    assert first == second, (first, second)
    for kind in probing:
        assert f"another {kind}" in first, (kind, first)
    assert not getattr(ex, "_probed", set()), "a look that only rates spends no probe"
    # the pick-up that clicks still gets the probe first, and spends it
    step = {"do": "place", "kind": probing[0], "role": "dps", "segment": [0.2, 1.0]}
    spots = ex.pick_spots(probing[0], step, n=S.Executor.SPOTS_PER_HOLD)
    assert spots and spots[0][2] >= 1e9, spots
    assert any(k == probing[0] for k, _, _ in ex._probed)
    again = ex.pick_spots(probing[0], step, n=S.Executor.SPOTS_PER_HOLD)
    assert not again or again[0][2] < 1e9, "one probe per kind and game, as before"


def test_new_kind_ratings_keep_the_probes():
    """new_kind_options rates a placement of every kind not standing (16:13:05
    in the case: 13 probes spent in one look)."""
    ex, _ = _executor()

    class Flat:
        def margin(self, towers, rnd):
            return 0.5

    R.new_kind_options(ex, Flat(), CASH, 78)
    assert not getattr(ex, "_probed", set()), ex._probed


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
