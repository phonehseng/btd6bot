"""counters.json's gaps filled from the game model (docs/tower_exclusions_audit.md item 5).

The hand facts had no attacks for the Desperado, Mermonkey, Skywarden, Beast
Handler and Glue Gunner, and no blimp damage for those or for the Ice Monkey
and Dartling: they could never answer a zebra or a DDT, and counted as zero
blimp damage. tools/build_bloon_kb.py now derives the missing facts from
the game model (counters.json "model_towers", read by threats.model_facts):

  * every gap tower has them, and hand facts still win where they exist;
  * a derived attack never claims a property the game model says that
    crosspath cannot pop;
  * a glue that only slows pops nothing; abilities are left out;
  * the Desperado and the Mermonkey now answer a zebra, the Desperado a DDT,
    and the blimp ramp counts their damage.

The "is the file up to date" check is test_threats_offline's
test_derived_parts_are_up_to_date. All offline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import gamemodel as GM  # noqa: E402
from btd6bot import threats as TH  # noqa: E402

GAP_ATTACKS = ("desperado", "mermonkey", "skywarden", "beast_handler", "glue")
GAP_BLIMP = GAP_ATTACKS + ("ice", "dartling")


def test_every_gap_tower_has_derived_facts_and_hand_facts_win():
    if not GM.available():
        return
    for kind in GAP_ATTACKS:
        assert TH.model_facts(kind).get("attacks"), kind
    for kind in GAP_BLIMP:
        assert TH.model_facts(kind).get("blimp_dps"), kind
    for kind in ("ice", "dartling"):            # their hand attacks stay
        assert "attacks" not in TH.model_facts(kind) and TH.tower_facts(kind)["attacks"], kind
    assert TH.model_facts("dart") == {} and TH.blimp_dps("dart", (0, 0, 4)) == 15


def test_derived_attacks_never_claim_what_the_game_denies():
    if not GM.available():
        return
    for kind in GAP_ATTACKS:
        for attack in TH.model_facts(kind)["attacks"]:
            assert attack["confidence"] == "game_model" and attack["type"] == "model"
            for cross in attack["crosspaths"]:
                tiers = TH._tiers(cross)
                for prop in ("lead", "black", "white", "purple"):
                    if prop not in attack["cannot_pop"]:
                        assert GM.can(kind, tiers, prop) is not False, (kind, cross, prop)


def test_a_glue_that_only_slows_pops_nothing():
    if not GM.available():
        return
    assert TH.attacks("glue", (0, 0, 0)) == ()
    assert TH.blimp_dps("glue", (0, 0, 0)) == 0.0
    assert TH.attacks("glue", (2, 0, 0))                     # Corrosive Glue does damage


def test_gift_box_towers_answer_two_immunities_and_blimps():
    if not GM.available():
        return
    zebra, ddt = TH.sig_from_name("zebra"), TH.sig_from_name("ddt")
    assert TH.covers([("d", "desperado", (0, 0, 0))], zebra)[0]
    assert TH.covers([("m", "mermonkey", (0, 0, 0))], zebra)[0]
    assert TH.covering_crosspaths("desperado", ddt)
    load = {"speed": 25.0, "span_s": 10.0, "blimps": 2}
    assert TH.blimp_capacity([("d", "desperado", (4, 0, 0))], load, 500.0) > 0
    assert TH.blimp_dps("desperado", (4, 0, 0)) > TH.blimp_dps("desperado", (0, 0, 0)) > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
