"""CHIMPS guide builds for the Intermediate maps (2026-11-12).

Every Beginner CHIMPS map was won by a build that follows a published guide
step by step with exact spots and `plan_first`. docs/chimps_map_guides.md
picked the best-sourced no-ability guide for each Intermediate map without
a CHIMPS medal; strategies/maps/<map>_chimps.yaml follows it (on the five
maps whose own generic Flagship builds lost many times,
<map>_chimps_guide.yaml, and the old build is parked). tools/pin_spots.py
pinned every tower on a cell of the live learned map the game never
refused, inside the area the guide names in words.

Checked here, for each build:
  * it is a plan_first CHIMPS build for its one map, marked UNTESTED at the
    map builds' lowest base_success, and its header names the guide, the
    source URL, the hero and the core towers;
  * every tower of the plan and the fill has a spot, legal on the map's
    geometry in plan order and never refused in the live learned map;
  * no upgrade asks for a tier the account cannot buy (the locked tiers of
    docs/chimps_map_guides.md) or an income tier CHIMPS skips;
  * the threat simulation on the learned map (tools/simulate_threats.py,
    CHIMPS cash: $650 at round 6, then only the rounds' own income) finds
    no threat gap through round 100 and buys the whole plan;
  * the plan is affordable by round 100 on the CHIMPS cash curve
    (tests/test_chimps_builds_offline.plan_timeline);
  * on the maps with an older, lost CHIMPS build, the guide build rates
    above it in the planner, so a NEXT line without a strategy picks it;
  * the opening (the purchases by round 10) meets tools/opening_rule: a
    live-proven opening, the guide's own one, or one the corrected model
    rates as holding every round 6-10 on every lane. On 2026-11-13 six of
    these builds lost rounds 7-20 on openings an opening search had chosen
    by model ratings the game did not honour (cases 20261113_032115 Bazaar,
    _032621 Lost Crevasse, _033512 Rake, _041444 Water Park, _041946 Moon
    Landing, _042420 Sulfur Springs). Builds that do not meet it yet are in
    OPENING_KNOWN with what they need; the test fails when another build
    fails, or a listed one passes (then drop it from the list).

Not covered: Encrypted and Chutes have no written guide (the doc found
only videos and wiki notes), so no build is written for them.

Run: python tests/test_chimps_intermediate_guides_offline.py (no game)."""
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import pin_spots  # noqa: E402
import simulate_threats as SIM  # noqa: E402
import test_chimps_builds_offline as TC  # noqa: E402
import test_map_hints_offline as TM  # noqa: E402
from btd6bot import maplearn as ML  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)

# build id -> map
BUILDS = {
    "lostcrevasse_chimps_guide": "Lost Crevasse",
    "sulfursprings_chimps_guide": "Sulfur Springs",
    "springspring_chimps_guide": "Spring Spring",
    "moonlanding_chimps_guide": "Moon Landing",
    "rake_chimps_guide": "Rake",
    "luminouscove_chimps": "Luminous Cove",
    "ancientportal_chimps": "Ancient Portal",
    "haunted_chimps": "Haunted",
    "firingrange_chimps": "Firing Range",
    "waterpark_chimps": "Water Park",
    "coveredgarden_chimps": "Covered Garden",
    "bloonariusprime_chimps": "Bloonarius Prime",
    "bazaar_chimps": "Bazaar",
    "polyphemus_chimps": "Polyphemus",
    "quietstreet_chimps": "Quiet Street",
    "balance_chimps": "Balance",
}
# the generic builds these guide builds replace (lost many times live)
PARKED = {"lostcrevasse_chimps": "lostcrevasse_chimps_guide",
          "sulfursprings_chimps": "sulfursprings_chimps_guide",
          "springspring_chimps": "springspring_chimps_guide",
          "moonlanding_chimps": "moonlanding_chimps_guide",
          "rake_chimps": "rake_chimps_guide"}
