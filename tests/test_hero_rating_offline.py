"""Heroes in the damage model (docs/model_fix_plan.md item 7).

Before phase 2 every rating left the hero out: the optimizer paid for it and
counted nothing, Etienne's map-wide camo and Obyn's Druid buffs were never
seen, and the hero bookkeeping the bot uses (XP ratios, ability levels and
cooldowns) had wrong constants. The numbers pinned here are the ones of
docs/model_audit_support_heroes.md (H-XP, H-CD, G1, section 4) and of the
game model (data/game_model/attacks.json, tools/export_attacks.py).

All offline: no game, no game files.
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import abilities as A  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot import towers as T  # noqa: E402


def _beside_track(track, offset=15.0, at=0.5):
    """A point `offset` units off the first route, `at` of the way along it."""
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + offset, float(p[1])


# ---------------------------------------------------------------------------
# Hero bookkeeping: XP ratios, XP bonuses, levels by round
# ---------------------------------------------------------------------------

def test_xp_ratios_follow_the_wiki():
    """Corvus and Silas were swapped (H-XP): Corvus 1.425, Silas 1.5."""
    assert A.HERO_XP_SCALE["corvus"] == 1.425
    assert A.HERO_XP_SCALE["silas"] == 1.5
    assert A.HERO_XP_SCALE["adora"] == A.HERO_XP_SCALE["churchill"] == 1.71
    assert A.HERO_XP_SCALE["benjamin"] == A.HERO_XP_SCALE["psi"] == 1.5


def test_xp_multiplier_counts_map_and_knowledge():
    """+10% per map difficulty above Beginner; Self Taught Heroes, Monkey
    Education and Monkeys Together Strong together x1.2474 (the wiki's
    figure)."""
    every = ("Self Taught Heroes", "Monkey Education", "Monkeys Together Strong")
    assert math.isclose(A.hero_xp_multiplier("Monkey Meadow", every), 1.2474, rel_tol=1e-4)
    assert math.isclose(A.hero_xp_multiplier("Dark Castle", every), 1.3 * 1.2474, rel_tol=1e-4)
    assert A.hero_xp_multiplier("Monkey Meadow") == 1.0
    assert A.hero_xp_multiplier("not a map", ("Monkey Education",)) == 1.08


def test_levels_by_round_match_the_audit_table():
    """docs/model_audit_support_heroes.md 4.1, placed at round 6."""
    every = A.hero_xp_multiplier("Monkey Meadow", ("Self Taught Heroes", "Monkey Education",
                                                   "Monkeys Together Strong"))
    expert = A.hero_xp_multiplier("Dark Castle", ("Self Taught Heroes", "Monkey Education",
                                                  "Monkeys Together Strong"))
    rounds = (20, 30, 40, 50, 60, 70, 80, 90, 100)
    plain = [A.estimate_hero_level("quincy", 6, r, 1.0) for r in rounds]
    assert plain == [5, 6, 7, 9, 10, 12, 14, 17, 20]
    assert [A.estimate_hero_level("quincy", 6, r, every) for r in rounds] == [5, 7, 8, 9, 11, 13, 16, 19, 20]
    assert [A.estimate_hero_level("quincy", 6, r, expert) for r in rounds] == [5, 7, 9, 10, 12, 15, 19, 20, 20]
    assert [A.estimate_hero_level("adora", 6, r, every) for r in rounds] == [4, 6, 7, 8, 9, 11, 12, 15, 17]


def test_hero_abilities_follow_the_game_model():
    """Every ability of towers.HEROES has the game's unlock level and the
    cooldown it has there (attacks.json hero levels); the audit's H-CD
    table: Ball of Light 60, UCAV 90, Drone Swarm 70, Biohack 30, Syphon
    65, Long Arm 45, and Ezili's Totem at 7 / MOAB Hex at 10."""
    heroes = D.attacks()["heroes"]
    for hero, info in T.HEROES.items():
        if hero in ("corvus", "dan_dmonke", "geraldo"):
            continue              # spellbook / forms: their buttons are not the bot's
        first = {}
        for lv in range(1, 21):
            for ab in heroes[hero]["levels"][str(lv)].get("abilities", []):
                first.setdefault(ab["name"], (lv, ab.get("cooldown")))
        assert len(first) == len(info["abilities"]), (hero, first)
        for ab in info["abilities"]:
            name = next(n for n in first if n.lower().startswith(ab["name"].lower()[:8])
                        or ab["name"].lower() in n.lower())
            level, cooldown = first[name]
            assert ab["level"] == level, (hero, ab["name"], level)
            assert ab["cooldown_s"] == cooldown, (hero, ab["name"], cooldown)
    by = {a["name"]: a for a in T.HEROES["ezili"]["abilities"]}
    assert by["Sacrificial Totem"]["level"] == 7 and by["MOAB Hex"]["level"] == 10
    by = {a["name"]: a for a in T.HEROES["rosalia"]["abilities"]}
    assert by["Scatter Missile"]["level"] == 3 and by["Kinetic Charge"]["level"] == 10
    by = {a["name"]: a["cooldown_s"] for a in T.HEROES["adora"]["abilities"]}
    assert by == {"Long Arm of Light": 45, "Blood Sacrifice": 30, "Ball of Light": 60}


