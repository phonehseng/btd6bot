"""Lives OCR must not read the heart icon's rim as a digit (layout 'lives').

With bonus lives the heart wears a pale ring. The old crop began on that ring
and OCR read it as a leading '2': Polyphemus Apopalypse showed 86 lives and
the bot read 286 for 30 rounds, so every leak went unseen until the defeat
(Ravine Easy: 200 read as 2200). The fixtures are the HUD's top-left corner
of two recorded frames (960x600 window); the rest of the frame is blank.
Run: python tests/test_lives_ocr_offline.py"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.hud import parse_int, rec_text  # noqa: E402
from btd6bot.layout import LAYOUTS  # noqa: E402
from btd6bot.vision import crop  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = (600, 960)   # height, width of the recorded frames


def lives_in(fixture):
    """Paste the saved HUD corner into a blank window and read the lives."""
    corner = cv2.imread(str(FIXTURES / fixture))
    frame = np.zeros(WINDOW + (3,), np.uint8)
    frame[:corner.shape[0], :corner.shape[1]] = corner
    return parse_int(rec_text(crop(frame, LAYOUTS["16:10"]["lives"]))[0])


def test_ringed_heart_is_not_a_digit():
    assert lives_in("hud_lives_ring_86.jpg") == 86
    assert lives_in("hud_lives_ring_200.jpg") == 200


if __name__ == "__main__":
    test_ringed_heart_is_not_a_digit()
    print("ok")
