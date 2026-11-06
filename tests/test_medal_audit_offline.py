"""The medal audit: the map cards correct the account's medals both ways.

Until 2026-11-06 a medal scan only added medals. With Apopalypse/Reverse and
Half Cash misread, the account kept medals the game never gave (Lotus Island
Apopalypse and Half Cash), the planner never played them and those maps
never got their black border. The owner asked for the cards to be the source
of truth when they read clearly, with a guard against the 2026-10-22 loop
(a scan "removing" medals the bot had just won, then replaying them).
Run: python tests/test_medal_audit_offline.py"""
import logging
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from btd6bot import runner as R  # noqa: E402
from btd6bot.account import MODES, AccountState  # noqa: E402
from btd6bot.medals import (HISTORY_TIME, MODE_POINTS, RECENT_WIN_GUARD, audit_card,  # noqa: E402
                            grid_card_frame, read_grid_detail, recent_wins, wants_second_look)
from btd6bot.vision import Word  # noqa: E402
from test_medal_grid_offline import load_page  # noqa: E402

logging.getLogger("runner").setLevel(logging.CRITICAL)

ALL = {mode: True for mode in MODE_POINTS}


def lotus_read():
    """Lotus Island's card from the 2026-11-06 capture: (medals, frame)."""
    frame = load_page("page17")
    return read_grid_detail(frame, 2, 0), grid_card_frame(frame, 2, 0)


def cubism_read():
    """Cubism's card (all 14, black border)."""
    frame = load_page("page01")
    return read_grid_detail(frame, 0, 1), grid_card_frame(frame, 0, 1)


def stamp(seconds_ago, now):
    return time.strftime(HISTORY_TIME, time.localtime(now - seconds_ago))


def test_the_modes_are_the_cards_medals():
    assert set(MODES) == set(MODE_POINTS), "a black border is every mode's medal"


def test_removal_needs_a_second_read():
    record = dict(ALL)                    # what the account said on 2026-11-06
    read = lotus_read()
    assert wants_second_look(record, *read)
    once = audit_card(record, [read])
    assert once["remove"] == [] and set(once["kept"]) == {"apopalypse", "half_cash", "chimps"}
    twice = audit_card(record, [read, read])
    assert set(twice["remove"]) == {"apopalypse", "half_cash", "chimps"}
    assert not twice["add"] and not twice["unsure"]


def test_addition_from_one_clear_read():
    record = {"easy": True, "medium": True}
    got = audit_card(record, [cubism_read()])
    assert set(got["add"]) == set(MODE_POINTS) - {"easy", "medium"} and not got["remove"]
    assert not wants_second_look(record, *cubism_read()), "nothing to take away: one read is enough"


def test_low_confidence_changes_nothing():
    medals, frame = lotus_read()
    record = dict(ALL)
    for reads in ([(dict(medals, reverse=None), frame)] * 2,     # one medal unsure
                  [(medals, None)] * 2,                           # no frame seen
                  [(medals, "black")] * 2,                        # frame and medals disagree
                  [(medals, frame), (dict(medals, apopalypse=True), frame)]):   # reads differ
        got = audit_card(record, reads)
        assert got["unsure"] and not got["add"] and not got["remove"], reads[0][1]


def test_a_medal_just_won_is_never_removed():
    now = time.time()
    history = [{"t": stamp(120, now), "map": "Lotus Island", "mode": "apopalypse", "won": True},
               {"t": stamp(60, now), "map": "Lotus Island", "mode": "half_cash", "won": False},
               {"t": stamp(RECENT_WIN_GUARD + 60, now), "map": "Lotus Island", "mode": "chimps",
                "won": True}]
    assert recent_wins(history, now) == {("Lotus Island", "apopalypse")}
    read = lotus_read()
    got = audit_card(dict(ALL), [read, read], protected={"apopalypse"})
    assert got["guarded"] == ["apopalypse"]
    assert set(got["remove"]) == {"half_cash", "chimps"}


