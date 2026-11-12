"""A refusal beside one of the bot's own towers is not learned for the map.

The game keeps towers' footprints apart, so a spot next to a standing tower
is refused although the ground is fine. Learned for the map, it barred that
ground in every later game: the 2026-11-12 pin audit found 673 refused
cells in the 4x4 blocks where a tower later stood, and 39% of Sunset
Gulch's land refused."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import test_blimp_answer_copies_offline as W  # noqa: E402  (a Workshop executor on a real map)


def test_a_refusal_beside_a_tower_is_not_learned():
    ex = W._executor(W.BOARD)
    n1 = ex.g.towers["n1"]
    cx, cy = (int(round(v)) for v in ex.m.frac_to_cell(n1.x, n1.y))
    assert ex._tower_in_the_way("dart", cx + 1, cy) == "n1"
    learned = []
    ex.m.refuse = lambda layer, x, y, *a: learned.append((layer, x, y))
    ex._learn_blocked("dart", cx + 1, cy)
    assert not learned, "beside a standing tower: kept for this game only"


def test_a_refusal_in_the_open_is_still_learned():
    ex = W._executor([])
    learned = []
    ex.m.refuse = lambda layer, x, y, *a: learned.append((layer, x, y))
    assert ex._tower_in_the_way("dart", 40, 40) is None
    ex._learn_blocked("dart", 40, 40)
    assert learned, "no tower near: the ground itself refused"


if __name__ == "__main__":
    test_a_refusal_beside_a_tower_is_not_learned()
    test_a_refusal_in_the_open_is_still_learned()
    print("all tests passed")
