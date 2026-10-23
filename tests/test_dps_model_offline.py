"""The attack export (data/game_model/attacks.json, tools/export_attacks.py)
and the damage model built on it (btd6bot/dps_model.py).

Four groups of checks, all offline (no game, no game files):
  * the export against numbers every BTD6 player knows (a Dart Monkey does
    1 damage with pierce 2 every 0.95 s, a Super Monkey fires every 0.045 s,
    ...) and against the capability flags towers.json got from the same
    decoded model (camo detection must agree crosspath for crosspath);
  * the mode rules read from the game's Mod assets (Hard bloons are 1.25x
    as fast, Double HP MOABs have twice the health, ...);
  * map routes from the map geometry (MOAB-only lanes, alternating spawns);
  * the round simulation's basic promises: more or stronger towers never
    leak more, a bloon nobody can pop always leaks, and so on.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import dps_model as D  # noqa: E402

ATTACKS = ROOT / "data" / "game_model" / "attacks.json"
TOWERS = ROOT / "data" / "game_model" / "towers.json"


def _headline(kind, code="000"):
    from export_attacks import headline
    return headline(D.attacks()["towers"][kind]["crosspaths"][code])


# ---------------------------------------------------------------------------
# The export against well-known numbers
# ---------------------------------------------------------------------------

def test_export_covers_every_crosspath():
    data = json.loads(ATTACKS.read_text(encoding="utf-8"))
    towers = json.loads(TOWERS.read_text(encoding="utf-8"))
    for kind, entry in towers.items():
        assert set(entry["crosspaths"]) <= set(data["towers"][kind]["crosspaths"]), kind
    assert data["source"]["crosspaths"] > 1600
    assert data["frames_per_second"] == 60          # derived from burst weapons (6 frames = 0.1 s)


def test_base_towers_match_known_numbers():
    dart = _headline("dart")
    assert (dart["damage"], dart["pierce"], dart["rate"], dart["range"]) == (1.0, 2.0, 0.95, 32.0)
    assert dart["type"] == "sharp" and not dart["camo"]
    ninja = _headline("ninja")
    assert (ninja["damage"], ninja["pierce"]) == (1.0, 2.0) and ninja["camo"]
    assert 0.55 <= ninja["rate"] <= 0.75            # 0.62 in this game version (~0.7 in older ones)
    assert _headline("super")["rate"] == 0.045
    sniper = _headline("sniper")
    assert (sniper["damage"], sniper["rate"]) == (2.0, 1.59) and sniper["range"] > 1000
    assert _headline("tack")["count"] == 8.0        # eight tacks all around
    assert _headline("boomerang")["pierce"] == 4.0
    assert _headline("bomb")["type"] == "explosion"  # the explosion, not the bomb in flight
    assert _headline("spike")["pierce"] == 5.0
    farm = D.attacks()["towers"]["farm"]["crosspaths"]["000"]
    assert farm["income"]["bananas_per_round"] == 80.0   # 4 bananas of $20


def test_triggered_weapons_fire_at_their_trigger_rate():
    # The buccaneer's Grape Shot / Cannon secondaries are fired by their
    # primaries; their own 0.05 s rate was once counted (100 shots/s).
    if not D.available():
        return
    for tiers in ((0, 1, 0), (0, 4, 2)):
        assert max(s.shots for s in D.profile("buccaneer", tiers).sources) < 30, tiers
    grape = [s.shots for s in D.profile("buccaneer", (0, 1, 0)).sources]
    assert grape.count(grape[-1]) >= 2      # secondary = primary's rate (3.7/s)


def test_upgrades_change_the_numbers():
    assert _headline("dart", "200")["pierce"] == 5.0      # Sharp Shots +1, Razor Sharp Shots +2
    assert _headline("dart", "003")["damage"] == 3.0      # Crossbow
    assert _headline("sniper", "100")["damage"] == 4.0    # Full Metal Jacket
    assert _headline("sniper", "100")["type"] != "sharp"  # ... and it pops lead
    assert _headline("sniper", "400")["damage"] == 30.0   # Maim MOAB
    assert _headline("super", "200")["rate"] == 0.03      # Plasma Blasts


def test_camo_agrees_with_capability_flags():
    """Camo detection worked out from the attack tree must agree with the
    'camo' capability word towers.json has for every crosspath."""
    towers = json.loads(TOWERS.read_text(encoding="utf-8"))

    def sees_camo(p, attack_camo):
        if not p:
            return False
        if attack_camo and p.get("camo") and (p.get("damage") or p.get("dot")) and not p.get("hits_nothing"):
            return True
        return any(sees_camo(s.get("projectile"), attack_camo and p.get("camo", False))
                   for s in p.get("spawn", [])) or any(
            sees_camo(w.get("projectile"), a.get("camo", False))
            for t in p.get("subtowers", []) for a in t.get("attacks", []) for w in a.get("weapons", []))

    bad = []
    for kind, entry in D.attacks()["towers"].items():
        for code, cp in entry["crosspaths"].items():
            words = set(towers[kind]["crosspaths"].get(code, []))
            camo = any(sees_camo(w.get("projectile"), a.get("camo", False)) or
                       (w.get("alternate") and sees_camo(w["alternate"]["projectile"], a.get("camo", False)))
                       for a in cp.get("attacks", []) for w in a.get("weapons", []))
            if camo != ("camo" in words):
                bad.append(f"{kind} {code}")
    assert not bad, bad


def test_lead_agrees_with_capability_flags():
    """Lead popping from the attack tree vs the decoder's 'lead' word: the
    same except towers whose lead damage comes from parts the export does
    not interpret (Beast Handler pets, Skywarden specials)."""
    towers = json.loads(TOWERS.read_text(encoding="utf-8"))

    def immunities(p, out):
        if not p:
            return
        if (p.get("damage") or p.get("dot")) and not p.get("hits_nothing"):
            im = set((p.get("damage") or p["dot"]).get("immune", []))
            if p.get("damage") and p.get("dot"):
                im &= set(p["dot"].get("immune", []))
            out.append(im)
        for s in p.get("spawn", []):
            immunities(s.get("projectile"), out)
        for t in p.get("subtowers", []):
            for a in t.get("attacks", []):
                for w in a.get("weapons", []):
                    immunities(w.get("projectile"), out)

    bad = []
    for kind, entry in D.attacks()["towers"].items():
        if kind in ("beast_handler", "skywarden"):
            continue
        for code, cp in entry["crosspaths"].items():
            found = []
            for a in cp.get("attacks", []):
                for w in a.get("weapons", []):
                    for p in (w.get("projectile"), (w.get("alternate") or {}).get("projectile"),
                              w.get("extra_projectile")):
                        immunities(p, found)
            if any("lead" not in im for im in found) != ("lead" in towers[kind]["crosspaths"].get(code, [])):
                bad.append(f"{kind} {code}")
    assert not bad, bad


def test_profiles():
    dart = D.profile("dart", (0, 0, 0))
    (src,) = dart.sources
    assert math.isclose(src.shots, 1 / 0.95) and src.pierce == 2 and src.immune == {"lead"}
    assert D.profile("sniper", (0, 0, 0)).is_global
    assert D.profile("mortar", (0, 0, 0)).aim_bound          # needs a hand-aimed target
    assert D.profile("spike", (0, 0, 0)).sources[0].placement == "track"
    glue = D.profile("glue", (2, 0, 0))                       # Corrosive Glue: damage over time only
    assert glue.sources and glue.sources[0].dot_total > 0
    assert D.profile("dart", (3, 3, 3)) is None               # the game has no such crosspath
    # a Buccaneer's second dart fires with the first (FireAlternateWeaponModel), not every 0.05 s
    assert all(s.shots <= 1.0 + 1e-9 for s in D.profile("buccaneer", (0, 0, 0)).sources)


# ---------------------------------------------------------------------------
# Modes and bloons
# ---------------------------------------------------------------------------

def test_mode_rules_from_the_game():
    assert D.mode_rules("easy")["speed"] == 1.0
    assert D.mode_rules("medium")["speed"] == 1.1
    assert D.mode_rules("hard")["speed"] == 1.25
    assert D.mode_rules("chimps")["speed"] == 1.25         # CHIMPS is played on Hard
    assert D.mode_rules("double_hp")["moab_hp"] == 2.0
    assert D.mode_rules("deflation")["cash"] == 0.0 and D.mode_rules("deflation")["start_cash"] == 20000
    assert D.mode_rules("half_cash")["cash"] == 0.5
    assert any(r == 40 and b == "Moab" for r, b, _ in D.mode_rules("easy")["round_health"])


def test_bloon_layers():
    assert D.rbe("Ceramic") == 104 and D.rbe("Moab") == 616 and D.rbe("Zomg") == 16656
    assert D.layer("Lead").immune == {"lead"} and "Moabs" in D.layer("Bfb").tags
    assert D.layer("Moab", 2.0).hp == 400.0                # Double HP MOABs
    assert D.layer("Ceramic").leak == 104                  # leaking costs the whole bloon


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_routes_follow_the_maps_splitters():
    meadow = D.Track("Monkey Meadow")
    assert len(meadow.paths) == 1 and meadow.scenarios == [[0]]
    quiet = D.Track("Quiet Street")                        # MOABs take their own lane
    assert {p["moab"] for p in quiet.paths} == {True, False}
    assert all(quiet.paths[i]["moab"] for i in quiet.routes_for(0, True))
    cove = D.Track("Luminous Cove")                        # spawns alternate by round
    assert len(cove.scenarios) == 2 and all(len(s) == 1 for s in cove.scenarios)
    pond = D.Track("Pat's Pond")                           # two lanes from opposite ends
    assert len(pond.paths) == 2 and len(pond.scenarios) == 1


def test_screen_world_round_trip():
    tr = D.Track("Monkey Meadow")
    for fx, fy in ((0.2, 0.3), (0.5, 0.5), (0.7, 0.8)):
        x, z, h = tr.frac_to_world(fx, fy)
        back = tr.world_to_frac(x, z, h)
        assert abs(back[0] - fx) < 1e-6 and abs(back[1] - fy) < 1e-6


# ---------------------------------------------------------------------------
# The round simulation
# ---------------------------------------------------------------------------

def _best_spot(track, radius):
    """A world position next to the track covering a lot of it (brute force)."""
    best = None
    for x in range(-160, 161, 8):
        for z in range(-100, 101, 8):
            zones = track.zones(x, z, radius)
            covered = sum(zz.length for zz in zones if zz)
            if best is None or covered > best[0]:
                best = (covered, x, z)
    return best[1], best[2]


def test_simulation_basic_promises():
    tr = D.Track("Monkey Meadow")
    x, z = _best_spot(tr, 32)
    one = [D.Placed("d1", "dart", (0, 0, 0), x, z)]
    two = one + [D.Placed("d2", "dart", (0, 0, 0), x + 10, z + 10)]
    st1, st2 = D.stations_for(one, tr), D.stations_for(two, tr)
    for rnd in (1, 5, 10):
        a = D.simulate_round(st1, "easy", rnd, tr)
        b = D.simulate_round(st2, "easy", rnd, tr)
        assert b.lives_lost <= a.lives_lost + 1e-6                     # more towers, never more leaks
        weak = D.simulate_round(st1, "easy", rnd, tr, strength=0.5)
        assert weak.lives_lost >= a.lives_lost - 1e-6                  # weaker towers, never fewer
    assert D.simulate_round(st1, "easy", 1, tr).safe                   # 20 reds vs a dart
    empty = D.simulate_round([], "easy", 1, tr)
    assert math.isclose(empty.lives_lost, 20) and not empty.safe       # nothing there: all 20 leak
    m1 = D.round_margin(st1, "easy", 3, tr)
    m2 = D.round_margin(st2, "easy", 3, tr)
    assert m2 >= m1 > 0


def test_unpoppable_bloons_always_leak():
    tr = D.Track("Monkey Meadow")
    x, z = _best_spot(tr, 40)
    ninjas = D.stations_for([D.Placed("n", "ninja", (0, 0, 0), x, z)], tr)   # sharp: cannot pop lead
    lead_round = next(r for r in range(20, 40)
                      if any(g["bloon"] == "lead" for g in D._round_groups("standard", r)))
    res = D.simulate_round(ninjas, "medium", lead_round, tr, strength=16.0)
    assert "Lead" in res.leaked and not res.safe
    assert D.round_margin(ninjas, "medium", lead_round, tr) <= 1 / 16 + 1e-9


def test_camo_needs_detection():
    tr = D.Track("Monkey Meadow")
    x, z = _best_spot(tr, 32)
    camo_round = next(r for r in range(20, 40)
                      if any(g.get("camo") for g in D._round_groups("standard", r)))
    darts = D.stations_for([D.Placed("d", "dart", (0, 0, 0), x, z)], tr)
    res = D.simulate_round(darts, "medium", camo_round, tr, strength=16.0)
    assert any("Camo" in b for b in res.leaked)
    ninjas = D.stations_for([D.Placed("n", "ninja", (0, 0, 0), x, z)], tr)
    res = D.simulate_round(ninjas, "medium", camo_round, tr, strength=16.0)
    assert not any("Camo" in b for b in res.leaked)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
