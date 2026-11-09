"""Placement probe on real captures: dart held over the path (invalid) and grass (valid)."""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot.game import Game  # noqa: E402

FX = ROOT / "tests" / "fixtures"


class _NoInput:
    def move(self, *a, **k):
        pass


def _game(frame, kind="dart"):
    g = Game.__new__(Game)
    g.inp, g._held_kind, g.hero = _NoInput(), kind, "quincy"
    g.fresh = lambda: frame
    return g


def test_probe_reads_red_ring():
    base = cv2.imread(str(FX / "probe_none.jpg"))
    assert _game(cv2.imread(str(FX / "probe_inv.jpg"))).probe(0.30, 0.43, base, settle=0) is False
    assert _game(cv2.imread(str(FX / "probe_val.jpg"))).probe(0.40, 0.50, base, settle=0) is True


# Tricky Tracks ABR (2026-11-09 02:55, recording rec_20261109_0255): the ace
# answer for round 40's MOAB was refused on 16 spots in a row. The probe had
# passed every one: it sampled a ring sized for a range of 12, which lies on
# the ace's own runway sprite, while the red circle round a refused ace is
# drawn at its model range of 22. Fixtures (1280x800): the ground with no
# tower held, the ace held over a refused spot near the track (red circle),
# the ground a moment before the spot that was accepted on the train, and the
# ace held there (grey circle).

def test_ace_probe_sees_the_red_circle_round_its_runway():
    base = cv2.imread(str(FX / "tricky_ace_none.jpg"))
    inv = cv2.imread(str(FX / "tricky_ace_inv.jpg"))
    for fx, fy in ((0.339, 0.760), (0.323, 0.777)):
        assert _game(inv, "ace").probe(fx, fy, base, settle=0) is False, (fx, fy)


def test_ace_probe_passes_the_spot_the_game_took():
    base = cv2.imread(str(FX / "tricky_ace_none_late.jpg"))
    val = cv2.imread(str(FX / "tricky_ace_val.jpg"))
    assert _game(val, "ace").probe(0.772, 0.606, base, settle=0) is True


def test_held_range_falls_back_to_the_game_model():
    assert _game(None, "ace")._held_range() == 22
    assert _game(None, "heli")._held_range() == 22
    assert _game(None, "dart")._held_range() == 32


if __name__ == "__main__":
    test_probe_reads_red_ring()
    test_ace_probe_sees_the_red_circle_round_its_runway()
    test_ace_probe_passes_the_spot_the_game_took()
    test_held_range_falls_back_to_the_game_model()
    print("ok")
