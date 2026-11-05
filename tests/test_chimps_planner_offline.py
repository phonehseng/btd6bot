"""CHIMPS is chosen safely: priced as Hard, never lifted by boosted records,
untested only with a map's own build, and owner picks checked.

- CHIMPS plays at Hard prices (x1.08), not Impoppable ones (x1.2): the
  runner priced it as Impoppable and could not read a tier back from the
  panel after village discounts (the Polyphemus loss).
- Every chimps_ninja_sun Impoppable game ran with Double Cash and Fast
  Track; CHIMPS has neither, so such a record may lower a CHIMPS factor but
  never lift it.
- A build with no CHIMPS game of its own clears the CHIMPS bar only when it
  was made for that one map (strategies/maps, strategies/optimized): not a
  general build with a multi-map allowlist, nor an achievement plan.
- The NEXT file cannot send the bot into a locked mode, nor into a one-life
  game under its bar unless the line ends with "!force".
Run: python tests/test_chimps_planner_offline.py (no game needed)."""
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_achievement_strats_offline as F     # noqa: E402  (the fakes)
from btd6bot import planner as P                # noqa: E402
from btd6bot import runner as R                 # noqa: E402
from btd6bot.account import MAPS, MODES, AccountState  # noqa: E402
from btd6bot.strategy import load_all           # noqa: E402

P.DEFAULT_CONFIG.maps_dir = None
P.DEFAULT_CONFIG.achievements_path = None
P.DEFAULT_CONFIG.achievements_state_path = None
P.DEFAULT_CONFIG.tower_xp_path = None
logging.getLogger("runner").setLevel(logging.CRITICAL)

MAP_LIST = list(MAPS)[:20]
BOOSTS = {"double_cash": True, "fast_track": True}   # the main account's buffs
MAP = "Monkey Meadow"                                # a beginner map


def spec(sid, base, maps=None):
    d = {"id": sid, "towers": {}, "modes": list(base), "base_success": base}
    if maps:
        d["maps"] = maps
    return P.StrategySpec.from_any(d)


def account_with(record, boosts=BOOSTS):
    """record: [(strategy id, mode, wins, losses)], spread over the first maps."""
    acc = AccountState()
    acc.boosts = dict(boosts)
    for sid, mode, wins, losses in record:
        for i in range(wins + losses):
            acc.record_result(MAP_LIST[i % len(MAP_LIST)], mode, sid, i < wins)
    return acc


# -- prices --------------------------------------------------------------------------
def test_chimps_is_priced_as_hard_and_impoppable_as_impoppable():
    def plan(mode):
        return SimpleNamespace(mode_key=mode, difficulty=MODES[mode].difficulty)
    assert R.game_difficulty(plan("chimps")) == "hard"
    assert R.game_difficulty(plan("impoppable")) == "impoppable"
    assert R.game_difficulty(plan("hard")) == "hard"
    assert R.game_difficulty(plan("medium")) == "medium"
    assert R.game_difficulty(plan("deflation")) == "easy"


# -- boosted records -----------------------------------------------------------------
def test_a_boosted_impoppable_record_does_not_lift_chimps():
    s = spec("ninja", {"impoppable": 0.4, "chimps": 0.4})
    acc = account_with([("ninja", "impoppable", 30, 1)])
    cal = P._Calibration(acc, {"ninja": s})
    assert cal.get("ninja", "impoppable") > 1.0                # the boosted mode keeps its lift
    assert cal.boosted_elsewhere("ninja", "chimps")
    assert cal.get("ninja", "chimps") <= 1.0
    assert cal.get("ninja", "chimps", acc.map_category(MAP)) <= 1.0


def test_without_boosts_the_record_still_counts_as_before():
    s = spec("ninja", {"impoppable": 0.4, "chimps": 0.4})
    acc = account_with([("ninja", "impoppable", 30, 1)], boosts={})
    cal = P._Calibration(acc, {"ninja": s})
    assert not cal.boosted_elsewhere("ninja", "chimps")
    assert cal.get("ninja", "chimps") > 1.0


def test_a_bad_boosted_record_still_lowers_chimps():
    s = spec("ninja", {"impoppable": 0.9, "chimps": 0.9})
    acc = account_with([("ninja", "impoppable", 2, 8)])
    cal = P._Calibration(acc, {"ninja": s})
    assert cal.get("ninja", "chimps") < 1.0


def test_chimps_games_of_its_own_may_lift_it():
    s = spec("ninja", {"impoppable": 0.4, "chimps": 0.4})
    acc = account_with([("ninja", "impoppable", 30, 1), ("ninja", "chimps", 10, 0)])
    cal = P._Calibration(acc, {"ninja": s})
    assert cal.get("ninja", "chimps") > 1.0


