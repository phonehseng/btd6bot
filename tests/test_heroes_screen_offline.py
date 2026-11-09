"""The HEROES screen is recognised on a hero's skin page (meta.Meta._on_heroes).

Live 2026-11-08 from 19:23: after the bot bought Obyn's Mountain Guardian skin
(Lookin fab), opening HEROES showed that skin's page. At full screen size OCR
did not read its green "Selected" and the title holds a single hero name, so
_on_heroes said no; every game until the fix kept Obyn instead of the build's
hero. The fixture is a frame of rec_20261108_214000.mkv (1280x800), resized
to the live screen sizes here.
Run: python tests/test_heroes_screen_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2  # noqa: E402

from btd6bot.menus import Menus  # noqa: E402
from btd6bot.meta import Meta  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "heroes_obyn_skin_page.jpg"


class _Screen:
    def __init__(self, img):
        self.img = img

    def grab(self):
        return self.img


def _on_heroes(width):
    frame = cv2.imread(str(FIXTURE))
    frame = cv2.resize(frame, (width, width * 10 // 16))
    meta = Meta.__new__(Meta)          # only _on_heroes and its menu reader are used
    meta.m = Menus(_Screen(frame), None)
    meta.m.read()
    return meta._on_heroes()


def test_the_skin_page_counts_as_the_heroes_screen():
    for width in (1280, 1920, 2560):
        assert _on_heroes(width), width


if __name__ == "__main__":
    test_the_skin_page_counts_as_the_heroes_screen()
    print("ok")
