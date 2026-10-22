"""Offline tests for the generated solo XP builds: strategies/generated/solo_<tower>.yaml,
written by tools/gen_builds.py (see docs/builds.md).

Every tower must have a build; every build must load bot-ready, be usable and
covered on a fully unlocked account in each mode it lists, pass the offline
threat simulation there (tools/simulate_threats.py, real prices and income),
put most of its plan's cash into its tower, and still be what the generator
makes from the current game data (otherwise: run python tools/gen_builds.py).

Run: python tests/test_generated_builds_offline.py (also collectable by pytest).
Never touches the game, mouse or keyboard."""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import strategy as S  # noqa: E402
from btd6bot import towers as T  # noqa: E402

import gen_builds as G  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)
for _name in ("strategy", "threats", "planner", "mapfit"):
    logging.getLogger(_name).setLevel(logging.ERROR)

GEN_DIR = S.STRAT_DIR / "generated"


def generated():
    """{tower kind: strategy} of the generated builds, as load_all reads them."""
    return {s["xp_target"]: s for s in S.load_all().values() if s.get("source") == "generated"}


def test_every_tower_has_a_build():
    builds = generated()
    for kind in T.TOWERS:
        assert (GEN_DIR / f"solo_{kind}.yaml").is_file(), f"no build file for {kind}"
        assert kind in builds, f"solo_{kind}.yaml is not loaded"
        assert builds[kind]["id"] == f"solo_{kind}"
    assert set(builds) == set(T.TOWERS), set(builds) ^ set(T.TOWERS)
    assert "hero" not in builds


def test_builds_load_bot_ready_and_valid():
    for kind, s in generated().items():
        assert s["bot_ready"] is True, (kind, s.get("bot_ready_reasons"))
        assert S.validate(s) == [], (kind, S.validate(s))
        assert S.readiness(s) == [], (kind, S.readiness(s))
        for mode in s["modes"]:
            assert mode in S.MODE_RULES, (kind, mode)
        assert set(s["planner"]["base_success"]) == set(s["modes"]), kind


def test_usable_and_covered_in_every_listed_mode():
    acct = G.SIM.full_account()
    for kind, s in generated().items():
        for mode in s["modes"]:
            ok, why = S.usable(s, mode, acct)
            assert ok, (kind, mode, why)
            # covered with only the towers that mode allows (category-only modes)
            ok, missing = S.coverage(G.for_mode(s, mode), mode, acct)
            assert ok, (kind, mode, missing)


def test_category_modes_only_where_the_category_fits():
    for kind, s in generated().items():
        for mode in s["modes"]:
            cat = S.MODE_TOWER_FILTER.get(mode)
            if cat is None:
                continue
            assert T.TOWERS[kind]["category"] == cat, (kind, mode)
            for k in s["planner"]["towers"]:
                assert T.TOWERS[k]["category"] == cat, (kind, mode, k)
            # a category-only mode needs its difficulty's standard mode too
            assert S.MODE_FAMILY[mode] in s["modes"], (kind, mode)


def test_simulation_passes_every_listed_mode():
    """The same verdict the generator gave, on the files as they are: no
    bloon nobody can pop, enough blimp damage (Hard: the build's own), and
    the tower keeps at least MIN_SHARE of the cash."""
    for kind, s in generated().items():
        b = SimpleNamespace(kind=kind)
        defence = G.defence_only_strategy(b, s) if G.needs_aim(kind) else None
        for mode in s["modes"]:
            v = G.judge(b, s, mode, defence)
            assert v.ok, (kind, mode, v.why)


def test_files_match_the_generator():
    """A file that no longer matches what the generator makes from the
    current game data must be regenerated (python tools/gen_builds.py).
    The water map list is left out: it follows data/map_fit.json, which
    mapfit refreshes on its own (test_water_builds_only_where_they_reach)."""
    for kind, s in generated().items():
        want = G._assemble(kind, s["modes"]).strategy(s["modes"], s["planner"]["base_success"])
        for key in ("plan", "fill", "panic", "answers", "hero"):
            assert s.get(key) == want.get(key), (kind, key)
        assert s["planner"]["towers"] == want["planner"]["towers"], kind
        assert ("maps" in s["planner"]) == ("maps" in want["planner"]), kind
        assert bool(s.get("uses_income")) == bool(want.get("uses_income")), kind


def test_the_tower_gets_most_of_the_plan():
    """XP is split by invested cash: the plan's cash (what the planner reads
    as the game's XP split) goes mainly into the tower being levelled."""
    for kind, s in generated().items():
        share = G.plan_share(s, kind)
        least = 0.85 if G.is_carry(kind) else 0.5
        assert share >= least, (kind, round(share, 2))
        assert max(S.invested_cash(s), key=S.invested_cash(s).get) == kind, kind


