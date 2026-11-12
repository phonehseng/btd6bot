"""An instakill's overflow is not shared with the small hits beside it.

dps_model._Rates._compute averaged the damage that overflows into a bloon's
children over all the hits a station lands on a layer. Druid of the Jungle
(1-3-0) mixes a 9,999,999-damage vine (one grab every 2.6 s) with 1-damage
brambles: the vine is 6% of the hits but carried ~10,000,000 of overflow, so
every bramble pop was given a carry of ~625,000 and one druid popped about 6
whole Rainbows, Zebras or Leads a second (docs/model_audit_magic.md,
finding 1). In the game only the vine's own grabs destroy a whole bloon; the
brambles pop one layer a hit: about 0.4 whole Rainbows a second.

Now hits that destroy the whole bloon are a share of their own, working
beside the ordinary hits: whole bloons/s = vine grabs/s + bramble HP/s over
the bloon's total health (rbe). For a Rainbow (rbe 47) that is
1/2.6 + 5.77/47 = 0.51.

Example: one 1-3-0 druid beside Monkey Meadow's first lane, packing 0.05
bloons per unit (the audit's measurement).
Run: python tests/test_overflow_instakill_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

RHO = 0.05


def _vine_station():
    tr = D.Track("Monkey Meadow")
    t = D.Placed("d", "druid", (1, 3, 0), -100.0, 40.0)
    st = next(s for s in D.with_parts([D.station_for(t, [t], tr)])
              if any(x.name == "JungleVine>Collidable" for x in s.sources))
    st.strength = 1.0
    return st


def _whole_per_s(st, bloon):
    work, passed = D._Rates(st).subtree(bloon, 1.0, RHO, 0, 0.0)
    assert passed == (), passed
    return 1.0 / work


def test_rainbows_whole_rate_is_vine_plus_bramble_chip():
    st = _vine_station()
    vine = next(s for s in st.sources if s.name == "JungleVine>Collidable")
    bramble = next(s for s in st.sources if s.name == "JungleVine>Projectile")
    lay = D.layer("Rainbow")
    grabs = D._hit_rate(vine, lay, RHO, st.zones[0])                 # 1 / 2.6 s
    chip = D._hit_rate(bramble, lay, RHO, st.zones[0]) * bramble.damage   # 5.77 HP/s
    expected = grabs + chip / D.rbe("Rainbow")
    got = _whole_per_s(st, "Rainbow")
    # the vine also takes its share of the layers inside (subtree): ~8% more
    assert abs(got - expected) < 0.1 * expected, (got, expected)
    assert 0.45 < got < 0.6, got                                      # was 6.15


def test_leads_and_zebras_are_no_longer_free():
    st = _vine_station()
    for bloon in ("Lead", "Zebra"):
        assert _whole_per_s(st, bloon) < 1.0, bloon                   # were 6.15 each


def test_reds_still_pop_at_the_full_hit_rate():
    """A layer without children is popped by every hit alike."""
    st = _vine_station()
    hp_rate = D._Rates(st).get("Red", 1.0, RHO, 0)[0]
    assert abs(_whole_per_s(st, "Red") - hp_rate) < 1e-9


def test_a_hit_bigger_than_the_bloon_destroys_it_whole():
    """A 3.5-damage hit on a Pink (rbe 5) carries 2.5 to its children; a
    1,000-damage hit destroys the whole Pink and carries nothing."""
    src = D.Source(name="big", shots=1.0, shots_single=1.0, pierce=1.0, damage=3.5, immune=frozenset(),
                   bonus={}, camo=True, only_tags=frozenset(), excluded_tags=frozenset(), reach=0.0)
    st = D.Station(tid="x", kind="dart", tiers=(0, 0, 0), zones=[D.Zone(0.0, 100.0)], sources=[src], order=0.0)
    st.strength = 1.0
    hp, carry, killed, _ = D._Rates(st).get("Pink", 1.0, RHO, 0)
    assert killed == 0.0 and abs(carry - 2.5) < 1e-9, (carry, killed)
    src.damage = 1000.0
    hp, carry, killed, _ = D._Rates(st).get("Pink", 1.0, RHO, 0)
    assert killed == 1.0 and carry == 0.0, (carry, killed)          # destroys it whole instead


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
