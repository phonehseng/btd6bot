"""Dev helper: save the current game frame (optionally downscaled) for inspection.

Usage: python tools/shot.py out.jpg [width] [x0 y0 x1 y1]
"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.screen import Screen  # noqa: E402

if __name__ == "__main__":
    out = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 960
    region = tuple(map(float, sys.argv[3:7])) if len(sys.argv) >= 7 else None
    img = Screen().grab(region)
    h, w = img.shape[:2]
    if width and w > width:
        img = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, img)
    print(out, img.shape)
