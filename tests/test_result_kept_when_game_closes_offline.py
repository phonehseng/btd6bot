"""A finished game keeps its result when BTD6 closes or loses the front
while the bot leaves the end screen (Bot._leave_finished_game).

Sanctuary Apopalypse (2026-11-10 17:16): lost at round 45, then the game
froze on the loading screen behind the Home button. Closing the frozen game
raised GameNotFound out of Bot.play(), the main loop only waited for the
game, and the defeat was neither recorded nor benched - the planner chose
Sanctuary Apopalypse again six minutes later.
Offline: a bot without a screen, fake menus. Run:
python tests/test_result_kept_when_game_closes_offline.py"""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import runner as R                    # noqa: E402
from btd6bot.inputs import Aborted, FocusLost      # noqa: E402
from btd6bot.screen import GameNotFound            # noqa: E402

logging.getLogger("runner").setLevel(logging.CRITICAL)

PLAN = SimpleNamespace(map="Sanctuary", mode_key="apopalypse", strategy_id="apopalypse_ninja_sniper")


class FakeMenus:
    """Menus whose screen read or leave can fail the way a closed game does.

    screen: what identify() reads; fail_at: the method name that raises
    `error` ("identify", "leave_victory" or "leave_defeat"), else None."""

    def __init__(self, screen="defeat", fail_at=None, error=None):
        self.screen, self.fail_at, self.error = screen, fail_at, error
        self.calls = []

    def _step(self, name):
        self.calls.append(name)
        if name == self.fail_at:
            raise self.error

    def identify(self):
        self._step("identify")
        return self.screen

    def leave_victory(self):
        self._step("leave_victory")

    def leave_defeat(self):
        self._step("leave_defeat")


def bot_with(menus, mm_before=1000, mm_after=1000):
    """A Bot with no screen: only what _leave_finished_game touches."""
    bot = R.Bot.__new__(R.Bot)
    bot.menus = menus
    bot._mm_before = mm_before
    bot._games_since_id = 0
    bot.read_mm = lambda: mm_after
    return bot


def test_a_defeat_is_kept_when_the_game_closes_on_the_way_home():
    menus = FakeMenus(fail_at="leave_defeat", error=GameNotFound("window 'BloonsTD6' not found"))
    cause, mm = bot_with(menus)._leave_finished_game(PLAN, "defeat")
    assert cause is None, "a defeat Match saw is the map's loss, also when the game closes after it"
    assert mm is None
    assert menus.calls == ["identify", "leave_defeat"]


def test_a_defeat_is_kept_when_the_screen_cannot_be_read_at_all():
    menus = FakeMenus(fail_at="identify", error=GameNotFound("window 'BloonsTD6' not found"))
    assert bot_with(menus)._leave_finished_game(PLAN, "defeat") == (None, None)


def test_a_win_is_kept_when_the_game_goes_behind_another_window():
    menus = FakeMenus(fail_at="leave_victory", error=FocusLost("BTD6 is not the foreground window"))
    assert bot_with(menus)._leave_finished_game(PLAN, "victory") == (None, None)
    assert menus.calls == ["leave_victory"], "a win needs no look at the screen first"


def test_an_abandoned_game_stays_outside_the_map_when_the_game_closes():
    menus = FakeMenus(fail_at="identify", error=GameNotFound("gone"))
    cause, _ = bot_with(menus)._leave_finished_game(PLAN, "abandoned")
    assert cause == R.outside_cause("abandoned", None) and cause


def test_an_owner_stop_still_stops():
    menus = FakeMenus(fail_at="leave_defeat", error=Aborted("STOP"))
    try:
        bot_with(menus)._leave_finished_game(PLAN, "defeat")
    except Aborted:
        return
    raise AssertionError("Aborted must not be swallowed")


def test_a_normal_leave_reads_the_monkey_money_gained():
    menus = FakeMenus(screen="defeat")
    assert bot_with(menus, mm_before=1000, mm_after=1060)._leave_finished_game(PLAN, "defeat") == (None, 60)
    menus = FakeMenus()
    assert bot_with(menus, mm_before=1000, mm_after=1250)._leave_finished_game(PLAN, "victory") == (None, 250)
    # a total that fell, or jumped by more than a game pays, is a misread
    assert bot_with(FakeMenus(), mm_before=1000, mm_after=900)._leave_finished_game(PLAN, "victory")[1] is None
    assert bot_with(FakeMenus(), mm_before=None, mm_after=900)._leave_finished_game(PLAN, "victory")[1] is None


def test_the_title_screen_after_a_game_is_still_an_outside_cause():
    bot = bot_with(FakeMenus(screen="title"))
    cause, _ = bot._leave_finished_game(PLAN, "defeat")
    assert cause == R.outside_cause("defeat", "title") and cause
    assert bot._games_since_id == R.ID_CHECK_EVERY, "the User ID is read again before the next game"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"ALL OK ({len(tests)} checks)")
