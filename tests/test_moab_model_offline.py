"""The damage model and ability fixes for the late MOAB-era board.

Five fixes, each checked offline (no game, no game files; the boards are the
ones the bot logged in its 2026-11-04 Impoppable losses):
  * village Primary Training / Primary Mentoring (3-x-x, 4-x-x) buff only
    Primary towers (the export's "sets" filter);
  * Glaive Lord's orbiting glaives and Master Bomber's sticky bombs are not
    map-wide: a 9,999,999 attack range on an ordinary ground tower is the
    model's "no range check", not a reach over the whole track;
  * CHIMPS is Hard plus the Clicks Mod only (no Impoppable Mod);
  * the heavy rounds come from the round data and include R92, R94, R96;
  * Bloon Sabotage is saved for heavy rounds and pressed at round start.

Run: python tests/test_moab_model_offline.py (also collectable by pytest).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import abilities as A  # noqa: E402
from btd6bot import dps_model as D  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402
from btd6bot.strategy import MODE_RULES  # noqa: E402

# Castle Revenge Impoppable, lost 2026-11-04 18:20: not one Primary tower
# (ninjas, supers, alchemist: Magic; spikes, villages: Support; ace: Military).
CASTLE_REVENGE = [
    ("n1", "ninja", (4, 0, 2), 0.607, 0.283), ("n2", "ninja", (2, 0, 4), 0.393, 0.709),
    ("a1", "alchemist", (4, 2, 0), 0.58, 0.317), ("ninja1", "ninja", (0, 0, 2), 0.163, 0.334),
    ("ninja2", "ninja", (0, 0, 1), 0.142, 0.726), ("v1", "village", (4, 0, 0), 0.596, 0.394),
    ("ninja3", "ninja", (0, 0, 0), 0.131, 0.675), ("ninja4", "ninja", (0, 0, 0), 0.131, 0.368),
    ("ninja5", "ninja", (0, 0, 0), 0.147, 0.624), ("ninja6", "ninja", (0, 0, 0), 0.11, 0.768),
    ("ans_blimps_ace", "ace", (4, 1, 0), 0.468, 0.513), ("n3", "ninja", (0, 0, 2), 0.553, 0.359),
    ("s1", "super", (3, 0, 2), 0.585, 0.615), ("super1", "super", (2, 0, 0), 0.184, 0.342),
    ("super2", "super", (2, 0, 0), 0.2, 0.649), ("sp1", "spike", (2, 0, 4), 0.152, 0.692),
    ("spike1", "spike", (2, 0, 0), 0.136, 0.76), ("v2", "village", (2, 3, 0), 0.505, 0.411),
    ("super3", "super", (2, 0, 2), 0.152, 0.368), ("s2", "super", (2, 0, 2), 0.473, 0.325),
    ("ninja8", "ninja", (0, 0, 0), 0.126, 0.641), ("spike2", "spike", (1, 0, 0), 0.339, 0.717),
    ("super7", "super", (2, 0, 0), 0.398, 0.317), ("spike3", "spike", (0, 0, 0), 0.628, 0.223),
    ("spike4", "spike", (0, 0, 0), 0.35, 0.266), ("spike5", "spike", (1, 0, 0), 0.446, 0.726),
]

# Quiet Street Impoppable, lost 2026-11-04 15:20 at round 98.
QUIET_STREET = [
    ("n1", "ninja", (4, 0, 2), 0.265, 0.359), ("n2", "ninja", (2, 0, 4), 0.751, 0.606),
    ("a1", "alchemist", (4, 2, 0), 0.216, 0.359), ("ninja1", "ninja", (4, 0, 2), 0.307, 0.351),
    ("ninja2", "ninja", (4, 0, 2), 0.302, 0.675), ("ninja3", "ninja", (4, 0, 2), 0.265, 0.675),
    ("v1", "village", (4, 0, 2), 0.334, 0.811), ("ninja4", "ninja", (0, 0, 1), 0.596, 0.888),
    ("ninja5", "ninja", (3, 0, 0), 0.318, 0.726), ("ninja6", "ninja", (0, 0, 2), 0.19, 0.675),
    ("ans_blimps_ace", "ace", (4, 1, 0), 0.318, 0.266), ("ninja7", "ninja", (0, 0, 0), 0.409, 0.871),
    ("n3", "ninja", (2, 0, 2), 0.227, 0.675), ("s1", "super", (3, 0, 2), 0.719, 0.743),
    ("ninja8", "ninja", (0, 0, 0), 0.419, 0.155), ("super2", "super", (2, 0, 0), 0.601, 0.121),
    ("super3", "super", (3, 0, 2), 0.35, 0.172), ("super4", "super", (2, 0, 2), 0.676, 0.836),
    ("super5", "super", (3, 0, 2), 0.767, 0.402), ("super6", "super", (2, 0, 2), 0.772, 0.692),
    ("super7", "super", (3, 0, 2), 0.623, 0.129), ("sp1", "spike", (2, 0, 5), 0.238, 0.3),
    ("v2", "village", (2, 3, 0), 0.74, 0.836), ("spike1", "spike", (1, 0, 2), 0.457, 0.913),
    ("super8", "super", (0, 0, 0), 0.783, 0.308), ("super9", "super", (1, 0, 0), 0.783, 0.274),
    ("a2", "alchemist", (4, 2, 0), 0.794, 0.785), ("ninja10", "ninja", (0, 0, 0), 0.184, 0.342),
    ("ans_blimps_sniper", "sniper", (4, 0, 1), 0.676, 0.913), ("spike2", "spike", (0, 0, 0), 0.761, 0.291),
]


def _board(rows, changes=None, extra=()):
    """Tower records as RoundForecast.stations reads them (screen fractions);
    changes: {tid: new tiers}; extra: more rows to add."""
    changes = changes or {}
    return [SimpleNamespace(tid=t, kind=k, tiers=changes.get(t, tiers), x=x, y=y)
            for t, k, tiers, x, y in list(rows) + list(extra)]


def _margin(forecast, board, rnd):
    return D.round_margin(forecast.stations(board), forecast.mode, rnd, forecast.track)


# ---------------------------------------------------------------------------
# (1) Primary-only village buffs
# ---------------------------------------------------------------------------

def test_primary_training_carries_its_set_filter():
    village = D.crosspath("village", (3, 0, 2))
    primary = [b for b in village["buffs"] if b.get("sets")]
    assert primary and all(b["sets"] == ["primary"] for b in primary)
    assert {b["kind"] for b in primary} >= {"pierce", "range"}
    assert D.tower_set("dart") == "primary" and D.tower_set("ninja") == "magic"


def test_village_primary_buffs_skip_a_board_without_primary_towers():
    fc = RoundForecast("Castle Revenge", "impoppable")
    assert fc._ready()
    # 2-0-2 -> 3-0-2 adds only Primary Training: nothing on this board is Primary
    before = _margin(fc, _board(CASTLE_REVENGE, {"v1": (2, 0, 2)}), 63)
    after = _margin(fc, _board(CASTLE_REVENGE, {"v1": (3, 0, 2)}), 63)
    assert abs(after - before) < 1e-9, (before, after)
    # the 4-0-0 the bot bought there was rated 0.57 -> 0.64 before the fix.
    # Primary Mentoring also widens the village itself (48 -> 55 units), and
    # since buffs reach only towers whose centre is inside the radius
    # (dps_model.buff_covers, Frozen Over 2026-11-05) the super s1, 50 units
    # away, gets Jungle Drums from the 4-0-0 alone: it is left out here.
    board = [row for row in CASTLE_REVENGE if row[0] != "s1"]
    four = _margin(fc, _board(board), 63)
    two = _margin(fc, _board(board, {"v1": (2, 0, 0)}), 63)
    assert abs(four - two) < 1e-9, (two, four)


def test_village_primary_buffs_still_reach_a_dart():
    tr = D.Track("Monkey Meadow")
    dart = D.Placed("d", "dart", (0, 0, 0), 0.0, 0.0)
    base = D.station_for(dart, [dart], tr)
    pierce = {s.name: s.pierce for s in base.sources}
    for tiers, more in (((2, 0, 2), 0.0), ((3, 0, 2), 1.0)):     # Primary Training: +1 pierce
        village = D.Placed("v", "village", tiers, 10.0, 0.0)
        st = D.station_for(dart, [dart, village], tr)
        assert all(abs(s.pierce - pierce[s.name] - more) < 1e-9 for s in st.sources), tiers


# ---------------------------------------------------------------------------
# (2) Glaive Lord and Master Bomber are local
# ---------------------------------------------------------------------------

def test_unbounded_attacks_are_classified():
    assert not D.profile("boomerang", (5, 0, 0)).is_global
    assert D.profile("boomerang", (5, 0, 0)).own_radius == 30.0    # OrbitingGlaive projectile radius
    assert not D.profile("ninja", (0, 0, 5)).is_global
    # still map-wide: snipers (isGlobalRange), an ace's pineapples and a
    # heli's missiles (flying), mortars (aimed at a point)
    for kind, tiers in (("sniper", (0, 0, 0)), ("ace", (0, 1, 0)), ("heli", (0, 0, 3)), ("mortar", (0, 0, 0))):
        assert D.profile(kind, tiers).is_global, kind
    sticky = next(a for a in D.crosspath("ninja", (0, 0, 5))["attacks"] if a["name"] == "StickyBombAttack")
    assert sticky["unbounded"] == "tower"
    assert all(s.placement != "global" for s in D.profile("ninja", (0, 0, 5)).sources)


def test_glaive_lord_covers_its_own_circle_only():
    fc = RoundForecast("Quiet Street", "impoppable")
    assert fc._ready()
    base = _margin(fc, _board(QUIET_STREET), 98)
    glaive = ("probe", "boomerang", (5, 0, 0), 0.295, 0.359)
    lifted = _margin(fc, _board(QUIET_STREET, extra=[glaive]), 98)
    # map-wide, this one Glaive Lord lifted round 98 from 0.18 to 1.63 here
    # (1.84 at the spot the loss report tried); local, it adds a fraction
    assert 0.0 <= lifted - base < 0.5, (base, lifted)
    st = next(s for s in fc.stations(_board([glaive])) if s.tid == "probe")
    covered = sum(z.length for z in st.zones if z)
    assert covered < 0.5 * sum(p["length"] for p in fc.track.paths)


# ---------------------------------------------------------------------------
# (3) CHIMPS mods
# ---------------------------------------------------------------------------

def test_chimps_is_hard_plus_clicks():
    assert D.MODE_MODS["chimps"] == ["Hard", "Clicks"]
    # the Impoppable Mod holds no speed, health or cash rule that CHIMPS would miss
    imp = D.attacks()["modes"]["Impoppable"]
    assert set(imp) <= {"start_round", "end_round", "cost_multipliers"}
    assert D.mode_rules("chimps")["cost_multiplier"] == D.mode_rules("hard")["cost_multiplier"]
    assert D.mode_rules("chimps")["speed"] == D.mode_rules("impoppable")["speed"]
    assert (D.mode_rules("chimps")["start_round"], D.mode_rules("chimps")["end_round"]) == (6, 100)


# ---------------------------------------------------------------------------
# (4) Heavy rounds from the round data
# ---------------------------------------------------------------------------

def test_heavy_rounds_come_from_the_rounds():
    assert {92, 94, 96, 98} <= A.HEAVY_ROUNDS
    assert A.HEAVY_FLOOR <= A.HEAVY_ROUNDS
    assert 91 not in A.HEAVY_ROUNDS and 97 not in A.HEAVY_ROUNDS
    assert {92, 94, 96} <= A.heavy_rounds_for(MODE_RULES["chimps"])
    assert max(A.heavy_rounds_for(MODE_RULES["hard"])) <= 80        # Hard ends at round 80


# ---------------------------------------------------------------------------
# (5) Bloon Sabotage
# ---------------------------------------------------------------------------

def _presses(rnd, seconds=30):
    pl = A.AbilityPlanner(None, MODE_RULES["chimps"])
    ninja = SimpleNamespace(tid="n", kind="ninja", tiers=(0, 4, 0))
    out = []
    for t in range(seconds):
        pl.update_towers([ninja], rnd)
        keys = pl.decide(float(t), rnd, True)
        if keys:
            out.append((t, keys, [r for _, _, r in pl.last_fired]))
    return out


def test_sabotage_is_saved_for_heavy_rounds():
    assert A.TOWER_ABILITIES["Bloon Sabotage"][1] == "moab"
    assert A.tower_abilities("ninja", (0, 4, 0)) == ["Bloon Sabotage"]
    # round 98: pressed on the first tick of the round (ZOMGs spawn in 0-5 s)
    presses = _presses(98)
    assert presses and presses[0][0] == 0 and presses[0][2] == ["heavy round"]
    # a light MOAB-era round: kept for the next heavy one
    assert _presses(97) == []


def test_sabotage_waits_for_the_rounds_blimps():
    """Round 95 (Spring Spring CHIMPS, lost there 2026-11-07/08): 30 s of
    purples and leads, then the fortified MOABs and camo DDTs from 30.8 game
    seconds. The slow is pressed as they come (15 real seconds at 2x), not
    at the round's start - also when the forecast calls the round a crisis;
    round 99's MOABs come at once, and round 99 counts as heavy."""
    assert A.first_blimp_s("standard", 95) == 30.81 and A.first_blimp_s("standard", 99) == 0.0
    assert A.first_blimp_s("standard", 30) is None
    presses = _presses(95)
    assert presses and presses[0][0] == 15 and presses[0][2] == ["heavy round"], presses
    assert 99 in A.HEAVY_ROUNDS
    presses = _presses(99)
    assert presses and presses[0][0] == 0, presses
    pl = A.AbilityPlanner(None, MODE_RULES["chimps"])
    ninja = SimpleNamespace(tid="n", kind="ninja", tiers=(0, 4, 0))
    first = None
    for t in range(30):
        pl.update_towers([ninja], 95)
        if pl.decide(float(t), 95, True, crisis=True) and first is None:
            first = (t, [r for _, _, r in pl.last_fired])
    assert first and first[0] == 15, first
    # a leak still fires it at once
    pl = A.AbilityPlanner(None, MODE_RULES["chimps"])
    pl.update_towers([ninja], 95)
    assert pl.decide(0.0, 95, True, lives_dropped=True)


