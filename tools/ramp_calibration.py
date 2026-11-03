"""How well does the in-game blimp check predict a loss?

During a game the strategy logs, once per blimp round, a line like

    blimp check round 40: 1400 blimp HP, 900 units of track; the defence deals about 0.6x that in reach - short

(strategy._ramp_due). This tool pairs the first such ratio for a chosen round
with the outcome of the game it was logged in (the NEXT ... line starts a
game, the RESULT / 'outcome' line ends it) over every logs/bot.log* file, and
prints, per mode family, how many games were won and lost with the ratio
under and over 1.0 (strategy.RAMP_OK).

With --offline it asks the same question of the OFFLINE estimate instead:
tools/simulate_threats.py plays each (strategy, mode) of logs/results.jsonl
against the round calendar with no game, and its blimp ratio for that round
is paired with every finished game of that (strategy, mode). This is the
number the planner could use before a build was ever played - but only if
it predicts losses, which this table shows.

Usage:  python tools/ramp_calibration.py [round] [--list] [--offline]
        round defaults to 40, the first MOAB; --list prints every game too.
"""
import collections
import glob
import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECK = re.compile(r"blimp check round (\d+): [\d.]+ blimp HP.*?about ([\d.]+)x")
START = re.compile(r"NEXT.*?\] (.+?) / (\w+) with (\S+):")
END = re.compile(r"RESULT.*?(victory|defeat)|'outcome': '(victory|defeat)'")

# modes grouped the way the planner thinks of them (planner.EASY_FAMILY ...)
FAMILY = {"easy": "easy", "primary_only": "easy", "deflation": "easy",
          "medium": "medium", "military_only": "medium", "reverse": "medium", "apopalypse": "medium"}


def games(paths):
    """(map, mode, strategy, outcome, {round: first logged ratio}) per game."""
    for path in paths:
        cur = None
        for line in open(path, encoding="utf-8", errors="replace"):
            m = START.search(line)
            if m:
                cur = (m.groups(), {})
                continue
            if cur is None:
                continue
            m = CHECK.search(line)
            if m:
                cur[1].setdefault(int(m.group(1)), float(m.group(2)))
                continue
            m = END.search(line)
            if m:
                (map_name, mode, strategy), ratios = cur
                yield map_name, mode, strategy, m.group(1) or m.group(2), ratios
                cur = None


OFFLINE_BUCKETS = (0.5, 1.0, 2.0)   # ratio bands: under 0.5x, 0.5-1x, 1-2x, 2x and more


def offline(rnd):
    """Pair the simulator's blimp ratio for round ``rnd`` of each played
    (strategy, mode) with the outcomes of its games in logs/results.jsonl,
    and print the share lost per mode family and ratio band."""
    from btd6bot import strategy as S
    from simulate_threats import simulate
    logging.disable(logging.CRITICAL)      # the executor logs every simulated purchase
    strats = S.load_all()
    results = [json.loads(line) for line in open(ROOT / "logs" / "results.jsonl", encoding="utf-8")
               if line.strip()]
    ratio = {}
    for key in {(r["strategy"], r["mode"]) for r in results}:
        s = strats.get(key[0])
        if s is None or key[1] == "apopalypse":   # random rounds: no calendar
            continue
        ratio[key] = dict(simulate(s, key[1])["ramp"]).get(rnd)
    # (family, band) -> [won, lost]
    table = collections.defaultdict(lambda: [0, 0])
    for r in results:
        x = ratio.get((r["strategy"], r["mode"]))
        if x is None or r.get("outcome") not in ("victory", "defeat"):
            continue
        band = sum(x >= b for b in OFFLINE_BUCKETS)
        table[(FAMILY.get(r["mode"], "hard"), band)][r["outcome"] == "defeat"] += 1
    names = [f"<{OFFLINE_BUCKETS[0]}x"] + [f"{a}-{b}x" for a, b in zip(OFFLINE_BUCKETS, OFFLINE_BUCKETS[1:])] \
        + [f"{OFFLINE_BUCKETS[-1]}x+"]
    print(f"offline blimp ratio round {rnd} (tools/simulate_threats.py) vs. outcome:")
    for (fam, band), (won, lost) in sorted(table.items()):
        print(f"  {fam:7} {names[band]:8} {won:3} won {lost:3} lost ({lost / max(won + lost, 1):.0%} lost)")


def main(argv):
    rnd = int(next((a for a in argv if a.isdigit()), 40))
    if "--offline" in argv:
        offline(rnd)
        return
    paths = sorted(glob.glob(str(ROOT / "logs" / "bot.log*")))
    # family -> [won under 1, lost under 1, won at 1+, lost at 1+]
    table = collections.defaultdict(lambda: [0, 0, 0, 0])
    for map_name, mode, strategy, outcome, ratios in games(paths):
        ratio = ratios.get(rnd)
        if ratio is None:
            continue
        if "--list" in argv:
            print(f"{outcome:8} {ratio:5.1f}x  {map_name} / {mode} / {strategy}")
        cell = (0 if ratio < 1.0 else 2) + (1 if outcome == "defeat" else 0)
        table[FAMILY.get(mode, "hard")][cell] += 1
    print(f"blimp check round {rnd} (ratio = blimp damage in reach / blimp HP):")
    for fam, (wl, ll, wh, lh) in sorted(table.items()):
        under = ll / max(wl + ll, 1)
        over = lh / max(wh + lh, 1)
        print(f"  {fam:7} under 1x: {wl:3} won {ll:3} lost ({under:.0%} lost) | "
              f"1x+: {wh:3} won {lh:3} lost ({over:.0%} lost)")


if __name__ == "__main__":
    main(sys.argv[1:])
