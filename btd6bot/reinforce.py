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
    spot for it - rated at the crosspath the cash can grow it into (grow),
    since a bare tower adds nothing to a late round in the model.

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

import contextlib
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace

from . import towers as T

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
MIN_LIFT = 0.01        # a purchase lifting the weakest round less than this does not
                       # outbid a plan step that is waiting for cash (waiting_plan_step)


def crisis_now(forecast, ex, rnd, lives_dropped=None):
    """Is the round being played in trouble? True when the damage model rates
    round rnd or the next one under WEAK_MARGIN, or lives fell this round
    (lives_dropped; None: asked of the executor, Executor.lives_fell_lately).

    MIN_LIFT, waiting_plan_step and save_target judge a purchase against the
    weakest round of the whole look-ahead, never the round being played, so
    cash stayed put while that round was lost: Bazaar Reverse (2026-11-05)
    kept $7k-20k "for plan step a1 0-4-2" from round 39 while round 51 was
    rated 0.44 and lost there; Bloonarius Prime ABR was wiped at round 40
    with $3,901 unspent. While this is true best() measures a purchase's
    lift on the round being played too (lift) and lets go of cash held for
    a later step down to what income rebuilds before that step (release)."""
    if lives_dropped is None:
        fell = getattr(ex, "lives_fell_lately", None)
        lives_dropped = bool(fell(rnd, 1)) if callable(fell) else False
    if lives_dropped:
        return True
    if rnd is None:
        return False
    margins = [m for m in (forecast.margin(board(ex), r) for r in (rnd, rnd + 1)) if m is not None]
    return bool(margins) and min(margins) < WEAK_MARGIN


def lift(forecast, before_towers, after_towers, rnd, worst, crisis):
    """(before, after): the margin a purchase is judged on. Normally round
    `worst`'s; in a crisis (crisis_now) the lowest of the round being
    played, the next one and `worst` - so a purchase that lifts the round
    being played while `worst` does not move still counts, and one that
    only helps a round already safer than the weakest does not."""
    rounds = [worst] + ([r for r in (rnd, rnd + 1) if r is not None and r != worst] if crisis else [])

    def low(towers):
        ms = [m for m in (forecast.margin(towers, r) for r in rounds) if m is not None]
        return min(ms) if ms else None
    return low(before_towers), low(after_towers)


def release(ex, held, due_round, rnd):
    """What is left to hold of `held` dollars needed by due_round once the
    income until then is counted (Executor.income_until): the rest may be
    spent now. Unknown income: all of it stays held."""
    income_until = getattr(ex, "income_until", None)
    income = income_until(due_round, rnd) if callable(income_until) and due_round is not None else 0.0
    return max(0.0, held - (income or 0.0))


def _why(ex, source, reason):
    """ex.why(source, reason) for the journal, or nothing for an executor
    without it (test fakes)."""
    why = getattr(ex, "why", None)
    return why(source, reason) if callable(why) else contextlib.nullcontext()


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


