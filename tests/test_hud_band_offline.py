"""No tower goes under the HUD (placement.hud_zones) - no game needed.

Erosion Reverse, 2026-11-06 13:20: four surplus snipers were bought at
y=0.070, x 0.724-0.836, under the round counter and settings gear. A click
there lands on the HUD, so none of them could be selected; each was
"forgotten" after two failed selections and bought again.

Quad Impoppable, 2026-11-12 08:51 (loss case 20261112_085548_Quad_impoppable):
the lives and cash bar top left does the same. Aces pinned at 0.056,0.095
(under the heart) and 0.147,0.095 (under the coin) and a bomb at 0.216,0.078
(under the cash digits) stood but were never selected, so their upgrades
never came; round 63 was lost.

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
    (x0, y0, x1, y1), *top_left = PL.hud_zones()
    assert top_left == PL.top_left_hud_zones()
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


def test_the_top_left_bar_follows_the_layout():
    """The heart, lives and coin zone ends at the calibrated lives/cash
    crops' bottom; the digits zone starts at the cash crop and spans it."""
    lay = L.LAYOUTS["16:10"]
    (ix0, iy0, ix1, iy1), (dx0, dy0, dx1, dy1) = PL.top_left_hud_zones()
    assert (ix0, iy0) == (PF[0], PF[1]) and ix1 == lay["cash"][0] == dx0
    assert iy1 == max(lay["lives"][3], lay["cash"][3])
    assert dx1 == lay["cash"][2] and dy0 == PF[1] and dy1 < iy1


def test_quad_towers_stay_out_from_under_the_lives_and_cash_bar():
    """The three Quad spots of 2026-11-12 08:51 that could not be selected,
    and the Deflation sniper's two of 2026-11-11, are no legal spot any
    more; the spots where towers were selected stay legal ground."""
    m = _model("Quad")
    band = PL.hud_cells(m)
    for fx, fy in ((0.056, 0.095), (0.147, 0.095), (0.216, 0.078),   # ac1, ac2, b1 (Quad Impoppable)
                   (0.024, 0.078), (0.056, 0.104)):                  # sni16 (2026-11-11)
        cx, cy = m.frac_to_cell(fx, fy)
        assert band[cy, cx], (fx, fy)
    for fx, fy in ((0.024, 0.138), (0.142, 0.112), (0.163, 0.112),    # selected and upgraded
                   (0.232, 0.095), (0.259, 0.095), (0.024, 0.129)):
        cx, cy = m.frac_to_cell(fx, fy)
        assert not band[cy, cx], (fx, fy)
    for kind in ("ace", "bomb", "sniper"):
        ok = PL.valid_spots(m, kind)
        assert not (ok & band).any(), kind


if __name__ == "__main__":
    test_band_follows_the_layout()
    test_erosion_snipers_stay_out_of_the_band()
    test_the_top_left_bar_follows_the_layout()
    test_quad_towers_stay_out_from_under_the_lives_and_cash_bar()
    print("hud band: OK")
