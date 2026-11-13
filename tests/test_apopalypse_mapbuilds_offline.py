"""Apopalypse map builds for Dark Dungeons and Bloody Puddles (2026-11-12).

apopalypse_apache_spikes lost both maps:
  * Dark Dungeons, round 17 (case 20261112_120344_DarkDungeons_apopalypse):
    an opener dart, ninja 1-0-1 and only then one heli were bought while the
    three walled lanes already ran; 150 lives went in 35 s. Its own check
    rated the map 0.43 from round 16.
  * Bloody Puddles, round 41 (case 20261112_112348_BloodyPuddles_apopalypse):
    plan_first kept the whole bank from round 25 to 40 for h1's $20,000
    Apache tier with two 3-2-0 helis standing; round 34's rush took 92 lives
    with $10,856 in hand.

strategies/maps/darkdungeons_apopalypse.yaml and bloodypuddles_apopalypse.yaml
put the helis first and buy more 3-2-0 helis before the first Apache tier.
Their tools/apopalypse_check.py numbers (minutes per run) are in their
headers; this test keeps the shape that the numbers came from: the heli
opening, the cheap helis before the Apache, the map scope, and the general
build kept off both maps. Their `at` spots are checked legal in plan order by
tests/test_map_hints_offline.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL           # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.account import AccountState    # noqa: E402

BUILDS = {"darkdungeons_apopalypse": "Dark Dungeons", "bloodypuddles_apopalypse": "Bloody Puddles"}
GENERAL = "apopalypse_apache_spikes"
APACHE = "4-2-0"


def _spec(sid):
    s = S.load_all()[sid]
    return PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))


def _plan(sid):
    return S.load_all()[sid]["plan"]


def test_builds_are_valid_map_scoped_and_apopalypse_only():
    strats = S.load_all()
    for sid, map_name in BUILDS.items():
        st = strats[sid]
        assert S.validate(st) == [], (sid, S.validate(st))
        assert st["modes"] == ["apopalypse"] and st.get("plan_first") is True, sid
        assert st["map"] == map_name and st["planner"]["maps"] == [map_name], sid
        # no farms: Apopalypse never pauses between rounds
        assert not any(step.get("kind") == "farm" for _, step in S._all_steps(st)), sid
        # every tower placed on a fixed spot (the live-taken or learned-legal ones in the header)
        assert all(step.get("at") for step in st["plan"] if step["do"] == "place"), sid


def test_the_first_heli_is_bought_to_3_2_0_before_anything_else():
    """Dark Dungeons 2026-11-12: dart, ninja and hero came before the heli and
    the opening was 34 s late; the heli 3-2-0 alone rates 1.07-1.20 there."""
    for sid in BUILDS:
        plan = _plan(sid)
        assert plan[0] == {"do": "place", "id": "h1", "kind": "heli", "role": "dps", "at": plan[0]["at"]}, sid
        assert plan[1] == {"do": "upgrade", "id": "h1", "to": "3-2-0"}, sid
        # then the second heli (two 3-2-0 helis: 2.04+ on rounds 15-20). On
        # both maps the hero and one 2-0-2 lane ninja come before it: see
        # test_dark_dungeons_has_a_lane_ninja_and_the_hero_before_the_second_heli
        # and test_bloody_puddles_opens_with_the_hero_and_a_right_lane_ninja
        second = next(i for i, st in enumerate(plan) if i > 1 and st["do"] == "place" and st["kind"] == "heli")
        assert plan[second + 1] == {"do": "upgrade", "id": plan[second]["id"], "to": "3-2-0"}, sid
        assert sorted(st["kind"] for st in plan[2:second] if st["do"] == "place") == ["hero", "ninja"], sid


def test_dark_dungeons_has_a_lane_ninja_and_the_hero_before_the_second_heli():
    """Dark Dungeons 2026-11-12 17:51 (case 20261112_175304): the build's
    first game was lost on round 18, a minute in. The round-15 start paid
    for the dart and h1 3-2-0, h2 stood at 0-2-0 and both helis chased the
    same bloon while the other two lanes leaked; the hero was the plan's
    last step. The general build's games of 13:13 and 15:55 held rounds
    15-34 and 17-28 with h1 3-2-0, a ninja at the foot of the middle lane
    and the hero. So, between h1's 3-2-0 and the second heli:
      * that ninja is placed where it stood in those games and grown to
        2-0-2, and the hero is placed;
      * what the plan buys up to the hero (with the executor's $200 opener
        dart) costs no more than the hero's price over the Fast Track
        start, so the hero is the first buy from round 15's own cash."""
    from btd6bot import towers as T
    plan = _plan("darkdungeons_apopalypse")
    second_heli = next(i for i, st in enumerate(plan) if st["do"] == "place" and st["kind"] == "heli" and i > 0)
    between = plan[2:second_heli]
    ninja = next(st for st in between if st.get("kind") == "ninja")
    held_spots = ((0.478, 0.930), (0.473, 0.913))       # n1 on 13:13 and on 15:55
    assert any(abs(ninja["at"][0] - x) < 0.02 and abs(ninja["at"][1] - y) < 0.02 for x, y in held_spots), ninja
    assert {"do": "upgrade", "id": ninja["id"], "to": "2-0-2"} in between
    hero = next(i for i, st in enumerate(plan) if st.get("kind") == "hero")
    assert hero < second_heli, (hero, second_heli)

    family = S.PRICE_FAMILY.get("apopalypse", "medium")
    start_cash = 6730                                   # the HUD at 17:51:27, before the first purchase
    cost = T.tower_cost("dart", family)                 # the executor's opener
    tiers = {}
    for st in plan[:hero]:
        if st["do"] == "place":
            cost += T.tower_cost(st["kind"], family)
            tiers[st["id"]] = (st["kind"], [0, 0, 0])
        else:
            kind, have = tiers[st["id"]]
            want = [int(v) for v in st["to"].split("-")]
            for path in (1, 2, 3):
                while have[path - 1] < want[path - 1]:
                    have[path - 1] += 1
                    cost += T.upgrade_cost(kind, path, have[path - 1], family)
    assert cost <= start_cash, cost
    assert cost + T.hero_cost(S.load_all()["darkdungeons_apopalypse"]["hero"], family) > start_cash