# -- untested CHIMPS -----------------------------------------------------------------
def test_an_untested_general_build_stays_under_the_chimps_bar():
    s = spec("general", {"hard": 0.95, "chimps": 0.95})
    acc = account_with([("general", "hard", 20, 0)])
    cal = P._Calibration(acc, {"general": s})
    p, n = P.win_probability(acc, s, MAP, "chimps", calib=cal)
    assert n == 0 and p < P.DEFAULT_CONFIG.min_p_chimps, p
    assert p == P.p_threshold("chimps") - 0.01


def test_a_map_specific_optimized_build_may_reach_the_bar_untested():
    from btd6bot.strategy import OPTIMIZED_PRIOR
    s = spec("opt_meadow_chimps", {"chimps": OPTIMIZED_PRIOR["safe"]}, maps=[MAP])
    acc = account_with([])
    cal = P._Calibration(acc, {s.id: s})
    p, n = P.win_probability(acc, s, MAP, "chimps", calib=cal)
    assert n == 0 and P.DEFAULT_CONFIG.min_p_chimps <= p <= P.UNTESTED_HARD_P, p


def test_a_general_multi_map_build_stays_under_the_bar_untested():
    # an allowlist of several maps (strategies/chimps_sub_druid_water.yaml
    # lists 24 water maps) marks a general build, not one proven on this map
    s = spec("water", {"hard": 0.95, "chimps": 0.95}, maps=[MAP, "Logs", "Resort"])
    acc = account_with([("water", "hard", 20, 0)])
    cal = P._Calibration(acc, {s.id: s})
    p, n = P.win_probability(acc, s, MAP, "chimps", calib=cal)
    assert n == 0 and p < P.DEFAULT_CONFIG.min_p_chimps, p


def test_an_achievement_plan_pinned_to_the_map_stays_under_the_bar_untested():
    d = {"id": "ach_meadow", "towers": {}, "modes": ["hard", "chimps"],
         "base_success": {"hard": 0.95, "chimps": 0.95}, "map": MAP,
         "achievement": "Some Achievement"}
    s = P.StrategySpec.from_any(d)
    assert s.maps == frozenset({MAP}) and s.achievement
    acc = account_with([("ach_meadow", "hard", 20, 0)])
    cal = P._Calibration(acc, {s.id: s})
    p, n = P.win_probability(acc, s, MAP, "chimps", calib=cal)
    assert n == 0 and p < P.DEFAULT_CONFIG.min_p_chimps, p


def test_other_hard_modes_keep_the_untested_hard_cap():
    s = spec("general", {"hard": 0.95, "chimps": 0.95})
    acc = account_with([])
    cal = P._Calibration(acc, {"general": s})
    p, _ = P.win_probability(acc, s, MAP, "hard", calib=cal)
    assert p == P.UNTESTED_HARD_P, p


# -- the owner's NEXT pick -----------------------------------------------------------
def pick(line, medals=None):
    """owners_pick for a NEXT file holding `line` on a full account with
    `medals` ({map: {mode: True}}); returns (plan, file left behind)."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "NEXT"
        f.write_text(line, encoding="utf-8")
        bot = R.Bot.__new__(R.Bot)
        bot.account = F.full_account()
        bot.account.medals = dict(medals or {})
        bot.strats = load_all()
        with mock.patch.object(R, "NEXT_FILE", f):
            plan = bot.owners_pick(R.planner_specs(bot.strats, bot.account))
            left = f.exists()
    return plan, left


def test_a_locked_chimps_pick_is_refused_even_when_forced():
    for line in ("Alpine Run / chimps", "Alpine Run / chimps !force"):
        plan, left = pick(line)                     # no Impoppable medal there
        assert plan is None and not left, line


def test_a_one_life_pick_under_its_bar_is_refused():
    plan, left = pick("Alpine Run / chimps / chimps_ninja_sun", {"Alpine Run": {"impoppable": True}})
    assert plan is None and not left


def test_force_plays_a_one_life_pick_under_its_bar():
    plan, _ = pick("Alpine Run / chimps / chimps_ninja_sun !force", {"Alpine Run": {"impoppable": True}})
    assert plan is not None and plan.strategy_id == "chimps_ninja_sun"
    assert (plan.mode_key, plan.difficulty) == ("chimps", "hard")
    assert 0.0 < plan.p_win < P.p_threshold("chimps")
    assert "forced" in plan.reason


def test_the_auto_start_warning_is_only_for_one_life_games():
    bot = R.Bot.__new__(R.Bot)
    bot._auto_start_seen = True
    with mock.patch.object(R.log, "warning") as warn:
        bot._warn_auto_start(SimpleNamespace(map="Alpine Run", mode_key="hard"))
        assert not warn.called
        bot._warn_auto_start(SimpleNamespace(map="Alpine Run", mode_key="chimps"))
        assert warn.called
    bot._auto_start_seen = False
    with mock.patch.object(R.log, "warning") as warn:
        bot._warn_auto_start(SimpleNamespace(map="Alpine Run", mode_key="chimps"))
        assert not warn.called


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
