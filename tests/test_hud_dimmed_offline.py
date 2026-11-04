"""The Play button under the Defeat / Victory card does not count as the HUD.

Quad Reverse (2026-11-04, case 20261104_071253): the template match ignores
brightness, so the dimmed Play button behind the Defeat card still scored
0.96 and Game.screen_ok() let clicks through - one opened the Restart dialog,
next to the Monkey-Money Continue button. hud_visible() now also wants the
button lit. The test builds a frame from the captured template itself, so it
needs neither the game nor the loss stills.
Run: python tests/test_hud_dimmed_offline.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import templates  # noqa: E402
from btd6bot.game import PLAY_BTN, PLAY_LIT_MIN, hud_visible  # noqa: E402

H, W = 1200, 1920


def frame_with_button(dim=1.0):
    """A grey 1920x1200 frame with the fast-forward button pasted inside the
    Play-button region, everything multiplied by `dim` (an overlay)."""
    f = np.full((H, W, 3), 110, np.uint8)
    tpl = templates.load("play_fast", H)
    x0, y0 = int(PLAY_BTN[0] * W) + 20, int(PLAY_BTN[1] * H) + 15
    f[y0:y0 + tpl.shape[0], x0:x0 + tpl.shape[1]] = tpl
    return (f * dim).astype(np.uint8)


def test_lit_button_is_the_hud():
    assert hud_visible(frame_with_button())


def test_end_card_dimming_hides_the_hud():
    # 0.36 of the lit brightness was measured under the Defeat card, 0.18
    # while it fades in
    for dim in (0.36, 0.18):
        assert not hud_visible(frame_with_button(dim)), dim


def test_no_button_no_hud():
    assert not hud_visible(np.full((H, W, 3), 110, np.uint8))


def test_threshold_between_lit_and_dimmed():
    assert 0.36 < PLAY_LIT_MIN < 0.99


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
