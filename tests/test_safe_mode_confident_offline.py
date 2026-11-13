"""Safe mode plays confident games first; without one it plays the normal order.

2026-11-03: with the confident Medium games used up, safe mode went on to
p 0.78-0.84 games with no record (High Finance, Cornfield, Sanctuary
Medium) and lost all three within 15 minutes. Runner.next_plan now keeps
only p >= planner.CONFIDENT_P while the breaker is on and one is left.
Without one it used to idle, and from 02:57 to 15:41 the bot did nothing
with 172 medals open; the owner's rule is to keep playing in medal order,
so it now falls back to the planner's normal order (no game needed).
Run: python tests/test_safe_mode_confident_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import planner, runner, safety  # noqa: E402


def cand(map_name, mode, p, ease=1.0):
    s = NS(id=f"{map_name}_{mode}", heroes=())
    return NS(map=map_name, mode=mode, p=p, ease=ease, s=s, score=1.0, notes=[],
              minutes=8.0, first=True)


def plan_with(cands, safe=True):
    """Runner.next_plan on a stand-in runner whose planner offers `cands`."""
    saved = (runner.planner_specs, planner.rank_games, safety.active, safety.status)
    runner.planner_specs = lambda strats, account: []
    planner.rank_games = lambda account, specs, **kw: ("TEST", ["no candidates"], list(cands))
    safety.active = lambda: safe
    safety.status = lambda: "SAFE MODE (test)"
    try:
        # owners_pick: the NEXT file (d37f06d); watched_chimps_pick: the
        # CHIMPS_WATCH list (0705775) - neither picks a game in this test
        fake = NS(strats={}, account=None, benched=lambda m, mode: False,
                  owners_pick=lambda specs: None, watched_chimps_pick=lambda specs: None)
        return runner.Bot.next_plan(fake)
    finally:
        runner.planner_specs, planner.rank_games, safety.active, safety.status = saved


def test_unsure_games_are_skipped():
    plan = plan_with([cand("High Finance", "medium", 0.84, ease=2.0),
                      cand("Cargo", "medium", 0.90)])
    assert plan is not None and plan.map == "Cargo", plan
    print("ok safe mode skips p=0.84 for a p=0.90 game")


def test_normal_order_without_a_confident_game():
    plan = plan_with([cand("Sanctuary", "medium", 0.83), cand("Cornfield", "medium", 0.78)])
    assert plan is not None and plan.map == "Sanctuary", plan
    print("ok safe mode falls back to the planner's order when every game is under p=0.85")


def test_normal_mode_unchanged():
    plan = plan_with([cand("Cornfield", "medium", 0.78)], safe=False)
    assert plan is not None and plan.map == "Cornfield", plan
    print("ok outside safe mode the planner's own order stands")


if __name__ == "__main__":
    test_unsure_games_are_skipped()
    test_normal_order_without_a_confident_game()
    test_normal_mode_unchanged()
    print("ALL OK")
