"""A small progress summary for people watching the bot (logs/progress.json).

Written by the runner at start-up, after every game and while waiting. It is
read by dashboards such as the editor's "btd6-progress" pane, but is plain
JSON anyone can open. Nothing in the bot reads it back.

Contents:
  updated      unix time of this summary
  status       the current one-line status (same text as logs/state.txt)
  account      id, level, monkey money
  maps         number of single-player maps
  medals       per mode: how many maps have that medal
  goals        headline goals with done/total (Hard, Hard sub-modes, CHIMPS ...)
  session      games, wins, losses, minutes played since this bot process started
  recent       the last results, newest last
"""
import json
import time
from pathlib import Path

from .account import EXCLUDED_MAPS, MAPS, MODES

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_FILE = ROOT / "logs" / "progress.json"
RESULTS_FILE = ROOT / "logs" / "results.jsonl"   # one line per finished game

HARD_SUBMODES = ("magic_only", "double_hp", "half_cash", "abr", "impoppable")

_session = {"started": time.time(), "games": 0, "wins": 0, "losses": 0, "minutes": 0.0}


def record_result(plan, res):
    """Append one finished game to results.jsonl and count it for the session."""
    won = res.get("outcome") == "victory"
    row = {"t": round(time.time()), "map": plan.map, "mode": plan.mode_key,
           "strategy": plan.strategy_id, "outcome": res.get("outcome"),
           "round": res.get("round"), "minutes": round(res.get("minutes") or 0, 1),
           "lives_lost": res.get("lives_lost"), "mm": res.get("mm")}
    _session["games"] += 1
    _session["wins" if won else "losses"] += 1
    _session["minutes"] += row["minutes"]
    try:
        RESULTS_FILE.parent.mkdir(exist_ok=True)
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def _recent(n=8):
    try:
        lines = RESULTS_FILE.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except (OSError, ValueError):
        return []


def _current_account_id():
    try:
        return (ROOT / "data" / "current_account.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write(account, status=""):
    """Rewrite logs/progress.json from the account's notes."""
    maps = [m for m in MAPS if m not in EXCLUDED_MAPS]
    medals = {mode: sum(1 for m in maps if account.has_medal(m, mode)) for mode in MODES}
    total = len(maps)
    goals = [
        {"name": "Hard", "done": medals.get("hard", 0), "total": total},
        {"name": "Hard sub-modes", "done": sum(medals.get(k, 0) for k in HARD_SUBMODES),
         "total": total * len(HARD_SUBMODES)},
        {"name": "CHIMPS", "done": medals.get("chimps", 0), "total": total},
        {"name": "Medium (all modes)", "done": sum(medals.get(k, 0) for k in
                                                   ("medium", "military_only", "apopalypse", "reverse")),
         "total": total * 4},
        {"name": "Easy (all modes)", "done": sum(medals.get(k, 0) for k in
                                                 ("easy", "primary_only", "deflation")),
         "total": total * 3},
    ]
    summary = {
        "updated": round(time.time()),
        "status": status,
        "account": {"id": _current_account_id(), "level": account.player_level,
                    "monkey_money": account.monkey_money},
        "maps": total,
        "medals": medals,
        "goals": goals,
        "session": dict(_session),
        "recent": _recent(),
    }
    try:
        PROGRESS_FILE.parent.mkdir(exist_ok=True)
        tmp = PROGRESS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        tmp.replace(PROGRESS_FILE)
    except OSError:
        pass
