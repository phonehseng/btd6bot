"""The damage model credits an Alchemist's Acidic Mixture Dip with letting
the towers next to it pop lead, and a Monkey Intelligence Bureau village
with every damage type.

Dark Dungeons Magic Monkeys Only (2026-11-05, loss case 20261105_070008):
the Alchemist's potion attacks (projectiles that hit their target only and
carry Add<Potion>ToProjectileModel) were no buff in the model, so a Ninja +
Alchemist build popped no lead at all in its eyes - every lead round sat at
the margin floor from round 23 on, the real game held rounds 28 and 30, and
reinforce, seeing "0.06 -> 0.06" for every purchase, bought nothing for
round 37's 15 leads. Offline, against data/game_model/attacks.json.
Run: python tests/test_alch_potion_buff_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def test_dip_is_a_lead_buff_from_tier_2_on():
    plain = D.profile("alchemist", (0, 0, 0))
    dip = D.profile("alchemist", (2, 0, 0))
    assert not [b for b in plain.buffs if b["kind"] == "damage_type"]
    buffs = [b for b in dip.buffs if b["kind"] == "damage_type"]
    assert len(buffs) == 1, buffs
    assert buffs[0]["props"] == ["lead"]
    assert buffs[0]["bonus"]["Lead"]["add"] >= 1.0
    assert buffs[0]["radius"] > 0
    # the brew's numbers are not in the export: no buff is made up for it
    brew = [b for b in D.profile("alchemist", (3, 2, 0)).buffs if b["kind"] == "damage_type"]
    assert len(brew) == 1


def test_buffed_sources_lift_the_named_immunity_only():
    ninja = D.profile("ninja", (0, 0, 0))
    assert all("lead" in s.immune for s in ninja.sources)
    dip = [b for b in D.profile("alchemist", (2, 0, 0)).buffs if b["kind"] == "damage_type"][0]
    buffed = D._buffed_sources(ninja, [dip])
    assert all("lead" not in s.immune for s in buffed)
    assert all(s.bonus["Lead"]["add"] >= 1.0 for s in buffed)
    # a bomb's explosion still cannot pop black bloons: the dip names lead only
    bomb = D.profile("bomb", (0, 0, 0))
    assert any("black" in s.immune for s in bomb.sources)
    assert any("black" in s.immune for s in D._buffed_sources(bomb, [dip]))
    # MIB (village 2-3-0): every immunity goes
    mib = [b for b in D.profile("village", (2, 3, 0)).buffs if b["kind"] == "damage_type"]
    assert mib, "village 2-3-0 should export a damage_type buff"
    assert all(not s.immune for s in D._buffed_sources(bomb, mib))
    # the plain sources are untouched
    assert all("lead" in s.immune for s in ninja.sources)


def test_lead_round_is_rated_better_next_to_an_alchemist():
    """A ninja with an alchemist beside it loses fewer lives to a lead round
    than the same ninja alone (map geometry needed: skipped without it)."""
    from btd6bot.forecast import RoundForecast
    fc = RoundForecast("Monkey Meadow", "hard")
    if not fc._ready():
        print("skip: no map geometry")
        return
    from types import SimpleNamespace
    ninja = SimpleNamespace(tid="n1", kind="ninja", tiers=(3, 0, 2), x=0.30, y=0.42)
    alch = SimpleNamespace(tid="a1", kind="alchemist", tiers=(2, 0, 0), x=0.32, y=0.46)
    alone = D.simulate_round(fc.stations([ninja]), "hard", 28, fc.track).lives_lost
    helped = D.simulate_round(fc.stations([ninja, alch]), "hard", 28, fc.track).lives_lost
    assert alone > 0, "a ninja alone must leak round 28's leads"
    assert helped < alone, (alone, helped)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
