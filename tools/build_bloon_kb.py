"""Build the derived parts of the bloon knowledge base.

Hand-entered facts live in the data files themselves:
  data/bloons.json     per bloon: class, layer HP, children, properties
                       (plus speed/bright/hue, which tracklearn.py uses)
  data/counters.json   damage types, and per tower the damage type of each
                       attack per crosspath, its camo access and its auras

Everything that can be worked out from those facts and from the game's own
round data (data/game_data/round_sets.json) is derived here and written
back, so it can never drift from its sources:
  bloons.json  bloons.<name>: rbe, rbe_fortified, immune_to, signatures,
                              first_spawn (per round set and modifier)
               threat_rounds: per mode, the first round each signature
                              (camo, lead, camo+lead, zebra, ddt ...) is needed
               crosscheck:    disagreements with data/game_model (when present)
  counters.json model_towers: attacks and blimp damage the hand facts lack,
                              from the game model (derive_model_towers)
                counters:     per signature, every tower and the minimal
                              crosspath at which it handles it on its own,
                              and what support (radar / MIB) adds

Usage:  python tools/build_bloon_kb.py           (rewrite the derived parts)
        python tools/build_bloon_kb.py --check   (exit 1 if they are out of date)
tests/test_threats_offline.py runs the --check comparison too.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import threats as TH  # noqa: E402

DATA = ROOT / "data"
GAME_MODEL = DATA / "game_model"

# Modes whose threat rounds are listed: (round set, mode name in strategy.MODE_RULES).
# Modes that share a window with another are folded into it in the output.
LISTED_MODES = ("easy", "medium", "hard", "impoppable", "abr", "deflation")
# The signatures the bot checks, in the order they are listed.
SIGNATURE_ORDER = ("camo", "lead", "black", "white", "zebra", "purple", "camo+lead",
                   "camo+black", "camo+white", "camo+zebra", "camo+purple", "blimp", "ddt")


def _mode_window(mode):
    from btd6bot.strategy import MODE_RULES
    r = MODE_RULES[mode]
    return r["start_round"], r["end_round"]


def immune_to(props):
    """Damage types that cannot pop a bloon with these properties."""
    out = []
    for dtype, facts in (TH.counters().get("damage_types") or {}).items():
        if set(facts.get("cannot_pop") or ()) & set(props):
            out.append(dtype)
    return out


def first_spawn(bloon):
    """{round set: {'any'|'camo'|'regrow'|'fortified': first round}} the bloon
    is sent as a group of its own (not as a child)."""
    out = {}
    for set_name in ("standard", "abr"):
        seen = {}
        for rnd in range(1, 141):
            for g in TH.round_groups(set_name, rnd):
                if g["bloon"] != bloon:
                    continue
                seen.setdefault("any", rnd)
                for mod in ("camo", "regrow", "fortified"):
                    if g.get(mod):
                        seen.setdefault(mod, rnd)
        out[set_name] = seen
    return out


def derive_bloons():
    """The derived per-bloon fields: {bloon: {field: value}}."""
    out = {}
    for name, facts in TH.bloons().items():
        props = facts.get("properties") or []
        d = {
            "rbe": TH.rbe(name),
            "immune_to": immune_to(props),
            "signatures": sorted(TH.sig_name(s) for s in TH.signatures(name)),
            "first_spawn": first_spawn(name),
        }
        if facts.get("hp_fortified"):
            d["rbe_fortified"] = TH.rbe(name, fortified=True)
        out[name] = d
    return out


def derive_threat_rounds():
    """{mode: {signature name: first round needed}} for the listed modes."""
    out = {}
    for mode in LISTED_MODES:
        start, end = _mode_window(mode)
        first = TH.first_rounds(TH.set_for_mode(mode), start, end)
        out[mode] = {"rounds": f"{start}-{end}",
                     "first": {k: first[k] for k in SIGNATURE_ORDER if k in first}}
    return out


def derive_counters():
    """{signature: {'alone': [...], 'with_radar': [...], 'with_mib': [...]}}.

    alone:      the tower handles it by itself at that (minimal) crosspath
    with_radar: ... when it stands in a Radar Scanner village's range
    with_mib:   ... when it stands in a Monkey Intelligence Bureau's range
    Only facts the bot counts (established / game_model) are used."""
    radar = [("radar", "village", (0, 2, 0))]
    mib = [("mib", "village", (0, 3, 0))]
    out = {}
    for name in SIGNATURE_ORDER:
        sig = TH.sig_from_name(name)
        entry = {"alone": [], "with_radar": [], "with_mib": []}
        for kind in (TH.counters().get("towers") or {}):
            for key, others in (("alone", []), ("with_radar", radar), ("with_mib", mib)):
                for t in TH.covering_crosspaths(kind, sig, others, tid="t"):
                    if key != "alone" and any(all(a <= b for a, b in zip(_t(x["crosspath"]), t))
                                              for x in entry["alone"] if x["tower"] == kind):
                        continue    # already handles it alone at a smaller crosspath
                    if kind == "village" and key != "alone":
                        continue
                    how = TH.covers(others + [("t", kind, t)], sig, poppers={"t"})[1]
                    entry[key].append({"tower": kind, "crosspath": "-".join(map(str, t)),
                                       "how": how.split(": ", 1)[-1].rstrip(")")})
        out[name] = entry
    return out


def _t(cross):
    return tuple(int(c) for c in cross.split("-"))


# ---------------------------------------------------------------------------
# Facts the hand entries lack, derived from the game model
# ---------------------------------------------------------------------------
# counters.json had no attack facts for the Desperado, Mermonkey, Skywarden,
# Beast Handler and Glue Gunner ("no reliable facts - never counted"), and
# no blimp damage figure for those or for the Ice Monkey and Dartling. So
# they could never answer a bloon with two immunities at once (zebra, DDT:
# threats._hit needs one attack that pops both), counted as zero blimp
# damage in the executor's blimp ramp, and got a "support" build in
# gen_builds (docs/tower_exclusions_audit.md item 5). The game model has all
# of them, and btd6bot/dps_model.py turns it into damage sources; this part
# reads those sources for every tower whose hand facts are missing.
#
# Conservative on purpose: an ability counts for nothing (it fires only part
# of the time), a source that does no damage (a glue that only slows) pops
# nothing, and the blimp figure is one target's: the shots that reach it,
# plus its strongest damage over time once (a coat of glue does not stack).

def _hurts_blimps(src, moab):
    """Can this damage source hit MOAB-class bloons (camo and immunities
    aside: those are part of the signature)?"""
    if src.only_tags and not (src.only_tags & moab.tags):
        return False
    return not (src.excluded_tags & moab.tags)


def _own_damage_sources(D, kind, tiers):
    """The crosspath's damage sources (dps_model.profile) that do damage
    and are not an ability's; [] when the model has no such crosspath."""
    prof = D.profile(kind, tiers)
    if prof is None:
        return []
    return [s for s in prof.sources if not s.ability and (s.damage > 0 or s.dot_total > 0 or s.dot_rate > 0)]


