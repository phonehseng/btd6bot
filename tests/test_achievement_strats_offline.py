"""Offline tests for achievement strategies (strategies/achievements/*.yaml) and the
constraint enforcement in btd6bot.strategy (load_all / usable / hero_for / Executor).
Run: python tests/test_achievement_strats_offline.py (also collectable by pytest).
Uses a fake game and map model; never touches the game, mouse or keyboard."""

from __future__ import annotations

import sys
from pathlib import Path

import logging

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402

logging.getLogger("strategy").setLevel(logging.ERROR)

READY = {
    "ach_abracadabmonkey", "ach_all_for_one_and_one_for_one", "ach_big_bloons",
    "ach_bloons_master", "ach_chunky_monkeys", "ach_first_monkeys_first",
    "ach_role_reverser", "ach_so_spiiicey_ninja_kiwi", "ach_unsung_monkeys", "ach_war_monkeys",
}
SAFETY = {"ach_living_on_the_edge", "ach_snap_of_your_fingers"}


# -- fakes ----------------------------------------------------------------------------
class Placed:
    def __init__(self, tid, kind, x, y):
        self.tid, self.kind, self.x, self.y = tid, kind, x, y
        self.tiers = [0, 0, 0]


class FakeScreen:
    width = 1920


class FakeGame:
    def __init__(self, hero="quincy"):
        self.hero = hero
        self.towers = {}
        self.s = FakeScreen()
        self.fail_reason = None
        self.locked_seen = None
        self.placed = []     # every kind ever placed (sold ones too)
        self.sold = []

    def price(self, kind):
        return 500 if kind == "hero" else T.TOWERS[kind]["cost"]

    def place(self, tid, kind, fx, fy, check_valid=True):
        self.towers[tid] = Placed(tid, kind, fx, fy)
        self.placed.append(kind)
        return True

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        p.tiers[path - 1] += 1
        return True

    def target(self, p, mode):
        return True

    def sell(self, p):
        self.sold.append(p.kind)
        self.towers.pop(p.tid, None)
        return True


