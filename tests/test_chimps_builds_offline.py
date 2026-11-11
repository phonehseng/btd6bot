"""CHIMPS builds against the CHIMPS cash curve, and the optimizer's CHIMPS plans.

Why
---
chimps_ninja_sun went 22-9 in Impoppable, every game with Double Cash and
Fast Track (start at round 29/30). CHIMPS has neither: it starts at round 6
with $650, pays only the game's own income (data/rounds.json cash_pop +
cash_bonus) and charges Hard prices (strategy.PRICE_FAMILY). A plan written
for the boosted Impoppable bank buys its MOAB damage tens of rounds late
there. These checks walk a plan in order, at the prices CHIMPS charges, and
find the round each step becomes affordable.

Offline checks:
  * the CHIMPS plans buy their MOAB answer before the executor would start
    forcing it (round 40 minus the one-life lookahead), chimps_ninja_sun its
    Sticky Bomb ninja 2-0-4 so it stands for the first MOAB (round 40), the
    MIB village (2-3-0: camo + every damage type for the super ceramics) by
    round 76, and never need more than 90% of the cash earned by round 95
    (the rest is the margin for reinforce buys, misread prices and the
    R95-100 blimp rounds);
  * no strength threat is answered late: each one's answer (strategy.ANSWERS)
    stands from the plan's own steps by the round Strategy.due_threats starts
    forcing it in one-life modes, so the executor never buys an answer ahead
    of the plan and the cash curve above is the one it really follows;
  * chimps_ninja_sun loads bot-ready, covers every threat of Hard,
    Impoppable and CHIMPS with one plan, and keeps the late rework: no extra
    Sun Avatar; a Ground Zero ace and a MOAB Eliminator (the round-100 BAD
    answer) in the plan, the blimp classes of rounds 80-100 answered by them;
    in Impoppable (Double Cash, Fast Track) the whole plan is bought by
    round 90;
  * chimps_sub_druid_water covers CHIMPS (it once had no 'rush' answer);
  * every strategies/optimized/*chimps*.yaml is bot-ready with a worst model
    margin of at least strategy.OPTIMIZED_SAFE_MARGIN, no sell step, no
    income tower or income upgrade, and none of the tiers the damage model is
    known to overrate (optimize_builds.CHIMPS_MODEL_DOUBTS).
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import gamemodel  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402
from btd6bot import towers as T  # noqa: E402

STRATS = S.load_all()

# Rounds the CHIMPS plans must have bought a step by (see the module docstring).
FIRST_MOAB = {t: r for r, t in S.THREATS}["moab"]   # round 40, from data/rounds.json
# Strategy.due_threats raises its lookahead to this in one-life modes (one
# leak = defeat): a threat's answer is forced in from this many rounds ahead
ONE_LIFE_LOOKAHEAD = 6
MOAB_ANSWER_BY = FIRST_MOAB - ONE_LIFE_LOOKAHEAD   # the MOAB answer is the plan's step, not a forced one
STICKY_BY = FIRST_MOAB - 1  # Sticky Bomb affordable after round 39: it stands for the round-40 MOAB
MIB_BY = 76                # MIB village before the super ceramics of round 81
LATE_ACE_BY = 85           # chimps_ninja_sun's Ground Zero ace before the R86-98 blimp rounds
BAD_ANSWER_BY = {t: r for r, t in S.THREATS}["bad"] - ONE_LIFE_LOOKAHEAD   # round 94
BANK_SHARE_R95 = 0.90      # the whole plan within 90% of the cash earned by round 95


# ---------------------------------------------------------------------------
# The cash curve
# ---------------------------------------------------------------------------

def village_discount(tiers):
    """Fraction off prices near a village at this crosspath: the sum of its
    "discount" buffs in the game model (Monkey Business 10% + Commerce 5%)."""
    combo = (gamemodel._table("attacks").get("towers", {}).get("village", {})
             .get("crosspaths", {}).get("".join(map(str, tiers))) or {})
    return sum(b.get("value") or 0.0 for b in combo.get("buffs", []) if b.get("kind") == "discount")


def plan_timeline(strat, mode, boosts=None):
    """[(step, cumulative cost, round it is affordable)] for a strategy's
    `plan`, bought in order the way the executor buys it.

    Prices: the mode's price family (CHIMPS: Hard). A tower placed near a
    village (its place step lists the village in `near`, or the village's
    step lists it) gets that village's discount once the village has it, on
    its placement and tiers 1-3 only (tiers 4-5 are charged in full here: on
    the safe side). Cash: optimize_builds.economy - the mode's start round
    and cash, then each round's income from data/rounds.json. A step is
    affordable by round R when the cash paid by the end of round R (as
    earned_by counts it) covers everything up to and including it, so it
    stands from round R + 1; start_round - 1: before the first round;
    end_round + 1: never."""
    econ = O.economy(mode, boosts)
    fam = econ.family
    kinds, tiers, near = {}, {}, {}
    villages = set()
    for st in strat["plan"]:
        if st["do"] == "place" and st.get("id"):
            near[st["id"]] = set(st.get("near") or ())
            if st["kind"] == "village":
                villages.add(st["id"])
                for other in st.get("near") or ():
                    near.setdefault(other, set()).add(st["id"])

    def discount(tid):
        return max((village_discount(tiers[v]) for v in near.get(tid, ()) if v in villages and v in tiers),
                   default=0.0)

    out, spent = [], 0.0
    rnd, bank = econ.start_round - 1, econ.start_cash    # rnd: the last round paid into the bank
    # a step with `modes: [...]` is played only in those modes (Executor._step_allowed)
    for st in [st for st in strat["plan"] if mode in (st.get("modes") or [mode])]:
        cost = 0.0
        if st["do"] == "place":
            if st["kind"] == "hero":
                cost = T.hero_cost(strat["hero"], fam)
            else:
                tid = st.get("id") or f"#{len(kinds)}"
                kinds[tid], tiers[tid] = st["kind"], (0, 0, 0)
                cost = T.tower_cost(st["kind"], fam) * (1.0 - discount(tid))
        elif st["do"] == "upgrade":
            ids = [st["id"]] if st.get("id") else [t for t, k in kinds.items() if k == st["kind"]]
            new = S.parse_cross(st["to"])
            for tid in ids:
                off = discount(tid)
                old = tiers[tid]
                for path in range(3):
                    for tier in range(old[path] + 1, new[path] + 1):
                        cost += T.upgrade_cost(kinds[tid], path + 1, tier, fam) * (1.0 - (off if tier <= 3 else 0.0))
                tiers[tid] = tuple(max(a, b) for a, b in zip(old, new))
        spent += cost
        while bank < spent and rnd < econ.end_round:
            rnd += 1
            bank += econ.income(rnd)
        out.append((st, spent, rnd if bank >= spent else econ.end_round + 1))
    return out


def earned_by(mode, rnd, boosts=None):
    """Cash a game of this mode has been paid by the end of round rnd."""
    econ = O.economy(mode, boosts)
    return econ.start_cash + sum(econ.income(r) for r in range(econ.start_round, rnd + 1))


def first_round(timeline, tid, cross):
    """Round the step upgrading tower tid to cross (e.g. "2-0-4") is affordable."""
    for st, _, rnd in timeline:
        if st["do"] == "upgrade" and st.get("id") == tid and st["to"] == cross:
            return rnd
    raise AssertionError(f"plan has no step {tid} -> {cross}")


def chimps_plans():
    """The hand-written strategies that play CHIMPS (not the optimized ones,
    which carry their own round-by-round proof)."""
    return [s for s in STRATS.values() if "chimps" in s.get("modes", []) and s.get("source") is None]


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

def test_cash_curve_matches_the_round_data():
    """The CHIMPS bank the tests use: $650 before round 6, no boosts, the
    game's own pop + end-of-round cash (sums checked against rounds.json)."""
    econ = O.economy("chimps", {"double_cash": True, "fast_track": True})
    assert (econ.start_round, econ.start_cash, econ.cash_mult, econ.family) == (6, 650.0, 1.0, "hard")
    rounds = json.loads((ROOT / "data" / "rounds.json").read_text(encoding="utf-8"))["standard"]
    for r in (6, 40, 63, 98):
        assert econ.income(r) == rounds[str(r)]["cash_pop"] + rounds[str(r)]["cash_bonus"], r
    assert 16000 < earned_by("chimps", 40) < 17500
    assert 170000 < earned_by("chimps", 98) < 180000


