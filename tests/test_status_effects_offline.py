"""Status effects as time on the track, and damage-taken debuffs
(docs/model_fix_plan.md item 9).

A stunned, slowed or pushed bloon spends longer in every tower's reach; a
debuffed one takes more from every hit. The numbers pinned here are the
audits' (docs/model_audit_military.md M3, model_audit_primary.md F1/F3,
model_audit_magic.md finding 13) as the game model gives them
(data/game_model/attacks.json "effects", "zones").

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402

D.STATUS_RATING = True        # on by default; these tests are about it


def _beside_track(track, offset=15.0, at=0.5):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + offset, float(p[1])


def _lot(track, bloon, rho=1e-3, mode="chimps"):
    """One lot of `bloon` on route 0, at the mode's speed."""
    speed = D.layer(bloon).speed * D.mode_rules(mode)["speed"]
    return D.Lot(path=0, t0=0.0, bloon=bloon, count=1.0, rho=rho, speed=speed, speed_mult=D.mode_rules(mode)["speed"])


def _controls(board, track):
    stations = D.with_parts(D.stations_for(board, track))
    return D._Controls(stations, track, 1.0), stations


def test_maim_moab_holds_blimps():
    """Maim MOAB (sniper 4-x-x): one 1.59 s shot stuns a MOAB 3 s, a BFB
    1.5 s, a ZOMG or DDT 0.75 s - a lone MOAB is held for good, a BFB 94%
    of the time, a ZOMG 47% (fandom:Maim_MOAB). The model holds a bloon at
    most MAX_HOLD of its time in the zone."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    sniper = D.Placed("s", "sniper", (4, 0, 0), x, z)
    ctl, stations = _controls([sniper], tr)
    (st, src), = [(st, s) for st, s in ctl.holders if "maim" in s.effects]
    for bloon, share in (("Moab", 3 / 1.59), ("Bfb", 1.5 / 1.59), ("Zomg", 0.75 / 1.59)):
        lot = _lot(tr, bloon)
        per, stay = ctl._per_bloon(st, src, D.Layer(**{**D.layer(bloon).__dict__, "speed": lot.speed}),
                                   lot.rho, 0)
        key = D.MAIM_KEYS[bloon.capitalize() if bloon != "Moab" else "Moab"]
        assert math.isclose(per * src.effects["maim"][key], share, rel_tol=1e-3), bloon
        u = min(D.MAX_HOLD, share)
        (a, b, delay), = ctl.segments(lot)
        cap = D.MAX_STALL * tr.paths[0]["length"] / lot.speed
        assert math.isclose(delay, min(cap, stay * u / (1 - u)), rel_tol=1e-6), bloon
    # the BAD shrugs it off (badDuration 0)
    assert ctl.segments(_lot(tr, "Bad")) == ()


def test_cripple_moab_adds_five_damage_per_hit():
    """Cripple MOAB (sniper 5-x-x): a crippled blimp takes +5 from every
    hit for 7 s (MOAB) - a lone MOAB is always crippled, so every hit of a
    tower beside the sniper does 5 more (bw:Cripple_MOAB_(BTD6))."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    board = [D.Placed("s", "sniper", (5, 0, 0), x, z), D.Placed("d", "dart", (0, 0, 0), x + 20.0, z)]
    ctl, stations = _controls(board, tr)
    dart, = [st for st in stations if st.tid == "d"]
    bonus, seen = ctl.influence(dart, D.layer("Moab"), 0, 1e-3)
    assert math.isclose(bonus, 5.0) and seen == 0.0
    plain = D._Rates(D.stations_for(board[1:], tr)[0]).get("Moab", 1.0, 1e-3, 0)[0]
    dart.influence = D._Influence(ctl, dart)
    dart.strength = 1.0
    boosted = D._Rates(dart).get("Moab", 1.0, 1e-3, 0)[0]
    assert math.isclose(boosted / plain, 6.0, rel_tol=1e-6)        # 1 damage per dart -> 6


