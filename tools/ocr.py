"""Dev helper: OCR the current game screen and print every word with its position.

Usage: python tools/ocr.py [x0 y0 x1 y1]   (fractions; default whole screen)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.screen import Screen  # noqa: E402
from btd6bot.vision import Vision  # noqa: E402

if __name__ == "__main__":
    region = tuple(map(float, sys.argv[1:5])) if len(sys.argv) >= 5 else (0, 0, 1, 1)
    s = Screen()
    v = Vision(s)
    t = time.time()
    words = v.read(region)
    for w in sorted(words, key=lambda w: (round(w.y, 2), w.x)):
        print(f"{w.x:.3f} {w.y:.3f}  {w.text}  ({w.conf:.2f})")
    print(f"-- {len(words)} words in {time.time() - t:.2f}s")
