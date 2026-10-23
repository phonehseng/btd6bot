"""When the coming rounds look weak, buy what the damage model says helps most.

Pat's Pond Hard (2026-10-22) was lost at round 63, the ceramic rush: the
damage model had rated that round 0.63 at its start, and the rounds before
it around 1.0, yet the spare cash went where surplus() always puts it - the
next tier of the biggest tower - whether or not that helped round 63.

Here, while the look-ahead (this round and the next LOOKAHEAD - 1: long
enough to see a spike like round 63 while the cash for it still piles up -
on Pat's Pond $10-15k sat idle at rounds 46-51) is under WEAK_MARGIN, every
legal purchase the cash allows is tried in the model:

  * the next tier of each tower standing (Executor.upgrade_choices: the
    same crosspath and XP-lock rules as surplus; a tower's leading path may
    go past the plan's crosspath);
  * another tower of each damage kind on the map, at the executor's best
    spot for it.

Each is rated by the lives the look-ahead's rounds would cost with every
tower at half strength (1 / TARGET_MARGIN: a defence with margin 2 loses
none there). That count moves with every purchase and needs one simulation
per round; the margin search moves in steps of several percent and hid
most single upgrades (on Pat's Pond from round 47 it found nothing worth
$15,000). The purchase that saves the most of those lives per dollar is
bought. One purchase per call; Match calls again until the look-ahead is
safe or nothing the cash buys helps.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace

log = logging.getLogger("reinforce")

LOOKAHEAD = 10         # rounds rated: the one being played and the next nine
WEAK_MARGIN = 1.5      # worst look-ahead margin under this: reinforce
TARGET_MARGIN = 2.0    # margin the defence is reinforced up to
MIN_SAVED = 0.5        # lives (at half strength) a purchase must save to be worth it
MAX_OPTIONS = 20       # purchases tried per call
NOT_DAMAGE = ("village", "alchemist", "farm")


@dataclass
class Option:
    what: str                      # for the log: "upgrade s3 -> 2-0-5", "another sniper"
    cost: float
    step: dict                     # the executor step that buys it
    towers: list = field(default_factory=list)   # the board after it (for the model)


def lookahead_rounds(rnd, end_round, k=LOOKAHEAD):
    return [r for r in range(rnd, rnd + k) if r <= end_round] if rnd is not None else []


def board(ex):
    """The towers standing, as plain records the forecast reads."""
    return [SimpleNamespace(tid=p.tid, kind=p.kind, tiers=tuple(p.tiers), x=p.x, y=p.y)
            for p in ex.g.towers.values()]


def options(ex, cash):
    """Every purchase the cash allows (see the module docstring), cheapest
    first, at most MAX_OPTIONS."""
    now = board(ex)
    out = []
    for p, tiers, cost in ex.upgrade_choices(past_plan=True):
        if cost > cash:
            continue
        after = [SimpleNamespace(**{**vars(t), "tiers": tuple(tiers)}) if t.tid == p.tid else t for t in now]
        out.append(Option(f"upgrade {p.tid} -> {'-'.join(map(str, tiers))}", cost,
                          {"do": "upgrade", "id": p.tid, "to": "-".join(map(str, tiers))}, after))
    if not ex.at_tower_cap():
        kinds = {t.kind for t in now if t.kind != "hero" and t.kind not in NOT_DAMAGE}
        main = ex._main_kind()
        if main and main not in NOT_DAMAGE:
            kinds.add(main)
        for kind in sorted(kinds):
            if not ex.kind_allowed(kind):
                continue
            cost = ex.g.price(kind)
            if cost is None or cost > cash:
                continue
            step = {"do": "place", "kind": kind, "role": "dps", "segment": [0.2, 1.0]}
            spots = ex.pick_spots(kind, step, n=1)
            if not spots:
                continue
            fx, fy = ex.m.cell_to_frac(spots[0][0], spots[0][1])
            new = SimpleNamespace(tid=f"_new_{kind}", kind=kind, tiers=(0, 0, 0), x=fx, y=fy)
            out.append(Option(f"another {kind}", cost, step, now + [new]))
    out.sort(key=lambda o: o.cost)
    return out[:MAX_OPTIONS]


def best(ex, forecast, cash, rnd, end_round):
    """("safe", None) when the look-ahead holds - nothing leaks at half
    strength, so every round's margin is at least TARGET_MARGIN - or cannot
    be rated; ("wait", None) when nothing the cash buys helps yet; else
    ("buy", (Option, its worst round, that round's margin before, after))
    for the purchase that saves the most lives per dollar."""
    rounds = lookahead_rounds(rnd, end_round)
    half = 1.0 / TARGET_MARGIN
    # only the rounds that leak at half strength can gain (and each skipped
    # round saves a simulation per option)
    by_round = forecast.leaks(board(ex), rounds, half, per_round=True) or {}
    rounds_rated = [r for r, lost in by_round.items() if lost > 0]
    base = sum(by_round[r] for r in rounds_rated)
    if not base:
        return "safe", None
    pick = None
    for o in options(ex, cash):
        leak = forecast.leaks(o.towers, rounds_rated, half)
        if leak is None:
            continue
        saved = base - leak
        if saved < MIN_SAVED:
            continue
        value = saved / max(o.cost, 1.0)
        if pick is None or value > pick[0]:
            pick = (value, o)
    if pick is None:
        return "wait", None
    worst = max(rounds_rated, key=by_round.get)    # for the log: the round losing most
    before, after = forecast.margin(board(ex), worst), forecast.margin(pick[1].towers, worst)
    return "buy", (pick[1], worst, before, after)


def buy_best(ex, forecast, cash, rnd, end_round):
    """Buy the best purchase (see best()). Returns 'bought', 'safe' (the
    look-ahead holds: stop), 'wait' (nothing affordable helps yet: more cash
    may) or 'failed' (the purchase did not go through)."""
    status, found = best(ex, forecast, cash, rnd, end_round)
    if status != "buy":
        return status
    o, worst, before, after = found
    r = ex.try_step(dict(o.step), cash, rnd)
    if r in ("bought", "progress"):
        log.warning("reinforce: %s ($%d) - round %d, the weakest ahead, goes %.2f -> %.2f in the model",
                    o.what, o.cost, worst, before or 0.0, after or 0.0)
        return "bought"
    return "failed"