def test_embrittlement_and_super_brittle():
    """Embrittlement (ice 4-x-x): +1 damage taken for 2 s and camo
    stripped; Super Brittle (5-x-x): +4 for 3 s (fandom:Embrittlement,
    fandom:Super_Brittle)."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    x2, z2 = _beside_track(tr, offset=-15.0)     # across the track from the ice
    for tiers, add, life in (((4, 0, 0), 1.0, 2.0), ((5, 0, 0), 4.0, 3.0)):
        board = [D.Placed("i", "ice", tiers, x, z), D.Placed("d", "dart", (0, 0, 0), x2, z2)]
        ctl, stations = _controls(board, tr)
        (st, src), = [(st, s) for st, s in ctl.debuffers]
        assert src.effects["debuff"]["add"] == add and src.effects["debuff"]["lifespan"] == life
        dart, = [s for s in stations if s.tid == "d"]
        bonus, seen = ctl.influence(dart, D.layer("RedCamo"), 0, 0.05)
        per, stay = ctl._per_bloon(st, src, D.layer("Red"), 0.05, 0)
        # only on the stretch of the dart's zone where bloons carry the debuff (_debuffed_share)
        zd, zi = dart.zones[0], st.zones[0]
        share = D._debuffed_share(zd.entry, zd.entry + zd.length, zi.entry,
                                  zi.entry + zi.length + life * D.layer("RedCamo").speed)
        assert 0.0 < share <= 1.0
        assert math.isclose(bonus, add * share * min(1.0, per * life), rel_tol=1e-6)
        assert math.isclose(seen, min(1.0, per * stay), rel_tol=1e-6) and seen > 0.0
    # a camo red is out of the dart's sight alone, and seen at that share with the ice
    alone = D._Rates(D.stations_for([D.Placed("d", "dart", (0, 0, 0), x2, z2)], tr)[0])
    assert alone.get("RedCamo", 1.0, 0.05, 0) is None


def test_glue_slows():
    """Glue (0-0-0): 50% slow for 11 s - a bloon it hits loses 5.5 s; MOAB
    Glue (0-0-3) slows blimps to x0.625 (25% x the "Moabs" modifier 2.5:
    fandom:MOAB_Glue); the plain glue never touches blimps."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    glue = D.Placed("g", "glue", (0, 0, 0), x, z)
    st = D.station_for(glue, [glue], tr)
    assert st is not None                      # it used to be no station at all
    ctl, _ = _controls([glue], tr)
    red = _lot(tr, "Red", rho=1e-3)
    (a, b, delay), = ctl.segments(red)
    (gst, src), = ctl.holders
    per, stay = ctl._per_bloon(gst, src, D.Layer(**{**D.layer("Red").__dict__, "speed": red.speed}), red.rho, 0)
    assert math.isclose(delay, min(1.0, per * stay) * 11.0 * 0.5, rel_tol=1e-6)
    assert ctl.segments(_lot(tr, "Moab")) == ()
    eff = D.profile("glue", (0, 0, 3)).sources[0].effects
    assert math.isclose(D._slow_factor(eff, D.layer("Moab")), 0.625)


def test_arctic_wind_zone():
    """Arctic Wind (ice 0-3-0): bloons in its range move at x0.6 - a bloon
    crossing L units of its zone at speed v loses L / v x (1/0.6 - 1)."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    ice = D.Placed("i", "ice", (0, 3, 0), x, z)
    ctl, stations = _controls([ice], tr)
    lot = _lot(tr, "Red")
    segs = ctl.segments(lot)
    zone = stations[0].zones[0]
    # the wind's delay, with the freeze of the same tower on the same stretch
    wind = sum(d for a, b, d in segs if a == zone.entry)
    assert wind >= zone.length / lot.speed * (1 / 0.6 - 1) - 1e-6
    assert ctl.segments(_lot(tr, "Moab")) == ()     # Arctic Wind leaves blimps alone ("Moabs" excluded)


def test_slow_gives_downstream_towers_more_time():
    """A slowed bloon spends longer in the zones after the slow: a dart
    behind an Arctic Wind holds a round it leaks alone."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr, at=0.45)
    x2, z2 = _beside_track(tr, at=0.5)
    dart = D.Placed("d", "dart", (0, 0, 2), x2, z2)
    ice = D.Placed("i", "ice", (0, 3, 0), x, z)
    alone = D.round_margin(D.stations_for([dart], tr), "medium", 10, tr)
    both = D.round_margin(D.stations_for([dart, ice], tr), "medium", 10, tr)
    saved = D.STATUS_RATING
    try:
        D.STATUS_RATING = False
        off = D.round_margin(D.stations_for([dart, ice], tr), "medium", 10, tr)
    finally:
        D.STATUS_RATING = saved
    assert both > off >= alone


