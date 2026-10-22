"""Spot learning from pops-per-dollar: weak spots get avoided, unknown ones are neutral."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import layout as L  # noqa: E402
from btd6bot.game import Placed  # noqa: E402
from btd6bot.maplearn import MapModel, record_spot_results, spot_factor  # noqa: E402


def test_underperforming_spot_is_penalised():
    m = MapModel("test", L.get(1920, 1200)["playfield"])
    towers = [Placed("a", "tack", 0.3, 0.3, spent=1000), Placed("b", "tack", 0.6, 0.6, spent=1000),
              Placed("c", "dart", 0.5, 0.2, spent=500), Placed("d", "sniper", 0.1, 0.1, spent=1000)]
    for t, pops in zip(towers, (9000, 8000, 4000, 200)):
        t.pops = pops
    record_spot_results(m, towers)
    assert spot_factor(m, "sniper", *m.frac_to_cell(0.1, 0.1)) < 0.5
    assert spot_factor(m, "tack", *m.frac_to_cell(0.3, 0.3)) == 1.0
    assert spot_factor(m, "ninja", 5, 5) == 1.0  # never seen: neutral


def test_too_few_towers_records_nothing():
    m = MapModel("test", L.get(1920, 1200)["playfield"])
    t = Placed("a", "tack", 0.3, 0.3, spent=1000)
    t.pops = 10
    record_spot_results(m, [t])
    assert m.spot_stats == {}


if __name__ == "__main__":
    test_underperforming_spot_is_penalised()
    test_too_few_towers_records_nothing()
    print("ok")
