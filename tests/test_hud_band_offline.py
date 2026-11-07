"""No tower goes under the round counter (placement.hud_zones) - no game needed.

Erosion Reverse, 2026-11-06 13:20: four surplus snipers were bought at
y=0.070, x 0.724-0.836, under the round counter and settings gear. A click
there lands on the HUD, so none of them could be selected; each was
"forgotten" after two failed selections and bought again.

Run: python tests/test_hud_band_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L, mapgeom, placement as PL  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = L.LAYOUTS["16:10"]["playfield"]


def _model(name):
    m = MapModel(name, PF)
    mapgeom.apply(m, mapgeom.load(name))
    return m


def test_band_follows_the_layout():
    (x0, y0, x1, y1), = PL.hud_zones()
    lay = L.LAYOUTS["16:10"]
    assert x0 == lay["round"][0] and x1 == PF[2]          # from the counter to the field's edge
    assert y0 == PF[1] and y1 >= lay["round"][3]           # the counter's full height
    assert x0 <= lay["gear"][0] <= x1                     # the gear is inside


def test_erosion_snipers_stay_out_of_the_band():
    m = _model("Erosion")
    ok = PL.valid_spots(m, "sniper")
    for fx in (0.724, 0.761, 0.799, 0.836):               # the four snipers of 2026-11-06
        cx, cy = m.frac_to_cell(fx, 0.070)
        assert not ok[cy, cx], fx
    band = PL.hud_cells(m)
    assert band.any() and not (ok & band).any()
    # the lives and cash bar (top left) stays usable: towers there were selected fine
    cx, cy = m.frac_to_cell(0.142, 0.095)
    assert not band[cy, cx]


if __name__ == "__main__":
    test_band_follows_the_layout()
    test_erosion_snipers_stay_out_of_the_band()
    print("hud band: OK")
