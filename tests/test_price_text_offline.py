"""Upgrade prices whose '$' OCR misreads still count as prices (no game needed).

Peninsula Reverse (2026-11-03): OCR read Deadly Precision's '$2,200' as
'#2,200', Game.path_costs saw no price, every sniper's path 1 was closed for
the game and $51,030 stayed unspent until the round-50 loss. The Geared
Medium defeat still (frames/end_029.jpg of that loss) reproduces the read.
Run: python tests/test_price_text_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.game import looks_like_price  # noqa: E402
from btd6bot.hud import parse_int  # noqa: E402


def test_misread_dollar_signs():
    for text, value in (("$2,200", 2200), ("#2,200", 2200), ("S2,100", 2100),
                        ("s550", 550), ("2,100", 2100), ("$ 500", 500)):
        assert looks_like_price(text), text
        assert parse_int(text) == value, (text, parse_int(text))
    print("ok '$', '#', 'S' and no sign all read as prices")


def test_words_are_not_prices():
    for text in ("", "PATH CLOSED", "BounonG", "Sell", "owned"):
        assert not looks_like_price(text), text
    print("ok words and blanks are not prices")


if __name__ == "__main__":
    test_misread_dollar_signs()
    test_words_are_not_prices()
    print("ALL OK")
