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


STACKS_EVERY_S = 60
STALL_CHECK_S = 5      # how often the match loop's heartbeat is checked
STALLS_KEPT = 20       # stack dumps of stalls kept in logs/stalls/


def keep_stack_snapshot():
    """Every minute, write where every thread of the bot is to logs/stacks.txt.

    On 2026-10-23 the bot sat 25 minutes on a Victory screen with its log
    silent; nothing showed which loop it was in. This file always holds
    the latest answer (it is overwritten, not appended).

    Every few seconds the match loop's heartbeat (match.LoopBeat) is checked
    too: a loop stuck in one phase for long gets its stacks saved to
    logs/stalls/ and a warning in the log. Spring Spring CHIMPS
    (2026-11-08) went two minutes without a line, and the stacks.txt
    written during that stall had been overwritten by the time it was read.
    """
    import threading
    import time
    import traceback

    def stacks():
        frames = sys._current_frames()
        text = [time.strftime("%Y-%m-%d %H:%M:%S")]
        for t in threading.enumerate():
            if t.ident in frames and t is not threading.current_thread():
                text.append(f"\n--- thread {t.name}")
                text.append("".join(traceback.format_stack(frames[t.ident])))
        return "\n".join(text)

    def save_stall(report):
        folder = ROOT / "logs" / "stalls"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / time.strftime("stall_%Y%m%d_%H%M%S.txt")
            path.write_text(report + "\n" + stacks(), encoding="utf-8")
            for old in sorted(folder.glob("stall_*.txt"))[:-STALLS_KEPT]:
                old.unlink()
        except OSError:
            path = None
        logging.getLogger("bot").warning("match loop %s - stacks in %s", report, path)

    def loop():
        last = time.time()
        while True:
            time.sleep(STALL_CHECK_S)
            # only once the bot itself has imported it: no import from this thread
            match = sys.modules.get("btd6bot.match")
            report = match.LoopBeat.stall_report() if match else None
            if report:
                save_stall(report)
            if time.time() - last < STACKS_EVERY_S:
                continue
            last = time.time()
            try:
                (ROOT / "logs" / "stacks.txt").write_text(stacks(), encoding="utf-8")
            except OSError:
                pass   # a locked file must never stop the bot

    threading.Thread(target=loop, name="stack-snapshot", daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--hours", type=float, default=8.0)
    sub.add_parser("plan")
    sub.add_parser("status")
    args = ap.parse_args()
    setup_logging()
    keep_stack_snapshot()

    from btd6bot.account import AccountState
    from btd6bot.identity import current_path
    if args.cmd == "status":
        a = AccountState.load(current_path())
        print(f"level {a.player_level}  towers {sorted(a.unlocked_towers)}  heroes {sorted(a.unlocked_heroes)}")
        print(f"medals {a.medal_count()}  unique wins {a.unique_map_wins()}  games {a.games_played}")
        print(f"upgrades {a.unlocked_upgrades}")
        return
    if args.cmd == "plan":
        from btd6bot.planner import next_game
        from btd6bot.runner import planner_specs
        from btd6bot.strategy import load_all
        a = AccountState.load(current_path())
        plan = next_game(a, planner_specs(load_all(), a))
        print(plan.reason if plan else "nothing playable")
        for line in (plan.reasons if plan else []):
            print("  ", line)
        return
    # one bot at a time (two would fight over the mouse)
    import win32api
    import win32event
    import winerror
    _lock = win32event.CreateMutex(None, False, "Global\BTD6Bot")  # noqa: F841 (held for life)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        logging.getLogger("bot").warning("another bot instance is running - exiting")
        sys.exit(5)
    from btd6bot import hudstate
    hudstate.enable()          # this is the bot: its state goes to the big HUD (logs/hud.json)
    from btd6bot.inputs import Aborted
    from btd6bot.runner import Bot
    try:
        Bot().run(hours=args.hours)
    except Aborted:
        logging.getLogger("bot").warning("stopped by the user (Ctrl+Alt+F8 or STOP file)")
        sys.exit(3)  # run_forever.ps1 treats 3 as "user stop"


if __name__ == "__main__":
    main()