def test_apply_card_audit_corrects_the_account():
    acc = AccountState()
    acc.medals = {"Lotus Island": dict(ALL), "Cubism": {"easy": True}}
    now = time.time()
    acc.history = [{"t": stamp(30, now), "map": "Lotus Island", "mode": "chimps", "won": True}]
    lotus, cubism = lotus_read(), cubism_read()
    changed = R.apply_card_audit(acc, {"Lotus Island": [lotus, lotus], "Cubism": [cubism]}, now=now)
    assert set(acc.medals["Lotus Island"]) == set(MODE_POINTS) - {"apopalypse", "half_cash"}, \
        "Apopalypse and Half Cash go; CHIMPS stays: the bot won it 30 s ago"
    assert acc.black_bordered("Cubism") and not acc.black_bordered("Lotus Island")
    assert changed == {"added": 13, "removed": 2}


# -- triggers -----------------------------------------------------------------
def fake_bot(uid_dir, black=True, swept_ago=None):
    """A Bot with no game: scan_all_medals only counts its calls."""
    bot = R.Bot.__new__(R.Bot)
    bot.uid = "AAAA"
    bot.account = AccountState()
    bot.account.medals = {"Cubism": dict(ALL) if black else {"easy": True}}
    bot._medal_audit_why = None
    bot.scans = []
    bot.scan_all_medals = lambda: bot.scans.append(1) or 88
    bot.to_main_menu = lambda: True
    if swept_ago is not None:
        R._write_stamp(R._medal_sweep_file("AAAA"), time.time() - swept_ago)
    return bot


def with_accounts_dir(test):
    def run():
        with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "ROOT_DIR", Path(d)):
            (Path(d) / "data" / "accounts").mkdir(parents=True)
            test(d)
    return run


@with_accounts_dir
def test_planner_picking_a_black_bordered_map_triggers_the_scan(d):
    plan = SimpleNamespace(map="Cubism")
    bot = fake_bot(d, black=True, swept_ago=R.MEDAL_AUDIT_GAP + 60)
    assert bot._audit_black_bordered_pick(plan) and bot.scans == [1]
    assert not bot._audit_black_bordered_pick(plan) and bot.scans == [1], \
        "just scanned: not again within MEDAL_AUDIT_GAP (no loop)"
    bot = fake_bot(d, black=False, swept_ago=R.MEDAL_AUDIT_GAP + 60)
    assert not bot._audit_black_bordered_pick(plan) and bot.scans == [], "an unfinished map: no scan"


@with_accounts_dir
def test_a_disagreeing_card_frame_while_opening_a_map_asks_for_the_scan(d):
    # The map-select page stands in for the search page: the frame is read
    # around the card's name label either way.
    page = load_page("page17")
    label = Word("Lotus Island", (488 + 471 * 2) / 1920, 152 / 1200, 0.1, 0.03, 0.9)
    for ours_black, want in ((True, True), (False, False)):
        bot = fake_bot(d, swept_ago=R.MEDAL_AUDIT_GAP + 60)
        bot.account.medals = {"Lotus Island": dict(ALL) if ours_black else {"easy": True}}
        bot.s = SimpleNamespace(grab=lambda: page)
        bot.sync_medals("Lotus Island", label)
        assert bool(bot._medal_audit_why) == want, ours_black
        assert bot._audit_medals_if_asked() == want and bot.scans == ([1] if want else [])


if __name__ == "__main__":
    test_the_modes_are_the_cards_medals()
    test_removal_needs_a_second_read()
    test_addition_from_one_clear_read()
    test_low_confidence_changes_nothing()
    test_a_medal_just_won_is_never_removed()
    test_apply_card_audit_corrects_the_account()
    test_planner_picking_a_black_bordered_map_triggers_the_scan()
    test_a_disagreeing_card_frame_while_opening_a_map_asks_for_the_scan()
    print("ok")
