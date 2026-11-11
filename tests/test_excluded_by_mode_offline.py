"""A build can be kept off one map in one mode only
(StrategySpec.excluded_by_mode, YAML planner.excluded_by_mode).

#Ouch Half Cash (2026-11-10 and 2026-11-11, twice): hard_ninja_alch_sun
lost round 27 three times running. Excluding #Ouch for the build as a
whole would also drop it from #Ouch Hard, which is still open, so the
exclusion names the mode."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import planner as P  # noqa: E402


def spec(**kw):
    return P.StrategySpec(id="t", towers={}, modes=frozenset({"hard", "half_cash"}), **kw)


def test_the_named_mode_is_excluded_and_the_others_are_not():
    s = spec(excluded_by_mode={"half_cash": frozenset({"#Ouch"})})
    assert not P._strategy_fits(s, "#Ouch", "expert", "half_cash")
    assert P._strategy_fits(s, "#Ouch", "expert", "hard")
    assert P._strategy_fits(s, "Logs", "beginner", "half_cash")


def test_the_live_build_keeps_ouch_half_cash_out():
    import yaml
    raw = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "strategies/hard_ninja_alch_sun.yaml",
                              encoding="utf-8"))
    assert "#Ouch" in raw["planner"]["excluded_by_mode"]["half_cash"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
