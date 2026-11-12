"""Abilities credited by their uptime (docs/model_fix_plan.md item 8).

The bot presses the abilities it may press blind on cooldown, and the MOAB
ones in blimp rounds (btd6bot/abilities.py), so the damage model counts
each one at duty cycle: effect x min(1, duration / cooldown). The numbers
pinned here are the audits' (docs/model_audit_primary.md F2,
model_audit_support_heroes.md V4/S1/S2) as the game model gives them
(data/game_model/attacks.json "abilities").

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


def _ability(kind, tiers, name=None):
    """The sources of a crosspath that come from its abilities."""
    return [s for s in D.profile(kind, tiers).sources if s.ability and (name is None or s.ability == name)]


def _beside_track(track, offset=15.0, at=0.5):
    pts = track.paths[0]["xyz"]
    p = pts[int(len(pts) * at)]
    return float(p[0]) + offset, float(p[1])


def test_moab_eliminator_every_ten_seconds():
    """4,500 damage on a blimp, once every 10 s, at any range: about 4x
    the passive missile's blimp damage (F2)."""
    missile, = [s for s in _ability("bomb", (0, 5, 0)) if s.damage == 4500.0]
    assert math.isclose(missile.shots, 0.1)
    assert missile.only_tags == frozenset({"Moabs"}) and missile.reach == 0.0
    passive = [s for s in D.profile("bomb", (0, 5, 0)).sources if not s.ability and "Moabs" in s.bonus]
    blimp = D.layer("Moab")
    per_second = sum(s.shots * s.damage_vs(blimp) for s in passive)
    assert 3.0 < missile.shots * missile.damage / per_second < 5.0


def test_maelstroms_at_their_duty_cycle():
    """Super Maelstrom: 4 blades every 0.045 s for 9 s of 20 = 40 blades a
    second of 300 pierce; Blade Maelstrom: 2 blades for 3 s of 20."""
    blades, = _ability("tack", (0, 5, 0), "Super Maelstrom")
    assert math.isclose(blades.shots, 4 * (9 / 0.045) / 20, rel_tol=1e-6)
    assert blades.pierce == 300.0
    small, = _ability("tack", (0, 4, 0), "Blade Maelstrom")
    assert math.isclose(small.shots, 2 * (3 / 0.045) / 20, rel_tol=1e-6)


def test_spike_storms():
    """Spike Storm: 200 piles over the track every 50 s (the game model's
    cooldown); Carpet of Spikes also casts it by itself every 15 s
    (fandom:Carpet_of_Spikes: 200 piles of 10 pierce)."""
    storm = _ability("spike", (0, 4, 0))
    assert math.isclose(sum(s.shots for s in storm), 200 / 50, rel_tol=1e-6)
    carpet = _ability("spike", (0, 5, 0))
    assert math.isclose(sum(s.shots for s in carpet), 200 / 50 + 200 / 15, rel_tol=1e-6)
    assert all(s.placement == "track" and s.pierce == 10.0 for s in carpet)


def test_call_to_arms_and_homeland_defense():
    """x1.5 attack speed and pierce for 15 s in 45: +42% on a tower whose
    pierce is used up (1/3 x 1.5^2 + 2/3); Homeland Defense x2 for 20 s in
    45: +133% (docs/model_audit_support_heroes.md V4)."""
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    tack = D.Placed("t", "tack", (0, 0, 0), x, z)

    def capacity(board):
        st = D.station_for(tack, board, tr)
        return sum(s.shots * s.pierce for s in st.sources)

    alone = capacity([tack])
    for tiers, gain in (((0, 4, 0), 1 / 3 * 1.5 ** 2 + 2 / 3), ((0, 5, 0), 20 / 45 * 2 ** 2 + 25 / 45)):
        far = D.Placed("v", "village", tiers, x + 400.0, z + 400.0)        # global: no range needed
        assert math.isclose(capacity([tack, far]) / alone, gain, rel_tol=1e-6), tiers
    assert math.isclose(1 / 3 * 1.5 ** 2 + 2 / 3, 1.4167, rel_tol=1e-4)


