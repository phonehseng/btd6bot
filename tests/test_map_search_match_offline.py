"""Map search: a card title with one misread letter still opens the map
(runner.map_title_matches). Live 2026-11-09 01:03: X Factor's card read
"XFAGTOR" and the map was benched for 2 hours.
Run: python tests/test_map_search_match_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.runner import map_title_matches  # noqa: E402
from btd6bot.vision import norm  # noqa: E402


def test_one_misread_letter_matches():
    assert map_title_matches(norm("X Factor"), "XFAGTOR")
    assert map_title_matches(norm("X Factor"), "X FACTOR")
    assert map_title_matches(norm("Candy Falls"), "CANDYFALLS")


def test_other_titles_do_not_match():
    assert not map_title_matches(norm("X Factor"), "FRIenDs")
    assert not map_title_matches(norm("X Factor"), "139")
    assert not map_title_matches(norm("Cargo"), "CARVED")
    assert not map_title_matches(norm("X Factor"), "XFAGTUR")   # two letters off


if __name__ == "__main__":
    test_one_misread_letter_matches()
    test_other_titles_do_not_match()
    print("ok")
