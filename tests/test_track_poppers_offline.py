"""A tower that never reaches the track is no answer to a threat.

Peninsula Impoppable (2026-11-12 00:18, loss case 20261112_001915): the only
lead popper was an alchemist placed "where it buffs the most towers", out of
the track's reach; the threat check said "lead (round 28): covered by a1",
nothing else was bought for lead, and round 28's six leads took the life.
Executor._covers now counts only towers whose attacks reach the track."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402
import simulate_threats as SIM  # noqa: E402
from btd6bot import threats as TH  # noqa: E402
import test_blimp_answer_copies_offline as W  # noqa: E402  (a Workshop executor with a real map)


def _spot(ex, kind, reaching):
    """A legal (x, y) screen fraction for `kind` whose cell reaches the track
    (reaching=True) or reaches none of it."""
    from btd6bot import placement as PL
    reach = ex._reach(kind)
    valid = PL.valid_spots(ex.m, kind)
    cells = np.argwhere(valid & ((reach > 0) if reaching else (reach <= 0)))
    assert len(cells), f"no {'reaching' if reaching else 'idle'} spot for {kind}"
    cy, cx = cells[len(cells) // 2]
    return ex.m.cell_to_frac(cx, cy)


def test_an_alchemist_off_the_track_does_not_cover_lead():
    if not TH.available():
        return
    ex = W._executor([])
    sig = TH.sig_from_name("lead")
    x, y = _spot(ex, "alchemist", reaching=False)
    ex.g.towers["a1"] = SIM.Placed("a1", "alchemist", x, y, tiers=[0, 0, 0])
    assert not ex._covers(sig)[0], "out of reach: no answer"
    x, y = _spot(ex, "alchemist", reaching=True)
    ex.g.towers["a1"] = SIM.Placed("a1", "alchemist", x, y, tiers=[0, 0, 0])
    assert ex._covers(sig)[0], "in reach: lead is answered"


if __name__ == "__main__":
    test_an_alchemist_off_the_track_does_not_cover_lead()
    print("all tests passed")
