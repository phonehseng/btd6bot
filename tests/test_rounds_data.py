"""Sanity checks for data/rounds.json (round-by-round database).
Run: python tests/test_rounds_data.py   (also collectable by pytest). Offline only."""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "rounds.json"
with open(DATA, encoding="utf-8") as _f:
    DB = json.load(_f)

BLOONS = {"red", "blue", "green", "yellow", "pink", "black", "white", "purple", "lead",
          "zebra", "rainbow", "ceramic", "moab", "bfb", "zomg", "ddt", "bad"}
BLIMPS = ("moab", "bfb", "zomg", "ddt", "bad")
# Non-freeplay RBE (rounds <= 80); camo/regrow do not change RBE.
RBE = {"red": 1, "blue": 2, "green": 3, "yellow": 4, "pink": 5, "black": 11, "white": 11,
       "purple": 11, "lead": 23, "zebra": 23, "rainbow": 47, "ceramic": 104,
       "moab": 616, "bfb": 3164, "zomg": 16656, "ddt": 816, "bad": 55760}
RBE_FORT = {"lead": 26, "ceramic": 114, "moab": 856, "bfb": 4824, "zomg": 27296,
            "ddt": 1256, "bad": 98360}
SETS = ("standard", "abr")


def _rounds(name):
    return [(int(k), v) for k, v in sorted(DB[name].items(), key=lambda kv: int(kv[0]))]


def _flags_from_groups(groups):
    names = {g["bloon"] for g in groups}

    def cnt(b):
        return sum(g["count"] for g in groups if g["bloon"] == b)

    return {
        "camo": any(g["camo"] for g in groups) or "ddt" in names,
        "lead": "lead" in names or "ddt" in names,
        "regrow": any(g["regrow"] for g in groups),
        "purple": "purple" in names,
        "fortified": any(g["fortified"] for g in groups),
        "ceramic": "ceramic" in names,
        "black": bool(names & {"black", "zebra", "ddt"}),
        "white": bool(names & {"white", "zebra"}),
        "camo_lead": any(g["camo"] and g["bloon"] == "lead" for g in groups) or "ddt" in names,
        "fortified_lead": any(g["fortified"] and g["bloon"] == "lead" for g in groups),
        "fortified_ceramic": any(g["fortified"] and g["bloon"] == "ceramic" for g in groups),
        "fortified_blimp": any(g["fortified"] and g["bloon"] in BLIMPS for g in groups),
        **{b: cnt(b) for b in BLIMPS},
    }


def _has(rd, bloon, **mods):
    return any(g["bloon"] == bloon and all(g[k] == v for k, v in mods.items()) for g in rd["groups"])


PRED = {
    "camo": lambda rd: rd["flags"]["camo"],
    "lead": lambda rd: rd["flags"]["lead"],
    "regrow": lambda rd: rd["flags"]["regrow"],
    "purple": lambda rd: rd["flags"]["purple"],
    "ceramic": lambda rd: rd["flags"]["ceramic"],
    "black": lambda rd: rd["flags"]["black"],
    "white": lambda rd: rd["flags"]["white"],
    "camo_lead": lambda rd: rd["flags"]["camo_lead"],
    "fortified_lead": lambda rd: rd["flags"]["fortified_lead"],
    "fortified_ceramic": lambda rd: rd["flags"]["fortified_ceramic"],
    "moab": lambda rd: rd["flags"]["moab"] > 0,
    "bfb": lambda rd: rd["flags"]["bfb"] > 0,
    "zomg": lambda rd: rd["flags"]["zomg"] > 0,
    "ddt": lambda rd: rd["flags"]["ddt"] > 0,
    "bad": lambda rd: rd["flags"]["bad"] > 0,
    "fortified_moab": lambda rd: _has(rd, "moab", fortified=True),
    "fortified_bfb": lambda rd: _has(rd, "bfb", fortified=True),
    "fortified_zomg": lambda rd: _has(rd, "zomg", fortified=True),
    "fortified_ddt": lambda rd: _has(rd, "ddt", fortified=True),
    "fortified_bad": lambda rd: _has(rd, "bad", fortified=True),
    "camo_ceramic": lambda rd: _has(rd, "ceramic", camo=True),
    "regrow_ceramic": lambda rd: _has(rd, "ceramic", regrow=True),
    "zebra": lambda rd: _has(rd, "zebra"),
    "rainbow": lambda rd: _has(rd, "rainbow"),
}