def _r94_then_r95(ninjas):
    """Presses of round 94 (10 real s = 20 game s in progress) and round 95
    (from 30 real s) with `ninjas` Bloon Sabotage ninjas on the board."""
    pl = A.AbilityPlanner(None, MODE_RULES["chimps"])
    towers = [SimpleNamespace(tid=f"n{i}", kind="ninja", tiers=(0, 4, 0)) for i in range(ninjas)]
    pl.update_towers(towers, 93)
    pl.game_t = 120.0               # bought rounds ago: certainly off cooldown
    out = []
    for t in range(0, 60):
        rnd, in_round = (94, t < 10) if t < 30 else (95, True)
        pl.update_towers(towers, rnd)
        if pl.decide(float(t), rnd, in_round):
            out.append((rnd, t))
    return out


def test_the_slow_is_kept_from_round_94_for_round_95():
    """Rounds 92, 94, 95 and 96 are all heavy by blimp HP, but the slow is
    pressed only in the hand-picked rounds (abilities.is_slow_round): live
    2026-11-08 22:29 Spring Spring CHIMPS pressed it twice in round 94 and
    met round 95's MOABs and DDTs without it. Now round 94 passes without a
    press and round 95's blimps get it as they come (45 s here), with one
    ninja or two."""
    assert 94 in A.HEAVY_ROUNDS and not A.is_slow_round(94, MODE_RULES["chimps"])
    assert A.is_slow_round(95, MODE_RULES["chimps"]) and A.is_slow_round(99, MODE_RULES["chimps"])
    assert _r94_then_r95(1) == [(95, 45)]
    assert _r94_then_r95(2) == [(95, 45)]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
