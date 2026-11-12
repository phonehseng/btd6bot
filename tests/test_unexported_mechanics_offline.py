"""Mechanics the attack export does not carry (docs/model_fix_plan.md item 12).

Each tower below gets value from a behaviour tools/export_attacks.py never
reads; btd6bot/dps_model.py adds it (UNEXPORTED_RATING) from the export
where it has the numbers and from the audits otherwise. Every test pins one
mechanic: its numbers, and that it raises the tower's rating on a round
where it matters (UNEXPORTED_RATING on against off).

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402


def _beside(track, at=0.5, offset=15.0):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + offset, float(p[1])


def _margin(board, mode, rnd, track, on=True):
    saved = D.UNEXPORTED_RATING
    try:
        D.UNEXPORTED_RATING = on
        D.profile.cache_clear()
        return D.round_margin(D.stations_for(board, track), mode, rnd, track)
    finally:
        D.UNEXPORTED_RATING = saved
        D.profile.cache_clear()


def _gain(board, mode, rnd, track):
    return _margin(board, mode, rnd, track, False), _margin(board, mode, rnd, track, True)


def _source(kind, tiers, name):
    return next(s for s in D.profile(kind, tiers).sources if s.name.startswith(name))


def test_spirit_of_the_forest_vines():
    """Vines on the whole track tick twice a second: 2 / 3 / 4 damage beyond
    100, within 100, within 50 of the druid; 10 / 15 / 30 to Ceramics and
    blimps; camo yes, lead only with 1-x-x (magic finding 5)."""
    vines = [s for s in D.profile("druid", (0, 5, 0)).sources if s.name.startswith("Spirit vines")]
    assert len(vines) == 3 and all(s.camo and s.shots == 2.0 for s in vines)
    inner = sum(s.damage for s in vines)
    big = sum(s.damage_vs(D.layer("Moab")) for s in vines)
    assert (inner, big) == (4.0, 30.0)
    assert all("lead" in s.immune for s in vines)
    assert not any("lead" in s.immune for s in D.profile("druid", (1, 5, 0)).sources
                   if s.name.startswith("Spirit vines"))
    tr = D.Track("Monkey Meadow")
    off, on = _gain([D.Placed("d", "druid", (0, 5, 0), *_beside(tr))], "hard", 40, tr)
    assert on >= 3.0 * off, (off, on)


def test_prince_of_darkness_graveyard():
    """Prince of Darkness, graveyard half full: bolts +5 damage, undead of 8
    damage and 6.5 pierce, 2.5 a summon at 1.5x speed (magic finding 6)."""
    bolt = _source("wizard", (0, 0, 5), "Attack>BaseProjectile")
    undead = _source("wizard", (0, 0, 5), "Attack Necromancer>Projectile")
    assert bolt.damage == 1.0 + D.POD_BOLT_EXTRA
    assert (undead.damage, undead.pierce) == (8.0, 6.5)
    tr = D.Track("Monkey Meadow")
    off, on = _gain([D.Placed("w", "wizard", (0, 0, 5), *_beside(tr))], "hard", 63, tr)
    assert on >= 3.0 * off, (off, on)


def test_wizard_lord_phoenix():
    """The permanent phoenix: 20 damage, 50 pierce every 0.1 s, read like a
    circling plane's darts (x0.4) over the map (magic finding 7)."""
    bird = _source("wizard", (0, 5, 0), "Wizard Lord Phoenix")
    assert (bird.damage, bird.pierce, bird.placement) == (20.0, 50.0, "global")
    assert math.isclose(bird.shots, D.AIR_PATTERN_EFFICIENCY / 0.1)
    assert not bird.ability


def test_archmage_strips_its_own_camo():
    """An Archmage (wizard 5-0-0) sees no camo with its bolts, but its
    Shimmer strips the camo off what is in its range: it pops the camo
    round it was rated useless on (magic finding 7)."""
    tr = D.Track("Monkey Meadow")
    off, on = _gain([D.Placed("w", "wizard", (5, 0, 0), *_beside(tr))], "hard", 24, tr)
    assert off <= D.MARGIN_FLOOR * 1.01 and on >= 2.0, (off, on)


