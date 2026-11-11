"""A stray mode click must not cover the match HUD, and a box that does is
closed during the opening build (no game needed).

Sunken Columns Double HP (2026-11-09 07:53): the first click on the mode's
slot started the map loading; the wait after it ended on a look taken before
the game reacted, so the runner clicked the slot again - over the LOADING
screen. That click reached the map as it appeared, hit the water and opened
"Remove for $1,000". Every placement of the opening build then waited
"(screen)" and the game was refused with "no defence could be placed".

Frames from that game's recording (1280x800):
  * sunken_columns_hard_modes.jpg - the Hard mode screen before the click
  * sunken_columns_loading.jpg    - the LOADING screen the second click hit
  * sunken_columns_remove_box.jpg - the "Remove for $1,000" box over the map

Covers:
  * Bot._still_on_mode_select says yes on the mode screen, no on LOADING;
  * Bot.start clicks the mode once when the screen then shows LOADING;
  * Match._setup_screen_check closes the removal box with its red X (never
    the green check) and clears Game.screen_lost once the HUD is back.
Run: python tests/test_game_start_overlay_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import runner as R          # noqa: E402
from btd6bot.match import Match          # noqa: E402
from btd6bot.menus import Menus          # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def frame(name):
    img = cv2.imread(str(FIX / f"sunken_columns_{name}.jpg"))
    assert img is not None, name
    return img


class Screen:
    """A fake game window that shows one frame until told otherwise."""
    def __init__(self, img):
        self.img = img
        self.width, self.height = img.shape[1], img.shape[0]

    def grab(self, region=None):
        return self.img

    def refresh(self):
        pass


class Clicks:
    def __init__(self, on_click=None):
        self.at = []
        self.on_click = on_click

    def click(self, x, y):
        self.at.append((x, y))
        if self.on_click:
            self.on_click(x, y)


def test_mode_screen_and_loading_screen_are_told_apart():
    for name, still in (("hard_modes", True), ("loading", False)):
        bot = R.Bot.__new__(R.Bot)
        bot.menus = Menus(Screen(frame(name)), Clicks())
        bot.menus.read()
        assert bot._still_on_mode_select() is still, name


def test_the_mode_is_clicked_once_when_the_map_starts_loading():
    """The wait after the mode click reports the mode screen (a look taken
    before the game reacted) while the screen already shows LOADING: the
    runner must not click the slot a second time."""
    screen = Screen(frame("hard_modes"))
    inp = Clicks()
    menus = Menus(screen, inp)
    # the difficulty word is clicked; the mode's label is not found (as on
    # 2026-11-09), so the runner clicks the mode's slot
    menus.click_word = lambda *keys, **kw: keys[0] == "hard"

    def wait_for(targets, timeout=6.0, cheap_in_game=True):
        if "mode_intro_play" in targets:
            return "in_game"            # the loading wait: the match is up
        if targets == "mode_select":
            return "mode_select"        # after the difficulty click
        screen.img = frame("loading")   # the mode click took ...
        return "mode_select"            # ... but the look was taken before it
    menus.wait_for = wait_for
    menus.in_game = lambda: True

    bot = R.Bot.__new__(R.Bot)
    bot.menus, bot.inp = menus, inp
    bot.open_map = lambda name, mode=None: True
    bot._close_mode_intro = lambda: None
    plan = N(map="Sunken Columns", difficulty="hard", mode="double_hp", first_time=True, mode_key="double_hp")
    assert bot.start(plan) is True
    assert inp.at == [R.MODE_BUTTON_POS["double_hp"]], inp.at


def test_the_removal_box_is_closed_during_the_opening_build():
    screen = Screen(frame("remove_box"))
    box_cancel = []

    def on_click(x, y):
        # the red X sits left of the box's middle, the green check right of it
        assert x < 0.55, f"clicked ({x:.3f}, {y:.3f}) - that is the green check (buys the removal)"
        box_cancel.append((x, y))
        screen.img = frame("hard_modes")   # anything without the box; the HUD check is faked below

    menus = Menus(screen, Clicks(on_click))
    m = Match.__new__(Match)
    m.menus = menus
    hud = {"up": False}
    m.g = N(screen_lost=True, in_game=lambda: hud["up"])

    original = menus.dismiss_popup

    def dismiss():
        done = original()
        hud["up"] = bool(box_cancel)
        return done
    menus.dismiss_popup = dismiss

    m._setup_screen_check()
    assert len(box_cancel) == 1, box_cancel
    x, y = box_cancel[0]
    assert 0.45 < x < 0.55 and 0.5 < y < 0.62, (x, y)
    assert m.g.screen_lost is False


def test_nothing_is_looked_at_while_the_hud_is_up():
    m = Match.__new__(Match)
    m.menus = N(identify=lambda: (_ for _ in ()).throw(AssertionError("no look needed")))
    m.g = N(screen_lost=False)
    m._setup_screen_check()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
