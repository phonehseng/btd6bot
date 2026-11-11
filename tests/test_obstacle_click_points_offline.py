"""An obstacle whose first click opens no removal box is clicked at its other
points before it is left alone.

Mushroom Grotto Impoppable (2026-11-11 10:48-11:15, chimps_ninja_sun; loss
case 20261111_111519_MushroomGrotto_impoppable): nearly all of the map's
ground lies under its main mushroom ($400, 845 legal ninja cells). At round
48 the bot clicked the middle of the mushroom's outline twice - a small patch
at the foot of the stalk (recording rec_20261111_110000.mkv, 13-16 s: the
cursor rests there and no box opens) - and then left it alone for the game.
The village, both Super Monkeys, every ace, the bomb and the exit spikes had
been given up with "0 legal cells"; the game was played with darts and
ninjas and lost at round 93. The four small mushrooms, clicked on their
middle the same way, opened their boxes at once.

The map file puts the main mushroom's scene object 19 units further up, on
the cap. mapgeom.removables now lists that point and four more inside the
outline after the middle ("click_fracs"), and Executor._buy_removal moves to
the next one after each failed attempt.
Run: python tests/test_obstacle_click_points_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import layout as L, mapgeom  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402
from btd6bot.strategy import Executor  # noqa: E402

MAP, MAIN = "Mushroom Grotto", "RemoveableAreaTriggerMushroom_Main"
PF = L.get(1920, 1200)["playfield"]


def _removables():
    """{name: record} of the map's obstacles, None without its geometry."""
    if mapgeom.load(MAP) is None:
        print(f"skip: no {MAP} geometry")
        return None
    return {r["name"]: r for r in mapgeom.removables(MAP, PF)}


def _executor(opens_box):
    """An Executor on a fresh model of the map, no towers standing, whose
    game opens a removal box only where opens_box(fx, fy) says so. Every
    click is recorded in ex.clicked."""
    ex = Executor.__new__(Executor)
    ex.m = mapgeom.apply(MapModel(MAP, PF), mapgeom.load(MAP))
    ex.no_removals = False
    ex.land_only = True
    ex.removed, ex.removal_fails = [], {}
    ex.clicked = []

    def remove_obstacle(fx, fy, cost, name=""):
        ex.clicked.append((name, fx, fy))
        return opens_box(fx, fy)

    ex.g = SimpleNamespace(towers={}, hero=None, price=lambda kind: 430, remove_obstacle=remove_obstacle)
    return ex


def test_the_middle_stays_the_first_click():
    """Every obstacle is still clicked on the middle of its outline first,
    and all its points lie on the play field."""
    rem = _removables()
    if rem is None:
        return
    x0, y0, x1, y1 = PF
    for r in rem.values():
        assert r["click_fracs"][0] == r["frac"], r["name"]
        assert len(set(map(tuple, r["click_fracs"]))) == len(r["click_fracs"]), r["name"]
        assert all(x0 < fx < x1 and y0 < fy < y1 for fx, fy in r["click_fracs"]), (r["name"], r["click_fracs"])


def test_the_main_mushroom_is_clicked_on_its_cap_next():
    """The main mushroom's second point is the map file's own position of
    the mushroom, well above the foot of the stalk on screen; the small
    mushrooms' own positions are offsets inside their parent object (far
    from their outline) and are not used."""
    rem = _removables()
    if rem is None:
        return
    main = rem[MAIN]
    (fx0, fy0), (fx1, fy1) = main["click_fracs"][:2]
    assert fy1 < fy0 - 0.05 and abs(fx1 - fx0) < 0.02, main["click_fracs"]
    assert len(main["click_fracs"]) == 6          # middle, scene object, four inside the outline
    for name, r in rem.items():
        if name != MAIN:
            assert len(r["click_fracs"]) == 5, (name, r["click_fracs"])
    print(f"main mushroom: middle {main['frac']}, then {main['click_fracs'][1]}")


def test_a_failed_click_moves_to_the_next_point():
    """With a game that opens the main mushroom's box only on its cap, the
    second attempt buys it."""
    rem = _removables()
    if rem is None:
        return
    main = rem[MAIN]
    cap = tuple(main["click_fracs"][1])
    ex = _executor(lambda fx, fy: (fx, fy) == cap)
    assert not ex.clear_obstacle(5000, "ninja")          # the middle: no box
    assert ex.clear_obstacle(5000, "ninja")              # the cap
    assert [c[0] for c in ex.clicked] == [MAIN, MAIN], ex.clicked
    assert ex.clicked[0][1:] == tuple(main["frac"]) and ex.clicked[1][1:] == cap
    assert ex.removed == [main["id"]]


def test_an_obstacle_that_never_opens_is_left_alone_in_the_end():
    """Each point is tried once; then the obstacle is left alone and the
    next best one is bought instead."""
    rem = _removables()
    if rem is None:
        return
    main = rem[MAIN]
    main_points = {tuple(p) for p in main["click_fracs"]}
    ex = _executor(lambda fx, fy: (fx, fy) not in main_points)
    for _ in range(len(main_points)):
        assert not ex.clear_obstacle(5000, "ninja")
    assert {c[1:] for c in ex.clicked} == main_points, ex.clicked
    assert ex.clear_obstacle(5000, "ninja")              # a small mushroom now
    assert ex.clicked[-1][0] != MAIN and main["id"] not in ex.removed


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
