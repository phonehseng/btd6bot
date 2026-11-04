"""A reward screen during a match is clicked away (no game needed).

Alpine Run Impoppable's round-100 win showed an "INSTA MONKEY!" card; the
match loop had no case for it and read the screen 400 times in 8 minutes
without a click (2026-11-04 11:17). Match._off_screen now hands reward
screens to Menus.handle_collection_event, as the runner's menu loop does."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.match import Match  # noqa: E402


class FakeMenus:
    def __init__(self):
        self.handled = 0
        self.words = []

    def handle_collection_event(self):
        self.handled += 1
        return True

    def dismiss_popup(self):
        raise AssertionError("a reward screen is not a popup to dismiss")


def test_insta_reward_is_handled():
    m = Match.__new__(Match)      # only what _off_screen touches
    m.menus = FakeMenus()
    for st in ("insta_reward", "reward_cards", "collection_event"):
        assert m._off_screen(st) is None
    assert m.menus.handled == 3


if __name__ == "__main__":
    test_insta_reward_is_handled()
    print("ok")
