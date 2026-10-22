"""Cash OCR must reject misreads instead of trusting them (hud.parse_cash)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.hud import parse_cash  # noqa: E402


def test_valid_cash():
    assert parse_cash("$650") == 650
    assert parse_cash("$8,475") == 8475
    assert parse_cash("$8.475") == 8475            # comma read as a dot
    assert parse_cash("$20,002,398") == 20002398
    assert parse_cash("$650T") == 650              # stray glyph after the number


def test_misreads_are_rejected():
    assert parse_cash("$6507") is None             # an extra digit, no separator
    assert parse_cash("$1,2345") is None           # digit inserted into a group
    assert parse_cash("$1885") is None             # thousands always have a comma
    assert parse_cash("") is None


if __name__ == "__main__":
    test_valid_cash()
    test_misreads_are_rejected()
    print("ok")