def test_tower_ability_cooldowns_follow_the_game_model():
    """Homeland Defense 45, Spike Storm 50, Absolute Zero 25, Glue Strike 40."""
    towers = D.attacks()["towers"]
    for (kind, path, tier), name in A.TOWER_ABILITY_AT.items():
        if name in ("IMF Loan", "Monkey-Nomics", "Overclock", "Ultraboost", "Carpet of Spikes",
                    "Jungle's Bounty", "Call to Arms", "Homeland Defense", "Spike Storm"):
            continue          # checked below or not a plain one-path ability
        tiers = [0, 0, 0]
        tiers[path - 1] = tier
        exported = towers[kind]["crosspaths"]["".join(map(str, tiers))].get("abilities", [])
        assert any(ab.get("cooldown") == A.TOWER_ABILITIES[name][0] for ab in exported), (name, exported)
    assert A.TOWER_ABILITIES["Homeland Defense"][0] == 45
    assert A.TOWER_ABILITIES["Call to Arms"][0] == 45
    assert A.TOWER_ABILITIES["Spike Storm"][0] == A.TOWER_ABILITIES["Carpet of Spikes"][0] == 50
    assert A.TOWER_ABILITIES["Ultraboost"][0] == 35


# ---------------------------------------------------------------------------
# Hero profiles
# ---------------------------------------------------------------------------

def test_corvus_stays_out():
    """His mana spells are exported as permanent attacks: not rated."""
    assert D.profile(D.hero_kind("corvus"), (20,)) is None
    assert "corvus" in D.UNRATED_HEROES


def test_quincy_long_shot_is_an_alternative():
    """Quincy's v57 LongWeapon is his Focus mode, not a second arrow."""
    p = D.profile(D.hero_kind("quincy"), (5,))
    assert [s.name for s in p.sources] == ["Attack>BaseProjectile"]
    assert math.isclose(p.sources[0].shots, 1 / 0.95, rel_tol=1e-3)


def test_psi_is_an_instakill_over_time():
    """Psi holds a bloon and takes per_tick every tick (level 14: 4 per
    0.1 s, up to 15 s: 600 in all): a grip destroys a whole bloon of up to
    600 health, and an attack grips again a cooldown (0.85 s) after its grip
    ends - 1 / (cooldown + grip time) grips a second (fandom:Psi_(BTD6);
    docs/model_audit_magic.md finding 16)."""
    p = D.profile(D.hero_kind("psi"), (14,))
    main = [s for s in p.sources if s.name == "Attack>BaseProjectile"]
    assert main and all(s.placement == "global" for s in main)
    s = main[0]
    assert math.isclose(s.damage, 600.0) and math.isclose(s.grip_rate, 40.0)
    assert math.isclose(s.shots, 1 / 0.85, rel_tol=1e-3)
    st = D.Station("psi", D.hero_kind("psi"), (14,), [D.Zone(0.0, 500.0)], [s], 0.0)
    rates = D._Rates(st)
    # a ceramic (104 health) is held 104 / 40 = 2.6 s: one every 0.85 + 2.6 s
    assert math.isclose(rates.subtree("Ceramic", 1.0, 1.0, 0, 0.0)[0], 0.85 + D.rbe("Ceramic") / 40.0,
                        rel_tol=1e-6)
    # a green, one every 0.85 + 3 / 40 s
    assert math.isclose(rates.subtree("Green", 1.0, 1.0, 0, 0.0)[0], 0.85 + 3 / 40.0, rel_tol=1e-3)
    # a MOAB loses at most a grip's 600 over 0.85 + 15 s, crowd or not
    for rho in (1e-4, 1.0):
        hp, carry, killed, _ = rates.get("Moab", 1.0, rho, 0)
        assert math.isclose(hp * (1.0 + carry / D.layer("Moab").hp), 600.0 / (0.85 + 15.0), rel_tol=1e-6)
        assert killed == 0.0
    # no MOABs before level 14, no ceramics before 7
    assert not any(src.can_hit(D.layer("Moab")) for src in D.profile(D.hero_kind("psi"), (13,)).sources)
    assert not any(src.can_hit(D.layer("Ceramic")) for src in D.profile(D.hero_kind("psi"), (6,)).sources)


# ---------------------------------------------------------------------------
# Hero buffs on the towers around it
# ---------------------------------------------------------------------------