def test_bloon_master_alchemist_shrinks_blimps():
    """The shrink potion (the export's ShrinkPotion: every 10 s, 200 pierce,
    MOAB / BFB / DDT / ZOMG cost 19 / 49 / 49 / 99 more) turns blimps into
    Reds; never a BAD (magic finding 8)."""
    potion = _source("alchemist", (0, 0, 5), "Bloon Master shrink potion")
    assert math.isclose(potion.shots, 0.1) and potion.pierce == 200.0
    assert potion.pierce_cost == {"Moab": 19.0, "Bfb": 49.0, "Ddt": 49.0, "Zomg": 99.0}
    assert potion.can_hit(D.layer("Zomg")) and not potion.can_hit(D.layer("Bad"))
    assert not potion.can_hit(D.layer("Ceramic"))
    tr = D.Track("Monkey Meadow")
    board = [D.Placed("a", "alchemist", (0, 0, 5), *_beside(tr)),
             D.Placed("s", "sniper", (0, 2, 4), *_beside(tr, at=0.3))]
    off, on = _gain(board, "hard", 85, tr)
    assert on >= 4.0 * off and on >= 2.0, (off, on)


def test_sub_commander_aura():
    """Sub Commander: x2 damage and +4 pierce to the Subs within 42, itself
    included; two commanders do not stack (military M11)."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside(tr)
    cmd = D.Placed("c", "sub", (0, 0, 5), x, z)
    other = D.Placed("o", "sub", (2, 0, 4), x + 10.0, z)
    st = D.station_for(cmd, [cmd, other], tr)
    dart = next(s for s in st.sources if s.name == "Attack>Projectile")
    assert dart.damage == 4.0 and dart.pierce == 1.0 + 4.0
    second = D.Placed("c2", "sub", (0, 0, 5), x - 10.0, z)
    st2 = D.station_for(other, [cmd, second, other], tr)
    plain = D.station_for(other, [other], tr)
    for a, b in zip(st2.sources, plain.sources):
        assert a.damage == 2.0 * b.damage and a.pierce == b.pierce + 4.0
    off, on = _gain([cmd, other], "hard", 40, tr)
    assert on >= 2.0 * off, (off, on)


def test_carrier_flagship_speeds_water_towers_and_aces():
    """Carrier Flagship: attack cooldown -15% for water towers and Aces on
    the map, itself included (military M11)."""
    tr = D.Track("Monkey Meadow")
    flag = D.Placed("f", "buccaneer", (5, 0, 0), *_beside(tr))
    sub = D.Placed("s", "sub", (2, 0, 4), *_beside(tr, at=0.5, offset=-15.0))
    dart = D.Placed("d", "dart", (0, 0, 2), *_beside(tr, at=0.55))
    for t, sped in ((sub, True), (dart, False)):
        with_ = D.station_for(t, [flag, t], tr).sources[0].shots
        alone = D.station_for(t, [t], tr).sources[0].shots
        assert math.isclose(with_, alone / D.FLAGSHIP_RATE) if sped else with_ == alone


def test_pre_emptive_strike_hits_every_blimp_once():
    """Pre-emptive Strike: 750 damage on every blimp that enters the map
    (military M10); a MOAB (200) dies to it, the BFB it is inside does not
    get it again. Applied before the first station (_preempted)."""
    tr = D.Track("Monkey Meadow")
    sub = D.Placed("p", "sub", (0, 5, 0), *_beside(tr))
    sts = D.with_parts(D.stations_for([sub], tr))
    lots = D._lots("hard", 40, tr)[0]
    out = D._preempted(lots, sts, 1.0)
    moab = [lot for lot in out if lot.bloon == "Moab"]
    assert moab and all(lot.free == D.PREEMPT_DAMAGE for lot in moab)
    bad = D.Lot(path=0, t0=0.0, bloon="Bad", count=1.0, rho=0.01, speed=5.0)
    assert D._preempted([bad], sts, 1.0)[0].free == 0.0
    off, on = _gain([sub, D.Placed("s", "sniper", (0, 2, 4), *_beside(tr, at=0.3))], "hard", 40, tr)
    assert on > off, (off, on)


def test_comanche_mini_helis():
    """Comanche Commander: three permanent mini-Comanches, each a spray of
    3 darts every 0.228 s, 3 damage, 4 pierce; Comanche Defense half a
    mini on average (military M6)."""
    minis = _source("heli", (2, 0, 5), "Mini-Comanche darts")
    assert math.isclose(minis.shots, 3 * 3 / 0.228)
    assert (minis.damage, minis.pierce) == (3.0, 4.0)
    assert math.isclose(_source("heli", (2, 0, 4), "Mini-Comanche darts").shots, 0.5 * 3 / 0.228)
    tr = D.Track("Monkey Meadow")
    off, on = _gain([D.Placed("h", "heli", (2, 0, 5), *_beside(tr))], "hard", 63, tr)
    assert on >= 2.0 * off, (off, on)


def test_ice_shards_and_icicles():
    """Ice Shards (3-x-x: 3 shards of 2 damage, 3 pierce; 5-x-x: 6 of 5)
    and Icicles (x-x-4: 3 damage, 3 pierce) off the frozen bloons popped,
    two a freeze shot (primary F6)."""
    freeze = _source("ice", (3, 0, 0), "Attack>BaseProjectile")
    shards = _source("ice", (3, 0, 0), "Ice Shards")
    assert math.isclose(shards.shots, freeze.shots * D.FROZEN_POPPED_PER_SHOT * 3)
    assert (shards.damage, shards.pierce) == (2.0, 3.0)
    assert _source("ice", (5, 0, 0), "Ice Shards").damage == 5.0
    icicles = _source("ice", (0, 0, 4), "Icicles")
    assert (icicles.damage, icicles.pierce) == (3.0, 3.0)
    tr = D.Track("Monkey Meadow")
    board = [D.Placed("i", "ice", (3, 0, 0), *_beside(tr)), D.Placed("d", "dart", (0, 0, 2), *_beside(tr, 0.52, -15))]
    off, on = _gain(board, "medium", 20, tr)
    assert on >= 2.0 * off, (off, on)


def test_blazing_sun_fire():
    """The Blazing Sun: every 50th shot burns its target 600 over 12 s, no
    more than the bloon's whole health; the spread is left out. About the
    audit's +50% on a blimp round (primary F6)."""
    fire = _source("desperado", (5, 0, 0), "The Blazing Sun fire")
    gun = max((s for s in D.profile("desperado", (5, 0, 0)).sources if s.damage > 0), key=lambda s: s.shots)
    assert math.isclose(fire.shots, gun.shots / 50.0) and fire.dot_total == 600.0 and fire.dot_one_bloon
    tr = D.Track("Monkey Meadow")
    off, on = _gain([D.Placed("d", "desperado", (5, 0, 0), *_beside(tr))], "hard", 40, tr)
    assert 1.2 * off <= on <= 2.5 * off, (off, on)


def test_glaives_ricochet_further():
    """Glaive Ricochet and M.O.A.R. Glaives bounce 60 / 180 units further
    than the throw (primary F5); off by default (GLAIVE_BOUNCE_RATING) after
    calibration. Glaive Lord's bounce and seeking are never credited: either
    over-rated the Quiet Street loss case (tests/test_moab_model_offline.py)."""
    assert not D.GLAIVE_BOUNCE_RATING
    throw = D.crosspath("boomerang", "000")["range"]
    assert _source("boomerang", (4, 0, 0), "Attack>Projectile").zone_radius == throw
    saved = D.GLAIVE_BOUNCE_RATING
    try:
        D.GLAIVE_BOUNCE_RATING = True
        D.profile.cache_clear()
        for tiers, bounce in (((3, 0, 0), 60.0), ((4, 0, 0), 180.0), ((5, 0, 0), 0.0)):
            glaive = _source("boomerang", tiers, "Attack>Projectile")
            assert glaive.zone_radius == throw + bounce and glaive.placement == "aimed", tiers
    finally:
        D.GLAIVE_BOUNCE_RATING = saved
        D.profile.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
