"""tools/optimize_builds.py and the plans it writes (strategies/optimized/*.yaml).

Offline checks:
  * every written plan is a well-formed strategy for its map and mode
    (strategy.validate passes; the only step key the executor does not know
    yet is `at`, the exact spot; spots lie on the play field; towers are
    allowed in the mode; every crosspath is legal; the plan does not spend
    more than the economy it was planned for pays);
  * the economy: Fast Track start rounds as logged, Double Cash doubling;
  * a short optimization on Monkey Meadow comes out safe, puts money into
    its XP target and turns into valid YAML;
  * the log parser behind --calibrate reads a hand-made log correctly.
"""
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import layout as L  # noqa: E402
from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def _plans():
    return sorted(O.OUT_DIR.glob("*.yaml")) if O.OUT_DIR.is_dir() else []


def _cross(text):
    return tuple(int(c) for c in str(text).split("-"))


# ---------------------------------------------------------------------------
# The written plans
# ---------------------------------------------------------------------------

def test_written_plans_are_valid_strategies():
    x0, y0, x1, y1 = L.LAYOUTS["16:10"]["playfield"]
    for path in _plans():
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert d["id"] == f"opt_{path.stem}", path.name
        (mode,) = d["modes"]
        assert mode in S.MODE_RULES, path.name
        assert d["map"] in d["planner"]["maps"], path.name
        assert not S.validate(d), (path.name, S.validate(d))
        others = [r for r in S.readiness(d) if "'at'" not in r]
        assert not others, (path.name, others)
        only = S.MODE_TOWER_FILTER.get(mode)
        tiers = {}
        for step in d["plan"]:
            if step["do"] == "place" and step["kind"] != "hero":
                if only:
                    assert T.TOWERS[step["kind"]]["category"] == only, (path.name, step)
                fx, fy = step["at"]
                assert x0 <= fx <= x1 and y0 <= fy <= y1, (path.name, step)
                tiers[step["id"]] = (0, 0, 0)
            elif step["do"] == "upgrade":
                new = _cross(step["to"])
                assert all(n >= o for n, o in zip(new, tiers[step["id"]])), (path.name, step)   # never downgrades
                assert O.legal(new), (path.name, step)
                tiers[step["id"]] = new
            elif step["do"] == "target":
                assert step["mode"] in S.TARGET_MODES


def test_written_plans_spend_no_more_than_they_earn():
    for path in _plans():
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        (mode,) = d["modes"]
        sc = d["optimizer"]["scenario"]
        econ = O.economy(mode)
        family = econ.family
        income = sc["start_cash"] + sum(econ.income(r) * sc["income_multiplier"]
                                        for r in range(sc["start_round"], econ.end_round))
        spent, tiers, kinds = 0.0, {}, {}
        for step in d["plan"]:
            if step["do"] == "place":
                spent += (T.hero_cost(d["hero"], family) if step["kind"] == "hero"
                          else T.tower_cost(step["kind"], family))
                tiers[step["id"]], kinds[step["id"]] = (0, 0, 0), step["kind"]
            elif step["do"] == "upgrade":
                new = _cross(step["to"])
                spent += O.upgrade_cost(kinds[step["id"]], tiers[step["id"]], new, family)
                tiers[step["id"]] = new
        assert spent <= income + 1.0, (path.name, spent, income)


# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------

def test_fast_track_and_double_cash():
    boosts = {"fast_track": True, "double_cash": True}
    assert O.economy("easy", boosts).start_round == 10        # logged 2026-10-22
    assert O.economy("hard", boosts).start_round == 22        # logged 2026-10-21/22
    assert O.economy("deflation", boosts).start_round == 31   # no Fast Track in Deflation
    assert O.economy("deflation", boosts).start_cash == 40000  # logged: Double Cash doubles it
    assert O.economy("chimps", boosts).start_round == 6       # no boosts in CHIMPS
    assert O.economy("chimps", boosts).cash_mult == 1.0
    plain, doubled = O.economy("medium"), O.economy("medium", boosts)
    assert doubled.income(30) == 2 * plain.income(30) > 0
    hard = O.economy("hard", boosts)
    assert 8000 < hard.start_cash < 9700                      # below the $9,700 logged: on the safe side


# ---------------------------------------------------------------------------
# A short optimization
# ---------------------------------------------------------------------------

def test_short_optimization_is_safe_and_feeds_the_target():
    opt = O.Optimizer("Monkey Meadow", "easy", target="tack", account=None,
                      boosts={"fast_track": True, "double_cash": True})
    opt.econ.end_round = opt.econ.start_round + 6          # rounds 10-16: a few seconds
    plan = opt.run()
    assert not plan.unsafe, plan.margins
    assert min(plan.margins.values()) >= O.SAFETY_MARGIN
    assert plan.spent_by_kind.get("tack", 0) > 0
    xp = O.xp_report(plan, O.xp_weights(None))
    assert xp["target_xp"] > 0 and xp["minutes"] > 0
    text = O.plan_yaml(plan, opt.setup, O.xp_weights(None), xp)
    d = yaml.safe_load(text)
    assert d["xp_target"] == "tack" and not S.validate(d)
    assert [s for s in d["plan"] if s["do"] == "place" and s["kind"] == "hero"]


# ---------------------------------------------------------------------------
# Calibration: reading the bot's log
# ---------------------------------------------------------------------------

LOG = """\
2026-10-22 01:00:00,000 I runner: NEXT: [E] Monkey Meadow / easy with starter_tack_dart: score 1/min
2026-10-22 01:00:05,000 I game: placed t1 (tack) at 0.400,0.500
2026-10-22 01:00:06,000 I game: placed hero (hero) at 0.300,0.500
2026-10-22 01:00:07,000 I match: round 2  cash 300  lives 200
2026-10-22 01:00:09,000 I game: upgraded t1 -> 1-0-0
2026-10-22 01:00:10,000 W game: t1 is really 1-0-2, not 1-0-0 (panel prices [])
2026-10-22 01:00:11,000 I match: round 3  cash 100  lives 195
2026-10-22 01:00:20,000 I runner: RESULT {'start': 1.0, 'rounds': 2, 'lives_lost': 5, 'outcome': 'defeat', 'round': 3, 'minutes': 1.0}
"""


def test_log_parser():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bot.log"
        path.write_text(LOG, encoding="utf-8")
        (game,) = O.logged_games(path)
    assert (game["map"], game["mode"], game["strategy"]) == ("Monkey Meadow", "easy", "starter_tack_dart")
    assert game["outcome"] == "defeat" and game["last_round"] == 3
    (r2, lives2, snap2), (r3, lives3, snap3) = game["rounds"]
    assert (r2, lives2, r3, lives3) == (2, 200, 3, 195)
    assert snap2["t1"][3] == (0, 0, 0) and snap3["t1"][3] == (1, 0, 2)
    assert snap2["t1"][1:3] == (0.4, 0.5)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
