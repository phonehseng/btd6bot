"""BTD6 auto-farmer.

  python bot.py run [--hours 8]          plan and play games until time is up
  python bot.py plan                     show what the planner would play next
  python bot.py status                   account summary

Press F8 at any time to stop. Single-player standard maps only.
"""
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def setup_logging():
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname).1s %(name)s: %(message)s")
    fh = RotatingFileHandler(ROOT / "logs" / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, sh])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--hours", type=float, default=8.0)
    sub.add_parser("plan")
    sub.add_parser("status")
    args = ap.parse_args()
    setup_logging()

    from btd6bot.account import AccountState
    if args.cmd == "status":
        a = AccountState.load()
        print(f"level {a.player_level}  towers {sorted(a.unlocked_towers)}  heroes {sorted(a.unlocked_heroes)}")
        print(f"medals {a.medal_count()}  unique wins {a.unique_map_wins()}  games {a.games_played}")
        print(f"upgrades {a.unlocked_upgrades}")
        return
    if args.cmd == "plan":
        from btd6bot.planner import next_game
        from btd6bot.runner import planner_specs
        from btd6bot.strategy import load_all
        a = AccountState.load()
        plan = next_game(a, planner_specs(load_all(), a))
        print(plan.reason if plan else "nothing playable")
        for line in (plan.reasons if plan else []):
            print("  ", line)
        return
    from btd6bot.runner import Bot
    Bot().run(hours=args.hours)


if __name__ == "__main__":
    main()
