"""An Alchemist's Acidic Mixture Dip covers a budget of shots, not every shot.

The damage model treated the 2-x-x dip as a permanent aura: every tower
within 45 popped lead and dealt +1 to Ceramic / MOAB / Fortified on every
shot. In the game the Alchemist throws the dip at one tower every 10 s and
it lasts 10 of that tower's shots (12 at 2-2-0); only Permanent Brew (5-x-x)
makes it last for ever (fandom:Acidic_Mixture_Dip, fandom:Permanent_Brew;
docs/model_audit_magic.md, finding 2). The export carries both numbers
(the dip attack's rate, the potion's "shots": AcidicMixtureCheckModel.
maxCount, 9,999,999 for Permanent Brew).

The example: a Ninja 0-0-0 (one throw every 0.62 s: 1.61 shots/s) beside a
2-0-0 Alchemist: 10 / 10 = 1 dipped shot a second, so 1 / 1.61 = 62% of its
shurikens pop lead; with Permanent Brew all of them.
Run: python tests/test_dip_budget_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

TRACK = None


def _track():
    global TRACK
    if TRACK is None:
        TRACK = D.Track("Monkey Meadow")
    return TRACK


def _dip(tiers):
    a = next(a for a in D.crosspath("alchemist", tiers)["attacks"] if a["name"] == "AcidicMixture")
    w = a["weapons"][0]
    return w["projectile"]["potion"]["shots"], w["rate"]


def _ninja_sources(alch_tiers, others=()):
    n = D.Placed("n", "ninja", (0, 0, 0), -100.0, 35.0)
    a = D.Placed("a", "alchemist", alch_tiers, -95.0, 40.0)
    return D.station_for(n, [n, a, *others], _track()).sources


def _lead_share(sources):
    total = sum(s.shots for s in sources)
    return sum(s.shots for s in sources if "lead" not in s.immune) / total


def test_dip_covers_its_shot_budget():
    shots, every = _dip((2, 0, 0))                           # 10 shots every 10 s
    w = D.crosspath("ninja", (0, 0, 0))["attacks"][0]["weapons"][0]
    rate = 1.0 / w["rate"]                                   # 1.61 throws/s
    expected = shots / every / rate                          # 0.62
    got = _lead_share(_ninja_sources((2, 0, 0)))
    assert abs(got - expected) < 1e-6, (got, expected)
    assert abs(got - 0.62) < 0.01


def test_x2x_dip_lasts_12_shots():
    shots, every = _dip((2, 2, 0))
    assert shots == 12.0
    assert abs(_lead_share(_ninja_sources((2, 2, 0))) - min(1.0, shots / every * D.crosspath(
        "ninja", (0, 0, 0))["attacks"][0]["weapons"][0]["rate"])) < 1e-6


def test_permanent_brew_dips_every_shot():
    shots, _ = _dip((5, 0, 0))
    assert shots >= D.PERMANENT_POTION_SHOTS
    assert _lead_share(_ninja_sources((5, 0, 0))) == 1.0


def test_the_budget_is_shared_by_the_towers_in_range():
    """A second attacking tower beside the Alchemist halves each one's share."""
    alone = _lead_share(_ninja_sources((2, 0, 0)))
    dart = D.Placed("d", "dart", (0, 0, 0), -90.0, 40.0)
    shared = _lead_share(_ninja_sources((2, 0, 0), [dart]))
    assert abs(shared - alone / 2) < 1e-6, (alone, shared)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