def mib_round(strat, timeline):
    """Round the plan's first MIB village (middle path tier 3+) is affordable."""
    villages = {st["id"] for st in strat["plan"] if st["do"] == "place" and st.get("kind") == "village"}
    for st, _, rnd in timeline:
        if st["do"] == "upgrade" and st.get("id") in villages and S.parse_cross(st["to"])[1] >= 3:
            return rnd
    raise AssertionError(f"{strat['id']}: no MIB village in the plan")


def test_chimps_plans_fit_the_chimps_cash_curve():
    plans = chimps_plans()
    assert {"chimps_ninja_sun", "chimps_sub_druid_water"} <= {s["id"] for s in plans}
    for strat in plans:
        sid = strat["id"]
        tl = plan_timeline(strat, "chimps")
        total = tl[-1][1]
        assert total <= BANK_SHARE_R95 * earned_by("chimps", 95), (sid, total, earned_by("chimps", 95))
        # the strategy's own MOAB answer is a plan step, bought before it is due
        moab = strat["answers"]["moab"][0]
        assert first_round(tl, moab["id"], moab["to"]) <= MOAB_ANSWER_BY, (sid, moab)
        assert mib_round(strat, tl) <= MIB_BY, (sid, mib_round(strat, tl))
    tl = plan_timeline(STRATS["chimps_ninja_sun"], "chimps")
    # the real MOAB damage stands for the first MOAB
    assert first_round(tl, "n2", "2-0-4") <= STICKY_BY, first_round(tl, "n2", "2-0-4")
    # the late blimp damage (2026-11-10 rework): the Ground Zero ace before the
    # R90s, and the MOAB Eliminator - the R100 BAD answer - by the round the
    # executor would start forcing a BAD answer in (100 - ONE_LIFE_LOOKAHEAD)
    assert first_round(tl, "ac1", "2-4-0") <= LATE_ACE_BY, first_round(tl, "ac1", "2-4-0")
    assert first_round(tl, "b1", "0-5-0") <= BAD_ANSWER_BY, first_round(tl, "b1", "0-5-0")