def derive_model_towers():
    """{tower: {"attacks": [...], "blimp_dps": [[cross, dps], ...]}} for the
    towers whose hand facts in counters.json lack them (see above):

    attacks    (only for a tower with no counted hand attack) one entry per
               distinct (cannot_pop, blimp) pair of its damage sources, with
               every crosspath where such a source exists;
    blimp_dps  (only for a tower with no hand blimp_dps row) one row per
               crosspath that hurts MOAB-class bloons: shots per second at a
               lone target x damage to a MOAB, plus the strongest damage
               over time per second.
    Empty when the game model is missing."""
    from btd6bot import dps_model as D
    if not D.available():
        return {}
    co = TH.counters()
    moab = D.layer("Moab")
    out = {}
    for kind, facts in (co.get("towers") or {}).items():
        need_attacks = not any(TH._counted(a) for a in facts.get("attacks") or ())
        need_blimp = kind not in (co.get("blimp_dps") or {})
        if not (need_attacks or need_blimp):
            continue
        groups, rows = {}, []
        for t in TH.all_crosspaths():
            cross = "-".join(map(str, t))
            sources = _own_damage_sources(D, kind, t)
            for s in sources:
                key = (tuple(sorted(s.immune)), _hurts_blimps(s, moab))
                groups.setdefault(key, []).append(cross)
            onto = [s for s in sources if _hurts_blimps(s, moab)]
            dps = sum(s.shots_single * s.damage_vs(moab) for s in onto) + max((s.dot_rate for s in onto), default=0.0)
            if dps > 0:
                rows.append([cross, round(dps, 1)])
        entry = {}
        if need_attacks and groups:
            entry["attacks"] = [
                {"type": "model", "cannot_pop": list(immune), "blimp": blimp,
                 "crosspaths": sorted(set(crosses), key=lambda c: (sum(_t(c)), c)),
                 "confidence": "game_model", "what": "derived from the game model (dps_model sources)"}
                for (immune, blimp), crosses in sorted(groups.items())]
        if need_blimp and rows:
            entry["blimp_dps"] = rows
        if entry:
            out[kind] = entry
    return out


def crosscheck():
    """Compare the hand-entered bloon facts with data/game_model/bloons.json
    (decoded from the game by tools/decode_sim_model.py): layer HP, speed
    relative to a red, children and immunities."""
    path = GAME_MODEL / "bloons.json"
    if not path.exists():
        return {"status": "data/game_model/bloons.json not available - hand facts unverified"}
    try:
        gm = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"status": f"data/game_model/bloons.json unreadable: {e}"}
    entries = {k.lower(): v for k, v in gm.items() if isinstance(v, dict)}
    diffs, checked = [], 0
    for name, facts in TH.bloons().items():
        e = entries.get(name)
        if e is None:
            continue
        checked += 1
        if e.get("health") is not None and e["health"] != facts.get("hp"):
            diffs.append(f"{name}.hp: ours {facts.get('hp')}, game {e['health']}")
        if e.get("speed_vs_red") is not None and abs(e["speed_vs_red"] - facts.get("speed", 0)) > 0.005:
            diffs.append(f"{name}.speed: ours {facts.get('speed')}, game {e['speed_vs_red']}")
        kids = sorted(k.lower().replace("camo", "").replace("regrow", "").replace("fortified", "")
                      for k, n in (e.get("children") or {}).items() for _ in range(int(n)))
        if kids != sorted(facts.get("children") or []):
            diffs.append(f"{name}.children: ours {facts.get('children')}, game {e.get('children')}")
        ours_imm = set(facts.get("properties") or ()) & {"lead", "black", "white", "purple"}
        if set(e.get("immune") or ()) != ours_imm:
            diffs.append(f"{name}.immune: ours {sorted(ours_imm)}, game {e.get('immune')}")
    return {"status": f"checked {checked} bloons against data/game_model/bloons.json",
            "disagreements": diffs}


