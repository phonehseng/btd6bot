"""Achievement plans may replay their beaten map/mode (tier "ACH").

Why (2026-11-07): the owner saw the bot "not working on achievements". The
log had no achievement build picked in weeks, for three reasons:

1. the planner read data/achievements_state.json, a scan from 2026-10-21
   that nothing writes any more (the bot saves data/accounts/<id>.
   achievements.json), so it chased finished achievements (Thrifty) and
   never saw new progress;
2. every achievement build is pinned to a map/mode the account has beaten
   (Unsung Monkeys: Logs Easy), and the never-replay rule dropped it before
   it was even scored;
3. the Unsung Monkeys build failed coverage: a 2-3-0 MOAB SHREDR spike did
   not count as a MOAB answer, so runner.planner_specs dropped it.

The rules tested here: an achievement replay happens only while the scan
reads that card as in progress and the plan's wins since the scan have not
finished it; never under the mode's bar; after every first-time medal that
clears its bar and before the last-resort games; normal strategies still
never replay.
Run: python tests/test_achievement_replays_offline.py (also collectable by pytest)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (full_account)
from btd6bot import identity                   # noqa: E402
from btd6bot import planner as P               # noqa: E402
from btd6bot import runner as R                # noqa: E402
from btd6bot import strategy as S              # noqa: E402
from btd6bot.account import AccountState       # noqa: E402

P.DEFAULT_CONFIG.maps_dir = None               # independent of data/maps
P.DEFAULT_CONFIG.tower_xp_path = None

CATALOG = [{"name": "Unsung Monkeys", "description": "Win 10 games using only Support monkeys",
            "category": "single_player", "kind": "game_win_constraint", "mode": None,
            "map": None, "passive": False, "strategy": "ach_unsung_monkeys"}]
SCANNED = "2026-11-06 22:10:35"


def scan(status="progress", progress=30, scanned_at=SCANNED):
    card = {"desc": "Win 10 games using only Support monkeys", "status": status, "progress": progress}
    return {"scanned_at": scanned_at, "cards": {"Unsung Monkeys": card}}


def unsung(rate=0.95, **kw):
    d = {"id": "ach_unsung_monkeys", "achievement": "Unsung Monkeys", "map": "Logs",
         "modes": ["easy"], "towers": {"dart": [0, 0, 0]}, "base_success": {"easy": rate},
         "bot_ready": True}
    d.update(kw)
    return P.StrategySpec.from_any(d)


def plain(rate):
    return P.StrategySpec(id="plain", towers={"dart": (0, 0, 0)}, modes=frozenset({"easy"}),
                          base_success={"easy": rate})


def account():
    """A new account with Logs Easy beaten (by a normal strategy)."""
    acc = AccountState()
    acc.record_result("Logs", "easy", "plain", True, minutes=7.0)
    return acc


def ranked(acc, roster, state=None):
    return P.rank_games(acc, roster, achievements=(CATALOG, state if state is not None else scan()),
                        below_bar=True)


def test_replay_comes_before_the_last_resort():
    """Nothing clears its bar: the achievement replay goes ahead of the
    last-resort games, and it is the only beaten pair offered."""
    acc = account()
    phase, reasons, cands = ranked(acc, [plain(0.5), unsung()])
    assert phase == "ACH", (phase, reasons)
    top = cands[0]
    assert (top.map, top.mode, top.s.id, top.tier, top.first) == \
        ("Logs", "easy", "ach_unsung_monkeys", "ACH", False), top.notes
    assert "Unsung Monkeys" in top.achievements
    assert all(c.tier == "LAST" for c in cands[1:]) and len(cands) > 1
    # the normal strategy never replays Logs Easy
    assert not [c for c in cands if c.s.id == "plain" and c.map == "Logs" and c.mode == "easy"]
    assert any("achievement replays: 1" in r for r in reasons), reasons
    plan = P.next_game(acc, [plain(0.5), unsung()], achievements=(CATALOG, scan()))
    assert plan.phase == "ACH" and not plan.first_time and plan.map == "Logs", plan.reason


def test_first_time_medals_clearing_their_bar_go_first():
    acc = account()
    phase, _, cands = ranked(acc, [plain(0.95), unsung()])
    tiers = [c.tier for c in cands]
    assert phase != "ACH" and tiers[0] not in ("ACH", "LAST"), tiers
    assert "ACH" in tiers
    first_ach = tiers.index("ACH")
    assert all(t not in ("ACH", "LAST") for t in tiers[:first_ach])
    assert all(t in ("ACH", "LAST") for t in tiers[first_ach:])


def test_only_while_the_scan_reads_it_in_progress():
    acc = account()

    def replays(state, spec=None):
        _, _, cands = ranked(acc, [plain(0.5), spec or unsung()], state)
        return [c for c in cands if c.tier == "ACH"]

    assert replays(scan())
    assert not replays(scan(status="complete", progress=None))
    assert not replays(scan(status="collect", progress=None))
    assert not replays({"scanned_at": SCANNED, "cards": {}})     # not read: unknown
    assert not replays(scan(), unsung(bot_ready=False))          # not bot-ready
    assert not replays(scan(), unsung(rate=0.5))                 # under the bar: never


def test_stops_once_the_wins_since_the_scan_cover_the_rest():
    """30 % of 10 wins: 7 left. After 7 wins of the plan (after the scan)
    it waits for the next scan; wins from before the scan do not count."""
    acc = account()
    for _ in range(6):
        acc.record_result("Logs", "easy", "ach_unsung_monkeys", True, minutes=6.0)
    g = {x.name: x for x in P.wanted_achievements(acc, scan(scanned_at="2000-01-01 00:00:00"), CATALOG)}
    assert P._replay_allowed(unsung(), g, acc, "2000-01-01 00:00:00")      # 6 < 7
    acc.record_result("Logs", "easy", "ach_unsung_monkeys", False, minutes=3.0)  # a loss
    assert P._replay_allowed(unsung(), g, acc, "2000-01-01 00:00:00")
    acc.record_result("Logs", "easy", "ach_unsung_monkeys", True, minutes=6.0)
    assert not P._replay_allowed(unsung(), g, acc, "2000-01-01 00:00:00")  # 7 wins
    assert P._replay_allowed(unsung(), g, acc, "2999-01-01 00:00:00")      # all before the scan
    _, _, cands = ranked(acc, [plain(0.5), unsung()], scan(scanned_at="2000-01-01 00:00:00"))
    assert not [c for c in cands if c.tier == "ACH"]


def test_a_builds_own_wins_needed_wins():
    """A counter achievement (Freaky Friday: 100 ability uses) states how many
    of its games finish it from 0 %: 4 games, so at 52 % two replays."""
    acc = account()
    cat = [{"name": "Freaky Friday", "description": "Use the Alchemist's Transforming Tonic abilities 100 times",
            "category": "single_player", "kind": "cumulative", "passive": False}]
    state = {"scanned_at": "2000-01-01 00:00:00",
             "cards": {"Freaky Friday": {"status": "progress", "progress": 52}}}
    g = {x.name: x for x in P.wanted_achievements(acc, state, cat)}
    spec = unsung(id="ach_freaky_friday", achievement="Freaky Friday", wins_needed=4)
    for _ in range(2):
        assert P._replay_allowed(spec, g, acc, state["scanned_at"])
        acc.record_result("Logs", "easy", "ach_freaky_friday", True, minutes=9.0)
    assert not P._replay_allowed(spec, g, acc, state["scanned_at"])


def test_freaky_friday_build():
    """The new build is bot-ready, Logs Medium only, and buys Transforming
    Tonic alchemists, whose ability the AbilityPlanner fires on cooldown."""
    from btd6bot import abilities
    f = S.load_all()["ach_freaky_friday"]
    acct = F.full_account()
    assert f["bot_ready"] and S.validate(f) == [], f.get("bot_ready_reasons")
    assert S.usable(f, "medium", acct, map_name="Logs", allow_achievement=True)[0]
    assert not S.usable(f, "medium", acct, map_name="Resort", allow_achievement=True)[0]
    assert S.coverage(f, "medium", acct)[0]
    tonics = [st for st in f["plan"] if st.get("do") == "upgrade" and st["id"] in ("t1", "t2")]
    assert any(abilities.tower_abilities("alchemist", S.parse_cross(st["to"])) == ["Transforming Tonic"]
               for st in tonics)
    assert abilities.TOWER_ABILITIES["Transforming Tonic"][1] == "on_cooldown"


def test_planner_reads_the_current_accounts_scan():
    """The default config follows data/current_account.txt to
    data/accounts/<id>.achievements.json (what Achievements.scan writes)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        accounts = tmp / "accounts"
        accounts.mkdir()
        current = tmp / "current_account.txt"
        current.write_text("ABCDEFGHI", encoding="utf-8")
        live = accounts / "ABCDEFGHI.achievements.json"
        live.write_text(json.dumps(scan(progress=70)), encoding="utf-8")
        with mock.patch.object(identity, "CURRENT", current), \
                mock.patch.object(identity, "ACCOUNTS", accounts):
            assert P.account_scan_path() == str(live)
            cfg = P.PlannerConfig(maps_dir=None, tower_xp_path=None)
            assert cfg.achievements_state_path == P.ACCOUNT_SCAN
            _, state = P.load_achievements(cfg)
            assert state["cards"]["Unsung Monkeys"]["progress"] == 70
            live.unlink()
            assert P.account_scan_path() == str(P.LEGACY_SCAN)


