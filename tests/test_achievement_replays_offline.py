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
