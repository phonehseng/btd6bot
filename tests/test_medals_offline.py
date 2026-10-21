"""Offline check of medal reading on the saved map-select capture."""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot.medals import read_card  # noqa: E402


def test_monkey_meadow_easy_only():
    img = cv2.imread(str(ROOT / "docs" / "screens" / "search.jpg"))
    # Monkey Meadow's label centre on that screen (OCR: 0.255, 0.197)
    assert read_card(img, 0.255, 0.197) == {"easy": True, "medium": False, "hard": False,
                                            "impoppable": False}


def test_unplayed_cards_empty():
    img = cv2.imread(str(ROOT / "docs" / "screens" / "search.jpg"))
    for x, y in [(0.499, 0.197), (0.746, 0.197), (0.253, 0.487), (0.5, 0.488), (0.746, 0.488)]:
        assert not any(read_card(img, x, y).values()), (x, y)


if __name__ == "__main__":
    test_monkey_meadow_easy_only()
    test_unplayed_cards_empty()
    print("ok")
