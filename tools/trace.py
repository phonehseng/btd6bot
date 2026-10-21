"""Dev helper: play N rounds without placing anything and learn the track.

Usage: python tools/trace.py "Monkey Meadow" 3 [debug.png]
Expects a fresh game at round 1 with Auto Start enabled.
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L  # noqa: E402
from btd6bot.hud import Hud  # noqa: E402
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
    hud = Hud(lay)
    m = MapModel.load(name, lay["playfield"])
    tr = PathTracer(m)
    s.focus()
    if state(s.grab()) == "play_idle":
        inp.press("space")
        time.sleep(0.3)
    if state(s.grab()) == "play_run":
        inp.press("space")  # fast forward
    cur = hud.round(s.grab())
    tr.start_round()
    done, t = 0, time.time()
    while done < rounds:
        f = s.grab()
        tr.feed(f)
        r = hud.round(f)
        if r is not None and cur is not None and r > cur:
            tr.end_round()
            done += 1
            print(f"round {cur} traced in {time.time() - t:.1f}s, track cells={m.track_mask().sum()}")
            cur, t = r, time.time()
            tr.start_round()
        elif cur is None:
            cur = r
        time.sleep(0.03)
    m.save()
    if len(sys.argv) > 3:
        cv2.imwrite(sys.argv[3], m.debug_image())
