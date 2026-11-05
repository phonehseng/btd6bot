"""The planner's calibration pools a strategy's record over all its modes.

military_heli_sniper won 131 of 137 games in Easy, Medium, Military Only and
Reverse but was never tried on Hard, where a build with 1 win in 2 ranked
above it on a hand-written guess. Now a mode with no games borrows the
strategy's pooled factor: a good record half (in log terms), a bad record in
full, and a build untested in a Hard-family mode is never rated confident.
Run: python tests/test_calibration_offline.py (no game needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import planner as P            # noqa: E402
from btd6bot.account import MAPS, AccountState  # noqa: E402

P.DEFAULT_CONFIG.maps_dir = None
P.DEFAULT_CONFIG.achievements_path = None
P.DEFAULT_CONFIG.achievements_state_path = None
P.DEFAULT_CONFIG.tower_xp_path = None

MAP_LIST = list(MAPS)[:20]


def spec(sid, base):
    return P.StrategySpec.from_any({"id": sid, "towers": {}, "modes": list(base), "base_success": base})


def account_with(record):
    """record: [(strategy id, mode, wins, losses)], spread over the first maps."""
    acc = AccountState()
    for sid, mode, wins, losses in record:
        for i in range(wins + losses):
            acc.record_result(MAP_LIST[i % len(MAP_LIST)], mode, sid, i < wins)
    return acc


def test_a_strong_record_elsewhere_lifts_an_untried_mode_but_not_to_confident():
    good = spec("good", {"easy": 0.9, "medium": 0.85, "hard": 0.75})
    plain = spec("plain", {"easy": 0.9, "medium": 0.85, "hard": 0.75})
    acc = account_with([("good", "easy", 20, 0), ("good", "medium", 20, 0)])
    cal = P._Calibration(acc, {"good": good, "plain": plain})
    assert cal.get("good", "hard") > 1.0                       # borrowed from Easy/Medium
    assert cal.get("good", "hard") < cal.pooled["good"]        # ... only half of it
    assert cal.get("plain", "hard") == 1.0                     # no record: no change
    p_good, _ = P.win_probability(acc, good, "Monkey Meadow", "hard", calib=cal)
    p_plain, _ = P.win_probability(acc, plain, "Monkey Meadow", "hard", calib=cal)
    assert p_plain < p_good <= P.UNTESTED_HARD_P < P.CONFIDENT_P, (p_plain, p_good)


def test_a_bad_record_elsewhere_counts_in_full():
    bad = spec("bad", {"medium": 0.9, "hard": 0.9})
    acc = account_with([("bad", "medium", 5, 5)])
    cal = P._Calibration(acc, {"bad": bad})
    assert cal.get("bad", "hard") == cal.pooled["bad"] < 1.0


def test_games_in_the_mode_itself_still_decide():
    s = spec("s", {"medium": 0.85, "hard": 0.8})
    acc = account_with([("s", "medium", 20, 0), ("s", "hard", 2, 6)])
    cal = P._Calibration(acc, {"s": s})
    assert cal.get("s", "hard") < 1.0 < cal.get("s", "medium")


def test_a_mode_is_calibrated_per_map_category():
    # double_hp_sniper_sun in ABR: nearly every beginner map won, every
    # expert map lost - Muddy Puddles (expert) must not keep the mode's average
    s = spec("s", {"abr": 0.85})
    acc = AccountState()
    beginner = [m for m in MAPS if acc.map_category(m) == "beginner"][:8]
    expert = [m for m in MAPS if acc.map_category(m) == "expert"][:4]
    for m in beginner:
        acc.record_result(m, "abr", "s", True)
    for m in expert:
        acc.record_result(m, "abr", "s", False)
    cal = P._Calibration(acc, {"s": s})
    mode_f = cal.get("s", "abr")
    assert cal.get("s", "abr", "expert") < mode_f < cal.get("s", "abr", "beginner"), cal.by_cat
    assert cal.get("s", "abr", "advanced") == mode_f           # no games there: the mode's factor
    untried_expert = [m for m in MAPS if acc.map_category(m) == "expert"][4]
    p, _ = P.win_probability(acc, s, untried_expert, "abr", calib=cal)
    p_mode = min(0.98, P.prior_win_probability(acc, s, untried_expert, "abr") * mode_f)
    assert p < p_mode, (p, p_mode)


def test_calibration_keeps_the_no_income_cap():
    # Ravine Deflation (2026-11-04): solo_dartling, capped at 0.76 as a
    # general build in a no-income mode, was lifted by its Deflation record
    # elsewhere to p=0.93, played as confident and lost at round 52
    s = spec("s", {"deflation": 0.92})
    acc = account_with([("s", "deflation", 12, 0)])
    cal = P._Calibration(acc, {"s": s})
    untried = [m for m in MAPS if acc.strategy_record(m, "deflation", "s").get("wins", 0) == 0][0]
    assert cal.get("s", "deflation", acc.map_category(untried)) > 1.0   # the record lifts it
    p, n = P.win_probability(acc, s, untried, "deflation", calib=cal)
    assert n == 0 and p <= P.NO_INCOME_GENERAL_CAP + 1e-9 < P.CONFIDENT_P, p


def test_a_no_income_record_does_not_vouch_for_an_income_mode():
    # Infernal Reverse (2026-11-04): solo_dartling, 13 of 18 in Deflation and
    # 0 of 1 in Medium, was rated p=0.88 in Reverse and lost at round 47
    s = spec("s", {"deflation": 0.6, "medium": 0.85, "reverse": 0.85})
    acc = account_with([("s", "deflation", 13, 5), ("s", "medium", 0, 1)])
    cal = P._Calibration(acc, {"s": s})
    assert cal.get("s", "deflation") > 1.0                     # its own economy: lifted
    assert cal.get("s", "reverse") < 1.0                       # income: only the Medium loss counts
    # with no income game at all, the Deflation record cannot lift it either
    acc = account_with([("s", "deflation", 13, 0)])
    cal = P._Calibration(acc, {"s": s})
    assert cal.get("s", "reverse") == 1.0, cal.get("s", "reverse")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
