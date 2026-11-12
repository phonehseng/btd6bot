"""With every offered medal benched for a reason that is never retried, the
bot looks again with the struck-out last resorts and plays the loss longest
ago among them, instead of napping.

2026-11-12 01:56: the planner's last-resort list held only Erosion, Dark
Dungeons and Midnight Mansion Deflation - the three not struck out - each
benched for two days as "solo_dart rated 0.06, left 2x". Fourteen Impoppable
and Reverse games lost over an hour ago were due for their retry, but they
had struck out and were not on the list, so the bot napped in 30-minute
steps with 61 medals open.

Run: python tests/test_struck_out_retry_offline.py"""
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import planner  # noqa: E402
from btd6bot import runner as R  # noqa: E402
from btd6bot import safety  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402
from btd6bot.strategy import load_all  # noqa: E402

LEFT_AT_START = "solo_dart rated 0.06, left 2x"   # a bench that is never retried


def cand(map_name, mode, p=0.3):
    """A last-resort candidate as rank_games returns it, with the fields
    Bot.next_plan reads."""
    return SimpleNamespace(map=map_name, mode=mode, p=p, tier="LAST", score=1.0, minutes=10.0,
                           first=True, notes=[], ease=1.0,
                           s=SimpleNamespace(id=f"build_{mode}", heroes=(), achievement=None))


def bot_with(benches, reasons):
    """A Bot with only what next_plan needs: its bench files in a temp folder."""
    tmp = Path(tempfile.mkdtemp())
    b = R.Bot.__new__(R.Bot)
    b.bad, b.strats, b.account = set(), {}, AccountState()
    b._bench_file = lambda: tmp / "b.json"
    b._bench_why_file = lambda: tmp / "w.json"
    (tmp / "b.json").write_text(json.dumps(benches))
    (tmp / "w.json").write_text(json.dumps(reasons))
    b.owners_pick = lambda specs: None
    return b


def plan_with(bot, short, struck):
    """next_plan with the planner replaced: `short` is the usual last-resort
    list, `struck` what struck_too adds behind it. Returns the plan and the
    struck_too values the planner was asked with."""
    asked = []

    def rank(account, specs, below_bar=False, struck_too=False):
        asked.append(struck_too)
        return "LAST", ["reason"], list(short) + (list(struck) if struck_too else [])

    with mock.patch.object(planner, "rank_games", rank), \
            mock.patch.object(R, "planner_specs", lambda strats, account: {}), \
            mock.patch.object(R, "_show_choice", lambda *a, **k: None), \
            mock.patch.object(safety, "active", lambda: False):
        return bot.next_plan(), asked


def test_a_struck_out_loss_is_retried_when_the_offered_benches_never_are():
    now = time.time()
    short = [cand("Erosion", "deflation", 0.76)]
    # Last Resort is struck out but not benched: the due retry still goes first
    struck = [cand("Last Resort", "primary_only"), cand("Quad", "impoppable"),
              cand("Sunset Gulch", "impoppable")]
    bot = bot_with({"Erosion|deflation": now + 40 * 3600, "Quad|impoppable": now + 10 * 3600,
                    "Sunset Gulch|impoppable": now + 2 * 3600},
                   {"Erosion|deflation": {"why": LEFT_AT_START, "since": now - 8 * 3600},
                    "Quad|impoppable": {"why": "defeat", "since": now - 2 * 3600},
                    "Sunset Gulch|impoppable": {"why": "defeat", "since": now - 10 * 3600}})
    plan, asked = plan_with(bot, short, struck)
    assert asked == [False, True], asked
    assert plan is not None and (plan.map, plan.mode_key) == ("Sunset Gulch", "impoppable"), plan
    assert plan.phase == "RETRY", plan.phase


def test_a_struck_out_game_that_is_not_benched_is_played():
    now = time.time()
    bot = bot_with({"Erosion|deflation": now + 40 * 3600},
                   {"Erosion|deflation": {"why": LEFT_AT_START, "since": now - 8 * 3600}})
    plan, _ = plan_with(bot, [cand("Erosion", "deflation")], [cand("Quad", "impoppable")])
    assert plan is not None and plan.map == "Quad" and plan.phase == "LAST", plan


def test_the_nap_is_cut_to_the_first_struck_out_retry():
    now = time.time()
    bot = bot_with({"Erosion|deflation": now + 40 * 3600, "Quad|impoppable": now + 11.5 * 3600},
                   {"Erosion|deflation": {"why": LEFT_AT_START, "since": now - 8 * 3600},
                    "Quad|impoppable": {"why": "defeat", "since": now - 0.5 * 3600}})
    plan, _ = plan_with(bot, [cand("Erosion", "deflation")], [cand("Quad", "impoppable")])
    assert plan is None
    assert 0.5 * 3600 - 5 < bot.idle_seconds() < 0.5 * 3600 + 5, bot.idle_seconds()


def test_the_wider_list_is_not_asked_for_while_a_game_is_free_or_a_retry_ready():
    now = time.time()
    free = bot_with({}, {})
    plan, asked = plan_with(free, [cand("Erosion", "deflation")], [cand("Quad", "impoppable")])
    assert plan.map == "Erosion" and asked == [False], (plan, asked)
    ready = bot_with({"Erosion|deflation": now + 9 * 3600},
                     {"Erosion|deflation": {"why": "defeat", "since": now - 3 * 3600}})
    plan, asked = plan_with(ready, [cand("Erosion", "deflation")], [cand("Quad", "impoppable")])
    assert plan.map == "Erosion" and plan.phase == "RETRY" and asked == [False], (plan, asked)


def test_the_planner_puts_struck_out_last_resorts_behind_the_others():
    """rank_games on an account where one open medal's build has struck out:
    left out by default, last with struck_too, the rest of the list unchanged."""
    specs = R.planner_specs(load_all(), AccountState())
    acc = AccountState()
    _, _, before = planner.rank_games(acc, specs, below_bar=True)
    last = [c for c in before if c.tier == "LAST"]
    if len({(c.map, c.mode) for c in last}) < 2:
        return                      # a bare account offers too little to tell
    victim = last[0]
    for _ in range(planner.LAST_RESORT_STRIKES):
        acc.history.append({"t": "2026-11-12T01:00:00", "map": victim.map, "mode": victim.mode,
                            "strategy": victim.s.id, "won": False})
    key = (victim.map, victim.mode, victim.s.id)
    _, _, short = planner.rank_games(acc, specs, below_bar=True)
    _, _, wide = planner.rank_games(acc, specs, below_bar=True, struck_too=True)
    ids = lambda cands: [(c.map, c.mode, c.s.id) for c in cands]   # noqa: E731
    assert key not in ids(short), "a struck-out build is not a last resort by default"
    assert ids(wide)[:len(short)] == ids(short), "the usual list comes first, unchanged"
    assert key in ids(wide)[len(short):], "the struck-out build follows it"
    assert all(c.tier == "LAST" for c in wide[len(short):])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