class FakeModel:
    W, H = 100, 60

    def __init__(self):
        self.heat = np.zeros((self.H, self.W), np.float32)

    def frac_to_cell(self, x, y):
        return int(x * self.W), int(y * self.H)

    def cell_to_frac(self, cx, cy):
        return (cx + 0.5) / self.W, (cy + 0.5) / self.H

    def radius_cells(self, rng, width):
        return 5

    def score_spots(self, rc, seg, occupied, near=None, near_radius=None, placement="land",
                    extra_block=None, covered=None):
        self.last_placement = placement
        cover = np.ones((self.H, self.W), np.float32)
        if extra_block is not None:
            cover[extra_block] = 0
        return cover

    def best_spots(self, cover, n=12):
        idx = np.argsort(-cover, axis=None)[:n]
        return [(int(i % self.W), int(i // self.W), float(cover.flat[i])) for i in idx
                if cover.flat[i] > 0]


def full_account(heroes=None):
    a = AccountState()
    a.unlocked_towers = set(T.TOWERS)
    a.unlocked_heroes = set(T.HEROES) if heroes is None else set(heroes)
    a.unlocked_upgrades = {k: [5, 5, 5] for k in T.TOWERS}
    return a


def run(strat, mode="easy", hero="quincy", account=None, rounds=range(1, 101), ticks=6,
        cash=10 ** 7, panic_every=1):
    """Tick the executor through rounds with plenty of cash and a life lost every round."""
    g = FakeGame(hero)
    ex = S.Executor(g, FakeModel(), strat, mode, account)
    for i, rnd in enumerate(rounds):
        for t in range(ticks):
            ex.tick(cash, rnd, lives_dropped=(t == 0 and i % panic_every == 0))
    return g, ex


# -- loading -----------------------------------------------------------------------------
def test_all_achievement_yamls_load():
    files = sorted(S.ACH_DIR.rglob("*.yaml"))
    strats = S.load_all()
    ach = {sid: s for sid, s in strats.items() if s.get("achievement")}
    assert len(files) == 20 and len(ach) == len(files), (len(files), len(ach))
    top = {f.stem for f in S.STRAT_DIR.glob("*.yaml")}
    assert not (top & set(ach)), "achievement ids collide with general strategies"
    for sid, s in ach.items():
        assert s["source"] == "achievements"
        assert isinstance(s["bot_ready"], bool)
        assert S.validate(s) == [], (sid, S.validate(s))  # crosspaths, kinds, ids
        for mode in s.get("modes", []):
            assert mode in S.MODE_RULES, (sid, mode)
    for sid, s in strats.items():
        if not s.get("achievement"):
            assert s["bot_ready"] is True and S.validate(s) == [], (sid, S.validate(s))


def test_bot_ready_set_and_safety():
    strats = S.load_all()
    ready = {sid for sid, s in strats.items() if s.get("achievement") and s["bot_ready"]}
    assert ready == READY, sorted(ready ^ READY)
    for sid in SAFETY:
        assert any(r.startswith("SAFETY") for r in strats[sid]["bot_ready_reasons"]), sid
    acct = full_account()
    for sid, s in strats.items():
        if s.get("achievement") and not s["bot_ready"]:
            for m in s.get("modes", []):
                ok, why = S.usable(s, m, acct, allow_achievement=True)
                assert not ok and why.startswith("not bot-ready"), (sid, m, why)


def test_crosspath_validation_catches_bad_plans():
    bad = {"modes": ["easy"], "plan": [
        {"do": "place", "id": "t1", "kind": "tack"},
        {"do": "upgrade", "id": "t1", "to": "3-3-0"},
        {"do": "upgrade", "id": "t1", "to": "1-0-1"}, {"do": "upgrade", "id": "t1", "to": "0-2-0"},
        {"do": "upgrade", "id": "zz", "to": "1-0-0"}]}
    probs = " | ".join(S.validate(bad))
    assert "illegal crosspath 3-3-0" in probs and "3-3-1" in probs and "zz" in probs, probs


def test_achievement_strategies_not_general_purpose():
    strats = S.load_all()
    acct = full_account()
    for sid, s in strats.items():
        if s.get("achievement"):
            for m in s.get("modes", []):
                assert not S.usable(s, m, acct)[0], (sid, m)
    from unittest import mock

    from btd6bot import runner  # import only; nothing is instantiated
    # every achievement already complete -> no achievement plan is offered
    done = {s["achievement"]: {"status": "complete"} for s in strats.values() if s.get("achievement")}
    with mock.patch.object(runner.Achievements, "load", staticmethod(lambda: done)):
        ids = {sp.id for sp in runner.planner_specs(strats, acct)}
    assert not {i for i in ids if strats[i].get("achievement")}, ids
    assert "primary_core" in ids
    # nothing complete -> bot-ready achievement plans are offered, the others never
    with mock.patch.object(runner.Achievements, "load", staticmethod(lambda: {})):
        ids = {sp.id for sp in runner.planner_specs(strats, acct)}
    offered = {i for i in ids if strats[i].get("achievement")}
    assert offered and all(strats[i].get("bot_ready") for i in offered), offered


def test_usable_when_targeted_and_map_pinned():
    strats = S.load_all()
    acct = full_account()
    bm = strats["ach_bloons_master"]
    assert S.usable(bm, "chimps", acct, allow_achievement=True)[0]
    assert S.usable(bm, "chimps", acct, map_name="logs", allow_achievement=True)[0]
    ok, why = S.usable(bm, "chimps", acct, map_name="Resort", allow_achievement=True)
    assert not ok and "Logs" in why
    assert bm["planner"]["maps"] == ["Logs"]
    fm = strats["ach_first_monkeys_first"]  # map: null -> any map
    assert S.usable(fm, "easy", acct, map_name="Resort", allow_achievement=True)[0]


def test_achievement_strategies_wanted():
    strats = S.load_all()
    cards = {"First Monkeys First": {"status": "progress"}, "War Monkeys": {"status": "complete"},
             "Bloons Master": {"status": "collect"}}
    want = S.achievement_strategies(strats, cards)
    assert "ach_first_monkeys_first" in want
    assert "ach_war_monkeys" not in want and "ach_bloons_master" not in want
    assert "ach_living_on_the_edge" not in want  # never bot-ready


# -- hero constraints -----------------------------------------------------------------------
def test_required_hero():
    strats = S.load_all()
    bb = strats["ach_big_bloons"]
    no_pat = full_account(heroes={"quincy", "obyn"})
    ok, why = S.usable(bb, "easy", no_pat, allow_achievement=True)
    assert not ok and "pat_fusty" in why
    assert S.usable(bb, "easy", full_account(), allow_achievement=True)[0]
    assert S.hero_for(bb, full_account()) == "pat_fusty"
    # equipped hero is not the required one -> never placed
    g, _ = run(bb, "easy", hero="quincy", account=full_account(), rounds=range(1, 30))
    assert "hero" not in g.placed
    g, _ = run(bb, "easy", hero="pat_fusty", account=full_account(), rounds=range(1, 30))
    assert "hero" in g.placed


def test_place_hero_false_never_places_hero():
    strat = {"id": "x", "modes": ["easy"], "hero": "quincy",
             "constraints": {"place_hero": False},
             "plan": [{"do": "place", "id": "hero", "kind": "hero"},
                      {"do": "place", "id": "t1", "kind": "tack"}],
             "fill": [{"do": "place", "kind": "hero"}, {"do": "place", "kind": "dart", "max": 3}],
             "panic": [{"do": "place", "kind": "hero"}],
             "answers": {"camo": [{"do": "place", "kind": "hero"}]}}
    for c in ({"place_hero": False}, {"hero_allowed": False}):
        strat["constraints"] = c
        g, ex = run(strat, "easy", account=full_account())
        assert "hero" not in g.placed and "tack" in g.placed, (c, g.placed)
        assert not ex.hero_ok
    for sid in ("ach_2_megapops", "ach_all_for_one_and_one_for_one"):
        s = S.load_all()[sid]
        g, _ = run(s, s["modes"][0], hero="quincy", account=full_account())
        assert "hero" not in g.placed, sid


def test_allowed_and_forbidden_heroes():
    ch = S.load_all()["ach_chunky_monkeys"]
    assert S.hero_for(ch, full_account()) == "pat_fusty"
    assert S.hero_for(ch, full_account(heroes={"quincy", "churchill"})) == "churchill"
    assert S.hero_for(ch, full_account(heroes={"quincy"})) == "quincy"  # equipped, never placed
    g, _ = run(ch, "medium", hero="quincy", account=full_account(), rounds=range(1, 61))
    assert "hero" not in g.placed
    g, _ = run(ch, "medium", hero="churchill", account=full_account(), rounds=range(1, 61))
    assert "hero" in g.placed
    allowed = set(ch["constraints"]["allowed_towers"])
    assert set(g.placed) - {"hero"} <= allowed, g.placed
    sp = S.load_all()["ach_so_spiiicey_ninja_kiwi"]
    assert S.hero_for(sp, full_account(heroes={"admiral_brickell", "quincy"})) == "quincy"
    g, _ = run(sp, "abr", hero="admiral_brickell", account=full_account(), rounds=range(3, 81))
    assert "hero" not in g.placed


# -- tower constraints ---------------------------------------------------------------------
def test_primary_only_constraint_never_places_sniper():
    strat = {"id": "x", "modes": ["easy"], "hero": "quincy",
             "constraints": {"allowed_towers": ["dart", "boomerang", "bomb", "tack", "ice",
                                                "glue", "desperado"]},
             "plan": [{"do": "place", "id": "s1", "kind": "sniper"},
                      {"do": "place", "id": "t1", "kind": "tack"}],
             "fill": [{"do": "place", "kind": "sniper", "max": 4}, {"do": "place", "kind": "dart", "max": 4}],
             "panic": [{"do": "place", "kind": "sniper", "role": "exit"}],
             "answers": {"camo": [{"do": "place", "id": "s2", "kind": "sniper"}],
                         "moab": [{"do": "place", "kind": "heli"}]}}
    g, ex = run(strat, "easy", account=full_account())
    assert "sniper" not in g.placed and "heli" not in g.placed, g.placed
    assert "tack" in g.placed
    # every sniper panic step was filtered -> default panic is a primary tower
    assert [st["kind"] for st in ex.panic_steps] == ["tack"]
    for sid in ("ach_first_monkeys_first", "ach_war_monkeys", "ach_abracadabmonkey",
                "ach_unsung_monkeys", "ach_chunky_monkeys"):
        s = S.load_all()[sid]
        allowed = set(s["constraints"]["allowed_towers"])
        for mode in s["modes"]:
            r = range(S.rules(mode)["start_round"], S.rules(mode)["end_round"] + 1)
            g, ex = run(s, mode, hero=s.get("hero") or "quincy", account=full_account(), rounds=r)
            bad = set(g.placed) - allowed - {"hero"}
            assert not bad, (sid, mode, bad)
            assert all(st["kind"] in allowed or st["kind"] == "hero" for st in ex.panic_steps
                       if st.get("do") == "place"), (sid, ex.panic_steps)


def test_default_panic_respects_constraints():
    base = {"id": "x", "modes": ["easy", "military_only"], "plan": [{"do": "place", "kind": "dart"}]}
    acct = full_account()
    ex = S.Executor(FakeGame(), FakeModel(), dict(base), "easy", acct)
    assert [s["kind"] for s in ex.panic_steps] == ["tack"]
    ex = S.Executor(FakeGame(), FakeModel(), dict(base, constraints={"no_default_panic": True}),
                    "easy", acct)
    assert ex.panic_steps == []
    ex = S.Executor(FakeGame(), FakeModel(), dict(base, constraints={"allowed_towers": ["sniper", "dart"]}),
                    "easy", acct)
    assert [s["kind"] for s in ex.panic_steps] == ["dart"]
    ex = S.Executor(FakeGame(), FakeModel(), dict(base, constraints={"allowed_towers": ["heli"]}),
                    "easy", acct)
    assert ex.panic_steps == []  # nothing allowed -> no panic rather than a forbidden tower
    ex = S.Executor(FakeGame(), FakeModel(), dict(base), "military_only", acct)
    assert [s["kind"] for s in ex.panic_steps] == ["sniper"]  # never a tack in Military Only
    # no_default_panic with an empty plan list keeps the strategy's own panic
    s = S.load_all()["ach_chunky_monkeys"]
    ex = S.Executor(FakeGame(), FakeModel(), s, "medium", acct)
    assert [st["kind"] for st in ex.panic_steps] == ["spike", "mortar"]
    s = S.load_all()["ach_all_for_one_and_one_for_one"]
    ex = S.Executor(FakeGame(), FakeModel(), s, "hard", acct)
    assert ex.panic_steps == [] and ex.due_threat(40) is None


def test_max_towers_on_screen_and_purchased():
    s = S.load_all()["ach_all_for_one_and_one_for_one"]
    g, ex = run(s, "hard", hero="quincy", account=full_account(), rounds=range(3, 81))
    assert g.placed == ["buccaneer"], g.placed
    assert g.towers["b1"].tiers == [0, 5, 2], g.towers["b1"].tiers
    strat = {"id": "x", "modes": ["easy"],
             "constraints": {"max_towers_purchased": 2, "no_default_panic": True},
             "plan": [{"do": "place", "id": "a", "kind": "dart"},
                      {"do": "sell", "id": "a"},
                      {"do": "place", "id": "b", "kind": "dart"},
                      {"do": "place", "id": "c", "kind": "dart"}],
             "fill": [{"do": "place", "kind": "tack", "max": 5}]}
    g, ex = run(strat, "easy", account=full_account())
    assert len(g.placed) == 2 and g.sold == ["dart"], (g.placed, g.sold)
    strat["constraints"] = {"max_towers_on_screen": 2, "no_default_panic": True}
    g, ex = run(strat, "easy", account=full_account())
    assert len(g.towers) == 2 and len(g.placed) == 3, (g.placed, g.towers)


def test_no_sell_no_income_land_only():
    strat = {"id": "x", "modes": ["easy"],
             "constraints": {"no_sell": True, "no_income_towers": True, "land_only": True,
                             "forbidden_towers": ["ace"]},
             "plan": [{"do": "place", "id": "f", "kind": "farm"},
                      {"do": "place", "id": "sub", "kind": "sub"},
                      {"do": "place", "id": "ace", "kind": "ace"},
                      {"do": "place", "id": "m", "kind": "mermonkey"},
                      {"do": "place", "id": "e", "kind": "engineer"},
                      {"do": "upgrade", "id": "e", "to": "0-0-4"},
                      {"do": "upgrade", "id": "e", "to": "0-0-3"},
                      {"do": "sell", "id": "m"}]}
    g = FakeGame()
    model = FakeModel()
    ex = S.Executor(g, model, strat, "easy", full_account())
    for _ in range(40):
        ex.tick(10 ** 7, 10)
    assert set(g.placed) == {"mermonkey", "engineer"}, g.placed
    assert g.sold == [] and "m" in g.towers
    assert g.towers["e"].tiers == [0, 0, 3]  # Bloon Trap (income) skipped
    assert model.last_placement == "land"    # amphibious tower kept on land


def test_usable_constraint_checks():
    acct = full_account()
    s = {"id": "x", "achievement": "X", "modes": ["easy", "medium"],
         "constraints": {"min_difficulty": "medium"}, "plan": [{"do": "place", "kind": "dart"}]}
    assert not S.usable(s, "easy", acct, allow_achievement=True)[0]
    assert S.usable(s, "medium", acct, allow_achievement=True)[0]
    s = {"id": "x", "modes": ["easy"], "constraints": {"land_only": True},
         "plan": [{"do": "place", "kind": "sub"}]}
    assert not S.usable(s, "easy", acct)[0]
    s = {"id": "x", "modes": ["easy"], "hero": "pat_fusty", "constraints": {"no_hero_fallback": True},
         "plan": [{"do": "place", "kind": "dart"}]}
    assert not S.usable(s, "easy", full_account(heroes={"quincy"}))[0]
    assert S.usable(s, "easy", acct)[0]
    a = S.load_all()["ach_all_for_one_and_one_for_one"]
    weak = full_account()
    weak.unlocked_upgrades["buccaneer"] = [0, 4, 2]
    ok, why = S.usable(a, "hard", weak, allow_achievement=True)
    assert not ok and "buccaneer" in why


def test_general_strategies_unchanged():
    """No constraints: same default panic, hero choice and plan as before."""
    strats = S.load_all()
    acct = full_account(heroes={"quincy"})
    pc = strats["primary_core"]
    assert S.hero_for(pc, acct) == "quincy"
    assert S.hero_for(strats["chimps_ninja_sun"], acct) == "quincy"
    ex = S.Executor(FakeGame(), FakeModel(), pc, "hard", acct)
    assert len(ex.plan) == len(pc["plan"]) and len(ex.fill) == len(pc["fill"])
    g, _ = run(pc, "hard", account=acct, rounds=range(3, 40))
    assert "hero" in g.placed and "tack" in g.placed


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
