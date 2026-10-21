"""Dev helper: play N rounds without placing anything and learn the track.

Usage: python tools/trace.py "Monkey Meadow" 3 [debug.png]
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L  # noqa: E402
from btd6bot.inputs import Input  # noqa: E402
from btd6bot.maplearn import MapModel, PathTracer  # noqa: E402
from btd6bot.screen import Screen  # noqa: E402
from btd6bot.templates import classify  # noqa: E402

BTN = (0.905, 0.835, 1.0, 0.975)


def state(frame):
    return classify(frame, ["play_idle", "play_run", "play_fast"], BTN)[0]


if __name__ == "__main__":
    name, rounds = sys.argv[1], int(sys.argv[2])
    s = Screen()
    inp = Input(s)
    lay = L.get(s.width, s.height)
    m = MapModel.load(name, lay["playfield"])
    tr = PathTracer(m)
    s.focus()
    for r in range(rounds):
        while state(s.grab()) != "play_idle":
            time.sleep(0.3)
        inp.press("space")
        time.sleep(0.3)
        if state(s.grab()) == "play_run":
            inp.press("space")  # fast forward
        tr.start_round()
        t = time.time()
        while True:
            f = s.grab()
            if state(f) == "play_idle" and time.time() - t > 2:
                break
            tr.feed(f)
            time.sleep(0.05)
        tr.end_round()
        print(f"round traced in {time.time() - t:.1f}s, track cells={m.track_mask().sum()}")
    m.save()
    if len(sys.argv) > 3:
        cv2.imwrite(sys.argv[3], m.debug_image())
