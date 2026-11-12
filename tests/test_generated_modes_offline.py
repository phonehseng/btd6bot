"""Generated solo builds: every mode, a Hard build for every tower, the
paragon bar and gift-box helpers (docs/tower_exclusions_audit.md item 9).

  * candidate_modes tries every mode the game has (Double HP, Half Cash,
    ABR, Impoppable, CHIMPS too), CHIMPS never for an income tower;
  * the Hard and Impoppable families (and Apopalypse) need the build's own
    blimp damage;
  * a clean Hard pass starts at the planner's paragon bar, Impoppable one
    hand-tested step below it;
  * gift-box towers may be answer helpers (not a tower that must be aimed);
  * the Hard reinforcement adds copies of the build's blimp damage, records
    them in the file (generator.hard_extra), and stops at the first count
    that passes Hard.

Fast and offline: the threat simulation is stood in for where it would run.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gen_builds as G  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def test_every_mode_is_a_candidate():
    for kind in T.TOWERS:
        modes = G.candidate_modes(kind)
        assert {"easy", "medium", "hard", "double_hp", "half_cash", "abr", "impoppable"} <= set(modes), kind
        assert ("chimps" in modes) == (kind not in S.INCOME_TOWERS), kind
        assert all(m in S.MODE_RULES for m in modes)
    assert "magic_only" in G.candidate_modes("ninja") and "primary_only" in G.candidate_modes("dart")


def test_own_damage_modes():
    for mode in ("hard", "magic_only", "double_hp", "half_cash", "abr", "impoppable", "chimps", "apopalypse"):
        assert G.needs_own_damage(mode), mode
    for mode in ("easy", "deflation", "medium", "reverse"):
        assert not G.needs_own_damage(mode), mode


def test_a_clean_hard_pass_starts_at_the_paragon_bar():
    assert G.BASE_CEILING["hard"] == P.DEFAULT_CONFIG.paragon_min_p
    clean = G.Verdict("hard", True, "ok", ratio=2.0, share=0.9)
    assert G.base_success(clean) == P.DEFAULT_CONFIG.paragon_min_p
    one_life = G.Verdict("chimps", True, "ok", ratio=2.0, share=0.9)
    assert G.base_success(one_life) == G.BASE_CEILING["impoppable"] < G.BASE_CEILING["hard"]
    helped = G.Verdict("hard", True, "ok", ratio=2.0, share=0.9, helpers=("ace",))
    assert G.base_success(helped) < G.base_success(clean)


def test_gift_box_towers_may_be_helpers():
    b = G.build_carry("sniper")
    kinds = {tower[1] for threat in ("moab", "ceramic", "camo", "lead")
             for _c, _s, _d, tower in G._helper_options(threat, b, {"sniper"}, None, True)}
    assert kinds & set(T.GIFT_BOX_TOWERS) - {"dartling"}, kinds
    assert "dartling" not in kinds                    # it must be aimed: never a helper


def test_extra_copies_and_their_record():
    plain, more = G.build_carry("dart"), G.build_carry("dart", 2)
    count = lambda b: sum(1 for st, _ in b.plan if st.get("do") == "place" and st.get("kind") == "dart")  # noqa: E731
    assert count(more) == count(plain) + 2
    # a tower with no blimp damage of its own gets more defence instead
    support = "village"
    plain, more = G.build_support(support), G.build_support(support, 2)
    defence = plain.lines["defence"].kind
    dcount = lambda b: sum(1 for st, _ in b.plan if st.get("do") == "place" and st.get("kind") == defence)  # noqa: E731
    assert dcount(more) == dcount(plain) + 2
    b = G._assemble("dart", ["easy"], 3)
    assert b.strategy(["easy"])["generator"] == {"hard_extra": 3}
    assert "generator" not in G._assemble("dart", ["easy"]).strategy(["easy"])


def test_the_reinforcement_stops_at_the_first_count_that_passes():
    saved = G.judge, G._assemble
    tried = []

    def fake_assemble(kind, modes, extra=0):
        tried.append(extra)
        b = G.Build(kind)
        b.extra = extra
        return b

    def fake_judge(b, strat, mode, defence=None):
        ok = b.extra >= 2
        return G.Verdict(mode, ok, "ok" if ok else "blimp damage 0.80 < 1.00")
    G.judge, G._assemble = fake_judge, fake_assemble
    try:
        assert G._hard_extra("dart", ["hard"]) == 2 and tried == [1, 2]
        G.judge = lambda b, strat, mode, defence=None: G.Verdict(mode, False, "gap R40: moab (x)")
        assert G._hard_extra("dart", ["hard"]) == 0             # more copies cannot fix a gap
    finally:
        G.judge, G._assemble = saved


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
