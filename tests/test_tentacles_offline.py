"""Abyss Dweller's ring of tentacles: a bloon meets about two of them.

Loss case 20261111_210232_Quad_deflation: the damage model counted all
eight AttackTentacle attacks of a 3-0-1 Mermonkey at full rate and rated
round 60's BFB 8.72; it took all 200 lives."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot import dps_model as D  # noqa: E402


def tentacle_attacks(tiers):
    entry = D.crosspath("mermonkey", tiers)
    return [a for a in entry["attacks"] if D.TENTACLE_ATTACK.search(a["name"])]


def test_eight_tentacles_count_as_two():
    attacks = D.crosspath("mermonkey", (3, 0, 1))["attacks"]
    n = len(tentacle_attacks((3, 0, 1)))
    assert n == 8
    assert abs(D._tentacle_share(attacks) * n - D.TENTACLES_IN_REACH) < 1e-9


def test_towers_without_tentacles_are_unchanged():
    assert D._tentacle_share(D.crosspath("mermonkey", (2, 0, 1))["attacks"]) == 1.0
    assert D._tentacle_share(D.crosspath("dart", (0, 2, 3))["attacks"]) == 1.0


if __name__ == "__main__":
    test_eight_tentacles_count_as_two()
    test_towers_without_tentacles_are_unchanged()
    print("all tests passed")