def test_etienne_level_8_camo_reaches_every_tower():
    """The UAV's buff sits on a sub-tower (G1): hoisted, a tower anywhere
    on the map sees camo from level 8 on, and not before."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    dart = D.Placed("d", "dart", (0, 0, 0), x, z)
    for level, camo in ((7, False), (8, True), (20, True)):
        far = D.Placed("h", D.hero_kind("etienne"), (level,), x + 300.0, z + 300.0)
        st = D.station_for(dart, [dart, far], tr)
        assert any(s.camo for s in st.sources) is camo, level


def test_obyn_buffs_druids():
    """L2 +1 pierce to Druids, L5 +40% range to Druids of the Jungle
    (x-3-x), L8 camo to Druids in his range."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    druid = D.Placed("d", "druid", (1, 3, 0), x, z)
    base = D.station_for(druid, [druid], tr)
    thorns = min(base.parts or [base], key=lambda s: sum(zz.length for zz in s.zones if zz))
    alone = sum(zz.length for zz in thorns.zones if zz)

    def board(level):
        hero = D.Placed("h", D.hero_kind("obyn"), (level,), x + 10.0, z)
        return D.station_for(druid, [druid, hero], tr)

    def thorn_reach(st):
        return min(sum(zz.length for zz in s.zones if zz) for s in [st] + list(st.parts))

    pierce = {s.name: s.pierce for s in base.sources}
    assert all(s.pierce == pierce[s.name] + 1 for s in board(2).sources)
    assert math.isclose(thorn_reach(board(4)), alone)
    assert thorn_reach(board(5)) > 1.3 * alone                 # 35 -> 49 units of range
    assert not any(s.camo for s in board(7).sources)
    assert any(s.camo for s in board(8).sources)
    # the range buff is for Druids of the Jungle only
    plain = D.Placed("p", "druid", (2, 0, 0), x, z)
    hero = D.Placed("h", D.hero_kind("obyn"), (5,), x + 10.0, z)
    assert D._buffs_at(plain, [plain, hero])[1].mult == 1.0
    assert math.isclose(D._buffs_at(druid, [druid, hero])[1].mult, 1.4)


def test_heroes_can_be_switched_off():
    saved = D.HERO_RATING
    try:
        D.HERO_RATING = False
        from btd6bot.forecast import RoundForecast
        fc = RoundForecast("Monkey Meadow", "chimps", hero="obyn")
        assert fc.hero_level([SimpleNamespace(tid="hero", kind="hero", placed_round=6)], 40) is None
    finally:
        D.HERO_RATING = saved


# ---------------------------------------------------------------------------
# The forecast and the optimizer put the hero on the board
# ---------------------------------------------------------------------------

def test_forecast_rates_the_hero_at_its_level():
    from btd6bot.forecast import RoundForecast
    fc = RoundForecast("Monkey Meadow", "chimps", hero="obyn")
    assert fc._ready()
    x, z = _beside_track(fc.track)
    fx, fy = fc.track.world_to_frac(x, z)
    druid = SimpleNamespace(tid="d", kind="druid", tiers=(1, 3, 0), x=fx, y=fy, placed_round=6)
    hero = SimpleNamespace(tid="hero", kind="hero", tiers=(0, 0, 0), x=fx + 0.01, y=fy, placed_round=6)
    assert fc.hero_level([druid, hero], 20) == A.estimate_hero_level("obyn", 6, 20)
    assert fc.hero_level([druid], 20) is None
    with_hero = fc.margins([druid, hero], [24, 30])
    without = RoundForecast("Monkey Meadow", "chimps").margins([druid, hero], [24, 30])
    assert all(with_hero[r] >= without[r] for r in (24, 30))
    # the stations follow the hero's level: at level 8 Obyn gives the
    # druid camo, at level 4 he does not
    camo = {lv: any(s.camo for st in fc.stations([druid, hero], lv) if st.tid == "d" for s in st.sources)
            for lv in (4, 8)}
    assert camo == {4: False, 8: True}


def test_optimizer_evaluator_rates_the_hero():
    import optimize_builds as O
    setup = O.MapSetup("Monkey Meadow", "chimps")
    ev = O.Evaluator(setup, "chimps", hero="etienne")
    spot = setup.hero_spot("etienne", [])
    assert spot is not None
    sp = setup.ranked_spots("dart")[0]
    dart = O.Tower("d", "dart", sp, (0, 0, 0))
    h8 = O.Tower("hero", "hero", spot, (8,))
    st = ev.station_of(dart, [dart, h8])
    assert any(s.camo for s in st.sources)
    assert not any(s.camo for s in ev.station_of(dart, [dart, O.Tower("hero", "hero", spot, (7,))]).sources)
    assert O.Evaluator(setup, "chimps").station_of(h8, [dart, h8]) is None     # no hero named


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
