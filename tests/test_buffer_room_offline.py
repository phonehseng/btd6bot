"""A tower that a later village/alchemist step stands "near" is placed where
that buffer has legal ground in range (Executor._no_buffer_room).

Mesa ABR (2026-11-09, loss case 20261109_120238_Mesa_abr): hard_sniper_elite's
s1 stood on the central mesa top, the nearest legal village cell was out of
the village's range, v1 "near s1" was given up, the Radar village went to the
ninjas instead, and round 27's 250 camo bloons walked past snipers that could
not see them.
Run: python tests/test_buffer_room_offline.py"""
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L               # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot.maplearn import MapModel         # noqa: E402

logging.getLogger("strategy").setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parents[1]


def sniper_build():
    return yaml.safe_load((ROOT / "strategies" / "hard_sniper_elite.yaml").read_text())


def test_mesa_sniper_leaves_room_for_its_village():
    m = MapModel.load("Mesa", L.get(1920, 1200)["playfield"])
    if not m.known():
        return                      # map not learned on this machine
    plan = sniper_build()
    ex = S.Executor(F.FakeGame("etienne"), m, plan, "abr", F.full_account())
    s1_step, v1_step = plan["plan"][0], plan["plan"][2]
    assert v1_step["kind"] == "village" and v1_step["near"] == ["s1"]
    spots = ex.pick_spots("sniper", s1_step, n=3)
    assert spots
    # the spot of the lost game is not offered any more
    assert all((x - 108) ** 2 + (y - 58) ** 2 > 9 for x, y, _ in spots), spots
    fx, fy = m.cell_to_frac(spots[0][0], spots[0][1])
    s1 = F.Placed("s1", "sniper", fx, fy)
    s1.tiers = [2, 0, 2]
    ex.g.towers = {"s1": s1}
    village = ex._spots_widening("village", v1_step)   # what the executor asks
    assert village, "v1 still finds no spot near s1"
    vx, vy, _ = village[0]
    sx, sy = m.frac_to_cell(fx, fy)
    assert (vx - sx) ** 2 + (vy - sy) ** 2 <= ex._range_cells("village") ** 2


def test_no_buffer_step_no_block():
    m = MapModel.load("Mesa", L.get(1920, 1200)["playfield"])
    if not m.known():
        return
    plan = sniper_build()
    ex = S.Executor(F.FakeGame("etienne"), m, plan, "abr", F.full_account())
    valid = ex._legal_cells("sniper")
    # s2 is placed near v1; no buffer stands near s2
    assert ex._no_buffer_room(plan["plan"][5], valid) is None
    # a step with a researched spot keeps it
    assert ex._no_buffer_room(dict(plan["plan"][0], at=[0.5, 0.5]), valid) is None
    # once the village stands, nothing waits for room
    v1 = F.Placed("v1", "village", 0.3, 0.7)
    ex.g.towers = {"v1": v1}
    assert ex._no_buffer_room(plan["plan"][0], valid) is None


def test_ouch_alchemist_buffs_the_ninja_it_was_meant_for():
    """#Ouch Apopalypse (2026-11-09 12:17): a1 "near n1" found no spot in its
    near radius and went where it buffed the most towers (n2 and the opener
    on the right, at 0.644,0.462); the left lane, n1's, leaked 119 lives in
    a second. A cell that buffs a named tower now comes first."""
    m = MapModel.load("#Ouch", L.get(1920, 1200)["playfield"])
    if not m.known():
        return
    plan = yaml.safe_load((ROOT / "strategies" / "apopalypse_ninja_sniper.yaml").read_text())
    ex = S.Executor(F.FakeGame("obyn"), m, plan, "apopalypse", F.full_account())
    towers = {"opener": F.Placed("opener", "dart", 0.590, 0.291),
              "n1": F.Placed("n1", "ninja", 0.350, 0.726),     # the live game's spots
              "n2": F.Placed("n2", "ninja", 0.521, 0.419)}
    ex.g.towers = towers
    a1_step = plan["plan"][4]
    assert a1_step["id"] == "a1" and a1_step["near"] == ["n1"]
    spots = ex._spots_widening("alchemist", a1_step)
    assert spots
    x, y, _ = spots[0]
    assert ex._buffed("alchemist", x, y, [towers["n1"]]) == 1, m.cell_to_frac(x, y)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