def crosscheck_towers():
    """Where counters.json's own facts (without the game model) disagree with
    the game model, per tower and property: the crosspaths where they differ.
    The bot uses the game model there; this list shows which hand facts were
    wrong or too cautious."""
    from btd6bot import gamemodel
    if not gamemodel.available():
        return {"status": "data/game_model not available - counters.json facts unverified"}
    saved = TH._gm
    try:
        TH._gm = lambda: None           # our facts alone ...
        TH.clear_caches()
        ours = {}
        for kind in TH.counters().get("towers") or {}:
            for t in TH.all_crosspaths():
                for prop in ("lead", "black", "white", "purple"):
                    ours[(kind, t, prop)] = TH.covers([("t", kind, t)], frozenset({prop}))[0]
                # camo detection only (spikes hit camo on the track without it)
                ours[(kind, t, "camo")] = (TH.camo_access(kind, t) or "").startswith("detect")
    finally:
        TH._gm = saved
        TH.clear_caches()
    wrong, cautious = {}, {}
    for (kind, t, prop), mine in ours.items():
        game = gamemodel.can(kind, t, prop)
        if game is None or game == mine:
            continue
        key = f"{kind}.{prop}"
        (wrong if mine else cautious).setdefault(key, []).append("-".join(map(str, t)))
    trim = lambda d: {k: (v[:6] + [f"... {len(v)} crosspaths"] if len(v) > 6 else v)  # noqa: E731
                      for k, v in sorted(d.items())}
    return {"status": "counters.json facts alone vs the game model (the bot uses the game model)",
            "claimed_but_game_says_no": trim(wrong),
            "game_says_yes_we_did_not_claim": trim(cautious)}


def build():
    """(new bloons.json dict, new counters.json dict)."""
    bl = json.loads((DATA / "bloons.json").read_text(encoding="utf-8"))
    for name, fields in derive_bloons().items():
        bl["bloons"][name].update(fields)
    bl["threat_rounds"] = derive_threat_rounds()
    bl["signatures_note"] = ("A signature is the set of properties ONE attack has to get past "
                             "to pop the bloon (see btd6bot/threats.py). 'zebra' = black+white, "
                             "'ddt' = blimp+camo+lead+black.")
    bl["crosscheck"] = crosscheck()
    co = json.loads((DATA / "counters.json").read_text(encoding="utf-8"))
    co["model_towers"] = derive_model_towers()
    co["model_towers_note"] = ("Derived by tools/build_bloon_kb.py from the game model through "
                               "btd6bot/dps_model.py, for the towers whose hand facts above lack "
                               "attacks or a blimp_dps row (btd6bot/threats.py model_facts). "
                               "Abilities and damage-free sources are left out.")
    # the parts below read the file through threats.py: let them see the
    # derived facts just made, not the ones on disk
    saved = TH.counters
    TH.counters = lambda: co
    TH.clear_caches()
    try:
        co["counters"] = derive_counters()
        co["crosscheck"] = crosscheck_towers()
    finally:
        TH.counters = saved
        TH.clear_caches()
    co["counters_note"] = ("Derived by tools/build_bloon_kb.py from damage_types + towers "
                           "(only facts the bot counts). Minimal crosspaths; any crosspath "
                           "on the way above them works too unless an attack is replaced "
                           "(see 'max' in towers).")
    return bl, co


def _write(path, data):
    """Write JSON atomically: the bot running live may read the file meanwhile."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def out_of_date():
    """Names of the files whose derived parts differ from a fresh build."""
    bl, co = build()
    stale = []
    for path, new in ((DATA / "bloons.json", bl), (DATA / "counters.json", co)):
        old = json.loads(path.read_text(encoding="utf-8"))
        if old != json.loads(json.dumps(new)):
            stale.append(path.name)
    return stale


if __name__ == "__main__":
    if "--check" in sys.argv:
        stale = out_of_date()
        print("up to date" if not stale else f"out of date: {stale}")
        sys.exit(1 if stale else 0)
    bl, co = build()
    _write(DATA / "bloons.json", bl)
    _write(DATA / "counters.json", co)
    TH.clear_caches()
    print("written: data/bloons.json, data/counters.json")
    for mode, d in bl["threat_rounds"].items():
        print(f"  {mode:11s} {d['rounds']:7s} " + ", ".join(f"{k} {v}" for k, v in d["first"].items()))
