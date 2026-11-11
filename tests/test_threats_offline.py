"""Offline tests for the bloon knowledge base (data/bloons.json, data/counters.json,
btd6bot/threats.py) and the threat checks in strategy.Executor.

Covers:
  * the knowledge files are complete, consistent with an independent source
    (data/rounds.json RBE and first appearances) and up to date with their
    derivation (tools/build_bloon_kb.py --check);
  * the nature of bloons: children inherit camo, a lead pops into blacks,
    a DDT is camo + lead + black, a BAD carries DDTs;
  * which defences can pop which signature (one attack must get past every
    immunity at once), including radar, MIB, the Alchemist's lead dip, and
    the conservative cases (Sun Avatar and purple, Maim MOAB without camo,
    bombs and DDTs);
  * the fast answer search gives exactly what brute force over covers() gives;
  * the Executor answers a threat before its round with the cheapest allowed
    option, follows the plan when the plan covers it cheaply, respects the
    mode's tower set and the strategy's constraints, holds Play only while
    an answer is affordable, and never spends saved cash on surplus;
  * every general strategy, played offline through every mode it lists with
    the game's real income (tools/simulate_threats.py), can pop every bloon
    of every round when it arrives.
Run: python tests/test_threats_offline.py"""
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import strategy as S  # noqa: E402
from btd6bot import threats as TH  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.game import Placed  # noqa: E402

import build_bloon_kb  # noqa: E402
import simulate_threats as SIM  # noqa: E402

logging.getLogger("strategy").setLevel(logging.CRITICAL)
DATA = ROOT / "data"


def sig(name):
    return TH.sig_from_name(name)


# -- the knowledge files ----------------------------------------------------------------
def test_bloons_json_keeps_tracklearn_fields():
    """tracklearn.py reads speed / bright / hue; they must survive the extension."""
    bloons = json.loads((DATA / "bloons.json").read_text(encoding="utf-8"))["bloons"]
    for name, b in bloons.items():
        assert isinstance(b["speed"], (int, float)) and isinstance(b["bright"], bool), name
        if b["bright"]:
            assert b["hue"], name
    from btd6bot import tracklearn
    assert tracklearn.choose_rounds(), "track learning can still pick rounds"


def test_rbe_matches_rounds_json():
    """RBE derived from our children/HP facts == the independent table in rounds.json."""
    ref = json.loads((DATA / "rounds.json").read_text(encoding="utf-8"))["blimp_hp"]
    for name, value in ref["rbe"].items():
        assert TH.rbe(name) == value, (name, TH.rbe(name), value)
    for name, value in ref["rbe_fortified"].items():
        assert TH.rbe(name, fortified=True) == value, (name, TH.rbe(name, fortified=True), value)


def test_derived_parts_are_up_to_date():
    assert build_bloon_kb.out_of_date() == [], "run: python tools/build_bloon_kb.py"


def test_every_tower_has_facts():
    towers = TH.counters()["towers"]
    assert set(towers) == set(T.TOWERS), set(T.TOWERS) ^ set(towers)
    types = set(TH.counters()["damage_types"])
    levels = set(TH.counters()["confidence_levels"])
    for kind, facts in towers.items():
        for a in facts.get("attacks") or ():
            assert a["type"] in types, (kind, a)
            assert a.get("confidence", "established") in levels, (kind, a)


# -- the nature of bloons -------------------------------------------------------------------
def test_children_carry_their_own_immunities():
    names = lambda b, **kw: {TH.sig_name(s) for s in TH.signatures(b, **kw)}  # noqa: E731
    assert names("lead") == {"lead", "black"}, "a lead pops into two blacks"
    assert names("ceramic") == {"zebra", "black", "white"}, "ceramic -> rainbow -> zebra -> black/white"
    assert names("lead", camo=True) == {"camo+lead", "camo+black", "camo"}, "camo is inherited"
    assert "ddt" in names("ddt") and "camo+zebra" in names("ddt"), "DDTs drop camo ceramics"
    assert "ddt" in names("bad"), "a BAD carries three DDTs"
    assert sig("ddt") == frozenset({"blimp", "camo", "lead", "black"})


def test_first_rounds_from_the_game_rounds():
    std = TH.first_rounds("standard", 1, 140)
    abr = TH.first_rounds("abr", 1, 140)
    assert (std["camo"], std["purple"], std["lead"], std["camo+lead"], std["ddt"]) == (24, 25, 28, 59, 90)
    assert (abr["camo"], abr["lead"], abr["purple"], abr["camo+lead"], abr["ddt"]) == (5, 10, 15, 24, 88)
    # the same as rounds.json's independently built first appearances
    fa = json.loads((DATA / "rounds.json").read_text(encoding="utf-8"))["first_appearance"]
    for key in ("camo", "purple", "lead", "camo_lead", "ddt"):
        assert std[key.replace("_", "+")] == fa["standard"][key], key
        assert abr[key.replace("_", "+")] == fa["abr"][key], key
    # Hard (3-80) never meets a DDT; CHIMPS (6-100) does
    assert "ddt" not in TH.calendar("standard", 3, 80)
    assert TH.calendar("standard", 6, 100)["ddt"][0] == 90


