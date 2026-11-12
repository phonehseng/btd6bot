"""The optimizer compares heroes on merit (docs/tower_exclusions_audit.md item 1).

It used to plan with whatever hero was equipped when it ran (or Quincy),
and that hero was then played live, which kept it equipped. Now:

  * hero_candidates: every owned hero the damage model can rate that has a
    spot on the map, best on merit first - never Corvus (no profile), never
    Admiral Brickell on a map without water, never a hero the account lacks;
    Geraldo is rated on his own attack only (his shop is not exported);
  * optimize() picks the XP target with the first hero (the equipped one if
    it is a candidate), then sweeps the other heroes on that target and
    keeps the best plan by the usual rule (safe first, then XP per hour).

A real optimization takes 1-3 minutes, so the sweep is checked with a
stand-in Optimizer whose plans are safe only with one hero.
"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def test_candidates_are_owned_rated_and_placeable():
    if not D.available():
        return
    meadow = O.MapSetup("Monkey Meadow", "medium")
    every = O.hero_candidates(None, meadow)
    assert "corvus" not in every and "admiral_brickell" not in every      # no profile; no water
    assert every == [h for h in T.hero_merit_order() if h in every]       # best on merit first
    assert len(every) >= len(T.HEROES) - 2
    owned = N(unlocked_heroes={"quincy", "obyn", "corvus", "admiral_brickell"})
    assert O.hero_candidates(owned, meadow) == [h for h in T.hero_merit_order() if h in ("quincy", "obyn")]
    # Geraldo: his own attack only - nothing from his shop, no ability
    prof = D.profile(D.hero_kind("geraldo"), (20,))
    assert prof.sources and not any(s.ability for s in prof.sources)


class StandIn:
    """An Optimizer whose plan is safe only with the hero `good`; every run
    is recorded as (target, reserve, hero)."""
    runs = []
    good = "obyn"

    def __init__(self, map_name, mode, target=None, account=None, hero="quincy", boosts=None, reserve=True):
        self.args = (target, reserve, hero)
        self.setup = None

    def run(self):
        StandIn.runs.append(self.args)
        target, reserve, hero = self.args
        safe = hero == StandIn.good
        xp = {"dart": 100, "tack": 300}.get(target, 0) + (5 if reserve else 0)
        towers = [N(kind=target or "dart")]
        return N(unsafe=[] if safe else [40], margins={40: 2.5 if safe else 0.5}, seconds=0.0, board_cash=0.0,
                 towers=towers, hero=hero, xp=xp)


# the rest of an account the optimizer reads (xp_weights): no boosts, no XP
PLAIN = dict(boosts={}, unlocked_upgrades={}, paragons={}, tower_xp={})


def _sweep(account, heroes=None):
    saved = (O.Optimizer, O.xp_report, O.plan_yaml, O.target_candidates)
    StandIn.runs = []
    O.Optimizer = StandIn
    O.xp_report = lambda plan, weights: {"valued_xp_per_hour": plan.xp}
    O.plan_yaml = lambda plan, setup, weights, xp: ""
    O.target_candidates = lambda *a, **k: ["dart", "tack"]
    try:
        plan, _xp, _path = O.optimize("Monkey Meadow", "medium", account=account, write=False, heroes=heroes)
    finally:
        O.Optimizer, O.xp_report, O.plan_yaml, O.target_candidates = saved
    return plan, list(StandIn.runs)


def test_the_sweep_keeps_the_hero_that_makes_the_plan_safe():
    if not D.available():
        return
    account = N(unlocked_heroes={"quincy", "obyn", "churchill"}, selected_hero="quincy", **PLAIN)
    plan, runs = _sweep(account)
    assert plan.hero == "obyn" and not plan.unsafe
    # stage 1: both targets, both spot rules, with the equipped hero
    assert runs[:4] == [("dart", True, "quincy"), ("dart", False, "quincy"),
                        ("tack", True, "quincy"), ("tack", False, "quincy")]
    # stage 2: the other owned heroes on the winning target and spot rule
    assert sorted(h for _, _, h in runs[4:]) == ["churchill", "obyn"]
    assert {(t, r) for t, r, _ in runs[4:]} == {("tack", True)}
    # heroes=1: no sweep at all
    plan, runs = _sweep(account, heroes=1)
    assert len(runs) == 4 and plan.hero == "quincy"
    # an explicit list: exactly those heroes, each with every target and spot rule
    plan, runs = _sweep(account, heroes=["quincy", "obyn"])
    assert len(runs) == 8 and {h for _, _, h in runs} == {"quincy", "obyn"} and plan.hero == "obyn"


def test_without_an_equipped_candidate_the_best_on_merit_goes_first():
    if not D.available():
        return
    account = N(unlocked_heroes={"quincy", "obyn", "corvus"}, selected_hero="corvus", **PLAIN)
    _plan, runs = _sweep(account)
    first = [h for h in T.hero_merit_order() if h in ("quincy", "obyn")][0]
    assert {h for _, _, h in runs[:4]} == {first}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
