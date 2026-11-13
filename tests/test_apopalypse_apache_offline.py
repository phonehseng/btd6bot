"""apopalypse_apache_spikes: the Apopalypse build for the harder maps.

Why
---
The 22 Apopalypse medals still open on the account are all on Intermediate,
Advanced and Expert maps. apopalypse_ninja_sniper (ninjas, Full Auto Rifle
snipers, an alchemist) won 17 and lost 32 there, 2-14 since 2026-11-08,
losing a wall at rounds 42-59 when dense ceramic waves and MOAB groups
overlapped, and was excluded from 7 maps by hand. The new build's damage
is Apache Dartship helis (Heli Pilot 4-2-0): Pursuit flies them to the
bloons wherever the walls, lanes and panes are, IFR gives them camo, and
the $8,500 Apache tier is the largest gain per dollar and per click
tools/apopalypse_check.py found (strategies/apopalypse_apache_spikes.yaml
has the design, sources and numbers).

Checked offline:
  * the build loads, validates and is planned in Apopalypse only, on
    Intermediate/Advanced/Expert maps, ahead of the old build there;
  * its spike steps are skipped where spikes have no ground (`not_maps`,
    Executor._step_allowed: Covered Garden's panes) and kept elsewhere;
  * on Covered Garden its helis stand off the panes while open ground is
    left (Executor._off_panes), so their Apache tiers are not set aside
    three rounds in four, and the round-45 wave that lost the old build
    its 122 lives (2026-11-09) is held with round 46 on its heels;
  * under the click model (one Apopalypse round, ~4 s, of clicking a
    round) its first Apache Dartship stands before Apopalypse's MOAB
    groups and its second before round 55, on a poor game's income;
  * the random-round check rates its rounds 41-60 above the old build's on
    Firing Range (a map the old build lost four times).
Run: python tests/test_apopalypse_apache_offline.py
"""
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import planner as PL           # noqa: E402
from btd6bot import strategy as S           # noqa: E402
from btd6bot.account import AccountState    # noqa: E402
import apopalypse_check as C                # noqa: E402
import simulate_threats as SIM              # noqa: E402

NEW, OLD = "apopalypse_apache_spikes", "apopalypse_ninja_sniper"
CLICK_BUDGET = 4.0          # clicktime.ROUND_S: one Apopalypse round of clicking


def _strat(sid):
    return yaml.safe_load((ROOT / "strategies" / f"{sid}.yaml").read_text(encoding="utf-8"))


def _spec(sid):
    s = S.load_all()[sid]
    return PL.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))


def test_build_is_valid_and_apopalypse_only():
    strat = S.load_all()[NEW]
    assert S.validate(strat) == [], S.validate(strat)
    assert strat["modes"] == ["apopalypse"] and strat.get("plan_first") is True
    # no farms: Apopalypse's random rush waves punish greed (bloonswiki strategy page)
    assert not any(st.get("kind") == "farm" for _, st in S._all_steps(strat))


def test_planned_on_harder_maps_ahead_of_the_old_build():
    acc = AccountState()
    new, old = _spec(NEW), _spec(OLD)
    # (Bloody Puddles left the list on 2026-11-12: its own map build plays it,
    # tests/test_apopalypse_mapbuilds_offline.py)
    for m in ("Firing Range", "Ravine", "Muddy Puddles", "Sunset Gulch", "Workshop"):
        cat = acc.map_category(m)
        assert PL._strategy_fits(new, m, cat, "apopalypse"), m
        assert PL._prior(new, m, cat, "apopalypse") > PL._prior(old, m, cat, "apopalypse"), m
    # Beginner maps keep their own map builds and the old general build
    assert not PL._strategy_fits(new, "Park Path", acc.map_category("Park Path"), "apopalypse")
    # Erosion: the map-fit table gives the heli no reach there (0.0)
    assert not PL._strategy_fits(new, "Erosion", acc.map_category("Erosion"), "apopalypse")
    # Covered Garden: the old build (round 45 on 2026-11-09) plays it again
    # since the new one lost round 16 there (2026-11-10: no heli ground off
    # the panes)
    cg = acc.map_category("Covered Garden")
    assert not PL._strategy_fits(new, "Covered Garden", cg, "apopalypse")
    assert PL._strategy_fits(old, "Covered Garden", cg, "apopalypse")