# -- what pops what -------------------------------------------------------------------------
def test_camo_lead_needs_one_tower_for_both():
    ninja_bomb = [("n", "ninja", (0, 0, 0)), ("b", "bomb", (0, 0, 0))]
    assert TH.covers(ninja_bomb, sig("camo"))[0] and TH.covers(ninja_bomb, sig("lead"))[0]
    assert not TH.covers(ninja_bomb, sig("camo+lead"))[0], "Ninja sees it, Bomb pops it - nobody does both"
    assert TH.covers(ninja_bomb + [("v", "village", (0, 2, 0))], sig("camo+lead"))[0], "radar lets the bomb see"
    near = lambda a, b: False  # noqa: E731  - the village stands too far away
    assert not TH.covers(ninja_bomb + [("v", "village", (0, 2, 0))], sig("camo+lead"), near)[0]


def test_explosions_and_freeze_alone_leak():
    assert not TH.covers([("b", "bomb", (0, 2, 0))], sig("black"))[0], "a lead's children escape bombs"
    assert TH.covers([("b", "bomb", (0, 0, 2))], sig("zebra"))[0], "Frag Bombs pop black and zebra"
    assert not TH.covers([("i", "ice", (0, 1, 0))], sig("white"))[0]
    assert TH.covers([("i", "ice", (2, 0, 0))], sig("lead"))[0], "Cold Snap"
    assert not TH.covers([("i", "ice", (2, 0, 0))], sig("blimp"))[0], "MOAB-class cannot be frozen"


def test_purple_is_conservative():
    assert not TH.covers([("s", "super", (3, 0, 2))], sig("purple"))[0], "Sun Avatar is plasma"
    assert not TH.covers([("t", "tack", (4, 0, 0))], sig("purple"))[0], "Ring of Fire is fire"
    assert not TH.covers([("w", "wizard", (0, 0, 2))], sig("purple"))[0], "magic bolts"
    assert TH.covers([("n", "ninja", (4, 0, 2))], sig("purple"))[0]


def test_game_model_is_the_source_of_truth():
    """Where data/game_model answers, it decides; counters.json only fills gaps."""
    from btd6bot import gamemodel
    if not gamemodel.available():
        return                                  # no decoded model on this machine
    for kind in TH.counters()["towers"]:
        for t in ((0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2), (4, 0, 2), (2, 0, 4)):
            for prop in ("lead", "black", "white", "purple"):
                game = gamemodel.can(kind, t, prop)
                if game is not None:
                    ours = TH.covers([("t", kind, t)], frozenset({prop}))[0]
                    assert ours == game, (kind, t, prop, ours, game)
            game = gamemodel.can(kind, t, "camo")
            if game:
                assert TH.camo_access(kind, t), (kind, t)
    # facts the model confirmed where counters.json was unsure (or wrong)
    assert TH.covers([("d", "druid", (2, 0, 0))], sig("lead"))[0], "Heart of Thunder pops lead"
    assert TH.covers([("b", "boomerang", (0, 0, 2))], sig("purple"))[0], "Red Hot Rangs is not fire"


def test_without_the_game_model_likely_facts_do_not_count():
    saved = TH._gm
    TH._gm = lambda: None
    TH.clear_caches()
    try:
        assert not TH.covers([("s", "sub", (3, 0, 0)), ("x", "sniper", (1, 0, 0))], sig("camo+lead"))[0], \
            "Submerge and Support decamo is only 'likely' in counters.json"
        assert not TH.covers([("d", "druid", (2, 0, 0))], sig("lead"))[0], "lightning unconfirmed there"
    finally:
        TH._gm = saved
        TH.clear_caches()


def test_ddt_needs_camo_lead_and_black_at_once():
    assert not TH.covers([("s", "sniper", (4, 0, 0)), ("n", "ninja", (0, 0, 0))], sig("ddt"))[0], \
        "Maim MOAB without Night Vision cannot target a DDT"
    assert TH.covers([("s", "sniper", (4, 1, 0))], sig("ddt"))[0]
    assert not TH.covers([("b", "bomb", (0, 4, 0)), ("v", "village", (0, 2, 0))], sig("ddt"))[0], \
        "explosions cannot hurt DDTs (black)"
    assert TH.covers([("b", "bomb", (0, 4, 0)), ("v", "village", (0, 3, 0))], sig("ddt"))[0], "MIB"
    assert TH.covers([("n", "ninja", (2, 0, 4))], sig("ddt"))[0], "Sticky Bomb"
    # a decamo is not trusted against DDTs
    assert not TH.covers([("d", "dart", (4, 0, 0)), ("n", "ninja", (0, 2, 0))], sig("ddt"))[0]
    assert TH.covers([("d", "dart", (4, 0, 0)), ("n", "ninja", (0, 2, 0))], sig("camo+lead"))[0]


