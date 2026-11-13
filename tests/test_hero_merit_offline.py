"""Heroes are chosen on merit (docs/tower_exclusions_audit.md item 1).

Before 2026-11-12 the hero fallback lists (strategy.HERO_FALLBACK,
planner.HERO_PRIORITY) were the four free heroes of a fresh account in a
hand order, so twelve of eighteen heroes were never chosen. They now follow
data/hero_merit.json, ranked in the damage model by tools/rank_heroes.py:

  * the file is up to date with the model (a model change re-ranks: run
    `python tools/rank_heroes.py`);
  * every hero the model can rate is ranked; Corvus is not (no profile,
    dps_model.UNRATED_HEROES) and comes last;
  * the fallback order holds every hero, land heroes before water ones, and
    the fresh-account four after the ranked ones;
  * hero_for and the planner take the best owned hero on that order.

All offline: no game.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import rank_heroes  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import planner as P  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402

DATA = json.loads(T.HERO_MERIT_FILE.read_text(encoding="utf-8"))


def test_the_ranking_is_up_to_date_with_the_model():
    if not D.available():
        return
    assert rank_heroes.rank() == DATA["scores"], "run: python tools/rank_heroes.py"


def test_every_rated_hero_is_ranked_and_corvus_is_last():
    scores = DATA["scores"]
    for hero in T.HEROES:
        assert (hero in scores) == rank_heroes.rated(hero), hero
    assert "corvus" not in scores and "corvus" in D.UNRATED_HEROES
    order = T.hero_merit_order()
    assert sorted(order) == sorted(T.HEROES) and order[-1] == "corvus"
    assert list(order[:len(scores)]) == sorted(scores, key=lambda h: (-scores[h], h))


def test_fallbacks_follow_merit_land_first_and_keep_the_fresh_account_heroes():
    order = T.hero_fallback_order()
    assert sorted(order) == sorted(T.HEROES)
    water = [i for i, h in enumerate(order) if T.HEROES[h].get("placement") == "water"]
    land = [i for i, h in enumerate(order) if T.HEROES[h].get("placement") != "water"]
    assert water and max(land) < min(water), order
    assert set(T.FRESH_ACCOUNT_HEROES) <= set(order)
    assert S.HERO_FALLBACK == list(order) == P.hero_priority()
    # no longer the four free heroes only, and not in their hand order
    assert len(S.HERO_FALLBACK) == len(T.HEROES)


def _account(heroes):
    return SimpleNamespace(unlocked_heroes=set(heroes))


def test_hero_for_takes_the_best_owned_hero_on_merit():
    order = [h for h in T.hero_fallback_order() if T.HEROES[h].get("placement") != "water"]
    best, second = order[0], order[1]
    strat = {"id": "x", "hero": "corvus", "plan": []}        # a hero this account lacks
    assert S.hero_for(strat, _account({best, second, "quincy"})) == best
    assert S.hero_for(strat, _account({second, "quincy"})) == second
    # the old order is still the last resort of a fresh account
    assert S.hero_for({"id": "y", "plan": []}, _account({"quincy"})) == "quincy"
    spec = SimpleNamespace(heroes=[])
    assert P._pick_hero(spec, _account({second, "obyn"})) == (second if order.index(second) <
                                                             order.index("obyn") else "obyn")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
