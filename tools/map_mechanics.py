"""Rebuild data/map_mechanics.json and the per-map table in docs/map_mechanics.md.

Usage:
    python tools/map_mechanics.py            # print the table
    python tools/map_mechanics.py --write    # also rewrite the table in the doc

Reads only data/map_geometry (extracted from copies of the game files by
btd6bot/gamefiles.py); the game itself is never touched.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import mapgeom  # noqa: E402

DOC = ROOT / "docs" / "map_mechanics.md"
START, END = "<!-- table:start -->", "<!-- table:end -->"

# short words for each feature kind in the table
WORDS = {
    "area_cycle": "areas open/close in turn",
    "area_appears": "areas appear",
    "area_vanishes": "areas vanish",
    "rotating_area": "rotating ground (carries towers)",
    "moving_platform": "moving platforms (carry towers)",
    "towers_suspended": "towers switched off",
    "path_opens": "path opens",
    "alternating_paths": "paths alternate",
    "seasonal_area": "seasonal obstacle",
    "paid_switch": "paid switch",
    "map_ability": "paid map ability",
    "click_event": "clickable objects",
}


def _rows(data):
    for map_id, m in sorted(data["maps"].items(), key=lambda kv: kv[1]["name"].lower()):
        if map_id in mapgeom.NOT_PLAYABLE_IDS:
            continue
        feats = m["features"]
        rem = [f for f in feats if f["kind"] == "removable"]
        ore = [f for f in feats if f["kind"] == "round_removable"]
        obstacles = ""
        if rem:
            costs = sorted(f["cost"] for f in rem)
            price = f"${costs[0]:,}" if costs[0] == costs[-1] else f"${costs[0]:,}-{costs[-1]:,}"
            locked = sum(1 for f in rem if f.get("unlocked_by"))
            obstacles = f"{len(rem)} ({price})" + (f", {locked} unlocked later" if locked else "")
        if ore:
            obstacles += (" " if obstacles else "") + f"{len(ore)} ore to mine"
        auto = sorted({WORDS[f["kind"]] for f in feats if f["automatic"] and f["kind"] in WORDS
                       and f.get("first_round") != 0})
        player = sorted({WORDS[f["kind"]] for f in feats if not f["automatic"] and f["kind"] in WORDS})
        share = m.get("hidden_track_share", 0.0)
        hidden_txt = f"{share:.0%} of the track" if share >= 0.005 else ""
        yield (m["name"], obstacles, ", ".join(auto), ", ".join(player), hidden_txt,
               "; ".join(m.get("advice", [])))


def table(data):
    lines = ["| Map | Removable obstacles | Changes by itself | Only if the player acts | "
             "Bloons out of reach | Bot's note |",
             "|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(r) + " |" for r in _rows(data)]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help=f"rewrite the table in {DOC.name}")
    args = ap.parse_args()
    data = mapgeom.write_mechanics_summary()
    text = table(data)
    print(text)
    if args.write and DOC.exists():
        doc = DOC.read_text(encoding="utf-8")
        new = re.sub(re.escape(START) + ".*?" + re.escape(END), START + "\n" + text + "\n" + END,
                     doc, flags=re.S)
        DOC.write_text(new, encoding="utf-8")
        print(f"\n{DOC} updated")
