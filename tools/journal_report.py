"""Sum up the game journals (btd6bot/journal.py): why games were lost, what
leaked, what the money went on, and how far the damage model can be trusted.

Read-only. Reads logs/journal/*.jsonl and the journal.jsonl copies in the
loss case folders (~/.btd6bot_cache/losses/*/), each game counted once.

Usage:
    python tools/journal_report.py [--mode chimps] [--strategy chimps_ninja_sun]
                                   [--map "Alpine Run"] [--since 7d] [--losses-only] [--json]

Tables:
  * causes of death by category and strategy (journal.cause_of_death)
  * deaths and leaks by round
  * lives leaked by bloon type (each leak split by the bloons' share of the round's RBE)
  * properties nothing on the map popped when lives were lost
  * spend and purchases by why.source (plan, fill, panic, reinforce ...)
  * model calibration: the margin a round started with against how often it leaked
  * per strategy, the median round each tower reached each crosspath, in wins
    and in losses (a step that arrives later in losses is a step that comes too late)
"""
import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import journal   # noqa: E402

LOSS_DIR = Path.home() / ".btd6bot_cache" / "losses"
# margin buckets of the calibration table: (label, low, high)
MARGIN_BUCKETS = (("<0.5", float("-inf"), 0.5), ("0.5-1", 0.5, 1.0), ("1-1.5", 1.0, 1.5), (">1.5", 1.5, float("inf")))
UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def parse_since(text):
    """'7d', '12h', '30m', '2w' -> seconds; None for no limit."""
    if not text:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([mhdw])\s*", text.lower())
    if not m:
        raise SystemExit(f"--since wants a number and m/h/d/w, like 7d (got {text!r})")
    return float(m.group(1)) * UNIT_SECONDS[m.group(2)]


def journal_files(journal_dir, loss_dir):
    """Every journal file: the live folder first, then the loss copies."""
    files = sorted(Path(journal_dir).glob("*.jsonl")) if journal_dir else []
    if loss_dir:
        files += sorted(Path(loss_dir).glob("*/journal.jsonl"))
    return files


class GameRecord:
    """One game's journal events, sorted into what the tables need."""

    def __init__(self, path, events):
        self.path = path
        self.events = events
        self.start = next((e for e in events if e.get("ev") == "game_start"), {})
        self.end = next((e for e in reversed(events) if e.get("ev") == "game_end"), None)
        self.leaks = [e for e in events if e.get("ev") == "leak"]
        self.rounds = [e for e in events if e.get("ev") == "round"]
        self.purchases = [e for e in events if e.get("ev") in journal.PURCHASES]

    @property
    def key(self):
        """The same game in the live folder and in a loss folder is one game."""
        return (self.start.get("map"), self.start.get("mode"), round(self.start.get("t") or 0))

    @property
    def outcome(self):
        return (self.end or {}).get("outcome") or "unfinished"

    @property
    def strategy(self):
        return self.start.get("strategy") or "?"

    @property
    def lost(self):
        return self.outcome not in ("victory", "unfinished")


def load_games(files, mode=None, strategy=None, map_name=None, since=None, losses_only=False, now=None):
    """GameRecords of the journal files that pass the filters, one per game."""
    now = now or time.time()
    seen, out = set(), []
    for f in files:
        events = journal.read(f)
        if not events:
            continue
        g = GameRecord(f, events)
        if g.key in seen:
            continue
        seen.add(g.key)
        if mode and g.start.get("mode") != mode:
            continue
        if strategy and g.strategy != strategy:
            continue
        if map_name and map_name.lower() not in (g.start.get("map") or "").lower():
            continue
        if since and now - (g.start.get("t") or 0) > since:
            continue
        if losses_only and not g.lost:
            continue
        out.append(g)
    return out


def _bloon_label(group):
    flags = [k for k in ("fortified", "camo", "regrow") if group.get(k)]
    return " ".join(flags + [group.get("bloon", "?")])