# builds whose opening does not meet tools/opening_rule yet, with what it
# needs (the openings of other sessions' builds; test_every_opening_meets_the_opening_rule)
OPENING_KNOWN = {
    "springspring_chimps_guide": "the search's tack before the guide's Etienne; the guide's sub + mermonkey "
                                 "held to round 37 (journal 20261112_154428) with the mermonkey at 0.804, 0.572",
    "luminouscove_chimps": "the guide's dart + boat lost round 8 twice (rated 2.48, backlog 107): needs a "
                           "proven opening or 107 fixed",
    "bloonariusprime_chimps": "the search's druid and glue before the guide's second dart, sub and third dart",
    "quietstreet_chimps": "the search's second dart before the guide's snipers",
    "balance_chimps": "the search's druid, dart and tack before the guide's Sauda",
    "waterpark_chimps": "nothing meets it yet: the guide's dart + boomerang lost twice, no opening is proven, "
                        "and no affordable one rates over 0.64 corrected; the guide's two towers and a desperado "
                        "during round 7 play until an opening is proven live",
}
# tiers the main account cannot buy (docs/chimps_map_guides.md, "Account
# constraints"): [top, middle, bottom] caps; every other tower is 5-5-5
CAPS = {"mortar": (5, 5, 0), "village": (4, 5, 5), "mermonkey": (4, 4, 4),
        "dartling": (5, 4, 5), "super": (5, 5, 3), "skywarden": (4, 3, 3)}


def _load(sid):
    path = ROOT / "strategies" / "maps" / f"{sid}.yaml"
    return path.read_text(encoding="utf-8"), yaml.safe_load(path.read_text(encoding="utf-8"))


def _capped_account():
    """A fully unlocked account with the main account's tier caps."""
    acct = SIM.full_account()
    for kind, cap in CAPS.items():
        acct.unlocked_upgrades[kind] = list(cap)
    return acct


def test_each_build_is_an_untested_plan_first_guide_build():
    for sid, name in BUILDS.items():
        text, d = _load(sid)
        assert d["id"] == sid and d["map"] == name and d["modes"] == ["chimps"], sid
        assert d["plan_first"] is True, sid
        assert d["planner"]["base_success"] == {"chimps": pin_spots.UNTESTED_SUCCESS}, sid
        assert d["planner"]["maps"] == [name], sid
        for word in ("UNTESTED", "Guide:", "https://", "Hero:", "Core towers:", "Adapted"):
            assert word in text, (sid, word)
        assert any(st["do"] == "place" and st["kind"] == "hero" for st in d["plan"]), (sid, "no hero")


def _accepted_live(model, spot):
    """Has the live game accepted a tower of this spot's surface on its cell
    although the map file marks it blocked (MapModel.accepted_mask)? Never
    for the hero, whose refusals are learned on their own layer."""
    kind, hero, at = spot
    if hero or kind == "clear":
        return False
    cx, cy = model.frac_to_cell(*at)
    return any(model.accepted_mask(surface)[cy, cx] for surface in pin_spots.PL.surfaces(kind))


def test_every_tower_is_pinned_legal_and_never_refused():
    ML.DATA = pin_spots.live_maps_dir()
    for sid, name in BUILDS.items():
        _, d = _load(sid)
        steps = d["plan"] + (d.get("fill") or [])
        spots = []
        for st in steps:
            if st["do"] == "clear":
                spots.append(("clear", st.get("obstacle"), None))
            if st["do"] != "place" or st.get("role") == "exit":
                continue
            assert st.get("at"), (sid, st.get("id"), "no spot")
            hero = d["hero"] if st["kind"] == "hero" else None
            spots.append((st["kind"], hero, tuple(st["at"])))
        model = pin_spots.Pinner(name, "chimps").model     # the live learned map
        # The map file marks some ground blocked that the game takes: Bazaar's
        # middle strip between the canals held a sniper in four games. A cell
        # the game has accepted for the tower's surface is legal ground.
        illegal = [spot for spot in TM.illegal_spots(name, spots, 100) if not _accepted_live(model, spot)]
        assert not illegal, (sid, illegal)
        for kind, hero, at in spots:
            if kind == "clear":
                continue
            cell = model.frac_to_cell(*at)
            assert pin_spots.never_refused(model, kind, cell, hero), (sid, kind, at)