def test_alchemist_dip_lends_lead():
    team = [("s", "sniper", (0, 2, 4)), ("a", "alchemist", (2, 0, 0))]
    assert TH.covers(team, sig("camo+lead"))[0]
    assert not TH.covers(team, sig("camo+lead"), lambda a, b: False)[0], "only within its range"
    assert not TH.covers([("s", "sniper", (0, 2, 4)), ("a", "alchemist", (1, 0, 0))], sig("camo+lead"))[0]


def test_fast_answer_search_equals_brute_force():
    rng = random.Random(7)
    kinds = list(TH.counters()["towers"])
    sigs = sorted({s for r in range(1, 141) for s in TH.round_signatures("standard", r)}, key=TH.sig_name)
    for _ in range(300):
        base = [(f"b{i}", rng.choice(kinds + ["village", "alchemist"]), rng.choice(TH.all_crosspaths()))
                for i in range(rng.randint(0, 5))]
        ids = [b[0] for b in base] + ["__new__"]
        pairs = {(a, b): rng.random() < 0.5 for a in ids for b in ids}
        inr = lambda a, b: pairs[(a, b)]  # noqa: E731
        s, kind = rng.choice(sigs), rng.choice(kinds)
        slow = []
        for t in TH.all_crosspaths():
            if not any(all(f[i] <= t[i] for i in range(3)) for f in slow) and \
                    TH.covers(base + [("__new__", kind, t)], s, inr)[0]:
                slow.append(t)
        assert TH.covering_crosspaths(kind, s, base, in_range=inr) == slow, (kind, TH.sig_name(s), base)


def test_blimp_load_includes_children_and_ramping():
    assert TH.round_blimp_load("standard", 40)["hp"] == 200
    assert TH.round_blimp_load("standard", 40, double_hp=True)["hp"] == 400
    r100 = TH.round_blimp_load("standard", 100)
    assert abs(r100["hp"] - 41200 * 1.4) < 1e-6, "BAD + 2 ZOMGs + 3 DDTs, freeplay x1.40"
    assert TH.round_blimp_load("standard", 39) is None
    # the lives a leak costs: one MOAB with its children (data/bloons.json rbe)
    assert TH.round_blimp_load("standard", 40)["leak"] == 616
    assert r100["leak"] > TH.round_blimp_load("standard", 40)["leak"]


def test_a_lethal_blimp_round_wants_a_margin():
    """Mushroom Grotto Double HP (2026-11-05): round 40's MOAB passed the
    blimp check at 1.1x and took all 100 lives. A round whose blimps would
    cost the mode's lives is judged against RAMP_OK_LETHAL; a load that
    would cost fewer lives (or says nothing about it) keeps RAMP_OK."""
    g, ex = executor({}, towers=[("s1", "sniper", (3, 2, 0))], cash=1000)
    load = TH.round_blimp_load("standard", 40, double_hp=True)
    assert ex.rules["lives"] == 100 and load["leak"] >= 100
    assert ex.ramp_bar(load) == ex.RAMP_OK_LETHAL > ex.RAMP_OK
    assert ex.ramp_bar({**load, "leak": 50}) == ex.RAMP_OK
    assert ex.ramp_bar({"hp": 200}) == ex.RAMP_OK and ex.ramp_bar(None) == ex.RAMP_OK
    # one life: every blimp leak ends the game
    g, ex = executor({}, mode="impoppable", towers=[("s1", "sniper", (3, 2, 0))], cash=1000)
    assert ex.ramp_bar({**load, "leak": 1}) == ex.RAMP_OK_ONE_LIFE > ex.RAMP_OK_LETHAL


# -- the Executor -----------------------------------------------------------------------------
def executor(strat, mode="hard", cash=650, towers=(), account=None):
    g = SIM.CashGame(S.PRICE_FAMILY[mode])
    g.cash = cash
    for tid, kind, tiers in towers:
        g.towers[tid] = Placed(tid, kind, 0.3 + 0.01 * len(g.towers), 0.3, list(tiers))
    ex = S.Executor(g, SIM.OpenModel(), dict({"id": "t", "modes": [mode], "plan": []}, **strat), mode,
                    account or SIM.full_account())
    return g, ex


def run_rounds(g, ex, rounds, income=0, ticks=8):
    for rnd in rounds:
        g.round = rnd
        for _ in range(ticks):
            ex.tick(g.cash, rnd)
        g.cash += income


def test_lead_is_answered_before_round_28():
    g, ex = executor({}, towers=[("n1", "ninja", (2, 0, 1))], cash=2000)
    assert ex.due_threat(20) is None, "too early: nothing held yet"
    run_rounds(g, ex, range(24, 28))
    assert TH.covers(list(g.towers.values()), sig("lead"))[0]
    # the cheapest Hard lead answer: a $405 Bomb Shooter or an upgrade of n1 (0-0-3 is far dearer)
    lead_buys = [t for _, t in g.bought if "lead" in t]
    assert lead_buys and "bomb" in lead_buys[0], g.bought


