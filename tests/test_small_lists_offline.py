"""The small fixed tower lists, widened on merit (docs/tower_exclusions_audit.md item 12).

  * PANIC_KINDS: the hand eight first, then every other tower that pops on
    its own from 0-0-0 and stands on land, cheapest first - never a glue,
    village, farm or a tower that must be aimed;
  * Executor.CHEAP_OPENERS: the hand six first, then the other such towers
    no dearer than the dearest of them (Desperado, Mermonkey, Skywarden ...);
  * CAMO_BACKUPS: the hand six first, then each other tower's cheapest
    crosspath that strong_camo counts;
  * coverage's answer kinds include water towers for a strategy pinned to
    maps where they reach the track.

All offline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402

NEVER = {"glue", "village", "farm", "mortar"}


def test_panic_kinds_keep_the_hand_order_and_add_every_popper():
    hand = ["tack", "dart", "sniper", "ninja", "wizard", "boomerang", "engineer", "spike"]
    assert S.PANIC_KINDS[:len(hand)] == hand
    rest = S.PANIC_KINDS[len(hand):]
    assert {"desperado", "mermonkey", "skywarden"} <= set(rest)
    assert not set(S.PANIC_KINDS) & NEVER and "dartling" not in S.PANIC_KINDS
    assert all(T.TOWERS[k].get("placement") != "water" for k in rest)
    assert [T.tower_cost(k) for k in rest] == sorted(T.tower_cost(k) for k in rest)


def test_cheap_openers_add_the_cheap_poppers():
    ops = S.Executor.CHEAP_OPENERS
    assert ops[:6] == S.Executor.HAND_OPENERS == ("dart", "tack", "boomerang", "sniper", "sub", "wizard")
    cap = max(T.tower_cost(k) for k in S.Executor.HAND_OPENERS)
    assert {"desperado", "mermonkey", "skywarden"} <= set(ops)
    assert all(T.tower_cost(k) <= cap for k in ops) and not set(ops) & NEVER


def test_camo_backups_count_as_strong_camo():
    assert S.CAMO_BACKUPS[0] == ("village", "0-2-0")
    kinds = [k for k, _ in S.CAMO_BACKUPS]
    assert len(kinds) == len(set(kinds)) and {"desperado", "skywarden", "mermonkey"} <= set(kinds)
    for kind, cross in S.CAMO_BACKUPS[6:]:
        tiers = S.parse_cross(cross)
        # two such towers make strong camo, as for the hand-listed ones
        assert S.strong_camo([(kind, tiers), (kind, tiers)]), (kind, cross)
        assert kind not in S.INCOME_TOWERS and T.TOWERS[kind].get("placement") != "water"


def test_water_towers_answer_on_maps_built_for_them():
    pond = {"id": "p", "planner": {"maps": ["Pat's Pond"]}}
    kinds = {k for k, _ in S._answer_kinds(pond, "medium")}
    assert {"sub", "buccaneer"} <= kinds
    unknown = {k for k, _ in S._answer_kinds({"id": "u"}, "medium")}
    assert not {"sub", "buccaneer"} & unknown                 # the map is unknown: as before
    dry = {k for k, _ in S._answer_kinds({"id": "d", "map": "Monkey Meadow"}, "medium")}
    assert "sub" not in dry


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
