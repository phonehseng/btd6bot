"""Spiked Mines explode once per mine and cannot hurt black bloons or DDTs.

docs/model_audit_support_heroes.md, S5. The 4-x-x mine has two spawns of
its Explosion, one on "exhaust" (its pierce used up) and one on "expire"
(its lifespan over), and the model counted both: two explosions per mine.
They are alternatives (dps_model._alternative_spawns): on the busy rounds
the bot loses, the mine is exhausted and explodes once.

The Explosion is explosion type (immune to black) and its burn is immune
to purple. The model intersected the two sets, so the explosion had no
immunity at all and the mines damaged DDTs on R95 and R99, which they
cannot (fandom:Spiked_Mines: "explosion type"). Super Mines (5-x-x) are
normal type and do hit black bloons and DDTs.
Run: python tests/test_spiked_mines_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _explosions(tiers):
    return [s for s in D.profile("spike", tiers).sources if s.name == "Attack>Explosion"]


def test_one_explosion_per_mine():
    w = D.crosspath("spike", (4, 0, 0))["attacks"][0]["weapons"][0]
    mines = w["count"] / w["rate"]                         # 0.57 mines/s
    ex = _explosions((4, 0, 0))
    assert len(ex) == 1, ex                                # was two
    assert abs(ex[0].shots - mines) < 1e-9


def test_spiked_mines_cannot_hurt_black_or_ddt():
    ex = _explosions((4, 0, 0))[0]
    assert ex.immune == frozenset({"black"}) and ex.dot_immune == frozenset({"purple"})
    for bloon in ("Black", "Zebra", "Ddt", "DdtCamo"):
        assert not ex.can_hit(D.layer(bloon)), bloon
    assert ex.can_hit(D.layer("Purple"))                  # the blast hurts purples, the burn does not


def test_the_burn_skips_purples():
    ex = _explosions((4, 0, 0))[0]
    st = D.Station(tid="s", kind="spike", tiers=(4, 0, 0), zones=[D.Zone(0.0, 100.0)], sources=[ex], order=0.0)
    st.strength = 1.0
    rates = D._Rates(st)
    hit_only = D._hit_rate(ex, D.layer("Purple"), 0.05, st.zones[0]) * min(ex.damage, D.layer("Purple").hp)
    assert abs(rates.get("Purple", 1.0, 0.05, 0)[0] - hit_only) < 1e-9
    assert rates.get("Red", 1.0, 0.05, 0)[0] > D._hit_rate(ex, D.layer("Red"), 0.05, st.zones[0]) * 1.0


def test_super_mines_hit_ddts():
    ex = _explosions((5, 0, 0))
    assert len(ex) == 1 and ex[0].can_hit(D.layer("Ddt"))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