def test_plan_is_followed_when_it_covers_cheaply():
    # (a plan that opens with a dart gets no extra opener tower)
    plan = [{"do": "place", "id": "d0", "kind": "dart", "role": "dps"},
            {"do": "place", "id": "a1", "kind": "alchemist", "role": "support", "near": ["d0"]}]
    g, ex = executor({"plan": plan}, towers=[("d0", "dart", (0, 0, 0)), ("n1", "ninja", (2, 0, 1))],
                     cash=600)
    run_rounds(g, ex, [25, 26])
    assert "a1" in g.towers and not any(t.startswith("place ans_") for _, t in g.bought), g.bought


def test_expensive_strategy_answer_gives_way_to_a_cheap_one():
    """minimal_sun_avatar: answers.lead = Flash Bomb ($2,430) arrived at R30, 2 rounds late."""
    strat = {"answers": {"lead": [{"do": "upgrade", "id": "n2", "to": "2-0-3"}]}}
    g, ex = executor(strat, towers=[("n1", "ninja", (2, 0, 1)), ("n2", "ninja", (2, 0, 2))], cash=600)
    run_rounds(g, ex, range(25, 28))
    assert TH.covers(list(g.towers.values()), sig("lead"))[0], g.bought


def test_mode_and_constraints_limit_the_answers():
    g, ex = executor({}, mode="magic_only", towers=[("n1", "ninja", (2, 0, 1))], cash=5000)
    run_rounds(g, ex, [26])
    kinds = {p.kind for p in g.towers.values()}
    assert kinds <= {"ninja", "wizard", "super", "alchemist", "druid"}, kinds
    assert TH.covers(list(g.towers.values()), sig("lead"))[0]
    g, ex = executor({"constraints": {"forbidden_towers": ["bomb", "alchemist"]}},
                     towers=[("n1", "ninja", (2, 0, 1))], cash=5000)
    run_rounds(g, ex, [26])
    assert not {"bomb", "alchemist"} & {p.kind for p in g.towers.values()}


def test_tower_cap_means_upgrades_only():
    strat = {"constraints": {"max_towers_on_screen": 1}}
    g, ex = executor(strat, towers=[("n1", "ninja", (2, 0, 1))], cash=9000)
    run_rounds(g, ex, [26])
    assert list(g.towers) == ["n1"] and g.towers["n1"].tiers[2] >= 3, g.towers["n1"].tiers


def test_chimps_never_buys_income_and_answers_ddts():
    g, ex = executor({}, mode="chimps", towers=[("s1", "sniper", (4, 0, 0)), ("n1", "ninja", (0, 0, 0))],
                     cash=20000)
    run_rounds(g, ex, range(85, 90))
    towers = list(g.towers.values())
    assert TH.covers(towers, sig("ddt"))[0], g.bought
    assert not any(p.kind == "farm" or (p.kind == "buccaneer" and p.tiers[2] >= 3) for p in towers)


def test_no_answers_constraint_buys_nothing():
    g, ex = executor({"constraints": {"no_answers": True}}, towers=[("n1", "ninja", (0, 0, 0))], cash=9000)
    run_rounds(g, ex, range(24, 30))
    assert not g.bought and not ex.hold_round(28, 9000)


def test_hold_round_only_while_an_answer_is_affordable():
    g, ex = executor({}, towers=[("n1", "ninja", (2, 0, 1))], cash=100)
    assert not ex.hold_round(28, 100), "nothing affordable: waiting earns nothing"
    assert ex.hold_round(28, 1000), "a $405 bomb is affordable: buy it before Play"
    ex.hold_since[28] = time.time() - ex.HOLD_MAX_S - 1
    assert not ex.hold_round(28, 1000), "never stall a game"
    g.towers["b1"] = Placed("b1", "bomb", 0.5, 0.5, [0, 0, 2])
    assert not ex.hold_round(29, 1000), "covered: nothing to wait for"


def test_saved_cash_is_not_spent_on_surplus():
    g, ex = executor({}, towers=[("n1", "ninja", (2, 0, 1))], cash=300)
    ex.tick(300, 26)
    assert ex.saving_for_threat and ex.surplus(300, 26) is False


def test_plan_blimp_step_keeps_its_cash():
    """Spillway ABR (2026-11-04): round 40's MOAB was rated short and the
    plan's next step (a $6,805 Maim MOAB sniper) was the answer, but idle
    spending ate the cash for it. Now its cash is held when it can be paid
    in time; a step too dear to arrive in time holds nothing back."""
    plan = [{"do": "upgrade", "id": "s1", "to": "4-2-0"}]
    load = TH.round_blimp_load("standard", 40, double_hp=True)
    towers = [("s1", "sniper", (3, 2, 0)), ("n1", "ninja", (2, 0, 1))]
    g, ex = executor({"plan": plan}, towers=towers, cash=5000)
    ex.rules["tough_moabs"] = True       # Double HP: a MOAB the 3-2-0 cannot stop
    ex.tick(5000, 38)
    assert g.towers["s1"].tiers[0] == 3, "not affordable yet - two rounds of income make it"
    assert ex.saving_for_threat and ex.surplus(5000, 38) is False, ex.waiting
    # too dear to arrive in time: holding the cash would only strand it
    g, ex = executor({"plan": plan}, towers=towers, cash=1000)
    ex.rules["tough_moabs"] = True
    ex._init_threats()
    ex.cash_seen = 1000
    assert ex._answer_ramp(*ex._ramp_due(38), 1000, 38) == "plan"
    # a plan step that adds no blimp damage is not a ramp step
    assert ex._plan_ramp_cost({"do": "upgrade", "id": "n1", "to": "2-0-2"}, load) is None
    assert ex._plan_ramp_cost(plan[0], load) == T.upgrade_cost("sniper", 1, 4, "hard")


