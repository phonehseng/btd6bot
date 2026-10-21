"""Dev helper: list strategies and which modes the current account can run them in."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btd6bot.account import AccountState  # noqa: E402
from btd6bot.strategy import load_all, usable  # noqa: E402

if __name__ == "__main__":
    a = AccountState.load()
    for sid, s in load_all().items():
        ok = [m for m in s.get("modes", []) if usable(s, m, a)[0]]
        why = {m: usable(s, m, a)[1] for m in s.get("modes", []) if m not in ok}
        print(f"{sid:28s} hero={str(s.get('hero')):10s} usable={ok}")
        if why:
            print(f"{'':28s} blocked: {sorted(set(why.values()))}")
