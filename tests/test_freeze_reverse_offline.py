"""Glacial Trail's tower freeze applies in Reverse games too
(dps_model._freeze_cycle).

Glacial Trail Reverse (2026-11-11): the map model of a Reverse game is
keyed "Glacial Trail reverse". The freeze table knows "Glacial Trail", so
the lookup found no freeze. sp1, frozen in round 34, failed two
selections and was forgotten as "not on the map" (Executor._forget_if_missing
keeps towers only on freezing maps). Its Spiked Mines were never bought,
and round 44 took all 150 lives."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import dps_model as D  # noqa: E402


def test_reverse_names_freeze_like_the_map():
    for name in ("Glacial Trail reverse", "GlacialTrailreverse", "glacialtrailreverse"):
        assert D.tower_uptime(name) == D.tower_uptime("Glacial Trail") < 1.0, name
        assert D.frozen_in(name, 15, 34) and not D.frozen_in(name, 15, 33), name


def test_maps_without_a_freeze_stay_unfrozen():
    for name in ("Logs", "Logs reverse", "Reverse", ""):
        assert D.tower_uptime(name) == 1.0, name
        assert not D.frozen_in(name, 15, 34), name


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
