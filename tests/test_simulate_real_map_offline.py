"""The offline simulator can play a build on the map's own geometry.

tools/simulate_threats.py used to place every tower on an open field
(OpenModel), where no track is known, so the blimp check fell back to
"2.5 x range" of track per tower on every map. With real_map=True it fills a
MapModel from data/map_geometry instead: the executor picks spots on the real
ground and measures each tower's reach from the track cells in its range.
Checked here: the model has a track, the executor gets a real reach function
on it, the simulation still runs to the end with ratios, and a map without
geometry falls back to the open field.
Run: python tests/test_simulate_real_map_offline.py"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import strategy as S   # noqa: E402
import simulate_threats as SIM      # noqa: E402

MAP = "Cargo"
STRATEGY, MODE = "military_sub_sniper_water", "medium"


def test_map_model_has_a_track():
    m = SIM.map_model(MAP)
    assert m is not None, f"{MAP} has geometry"
    assert int(m.track_mask().sum()) >= 30, "the track mask is what the reach is measured on"


def test_executor_measures_reach_on_the_track():
    g = SIM.CashGame("medium")
    ex = S.Executor(g, SIM.map_model(MAP), S.load_all()[STRATEGY], MODE, SIM.full_account())
    ex._init_threats()     # the threat state is set up on first use, as in a game
    assert ex._reach_fn() is not None, "a real map gives a real reach function"
    open_ex = S.Executor(g, SIM.OpenModel(MAP), S.load_all()[STRATEGY], MODE, SIM.full_account())
    open_ex._init_threats()
    assert open_ex._reach_fn() is None, "the open field has no track: threats uses 2.5 x range"


def test_simulation_runs_on_the_real_map():
    r = SIM.simulate(S.load_all()[STRATEGY], MODE, MAP, real_map=True)
    assert dict(r["ramp"]).get(40) is not None, "round 40 (first MOAB) is rated"
    assert r["spent"] > 0


def test_unknown_map_falls_back_to_open_field():
    assert SIM.map_model("No Such Map") is None
    r = SIM.simulate(S.load_all()[STRATEGY], MODE, "No Such Map", real_map=True)
    assert r["ramp"], "the open field still rates the blimp rounds"


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