def test_bloody_puddles_opens_with_the_hero_and_a_right_lane_ninja():
    """Bloody Puddles 2026-11-12 16:49 (case 20261112_165343, this build's
    first game): with both helis first and the hero last, Obyn never stood,
    nothing stayed by the right lanes while the Pursuit helis chased the left
    ones, and the game leaked from round 17 (33 lives) to its end on round 25
    (reds, zebras, whites). The 11:17 game on the same map opened with a
    ninja at (0.6225, 0.6831), the first 3-2-0 heli and Obyn, lost 13 lives
    on rounds 15-16 and then held to round 33. That opening is now this
    build's, after h1's 3-2-0."""
    plan = _plan("bloodypuddles_apopalypse")
    assert plan[2]["kind"] == "hero", plan[2]
    assert plan[3]["kind"] == "ninja" and plan[3]["at"] == [0.623, 0.683], plan[3]
    assert plan[4] == {"do": "upgrade", "id": plan[3]["id"], "to": "2-0-2"}, plan[4]
    assert sum(1 for st in plan if st.get("kind") == "hero") == 1


def test_cheap_helis_stand_before_the_first_apache_tier():
    """Bloody Puddles 2026-11-12: the bank waited 15 rounds for the $20,000
    tier with two helis on the board, and Dark Dungeons 13:13 (case
    20261112_132035_DarkDungeons_apopalypse) lost round 35 with $10.2k waiting
    for it. Every heli of the build is placed and at 3-2-0 before the first
    Apache Dartship (four on each map)."""
    for sid, want in (("darkdungeons_apopalypse", 4), ("bloodypuddles_apopalypse", 4)):
        plan = _plan(sid)
        first_apache = next(i for i, st in enumerate(plan) if st.get("to") == APACHE)
        before = plan[:first_apache]
        helis = {st["id"] for st in before if st["do"] == "place" and st["kind"] == "heli"}
        at_320 = {st["id"] for st in before if st["do"] == "upgrade" and st.get("to") == "3-2-0"}
        assert len(helis) == want and helis <= at_320, (sid, helis, at_320)
        # nothing the model rated useless here waits in front of the Apache
        assert not any(st.get("kind") in ("spike", "alchemist", "village") for st in before), sid


def test_planner_plays_the_map_builds_not_the_general_one():
    acc = AccountState()
    general = _spec(GENERAL)
    for sid, map_name in BUILDS.items():
        cat = acc.map_category(map_name)
        assert PL._strategy_fits(_spec(sid), map_name, cat, "apopalypse"), sid
        assert not PL._strategy_fits(general, map_name, cat, "apopalypse"), map_name
    # the general build still plays the maps it won on
    assert PL._strategy_fits(general, "Firing Range", acc.map_category("Firing Range"), "apopalypse")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
            n += 1
    print(f"{n} passed")