def test_sabotage_slows_blimps_only():
    """Bloon Sabotage is pressed in blimp rounds when the blimps come
    (abilities.ROUND_START): its slow counts on MOAB-class bloons only."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    ninja = D.Placed("n", "ninja", (0, 4, 0), x, z)
    ctl, _ = _controls([ninja], tr)
    sabotage = [(st, s) for st, s in ctl.holders if s.ability_use == "moab" and "slow" in s.effects]
    assert sabotage
    moab = _lot(tr, "Moab")
    st, src = sabotage[0]
    per, stay = ctl._per_bloon(st, src, D.Layer(**{**D.layer("Moab").__dict__, "speed": moab.speed}), moab.rho, 0)
    assert per > 0.0
    assert ctl._per_bloon(st, src, D.layer("Red"), moab.rho, 0)[0] == 0.0
    assert sum(d for _, _, d in ctl.segments(moab)) > 0.0


def test_bad_ignores_pushes():
    """MOAB Press pushes blimps back 2 units a hit; a BAD is immune."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    rang = D.Placed("b", "boomerang", (0, 0, 4), x, z)
    ctl, _ = _controls([rang], tr)
    assert sum(d for _, _, d in ctl.segments(_lot(tr, "Moab"))) > 0.0
    assert ctl.segments(_lot(tr, "Bad")) == ()


def test_stall_is_capped():
    """All delays together add at most MAX_STALL x the lot's own time on
    its route."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    board = [D.Placed(f"s{i}", "sniper", (4, 0, 0), x + 3 * i, z) for i in range(6)]
    ctl, _ = _controls(board, tr)
    lot = _lot(tr, "Moab")
    total = sum(d for _, _, d in ctl.segments(lot))
    assert total <= D.MAX_STALL * tr.paths[0]["length"] / lot.speed + 1e-6


def test_time_along_the_route():
    """_time_at and _pos_at are inverses with delays on the route."""
    lot = D.Lot(path=0, t0=5.0, bloon="Red", count=1.0, rho=0.1, speed=10.0)
    segs = ((100.0, 200.0, 30.0), (150.0, 160.0, 5.0))
    for x in (0.0, 50.0, 120.0, 155.0, 199.0, 400.0):
        t = D._time_at(lot, segs, x)
        assert math.isclose(D._pos_at(lot, segs, t), x, abs_tol=1e-6)
    assert math.isclose(D._time_at(lot, segs, 300.0), 5.0 + 30.0 + 35.0)


def _margins(base, extra, mode, rnd, track):
    """(base alone, base + extra, base + extra with status effects off)."""
    saved = D.STATUS_RATING
    try:
        D.STATUS_RATING = True
        alone = D.round_margin(D.stations_for(base, track), mode, rnd, track)
        both = D.round_margin(D.stations_for(base + extra, track), mode, rnd, track)
        D.STATUS_RATING = False
        off = D.round_margin(D.stations_for(base + extra, track), mode, rnd, track)
    finally:
        D.STATUS_RATING = saved
    return alone, both, off


def _damage_board(track):
    return [D.Placed("d", "dart", (0, 0, 2), *_beside_track(track, at=0.5)),
            D.Placed("t", "tack", (2, 0, 0), *_beside_track(track, offset=-15.0, at=0.55))]


def test_status_effects_are_on_by_default():
    """Item 9 is on by default once it is fast enough
    (docs/model_fix_plan.md phase 2b, item A)."""
    import re
    assert re.search(r"^STATUS_RATING = True$", Path(D.__file__).read_text(encoding="utf-8"), re.M)


def test_ice_board_holds_longer():
    """An Enhanced Freeze (ice 0-2-0) and a Permafrost (2-0-0) in front of
    a dart and a tack: frozen and slowed bloons stay longer in the damage
    towers' reach. Pinned: with the ice the round holds at least 1.5x the
    board without it, and the ice's control is worth more than its own
    damage (status effects off)."""
    tr = D.Track("Monkey Meadow")
    ice = [D.Placed("i", "ice", (0, 2, 0), *_beside_track(tr, at=0.45)),
           D.Placed("i2", "ice", (2, 0, 0), *_beside_track(tr, offset=-15.0, at=0.47))]
    alone, both, off = _margins(_damage_board(tr), ice, "medium", 20, tr)
    assert both >= 1.5 * alone, (alone, both)
    assert both >= 1.3 * off, (both, off)


def test_glue_board_holds_longer():
    """A Glue Hose (glue 0-0-2) does no damage; its 50% slow alone lets the
    dart and tack behind it hold round 20 with a far wider margin."""
    tr = D.Track("Monkey Meadow")
    glue = [D.Placed("g", "glue", (0, 0, 2), *_beside_track(tr, at=0.45))]
    alone, both, off = _margins(_damage_board(tr), glue, "medium", 20, tr)
    assert math.isclose(off, alone, rel_tol=1e-6)          # no damage of its own
    assert both >= 1.5 * alone, (alone, both)


def test_maim_moab_on_a_moab_round():
    """Maim MOAB (sniper 4-0-0) on hard round 40 (one MOAB): stunned 3 s
    of every 1.59 s, the MOAB stands in the boomerang's and dart's reach
    for longer. By default its hits are shared among the ~28 bloons a
    burst's packing puts in the sniper's zone, so the stun adds little;
    counted as the one MOAB it is (STATUS_GROUP_CAP, off by default after
    calibration) it is worth at least 15% on top of the sniper's damage."""
    tr = D.Track("Monkey Meadow")
    base = [D.Placed("b", "boomerang", (0, 2, 4), *_beside_track(tr, at=0.5)),
            D.Placed("d", "dart", (0, 2, 4), *_beside_track(tr, offset=-15.0, at=0.6))]
    sniper = [D.Placed("s", "sniper", (4, 0, 0), *_beside_track(tr, at=0.4))]
    alone, both, off = _margins(base, sniper, "hard", 40, tr)
    assert both >= off and both > alone
    saved = D.STATUS_GROUP_CAP
    try:
        D.STATUS_GROUP_CAP = True
        alone, capped, off = _margins(base, sniper, "hard", 40, tr)
    finally:
        D.STATUS_GROUP_CAP = saved
    assert capped >= 1.15 * off, (capped, off)