# ------------------------------------------------------------------ tests

def test_top_level_keys():
    for key in ("version", "sources", "standard", "abr", "first_appearance", "difficulty_notes",
                "blimp_hp", "checkpoints"):
        assert key in DB, key
    assert len(DB["sources"]) >= 2
    for name in SETS:
        nums = [r for r, _ in _rounds(name)]
        assert nums[0] == 1 and nums == list(range(1, len(nums) + 1)), name
    assert len(DB["standard"]) >= 140 and len(DB["abr"]) >= 100


def test_round_40_single_moab():
    r40 = DB["standard"]["40"]
    blimps = [g for g in r40["groups"] if g["bloon"] in BLIMPS]
    assert len(r40["groups"]) == 1 and len(blimps) == 1, r40["groups"]
    g = blimps[0]
    assert g["bloon"] == "moab" and g["count"] == 1 and not g["fortified"] and not g["camo"]
    assert r40["flags"]["moab"] == 1
    assert all(r40["flags"][b] == 0 for b in ("bfb", "zomg", "ddt", "bad"))
    assert r40["rbe"] == 616 == 200 + 4 * 104
    # ABR R40 is a single *fortified* MOAB
    a40 = DB["abr"]["40"]
    assert [(g["bloon"], g["count"], g["fortified"]) for g in a40["groups"]] == [("moab", 1, True)]
    assert a40["rbe"] == 856


def test_groups_wellformed_and_positive():
    for name in SETS:
        for r, rd in _rounds(name):
            assert rd["groups"], (name, r)
            assert rd["rbe"] > 0 and rd["cash"] > 0, (name, r)
            assert rd["cash_bonus"] == 100 + r, (name, r)
            assert abs(rd["cash"] - (rd["cash_pop"] + rd["cash_bonus"])) < 0.02, (name, r)
            assert rd["bloons"] == sum(g["count"] for g in rd["groups"])
            for g in rd["groups"]:
                assert g["bloon"] in BLOONS, (name, r, g)
                assert g["count"] > 0
                # R86 (both sets) really starts at -0.15 s in the game data
                assert -0.5 <= g["start_s"] <= g["end_s"], (name, r, g)
                if g["fortified"]:
                    assert g["bloon"] in ("lead", "ceramic") + BLIMPS, (name, r, g)


def test_flags_match_groups():
    for name in SETS:
        for r, rd in _rounds(name):
            want = _flags_from_groups(rd["groups"])
            for k, v in want.items():
                assert rd["flags"][k] == v, (name, r, k, rd["flags"][k], v)


def test_rbe_recomputed_from_groups():
    """Independent check: base RBE of rounds 1-80 = sum of per-bloon RBE."""
    for name in SETS:
        for r, rd in _rounds(name):
            if r > 80:
                break
            total = sum(g["count"] * (RBE_FORT[g["bloon"]] if g["fortified"] else RBE[g["bloon"]])
                        for g in rd["groups"])
            assert total == rd["rbe"], (name, r, total, rd["rbe"])


def test_first_appearance_consistent_with_flags():
    for name in SETS:
        fa = DB["first_appearance"][name]
        rounds = _rounds(name)
        for key, pred in PRED.items():
            hits = [r for r, rd in rounds if pred(rd)]
            expected = hits[0] if hits else None
            assert fa.get(key) == expected, (name, key, fa.get(key), expected)
        for key in ("camo", "lead", "regrow", "purple", "ceramic", "fortified_lead", "moab",
                    "fortified_moab", "bfb", "zomg", "ddt", "bad", "camo_lead", "fortified_ceramic"):
            assert key in fa, (name, key)


def test_known_first_appearances():
    std, abr = DB["first_appearance"]["standard"], DB["first_appearance"]["abr"]
    assert (std["regrow"], std["camo"], std["purple"], std["lead"], std["ceramic"]) == (17, 24, 25, 28, 38)
    assert (std["moab"], std["bfb"], std["fortified_moab"], std["zomg"], std["ddt"], std["bad"]) == \
        (40, 60, 62, 80, 90, 100)
    assert (std["camo_lead"], std["fortified_lead"], std["fortified_ceramic"]) == (59, 45, 46)
    assert (abr["camo"], abr["lead"], abr["purple"], abr["ceramic"], abr["camo_lead"]) == (5, 10, 15, 32, 24)
    assert (abr["moab"], abr["fortified_moab"], abr["bfb"], abr["zomg"], abr["ddt"], abr["bad"]) == \
        (40, 40, 54, 79, 88, 99)


