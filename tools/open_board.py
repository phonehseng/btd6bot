"""The open first-time medals of an account and how sure the planner is of each.

For every (map, mode) medal the account still lacks this prints the best win
probability ``p`` the planner gives any build there, the build that gets it
(``c.s.id``), its games on record there (n) and the progression tier
rank_games put it in (``c.tier``):

    a tier (E, M, H, ...)  over a bar: played in the normal order
    LAST                   under every bar: a last resort, played rather than idling
    out                    fits, but rank_games drops it (struck out or hopeless)
    none                   no build fits this map and mode at all

The bar each p is measured against is ``planner.p_threshold`` for the mode.

By default the strategies are built exactly as the live runner builds them
(``runner.planner_specs`` over ``strategy.load_all()``): only modes the
account's unlocked upgrades can cover, the owned hero, Hard+ priors capped
while untested. ``--generic`` ranks the planner's built-in default
strategies instead (``rank_games`` with no strategy list) - generic builds
like magic_core and late_game_chimps, not the map builds the bot plays.

Use it before and after a change to builds, plans or the model, to see which
medals moved and which still sit under their bar.

Usage:
    python tools/open_board.py                     # the account the bot saw last
    python tools/open_board.py --account SFYOSHHYV
    python tools/open_board.py --mode impoppable   # one mode only
    python tools/open_board.py --generic           # planner's default strategies
    python tools/open_board.py --top 3             # also the next-best builds
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import planner  # noqa: E402
from btd6bot.account import AccountState  # noqa: E402


def main_checkout() -> Path:
    """The main checkout this tree belongs to (itself, outside a worktree).
    Account files are not in git, so a worktree reads the live ones there."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return ROOT


def account_path(uid: str | None) -> Path:
    """The account's state file: data/accounts/<uid>.json, or the account
    the bot saw last (identity.current_path) when no id is given - in this
    tree when it has one, else in the main checkout."""
    if not uid:
        from btd6bot.identity import current_path
        path = Path(current_path())
        if path.exists():
            return path
        uid = path.stem
    for root in (ROOT, main_checkout()):
        path = root / "data" / "accounts" / f"{uid}.json"
        if path.exists():
            return path
    raise SystemExit(f"no state file for account {uid}")


def live_specs(account: AccountState):
    """The strategy list the runner hands rank_games (runner.planner_specs)."""
    from btd6bot.runner import planner_specs
    from btd6bot.strategy import load_all
    return planner_specs(load_all(), account)


def open_medals(account: AccountState, specs=None) -> dict[tuple[str, str], list]:
    """{(map, mode): first-time candidates there, highest p first}.

    Each candidate carries the tier rank_games gave it; a pairing rank_games
    drops (struck out or hopeless as a last resort) is kept with tier
    "out", so the board shows every build that fits, not only those the
    runner would pick."""
    strategies = planner._normalise_strategies(specs)
    _phase, _reasons, ranked = planner.rank_games(account, specs, below_bar=True)
    tiers = {(c.map, c.mode, c.s.id): c.tier for c in ranked if c.first}
    every = planner._candidates(account, strategies, planner.DEFAULT_CONFIG, None,
                                planner.paragon_status(account))
    by_medal: dict[tuple[str, str], list] = defaultdict(list)
    for c in every:
        if not c.first:
            continue
        c.tier = tiers.get((c.map, c.mode, c.s.id), "out")
        by_medal[(c.map, c.mode)].append(c)
    for lst in by_medal.values():
        lst.sort(key=lambda c: -c.p)
    return dict(by_medal)


def unfitted_medals(account: AccountState, board) -> list[tuple[str, str]]:
    """Open first-time medals no build fits at all (absent from ``board``),
    walked the way planner._candidates walks maps and modes."""
    out = []
    for m in planner._all_maps():
        if not account.map_unlocked(m):
            continue
        for mode in planner.MODES:
            if (mode in planner.EXCLUDED_MODES or not account.mode_unlocked(m, mode)
                    or account.has_medal(m, mode)):
                continue
            if (m, mode) not in board:
                out.append((m, mode))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--account", help="account id (default: the account the bot saw last)")
    ap.add_argument("--mode", help="show only this mode")
    ap.add_argument("--generic", action="store_true",
                    help="rank the planner's default strategies, not the runner's")
    ap.add_argument("--top", type=int, default=1, help="builds shown per medal")
    args = ap.parse_args()

    account = AccountState.load(account_path(args.account))
    specs = None if args.generic else live_specs(account)
    board = open_medals(account, specs)
    rows = sorted(board.items(), key=lambda kv: kv[1][0].p)
    bare = unfitted_medals(account, board)
    if args.mode:
        rows = [r for r in rows if r[0][1] == args.mode]
        bare = [k for k in bare if k[1] == args.mode]

    print(f"{'p':>5}  {'bar':>4}  {'tier':<5} {'mode':<13} {'map':<22} build")
    over = 0
    for (m, mode), lst in rows:
        bar = planner.p_threshold(mode)
        over += lst[0].p >= bar
        for i, c in enumerate(lst[:args.top]):
            head = (f"{c.p:5.2f}  {bar:4.2f}  {c.tier or '-':<5} {mode:<13} {m:<22}" if i == 0
                    else f"{c.p:5.2f}  {'':4}  {c.tier or '-':<5} {'':<13} {'':<22}")
            print(f"{head} {c.s.id}  (n={c.n})")
    for m, mode in sorted(bare, key=lambda k: (k[1], k[0])):
        print(f"{'-':>5}  {planner.p_threshold(mode):4.2f}  none  {mode:<13} {m:<22} (no build fits)")
    low = sum(1 for _k, lst in rows if lst[0].p < 0.4)
    print(f"\n{len(rows) + len(bare)} open medals: {over} at or over their bar, "
          f"{low} under 0.4, {len(bare)} with no fitting build")


if __name__ == "__main__":
    main()
