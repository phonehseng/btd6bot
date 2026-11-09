"""Sanctuary's moving platforms: placement where they stand, towers carried.

Sanctuary (2026-11-09): a Medium game was won with steps_given_up=145 and
a Reverse game lost round 52 with 107. Three causes, all checked here:

  1. The placement grids held the six platforms in the scene's pose, but
     they move when every round starts. The bot clicked water: 44 refused
     clicks in the Medium game, 85 in the Reverse one, and each refusal was
     learned for the map - 944 of Sanctuary's 1,016 refused land cells lay
     on platform ground, half of it, so later steps found "no legal spot
     left (22 legal cells, all tried)".
  2. Towers ride their platforms: the bot clicked the spot it had placed a
     sniper on, found nothing, forgot it and bought it again.
  3. Threat answers try a new tower of every kind (ans_camo_white_ninja,
     ..._desperado, ...) and give up each kind that finds no spot, without
     a click: 130 of the 145 "plan steps given up" were those.

What the recordings of those games showed (tools/measure_platforms.py,
rec_20261109_101000-102000 and 102800-103600): in round r every platform
stands in state seq[(r - 1) % len(seq)] (Medium and Reverse alike), before
Play of a Fast Track game in round 14's, and the two swinging platforms
(LH1, RH1) where their curve says after turning it 28 degrees and shrinking
it to 0.84. The three frames in tests/fixtures/sanctuary_*.jpg are from
those recordings (480x300).
Run: python tests/test_sanctuary_platforms_offline.py"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import mapgeom, placement          # noqa: E402
from btd6bot import strategy as S               # noqa: E402
from btd6bot.carried import CarriedTowers       # noqa: E402
from btd6bot.game import Placed                 # noqa: E402
from btd6bot.layout import LAYOUTS              # noqa: E402
from btd6bot.maplearn import MapModel           # noqa: E402

PF = LAYOUTS["16:10"]["playfield"]
FIXTURES = ROOT / "tests" / "fixtures"

# States read off the screen (Medium 2026-11-09) for a few rounds:
# platform event name -> state, per round being played.
SEEN = {
    15: {"PlatformCentreTop": 0, "PlatformCentreBottom": 1, "PlatformRH2": 3, "PlatformLH2": 2,
         "PlatformLH1": 0},
    17: {"PlatformCentreTop": 2, "PlatformCentreBottom": 1, "PlatformRH2": 1, "PlatformLH2": 2,
         "PlatformRH1": 0},
    34: {"PlatformCentreTop": 1, "PlatformCentreBottom": 0, "PlatformRH2": 2, "PlatformLH2": 3},
    36: {"PlatformCentreTop": 1, "PlatformCentreBottom": 0, "PlatformRH2": 0, "PlatformLH2": 1},
    # before Play at round 15 (the Fast Track start): as in round 14
    14: {"PlatformCentreTop": 1, "PlatformCentreBottom": 0, "PlatformRH2": 2, "PlatformLH2": 1,
         "PlatformLH1": 1},
}
# Measured shifts from the scene of the right swinging platform (world units).
RH1_MEASURED = {1: (38.1, 6.4), 2: (65.3, 21.5), 3: (74.3, 43.0), 4: (79.6, 73.2)}


def _model():
    m = MapModel("Sanctuary", PF)
    geom = mapgeom.load("Sanctuary")
    if geom is None:
        return None
    mapgeom.apply(m, geom)
    return m


def _platforms(m):
    return {p["name"]: p for p in mapgeom.grids_for(m)["platforms"]}


def test_state_by_round():
    m = _model()
    if m is None:
        return
    plats = _platforms(m)
    assert len(plats) == 8          # six that take towers, two solid arms under LH1/RH1
    assert sum(1 for p in plats.values() if p["ground"]) == 6
    for rnd, states in SEEN.items():
        for name, state in states.items():
            got = mapgeom.platform_state(plats[name]["mover"], rnd)
            assert got == state, (rnd, name, got, state)
    # the layout repeats every 24 rounds
    for p in plats.values():
        assert all(mapgeom.platform_state(p["mover"], r) == mapgeom.platform_state(p["mover"], r + 24)
                   for r in range(1, 30))


def test_swinging_platforms_where_measured():
    m = _model()
    if m is None:
        return
    plats = _platforms(m)
    right = plats["PlatformRH1"]["mover"]["state_poses"]
    left = plats["PlatformLH1"]["mover"]["state_poses"]
    for state, (dx, dz) in RH1_MEASURED.items():
        assert abs(right[state][0] - dx) < 5 and abs(right[state][1] - dz) < 5, (state, right[state])
        # the left arm is its mirror image
        assert abs(left[state][0] + dx) < 5 and abs(left[state][1] - dz) < 5, (state, left[state])


def test_grids_follow_the_platforms():
    """With pose_round the legal cells lie on the platforms where they stand
    in that round; the scene-pose grids (no round) put most of them on
    water in most rounds."""
    m = _model()
    if m is None:
        return
    scene = placement.valid_spots(m, "sniper")
    for rnd in (14, 15, 16, 29):
        posed = placement.valid_spots(m, "sniper", pose_round=rnd)
        assert posed.sum() > 500, (rnd, posed.sum())
        ys, xs = np.nonzero(posed)
        on = sum(1 for x, y in zip(xs[::7], ys[::7])
                 if mapgeom.platform_under(m, *m.cell_to_frac(x, y), rnd)[0] is not None)
        assert on == len(xs[::7]), (rnd, on, len(xs[::7]))
    # the scene's layout is no round's layout: round 29 shares under half of it
    assert (scene & placement.valid_spots(m, "sniper", pose_round=29)).sum() < 0.5 * scene.sum()


def test_screen_shows_the_layout():
    """The stone of the platforms tells the rounds apart (frames of the
    2026-11-09 games), and a Fast Track game before Play stands as in the
    round before the HUD's."""
    m = _model()
    if m is None:
        return
    for name, rnd in (("sanctuary_r29.jpg", 29), ("sanctuary_reverse_r40.jpg", 40),
                      ("sanctuary_r15_before_play.jpg", 14)):
        frame = cv2.imread(str(FIXTURES / name))
        assert mapgeom.platform_round_on_screen(m, frame, [rnd - 1, rnd, rnd + 1]) == rnd, name
    # the HUD said 15 before Play: the screen corrects the guess
    frame = cv2.imread(str(FIXTURES / "sanctuary_r15_before_play.jpg"))
    assert mapgeom.platform_round_on_screen(m, frame, [15, 14, 16]) == 14
    # no platforms, no reading
    assert mapgeom.platform_round_on_screen(MapModel("Monkey Meadow", PF), frame, [1, 2]) is None