def test_chimps_ninja_sun_is_ready_in_every_mode():
    """One plan serves Hard, Impoppable and CHIMPS: a strategy carries one
    `plan` for all its modes (the Executor reads strat["plan"]), and the plan
    timed to the CHIMPS bank is simply bought earlier with Impoppable's
    boosts. Its CHIMPS prior stays low enough that it is not auto-played
    there before it has evidence."""
    assert STRATS["chimps_ninja_sun"]["planner"]["base_success"]["chimps"] <= 0.4
    for sid in ("chimps_ninja_sun", "chimps_sub_druid_water"):
        strat = STRATS[sid]
        assert strat["bot_ready"], (sid, S.readiness(strat))
        for mode in strat["modes"]:
            ok, missing = S.coverage(strat, mode)
            assert ok, (sid, mode, missing)


def test_late_game_is_moab_damage_not_extra_sun_avatars():
    """The R86-98 losses: a 3-0-2 Sun Avatar has no MOAB bonus, so the late
    money goes to blimp damage. Since the 2026-11-10 rework that is a Bloon
    Sabotage ninja, a MOAB Assassin bomb grown to MOAB Eliminator (the BAD
    answer) and a Ground Zero ace - the damage model rated a $32,400
    Perma-Spike and four Maim MOAB snipers at almost nothing for rounds
    90-100 (strategies/chimps_ninja_sun.yaml header). One Sun Avatar stays
    for the super ceramics from round 81."""
    strat = STRATS["chimps_ninja_sun"]
    final = {}
    # the CHIMPS plan (Impoppable adds steps of its own: `modes: [impoppable]`)
    for st in [st for st in strat["plan"] if "chimps" in (st.get("modes") or ["chimps"])]:
        if st["do"] == "place" and st.get("id") and st["kind"] != "hero":
            final[st["id"]] = (st["kind"], (0, 0, 0))
        elif st["do"] == "upgrade" and st.get("id") in final:
            final[st["id"]] = (final[st["id"]][0], tuple(S.parse_cross(st["to"])))
    builds = set(final.values())
    assert sum(1 for k, _ in final.values() if k == "super") == 1
    for need in (("spike", (2, 0, 4)), ("ninja", (0, 4, 0)), ("bomb", (0, 5, 0)),
                 ("ace", (2, 4, 0)), ("ninja", (2, 0, 4)), ("village", (2, 3, 0))):
        assert need in builds, need
    # the late blimp classes are answered by the late damage, not by the
    # round-39 Sticky Bomb that stands long before them
    assert strat["answers"]["zomg"][0] == {"do": "upgrade", "id": "ac1", "to": "2-4-0"}
    for cls in ("ddt", "bad"):
        assert strat["answers"][cls][0] == {"do": "upgrade", "id": "b1", "to": "0-5-0"}, cls
    # Flash Bomb answers the first MOABs (affordable by R34), Sticky Bomb follows
    assert strat["answers"]["moab"] == [{"do": "upgrade", "id": "n2", "to": "2-0-3"}]
    assert strat["answers"]["bfb"] == [{"do": "upgrade", "id": "n2", "to": "2-0-4"}]
    # the surplus buys no Super Monkeys and no more 4-0-2 ninjas (no blimp damage)
    for st in strat.get("fill") or ():
        assert st.get("kind") not in ("super", "ninja"), st


