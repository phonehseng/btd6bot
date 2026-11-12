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


def _live_specs():
    """Planner specs of the strategy files, as runner.planner_specs builds them."""
    from btd6bot import strategy as S
    return {sid: P.StrategySpec.from_any(dict(s, id=sid, **(s.get("planner") or {})))
            for sid, s in S.load_all().items() if not s.get("achievement")}


def test_the_sniper_build_is_kept_off_last_resort_abr_only():
    """Last Resort ABR (2026-11-10 and 2026-11-12): double_hp_sniper_sun lost
    all 100 lives on rounds 27-28, right after the Fast Track start, both
    times. It stays a candidate for the map's Double HP medal, and Last
    Resort ABR keeps other builds to play (the bot never idles on an open
    medal)."""
    specs = _live_specs()
    sniper = specs["double_hp_sniper_sun"]
    assert not P._strategy_fits(sniper, "Last Resort", "advanced", "abr")
    assert P._strategy_fits(sniper, "Last Resort", "advanced", "double_hp")
    others = [sid for sid, s in specs.items() if P._strategy_fits(s, "Last Resort", "advanced", "abr")]
    assert "military_heli_sniper" in others and "abr_ninja_alch" in others, others


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