def test_far_short_blimp_round_does_not_wait_on_a_weak_plan_step():
    """#Ouch Double HP (2026-11-07): round 40's MOAB was rated 0.2x from
    round 37, and the plan's next step - a Bloonjitsu ninja (n1 -> 4-0-2),
    which adds only a little MOAB damage - counted as the blimp step, so
    all the cash was held for it until round 39. Far short of the bar, a
    step that closes less than half of the shortfall loses its turn and
    blimp damage is bought (or saved for) at once."""
    plan = [{"do": "upgrade", "id": "n1", "to": "4-0-2"}]
    towers = [("n1", "ninja", (3, 0, 2)), ("n2", "ninja", (3, 0, 2))]
    g, ex = executor({"plan": plan}, towers=towers, cash=3000)
    ex.rules["tough_moabs"] = True       # Double HP MOABs
    ex._init_threats()
    ex.cash_seen = 3000
    R, load, ratio = ex._ramp_due(37)
    assert R == 40 and ratio < ex.RAMP_PANIC, ratio
    short = (ex.ramp_bar(load) - ratio) * load["hp"]
    assert ex._plan_step_too_weak(plan[0], load, ratio, short), ex._plan_ramp_gain(plan[0], load)
    assert ex._answer_ramp(R, load, ratio, 3000, 37) in ("bought", "wait"), g.bought
    # not far short: the plan keeps its turn as before
    assert not ex._plan_step_too_weak(plan[0], load, ex.RAMP_PANIC, short)


def test_round_before_blimps_buys_damage_over_other_plan_steps():
    """Spillway Medium (2026-11-04): round 40's MOAB was rated 0.8x from
    round 37, the plan's next step was a heli the game kept refusing, and
    the MOAB leaked with $7,519 unspent. Two rounds ahead the plan still
    goes on, and the round before too while it is not stuck; once steps
    were set aside, blimp damage is bought instead."""
    plan = [{"do": "upgrade", "id": "n1", "to": "2-0-2"}]   # not blimp damage
    towers = [("s1", "sniper", (2, 2, 0)), ("n1", "ninja", (2, 0, 1))]
    g, ex = executor({"plan": plan}, towers=towers, cash=20000)
    ex.rules["tough_moabs"] = False      # normal MOAB HP: the 2-2-0 sniper is short, not hopeless
    ex._init_threats()
    ex.cash_seen = 20000
    R, load, ratio = ex._ramp_due(38)
    assert R == 40 and ex.RAMP_PANIC < ratio < ex.RAMP_OK, ratio   # short, like Spillway's 0.8x
    assert ex._answer_ramp(R, load, ratio, 20000, 38) == "plan"
    assert ex._answer_ramp(R, load, ratio, 20000, 39) == "plan", "not stuck: the plan goes on"
    ex.deferred.append({"do": "place", "id": "hel1", "kind": "heli", "role": "dps"})
    assert ex._answer_ramp(R, load, ratio, 20000, 38) == "plan", "two rounds ahead: still the plan"
    assert ex._answer_ramp(R, load, ratio, 20000, 39) == "bought", g.bought


def test_one_life_buys_blimp_damage_two_rounds_ahead():
    """Spring Spring Impoppable (2026-11-04): round 40's MOAB was rated 0.5x
    from round 37, the plan's next step (a ninja 2-0-4) added no blimp damage
    and was not stuck, so it kept its turn and the MOAB leaked the only life
    with $5,672 saved for it. With one life the plan's last turn is two rounds
    before the blimps, stuck or not, and the check looks further ahead."""
    plan = [{"do": "upgrade", "id": "n1", "to": "2-0-2"}]   # not blimp damage
    towers = [("s1", "sniper", (2, 2, 0)), ("n1", "ninja", (2, 0, 1))]
    g, ex = executor({"plan": plan}, towers=towers, cash=20000)
    ex.rules.update(tough_moabs=False, one_life=True)
    ex._init_threats()
    ex.cash_seen = 20000
    assert ex._ramp_due(35) and ex._ramp_due(35)[0] == 40, "one life: five rounds of warning"
    R, load, ratio = ex._ramp_due(37)
    assert R == 40 and ex.RAMP_PANIC < ratio < ex.RAMP_OK, ratio
    assert ex._answer_ramp(R, load, ratio, 20000, 37) == "plan", "three rounds ahead: the plan goes on"
    assert ex._answer_ramp(R, load, ratio, 20000, 38) == "bought", g.bought