def _executor(map_name):
    g = SIM.CashGame("medium", "obyn")
    return S.Executor(g, SIM.OpenModel(map_name), _strat(NEW), "apopalypse", SIM.full_account())


def test_spikes_skipped_where_they_have_no_ground():
    def spike_steps(ex):
        return [st for st in ex.plan if st.get("id") in ("sp1", "sp2")]
    assert spike_steps(_executor("Ravine")), "the spikes belong to the plan elsewhere"
    assert not spike_steps(_executor("Covered Garden"))
    # a misspelt map name in not_maps is a validation error, not a silent no-op
    bad = dict(_strat(NEW))
    bad["plan"] = [dict(st) for st in bad["plan"]]
    bad["plan"][0]["not_maps"] = ["Coverd Garden"]
    assert any("not_maps" in r for r in S.validate(bad))


def test_apaches_are_bought_in_time_under_the_click_budget():
    boards, res = C.boards(_strat(NEW), "Ravine", learned=False, click_budget=CLICK_BUDGET)
    tiers = lambda rnd, tid: tuple(boards[rnd].get(tid, (None, (0, 0, 0)))[1])  # noqa: E731
    assert tiers(45, "h1") == (4, 2, 0), tiers(45, "h1")     # MOAB groups from round 41
    assert tiers(55, "h2") == (4, 2, 0), tiers(55, "h2")     # BFBs from round 51


def test_covered_garden_helis_stand_off_the_panes():
    from btd6bot import mapgeom
    _, res = C.boards(_strat(NEW), "Covered Garden", learned=False, click_budget=CLICK_BUDGET)
    model = SIM.map_model("Covered Garden", False)
    for tid in ("h1", "h2"):
        kind, tiers, fx, fy = res["placed"][tid]
        assert mapgeom.pane_at(model, fx, fy, None)[0] is None, (tid, fx, fy)
        assert tuple(tiers) == (4, 2, 0), (tid, tiers)
    # short-range towers keep the garden ground: the ninjas' track is there
    assert any(mapgeom.pane_at(model, *res["placed"][t][2:], None)[0] is not None for t in ("n1", "n2"))


def test_covered_garden_round_45_wave():
    """The wave that took all 122 lives on Covered Garden (2026-11-09 20:36,
    apopalypse_ninja_sniper; the journal's leak: 25 rainbows, 180 pinks, 4
    fortified leads, 10 camo purples) against each build's round-45 board,
    with round 46 sent on its heels as apopalypse_check builds its worst
    windows (the wave alone rates 2-3 for both: what lost the game was the
    next round arriving before it was popped). Old ~0.7, new ~3.2."""
    from btd6bot import apopalypse as A

    def group(bloon, count):
        return next(g for g in A.groups() if g.bloon == bloon and g.count == count)
    wave = [group("Rainbow", 25), group("Pink", 180), group("LeadFortified", 4), group("PurpleCamo", 10)]
    rater = C.Rater("Covered Garden")
    margin = {}
    for sid in (NEW, OLD):
        boards, _ = C.boards(_strat(sid), "Covered Garden", learned=False, click_budget=CLICK_BUDGET)
        board = boards[45]
        st = rater.stations(board)
        nxt = rater.worst_rounds(board, st, 46)
        margin[sid] = min(rater.margin(st, [wave, r46]) for r46 in nxt.values())
    assert margin[OLD] < 1.0 < 2.0 < margin[NEW], margin


def test_late_rounds_rate_above_the_old_build():
    rounds = {46, 50, 55, 59}
    worst = {}
    for sid in (NEW, OLD):
        res = C.check(_strat(sid), "Firing Range", samples=2, drift=0.0, rounds=rounds,
                      learned=False, click_budget=CLICK_BUDGET)
        worst[sid] = min(c.margin for c in res["plain"])
    assert worst[NEW] > worst[OLD] + 0.3, worst


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
            n += 1
    print(f"{n} passed")
