"""Strength-threat answers from the damage model (docs/tower_exclusions_audit.md item 3).

strategy.ANSWERS, written by hand, never accepted Glue, Desperado,
Alchemist, Mermonkey, Skywarden, Engineer or Beast Handler for a ceramic,
MOAB-class or rush round (Ice and Dartling only for the rush), and
runner.py drops every mode where coverage() finds a threat unanswered. Now
tools/build_bloon_kb.py adds the paths the damage model rates at least as
strong as the median hand-listed answer (counters.json "model_answers"):

  * the hand table is kept whole and first; entries are only added, and
    only for a (tower, path) it does not list;
  * no income tower; a Heli only with Pursuit (path 1, tier 2 and up);
  * towers the hand table left out now answer where the model says so;
  * a Desperado build that coverage() refused for the MOAB is accepted.

"Is the derived part up to date" is test_threats_offline's
test_derived_parts_are_up_to_date. All offline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402

DERIVED = (TH.counters().get("model_answers") or {}).get("answers") or {}


def test_hand_answers_stay_whole_and_first():
    for threat, hand in S.HAND_ANSWERS.items():
        if threat in ("camo", "lead"):
            continue                    # those two follow the game model (_answers_from_game_model)
        assert S.ANSWERS[threat][:len(hand)] == hand, threat


def test_derived_answers_add_only_unlisted_paths():
    if not D.available():
        return
    assert set(DERIVED) == {"ceramic", "rush", "moab", "bfb", "zomg", "ddt", "bad"}
    for threat, entries in DERIVED.items():
        hand = S.HAND_ANSWERS[threat]
        listed = {(k, p) for k, p, _ in hand} | {(k, q) for k, p, _ in hand if p == 0 for q in (1, 2, 3)}
        for kind, path, tier in entries:
            assert (kind, path) not in listed, (threat, kind, path)
            assert kind not in S.INCOME_TOWERS and 1 <= tier <= 5, (threat, kind, tier)
            if kind == "heli":
                assert path == 1 and tier >= 2, (threat, path, tier)    # Pursuit first
            assert (kind, path, tier) in S.ANSWERS[threat]


def test_towers_the_hand_table_left_out_now_answer_on_merit():
    if not D.available():
        return
    kinds = {k for entries in DERIVED.values() for k, _, _ in entries}
    # the model finds a strength answer for these, which the hand table never had
    for kind in ("desperado", "mermonkey", "skywarden", "glue", "engineer"):
        assert kind in kinds, kind
    assert "ice" in {k for k, _, _ in DERIVED["moab"]}       # beyond the rush
    # the Mortar is rated at a fixed aim point now (damage model, merged
    # 2026-11-12), so it may count where a build has it; it still needs
    # aiming, so the executor never buys a new one as an answer
    from btd6bot import threats as TH
    assert TH.tower_facts("mortar").get("needs_aim")


def test_a_desperado_build_is_covered_for_the_moab_now():
    if not D.available():
        return
    entry = next(e for e in DERIVED["moab"] if e[0] == "desperado")
    tiers = [0, 0, 0]
    tiers[entry[1] - 1] = entry[2]
    to = "-".join(map(str, tiers))
    strat = {"id": "t", "plan": [{"do": "place", "id": f"d{i}", "kind": "desperado"} for i in range(3)]
             + [{"do": "upgrade", "id": f"d{i}", "to": to} for i in range(3)]}
    _ok, missing = S.coverage(strat, "medium")
    assert "moab" not in missing, missing
    saved = dict(S.ANSWERS)
    try:
        S.ANSWERS.clear()
        S.ANSWERS.update({t: list(v) for t, v in S.HAND_ANSWERS.items()})
        assert "moab" in S.coverage(strat, "medium")[1]       # the hand table alone refused it
    finally:
        S.ANSWERS.clear()
        S.ANSWERS.update(saved)


def test_the_executor_buys_only_toward_hand_listed_strength_answers():
    """A model answer counts where a build has it, but the executor's own
    generic answer upgrades toward hand-listed ones only (buyable_answers):
    on Ascent Easy it otherwise took the plan's cash for a 4-0-0 Skywarden."""
    for threat in DERIVED:
        assert S.buyable_answers(threat) == S.HAND_ANSWERS[threat], threat
    assert S.buyable_answers("camo") == S.ANSWERS["camo"]           # the game model's, as before
    assert S.buyable_answers("purple") == S.ANSWERS["purple"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
