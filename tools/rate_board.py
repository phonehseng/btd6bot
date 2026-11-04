"""Rate a logged game's board in the damage model, round by round.

The bot logs every purchase ("game: placed n1 (ninja) at 0.206,0.232",
"game: upgraded n1 -> 2-0-1", "game: sold ..."), but not the board itself.
This tool replays those lines between two timestamps to rebuild the towers
standing at a moment of the game, then asks the damage model (dps_model, the
same RoundForecast the match loop uses) how each round would go against
them: its margin, the lives it expects to lose and which bloons leak.

With --drop it also rates each round once per spawn group with that group
removed, which shows which group the rating hangs on. Example: on Lost
Crevasse Impoppable (2026-11-04) round 78 was rated 0.30 with ~7,000 lives
lost, yet the real game held it without a bloon getting past the start;
--drop showed the 72 camo ceramics spawned within 1.2 s were the whole
cause (0.69 without them). Use it when a game's log shows a round rated far
from what happened, or to see what a loss's board was short of.

Usage:
    python tools/rate_board.py "Lost Crevasse" impoppable "2026-11-04 14:07" "2026-11-04 14:17:49" 76 81
    python tools/rate_board.py "Lost Crevasse" impoppable "2026-11-04 14:07" "2026-11-04 14:17:49" 78 --drop
    python tools/rate_board.py ... --log path/to/game.log    # a loss case's game.log
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import dps_model as D  # noqa: E402
from btd6bot.forecast import RoundForecast  # noqa: E402

PLACED = re.compile(r"game: placed (\S+) \((\w+)\) at ([\d.]+),([\d.]+)")
UPGRADED = re.compile(r"game: upgraded (\S+) -> (\d)-(\d)-(\d)")
SOLD = re.compile(r"game: sold (\S+)")
STAMP_LEN = len("2026-11-04 14:07:32,598")


def board_from_log(lines, start, stop):
    """The towers standing at `stop` (timestamps compare as text, so a
    prefix like "2026-11-04 14:07" works), built from the purchase lines
    logged since `start`. Returns {tid: record with tid, kind, tiers, x, y}
    in screen fractions, as RoundForecast.stations reads them."""
    towers = {}
    for line in lines:
        stamp = line[:STAMP_LEN]
        if stamp < start or stamp > stop:
            continue
        if m := PLACED.search(line):
            towers[m[1]] = SimpleNamespace(tid=m[1], kind=m[2], tiers=(0, 0, 0), x=float(m[3]), y=float(m[4]))
        elif (m := UPGRADED.search(line)) and m[1] in towers:
            towers[m[1]].tiers = (int(m[2]), int(m[3]), int(m[4]))
        elif m := SOLD.search(line):
            towers.pop(m[1], None)
    return towers


def rate(stations, mode, rnd, track):
    """(margin, lives lost, {bloon: count leaked}) of one round."""
    res = D.simulate_round(stations, mode, rnd, track)
    leaked = {k: round(v, 1) for k, v in res.leaked.items() if v >= 0.05}
    return D.round_margin(stations, mode, rnd, track), res.lives_lost, leaked


def without_group(group_id):
    """A stand-in for dps_model._round_groups that leaves out every spawn
    group of bloon `group_id` (used by --drop)."""
    full = D._round_groups

    def groups(set_name, rnd):
        return tuple(g for g in full(set_name, rnd) if (g.get("id") or g["bloon"]) != group_id)
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map", help='map name as the game shows it, e.g. "Lost Crevasse"')
    ap.add_argument("mode", help="bot mode key, e.g. impoppable, hard, magic_only")
    ap.add_argument("start", help="timestamp the game started (its first placement or later)")
    ap.add_argument("stop", help="timestamp of the moment to rate the board at")
    ap.add_argument("first", type=int, help="first round to rate")
    ap.add_argument("last", type=int, nargs="?", help="last round to rate (default: first)")
    ap.add_argument("--drop", action="store_true", help="also rate each round without each spawn group")
    ap.add_argument("--log", default=str(ROOT / "logs" / "bot.log"), help="log to read (default logs/bot.log)")
    args = ap.parse_args()

    with open(args.log, encoding="utf-8", errors="replace") as f:
        towers = board_from_log(f, args.start, args.stop)
    if not towers:
        sys.exit("no placements logged between those timestamps")
    for t in towers.values():
        print(f"  {t.tid:10s} {t.kind:10s} {'-'.join(map(str, t.tiers))}")

    forecast = RoundForecast(args.map, args.mode)
    if not forecast._ready():
        sys.exit("the damage model is not available for this map")
    stations = forecast.stations(list(towers.values()))
    if not stations:
        sys.exit("no tower on this board reaches the track in the model")
    track = forecast.track

    for rnd in range(args.first, (args.last or args.first) + 1):
        margin, lives, leaked = rate(stations, args.mode, rnd, track)
        print(f"round {rnd}: margin {margin:.2f}, lives lost {lives:.1f}, leaked {leaked}")
        if not args.drop:
            continue
        set_name = "abr" if args.mode == "abr" else "standard"
        full = D._round_groups
        for gid in sorted({g.get("id") or g["bloon"] for g in full(set_name, rnd)}):
            D._round_groups = without_group(gid)
            track.__dict__.pop("_lot_cache", None)    # lots are cached on the track (dps_model._lots)
            try:
                m, lv, _ = rate(stations, args.mode, rnd, track)
            finally:
                D._round_groups = full
                track.__dict__.pop("_lot_cache", None)
            print(f"    without {gid:14s} margin {m:.2f}, lives lost {lv:.1f}")


if __name__ == "__main__":
    main()
