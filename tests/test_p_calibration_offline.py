"""Win-probability caps and penalties measured against the bot's own record
(2026-11-11).

1. The model-ceiling cap (planner.ceiling_cap) was a fixed guess,
   CEILING_P_CAP x ceiling / CEILING_PLAYABLE. Up to 2026-11-11, games with
   lives to spare under a ceiling of 0.5-1.5 were won 39 times in 70 (56%)
   while rated 0.2-0.3, and one-life games under a ceiling of 0.2 were won
   once in 43. With an account the cap is now that account's record in the
   ceiling's band and life class, shrunk towards the old formula
   (planner.ceiling_band_cap).
2. Every loss on a map/mode multiplied a general build's prior by 0.7. In
   multi-life modes only the first loss moved the record that much (75% at
   the first try, 50% after one loss, 45-52% after two or three), so the
   later ones count MAP_LOSS_REPEAT_FACTOR there (planner.map_loss_factor).

Run: python tests/test_p_calibration_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as PL  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402

# made-up ceilings, so the tests do not hang on today's research numbers
CEILINGS = {"Mesa|half_cash": 0.7, "Erosion|half_cash": 0.7, "Mesa|impoppable": 0.06,
            "Erosion|impoppable": 0.06, "Bazaar|half_cash": 1.2}


def _with_ceilings(fn):
    """Run ``fn`` with CEILINGS as the planner's model ceilings."""
    def run():
        saved = PL._CEILINGS
        PL._CEILINGS = dict(CEILINGS)
        try:
            fn()
        finally:
            PL._CEILINGS = saved
    run.__name__ = fn.__name__
    return run


def _account(games):
    """An account whose history is ``games``: (map, mode, won) tuples."""
    acc = AccountState()
    acc.history = [{"t": f"2026-11-11T{i // 60:02d}:{i % 60:02d}:00", "map": m, "mode": mode,
                    "strategy": "x", "won": won} for i, (m, mode, won) in enumerate(games)]
    return acc


@_with_ceilings
def test_no_record_keeps_the_formula_cap():
    acc = _account([])
    for ceiling, mode in ((0.7, "half_cash"), (0.06, "impoppable"), (1.2, "half_cash")):
        assert abs(PL.ceiling_band_cap(acc, ceiling, mode) - PL._formula_ceiling_cap(ceiling)) < 1e-12
    # without an account ceiling_cap is the formula, as before
    assert PL.ceiling_cap(0.9, "Mesa", "half_cash") == PL._formula_ceiling_cap(0.7)


@_with_ceilings
def test_a_band_won_often_lifts_its_cap():
    """Half of 40 multi-life games under a 0.5-1.0 ceiling won: the cap of
    an untried map in that band moves from the formula's 0.23 most of the
    way to 0.5. A 1.2 ceiling is another band and keeps its formula cap."""
    acc = _account([("Erosion", "half_cash", i % 2 == 0) for i in range(40)])
    formula = PL._formula_ceiling_cap(0.7)
    cap = PL.ceiling_cap(0.9, "Mesa", "half_cash", acc)
    assert formula < cap < 0.5
    assert abs(cap - (20 + PL.CEILING_BAND_PRIOR_GAMES * formula) / (40 + PL.CEILING_BAND_PRIOR_GAMES)) < 1e-12
    assert PL.ceiling_cap(0.9, "Bazaar", "half_cash", acc) == PL._formula_ceiling_cap(1.2)
    # a cap never raises a p already under it
    assert PL.ceiling_cap(0.1, "Mesa", "half_cash", acc) == 0.1


@_with_ceilings
def test_one_life_and_multi_life_are_measured_apart():
    """Multi-life wins say nothing for a one-life game under the same band,
    and one-life losses pull the one-life cap under the formula."""
    acc = _account([("Erosion", "half_cash", True)] * 20 + [("Erosion", "impoppable", False)] * 20)
    assert PL.ceiling_band_cap(acc, 0.06, "impoppable") < PL._formula_ceiling_cap(0.06)
    assert PL.ceiling_band_cap(acc, 0.7, "half_cash") > 0.8


@_with_ceilings
def test_the_band_record_follows_new_games():
    acc = _account([("Erosion", "half_cash", False)] * 10)
    low = PL.ceiling_band_cap(acc, 0.7, "half_cash")
    acc.history.append({"t": "2026-11-12T00:00:00", "map": "Erosion", "mode": "half_cash",
                        "strategy": "x", "won": True})
    assert PL.ceiling_band_cap(acc, 0.7, "half_cash") > low


def test_ceiling_bands():
    assert PL._ceiling_band(0.0) == 0
    assert PL._ceiling_band(PL.HOPELESS_CEILING - 1e-9) == 0
    assert PL._ceiling_band(PL.HOPELESS_CEILING) == 1
    assert PL._ceiling_band(0.7) == 2
    assert PL._ceiling_band(1.4) == 3


def test_map_losses_after_the_first_count_less_with_lives_to_spare():
    f = PL.map_loss_factor
    assert f("half_cash", 0) == f("impoppable", 0) == 1.0
    assert f("half_cash", 1) == f("impoppable", 1) == PL.MAP_LOSS_FACTOR
    assert abs(f("half_cash", 3) - PL.MAP_LOSS_FACTOR * PL.MAP_LOSS_REPEAT_FACTOR ** 2) < 1e-12
    # one-life modes keep 0.7^n down to the floor
    assert abs(f("impoppable", 3) - max(PL.MAP_LOSS_FLOOR, PL.MAP_LOSS_FACTOR ** 3)) < 1e-12
    assert f("impoppable", 10) == f("half_cash", 30) == PL.MAP_LOSS_FLOOR
    assert f("half_cash", 3) > f("impoppable", 3)


def test_optimizer_builds_are_a_family_of_their_own():
    """opt_quad_deflation (2026-11-11) was rated by the generated solo builds'
    Deflation record and lost at round 60: the optimizer's builds are their
    own calibration family now."""
    from btd6bot.planner import StrategySpec
    opt = StrategySpec.from_any({"id": PL.OPTIMIZED_PREFIX + "quad_deflation", "towers": {}, "modes": ["deflation"],
                                 "base_success": {"deflation": 0.88}, "xp_target": "ice", "maps": ["Quad"]})
    solo = StrategySpec.from_any({"id": "solo_dart", "towers": {}, "modes": ["deflation"],
                                  "base_success": {"deflation": 0.8}, "xp_target": "dart"})
    assert PL.build_family(opt) == "optimized"
    assert PL.build_family(solo) == "solo"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
