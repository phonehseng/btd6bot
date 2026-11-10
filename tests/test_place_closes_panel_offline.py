"""Game.place closes an open upgrade panel before it picks the tower up.

Glacial Trail Medium (2026-11-10): dr2 was placed on the right and confirmed
by selecting it, so its upgrade panel covered the left third of the map. The
click for sp2 on Floor2 (0.142, 0.521) landed on the panel, the spot was
learned as unplaceable and the step given up for the game.
Offline: a Game with its screen methods replaced by recorders.
Run: python tests/test_place_closes_panel_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot.game import Game  # noqa: E402


def test_the_panel_is_closed_before_the_hold():
    calls = []
    g = Game.__new__(Game)
    g.screen_ok = lambda: True
    g.cash_stable = lambda: 5000
    g.price = lambda kind: 500
    g.cancel_hold = lambda: calls.append("cancel")
    g.close_panels = lambda: calls.append("close") or True
    g.fresh = lambda: calls.append("baseline")
    g.hold = lambda kind: calls.append("hold") or False    # stop right after the hold
    assert g.place("sp2", "spike", 0.142, 0.521) is None and g.fail_reason == "hold"
    assert calls == ["cancel", "close", "baseline", "hold"], calls


if __name__ == "__main__":
    test_the_panel_is_closed_before_the_hold()
    print("ok")
