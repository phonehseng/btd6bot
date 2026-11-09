"""In a no-income mode a general build is kept under the map's own build.

Tricky Tracks Deflation (2026-11-08, loss case 20261108_110044): solo_mortar
was played at p=0.76 over the map's own trickytracks_deflation at about
0.71 and lost round 49 (planner._below_own_build_without_income).
Run: python tests/test_no_income_own_build_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner as P  # noqa: E402


def _cand(s, mode, p, map_name="Tricky Tracks"):
    return P._Cand(map_name, mode, s, p, 0, 8.0, 1000.0, 300.0, True, 0.0, 0.0, 0.0,
                   [f"p={p:.2f} (n=0)"], ok=p >= P.p_threshold(mode))


OWN = P.StrategySpec(id="trickytracks_deflation", towers={}, modes=frozenset({"deflation"}),
                     maps=frozenset({"Tricky Tracks"}))
GENERAL = P.StrategySpec(id="solo_mortar", towers={}, modes=frozenset({"deflation", "medium"}))


def test_general_build_goes_under_the_own_build_in_deflation():
    own, gen = _cand(OWN, "deflation", 0.71), _cand(GENERAL, "deflation", 0.76)
    P._below_own_build_without_income([own, gen], P.DEFAULT_CONFIG)
    assert own.p == 0.71
    assert abs(gen.p - 0.70) < 1e-9, gen.p
    assert "own build" in gen.notes[0]


def test_untouched_with_income_or_without_an_own_build():
    gen_medium = _cand(GENERAL, "medium", 0.76)
    own = _cand(OWN, "deflation", 0.71)
    P._below_own_build_without_income([own, gen_medium], P.DEFAULT_CONFIG)
    assert gen_medium.p == 0.76
    elsewhere = _cand(GENERAL, "deflation", 0.76, map_name="Dark Path")
    P._below_own_build_without_income([own, elsewhere], P.DEFAULT_CONFIG)
    assert elsewhere.p == 0.76
    lower = _cand(GENERAL, "deflation", 0.5)
    P._below_own_build_without_income([own, lower], P.DEFAULT_CONFIG)
    assert lower.p == 0.5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
