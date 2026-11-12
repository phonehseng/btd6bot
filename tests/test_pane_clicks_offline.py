"""Towers under a shut Covered Garden pane are not clicked, sold or forgotten.

Audit of 2026-11-12 (dynamic maps, item 9): the pop-count read in
sell_useless, _sell_and_avoid and _recheck_doubtful clicked towers without
asking _reachable. A click on the shut glass fails the select, which clears
`verified` and raises `select_fails`, so a standing tower could be forgotten
by _forget_if_missing and bought again; _sell_and_avoid also barred the spot
before a sale that never happened.

The top-left quarter (the guides' ninja pocket by the fountain, 0.32, 0.28)
is open in rounds 2, 6, 10, 14 ... (tests/test_panes_offline.py). Offline:
the map geometry and the executor on fakes, no game; with no screen to read,
_pane_now judges by the bot's round.
Run: python tests/test_pane_clicks_offline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import layout as L, mapgeom, strategy as S   # noqa: E402
from btd6bot.maplearn import MapModel          # noqa: E402

UNDER_PANE = (0.32, 0.28)     # top-left quarter: open in rounds 2, 6, 10 ...
OPEN_STRIP = (0.05, 0.62)     # the left strip, never covered


class ClickGame(F.FakeGame):
    """FakeGame that records every tower it is asked to select."""

    def __init__(self):
        super().__init__()
        self.selected = []

    def select(self, p):
        self.selected.append(p.tid)
        return True

    def deselect(self, p):
        return True


def setup():
    geom = mapgeom.load("Covered Garden")
    if geom is None:
        return None
    m = mapgeom.apply(MapModel("Covered Garden", L.get(1920, 1200)["playfield"]), geom)
    m.refused = {}
    plan = {"id": "t", "name": "t", "hero": None, "plan": []}
    ex = S.Executor(ClickGame(), m, plan, "medium", F.full_account())
    ex.lookahead_worst = lambda rnd: None    # the defence is calm: sales are allowed
    assert not mapgeom.pane_at(m, *UNDER_PANE, 3)[1]
    assert mapgeom.pane_at(m, *UNDER_PANE, 6)[1]
    return ex


def tower(tid, kind, at):
    return F.Placed(tid, kind, *at)


def test_a_tower_under_a_shut_pane_is_not_forgotten():
    ex = setup()
    if ex is None:
        return
    n1 = tower("n1", "ninja", UNDER_PANE)
    n1.verified, n1.select_fails = False, 5
    ex.g.towers = {"n1": n1}
    ex.now_round = 3
    assert not ex._forget_if_missing(n1) and "n1" in ex.g.towers
    ex.now_round = 6          # its pane is open: failures there do count
    assert ex._forget_if_missing(n1) and "n1" not in ex.g.towers


def test_no_sale_and_no_barred_spot_under_a_shut_pane():
    ex = setup()
    if ex is None:
        return
    n1, d1 = tower("n1", "ninja", UNDER_PANE), tower("d1", "dart", OPEN_STRIP)
    ex.g.towers = {"n1": n1, "d1": d1}
    ex.now_round = 3
    assert not ex._sell_and_avoid(n1, 3, "test")
    assert ex.g.sold == [] and not ex.failed_spots
    ex.now_round = 6
    assert ex._sell_and_avoid(n1, 6, "test")
    assert ex.g.sold == ["ninja"] and ex.failed_spots


def test_a_failed_sale_bars_no_spot():
    ex = setup()
    if ex is None:
        return
    d1 = tower("d1", "dart", OPEN_STRIP)
    ex.g.towers = {"d1": d1, "d2": tower("d2", "dart", OPEN_STRIP)}
    ex.g.sell = lambda p: False
    ex.now_round = 3
    assert not ex._sell_and_avoid(d1, 3, "test")
    assert not ex.failed_spots


def test_doubtful_tower_under_a_shut_pane_is_not_clicked():
    ex = setup()
    if ex is None:
        return
    n1 = tower("n1", "ninja", UNDER_PANE)
    n1.verified = False
    ex.g.towers = {"n1": n1}
    ex.now_round = 3
    ex._recheck_doubtful()
    assert ex.g.selected == [] and n1.verified and ex.defended()


def test_pop_count_is_read_only_off_shut_panes():
    ex = setup()
    if ex is None:
        return
    n1, d1 = tower("n1", "ninja", UNDER_PANE), tower("d1", "dart", OPEN_STRIP)
    for p in (n1, d1):
        p.placed_round, p.pops = 0, 0
    ex.g.towers = {"n1": n1, "d1": d1}
    ex.now_round = 11         # shut: the top-left pane opens in 10 and 14
    ex.sell_useless(11)
    assert ex.g.selected == ["d1"], ex.g.selected


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
