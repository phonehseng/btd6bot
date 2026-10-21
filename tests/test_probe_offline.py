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


if __name__ == "__main__":
    test_probe_reads_red_ring()
    print("ok")