def test_half_cash_blimp_check_looks_twice_as_far():
    """Another Brick / X Factor / Pat's Pond Half Cash (2026-11-06): round
    40's MOAB was first checked from round 37, and three rounds of half
    income could not pay for the MOAB answer. With half the income the check
    looks twice as far ahead (MIN_LEAD 3 -> 6), never past MAX_LEAD."""
    towers = [("s1", "sniper", (2, 2, 0)), ("n1", "ninja", (2, 0, 1))]
    g, ex = executor({}, towers=towers, cash=500)
    # a copy: the fixture's rules dict is shared, and earlier tests leave
    # one_life set in it
    ex.rules = dict(ex.rules, tough_moabs=False, one_life=False, half_cash=False)
    ex._init_threats()
    ex.cash_seen = 500
    assert ex._ramp_lead() == ex.MIN_LEAD
    # Ravine Magic Only / Pat's Pond ABR (2026-11-10): the damage model rated
    # round 40 at 0.06-0.15 for six rounds. Only then is the first blimp
    # round looked at twice as early; a model rating of 0.5 keeps the plain lead.
    ex.rules["start_round"] = 22      # both were Fast Track starts
    ex._init_threats()
    ex.cash_seen = 500
    ex._rated = lambda key, rnd, fn: (0.5,)
    assert ex._ramp_due(34) is None, "the model does not call round 40 hopeless: plain lead"
    ex._rated = lambda key, rnd, fn: (0.06,)
    assert ex._ramp_due(33) is None, "round 40 is seven rounds away, not yet checked"
    due = ex._ramp_due(34)
    assert due and due[0] == 40, "round 40, the first blimp round, is checked twice as early"
    del ex._rated
    # a later blimp round keeps the plain lead of MIN_LEAD rounds
    second = next(R for R in range(41, 81) if ex.blimp_load(R))
    assert ex._ramp_lead_for(second) == ex.MIN_LEAD
    assert ex._ramp_lead_for(40) == 2 * ex.MIN_LEAD
    ex.rules["start_round"] = 3       # a full Hard game has 37 rounds to grow: plain lead
    ex._init_threats()
    assert ex._ramp_lead_for(40) == ex.MIN_LEAD
    ex.rules["half_cash"] = True
    ex._init_threats()
    ex.cash_seen = 500
    assert ex._ramp_lead() == 2 * ex.MIN_LEAD
    due = ex._ramp_due(34)
    assert due and due[0] == 40, "half income: round 40 is checked from round 34"
    ex.rules["one_life"] = True
    assert ex._ramp_lead() == ex.MAX_LEAD, "one life and half cash: capped at MAX_LEAD"


def test_continuous_blimp_load_sums_overlapping_rounds():
    """#Ouch and Firing Range Apopalypse (2026-11-06): four MOABs were on
    screen at once at round 47 and 121-150 lives went in under 10 s, while
    the blimp check rated round 50's two MOABs alone at 6.4x and 8.7x.
    Under continuous sends rounds pass every ~2.5 s, so round 50's MOABs
    share an 886-unit track (Firing Range) with those of rounds 52-55."""
    single = TH.round_blimp_load("standard", 50)
    both = TH.continuous_blimp_load("standard", 50, 886.0, end_round=60)
    assert both["rounds"][0] == 50 and {52, 53, 54, 55} <= set(both["rounds"]), both
    assert both["hp"] == sum(TH.round_blimp_load("standard", r)["hp"] for r in both["rounds"])
    assert both["hp"] >= 4 * single["hp"]
    assert TH.continuous_blimp_load("standard", 49, 886.0) is None, "no blimps of its own"
    # a short track: one crossing (100 / 25 = 4 s) covers rounds 50 and 51 only
    assert TH.continuous_blimp_load("standard", 50, 100.0)["rounds"] == [50]
    last = max(r for r in range(50, 61) if TH.round_blimp_load("standard", r))
    assert TH.continuous_blimp_load("standard", last, 886.0, end_round=60)["rounds"][-1] <= 60, \
        "never past the mode's last round"

    towers = [("s1", "sniper", (4, 2, 0)), ("n1", "ninja", (4, 0, 2))]
    g, ex = executor({}, mode="apopalypse", towers=towers, cash=500)
    ex._init_threats()
    ex.track_len = 886.0
    apop = ex.blimp_ratio(ex.blimp_load(50))
    alone = ex.blimp_ratio(TH.round_blimp_load(ex.round_set, 50))
    assert apop < alone / 2, (apop, alone)
    _, hard = executor({}, mode="hard", towers=towers, cash=500)
    hard._init_threats()
    assert hard.blimp_load(50) == TH.round_blimp_load(hard.round_set, 50), "standard modes: one round"


class _Forecast:
    """A damage model that rates every round at one margin."""

    def __init__(self, margin):
        self.margin = margin

    def worst(self, towers, rounds):
        return self.margin, rounds[0]