def answered(threat, board):
    """Does a board {id: (kind, tiers)} answer this strength threat by the
    tables Strategy.has_answer uses for it?"""
    if threat in S.STRONG_CAMO:
        return S.strong_camo(board.values())
    return any(k == kind and (path == 0 or tiers[path - 1] >= tier)
               for kind, tiers in board.values() for k, path, tier in S.ANSWERS.get(threat, []))


def answer_rounds(strat, mode):
    """{threat: round its answer is affordable from the plan's own steps}
    for the strength threats (the ones without a bloon signature: ceramic,
    moab, bfb, rush, zomg, bad, camo ceramic), walking plan_timeline."""
    threats = [t for _, t in S.THREATS
               if t in S.STRONG_CAMO or (t != "ddt" and TH.sig_from_name(t) is None)]
    board, out = {}, {}
    for st, _, rnd in plan_timeline(strat, mode):
        if st["do"] == "place" and st.get("id") and st["kind"] != "hero":
            board[st["id"]] = (st["kind"], (0, 0, 0))
        elif st["do"] == "upgrade" and st.get("id") in board:
            kind, old = board[st["id"]]
            board[st["id"]] = (kind, tuple(max(a, b) for a, b in zip(old, S.parse_cross(st["to"]))))
        for t in threats:
            if t not in out and answered(t, board):
                out[t] = rnd
    return {t: out.get(t) for t in threats}


def test_no_answer_is_forced_ahead_of_the_chimps_plan():
    """Strategy.due_threats forces a threat's answer from ONE_LIFE_LOOKAHEAD
    rounds before it in CHIMPS, ahead of the plan. When the plan's own steps
    are not there by then, the executor buys the answer first and every later
    step slips (the ceramic answer n1 3-0-2 once sat behind the $7.8k Sticky
    Bomb and pushed it past the first MOAB). Every strength threat must be
    answered by chimps_ninja_sun's plan itself in time.
    (chimps_sub_druid_water is not held to this yet: its Radar village, the
    camo ceramic answer of round 51, is affordable at R48, three rounds after
    the executor starts forcing one - docs/backlog.md.)"""
    first = {t: r for r, t in S.THREATS}
    start = S.MODE_RULES["chimps"]["start_round"]
    for threat, rnd in answer_rounds(STRATS["chimps_ninja_sun"], "chimps").items():
        due = max(first[threat], start)
        assert rnd is not None and rnd <= due - ONE_LIFE_LOOKAHEAD, (threat, rnd, due)


