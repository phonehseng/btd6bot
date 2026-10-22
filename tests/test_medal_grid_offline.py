"""Map-select card medals on live screenshots (skipped when the captures are absent)."""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from btd6bot.medals import MODE_POINTS, grid_cell, read_grid_card  # noqa: E402

SHOTS = ROOT / "docs" / "screens"
CASES = {
    ("mapselect_all.png", 0, 0): set(MODE_POINTS),
    ("mapselect_all.png", 1, 1): set(MODE_POINTS),
    ("mapselect_expert.png", 0, 0): {"hard"},
    ("mapselect_expert.png", 1, 0): {"hard"},
    ("mapselect_expert.png", 2, 0): {"hard", "double_hp"},
    ("mapselect_expert.png", 0, 1): {"easy", "primary_only", "deflation", "hard", "double_hp", "impoppable"},
    ("mapselect_expert.png", 1, 1): {"hard", "double_hp", "impoppable"},
    ("mapselect_expert.png", 2, 1): {"hard"},
}


def test_grid_cards():
    ran = 0
    for (name, col, row), want in CASES.items():
        p = SHOTS / name
        if not p.exists():
            continue
        got = {m for m, e in read_grid_card(cv2.imread(str(p)), col, row).items() if e}
        assert got == want, (name, col, row, sorted(got ^ want))
        ran += 1
    assert ran or not SHOTS.exists()


def test_grid_cell():
    assert grid_cell(0.246, 0.128) == (0, 0)
    assert grid_cell(0.745, 0.418) == (2, 1)
    assert grid_cell(0.06, 0.83) is None


if __name__ == "__main__":
    test_grid_cards()
    test_grid_cell()
    print("ok")
