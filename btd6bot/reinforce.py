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
bought - or, when the worst round would leak even at full strength
(margin under 1), the one that saves the most lives. One purchase per call; Match calls again until the look-ahead is
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
SAVE_LEAD = 2          # rounds of income needed before saving for a dearer purchase pays
SAVE_REACH = 3.0       # ... and it may cost at most this many times the cash in hand
BLIND_SPEND_CASH = 10_000   # cash idle in a crisis the model sees no use for: spent anyway


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
    return trim(out)


def trim(out, k=MAX_OPTIONS):
    """At most k of the cost-sorted options: the cheapest half and the
    dearest half. Keeping only the cheapest k hid every strong purchase on
    a crowded board: Spillway Magic Monkeys Only (2026-10-24) had 14 ninjas
    and 5 wizards, so their first tiers filled the list, and the bot bought
    $270 wizards (round 54 rated 0.24 -> 0.26) with $19-27k in the bank
    until it lost at round 60."""
    if len(out) <= k:
        return out
    return out[:k - k // 2] + out[len(out) - k // 2:]


def best(ex, forecast, cash, rnd, end_round, lives=None):
    """("safe", None) when the look-ahead holds - nothing leaks at half
    strength, so every round's margin is at least TARGET_MARGIN - or cannot
    be rated; ("wait", None) when nothing the cash buys helps yet; ("save",
    (Option, ...)) when the worst round leaks even at full strength, nothing
    affordable lifts it over 1, a dearer purchase would (save_target) and
    the rounds before it do not cost the `lives` left (dies_first); else
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
    worst = max(rounds_rated, key=by_round.get)    # the round losing most
    before = forecast.margin(board(ex), worst)
    # Under margin 1 the worst round leaks even at full strength: the game
    # is at stake, so the purchase saving the most lives wins, not the most
    # per dollar (which kept buying the cheapest small step, see trim()).
    crisis = before is not None and before < 1.0
    pick = None
    tried = options(ex, cash)
    for o in tried:
        leak = forecast.leaks(o.towers, rounds_rated, half)
        if leak is None:
            continue
        saved = base - leak
        if saved < MIN_SAVED:
            continue
        value = saved if crisis else saved / max(o.cost, 1.0)
        if pick is None or value > pick[0]:
            pick = (value, o)
    if pick is None and crisis:
        pick = strongest(forecast, tried, worst, before)
    if pick is None and crisis and cash >= BLIND_SPEND_CASH:
        pick = dearest_upgrade(tried)
        if pick:
            log.warning("reinforce: the model sees nothing that helps round %d (%.2f) - spending "
                        "$%d anyway on the dearest upgrade, %s", worst, before or 0.0, cash, pick[1].what)
    after = forecast.margin(pick[1].towers, worst) if pick else None
    if crisis and (after is None or after < 1.0) and not dies_first(forecast, ex, rnd, worst, lives):
        # Nothing affordable stops the leak: spending now only delays the
        # purchase that would (see save_target).
        target = save_target(forecast, ex, cash, rnd, worst)
        if target is not None:
            o, lifted = target
            log.info("reinforce: saving for %s ($%d) - round %d goes %.2f -> %.2f; nothing $%d buys "
                     "gets it over 1", o.what, o.cost, worst, before or 0.0, lifted, cash)
            return "save", (o, worst, before, lifted)
    if pick is None:
        # said out loud: on Cornfield Medium (2026-11-03) this stayed silent
        # for ten rounds while $25k sat idle, and the loss had to be worked
        # out offline
        log.info("reinforce: nothing $%d buys helps round %d (%.2f; %d purchases tried)",
                 cash, worst, before or 0.0, len(tried))
        return "wait", None
    return "buy", (pick[1], worst, before, after)


def strongest(forecast, tried, worst, before):
    """(value, Option) for the purchase that lifts round `worst`'s margin
    the most at full strength, or None when none lifts it at all.

    The crisis fallback when no purchase saves MIN_SAVED lives at half
    strength: once a round is far past saving at half strength (a ZOMG
    leaks whole either way), that count no longer moves. Infernal Double
    HP MOABs (2026-11-03) rated round 79 at 0.25 for ten rounds and sat on
    up to $77,100 with "nothing buys helps" - then lost there."""
    found = None
    for o in tried:
        m = forecast.margin(o.towers, worst)
        if m is not None and m > (before or 0.0) + 0.01 and (found is None or m > found[0]):
            found = (m, o)
    return found


def dearest_upgrade(tried):
    """(cost, Option) for the dearest upgrade among the purchases tried, or
    None: the last resort when a crisis round lies ahead, BLIND_SPEND_CASH or
    more sits in the bank and the model rates no purchase as helping at all.
    The model misses what it does not simulate (a tier 5's ability, a
    buff's reach, a map's own mechanics), and an idle bank never helps:
    Infernal Double HP (2026-11-03) lost round 79 with $77,100 unspent. A
    higher tier of a standing tower is the safest bet - it adds to what
    already reaches the track."""
    ups = [o for o in tried if o.step.get("do") == "upgrade"]
    if not ups:
        return None
    o = max(ups, key=lambda o: o.cost)
    return o.cost, o


def dies_first(forecast, ex, rnd, worst, lives):
    """True when the rounds before `worst` already cost the lives left at
    full strength: saving for `worst` would lose the game before it comes.

    Cargo Double HP MOABs (2026-11-03) saved $29,951 toward a $45,900 Ace
    upgrade for round 79 while round 75 itself was rated 0.27 - and was
    lost at round 75 with the cash in the bank. Without a lives count this
    cannot be judged and saving stays allowed."""
    if lives is None or rnd is None or worst <= rnd:
        return False
    lost = forecast.leaks(board(ex), list(range(rnd, worst)), 1.0)
    return lost is not None and lost >= lives


def save_target(forecast, ex, cash, rnd, worst):
    """(Option, margin after) for the cheapest purchase the cash cannot buy
    yet that gets round `worst` to margin 1 or better - or None.

    Peninsula Medium (2026-10-27) rated round 40 at 0.06 from round 37 on,
    and reinforcing kept buying $1,000 sub upgrades that each saved a few
    lives at half strength but left that round at 0.06; the cash for an
    upgrade that would have held it never piled up. Saving makes sense only
    while the round is SAVE_LEAD or more rounds away (income needs rounds to
    arrive) and the target costs at most SAVE_REACH times the cash in hand
    (further than that it would not come in time)."""
    if rnd is None or worst - rnd < SAVE_LEAD or cash <= 0:
        return None
    for o in options(ex, cash * SAVE_REACH):       # cheapest first
        if o.cost <= cash:
            continue
        m = forecast.margin(o.towers, worst)
        if m is not None and m >= 1.0:
            return o, m
    return None


def buy_best(ex, forecast, cash, rnd, end_round, lives=None):
    """Buy the best purchase (see best()). Returns 'bought', 'safe' (the
    look-ahead holds: stop), 'wait' (nothing affordable helps yet: more cash
    may), 'save' (keep the cash for a dearer purchase that does help) or
    'failed' (the purchase did not go through)."""
    status, found = best(ex, forecast, cash, rnd, end_round, lives)
    if status != "buy":
        return status
    o, worst, before, after = found
    r = ex.try_step(dict(o.step), cash, rnd)
    if r in ("bought", "progress"):
        log.warning("reinforce: %s ($%d) - round %d, the weakest ahead, goes %.2f -> %.2f in the model",
                    o.what, o.cost, worst, before or 0.0, after or 0.0)
        return "bought"
    log.info("reinforce: %s ($%d) did not go through (%s)", o.what, o.cost, r)
    return "failed"