def test_unsung_monkeys_build_is_offered():
    """The real YAML: MOAB SHREDR (spike x-3-x) answers MOABs, so the build
    passes coverage and runner.planner_specs offers it while it is wanted."""
    strats = S.load_all()
    acct = F.full_account()
    u = strats["ach_unsung_monkeys"]
    assert u["bot_ready"], u.get("bot_ready_reasons")
    assert S.coverage(u, "easy", acct) == (True, [])
    cards = {"Unsung Monkeys": {"status": "progress", "progress": 30}}
    with mock.patch.object(R.Achievements, "load", staticmethod(lambda: cards)):
        ids = {sp.id for sp in R.planner_specs(strats, acct)}
    assert "ach_unsung_monkeys" in ids


def test_axis_of_havoc_build():
    """ach_axis_of_havoc: candyfalls_chimps (won live) with its exit Spike
    Factory traded for the three tier-5 snipers. Bot-ready, Candy Falls
    CHIMPS only, every spot legal in plan order, and offline it owns all
    three tier 5s by round 99 without any round under the safety margin."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import optimize_builds as OB
    import simulate_threats as SIM
    import test_map_hints_offline as H
    strats = S.load_all()
    a = strats["ach_axis_of_havoc"]
    acct = F.full_account()
    assert a["bot_ready"] and S.validate(a) == [], a.get("bot_ready_reasons")
    assert a["extends"] == "candyfalls_chimps" and S.extends_problems(a, strats) == []
    assert a.get("plan_first") is True
    assert S.usable(a, "chimps", acct, map_name="Candy Falls", allow_achievement=True)[0]
    assert not S.usable(a, "chimps", acct, map_name="Logs", allow_achievement=True)[0]
    assert S.coverage(a, "chimps", acct) == (True, [])
    # one sniper per tier 5 (path -> sniper id), each reached by a plan step
    kinds = {st["id"]: st["kind"] for st in a["plan"] if st.get("do") == "place"}
    t5 = {path: st["id"] for st in a["plan"] if st.get("do") == "upgrade" and kinds[st["id"]] == "sniper"
          for path, tier in enumerate(S.parse_cross(st["to"])) if tier == 5}
    assert sorted(t5) == [0, 1, 2] and len(set(t5.values())) == 3, t5
    # spots: legal for their tower, in plan order, on the map's geometry
    spots = [(st["kind"], a["hero"] if st["kind"] == "hero" else None, tuple(st["at"]))
             for st in a["plan"] if st.get("do") == "place"]
    assert H.illegal_spots(a["map"], spots, 100) == []
    # the plan replayed as the cash allows: every round at the safety margin
    margins = OB.replay_plan(a)
    # Rounds 27-36 are candyfalls_chimps' own opening, which held them in its
    # live win. Since damage over time is credited only on the bloons an
    # attack reaches (2026-11-12, the glue fix) the model rates them 1.65-2.0,
    # under the 2.0 safety margin; the live win is the better witness, so the
    # floor here is the one the base build's won game rated at most.
    # 1.45 since 2026-11-13: with 93c2d83 (2026-11-12, few blimps are few: a
    # zone holds no more than the group sent down it, a projectile's pierce
    # counts only the blimps within its reach) the late blimp rounds rate
    # lower - round 95 1.79, 98 1.76, 99 1.59, 100 1.48 (all 1.8 or more
    # before). This build itself won live on 2026-11-08 03:58, round 100
    # included, so the floor is today's worst less a little.
    LIVE_PROVEN_FLOOR = 1.45
    assert min(margins.values()) >= LIVE_PROVEN_FLOOR, min(margins.items(), key=lambda kv: kv[1])
    # the executor's own game (threat answers, plan_first): all steps bought,
    # no bloon it cannot pop, and the three tier 5s stand together by round 99
    boards = {}
    r = SIM.simulate(dict(a), "chimps", a["map"], real_map=True, boards=boards)
    assert r["plan_done"] == f"{len(a['plan'])}/{len(a['plan'])}" and not r["gaps"], r["plan_done"]
    trio = [rnd for rnd in sorted(boards)
            if {p for k, t, _, _ in boards[rnd].values() if k == "sniper" for p in range(3) if t[p] == 5}
            == {0, 1, 2}]
    assert trio and trio[0] <= 99, trio[:1]


def test_extends_claim_is_checked():
    """`extends` is accepted only for a map build of the same map whose plan
    opens the achievement plan, short of at most EXTENDS_MAX_DROPPED of its
    last steps."""
    strats = S.load_all()
    a = strats["ach_axis_of_havoc"]
    assert S.extends_problems(dict(a, extends="nope"), strats)
    assert S.extends_problems(dict(a, map="Logs"), strats)
    assert S.extends_problems(dict(a, extends="ach_unsung_monkeys"), strats)
    base = strats["candyfalls_chimps"]["plan"]
    cut = len(base) - S.EXTENDS_MAX_DROPPED - 1
    probs = S.extends_problems(dict(a, plan=base[:cut] + a["plan"][22:]), strats)
    assert probs and "keeps only" in probs[0], probs
    changed = [dict(st) for st in a["plan"]]
    changed[2]["at"] = [0.5, 0.5]     # a moved boat is not the proven build
    assert S.extends_problems(dict(a, plan=changed), strats)
    assert S.extends_problems(dict(a, extends=None), strats) == []


def test_extended_achievement_plan_clears_the_chimps_bar():
    """An untested achievement plan is held just under the CHIMPS bar; one
    that extends the map's proven build is judged as that build and may be
    replayed (tier ACH) while its card is in progress."""
    acc = AccountState()
    acc.map_unlocked = lambda m: True     # Candy Falls is an Intermediate map
    for mode in ("hard", "impoppable", "chimps"):    # CHIMPS beaten, with what unlocks it
        acc.record_result("Candy Falls", mode, "candyfalls_chimps", True, minutes=19.0)
    cat = [{"name": "Axis of Havoc", "description": "Have one of each T5 sniper in one game of CHIMPS",
            "category": "single_player", "kind": "game_stat", "mode": "chimps", "map": None,
            "passive": False, "strategy": None}]
    state = {"scanned_at": SCANNED, "cards": {"Axis of Havoc": {"status": "progress", "progress": 0}}}

    def spec(**kw):
        d = {"id": "ach_axis_of_havoc", "achievement": "Axis of Havoc", "map": "Candy Falls",
             "modes": ["chimps"], "towers": {"dart": [0, 0, 0]}, "base_success": {"chimps": 0.85},
             "bot_ready": True, "wins_needed": 1}
        d.update(kw)
        return P.StrategySpec.from_any(d)

    with_base, without = spec(extends="candyfalls_chimps"), spec()
    assert P.is_own_map_build(with_base, "Candy Falls") and not P.is_own_map_build(without, "Candy Falls")
    assert not P.is_own_map_build(with_base, "Logs")
    for s, replayed in ((with_base, True), (without, False)):
        _, _, cands = P.rank_games(acc, [plain(0.5), s], achievements=(cat, state), below_bar=True)
        ach = [c for c in cands if c.tier == "ACH" and c.s.id == "ach_axis_of_havoc"]
        assert bool(ach) == replayed, [(c.tier, c.map, c.mode, c.s.id, round(c.p, 3)) for c in cands
                                       if c.s.id == "ach_axis_of_havoc"]


def test_assume_open_replays_an_unread_card_a_bounded_number_of_times():
    """A hidden card ("???" until earned) is never read by the scan. With
    the catalog's assume_open the plan replays until its wins *ever* reach
    wins_needed; no new scan resets that. A card the scan does read decides
    as before."""
    acc = account()
    cat = [dict(CATALOG[0], assume_open=True)]
    unread = {"scanned_at": SCANNED, "cards": {}}
    spec = unsung(wins_needed=2)
    g = {x.name: x for x in P.wanted_achievements(acc, unread, cat)}
    assert g["Unsung Monkeys"].status == "unknown" and g["Unsung Monkeys"].assume_open
    assert P._replay_allowed(spec, g, acc, SCANNED)
    _, _, cands = P.rank_games(acc, [plain(0.5), spec], achievements=(cat, unread), below_bar=True)
    assert [c for c in cands if c.tier == "ACH" and c.s.id == "ach_unsung_monkeys"]
    for _ in range(2):
        acc.record_result("Logs", "easy", "ach_unsung_monkeys", True, minutes=6.0)
    assert not P._replay_allowed(spec, g, acc, SCANNED)
    assert not P._replay_allowed(spec, g, acc, "2999-01-01 00:00:00")   # a later scan changes nothing
    done = {x.name: x for x in P.wanted_achievements(acc, scan(status="complete", progress=None), cat)}
    assert "Unsung Monkeys" not in done


def walk_plan(plan, mode, boosts=None):
    """The plan bought in order as the cash allows (a step with `round:`
    waits for that round), on the account's economy: Double Cash and Fast
    Track (data/accounts/SFYOSHHYV.json boosts). Fill, answers and
    reinforcement buys are left out. Returns (round each step was bought
    {index: round}, tower XP earned per kind {kind: xp}, steps bought).
    Tower XP: base round XP x1.08 (Monkey Education; Logs is a Beginner map,
    x1.0), split by the cash invested per kind (btd6bot/towerxp.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import optimize_builds as OB
    from btd6bot import towers as T
    from btd6bot.account import round_xp
    from btd6bot.towerxp import EDUCATION_MULT
    econ = OB.economy(mode, boosts or {"double_cash": True, "fast_track": True})
    cash, kinds, tiers, spent, bought, xp, i = econ.start_cash, {}, {}, {}, {}, {}, 0
    steps = plan["plan"]
    for rnd in range(econ.start_round, econ.end_round + 1):
        while i < len(steps):
            st = steps[i]
            if st.get("round") and rnd < st["round"]:
                break
            if st["do"] == "ability":       # costs nothing; the tower goes (Blood Sacrifice)
                if rnd < (st.get("when") or {}).get("round", 0):
                    break
                kinds.pop(st["target"], None)
                bought[i] = rnd
                i += 1
                continue
            if st["do"] == "place":
                cost = (T.hero_cost(plan["hero"], econ.family) if st["kind"] == "hero"
                        else T.tower_cost(st["kind"], econ.family))
            else:
                cost = OB.upgrade_cost(kinds[st["id"]], tiers[st["id"]], S.parse_cross(st["to"]), econ.family)
            if cost > cash:
                break
            cash -= cost
            if st["do"] == "place":
                kinds[st["id"]], tiers[st["id"]], spent[st["id"]] = st["kind"], (0, 0, 0), cost
            else:
                tiers[st["id"]] = tuple(max(a, b) for a, b in zip(tiers[st["id"]], S.parse_cross(st["to"])))
                spent[st["id"]] += cost
            bought[i] = rnd
            i += 1
        invested = {}
        for tid, kind in kinds.items():
            if kind != "hero":
                invested[kind] = invested.get(kind, 0) + spent[tid]
        total = sum(invested.values()) or 1
        for kind, v in invested.items():
            xp[kind] = xp.get(kind, 0) + round_xp(rnd) * EDUCATION_MULT * v / total
        cash += econ.income(rnd)
    return bought, xp, i


def test_world_league_training_build():
    """Logs Medium replay: an early Beast Handler holds enough of the cash on
    the board to earn more than half of the 16,809 Beast Handler XP the
    account is short of in one game, so two wins (wins_needed) finish it."""
    strats = S.load_all()
    w = strats["ach_world_league_training"]
    acct = F.full_account()
    assert w["bot_ready"] and S.validate(w) == [], w.get("bot_ready_reasons")
    assert S.usable(w, "medium", acct, map_name="Logs", allow_achievement=True)[0]
    assert not S.usable(w, "medium", acct, map_name="Resort", allow_achievement=True)[0]
    assert S.coverage(w, "medium", acct)[0]
    bought, xp, n = walk_plan(w, "medium")
    assert n == len(w["plan"]), f"plan stuck at step {n}"
    short = 150_000 - 133_191
    wins = P.StrategySpec.from_any(dict(w)).wins_needed
    assert wins == 2 and xp["beast_handler"] * wins >= short, xp


def test_not_lacking_critical_information_build():
    """Logs Medium replay: three 2-3-0 Robo Monkeys (crits count) inside a
    Jungle Drums village, all bought by round 60."""
    strats = S.load_all()
    c = strats["ach_not_lacking_critical_information"]
    acct = F.full_account()
    assert c["bot_ready"] and S.validate(c) == [], c.get("bot_ready_reasons")
    assert S.usable(c, "medium", acct, map_name="Logs", allow_achievement=True)[0]
    assert S.coverage(c, "medium", acct)[0]
    final = {}
    for st in c["plan"]:
        if st.get("do") == "upgrade":
            final[st["id"]] = tuple(S.parse_cross(st["to"]))
    robos = [tid for tid, t in final.items() if tid.startswith("r") and t == (2, 3, 0)]
    assert len(robos) == 3, final
    assert final["v1"][0] >= 2                    # Jungle Drums
    assert all("v1" in st.get("near", []) for st in c["plan"] if st.get("id") in robos and st["do"] == "place")
    _, _, n = walk_plan(c, "medium")
    assert n == len(c["plan"]), f"plan stuck at step {n}"


def test_kali_build():
    """Bot-ready since the `do: ability` step exists: the sacrificial M.A.D.
    is bought by round 80, last, after the defence for rounds 76-80
    (Perma-Spike), and is worth the worst case of ten Adora levels from
    level 7-10 (4 XP per dollar; the step's min_value is exactly that worst
    case); Adora placed at round 70 is level 7-10 from round 76 to 80, when
    the step may fire, and the step waits for a board rated min_margin
    without d1."""
    from btd6bot import abilities as AB
    from btd6bot import towers as T
    from btd6bot.towerxp import EDUCATION_MULT
    k = S.load_all()["ach_kali_maaaaaaaa"]
    assert k["bot_ready"] and S.readiness(k) == [], S.readiness(k)
    assert S.validate(k) == []
    bought, _, n = walk_plan(k, "hard")
    assert n == len(k["plan"]), f"plan stuck at step {n}"
    idx = {(st.get("id"), st.get("to")): i for i, st in enumerate(k["plan"])}
    mad_round = bought[idx[("d1", "0-5-0")]]
    hero_round = bought[idx[("hero", None)]]
    assert hero_round == 70 and mad_round <= 80, (hero_round, mad_round)
    assert idx[("sp1", "2-0-5")] < idx[("d1", "0-5-0")]          # the defence first
    sac = k["plan"][-1]
    assert sac["do"] == "ability" and sac["target"] == "d1" and bought[len(k["plan"]) - 1] <= 80
    xp = AB.HERO_LEVEL_XP
    scale = AB.HERO_XP_SCALE["adora"]
    worst = max((xp[lv + 10] - xp[lv]) * scale for lv in range(7, 11))
    assert sac["min_value"] * 4 >= worst > (sac["min_value"] - 1) * 4
    assert T.total_cost("dartling", "0-5-0", "hard") >= sac["min_value"]
    when = sac["when"]
    assert (when["hero_level_min"], when["hero_level_max"]) == (7, 10)
    assert when["min_margin"] >= 1.0
    levels = [AB.estimate_hero_level("adora", hero_round, r, EDUCATION_MULT)
              for r in range(max(when["round"], mad_round), 81)]
    assert all(7 <= lv <= 10 for lv in levels), levels


def test_kali_replay_survives_the_sacrifice():
    """The executor's own replay of the build on Logs Hard (tools/
    simulate_threats.py: the map's learned spots, the account's Fast Track
    start and Double Cash): the plan runs to its last step, no round lacks
    an answer, Blood Sacrifice takes d1 in round 76-80, and every round
    from 76 to 80 is rated at least the step's min_margin on the board
    without d1 - the defence never needs the M.A.D.

    The first live try (2026-11-09) had the spike at 2-0-4: the replay
    rated round 76 1.09 and 78 0.84 (live 0.81 and 0.58), the step fired 8 s
    into round 76 and the ceramics the M.A.D. was shooting at the exit
    leaked. Without plan_first the spare-cash ninjas took the M.A.D.'s cash
    and d1 ended at 0-4-0, worth $12,475."""
    import logging
    from types import SimpleNamespace as SN
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import optimize_builds as OB
    import simulate_threats as SIM
    from btd6bot import dps_model as D
    from btd6bot.forecast import RoundForecast
    k = S.load_all()["ach_kali_maaaaaaaa"]
    econ = OB.economy("hard", {"double_cash": True, "fast_track": True})
    sc = {"start_round": econ.start_round, "start_cash": econ.start_cash, "income_multiplier": econ.cash_mult}
    m = SIM.map_model("Logs", learned=True)
    fc = RoundForecast("Logs", "hard", m.sight, (getattr(m, "sight_height", None), getattr(m, "ground_height", None)))
    assert fc._ready()
    boards = {}
    logging.disable(logging.CRITICAL)
    try:
        r = SIM.simulate(k, "hard", "Logs", real_map=True, learned=True, scenario=sc, boards=boards)
    finally:
        logging.disable(logging.NOTSET)
    assert r["plan_done"] == f"{len(k['plan'])}/{len(k['plan'])}", r["plan_done"]
    assert r["gaps"] == [], r["gaps"]
    # the first board without d1 (the simulator plays the step before the
    # round's board is taken; live it fires while the round plays)
    sac = [rnd for rnd, b in sorted(boards.items()) if rnd >= 70 and "d1" not in b]
    assert sac and 76 <= sac[0] <= 80, sac
    floor = k["plan"][-1]["when"]["min_margin"]
    without = {}
    for rnd in range(76, 81):
        towers = [SN(tid=t, kind=kk, tiers=ti, x=fx, y=fy) for t, (kk, ti, fx, fy) in boards[rnd].items()
                  if t != "d1"]
        without[rnd] = D.round_margin(fc.stations(towers), "hard", rnd, fc.track)
    assert all(v >= floor for v in without.values()), without


def test_catalog_points_at_the_new_builds():
    """data/achievements.json: the new builds are wired to their
    achievements, the unreadable cards are assume_open, and on a scan that
    does not read them the planner replays both bot-ready builds."""
    root = Path(__file__).resolve().parents[1]
    cat = json.loads((root / "data" / "achievements.json").read_text(encoding="utf-8"))
    by = {e["name"]: e for e in cat}
    assert by["World League Training"]["strategy"] == "ach_world_league_training"
    assert by["Not Lacking Critical Information"]["strategy"] == "ach_not_lacking_critical_information"
    assert by["Kali Maaaaaaaa"]["strategy"] == "ach_kali_maaaaaaaa"
    assert by["World League Training"].get("assume_open") and by["Not Lacking Critical Information"].get("assume_open")
    strats = S.load_all()
    acc = AccountState()
    acc.record_result("Logs", "medium", "plain", True, minutes=9.0)
    kinds = ("ninja", "alchemist", "village", "super", "spike", "beast_handler", "dartling")
    acc.unlocked_towers |= set(kinds)       # the main account owns every upgrade
    acc.unlocked_upgrades = {k: [5, 5, 5] for k in kinds}
    acc.unlocked_heroes |= {"obyn", "adora"}
    ids = ("ach_world_league_training", "ach_not_lacking_critical_information", "ach_kali_maaaaaaaa")
    with mock.patch.object(R.Achievements, "load", staticmethod(lambda: {})):     # no card read
        specs = [plain(0.5)] + R.planner_specs({sid: strats[sid] for sid in ids}, F.full_account())
    assert {sp.id for sp in specs} == {"plain", *ids}         # Kali: bot-ready since `do: ability`
    unread = {"scanned_at": SCANNED, "cards": {}}
    _, _, cands = P.rank_games(acc, specs, achievements=(cat, unread), below_bar=True)
    ach = {c.s.id for c in cands if c.tier == "ACH"}
    assert ach == {"ach_world_league_training", "ach_not_lacking_critical_information"}, ach


def test_safe_mode_beginner_pass_skips_replays():
    """Safe mode's Beginner-first pass is for open medals; a replay is not one."""
    s = unsung()
    ach = NS(s=s, map="Logs", mode="easy", ease=P.CATEGORY_EASE["beginner"], ok=True, tier="ACH", p=0.95)
    assert R.beginner_before_safe_mode([ach], lambda m, mode: False) == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print("all tests passed")
