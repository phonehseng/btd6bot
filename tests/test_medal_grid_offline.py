"""Map-select card medals and card frames on live screenshots.

tests/fixtures/medal_pages holds five of the 17 map-select pages captured on
2026-11-06 (1920x1200), cropped to the two bands that carry the card frames
and the medals. Every expected value below was read by eye on zoomed crops
and agrees with the game's own mode screens: Lotus Island shows Military Only
and Reverse earned, Apopalypse, Half Cash and CHIMPS not. The reader of that
morning had Apopalypse/Reverse, ABR/Double HP and Half Cash mixed up.
The older docs/screens captures are skipped when absent."""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from btd6bot.medals import (GRID_DY, MODE_POINTS, card_is_confident, grid_card_frame,  # noqa: E402
                            grid_cell, read_grid_card, read_grid_detail)

SHOTS = ROOT / "docs" / "screens"
CASES = {
    ("mapselect_all.png", 0, 0): set(MODE_POINTS),
    ("mapselect_all.png", 1, 1): set(MODE_POINTS),
    ("mapselect_expert.png", 0, 0): {"hard"},
    ("mapselect_expert.png", 1, 0): {"hard"},
    ("mapselect_expert.png", 2, 0): {"hard", "abr"},
    ("mapselect_expert.png", 0, 1): {"easy", "primary_only", "deflation", "hard", "abr", "impoppable"},
    ("mapselect_expert.png", 1, 1): {"hard", "abr", "impoppable"},
    ("mapselect_expert.png", 2, 1): {"hard"},
}

# -- the 2026-11-06 carousel ---------------------------------------------------
PAGES = ROOT / "tests" / "fixtures" / "medal_pages"
SCREEN = (1200, 1920)
BAND_X, BAND_Y = (285, 1645), (255, 470)   # crop of each card row (row 0; row 1 is GRID_DY lower)
CELLS = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]
CARDS = {   # page -> card names in grid order (CELLS)
    "page01": ["Park Path", "Alpine Run", "Frozen Over", "Cubism", "Four Circles", "Hedge"],
    "page02": ["Logs", "End Of The Road"],
    "page04": ["Covered Garden", "Quarry", "Quiet Street", "Bloonarius Prime", "Balance", "Encrypted"],
    "page12": ["Tricky Tracks", "Glacial Trail", "Dark Dungeons", "Sanctuary", "Ravine", "Flooded Valley"],
    "page17": ["Resort", "Skates", "Lotus Island", "Candy Falls", "Winter Park", "Carved"],
}
# medals each card does NOT show (empty: all 14, a black border)
MISSING = {
    "Park Path": {"apopalypse", "half_cash"},
    "Alpine Run": {"apopalypse", "chimps"},
    "Frozen Over": {"apopalypse", "half_cash", "chimps"},
    "Cubism": set(),
    "Four Circles": set(),
    "Hedge": {"apopalypse", "half_cash", "chimps"},
    "Logs": set(),
    "End Of The Road": {"apopalypse", "half_cash", "chimps"},
    "Covered Garden": set(MODE_POINTS) - {"easy", "primary_only"},
    "Quarry": {"apopalypse", "half_cash", "chimps"},
    "Quiet Street": {"apopalypse", "half_cash", "impoppable", "chimps"},
    "Bloonarius Prime": {"apopalypse", "magic_only", "double_hp", "half_cash", "abr", "impoppable", "chimps"},
    "Balance": {"apopalypse", "double_hp", "half_cash", "impoppable", "chimps"},
    "Encrypted": {"apopalypse", "double_hp", "half_cash", "impoppable", "chimps"},
    "Tricky Tracks": set(MODE_POINTS) - {"hard"},
    "Glacial Trail": set(MODE_POINTS) - {"hard"},            # ice thumbnail
    "Dark Dungeons": set(MODE_POINTS) - {"easy", "medium", "reverse", "hard", "abr"},
    "Sanctuary": set(MODE_POINTS) - {"easy", "primary_only", "deflation", "hard", "abr", "impoppable"},
    "Ravine": {"apopalypse", "magic_only", "double_hp", "half_cash", "chimps"},
    "Flooded Valley": set(MODE_POINTS) - {"easy", "medium", "military_only", "reverse", "hard"},  # water
    "Resort": set(),
    "Skates": {"apopalypse", "half_cash", "chimps"},
    "Lotus Island": {"apopalypse", "half_cash", "chimps"},
    "Candy Falls": {"apopalypse", "half_cash"},
    "Winter Park": {"apopalypse", "half_cash", "chimps"},
    "Carved": {"apopalypse", "half_cash", "chimps"},
}


