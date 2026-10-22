"""Pre-commit check: the bot imports, strategies load, and every offline test passes.

Usage: python tools/check.py      (exit code 0 = safe to commit / reload)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    steps = [[sys.executable, "-c", "import btd6bot.runner, btd6bot.strategy as s; s.load_all()"]]
    steps += [[sys.executable, str(t)] for t in sorted((ROOT / "tests").glob("test_*.py"))]
    failed = []
    for cmd in steps:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        name = Path(cmd[-1]).name if cmd[-1].endswith(".py") else "import"
        ok = r.returncode == 0
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failed.append(name)
            print("\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]))
    print("ALL OK" if not failed else f"{len(failed)} FAILED: {failed}")
    sys.exit(1 if failed else 0)
