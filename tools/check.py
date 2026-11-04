"""Pre-commit check: the bot imports, strategies load, and every offline test passes.

Usage: python tools/check.py [--jobs N]   (exit code 0 = safe to commit / reload)

The steps run side by side (by default half the CPU cores, so a game the
bot is playing keeps the other half): one after another they now take over
ten minutes, longer than an hourly caretaker run can wait for one command.
The results are still printed in a fixed order.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(cmd):
    """Run one check step; returns (name, passed, last lines of its output)."""
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
    name = Path(cmd[-1]).name if cmd[-1].endswith(".py") else "import"
    return name, r.returncode == 0, "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
                    help="steps run at the same time (1 = one by one)")
    args = ap.parse_args()
    steps = [[sys.executable, "-c", "import btd6bot.runner, btd6bot.strategy as s; s.load_all()"]]
    steps += [[sys.executable, str(t)] for t in sorted((ROOT / "tests").glob("test_*.py"))]
    failed = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name, ok, tail in pool.map(run_step, steps):   # map keeps the step order
            print(("PASS " if ok else "FAIL ") + name, flush=True)
            if not ok:
                failed.append(name)
                print(tail)
    print("ALL OK" if not failed else f"{len(failed)} FAILED: {failed}")
    sys.exit(1 if failed else 0)
