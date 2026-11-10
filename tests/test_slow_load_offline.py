"""Offline check for runner.Bot.start: a map that takes 45 s to load after the
mode click still starts (Bot.LOAD_WAIT_S), and one that never loads fails.

Five Apopalypse loads on 2026-11-09/10 took 33-48 s; with the old 30 s wait
each was logged "failed to start", left from the pause menu and benched for
2 hours. Run: python tests/test_slow_load_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import runner  # noqa: E402


class Clock:
    """Stands in for the time module: sleeping and waiting move it forward."""
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeMenus:
    """Menus whose map takes `load_s` seconds after the mode click to show
    the mode's intro box (None: never)."""
    def __init__(self, clock, load_s):
        self.clock, self.load_s = clock, load_s
        self.clicked_mode_at = None
        self.intro_pressed = False

    def read(self):
        return []

    def click_word(self, *words, **kw):
        if self.clicked_mode_at is None and words and words[0] != "hard":
            self.clicked_mode_at = self.clock.t
        return True

    def identify(self, read=True):
        return "unknown"

    def wait_for(self, states, timeout=3):
        self.clock.t += timeout
        if states == "mode_select":
            return "mode_select"
        if self.clicked_mode_at is None:
            return "mode_select"
        if self.intro_pressed:
            return "in_game"
        loaded = self.load_s is not None and self.clock.t - self.clicked_mode_at >= self.load_s
        return "mode_intro_play" if loaded else "unknown"

    def dismiss_popup(self):
        pass

    def in_game(self):
        return False


def start(load_s):
    clock = Clock()
    bot = runner.Bot.__new__(runner.Bot)
    bot.account = N(has_medal=lambda m, k: False)
    bot.open_map = lambda name: True
    bot.menus = FakeMenus(clock, load_s)
    bot.inp = N(click=lambda x, y: None)
    bot._close_mode_intro = lambda: None

    def press():
        bot.menus.intro_pressed = True
    bot._press_intro_play = press
    plan = N(map="Sanctuary", mode="apopalypse", mode_key="apopalypse", difficulty="hard",
             first_time=False)
    real = runner.time
    runner.time = clock
    try:
        return bot.start(plan)
    finally:
        runner.time = real


def test_a_slow_load_still_starts():
    assert start(45) is True


def test_a_map_that_never_loads_fails():
    assert start(None) is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