def test_impoppable_plan_fits_the_boosted_bank():
    """chimps_ninja_sun in Impoppable (Double Cash + Fast Track, as every one
    of its games so far): the late MOAB damage (Ground Zero, MOAB
    Eliminator) well before R95."""
    boosts = {"double_cash": True, "fast_track": True}
    tl = plan_timeline(STRATS["chimps_ninja_sun"], "impoppable", boosts)
    assert tl[-1][2] <= 90, tl[-1][2]
    assert tl[-1][1] <= BANK_SHARE_R95 * earned_by("impoppable", 95, boosts)


def test_sub_druid_water_has_a_rush_answer():
    strat = STRATS["chimps_sub_druid_water"]
    assert "rush" in strat["answers"]
    ok, missing = S.coverage(strat, "chimps")
    assert ok, missing


def _optimized_chimps():
    return sorted(O.OUT_DIR.glob("*chimps*.yaml")) if O.OUT_DIR.is_dir() else []


def test_optimized_chimps_builds_are_safe_and_follow_the_rules():
    """The gate for the optimizer's CHIMPS output, ahead of its first file:
    no strategies/optimized/*chimps*.yaml is committed yet (a CHIMPS run
    takes over half an hour per XP target, docs/backlog.md item 35), so the
    loop below checks nothing until one is. The rules it enforces are
    checked on their own in test_model_doubts_and_income_rules."""
    for path in _optimized_chimps():
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        strat = STRATS[d["id"]]
        assert d["modes"] == ["chimps"], path.name
        assert strat["bot_ready"], (path.name, strat["bot_ready_reasons"])
        opt = d["optimizer"]
        assert opt["worst_margin"] >= S.OPTIMIZED_SAFE_MARGIN and not opt["unsafe_rounds"], path.name
        kinds = {}
        for st in d["plan"] + (d.get("fill") or []):
            assert st["do"] != "sell", (path.name, st)
            if st["do"] == "place":
                assert st["kind"] not in S.INCOME_TOWERS, (path.name, st)
                kinds[st.get("id")] = st["kind"]
            elif st["do"] == "upgrade":
                kind = st.get("kind") or kinds[st["id"]]
                tiers = S.parse_cross(st["to"])
                assert not O.income_tiers(kind, tiers), (path.name, st)
                assert not O.model_doubt(kind, tiers), (path.name, st, O.model_doubt(kind, tiers))


def test_model_doubts_and_income_rules():
    """The optimizer's CHIMPS filters: income towers and upgrades are out
    wherever the mode forbids income, and the tiers the damage model is
    known to overrate are out in CHIMPS until that model is fixed."""
    assert O.income_tiers("buccaneer", (0, 0, 3)) and O.income_tiers("engineer", (0, 0, 4))
    assert not O.income_tiers("buccaneer", (2, 0, 2))
    assert O.model_doubt("boomerang", (5, 0, 2)) and O.model_doubt("ninja", (2, 0, 5))
    assert not O.model_doubt("ninja", (2, 0, 4)) and not O.model_doubt("boomerang", (4, 0, 2))
    assert O.model_doubt("village", (3, 0, 2), towers=[("ninja", (4, 0, 2))])
    assert not O.model_doubt("village", (3, 0, 2), towers=[("dart", (0, 2, 4))])
    for target in (None, "farm"):
        opt = O.Optimizer.__new__(O.Optimizer)
        opt.mode, opt.target, opt.account = "chimps", target, None
        opt.setup = O.MapSetup("Monkey Meadow", "chimps")
        assert "farm" not in opt._kinds(), target
    assert "chimps" in dict(O.CHIMPS_RUNS).values()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