def options(ex, cash, kinds=None):
    """Every purchase the cash allows (see the module docstring), cheapest
    first, at most MAX_OPTIONS.

    kinds: the tower kinds offered as "another <kind>" - by default the
    damage kinds standing plus the plan's main kind. With an explicit list
    only those placements are offered, and no upgrades (new_kind_options)."""
    now = board(ex)
    out = []
    if kinds is None:
        for p, tiers, cost in ex.upgrade_choices(past_plan=True):
            if cost > cash:
                continue
            after = [SimpleNamespace(**{**vars(t), "tiers": tuple(tiers)}) if t.tid == p.tid else t for t in now]
            out.append(Option(f"upgrade {p.tid} -> {'-'.join(map(str, tiers))}", cost,
                              {"do": "upgrade", "id": p.tid, "to": "-".join(map(str, tiers))}, after))
    if not ex.at_tower_cap():
        if kinds is None:
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
            # a placement the executor has already given up would only come
            # back 'skip' - and, rated best, crowd out every other purchase
            # (Water Park ABR, see Executor.place_held_back)
            held_back = getattr(ex, "place_held_back", None)
            if held_back is not None and held_back(step):
                continue
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
    for the purchase that saves the most lives per dollar.

    While the round being played is in trouble (crisis_now) neither a
    waiting plan step nor a dearer purchase holds more of the cash than
    income cannot rebuild before it is needed (release), and a purchase's
    lift is judged on the round being played too (lift)."""
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
    tried = grow(ex, forecast, options(ex, cash), cash, worst)
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
    # the two fallbacks below spend a big idle bank on purpose, even when
    # the model sees no gain: the plan-step check further down leaves them be
    blind = pick is None and crisis and cash >= BLIND_SPEND_CASH
    if pick is None and crisis and cash >= BLIND_SPEND_CASH:
        pick = strongest(forecast, new_kind_options(ex, forecast, cash, worst), worst, before)
        if pick:
            log.warning("reinforce: nothing standing can grow to help round %d (%.2f) - trying a "
                        "tower kind not on the board yet, %s", worst, before or 0.0, pick[1].what)
    if pick is None and crisis and cash >= BLIND_SPEND_CASH:
        pick = dearest_upgrade(tried)
        if pick:
            log.warning("reinforce: the model sees nothing that helps round %d (%.2f) - spending "
                        "$%d anyway on the dearest upgrade, %s", worst, before or 0.0, cash, pick[1].what)
    after = forecast.margin(pick[1].towers, worst) if pick else None
    now = crisis_now(forecast, ex, rnd)
    plan_wait = waiting_plan_step(ex, cash)
    if pick is not None and not blind and plan_wait is not None:
        step, cost = plan_wait
        judged_before, judged_after = lift(forecast, board(ex), pick[1].towers, rnd, worst, now)
        moved = (judged_after or 0.0) - (judged_before or 0.0)
        # in a crisis the plan step keeps only what income cannot rebuild
        # before its round (its own `round`, else the next one)
        keep = release(ex, cost, step.get("round") or rnd + 1, rnd) if now else cost
        if (cash - pick[1].cost < keep
                and plan_keeps_claim(forecast, ex, step, cost, cash, rnd, worst, now, pick[1], moved)):
            log.info("reinforce: %s would move round %d only %.2f -> %.2f - the cash stays for plan "
                     "step %s ($%d)", pick[1].what, worst, before or 0.0, after or 0.0, step, cost)
            return "wait", None
    if crisis and (after is None or after < 1.0) and not dies_first(forecast, ex, rnd, worst, lives):
        # Nothing affordable stops the leak: spending now only delays the
        # purchase that would (see save_target).
        target = save_target(forecast, ex, cash, rnd, worst)
        if (target is not None and now and pick is not None
                and cash - pick[1].cost >= release(ex, target[0].cost, worst, rnd)):
            # the round being played is in trouble too, and income rebuilds
            # what the dearer purchase still needs by round `worst`: buy now
            log.info("reinforce: round %d is in trouble - buying %s now; income pays for %s ($%d) "
                     "by round %d", rnd, pick[1].what, target[0].what, target[0].cost, worst)
            target = None
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


def waiting_plan_step(ex, cash):
    """(step, cost) for the strategy's current plan step when it is waiting
    for cash - it costs more than `cash` - else None.

    Reinforce and the plan draw on the same bank. On Castle Revenge
    Impoppable and Haunted Half Cash (2026-11-04) the plan's next step was
    a Sun Avatar (s -> 3-0-2) while reinforce kept buying Super Monkey
    tiers, spikes and ninja tiers that the model itself rated "0.52 ->
    0.52": each one saved half a life at half strength in some other round,
    none lifted the weakest round, and the Sun Avatar never came before the
    MOAB-class round that ended both games. best() leaves the cash to such
    a step unless a purchase lifts the weakest round by MIN_LIFT or more."""
    plan, idx = getattr(ex, "plan", None), getattr(ex, "idx", None)
    if not plan or idx is None or idx >= len(plan):
        return None
    step = plan[idx]
    if step.get("do") not in ("place", "upgrade"):
        return None
    try:
        cost = ex._first_step_cost(step)
    except Exception:       # a step the executor cannot price (tower gone): no claim on the cash
        return None
    if cost is None or cost == float("inf") or cost <= cash:
        return None
    return step, cost


def plan_keeps_claim(forecast, ex, step, cost, cash, rnd, worst, crisis, pick, moved):
    """Does the plan step waiting for cash keep its claim on the bank against
    `pick`, the reinforcement that would eat into it (and moves the judged
    round by `moved`)?

    The first rule - any purchase lifting the weakest round by MIN_LIFT or
    more outbids the step - judged the purchase alone, never the step. Two
    games were lost that way on 2026-11-05:

      * Ancient Portal Impoppable saved toward Perma-Spike (sp1 2-0-5,
        $36,000, the plan's answer to rounds 95-100) from round 70 on, and
        at round 88 reinforce spent the $27,284 in the bank on a Super
        Monkey tier that moved round 96 from 0.39 to 0.42. Round 94 was lost
        with $17,562 in hand and the spike factory still 2-0-4.
      * Quad ABR kept $10,000-20,500 "for plan step b1 -> 5-0-2" (Glaive
        Lord, $35,100) from round 54 while the ceramic rush of round 63 was
        rated 0.34-0.47; no income could pay the step before that round,
        and the game was lost there with the cash in the bank.

    So the step keeps its claim only when both hold:
      1. it can be paid before round `worst` from the cash in hand and the
         income until then (payable_by; unknown income: assumed payable);
      2. rated in the damage model like any other purchase (plan_option), it
         lifts the judged rounds at least as much as the pick does - a pick
         under MIN_LIFT never outbids it, and a step the model cannot rate
         (tower gone, no spot) keeps the old MIN_LIFT bar."""
    if payable_by(ex, cost, cash, worst, rnd) is False:
        log.info("reinforce: plan step %s ($%d) cannot be paid before round %d from $%d and the income "
                 "until then - it holds no cash", step, cost, worst, cash)
        return False
    if moved < MIN_LIFT:
        return True
    option = plan_option(ex, step, cost)
    if option is None:
        return False
    step_before, step_after = lift(forecast, board(ex), option.towers, rnd, worst, crisis)
    step_moved = (step_after or 0.0) - (step_before or 0.0)
    if step_moved < moved:
        log.info("reinforce: %s ($%d) would move round %d only %.2f -> %.2f, less than %s does "
                 "(%.2f) - the purchase comes first", option.what, cost, worst, step_before or 0.0,
                 step_after or 0.0, pick.what, moved)
        return False
    return True


def payable_by(ex, cost, cash, due_round, rnd):
    """Can `cost` be paid before due_round from `cash` and the income until
    then (Executor.income_until)? None when the executor has no income figure
    (test fakes) or the rounds are unknown: the caller assumes it can."""
    income_until = getattr(ex, "income_until", None)
    if not callable(income_until) or rnd is None or due_round is None:
        return None
    income = income_until(due_round, rnd) if due_round > rnd else 0.0
    return cash + (income or 0.0) >= cost


def plan_option(ex, step, cost):
    """The waiting plan step as an Option the damage model can rate: the
    board after the one tier (Executor._next_path: the tier its cost buys)
    or placement it is saving for. None when it cannot be simulated: the
    tower is gone, the placement has no spot, or the executor cannot say
    which tier comes next (test fakes)."""
    now = board(ex)
    if step.get("do") == "upgrade":
        p = ex.g.towers.get(step.get("id"))
        next_path = getattr(ex, "_next_path", None)
        if p is None or not callable(next_path):
            return None
        try:
            nxt = next_path(p, [int(c) for c in str(step["to"]).split("-")])
        except Exception:
            return None
        if not nxt:
            return None
        tiers = list(p.tiers)
        tiers[nxt[0] - 1] += 1
        after = [SimpleNamespace(**{**vars(t), "tiers": tuple(tiers)}) if t.tid == p.tid else t for t in now]
        return Option(f"plan step upgrade {p.tid} -> {'-'.join(map(str, tiers))}", cost, step, after)
    if step.get("do") == "place":
        kind = step.get("kind")
        if kind is None or ex.at_tower_cap():
            return None
        spots = ex.pick_spots(kind, step, n=1)
        if not spots:
            return None
        fx, fy = ex.m.cell_to_frac(spots[0][0], spots[0][1])
        new = SimpleNamespace(tid=step.get("id") or f"_plan_{kind}", kind=kind, tiers=(0, 0, 0), x=fx, y=fy)
        return Option(f"plan step place {kind}", cost, step, now + [new])
    return None


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


def new_kind_options(ex, forecast, cash, rnd):
    """"another <kind>" purchases for every damage kind the game allows that
    is not standing yet (options() only offers the kinds already on the
    board): the crisis fallback when nothing standing can grow.

    Spice Islands Impoppable (2026-11-04): the land near the track ran out
    by round 47 (ninja, super and spike steps all given up, "none in reach
    of the track"), every standing tower was at its last tier, and from
    round 63 to the loss at round 98 reinforce logged "nothing $X buys
    helps (0 purchases tried)" while the bank grew to $161,626 - on a map
    that is mostly water, where a sub or a buccaneer would still have fit."""
    standing = {p.kind for p in ex.g.towers.values()}
    kinds = [k for k in T.TOWERS if k not in standing and k not in NOT_DAMAGE
             and k != "hero" and ex.kind_allowed(k)]
    return grow(ex, forecast, options(ex, cash, kinds=kinds), cash, rnd)


def grow(ex, forecast, opts, cash, rnd):
    """The options with every "another <kind>" placement rated at the best
    crosspath the bank could grow it into (grown()) for round `rnd`;
    upgrades pass through unchanged.

    A bare tower barely scratches a late round (a 0-0-0 sub adds nothing
    to Spice Islands' round 98 in the model, a 2-0-4 one +0.05), and the
    upgrades only become purchases once it stands - so rated bare, a
    placement never looks like the answer. Bazaar ABR (2026-11-05) rated
    round 63 at 0.12 from round 54 with $11-21k idle and logged "another
    ninja would move round 63 only 0.12 -> 0.12" while $5,800 bought a
    4-0-2 Bloonjitsu ninja; the game ended at round 63.

    The grown option costs what the grown tower costs in all (the lives it
    saves are judged per dollar against single upgrades), and among
    crosspaths the model rates alike the cheapest is kept. What is bought is
    still just the placement, and its upgrades follow through the normal
    options once it stands."""
    family = _price_family(ex)
    out = []
    for o in opts:
        if o.step.get("do") != "place":
            out.append(o)
            continue
        *rest, new = o.towers
        rated = []
        for tiers in grown(ex, new.kind, cash) | {(0, 0, 0)}:     # bare: when growing adds nothing
            m = forecast.margin(rest + [SimpleNamespace(**{**vars(new), "tiers": tiers})], rnd)
            if m is not None:
                rated.append((m, -T.total_cost(new.kind, tiers, family), tiers))
        if rated:
            m, neg_cost, tiers = max(rated)
            new = SimpleNamespace(**{**vars(new), "tiers": tiers})
            if any(tiers):
                o = Option(f"{o.what} (to grow to {'-'.join(map(str, tiers))})", -neg_cost,
                           o.step, rest + [new])
        out.append(o)
    return out


def _price_family(ex):
    """The price family (hard, impoppable, ...) of the executor's mode."""
    from .strategy import PRICE_FAMILY      # here: strategy imports this module
    return PRICE_FAMILY.get(getattr(ex, "mode", None), "hard")


# The crosspaths a new tower is rated at (grown): each path as the main one,
# with either other path as its side path.
CROSSPATHS = [(5, 2, 0), (5, 0, 2), (2, 5, 0), (0, 5, 2), (2, 0, 5), (0, 2, 5)]


def grown(ex, kind, cash):
    """The tiers a new tower of `kind` reaches toward each of CROSSPATHS
    with `cash` (its own price included): the main path to tier 2, the side
    path to its target, then the main path on - as far as the cash goes and
    the account's tower XP has unlocked (tiers 1-2 are always open)."""
    family = _price_family(ex)
    account = getattr(ex, "account", None)
    unlocked = account.upgrades(kind) if account else (5, 5, 5)
    left = cash - T.tower_cost(kind, family)
    reached = set()
    for target in CROSSPATHS:
        main = target.index(5)
        side = next(i for i in range(3) if i != main and target[i])
        order = [main] * 2 + [side] * target[side] + [main] * 3
        t, budget = [0, 0, 0], left
        for path in order:
            tier = t[path] + 1
            if tier > 2 and tier > unlocked[path]:
                break
            cost = T.upgrade_cost(kind, path + 1, tier, family)
            if cost > budget:
                break
            budget -= cost
            t[path] = tier
        reached.add(tuple(t))
    return reached


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
    # part of the cash the executor keeps for a far threat (Executor._hold_for)
    held = getattr(ex, "held_cash", 0) or 0
    if held and cash is not None:
        cash = max(0, cash - held)
    status, found = best(ex, forecast, cash, rnd, end_round, lives)
    if status != "buy":
        return status
    o, worst, before, after = found
    with _why(ex, "reinforce", f"{o.what}: round {worst} {before or 0.0:.2f}->{after or 0.0:.2f}"):
        r = ex.try_step(dict(o.step), cash, rnd)
    if r in ("bought", "progress"):
        log.warning("reinforce: %s ($%d) - round %d, the weakest ahead, goes %.2f -> %.2f in the model",
                    o.what, o.cost, worst, before or 0.0, after or 0.0)
        return "bought"
    log.info("reinforce: %s ($%d) did not go through (%s)", o.what, o.cost, r)
    return "failed"