def load_page(stem):
    """A full-size frame with the fixture's two card-row bands put back in place."""
    bands = cv2.imread(str(PAGES / f"{stem}.jpg"))
    h = BAND_Y[1] - BAND_Y[0]
    frame = np.zeros(SCREEN + (3,), np.uint8)
    for row in range(2):
        y0 = BAND_Y[0] + GRID_DY * row
        frame[y0:y0 + h, BAND_X[0]:BAND_X[1]] = bands[h * row:h * (row + 1)]
    return frame


def page_cards():
    """(name, frame, col, row) for every card on the fixture pages."""
    for stem, names in CARDS.items():
        frame = load_page(stem)
        for name, (col, row) in zip(names, CELLS):
            yield name, frame, col, row


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


def test_carousel_cards_read_what_they_show():
    """Complete cards read all 14; partial ones (water and ice thumbnails,
    tan and orange frames) exactly the medals they show, every one clearly."""
    for name, frame, col, row in page_cards():
        detail = read_grid_detail(frame, col, row)
        unsure = [m for m, state in detail.items() if state is None]
        assert not unsure, (name, unsure)
        missing = {m for m, earned in detail.items() if not earned}
        assert missing == MISSING[name], (name, "wrong:", sorted(missing ^ MISSING[name]))


def test_lotus_island_matches_its_mode_screens():
    """The incident: the 03:31 scan took Lotus Island's purple Reverse medal
    for Apopalypse."""
    frame = load_page("page17")
    got = read_grid_card(frame, 2, 0)
    assert got["military_only"] and got["reverse"]
    assert not got["apopalypse"] and not got["half_cash"] and not got["chimps"]


def test_card_frame_tells_black_borders():
    for name, frame, col, row in page_cards():
        want = "black" if not MISSING[name] else "gold"
        assert grid_card_frame(frame, col, row) == want, name
        assert card_is_confident(read_grid_detail(frame, col, row), want), name


def test_unclear_cards_are_not_confident():
    frame = load_page("page01")
    blank = np.zeros_like(frame)
    assert grid_card_frame(blank, 0, 0) is None, "no card there: no frame"
    assert not card_is_confident(read_grid_detail(blank, 0, 0), None)
    # a page caught half-way: the frame of one card, the medals of another
    medals = read_grid_detail(frame, 0, 0)            # Park Path, partial
    assert not card_is_confident(medals, "black"), "a black frame needs all 14"
    complete = read_grid_detail(frame, 0, 1)          # Cubism, all 14
    assert not card_is_confident(complete, "gold"), "all 14 under a gold frame"
    assert not card_is_confident(dict(complete, chimps=None), "black"), "an unsure medal"


def test_grid_cell():
    assert grid_cell(0.246, 0.128) == (0, 0)
    assert grid_cell(0.745, 0.418) == (2, 1)
    assert grid_cell(0.06, 0.83) is None


if __name__ == "__main__":
    test_grid_cards()
    test_carousel_cards_read_what_they_show()
    test_lotus_island_matches_its_mode_screens()
    test_card_frame_tells_black_borders()
    test_unclear_cards_are_not_confident()
    test_grid_cell()
    print("ok")