def test_spots_and_towers_ride_along():
    m = _model()
    if m is None:
        return
    # the build's spot for s1 (top platform, written in the scene's pose)
    at = (0.334, 0.198)
    plat, _ = mapgeom.platform_under(m, *at, None)
    assert plat is not None and plat["name"] == "PlatformCentreTop"
    there = mapgeom.carry_spot(m, *at, None, 17)
    assert mapgeom.platform_under(m, *there, 17)[0] is plat
    back = mapgeom.carry_spot(m, *there, 17, None)
    assert abs(back[0] - at[0]) < 1e-3 and abs(back[1] - at[1]) < 1e-3
    # off the platforms nothing moves
    assert mapgeom.carry_spot(m, 0.45, 0.5, None, 17) == (0.45, 0.5)

    c = CarriedTowers.for_map("Sanctuary", PF)
    assert c is not None and c.platforms is not None
    spot = mapgeom.carry_spot(m, *at, None, 14)
    s1 = Placed("s1", "sniper", *spot)
    towers = {"s1": s1}
    assert c.follow_platforms(14, towers) == []          # placed before Play (round 14's layout)
    assert c.follow_platforms(15, towers) == ["s1"]      # Play: the platforms move
    assert mapgeom.platform_under(m, s1.x, s1.y, 15)[0] is plat
    expected = mapgeom.carry_spot(m, *at, None, 15)
    assert abs(s1.x - expected[0]) < 1e-3 and abs(s1.y - expected[1]) < 1e-3
    for r in range(16, 40):
        c.follow_platforms(r, towers)
    # a whole cycle later it is back where it started
    assert abs(s1.x - expected[0]) < 1e-3 and abs(s1.y - expected[1]) < 1e-3
    # a tower placed now is matched to the layout it was placed in
    s2 = Placed("s2", "sniper", *mapgeom.carry_spot(m, *at, None, 39))
    towers["s2"] = s2
    c.follow_platforms(39, towers)
    c.follow_platforms(40, towers)
    expected = mapgeom.carry_spot(m, *at, None, 40)
    assert abs(s2.x - expected[0]) < 1e-3 and abs(s2.y - expected[1]) < 1e-3


