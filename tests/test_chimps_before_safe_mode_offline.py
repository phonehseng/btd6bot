"""Safe mode lets Beginner CHIMPS games with the map's own build go first.

The owner's order since 2026-11-05: black borders map tier by tier, Beginner
maps first. Safe mode (the loss circuit breaker) plays only games at
p >= CONFIDENT_P, while an untested map build is capped just under it, so the
Beginner CHIMPS builds would have waited behind every confident game on
every map. The owner chose (2026-11-05 15:30) to let them go first; nothing
else in safe mode changes.
Run: python tests/test_chimps_before_safe_mode_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import runner as R               # noqa: E402
from btd6bot.planner import CATEGORY_EASE     # noqa: E402
from btd6bot.strategy import load_all         # noqa: E402

BEGINNER, ADVANCED = CATEGORY_EASE["beginner"], CATEGORY_EASE["advanced"]


def first(cands, benched=()):
    return R.chimps_before_safe_mode(cands, lambda m, mode: (m, mode) in benched)


def specs():
    return {s.id: s for s in R.planner_specs(load_all(), F.full_account())}


def cand(s, map_name, mode="chimps", ease=BEGINNER, ok=True, tier="HS", p=0.84):
    return NS(s=s, map=map_name, mode=mode, ease=ease, ok=ok, tier=tier, p=p)


def test_only_beginner_chimps_with_the_maps_own_build_go_first():
    sp = specs()
    own, general = sp["endoftheroad_chimps"], sp["chimps_ninja_sun"]
    cands = [cand(own, "End Of The Road"),
             cand(general, "End Of The Road"),                   # not made for the map
             cand(own, "End Of The Road", ok=False, tier=None),  # under its bar
             cand(own, "End Of The Road", mode="hard"),         # not CHIMPS
             cand(own, "End Of The Road", ease=ADVANCED)]       # not a Beginner map
    picked = first(cands)
    assert picked == [cands[0]], picked


def test_a_benched_map_is_not_let_through():
    own = specs()["endoftheroad_chimps"]
    assert first([cand(own, "End Of The Road")], benched={("End Of The Road", "chimps")}) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