def summarize(games):
    """Every table, as plain data (what --json prints)."""
    causes = Counter()
    deaths_by_round, leaks_by_round, lives_by_round = Counter(), Counter(), Counter()
    lives_by_bloon = Counter()
    uncovered = Counter()
    by_source = defaultdict(lambda: {"places": 0, "upgrades": 0, "spent": 0})
    calib = {label: {"rounds": 0, "leaked": 0} for label, _, _ in MARGIN_BUCKETS}
    reached = defaultdict(lambda: {"wins": [], "losses": []})   # (strategy, tid, cross) -> rounds
    for g in games:
        if g.lost:
            cause = (g.end or {}).get("cause") or {}
            causes[(cause.get("category") or "unknown", g.strategy)] += 1
            deaths_by_round[(g.end or {}).get("round")] += 1
        for e in g.leaks:
            lost = e.get("lost") or 0
            leaks_by_round[e.get("rnd")] += 1
            lives_by_round[e.get("rnd")] += lost
            for grp in e.get("groups") or ():
                lives_by_bloon[_bloon_label(grp)] += lost * (grp.get("share") or 0)
            for name in e.get("uncovered") or ():
                uncovered[name] += 1
        for e in g.purchases:
            src = (e.get("why") or {}).get("source") or "unknown"
            by_source[src]["places" if e["ev"] == "place" else "upgrades"] += 1
            by_source[src]["spent"] += e.get("cost") or 0
        leak_rounds = {e.get("rnd") for e in g.leaks}
        for snap in g.rounds:
            m = snap.get("margin")
            if m is None or snap.get("setup"):
                continue
            label = next(lb for lb, lo, hi in MARGIN_BUCKETS if lo <= m < hi)
            calib[label]["rounds"] += 1
            calib[label]["leaked"] += snap.get("rnd") in leak_rounds
        if g.outcome != "unfinished":      # a game cut short says nothing about timing
            first = {}
            for e in g.purchases:
                cross = "placed" if e["ev"] == "place" else e.get("cross_after")
                first.setdefault((e.get("tid"), cross), e.get("rnd"))
            for (tid, cross), rnd in first.items():
                if rnd is not None:
                    reached[(g.strategy, tid, cross)]["losses" if g.lost else "wins"].append(rnd)
    return {
        "games": len(games),
        "wins": sum(g.outcome == "victory" for g in games),
        "losses": sum(g.lost for g in games),
        "causes": [{"category": c, "strategy": s, "games": n} for (c, s), n in causes.most_common()],
        "rounds": [{"round": r, "deaths": deaths_by_round.get(r, 0), "leaks": leaks_by_round.get(r, 0),
                    "lives": lives_by_round.get(r, 0)}
                   for r in sorted(set(deaths_by_round) | set(leaks_by_round), key=lambda x: (x is None, x or 0))],
        "lives_by_bloon": [{"bloon": b, "lives": round(v, 1)} for b, v in lives_by_bloon.most_common()],
        "uncovered": [{"property": p, "leaks": n} for p, n in uncovered.most_common()],
        "by_source": [dict(source=s, **v) for s, v in sorted(by_source.items(), key=lambda kv: -kv[1]["spent"])],
        "calibration": [{"margin": lb, "rounds": calib[lb]["rounds"], "leaked": calib[lb]["leaked"],
                         "leak_rate": round(calib[lb]["leaked"] / calib[lb]["rounds"], 3) if calib[lb]["rounds"] else None}
                        for lb, _, _ in MARGIN_BUCKETS],
        "crosspaths": [{"strategy": s, "tid": t, "cross": c,
                        "median_win": statistics.median(v["wins"]) if v["wins"] else None,
                        "median_loss": statistics.median(v["losses"]) if v["losses"] else None,
                        "wins": len(v["wins"]), "losses": len(v["losses"])}
                       for (s, t, c), v in sorted(reached.items(), key=lambda kv: tuple(map(str, kv[0])))],
    }


def table(title, rows, cols):
    """A plain-text table of dict rows; cols: [(key, heading)]."""
    lines = [title, "-" * len(title)]
    if not rows:
        return "\n".join(lines + ["(none)", ""])
    cells = [[("" if r.get(k) is None else str(r.get(k))) for k, _ in cols] for r in rows]
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, (_, h) in enumerate(cols)]
    lines.append("  ".join(h.ljust(w) for (_, h), w in zip(cols, widths)))
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in cells]
    return "\n".join(lines + [""])


def render(s):
    """The plain-text report of summarize()'s tables."""
    out = [f"{s['games']} games: {s['wins']} won, {s['losses']} lost", ""]
    out.append(table("Causes of death", s["causes"], [("category", "cause"), ("strategy", "strategy"),
                                                      ("games", "games")]))
    out.append(table("Deaths and leaks by round", s["rounds"], [("round", "round"), ("deaths", "deaths"),
                                                               ("leaks", "leaks"), ("lives", "lives lost")]))
    out.append(table("Lives leaked by bloon type (by RBE share)", s["lives_by_bloon"],
                     [("bloon", "bloon"), ("lives", "lives")]))
    out.append(table("Properties nothing popped when lives were lost", s["uncovered"],
                     [("property", "property"), ("leaks", "leaks")]))
    out.append(table("Spend by why.source", s["by_source"], [("source", "source"), ("places", "places"),
                                                            ("upgrades", "upgrades"), ("spent", "spent $")]))
    out.append(table("Model calibration: margin as the round started vs leaks", s["calibration"],
                     [("margin", "margin"), ("rounds", "rounds"), ("leaked", "leaked"), ("leak_rate", "rate")]))
    out.append(table("Median round each crosspath was reached", s["crosspaths"],
                     [("strategy", "strategy"), ("tid", "tower"), ("cross", "crosspath"),
                      ("median_win", "wins"), ("median_loss", "losses"), ("wins", "n won"), ("losses", "n lost")]))
    return "\n".join(out)


def main(argv=None, journal_dir=None, loss_dir=LOSS_DIR):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode")
    ap.add_argument("--strategy")
    ap.add_argument("--map")
    ap.add_argument("--since", help="only games started this recently: 7d, 12h, 30m, 2w")
    ap.add_argument("--losses-only", action="store_true")
    ap.add_argument("--json", action="store_true", help="the tables as JSON")
    args = ap.parse_args(argv)
    files = journal_files(journal_dir or journal.JOURNAL_DIR, loss_dir)
    games = load_games(files, args.mode, args.strategy, args.map, parse_since(args.since), args.losses_only)
    s = summarize(games)
    print(json.dumps(s, indent=1, default=str) if args.json else render(s))
    return s


if __name__ == "__main__":
    main()
