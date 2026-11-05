"""Offline: buying an obstacle's removal counts when the obstacle is gone,
even if the round's income hid the price in the cash counter (Cornfield
Magic Only, 2026-11-05: ten removals paid for, none counted, "0 legal
cells" with $29k in the bank). Fakes stand in for the screen and the mouse.
Run: python tests/test_obstacle_income_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import game as G  # noqa: E402

BOX = {"price": 1500, "confirm": (0.3, 0.5), "cancel": (0.2, 0.5)}


def _game(cash_reads):
    """A Game whose cash counter returns `cash_reads` in turn and whose
    clicks are recorded; no screen, layout or OCR involved."""
    g = G.Game.__new__(G.Game)
    g.clicks = []
    g.inp = N(click=lambda x, y: g.clicks.append((round(x, 3), round(y, 3))))
    g.screen_ok = lambda: True
    g.cash_stable = lambda dx=0.0: cash_reads.pop(0)
    g.fresh = lambda: None
    g._vision = lambda: N(read=lambda img=None, region=None: [])
    g.closed = 0

    def close_panels():
        g.closed += 1
        return False
    g.close_panels = close_panels
    return g


def _run(cash_reads, boxes):
    """remove_obstacle with the removal box reads scripted by `boxes`."""
    real_box, real_sleep = G.find_removal_box, G.time.sleep
    G.find_removal_box = lambda f, words: boxes.pop(0)
    G.time.sleep = lambda s: None
    try:
        g = _game(cash_reads)
        return g.remove_obstacle(0.4, 0.6, 1500, name="Cornfield8"), g
    finally:
        G.find_removal_box, G.time.sleep = real_box, real_sleep


def test_a_price_drop_in_the_cash_counts_without_a_second_look():
    ok, g = _run([13208, 11708], [dict(BOX)])
    assert ok
    assert g.clicks == [(0.4, 0.6), (0.3, 0.5)]       # the obstacle, then the green check


def test_income_hiding_the_price_the_vanished_obstacle_is_the_proof():
    """Cornfield8: cash 13,208 -> 13,974 after confirming $1,500 (Auto Start
    kept the round paying). Clicking the spot again opens no box, so the
    removal counts and the freed ground can be used."""
    ok, g = _run([13208, 13974], [dict(BOX), None])
    assert ok
    assert g.clicks == [(0.4, 0.6), (0.3, 0.5), (0.4, 0.6)]
    assert g.closed == 1          # whatever the second click selected is closed again


def test_an_obstacle_still_standing_is_not_counted_and_its_box_is_cancelled():
    ok, g = _run([13208, 13974], [dict(BOX), dict(BOX)])
    assert not ok
    assert g.clicks[-1] == (0.2, 0.5)                 # the red X of the reopened box


def test_no_box_on_the_first_click_buys_nothing():
    ok, g = _run([13208], [None])
    assert not ok
    assert g.clicks == [(0.4, 0.6)]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
