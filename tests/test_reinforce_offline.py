"""Offline checks for reinforce.py: when the damage model rates the coming
rounds as weak, the purchase that saves the most lives per dollar (at half
strength) is chosen; nothing is bought when the look-ahead holds or the
cash buys nothing that helps. Uses the real model on Pat's Pond Hard.
Run: python tests/test_reinforce_offline.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import reinforce as R  # noqa: E402
from btd6bot import towers as T  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402
from btd6bot.maplearn import MapModel  # noqa: E402

PF = (0.0, 0.04, 0.855, 0.96)


class Ex:
    """The parts of Executor that reinforce.py uses: a few snipers on Pat's
    Pond (spots from the game lost there on 2026-10-22)."""
    mode = "hard"

    def __init__(self, towers):
        self.g = N(towers={t.tid: t for t in towers}, price=lambda kind: T.tower_cost(kind, "hard"))
        self.m = MapModel.load("Pat's Pond", PF)
        self.bought = []

    def upgrade_choices(self, first=None, past_plan=False):
        for p in self.g.towers.values():
            for path in range(3):
                t = list(p.tiers)
                if t[path] >= 5:
                    continue
                t[path] += 1
                if sum(x > 0 for x in t) > 2 or sum(x > 2 for x in t) > 1:
                    continue
                yield p, t, T.upgrade_cost(p.kind, path + 1, t[path], "hard")

    def at_tower_cap(self):
        return False

    def _main_kind(self):
        return "sniper"

    def kind_allowed(self, kind):
        return True

    def pick_spots(self, kind, step, n=1):
        p = next(iter(self.g.towers.values()))
        return [(*self.m.frac_to_cell(p.x + 0.03, p.y), 1.0)]

    def try_step(self, step, cash, rnd):
        self.bought.append(step)
        return "bought"


def weak_board():
    return [N(tid="s1", kind="sniper", tiers=[2, 0, 2], x=0.729, y=0.717),
            N(tid="s2", kind="sniper", tiers=[1, 0, 0], x=0.056, y=0.828),
            N(tid="s3", kind="sniper", tiers=[0, 0, 0], x=0.783, y=0.402)]


def forecast(ex):
    return RoundForecast("Pat's Pond", "hard", ex.m.sight)


def test_a_weak_look_ahead_buys_what_saves_most():
    if not D.available():
        return
    ex = Ex(weak_board())
    status, found = R.best(ex, forecast(ex), 5000, 40, 80)
    assert status == "buy", status
    o, worst, before, after = found
    assert 40 <= worst <= 49 and o.cost <= 5000
    assert after >= before, (o.what, before, after)
    # bought through the executor, and logged as a reinforcement
    assert R.buy_best(ex, forecast(ex), 5000, 40, 80) == "bought" and ex.bought


def test_no_cash_means_wait():
    if not D.available():
        return
    ex = Ex(weak_board())
    assert R.best(ex, forecast(ex), 0, 40, 80) == ("wait", None)


def test_nothing_ahead_means_safe():
    if not D.available():
        return
    ex = Ex(weak_board())
    assert R.best(ex, forecast(ex), 5000, 81, 80) == ("safe", None)     # past the last round


def test_look_ahead_covers_the_rounds_left():
    assert R.lookahead_rounds(55, 80) == list(range(55, 65))
    assert R.lookahead_rounds(78, 80) == [78, 79, 80]
    assert R.lookahead_rounds(None, 80) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