def test_turbo_and_perma_charge():
    """Turbo Charge: weapon rate x0.2 (5x the shots) and +1 damage for 10 s
    in 45; Perma Charge: +10 damage for 15 s in 45."""
    turbo, = D.profile("boomerang", (0, 4, 0)).boosts
    assert math.isclose(turbo["share"], 10 / 45) and turbo["rate"] == 0.2 and turbo["damage_add"] == 1.0
    perma, = D.profile("boomerang", (0, 5, 0)).boosts
    assert math.isclose(perma["share"], 15 / 45) and perma["damage_add"] == 10.0
    tr = D.Track("Monkey Meadow")
    x, z = _beside_track(tr)
    rang = D.Placed("b", "boomerang", (0, 4, 0), x, z)
    st = D.station_for(rang, [rang], tr)
    plain = D.station_for(rang, [rang], tr, pressed=False)
    shots = sum(s.shots for s in st.sources) / sum(s.shots for s in plain.sources)
    assert math.isclose(shots, 1 - 10 / 45 + 10 / 45 / 0.2, rel_tol=1e-6)


def test_absolute_zero_speeds_up_ice_monkeys():
    """+50% attack speed (rate x0.667) to every Ice Monkey for 10 s of 25."""
    buff, = [b for b in D.profile("ice", (0, 5, 0)).buffs if b.get("ability")]
    assert buff["kind"] == "rate" and math.isclose(buff["value"], 0.6666667, rel_tol=1e-5)
    assert math.isclose(buff["share"], 10 / 25) and buff["towers"] == ["IceMonkey"]
    own, = D.profile("ice", (0, 5, 0)).boosts
    assert math.isclose(own["share"], 0.4)


def test_ball_of_light():
    """Adora level 10: 8 targets x 3 damage every 0.05 s for 12 s in 60;
    level 20: 20 damage for 15 s (fandom:Adora_(BTD6))."""
    ball, = [s for s in D.profile(D.hero_kind("adora"), (10,)).sources if s.ability == "Ball of Light"]
    assert math.isclose(ball.shots, 20 * 12 / 60) and ball.pierce == 8.0 and ball.damage == 3.0
    assert ball.placement == "global"
    late, = [s for s in D.profile(D.hero_kind("adora"), (20,)).sources if s.ability == "Ball of Light"]
    assert math.isclose(late.shots, 20 * 15 / 60) and late.damage == 20.0


def test_abilities_the_bot_never_presses_count_nothing():
    """First Strike (click-targeted), Overclock and Ultraboost (a tower to
    pick) are 'never' in abilities.TOWER_ABILITIES; Blood Sacrifice in
    towers.HEROES."""
    assert not _ability("sub", (0, 4, 0)) and not _ability("sub", (0, 5, 0))
    assert not D.profile("engineer", (0, 4, 0)).boosts and not _ability("engineer", (0, 4, 0))
    assert A.TOWER_ABILITIES["First Strike Capability"][1] == "never"


def test_adora_board_keeps_its_abilities():
    """Adora's Blood Sacrifice (abilities.DESTRUCTIVE_ABILITIES) no longer
    stops every press: the planner holds only the keys it may sit on
    (AbilityPlanner.unsafe_keys), so a tower's ability still counts on her
    board after her level 7, as before it."""
    assert A.presses_blind("adora", 6, 10)
    assert A.presses_blind("adora", 1, 60)
    assert A.presses_blind("quincy", 1, 100)
    from btd6bot.forecast import RoundForecast
    fc = RoundForecast("Monkey Meadow", "chimps", hero="adora")
    assert fc._ready()
    x, z = _beside_track(fc.track)
    fx, fy = fc.track.world_to_frac(x, z)
    tack = SimpleNamespace(tid="t", kind="tack", tiers=(0, 5, 0), x=fx, y=fy, placed_round=6)
    adora = SimpleNamespace(tid="hero", kind="hero", tiers=(0, 0, 0), x=fx + 0.02, y=fy, placed_round=6)
    early = [st for st in fc.stations_in([tack, adora], 10) if st.tid == "t"]
    late = [st for st in fc.stations_in([tack, adora], 80) if st.tid == "t"]
    assert any(s.ability for st in early for s in st.sources + [x for p in st.parts for x in p.sources])
    assert any(s.ability for st in late for s in st.sources + [x for p in st.parts for x in p.sources])


def test_abilities_can_be_switched_off():
    saved = D.ABILITY_RATING
    try:
        D.ABILITY_RATING = False
        D.profile.cache_clear()
        assert not _ability("bomb", (0, 5, 0)) and not D.profile("boomerang", (0, 4, 0)).boosts
    finally:
        D.ABILITY_RATING = saved
        D.profile.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
