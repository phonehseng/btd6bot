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
  counters.json counters:     per signature, every tower and the minimal
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
    co["counters"] = derive_counters()
    co["crosscheck"] = crosscheck_towers()
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