def test_water_builds_only_where_they_reach():
    """Sub and Buccaneer builds list their water maps (chosen from
    data/map_fit.json when generated: at least the planner's FULL_FIT of the
    track in reach); each must still be a real map where the tower reaches
    the track at all. The planner scales the rest by the live map fit."""
    from btd6bot import mapfit
    from btd6bot.account import canonical_map
    table = mapfit.load()
    for kind, s in generated().items():
        where = G.placement(kind)
        maps = s["planner"].get("maps")
        if where != "water":
            assert maps is None, (kind, "a land/amphibious tower plays every map")
            continue
        assert maps, f"{kind}: a water tower needs its water maps"
        for m in maps:
            assert canonical_map(m) == m, (kind, m)
            fit = (table.get(m) or {}).get("towers", {}).get(kind)
            if fit is not None:
                assert max(fit["early"], fit["late"]) > 0, (kind, m, fit)


def test_base_success_is_conservative():
    for kind, s in generated().items():
        for mode, p in s["planner"]["base_success"].items():
            fam = G.mode_family(mode)
            assert G.BASE_FLOOR <= p <= G.BASE_CEILING.get(fam, G.BASE_CEILING["hard"]), (kind, mode, p)
            # below every hand-written strategy of the same difficulty family
            hand = [h["planner"]["base_success"][mode] for h in S.load_all().values()
                    if not h.get("source") and not h.get("achievement")
                    and mode in ((h.get("planner") or {}).get("base_success") or {})]
            if hand:
                assert p <= max(hand), (kind, mode, p, max(hand))


def test_one_tier5_per_path():
    """The game allows one tier 5 per upgrade: no two towers of a build are
    ever taken to tier 5 on the same path of the same tower kind."""
    for kind, s in generated().items():
        ids = {st["id"]: st["kind"] for _, st in S._all_steps(s) if st.get("do") == "place" and st.get("id")}
        fives = {}
        for _, st in S._all_steps(s):
            if st.get("do") != "upgrade":
                continue
            tiers = S.parse_cross(st["to"])
            k = st.get("kind") or ids.get(st.get("id"))
            for path, t in enumerate(tiers):
                if t == 5:
                    assert st.get("id"), (kind, "a tier 5 by kind would take every copy there", st)
                    fives.setdefault((k, path), set()).add(st["id"])
        for (k, path), who in fives.items():
            assert len(who) == 1, (kind, k, path + 1, who)


def test_heli_buys_pursuit_first():
    """Heli Pilots follow the mouse until Pursuit (2-x-x): every heli's first
    upgrade step in the plan already includes it (gen_builds.CURSOR_FIX)."""
    s = generated()["heli"]
    path, tier = G.CURSOR_FIX["heli"]
    first = {}
    for st in s["plan"]:
        if st.get("do") == "upgrade" and st.get("id") in {p["id"] for p in s["plan"]
                                                         if p.get("kind") == "heli"}:
            first.setdefault(st["id"], S.parse_cross(st["to"]))
    assert first
    for tid, tiers in first.items():
        assert tiers[path - 1] >= tier, (tid, tiers)


def test_loader_skips_broken_generated_files():
    """A half-written or broken generated file never stops load_all() and is
    never auto-played (run on a copy of the strategy folder)."""
    tmp = Path(tempfile.mkdtemp())
    old_dir, old_ach = S.STRAT_DIR, S.ACH_DIR
    try:
        (tmp / "generated").mkdir()
        shutil.copy(GEN_DIR / "solo_dart.yaml", tmp / "generated" / "solo_dart.yaml")
        (tmp / "generated" / "solo_broken.yaml").write_text("plan: [ {do: place", encoding="utf-8")
        (tmp / "generated" / "solo_list.yaml").write_text("- just a list\n", encoding="utf-8")
        (tmp / "generated" / "solo_bad.yaml").write_text(
            "id: solo_bad\nmodes: [easy]\nplan:\n  - {do: place, id: a1, kind: nosuchtower}\n",
            encoding="utf-8")
        S.STRAT_DIR, S.ACH_DIR = tmp, tmp / "achievements"
        S.log.disabled = True        # the two "does not parse" errors are expected here
        out = S.load_all()
    finally:
        S.log.disabled = False
        S.STRAT_DIR, S.ACH_DIR = old_dir, old_ach
        shutil.rmtree(tmp, ignore_errors=True)
    assert out["solo_dart"]["bot_ready"] is True and out["solo_dart"]["source"] == "generated"
    assert "solo_broken" not in out and "solo_list" not in out
    assert out["solo_bad"]["bot_ready"] is False and out["solo_bad"]["bot_ready_reasons"]
    ok, why = S.usable(out["solo_bad"], "easy", None)
    assert not ok and "not bot-ready" in why


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001 - report every failure, then fail the run
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e)[:400])
    print("all passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
