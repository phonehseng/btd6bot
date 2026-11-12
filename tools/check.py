"""Pre-commit check: the bot imports, strategies load, and every offline test passes.

Usage: python tools/check.py [--jobs N]   (exit code 0 = safe to commit / reload)

The steps run side by side (by default half the CPU cores, so a game the
bot is playing keeps the other half): one after another they now take over
ten minutes, longer than an hourly caretaker run can wait for one command.
The results are still printed in a fixed order; the tests with wall-clock
limits (CLOCKED) come last, each on its own.

Each step runs at below-normal CPU priority with one math-library thread,
so the live bot and the game come first. A run started at normal priority
at 22:30:22 on 2026-11-08 (16 test processes, beside three build
optimisers) is the likeliest reason the bot then logged nothing for two
minutes and noticed a CHIMPS defeat (22:30:28) only at 22:32:25, while the
screen recorder fell 45 s behind as well.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# numpy/OpenCV start one thread per core in every process by default: with
# 16 steps side by side that is hundreds of busy threads
ONE_THREAD = {k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OPENCV_FOR_THREADS_NUM")}

# Tests that hold the code to a wall-clock limit run after all the others,
# one at a time. Beside fifteen other steps at below-normal priority the
# reinforce look-budget test (a 6 s budget, a 1 s limit for a remembered
# answer) failed on the clock alone in the runs of 2026-11-11 07:18-11:44,
# while it passed every time it was run by itself on the same commit.
# The same happened on 2026-11-12, with two or three check runs of other
# sessions on the machine at once, to the three other tests that time
# themselves: the glass HUD's field picture (1.5 s for a map's first
# picture: failed in both checks of the 07:18 caretaker run and at 12:16),
# the glass HUD's widgets (40 ms for a redraw: the 07:18 run) and the wait
# between games (a 1 s limit: the 10:05 run).
# Each passed when run by itself, and no caretaker fix of that morning
# could be merged because the check never ended "ALL OK".
CLOCKED = {"test_reinforce_budget_offline.py", "test_glass_field_offline.py",
           "test_glass_hud_offline.py", "test_between_games_offline.py"}


def run_step(cmd):
    """Run one check step; returns (name, passed, last lines of its output)."""
    flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=flags, env={**os.environ, **ONE_THREAD})
    name = Path(cmd[-1]).name if cmd[-1].endswith(".py") else "import"
    return name, r.returncode == 0, "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
                    help="steps run at the same time (1 = one by one)")
    args = ap.parse_args()
    steps = [[sys.executable, "-c", "import btd6bot.runner, btd6bot.strategy as s; s.load_all()"]]
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    steps += [[sys.executable, str(t)] for t in tests if t.name not in CLOCKED]
    alone = [[sys.executable, str(t)] for t in tests if t.name in CLOCKED]
    failed = []

    def report(name, ok, tail):
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            failed.append(name)
            print(tail)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(run_step, steps):   # map keeps the step order
            report(*result)
    for cmd in alone:                              # the pool is empty by now
        report(*run_step(cmd))
    print("ALL OK" if not failed else f"{len(failed)} FAILED: {failed}")
    sys.exit(1 if failed else 0)