def test_monarch_of_storms_blows_ddts_back():
    """Monarch of Storms (druid 5-0-0): its tornado (100 damage, 200
    pierce, MOAB / BFB / DDT / ZOMG pierce cost 2 / 8 / 6 / 32) blows
    blimps back 100-400 units (capped at 400 since v56, ZOMGs half as far,
    BADs never: docs/tower_research_2026-11.md). Blown back, a bloon walks
    track it crossed already; that is credited as time, not as more track
    in reach. Pinned on hard round 90 (three camo DDTs and fortified
    leads): the druid gives the sniper board a clear margin, and most of it
    is the blowback (status effects off it is far less)."""
    tr = D.Track("Monkey Meadow")
    base = [D.Placed("s1", "sniper", (0, 2, 5), *_beside_track(tr, at=0.5)),
            D.Placed("s2", "sniper", (4, 2, 0), *_beside_track(tr, at=0.3)),
            D.Placed("s3", "sniper", (2, 0, 5), *_beside_track(tr, offset=-15.0, at=0.7)),
            D.Placed("v", "village", (2, 2, 0), *_beside_track(tr, offset=30.0, at=0.6))]
    druid = [D.Placed("dr", "druid", (5, 0, 0), *_beside_track(tr, at=0.45))]
    alone, both, off = _margins(base, druid, "hard", 90, tr)
    assert alone < 1.0 and both >= 2.0, (alone, both)
    assert both >= 1.5 * off, (both, off)
    eff = next(s for s in D.profile("druid", (5, 0, 0)).sources if "blowback" in s.effects).effects
    assert D._control_applies(eff, "blowback", D.layer("Ddt"))
    assert not D._control_applies(eff, "blowback", D.layer("Bad"))
    assert eff["blowback"]["distance_max"] == 400.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