# pinned damage towers under the executor's reach floor in builds other
# sessions are reworking (test_every_pinned_damage_tower_reaches_the_track):
# build id -> {tower id: why it is left}
REACH_KNOWN = {
    "waterpark_chimps": {"r2": "50 of 84 cells (0.804, 0.215); the build is the caretaker's, reworked "
                               "round by round since 2026-11-12"},
}


def _pinned_reach_misses(d):
    """{tower id: (reach, floor)} of the build's pinned damage towers whose
    spot reaches less track than the live executor asks of it
    (Executor._at_in_reach: SELL_REACH_SHARE of the best legal cell's reach,
    on the live learned map with an empty board). Such a spot is passed over
    live and the tower stands wherever the executor's search puts it."""
    model = SIM.map_model(d["map"], learned=True)
    game = SIM.CashGame("hard", d.get("hero"), model)
    game.cash, game.round = 650, 6
    ex = S.Executor(game, model, d, "chimps", SIM.full_account())
    out = {}
    for st in d["plan"] + (d.get("fill") or []):
        kind = st.get("kind")
        if st["do"] != "place" or not st.get("at") or st.get("role") == "exit" \
                or kind in S.Executor.BUFFERS or kind in ("farm", "spike", "hero"):
            continue
        valid = ex._legal_cells(kind)
        floor = ex._reach_floor(kind, valid, ex.SELL_REACH_SHARE)
        reach = ex._reach(kind)
        if floor is None or reach is None:
            continue
        cx, cy = model.frac_to_cell(*st["at"])
        if reach[cy, cx] < floor:
            out[st["id"]] = (round(float(reach[cy, cx])), round(floor))
    return out


def test_every_pinned_damage_tower_reaches_the_track():
    """No build pins a damage tower where the live executor's reach check
    passes it over (Executor._at_in_reach). Sulfur Springs CHIMPS (case
    20261113_085155, lost round 63): the hardening's coordinate search put
    the wizard at (0.334, 0.112), 16 track cells under a floor of 37, the
    Glaive Ricochet boomerang at (0.152, 0.521), 1 cell under 42, and the
    glue at (0.206, 0.146), none under 128 - the damage model, which moves a
    tower on the map's 51-high ground 28 units down the screen, rated those
    spots high. Live the bot stood the wizard and the boomerang wherever its
    own search found track, Obyn stayed beside the empty pin, and the plan's
    ratings described a board that was never built."""
    ML.DATA = pin_spots.live_maps_dir()
    SIM._MAP_MODELS.clear()
    bad = {}
    for sid in BUILDS:
        _, d = _load(sid)
        miss = {tid: v for tid, v in _pinned_reach_misses(d).items() if tid not in REACH_KNOWN.get(sid, {})}
        if miss:
            bad[sid] = miss
    assert not bad, bad
    fixed = [(sid, tid) for sid, known in REACH_KNOWN.items() for tid in known
             if tid not in _pinned_reach_misses(_load(sid)[1])]
    assert not fixed, f"reach the track now, drop from REACH_KNOWN: {fixed}"


def test_no_locked_or_income_tier():
    for sid in BUILDS:
        _, d = _load(sid)
        kinds = {st["id"]: st["kind"] for st in d["plan"] + (d.get("fill") or []) if st["do"] == "place"}
        for st in d["plan"] + (d.get("fill") or []):
            if st["do"] != "upgrade":
                continue
            kind = kinds[st["id"]]
            tiers = S.parse_cross(st["to"])
            cap = CAPS.get(kind, (5, 5, 5))
            assert all(t <= c for t, c in zip(tiers, cap)), (sid, st)
            # CHIMPS skips a plan step that ends on an income tier
            # (Executor._step_allowed): 0-4-x snipers, 1-4-0 druids
            assert not any((kind, p, tiers[p - 1]) in S.INCOME_UPGRADES for p in (1, 2, 3)), (sid, st)


