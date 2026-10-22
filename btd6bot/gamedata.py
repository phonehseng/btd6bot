"""Read round sets and achievements from the game's own data (read-only).

The game_data bundle (BloonsTD6_Data/StreamingAssets/aa/StandaloneWindows64/Full/
game_data_assets_all_<hash>.bundle) holds plain, readable components:

  * RoundSet     every round of a round set as bloon groups
                 {bloon: "CeramicRegrowFortifiedCamo", count, start, duration};
                 "DefaultRoundSet" is the standard game, "AlternateRoundSet" ABR
  * Achievement  id, goal, reward ("MonkeyMoney:500#Power:MoabMine,3"),
                 isCoop, hidden, and the statistic it counts (steamStatName)

They are extracted to data/game_data/ whenever the bundle changes (a game
update), next to the map geometry (gamefiles.py). As there, only a cached
copy of the bundle is opened; the game's files are never modified.
"""
import json
import logging
import re
from pathlib import Path

from .gamefiles import _cached, _monoscripts, bundle_dir, find_install

log = logging.getLogger("gamedata")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "game_data"
ROUND_SETS = {"standard": "DefaultRoundSet", "abr": "AlternateRoundSet"}
MODIFIERS = ("Regrow", "Fortified", "Camo")   # suffixes on bloon ids, in the game's order


def parse_bloon_id(bloon_id):
    """'CeramicRegrowFortifiedCamo' -> ('ceramic', regrow, fortified, camo)."""
    base = bloon_id
    flags = {}
    for mod in reversed(MODIFIERS):          # strip from the end: ...Fortified, Camo
        flags[mod] = base.endswith(mod)
        if flags[mod]:
            base = base[: -len(mod)]
    for mod in MODIFIERS:                    # any order left over (defensive)
        if mod in base:
            flags[mod] = True
            base = base.replace(mod, "")
    return base.lower(), flags["Regrow"], flags["Fortified"], flags["Camo"]


def _round_groups(rnd):
    out = []
    for g in rnd.get("bloonGroups", []):
        base, regrow, fortified, camo = parse_bloon_id(g["bloon"])
        start = float(g.get("start", 0.0))
        out.append({"bloon": base, "count": int(g["count"]), "camo": camo, "regrow": regrow,
                    "fortified": fortified, "start_s": round(start, 3),
                    "end_s": round(start + float(g.get("duration", 0.0)), 3), "id": g["bloon"]})
    return out


def _parse_loot(text):
    """'MonkeyMoney:500#Power:MoabMine,3' -> {'monkey_money': 500, 'other': ['Power:MoabMine,3']}"""
    out = {"monkey_money": 0, "other": []}
    for part in (text or "").split("#"):
        m = re.match(r"MonkeyMoney:(\d+)", part)
        if m:
            out["monkey_money"] += int(m.group(1))
        elif part:
            out["other"].append(part)
    return out


def _read_bundle(path, monoscripts):
    import UnityPy  # only needed for extraction
    env = UnityPy.load(str(monoscripts), str(path))
    round_sets, achievements = {}, []
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        mb = o.read()
        script = mb.m_Script.read() if mb.m_Script else None
        if script is None:
            continue
        if script.m_ClassName == "RoundSet":
            t = o.read_typetree()
            round_sets[t["m_Name"]] = t
        elif script.m_ClassName == "Achievement":
            t = o.read_typetree()
            achievements.append({
                "id": t.get("achievementId"), "name": t.get("m_Name"), "type": t.get("type"),
                "goal": t.get("achievementGoal"), "counts": t.get("steamStatName"),
                "reward": _parse_loot(t.get("loot")), "coop": bool(t.get("isCoop")),
                "hidden": bool(t.get("hidden")),
            })
    return round_sets, achievements


def refresh(install=None):
    """Re-extract when the game_data bundle changed. Returns True if it did."""
    install = install or find_install()
    if install is None:
        return False
    found = sorted(bundle_dir(install).glob("game_data_assets_all_*.bundle"))
    monoscripts = _monoscripts(install)
    if not found or monoscripts is None:
        return False
    bundle = found[0]
    stamp = OUT_DIR / "source.json"
    try:
        if json.loads(stamp.read_text(encoding="utf-8")).get("bundle") == bundle.name:
            return False  # unchanged since the last extraction
    except (OSError, ValueError):
        pass
    round_sets, achievements = _read_bundle(_cached(bundle), monoscripts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rounds = {mode: {str(i): {"groups": _round_groups(r)}
                     for i, r in enumerate(round_sets[name]["rounds"], start=1)}
              for mode, name in ROUND_SETS.items() if name in round_sets}
    (OUT_DIR / "round_sets.json").write_text(json.dumps(rounds, separators=(",", ":")), encoding="utf-8")
    achievements.sort(key=lambda a: a["id"] if a["id"] is not None else 1e9)
    (OUT_DIR / "achievements.json").write_text(json.dumps(achievements, indent=1), encoding="utf-8")
    stamp.write_text(json.dumps({"bundle": bundle.name}), encoding="utf-8")
    log.info("game data extracted: %s, %d achievements",
             ", ".join(f"{m} {len(r)} rounds" for m, r in rounds.items()), len(achievements))
    return True


if __name__ == "__main__":
    # Manual refresh:  python -m btd6bot.gamedata
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    refresh()
