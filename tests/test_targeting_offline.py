"""Targeting labels that wrap onto two lines are still read: a heli's
"LOCK IN / PLACE" and "FOLLOW / MOUSE" (Pat's Pond, 2026-10-23), which the
one-line recogniser turned into "Ck" and "FMOLLSW". Offline: saved frames."""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L                 # noqa: E402
from btd6bot.vision import Vision, norm        # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def label(name):
    """The targeting button's words, read the way Game.target reads them."""
    img = cv2.imread(str(FIX / name))
    x0, y0, x1, y1 = L.get(1920, 1200)["upg_left"]["target_text"]
    words = Vision(N(grab=lambda region=None: img)).read(region=(x0, y0 - 0.012, x1, y1 + 0.012), img=img)
    return norm(" ".join(w.text for w in words))


def test_lock_in_place_is_read():
    assert "lock" in label("target_heli_lock.jpg")


def test_follow_mouse_is_read():
    assert "follow" in label("target_heli_follow.jpg")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
