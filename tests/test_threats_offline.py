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
import random
import sys
import time
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


def test_every_strategy_pops_every_bloon_in_time():
    """Each general strategy, in each mode it lists, played with the game's own
    income (no Double Cash, no farms counted): no round may bring a bloon the
    defence cannot pop at that moment."""
    strats = S.load_all()
    gaps = []
    for sid, s in sorted(strats.items()):
        if s.get("achievement") or not s.get("bot_ready", True):
            continue
        for mode in s.get("modes", []):
            if mode == "apopalypse":
                continue
            r = SIM.simulate(s, mode, ticks=8)
            gaps += [(sid, mode, rnd, need, how) for rnd, need, how in r["gaps"]]
    assert not gaps, gaps[:10]


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
