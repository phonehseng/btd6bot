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
        # the second heli follows at once (two 3-2-0 helis: 2.04+ on rounds 15-20)
        assert plan[2]["kind"] == "heli" and plan[3] == {"do": "upgrade", "id": plan[2]["id"], "to": "3-2-0"}, sid


def test_cheap_helis_stand_before_the_first_apache_tier():
    """Bloody Puddles 2026-11-12: the bank waited 15 rounds for the $20,000
    tier with two helis on the board. Every heli of the build is placed and
    at 3-2-0 before the first Apache Dartship."""
    for sid, want in (("darkdungeons_apopalypse", 3), ("bloodypuddles_apopalypse", 4)):
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
