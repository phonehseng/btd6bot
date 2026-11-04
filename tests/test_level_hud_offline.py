"""The HUD shows the player level and the XP bar from the main menu
(Runner._show_level -> status.set_level -> tools/overlay.py).

Level 142 (2026-11-04) read "678,907/2,750,000" beside the star; the bot's
own XP table expected about 100k per level there, so the bar is read, not
estimated. Offline. Run: python tests/test_level_hud_offline.py"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import status            # noqa: E402
from btd6bot.hud import parse_xp_bar  # noqa: E402


def test_the_xp_bar_text_is_read_as_two_numbers():
    assert parse_xp_bar("678,907/2,750,000") == (678907, 2750000)
    assert parse_xp_bar("678,907 / 2,750,000") == (678907, 2750000)


def test_a_bar_that_cannot_be_right_is_dropped():
    assert parse_xp_bar("678,907") is None              # no total
    assert parse_xp_bar("2,750,000/678,907") is None    # earned beyond the level
    assert parse_xp_bar("/2,750,000") is None
    assert parse_xp_bar("") is None


def test_the_hud_line():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "level.txt"
        with mock.patch.object(status, "LEVEL_FILE", f):
            status.set_level(142, (678907, 2750000))
            assert f.read_text(encoding="utf-8") == "Lv 142 | 678,907 / 2,750,000 XP (24%)"
            status.set_level(142, None)                    # the bar did not read
            assert f.read_text(encoding="utf-8") == "Lv 142"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