def _one_life_at_37(margin):
    """The one-life board of the test above at round 37, with a damage model
    rating every round at `margin`."""
    plan = [{"do": "upgrade", "id": "n1", "to": "2-0-2"}]
    towers = [("s1", "sniper", (2, 2, 0)), ("n1", "ninja", (2, 0, 1))]
    g, ex = executor({"plan": plan}, towers=towers, cash=20000)
    ex.rules.update(tough_moabs=False, one_life=True)
    ex._init_threats()
    ex.cash_seen = 20000
    ex.forecast = _Forecast(margin)
    return g, ex


def test_the_blimp_check_gives_way_when_the_damage_model_holds_the_round():
    """CHIMPS map builds (2026-11-05): the blimp check called rounds 75-99
    short where the damage model gave 16, bought loose towers and starved the
    plan's last big step. When the model rates the blimp round at
    model_bar or more (as sure as it was there: 16), no blimp damage is due."""
    g, ex = _one_life_at_37(16.0)
    load = TH.round_blimp_load(ex.round_set, 40)
    assert ex.blimp_ratio(load) < ex.ramp_bar(load), "the rough check alone calls round 40 short"
    assert ex._ramp_due(37) is None, "the model holds round 40: nothing is due"
    assert not ex.weak_now(39), "nor is round 40 weak for the cash holds"


def test_a_lukewarm_model_does_not_overrule_a_far_short_blimp_check():
    """Dark Castle Impoppable and Mushroom Grotto Reverse (2026-11-06): the
    blimp check read 0.2x and 0.6x, the damage model 2.18 and 2.28 - just over
    RAMP_MODEL_SAFE - and the check gave way; both round-40 MOABs leaked. The
    further short the check reads, the surer the model must be."""
    ex = _one_life_at_37(2.18)[1]
    assert ex.model_bar(0.2, 1.4) > 2.28 and ex.model_bar(0.6, 1.4) > 2.28
    assert ex.model_bar(0.17, 1.4) < 16, "the CHIMPS case (model 16) still overrules"
    assert ex.model_bar(1.4, 1.4) == ex.RAMP_MODEL_SAFE, "at the bar: the plain threshold"
    load = TH.round_blimp_load(ex.round_set, 40)
    ratio, bar = ex.blimp_ratio(load), ex.ramp_bar(load)
    if ex.model_bar(ratio, bar) > 2.18:
        assert ex._ramp_due(37) is not None, "the check stands: blimp damage is due for round 40"


def test_the_blimp_check_stands_where_the_damage_model_is_unsure():
    """Cargo Impoppable (2026-11-05): the model gave round 94 0.66 and the
    blimp check rightly called it short. Under RAMP_MODEL_SAFE it still buys."""
    g, ex = _one_life_at_37(S.Executor.RAMP_MODEL_SAFE - 0.5)
    R, load, ratio = ex._ramp_due(37)
    assert R == 40
    assert ex._answer_ramp(R, load, ratio, 20000, 38) == "bought", g.bought


def test_every_strategy_pops_every_bloon_in_time():
    """Each general strategy, in each mode it lists, played with the game's own
    income (no Double Cash, no farms counted): no round may bring a bloon the
    defence cannot pop at that moment."""
    games = [(sid, mode) for sid, s in sorted(S.load_all().items())
             if not s.get("achievement") and s.get("bot_ready", True)
             for mode in s.get("modes", []) if mode != "apopalypse"]
    # The games do not depend on each other and each takes seconds of the
    # damage model: one after another they had grown to 25 minutes of one
    # core (2026-11-11), longer than the rest of tools/check.py together.
    with ProcessPoolExecutor(max_workers=GAME_WORKERS) as pool:
        gaps = [gap for found in pool.map(_gaps_of_game, games, chunksize=4) for gap in found]
    assert not gaps, gaps[:10]


