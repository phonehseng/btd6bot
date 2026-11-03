"""How well does the in-game blimp check predict a loss?

During a game the strategy logs, once per blimp round, a line like

    blimp check round 40: 1400 blimp HP, 900 units of track; the defence deals about 0.6x that in reach - short

(strategy._ramp_due). This tool pairs the first such ratio for a chosen round
with the outcome of the game it was logged in (the NEXT ... line starts a
game, the RESULT / 'outcome' line ends it) over every logs/bot.log* file, and
prints, per mode family, how many games were won and lost with the ratio
under and over 1.0 (strategy.RAMP_OK).

Usage:  python tools/ramp_calibration.py [round] [--list]
        round defaults to 40, the first MOAB; --list prints every game too.
"""
import collections
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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


def main(argv):
    rnd = int(next((a for a in argv if a.isdigit()), 40))
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