def test_threat_simulation_has_no_gaps_and_buys_the_plan():
    ML.DATA = pin_spots.live_maps_dir()
    acct = _capped_account()
    for sid in BUILDS:
        _, d = _load(sid)
        r = SIM.simulate(dict(d, bot_ready=True), "chimps", d["map"], real_map=True, learned=True,
                         account=acct)
        assert not r["gaps"], (sid, r["gaps"][:3])
        done, total = (int(x) for x in r["plan_done"].split("/"))
        assert done == total, (sid, r["plan_done"])


def test_plan_is_affordable_by_round_100():
    for sid in BUILDS:
        _, d = _load(sid)
        timeline = TC.plan_timeline(d, "chimps")
        assert timeline[-1][2] <= 100, (sid, timeline[-1][1], timeline[-1][2])


def test_guide_builds_rank_above_the_parked_builds():
    from btd6bot import planner as P
    from btd6bot.account import AccountState
    from btd6bot.runner import planner_specs
    strats = S.load_all()
    specs = {s.id: s for s in planner_specs({k: strats[k] for k in list(PARKED) + list(PARKED.values())},
                                            _account_for_planner(AccountState))}
    for old, new in PARKED.items():
        assert strats[old]["planner"]["base_success"]["chimps"] <= TM.PARKED_SUCCESS, old
        name = strats[new]["map"]
        acct = _account_for_planner(AccountState)
        p_old = P.win_probability(acct, specs[old], name, "chimps")[0]
        p_new = P.win_probability(acct, specs[new], name, "chimps")[0]
        assert p_new > p_old, (new, p_new, old, p_old)


def test_every_opening_meets_the_opening_rule():
    import opening_rule as OR
    bad = {}
    for sid in BUILDS:
        _, d = _load(sid)
        src, why = OR.opening_source(d)
        if src is None:
            bad[sid] = why
    unexpected = {sid: why for sid, why in bad.items() if sid not in OPENING_KNOWN}
    assert not unexpected, unexpected
    fixed = [sid for sid in OPENING_KNOWN if sid not in bad]
    assert not fixed, f"meets the rule now, drop from OPENING_KNOWN: {fixed}"


def test_the_lost_openings_fail_the_opening_rule():
    """The openings of the 2026-11-13 losses, as their builds stood
    (git 573af1b), do not meet tools/opening_rule."""
    import opening_rule as OR
    lost = {
        "bazaar_chimps": ["x1", "x2", "x3", "gl1", "d1"],             # round 9
        "lostcrevasse_chimps_guide": ["d1", "t1", "hero"],            # round 7
        "sulfursprings_chimps_guide": ["w1", "s1", "b1"],             # round 8
        "moonlanding_chimps_guide": ["x1", "s1", "x1:0-1-0", "gl1"],  # round 8
        "rake_chimps_guide": ["e1", "e2", "ta1", "gl1", "da1"],       # round 20
        "waterpark_chimps": ["r1", "x1", "r1:0-0-1"],                 # round 7
    }
    for sid, order in lost.items():
        _, d = _load(sid)
        places = {st["id"]: st for st in d["plan"] if st["do"] == "place"}
        steps = []
        for item in order:
            tid, _, to = item.partition(":")
            steps.append({"do": "upgrade", "id": tid, "to": to} if to else places[tid])
        src, why = OR.opening_source(dict(d, plan=steps))
        assert src is None, (sid, src, why)


def _account_for_planner(cls):
    """A fresh account that owns every tower and hero, with the main
    account's tier caps (no games, no medals)."""
    acct = cls()
    full = _capped_account()
    acct.unlocked_towers = set(full.unlocked_towers)
    acct.unlocked_heroes = set(full.unlocked_heroes)
    acct.unlocked_upgrades = dict(full.unlocked_upgrades)
    return acct


if __name__ == "__main__":
    import inspect
    fails = 0
    for fname, fn in list(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", fname)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", fname, repr(e)[:600])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