def test_refusals_on_platforms_are_not_kept():
    m = _model()
    if m is None:
        return
    ground = mapgeom.platform_ground(m)
    assert ground is not None and ground.sum() > 1000
    ys, xs = np.nonzero(ground)
    m.refuse("land", int(xs[0]), int(ys[0]))
    m.refused["land"][0, 0] = True       # off the platforms: kept
    assert mapgeom.forget_platform_refusals(m, mapgeom.load("Sanctuary")) > 0
    assert not (m.refused["land"] & ground).any() and m.refused["land"][0, 0]

    # the executor does not learn a refusal there
    ex = S.Executor.__new__(S.Executor)
    ex.m = m
    ex.learned_blocks = 0
    ex.g = type("G", (), {"hero": None})()
    before = int(m.refused["land"].sum())
    ex._learn_blocked("sniper", int(xs[len(xs) // 2]), int(ys[len(ys) // 2]))
    assert int(m.refused["land"].sum()) == before and ex.learned_blocks == 0


def test_pose_round_from_play_state():
    """Before Play and between rounds the platforms stand as in the round
    before the HUD's; while a round runs, as in the HUD's."""
    m = _model()
    if m is None:
        return
    ex = S.Executor.__new__(S.Executor)
    ex.m = m
    ex.g = type("G", (), {"towers": {}})()    # no screen offline
    ex.failed_spots, ex.blocked = set(), np.zeros(m.heat.shape, bool)
    ex.now_round = 15
    ex.play_running = False
    assert ex._pose_round() == 14
    ex.play_running = True
    assert ex._pose_round() == 15
    # spots refused on platform ground in the old layout are tried again
    ground = mapgeom.platform_ground(m)
    ys, xs = np.nonzero(ground)
    ex.failed_spots = {("sniper", int(xs[0]), int(ys[0])), ("sniper", 0, 0)}
    ex.blocked[ys[0], xs[0]] = True
    ex.now_round = 16
    assert ex._pose_round() == 16
    assert ex.failed_spots == {("sniper", 0, 0)} and not ex.blocked[ys[0], xs[0]]
    # other maps: no pose round
    ex2 = S.Executor.__new__(S.Executor)
    ex2.m, ex2.now_round, ex2.play_running = MapModel("Monkey Meadow", PF), 15, False
    assert ex2._pose_round() is None


def test_threat_answers_are_not_plan_steps():
    ex = S.Executor.__new__(S.Executor)
    ex.plan = [{"do": "place", "id": "s1", "kind": "sniper"}, {"do": "place", "id": "w1", "kind": "wizard"},
               {"do": "upgrade", "id": "s1", "to": "0-1-0"}]
    ex.dead_steps = {S.Executor._step_key(s) for s in (
        {"do": "place", "id": "w1", "kind": "wizard", "role": "dps", "at": [0.371, 0.888]},
        {"do": "place", "id": "ans_camo_white_ninja", "kind": "ninja", "role": "dps", "segment": [0.0, 0.7]},
        {"do": "place", "id": "ans_camo_white_dart", "kind": "dart", "role": "dps", "segment": [0.0, 0.7]},
        {"do": "place", "kind": "sniper", "role": "dps", "segment": [0.2, 1.0]})}
    assert ex.given_up_counts() == {"plan": 1, "other": 3}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK")