def test_no_ddt_or_bad_in_hard_games():
    for name in SETS:
        for r in range(3, 81):
            f = DB[name][str(r)]["flags"]
            assert f["ddt"] == 0 and f["bad"] == 0, (name, r)
    assert DB["standard"]["80"]["flags"]["zomg"] == 1
    assert DB["standard"]["100"]["flags"]["bad"] == 1


def test_blimp_hp_table():
    b = DB["blimp_hp"]
    assert (b["moab"], b["bfb"], b["zomg"], b["ddt"], b["bad"]) == (200, 700, 4000, 400, 20000)
    rbe = b["rbe"]
    assert rbe["moab"] == b["moab"] + 4 * rbe["ceramic"]
    assert rbe["bfb"] == b["bfb"] + 4 * rbe["moab"]
    assert rbe["zomg"] == b["zomg"] + 4 * rbe["bfb"]
    assert rbe["ddt"] == b["ddt"] + 4 * rbe["ceramic"]
    assert rbe["bad"] == b["bad"] + 2 * rbe["zomg"] + 3 * rbe["ddt"]
    for k in ("moab", "bfb", "zomg", "ddt", "bad"):
        assert b["fortified"][k] == 2 * b[k]
    ramp = b["freeplay_hp_multiplier"]["per_round_81_140"]
    assert ramp["81"] == 1.02 and ramp["100"] == 1.4 and ramp["101"] == 1.45 and ramp["125"] == 2.75
    # R100 BAD: 20,000 x 1.40
    assert DB["standard"]["100"]["max_blimp_hp"] == 28000


def test_checkpoints():
    windows = {"hard": (3, 80), "chimps": (6, 100), "abr": (3, 80)}
    for mode, (lo, hi) in windows.items():
        cps = DB["checkpoints"][mode]
        rounds = [c["by_round"] for c in cps]
        assert rounds == sorted(rounds), mode
        assert all(lo <= r <= hi for r in rounds), mode
        for c in cps:
            assert c["need"] and c["why"] and c["threat"], c
            if c["answers_key"]:
                assert c["answers_key"] in DB["answers"]
    hard = {c["by_round"]: c["threat"] for c in DB["checkpoints"]["hard"]}
    assert hard[24] == "camo" and hard[28] == "lead" and hard[40] == "moab" and hard[80] == "zomg"
    assert {59, 63, 76, 78, 80} <= set(hard)
    chimps = {c["by_round"] for c in DB["checkpoints"]["chimps"]}
    assert {90, 95, 98, 100} <= chimps
    # a checkpoint never comes after the first appearance it guards
    fa = DB["first_appearance"]
    for mode, key in (("hard", "standard"), ("chimps", "standard"), ("abr", "abr")):
        for threat in ("camo", "lead", "moab", "bfb", "zomg", "ddt"):
            first = fa[key][threat]
            lo, hi = windows[mode]
            if first is None or not lo <= first <= hi:
                continue
            guards = [c["by_round"] for c in DB["checkpoints"][mode] if c["threat"] == threat]
            if guards:
                assert min(guards) <= first, (mode, threat, guards, first)


def test_answers_crosspaths_legal():
    pat = re.compile(r"^[0-5]-[0-5]-[0-5]$")
    for threat, cats in DB["answers"].items():
        assert set(cats) == {"primary", "military", "magic", "support"}, threat
        for cat, lst in cats.items():
            assert lst, (threat, cat)
            for a in lst:
                assert pat.match(a["crosspath"]), a
                tiers = [int(t) for t in a["crosspath"].split("-")]
                assert sum(1 for t in tiers if t > 0) <= 2 and sum(1 for t in tiers if t > 2) <= 1, a
                assert a["cost_hard"] > 0 and a["cost_impoppable"] >= a["cost_hard"], a


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("all tests passed")
