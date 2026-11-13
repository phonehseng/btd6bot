"""The generated solo builds name the hero they rate best with
(docs/tower_exclusions_audit.md item 1: every one used to name Quincy).

  * boards_by_round buys the plan as a Medium game pays for it, the hero at
    its own price;
  * pick_hero tries every land hero the damage model rates (never Corvus,
    never Admiral Brickell, who needs water) and names the best;
  * without the damage model the build keeps Quincy.

All offline: no game.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gen_builds as G  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def _plan(kind):
    b = G.build_carry(kind) if G.is_carry(kind) else G.build_support(kind)
    return b, [dict(st) for st, _ in b.plan]


def test_boards_follow_the_cash_a_medium_game_pays():
    _b, plan = _plan("dart")
    for hero in ("quincy", "churchill"):
        boards, placed = G.boards_by_round(plan, hero, G.HERO_ROUNDS)
        for rnd, board in boards.items():
            cost = sum(T.hero_cost(hero) if k == "hero" else T.total_cost(k, t) for _, k, t in board)
            assert cost <= G.income(rnd - 1) + 1e-6, (hero, rnd, cost)
        assert placed.get("hero") is not None
    # a dearer hero comes later
    cheap = G.boards_by_round(plan, "quincy", G.HERO_ROUNDS)[1]["hero"]
    dear = G.boards_by_round(plan, "churchill", G.HERO_ROUNDS)[1]["hero"]
    assert T.hero_cost("churchill") > T.hero_cost("quincy") and dear >= cheap


def test_the_build_names_the_hero_it_rates_best_with():
    if not D.available() or not D.HERO_RATING:
        return
    cands = G.hero_candidates()
    assert "corvus" not in cands and "admiral_brickell" not in cands and "geraldo" in cands
    assert len(cands) >= 15
    b, plan = _plan("dart")
    setup = G.OPT.MapSetup(G.HERO_MAP, G.HERO_MODE)
    scores = {h: G.rate_hero(plan, h, setup) for h in cands}
    best = max(cands, key=lambda h: (scores[h], -cands.index(h)))
    assert G.pick_hero(b) == best
    b.hero = best
    assert b.strategy(["medium"])["hero"] == best


def test_without_the_model_the_build_keeps_quincy():
    b, _plan_ = _plan("tack")
    saved = D.available
    D.available = lambda: False
    try:
        assert G.pick_hero(b) == G.HERO == "quincy"
    finally:
        D.available = saved


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