# Worker processes for test_every_strategy_pops_every_bloon_in_time: a
# quarter of the cores, so tools/check.py's other steps and the live bot
# keep theirs.
GAME_WORKERS = max(2, (os.cpu_count() or 4) // 4)
_WORKER_STRATS = None       # a worker's own copy of strategy.load_all()


def _gaps_of_game(game):
    """[(strategy id, mode, round, bloon need, how)] for one simulated game
    of strategy `sid` in `mode` - the rounds that bring a bloon the defence
    cannot pop at that moment. Runs in a worker process, which loads the
    strategies itself, once (_WORKER_STRATS)."""
    global _WORKER_STRATS
    if _WORKER_STRATS is None:
        _WORKER_STRATS = S.load_all()
    sid, mode = game
    s = _WORKER_STRATS[sid]
    # an optimized build is played as it was planned: its Fast Track
    # start and Double Cash income (strategies/optimized, docs/optimizer.md)
    scenario = (s.get("optimizer") or {}).get("scenario") if s.get("source") == "optimized" else None
    r = SIM.simulate(s, mode, ticks=8, scenario=scenario)
    return [(sid, mode, rnd, need, how) for rnd, need, how in r["gaps"]]


def test_ramp_passes_over_an_answer_it_cannot_finish():
    """Sunset Gulch Impoppable (2026-11-10 15:13): the MOAB answer "n2 ->
    2-0-4" became a fresh ninja (n2 popped nothing) and the ramp bought it
    to 2-0-3 for $4,830 at round 39 while its ace stood at 0-0-0; the MOAB
    took the one life with $4,321 in hand. An answer that cannot be paid
    in full before the blimps is passed over for blimp damage that can."""
    answers = {"moab": [{"do": "upgrade", "id": "n2", "to": "2-0-4"}]}
    towers = [("s1", "sniper", (2, 2, 0)), ("n1", "ninja", (2, 0, 1)), ("n2", "ninja", (2, 0, 1))]
    g, ex = executor({"plan": [], "answers": answers}, towers=towers, cash=2500)
    ex.rules.update(tough_moabs=False, one_life=True)
    ex._init_threats()
    ex.cash_seen = 2500
    R, load, ratio = ex._ramp_due(39)
    assert R == 40, R
    assert ex._steps_cost(answers["moab"]) > 2500 + 2 * 1000
    ex._answer_ramp(R, load, ratio, 2500, 39)
    assert tuple(g.towers["n2"].tiers) == (2, 0, 1), "the unaffordable answer is not started"
    # an answer that can be paid in time is still bought first
    g, ex = executor({"plan": [], "answers": answers}, towers=towers, cash=20000)
    ex.rules.update(tough_moabs=False, one_life=True)
    ex._init_threats()
    ex.cash_seen = 20000
    assert ex._answer_ramp(*ex._ramp_due(39), 20000, 39) == "bought"
    assert g.towers["n2"].tiers[2] >= 2, g.towers["n2"].tiers


def test_a_held_blimp_round_does_not_hide_a_short_one_behind_it():
    """Spillway Impoppable (2026-11-10 15:43): on round 79 the blimp check
    rated round 79 (2.2x) and stopped; round 80's ZOMG (1.1x of 1.4x) was
    first seen as it began and took the one life with $18,870 in hand. The
    check now looks past a round the defence holds."""
    g, ex = executor({"plan": []}, towers=[("s1", "sniper", (2, 2, 0))], cash=5000)
    ex.rules.update(one_life=True)
    ex._init_threats()
    loads = {39: {"hp": 12000, "rounds": [39]}, 40: {"hp": 10000, "rounds": [40]}}
    ratios = {12000: 2.2, 10000: 1.1}
    ex.blimp_load = lambda R: loads.get(R)
    ex.blimp_ratio = lambda load: ratios[load["hp"]]
    ex.ramp_bar = lambda load: 1.4
    ex._model_holds = lambda *a: False
    ex._held_round_weak = lambda R, rnd: False   # live, the model rated Spillway's round 79 at 1.35
    ex._ramp_lead_for = lambda R: 5
    ex._ramp_lead = lambda: 5
    due = ex._ramp_due(38)
    assert due is not None and due[0] == 40, due
    ratios[10000] = 1.6                     # both held: the first is reported, as before
    ex.noted.discard(("ramp", 40))
    assert ex._ramp_due(38)[0] == 39


def test_a_held_blimp_round_the_model_calls_weak_is_not_looked_past():
    """Bazaar Half Cash (build replay, 2026-11-10): looking past held round
    78 to the short rounds 79-80 drew the cash forward and round 78 fell from
    0.53 to 0.39 in the damage model. A held round the model rates under 1 is
    reported and the check stops there."""
    g, ex = executor({"plan": []}, towers=[("s1", "sniper", (2, 2, 0))], cash=5000)
    ex._init_threats()
    loads = {39: {"hp": 12000, "rounds": [39]}, 40: {"hp": 10000, "rounds": [40]}}
    ratios = {12000: 2.2, 10000: 1.1}
    ex.blimp_load = lambda R: loads.get(R)
    ex.blimp_ratio = lambda load: ratios[load["hp"]]
    ex.ramp_bar = lambda load: 1.4
    ex._model_holds = lambda *a: False
    ex._ramp_lead_for = lambda R: 5
    ex._ramp_lead = lambda: 5
    ex._held_round_weak = lambda R, rnd: R == 39
    assert ex._ramp_due(38)[0] == 39
    ex._rated = lambda what, rnd, rate: None    # no forecast: the held round counts as holding
    del ex._held_round_weak
    ex.noted.clear()
    assert ex._ramp_due(38)[0] == 40


def test_one_life_wants_a_wider_blimp_margin():
    """Bloonarius Prime Impoppable (2026-11-10 17:04): round 75's seven BFBs
    were checked at 2.0x, over the 1.4x bar, and one got through. With one
    life the bar is RAMP_OK_ONE_LIFE; other modes keep theirs."""
    load = {"hp": 11700, "leak": 5000}
    g, ex = executor({"plan": []}, mode="medium", towers=[("s1", "sniper", (2, 2, 0))], cash=5000)
    assert ex.ramp_bar(load) == ex.RAMP_OK_LETHAL
    g, ex = executor({"plan": []}, mode="impoppable", towers=[("s1", "sniper", (2, 2, 0))], cash=5000)
    assert ex.ramp_bar(load) == ex.RAMP_OK_ONE_LIFE > 2.0


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # report every failure, then fail the run
                failed += 1
                print("FAIL", name, repr(e)[:400])
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
