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

A purchase rated by the crosspath a standing tower grows into ("upgrade b1
-> 1-1-0 (to grow to 4-2-0)", grow_standing) is a goal, not one tier: its
rating is the whole path's, so buy_best buys the path's tiers one after
another while the cash it was rated on lasts, and an unfinished goal stays
on offer at the next looks (goal_option) until it stands, is overtaken, or
cannot come before its round any more.

Under a click budget (Apopalypse: clicktime.py) a purchase costs seconds as
well as dollars, and the lives it saves are weighed against both (worth()).
"""
from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

from . import clicktime as CT
from . import towers as T
from .forecast import CRISIS_MARGIN

log = logging.getLogger("reinforce")

LOOKAHEAD = 10         # rounds rated: the one being played and the next nine
WEAK_MARGIN = 1.5      # worst look-ahead margin under this: reinforce
TARGET_MARGIN = 2.0    # margin the defence is reinforced up to
MIN_SAVED = 0.5        # lives (at half strength) a purchase must save to be worth it
MAX_OPTIONS = 20       # purchases tried per call
NOT_DAMAGE = ("village", "alchemist", "farm")
SAVE_LEAD = 2          # rounds of income needed before saving for a dearer purchase pays
SAVE_REACH = 3.0       # ... and it may cost at most this many times the cash in hand
CONTINUOUS_SAVE_ROUNDS = 2   # under continuous sends: payable from the income of this many rounds
BLIND_SPEND_CASH = 10_000   # cash idle in a crisis the model sees no use for: spent anyway
ENDING_LOOKAHEAD = 3   # rounds after the one being played searched for a game-ending round
MIN_LIFT = 0.01        # a purchase lifting the weakest round less than this does not
                       # outbid a plan step that is waiting for cash (waiting_plan_step)
# Seconds one look (best) may spend rating purchases before it goes with the
# best found so far. Late rounds make every model margin dear (~0.2 s for
# round 98), and grow() rates each crosspath of each placement and of each
# standing tower behind it: on Polyphemus Impoppable (2026-11-05, loss case
# 20261105_192111) one look took 28 s, so the 20 s hold before round 98 ran
# out with a single $9,000 purchase made, and the next look, started with
# $13,990 as round 98 began, finished 30 s later - after the defeat. The
# match loop is blocked while a look runs: no other purchase, no ability,
# no Play. Looks earlier in a game take 1-3 s and never reach this.
#
# The budget covers the whole look, every stage that rates something, not
# only grow(). X Factor Impoppable (2026-11-10 20:18-21:13, one life, 30-40
# towers from round 80) logged 73 loop stalls of 16-48 s (~2,500 s of a
# 55-minute game) and "the 6 s look budget ran out while rating growth
# paths" 28 times: grow stopped at 6 s, but rating each purchase's leak,
# then strongest() and plan_claim_in_crisis() re-rating every purchase at
# the round in danger, ran on unbounded (offline, the round-85 board: 37 s,
# of it grow 6 s, the leak ratings 10 s, plan_claim_in_crisis 16 s). Now
# every such stage stops at the budget and the look answers "busy"
# (LookBudget); the forecast remembers its answers per board
# (forecast._memo), so the next look on the same board starts where this
# one stopped, and the purchase chosen is the one an unbounded look picks.
LOOK_BUDGET_S = 6.0
# Passes in a row a look may answer "busy" before its next pass chooses from
# what has been rated (LookBudget.settle). Remembering the ratings did not
# by itself make the looks converge. On Water Park Impoppable (2026-11-11
# 02:26:47-02:27:54, round 88, 28 towers) ten passes in a row ran out "while
# rating growth paths" and none chose anything while $7.9k-19.6k sat idle;
# the game was lost on round 91. Two things kept it from finishing:
#   * the bank grew between passes, and grow() rates each placement at the
#     crosspath *the cash* can grow it into (grown) - every pass asked about
#     new boards the forecast had never seen. The look's cash is now pinned
#     while it is unfinished (LookPin), so every pass asks the same questions.
#   * even with the cash pinned, the whole look is ~60 s of ratings on that
#     board (67 growth-path margins at ~0.7 s each), ten passes of 6 s while
#     the round goes on. So after MAX_BUSY_LOOKS busy passes the next one
#     goes with what it has: the growth paths from what was rated, then the
#     purchases' leaks for its own budget, choosing among those rated.
# A look therefore answers on its (MAX_BUSY_LOOKS + 1)-th pass at the latest.
MAX_BUSY_LOOKS = 3


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
    a later step down to what income rebuilds before that step (release).
    A round in real danger, rated under forecast.CRISIS_MARGIN, is
    danger_round's narrower question."""
    if lives_dropped is None:
        lives_dropped = _lives_fell(ex, rnd)
    if lives_dropped:
        return True
    if rnd is None:
        return False
    margins = [m for m in (forecast.margin(board(ex), r) for r in (rnd, rnd + 1)) if m is not None]
    return bool(margins) and min(margins) < WEAK_MARGIN


def danger_round(forecast, ex, rnd, lives_dropped=None, lives=None):
    """The round the game is at stake in right now, or None: rnd when lives
    fell this round, else the first of rnd and rnd + 1 the damage model
    rates under forecast.CRISIS_MARGIN - the band Match calls a crisis
    round (Match._in_crisis, _hold_for_crisis), where rounds lost lives
    11.8% of the time against 2.8% up to a margin of 1 (forecast.py) - or
    rates under 1 while the leak it expects would cost half the `lives`
    left (forecast.lethal_leak; Pat's Pond ABR 2026-11-05: round 54 rated
    0.58 took all 74 lives with $15,243 kept for a $21,600 plan step).
    best() measures a waiting plan step's reach against this round
    (plan_claim_in_crisis): a step that cannot be paid before it holds
    nothing against a purchase that lifts it.

    Narrower than crisis_now on purpose. The first version of that rule
    used crisis_now's WEAK_MARGIN (1.5), and a step short of cash can never
    be paid before the round being played, so the step lost its whole
    claim in every weak-but-holding round: on Ancient Portal Impoppable
    (2026-11-05) rounds 85-93 were rated 0.58-0.96 at their start and all
    held, while the Perma-Spike was still payable before the weakest round
    - exactly the saving 094f8de and 7919935 protect. Under CRISIS_MARGIN
    only round 94 (0.45, the round lost) counts."""
    if lives_dropped is None:
        lives_dropped = _lives_fell(ex, rnd)
    if lives_dropped:
        return rnd
    if rnd is None:
        return None
    lethal = getattr(forecast, "lethal_leak", None)    # test fakes without it: the margin alone
    towers = board(ex)
    for r in (rnd, rnd + 1):
        m = forecast.margin(towers, r)
        if m is None:
            continue
        if lethal is None:
            crisis = m < CRISIS_MARGIN
        else:
            crisis = forecast.is_crisis(m, lives, lethal(towers, r, m))
        if crisis:
            return r
    return None


def _lives_fell(ex, rnd):
    """Did lives fall in round rnd? Asked of the executor
    (Executor.lives_fell_lately); False for one without the record (test
    fakes)."""
    fell = getattr(ex, "lives_fell_lately", None)
    return bool(fell(rnd, 1)) if callable(fell) else False


def lift(forecast, before_towers, after_towers, rnd, worst, crisis):
    """(before, after): the margin a purchase is judged on. Normally round
    `worst`'s; in a crisis (crisis_now) the lowest of the round being
    played, the next one and `worst` - so a purchase that lifts the round
    being played while `worst` does not move still counts, and one that
    only helps a round already safer than the weakest does not."""
    rounds = judged_rounds(rnd, worst, crisis)

    def low(towers):
        ms = [m for m in (forecast.margin(towers, r) for r in rounds) if m is not None]
        return min(ms) if ms else None
    return low(before_towers), low(after_towers)


def judged_rounds(rnd, worst, crisis):
    """The rounds a purchase is judged on (lift, saved_lives): `worst`, plus
    in a crisis the round being played and the next one."""
    return [worst] + ([r for r in (rnd, rnd + 1) if r is not None and r != worst] if crisis else [])


def saved_lives(forecast, before_towers, after_towers, rounds):
    """Lives a purchase saves over `rounds` at full strength: the model's
    leak with `before_towers` minus the leak with `after_towers`. None when
    either board cannot be rated. Unlike a margin, the leak moves with every
    purchase, also for a round far below the margin floor (dps_model.at_floor)."""
    before = forecast.leaks(before_towers, rounds, 1.0)
    after = forecast.leaks(after_towers, rounds, 1.0)
    if before is None or after is None:
        return None
    return before - after


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
    # for a tower rated at the crosspath it grows into: the upgrade step to
    # that whole crosspath ({"do": "upgrade", "id": ..., "to": "4-2-0"}),
    # which buy_best follows on after the first tier (follow_goal)
    goal: dict | None = None


def _past(deadline):
    """True once a look's time budget has run out: `deadline` is a
    LookBudget (best) or a plain time.monotonic() deadline; never for None
    (no budget)."""
    if deadline is None:
        return False
    if isinstance(deadline, LookBudget):
        return deadline.past()
    return time.monotonic() > deadline


def look_deadline(seconds=None):
    """The time.monotonic() deadline of a look starting now: LOOK_BUDGET_S
    (read when called, so tests may change it) or `seconds` from now."""
    return time.monotonic() + (LOOK_BUDGET_S if seconds is None else seconds)


class LookBudget:
    """The time budget of one look (best): a time.monotonic() deadline, and
    whether a stage was cut short by it (`cut`, the stage's name).

    A look cut short does not buy from what it had rated (best answers
    "busy"): the forecast remembers every rating (forecast._memo), so the
    next look on the same board goes on where this one stopped, and the
    purchase finally chosen is the one an unbounded look would choose.
    Bought from a partial rating, it would depend on which stage ran out.

    The budget never cuts a look that has not yet rated anything new
    (forecast.computed has not moved since the look began): otherwise a
    look whose budget was spent on the board's own ratings, or one started
    with too little time, would never get further. Forecasts without the
    count (test fakes) are cut at the deadline alone.

    settle: this is the last pass of a look that has been cut short
    MAX_BUSY_LOOKS times. Its stages still stop at the deadline, but the
    look then chooses from what it and the passes before it rated instead
    of answering "busy" (cuts() is False), and the growth paths come only
    from ratings already made (memo_only): they were the stage that ate
    every earlier pass."""

    def __init__(self, deadline, forecast=None, settle=False):
        self.deadline = deadline
        self.forecast = forecast
        self.start_count = getattr(forecast, "computed", None)
        self.cut = None
        self.settle = settle

    def cuts(self):
        """Does the stage that just ran make the look answer "busy"? True
        when a stage was cut short, except on a settling pass."""
        return self.cut is not None and not self.settle

    def past(self):
        if self.deadline is None or time.monotonic() <= self.deadline:
            return False
        count = getattr(self.forecast, "computed", None)
        if self.start_count is not None and count == self.start_count:
            return False            # nothing new rated yet: no progress, no cut
        return True

    def over(self, stage, done=None, total=None):
        """past(), noted and said once a look: True when `stage` must stop."""
        if not self.past():
            return False
        if self.cut is None:
            self.cut = stage
            rated = f" ({done} of {total} rated)" if total is not None else ""
            then = ("choosing from what is rated (the look's last pass)" if self.settle
                    else "the next look goes on from there")
            log.info("reinforce: the %.0f s look budget ran out while %s%s - %s",
                     LOOK_BUDGET_S, stage, rated, then)
        return True


def _memo_only(deadline):
    """Rate growth paths only from what is remembered (LookBudget.settle)?"""
    return isinstance(deadline, LookBudget) and deadline.settle


def _margin(forecast, towers, rnd, deadline):
    """forecast.margin(towers, rnd) - or, on a settling pass (_memo_only),
    only a margin already rated (None when there is none). Forecasts that
    cannot answer from memory (test fakes) are asked as usual."""
    if _memo_only(deadline):
        known = getattr(forecast, "remembered_margin", None)
        if callable(known):
            return known(towers, rnd)
    return forecast.margin(towers, rnd)


@dataclass
class LookPin:
    """A look that has not finished yet (best answered "busy"): the board it
    is about (forecast.board_key of the towers, the game's last round, the
    lives), the cash it rates with, and how many passes answered "busy".

    The cash is pinned because grow() and options() depend on it: what the
    cash can grow a placement into, which upgrades it affords. Rated afresh
    with each pass's (higher) cash, the look kept asking about boards the
    forecast had never seen, so remembering its ratings saved nothing
    (Water Park Impoppable, 2026-11-11 round 88: cash $7.9k -> $19.6k over
    ten busy passes). The pinned cash is never more than the bank: a lower
    reading lowers it (a misread or a purchase made elsewhere), and a
    purchase changes the board, which starts a new look.

    The round being played is left out of the key on purpose: a round
    change must not restart the count, or a look that spans rounds would
    never settle (the rounds rated shift, the growth paths do not).

    `at` is when its last pass ran (time.monotonic()): a look not gone on
    with for PIN_STALE_S (the look-ahead turned safe, or the plan took the
    turns) is dropped, so a later look does not rate an old, smaller bank."""
    key: tuple
    cash: float
    busy: int = 0
    at: float = field(default_factory=time.monotonic)


PIN_STALE_S = 30.0     # an unfinished look not gone on with for this long starts afresh


def look_pin(ex, cash, end_round, lives):
    """The LookPin for the look starting now on `ex`'s board: the unfinished
    one (ex.look_pin) when it is about the same board and recent, its cash
    lowered to `cash` if the bank holds less, else a new one with `cash`."""
    from .forecast import board_key        # here: forecast is optional for test fakes
    key = (board_key(board(ex)), end_round, lives)
    pin = getattr(ex, "look_pin", None)
    now = time.monotonic()
    if (not isinstance(pin, LookPin) or pin.key != key or cash is None or pin.cash is None
            or now - pin.at > PIN_STALE_S):
        pin = LookPin(key, cash)
    elif cash < pin.cash:
        pin.cash = cash
    pin.at = now
    try:
        ex.look_pin = pin
    except AttributeError:                  # an executor fake without attributes
        pass
    return pin


def _over(deadline, stage, done=None, total=None):
    """Has the look's budget run out in `stage` (LookBudget.over)? For a
    plain deadline, _past."""
    if isinstance(deadline, LookBudget):
        return deadline.over(stage, done, total)
    return _past(deadline)


def lookahead_rounds(rnd, end_round, k=LOOKAHEAD):
    return [r for r in range(rnd, rnd + k) if r <= end_round] if rnd is not None else []


def _rating_spots(ex, kind, step):
    """The spot a placement on offer is rated at: Executor.peek_spots, which
    leaves the kind's one probe of a blocked cell (_probe_spot) for the
    pick-up that clicks it. Every look rates every placement it offers, and
    pick_spots spent the probe on the first rating: on Infernal Impoppable
    (2026-11-10) the sniper and the sub, whose only spot left was their
    probe, dropped out of the offers after one look, and from round 63 one
    purchase was tried per look. Executors without peek_spots (test fakes)
    are asked pick_spots."""
    peek = getattr(ex, "peek_spots", None)
    return (peek if callable(peek) else ex.pick_spots)(kind, step, n=1)


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
            spots = _rating_spots(ex, kind, step)
            if not spots:
                continue
            fx, fy = ex.m.cell_to_frac(spots[0][0], spots[0][1])
            new = SimpleNamespace(tid=f"_new_{kind}", kind=kind, tiers=(0, 0, 0), x=fx, y=fy)
            out.append(Option(f"another {kind}", cost, step, now + [new]))
    out.sort(key=lambda o: o.cost)
    return trim(out)


def camo_round(ex, rnd):
    """Does round `rnd` of the executor's mode send camo bloons (a camo
    group, or a bloon whose table entry is camo, such as a DDT)? Read from
    the game's round sets through the damage model; False when the model's
    data is missing."""
    from . import dps_model as D       # here: the model is optional offline
    if rnd is None or not D.available():
        return False
    set_name = "abr" if getattr(ex, "mode", None) == "abr" else "standard"
    table = D.bloon_table()
    for g in D._round_groups(set_name, rnd):
        if g.get("camo") or (table.get(g.get("id") or "") or {}).get("camo"):
            return True
    return False


def radar_option(ex, cash, rnd):
    """A Monkey Village beside the main damage tower that cannot see camo,
    rated at the Radar Scanner (0-2-0) it grows into (grow does the
    rating) - or None when that would not be an answer.

    Tricky Tracks Medium (2026-11-07, case 20261107_014709): round 51's 15
    camo ceramics took all 128 lives at once. The only camo sight was one
    dart, the model rated round 51 at 0.06 from round 49 on, but nothing
    reinforce offered lifted it: options() offers more of the damage kinds
    standing (three boomerangs, none of them seeing camo) and the village is
    no damage kind, so the one purchase that gives the whole group camo sight
    was never rated.

    Offered only when the round being judged (`rnd`, the worst one) sends
    camo bloons, no village with Radar Scanner stands yet, and the damage
    tower with the most money in it does not see camo on its own
    (dps_model.detects_camo) - it is placed beside that tower (role
    support). A bare village already standing is grown toward 0-2-0 instead
    (grow -> grow_standing), so a village bought this way is not left bare."""
    from . import dps_model as D
    kind = "village"
    if ex.at_tower_cap() or not getattr(ex, "kind_allowed", lambda k: True)(kind):
        return None
    if not camo_round(ex, rnd):
        return None
    towers = list(ex.g.towers.values())
    if any(t.kind == kind and t.tiers[1] >= 2 for t in towers):
        return None                     # a Radar Scanner already stands
    family = _price_family(ex)
    damage = [t for t in towers if t.kind != "hero" and t.kind not in NOT_DAMAGE and t.kind in T.TOWERS]
    if not damage:
        return None
    main = max(damage, key=lambda t: T.total_cost(t.kind, tuple(t.tiers), family))
    if D.detects_camo(main.kind, tuple(main.tiers)):
        return None
    cost = ex.g.price(kind)
    if cost is None or cost > cash:
        return None
    step = {"do": "place", "kind": kind, "role": "support", "near": [main.tid]}
    held_back = getattr(ex, "place_held_back", None)
    if held_back is not None and held_back(step):
        return None
    spots = _rating_spots(ex, kind, step)
    if not spots:
        return None
    fx, fy = ex.m.cell_to_frac(spots[0][0], spots[0][1])
    new = SimpleNamespace(tid=f"_new_{kind}", kind=kind, tiers=(0, 0, 0), x=fx, y=fy)
    return Option(f"another {kind} (camo sight for {main.tid})", cost, step, board(ex) + [new])


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


def best(ex, forecast, cash, rnd, end_round, lives=None, deadline=None):
    """("safe", None) when the look-ahead holds - nothing leaks at half
    strength, so every round's margin is at least TARGET_MARGIN - or cannot
    be rated; ("wait", None) when nothing the cash buys helps yet; ("save",
    (Option, ...)) when the worst round leaks even at full strength, nothing
    affordable lifts it over 1, a dearer purchase would (save_target) and
    the rounds before it do not cost the `lives` left (dies_first); else
    ("buy", (Option, its worst round, that round's margin before, after))
    for the purchase that saves the most lives per dollar (under a click
    budget, per share of the cash and of the seconds left: worth()).

    While the round being played is in trouble (crisis_now) neither a
    waiting plan step nor a dearer purchase holds more of the cash than
    income cannot rebuild before it is needed (release), and a purchase's
    lift is judged on the round being played too (lift). A plan step that
    cannot be paid before a round the game is at stake in (danger_round)
    holds nothing against a purchase that lifts that round
    (plan_claim_in_crisis).

    ("busy", None) when the look ran out of time first: `deadline` is the
    time.monotonic() by which it must be done (default LOOK_BUDGET_S from
    now), and every stage that rates many boards stops there - grow, the
    purchases' leaks, strongest, new_kind_options, save_target (LookBudget).
    The few ratings of the board as it stands are not cut; the forecast
    remembers all of them, so the next look goes on from there. While a
    look is unfinished its cash stays pinned (LookPin), and after
    MAX_BUSY_LOOKS busy passes the next one chooses from what has been
    rated (LookBudget.settle) - so every look answers within a few passes,
    however fast the bank grows."""
    pin = look_pin(ex, cash, end_round, lives)
    settle = pin.busy >= MAX_BUSY_LOOKS
    if settle:
        log.info("reinforce: the look at $%d has been cut short %d times - this pass chooses from "
                 "what is rated", pin.cash, pin.busy)
    budget = LookBudget(look_deadline() if deadline is None else deadline, forecast, settle=settle)
    status, found = _look(ex, forecast, cash if pin.cash is None else pin.cash, rnd, end_round,
                          lives, budget)
    if status == "busy":
        pin.busy += 1
    elif getattr(ex, "look_pin", None) is pin:
        ex.look_pin = None                  # done: the next look starts afresh
    return status, found


def _look(ex, forecast, cash, rnd, end_round, lives, deadline):
    """best() for the look's (pinned) `cash` and its LookBudget `deadline`."""
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
    # the round being played and the next ENDING_LOOKAHEAD: a game-ending
    # round has to be seen while a purchase for it can still be paid and
    # grown. Only the next round used to count, so on Pat's Pond ABR
    # (2026-11-07, case 20261107_044339) round 57 - rated 0.83, "145 of the
    # 100 lives" - was judged on only once it was next; rounds 54-56 judged
    # purchases on round 63 (0.28), nothing lifted that enough, and $13.9k
    # sat unspent until round 57 ended the game. Rounds further off are left
    # to the saving rules (save_target, dies_first): income comes in first.
    ending = deciding_round(forecast, ex, [r for r in rounds_rated if r <= rnd + ENDING_LOOKAHEAD], lives)
    if ending is not None and ending != worst:
        # the game would end at `ending`: rounds after it never come, so the
        # purchase is judged on that round and the ones before it only
        log.info("reinforce: round %d would end the game at full strength (%s lives left) - judging "
                 "purchases on it, not on round %d", ending, lives, worst)
        worst = ending
        rounds_rated = [r for r in rounds_rated if r <= ending]
        base = sum(by_round[r] for r in rounds_rated)
    before = forecast.margin(board(ex), worst)
    # Under margin 1 the worst round leaks even at full strength: the game
    # is at stake, so the purchase saving the most lives wins, not the most
    # per dollar (which kept buying the cheapest small step, see trim()).
    crisis = before is not None and before < 1.0
    pick = None
    opts = options(ex, cash)
    radar = radar_option(ex, cash, worst)     # camo sight for the group (backlog #64)
    if radar is not None:
        opts.append(radar)
    tried = grow(ex, forecast, opts, cash, worst, deadline=deadline)
    if not deadline.settle and deadline.over("rating growth paths"):
        return "busy", None
    unfinished = goal_option(ex, cash, rnd)
    if unfinished is not None:
        tried = [unfinished] + tried       # judged like any other purchase, by the whole path
    # under a click budget (Apopalypse) the seconds a purchase takes count
    # too: worth(), clicktime.py
    budget_s = CT.time_left(ex, rnd, worst)
    now_board = board(ex)
    for done, o in enumerate(tried):
        if deadline.over("rating the purchases' leaks", done, len(tried)):
            if not deadline.settle:
                return "busy", None
            break           # the last pass: the pick is the best of those rated
        leak = forecast.leaks(o.towers, rounds_rated, half)
        if leak is None:
            continue
        saved = base - leak
        if saved < MIN_SAVED:
            continue
        value = worth(ex, o, saved, cash, budget_s, crisis, now_board)
        if pick is None or value > pick[0]:
            pick = (value, o)
    if pick is None and crisis:
        pick = strongest(forecast, tried, worst, before, deadline=deadline)
        if deadline.cuts():
            return "busy", None
    now = crisis_now(forecast, ex, rnd)
    plan_wait = waiting_plan_step(ex, cash)
    if pick is not None and plan_wait is not None:
        step, cost = plan_wait
        danger = danger_round(forecast, ex, rnd, lives=lives)
        lifts = None
        if danger is not None and payable_by(ex, cost, cash, danger, rnd) is False:
            lifts = plan_claim_in_crisis(forecast, ex, tried, pick, danger, deadline=deadline)
            if deadline.cuts():
                return "busy", None
        if lifts is not None:
            # the step cannot come before the round the game is at stake in,
            # so it holds nothing against the purchase that lifts that round
            log.info("reinforce: plan step %s ($%d) cannot be paid before round %d, the round in "
                     "danger, from $%d and the income until then - %s lifts that round %.2f -> %.2f "
                     "and comes first", step, cost, danger, cash, lifts[1].what, lifts[2], lifts[3])
            pick = lifts[:2]
        else:
            after = forecast.margin(pick[1].towers, worst)
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
    # The two fallbacks below spend a big idle bank on purpose, even when the
    # model sees no gain - but only when no purchase saved a life anywhere.
    # A pick the waiting plan step has just vetoed does not turn into a
    # blind spend of the step's saving (094f8de kept them for the no-pick
    # case; the step's check runs first here so that it never flags them).
    if pick is None and crisis and cash >= BLIND_SPEND_CASH:
        pick = strongest(forecast, new_kind_options(ex, forecast, cash, worst, deadline=deadline),
                         worst, before, deadline=deadline)
        if deadline.over("rating tower kinds not on the board") and not deadline.settle:
            return "busy", None
        if pick:
            log.warning("reinforce: nothing standing can grow to help round %d (%.2f) - trying a "
                        "tower kind not on the board yet, %s", worst, before or 0.0, pick[1].what)
    if pick is None and crisis and cash >= BLIND_SPEND_CASH:
        pick = dearest_upgrade(tried)
        if pick:
            log.warning("reinforce: the model sees nothing that helps round %d (%.2f) - spending "
                        "$%d anyway on the dearest upgrade, %s", worst, before or 0.0, cash, pick[1].what)
    after = forecast.margin(pick[1].towers, worst) if pick else None
    if crisis and (after is None or after < 1.0) and not dies_first(forecast, ex, rnd, worst, lives):
        # Nothing affordable stops the leak: spending now only delays the
        # purchase that would (see save_target).
        target = save_target(forecast, ex, cash, rnd, worst, deadline=deadline)
        if deadline.cuts():
            return "busy", None
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


def worth(ex, o, saved, cash, budget_s, crisis, now=None):
    """How much purchase `o`, saving `saved` lives, is worth against the
    others of one look.

    Without a click budget (budget_s None: every mode whose rounds wait for
    the bot) it is the lives saved per dollar, or in a crisis (the worst
    round leaks at full strength) the lives saved.

    Under a click budget (clicktime.time_limited: Apopalypse, where a round
    passes every 3-4 s and one purchase takes about one of them) the
    seconds of clicking it takes (clicktime.board_seconds: a placement, a
    tier, or the whole path a grown option is rated at) are spent too, out
    of the budget_s seconds before the round judged. Per dollar, Mesa
    Apopalypse (2026-11-09) bought $300-$450 tiers one a round while
    $7.7k-$17.4k sat in the bank from round 44 to the loss at round 59. So
    a purchase is worth the lives it saves per share of both budgets
    (clicktime.effort: its cost over the cash in hand plus its seconds over
    budget_s): with little cash that is about per dollar, with a large bank
    about per second, so a big tier on a standing tower (one click) beats a
    new tower grown tier by tier. In a crisis the dollars still do not
    count, but a purchase that cannot be clicked before the round is worth
    only the share of it that can (budget_s over its seconds)."""
    if budget_s is None:
        return saved if crisis else saved / max(o.cost, 1.0)
    secs = CT.board_seconds(ex, board(ex) if now is None else now, o.towers)
    if crisis:
        return saved * min(1.0, budget_s / max(secs, 1e-6))
    return saved / CT.effort(o.cost, secs, cash, budget_s)


def deciding_round(forecast, ex, rounds, lives):
    """The first of `rounds` by which the board, at full strength, would have
    lost every one of the `lives` left - the round the game ends in if
    nothing is bought - or None (no lives count, or the board survives the
    look-ahead in the model).

    best() otherwise judges a purchase on the round losing the most lives at
    half strength, and that can lie past the round that ends the game. Quiet
    Street Impoppable (2026-11-06, case 20261106_205252, one life): at round
    39 every purchase was judged on round 48 (0.73) while round 40 was rated
    0.75 with 108 lives expected to leak. Both margins sat near each other,
    so a $240 ace tier that would lift round 40 to 0.98 read "0.73 -> 0.73",
    the plan's $6,000 step took the cash, and round 40's MOAB ended the game.
    Lives lost in a round after the game is over count for nothing.
    best() asks this only of the round being played and the next one."""
    if lives is None or lives <= 0 or not rounds:
        return None
    by_round = forecast.leaks(board(ex), sorted(rounds), 1.0, per_round=True)
    if not by_round:
        return None
    lost = 0.0
    for r in sorted(by_round):
        lost += by_round[r]
        if lost >= lives:
            return r
    return None


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
         (tower gone, no spot) keeps the old MIN_LIFT bar.
    A judged round at the margin floor moves no margin whatever is bought,
    so there the lives saved decide instead (floor_pick_outsaves)."""
    if payable_by(ex, cost, cash, worst, rnd) is False:
        log.info("reinforce: plan step %s ($%d) cannot be paid before round %d from $%d and the income "
                 "until then - it holds no cash", step, cost, worst, cash)
        return False
    if moved < MIN_LIFT:
        return not floor_pick_outsaves(forecast, ex, step, cost, rnd, worst, crisis, pick)
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


def floor_pick_outsaves(forecast, ex, step, cost, rnd, worst, crisis, pick):
    """Does `pick` beat the waiting plan step on lives saved, the judged
    rounds being at the margin floor (dps_model.at_floor)?

    The margin search floors at 1/16, and MIN_LIFT compares margins: once
    the weakest round sits there every purchase reads "0.06 -> 0.06", so
    plan_keeps_claim kept the cash for the step whatever the purchase would
    save. Dark Dungeons Magic Monkeys Only (2026-11-05, case
    20261105_070008) held cash that way 14 times while the round was lost
    (backlog 39b). The leak moves with every purchase, so at the floor the
    pick outbids the step when it saves MIN_SAVED lives or more and more
    than the step itself would. False when the rounds are not at the floor,
    the pick saves too little, or the step cannot be rated (it keeps its
    claim, as under the MIN_LIFT rule)."""
    from .dps_model import at_floor     # lazy, like forecast.py: the model loads on first use
    rounds = judged_rounds(rnd, worst, crisis)
    here = board(ex)
    margins = [m for m in (forecast.margin(here, r) for r in rounds) if m is not None]
    if not margins or not at_floor(min(margins)):
        return False
    pick_saved = saved_lives(forecast, here, pick.towers, rounds)
    if pick_saved is None or pick_saved < MIN_SAVED:
        return False
    option = plan_option(ex, step, cost)
    if option is None:
        return False
    step_saved = saved_lives(forecast, here, option.towers, rounds)
    if step_saved is None or step_saved >= pick_saved:
        return False
    log.info("reinforce: round %d is at the margin floor - %s saves %.0f lives there, plan step %s ($%d) "
             "%.0f; the purchase comes first", worst, pick.what, pick_saved, step, cost, step_saved)
    return True


def plan_claim_in_crisis(forecast, ex, tried, pick, danger, deadline=None):
    """The purchase to make while round `danger` (danger_round: rated under
    forecast.CRISIS_MARGIN, or lives fell) is at hand and the waiting plan
    step cannot be paid before it from the cash and the income until then
    (payable_by False): (value, Option, margin before, margin after) for
    `pick` when it lifts that round by MIN_LIFT or more, else for the
    purchase among `tried` that lifts it most (strongest), else None. With
    None best() judges the pick by the weakest look-ahead round as before
    (plan_keeps_claim): a pick that lifts neither round still does not
    outbid a step income can deliver before the weakest one, and a big
    idle bank is not spent blind on the step's saving either (094f8de).

    plan_keeps_claim drops a step that income cannot deliver before the
    weakest look-ahead round. Ancient Portal Impoppable (2026-11-05, lost at
    round 94 with $17,562 in hand) showed the gap in the round itself: 94
    was rated 0.45 at its start, the step (Perma-Spike, $36,000) was still
    payable before the weakest round, 98 or 99, so the claim held and the
    pick was vetoed with "another super would move round 98 only 0.27 ->
    0.27 - the cash stays for plan step". A step that cannot come before
    the round the game is at stake in is no defence for that round; the
    step keeps its claim outside such a round, and while income can still
    deliver it in time (094f8de, 7919935).

    deadline: the look's (best); strongest stops there."""
    before = forecast.margin(board(ex), danger)
    after = forecast.margin(pick[1].towers, danger)
    found = pick if after is not None and after - (before or 0.0) >= MIN_LIFT else None
    if found is None:
        found = strongest(forecast, tried, danger, before, deadline=deadline)
    if found is None:
        return None
    return found[0], found[1], before or 0.0, forecast.margin(found[1].towers, danger) or 0.0


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
        spots = _rating_spots(ex, kind, step)
        if not spots:
            return None
        fx, fy = ex.m.cell_to_frac(spots[0][0], spots[0][1])
        new = SimpleNamespace(tid=step.get("id") or f"_plan_{kind}", kind=kind, tiers=(0, 0, 0), x=fx, y=fy)
        return Option(f"plan step place {kind}", cost, step, now + [new])
    return None


def strongest(forecast, tried, worst, before, deadline=None):
    """(value, Option) for the purchase that lifts round `worst`'s margin
    the most at full strength, or None when none lifts it at all.

    The crisis fallback when no purchase saves MIN_SAVED lives at half
    strength: once a round is far past saving at half strength (a ZOMG
    leaks whole either way), that count no longer moves. Infernal Double
    HP MOABs (2026-11-03) rated round 79 at 0.25 for ten rounds and sat on
    up to $77,100 with "nothing buys helps" - then lost there.

    Past `deadline` (the look's, best) the purchases not rated yet are left
    out: best() then answers "busy" and the next look rates them. On a
    settling pass (LookBudget.settle) the rest are still judged by the
    margins already rated - most were, as growth paths."""
    found = None
    for done, o in enumerate(tried):
        if _over(deadline, f"rating purchases for round {worst}", done, len(tried)):
            if not _memo_only(deadline):
                break
            m = _margin(forecast, o.towers, worst, deadline)
        else:
            m = forecast.margin(o.towers, worst)
        if m is not None and m > (before or 0.0) + 0.01 and (found is None or m > found[0]):
            found = (m, o)
    return found


def new_kind_options(ex, forecast, cash, rnd, deadline=None):
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
    return grow(ex, forecast, options(ex, cash, kinds=kinds), cash, rnd, deadline=deadline)


def grow(ex, forecast, opts, cash, rnd, deadline=None):
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
    options once it stands.

    A placement is offered only once every standing tower of its kind has
    the tiers the new one is rated at; until then the option is the next
    upgrade of the standing one closest to them, rated at the same target
    (grow_standing). Spillway Medium (2026-11-05, case 20261105_093123):
    eleven bare snipers and seven bare subs were bought one after another,
    each as "another sniper (to grow to 1-2-0)", and none was ever grown -
    the standing ones' single tiers were rated one tier at a time against
    a placement rated at its whole future - and round 40's MOAB took the
    125 lives left.

    On a settling pass (LookBudget.settle) every crosspath is judged by the
    margin already rated for it, and those never rated are left out; a
    placement none of whose crosspaths was rated stays bare, and one whose
    standing towers' growth could not be judged is not offered at all (it
    would buy a new tower while the standing ones wait, as on Spillway)."""
    family = _price_family(ex)
    memo_only = _memo_only(deadline)
    out = []
    for o in opts:
        if o.step.get("do") != "place" or (_past(deadline) and not memo_only):
            # past the look's time budget a placement stays rated bare: the
            # look goes on with what it has rather than block the game
            out.append(o)
            continue
        *rest, new = o.towers
        rated = []
        for tiers in grown(ex, new.kind, cash) | {(0, 0, 0)}:     # bare: when growing adds nothing
            if rated and _past(deadline) and not memo_only:
                # a late margin costs 0.3-0.7 s and a placement has up to
                # seven crosspaths: checked per placement only, a look ran
                # 3-4 s past its budget (X Factor Impoppable, round 85)
                break
            m = _margin(forecast, rest + [SimpleNamespace(**{**vars(new), "tiers": tiers})], rnd, deadline)
            if m is not None:
                rated.append((m, -T.total_cost(new.kind, tiers, family), tiers))
        if rated:
            m, neg_cost, tiers = max(rated)
            if any(tiers):
                standing = grow_standing(ex, forecast, rest, new.kind, tiers, m, cash, rnd, family,
                                         deadline=deadline)
                if standing is UNJUDGED:
                    continue
                if standing is not None:
                    out.append(standing)
                    continue
                new = SimpleNamespace(**{**vars(new), "tiers": tiers})
                whole = "-".join(map(str, tiers))
                # the placement was rated at the crosspath it grows into, so
                # growing it is part of the purchase: the goal's tower id is
                # filled in once it stands (buy_best, _new_tower_goal)
                o = Option(f"{o.what} (to grow to {whole})", -neg_cost,
                           o.step, rest + [new], goal={"do": "upgrade", "id": None, "to": whole})
        out.append(o)
    return out


def grow_standing(ex, forecast, rest, kind, tiers, margin, cash, rnd, family, deadline=None):
    """The next upgrade of a standing tower of `kind` that is behind the
    tiers a new one would be rated at (`tiers`), rated at the crosspath the
    cash grows it into - or None when every standing tower of the kind has
    those tiers, or none of them grows (with the cash, along its own paths)
    to a board the model rates at least as well as the new tower's
    (`margin`: a badly placed tower is not grown for its own sake).

    The standing tower closest to the target comes first; among its
    reachable crosspaths the model's best, then the cheapest, is kept, and
    the option costs what is left to pay to it - judged per dollar like
    the placement it replaces. What is bought is the next tier on the way;
    the rest follow the same way once it stands.

    Past the look's `deadline` (LOOK_BUDGET_S) the crosspaths still unrated
    are skipped once one has been found, and no further standing tower is
    tried: UNJUDGED then (the look answers "busy" anyway). Only the
    crosspaths of one tower used to be bounded, so a kind with several
    towers behind and none reaching `margin` was rated whole - on Water
    Park Impoppable (2026-11-11, round 88: two bare druids behind 2-0-4)
    a look ran 13-14 s of its 6 s budget. On a settling pass
    (LookBudget.settle) only the margins already rated count, and UNJUDGED
    means that a standing tower could not be judged from them."""
    want = sum(tiers)
    behind = sorted((t for t in rest if t.kind == kind and sum(t.tiers) < want), key=lambda t: -sum(t.tiers))
    memo_only = _memo_only(deadline)
    unrated = False
    for i, t in enumerate(behind):
        if i and _past(deadline) and not memo_only:
            return UNJUDGED
        best = None
        for target, first in grown_from(ex, kind, tuple(t.tiers), cash, tower=t).items():
            if best is not None and _past(deadline) and not memo_only:
                break
            if first is None:
                continue
            after = [SimpleNamespace(**{**vars(x), "tiers": target}) if x.tid == t.tid else x for x in rest]
            m = _margin(forecast, after, rnd, deadline)
            if m is None and memo_only:
                unrated = True
            if m is None or m < margin:
                continue
            cost = T.total_cost(kind, target, family) - T.total_cost(kind, tuple(t.tiers), family)
            if best is None or (m, -cost) > best[:2]:
                best = (m, -cost, target, first, after)
        if best is not None:
            m, neg_cost, target, first, after = best
            code, whole = "-".join(map(str, first)), "-".join(map(str, target))
            return Option(f"upgrade {t.tid} -> {code} (to grow to {whole})", -neg_cost,
                          {"do": "upgrade", "id": t.tid, "to": code}, after,
                          goal={"do": "upgrade", "id": t.tid, "to": whole})
    return UNJUDGED if unrated else None


# grow_standing's answer when a standing tower behind could not be judged
# within the look's budget, or from what was rated (a settling pass)
UNJUDGED = object()


def _tiers(code):
    """"4-2-0" -> (4, 2, 0)."""
    return tuple(int(c) for c in str(code).split("-"))


def _next_tier_cost(kind, tiers, target, family):
    """The price of the cheapest single tier that moves `tiers` toward
    `target` (the order Executor._next_path buys in), or None when the tower
    is at the target or has gone another way."""
    if any(c > t for c, t in zip(tiers, target)):
        return None
    costs = [T.upgrade_cost(kind, i + 1, tiers[i] + 1, family) for i in range(3) if tiers[i] < target[i]]
    return min(costs) if costs else None


def goal_option(ex, cash, rnd):
    """The unfinished reinforce goal (ex.reinforce_goal, left by follow_goal)
    as an Option for best(): the next tier toward the goal's crosspath,
    costed at what the rest of the path costs and rated at the finished
    crosspath, as grow_standing rated it when it was chosen - or None.

    Lotus Island CHIMPS (2026-11-05, case 20261105_171203) picked "buccaneer1
    -> 1-1-0 (to grow to 4-2-0) ($13555)", rated by the Aircraft Carrier it
    grows into (round 95: 0.38 -> 0.99), bought the $295 tier and never came
    back to the rest: at the next look the path was one option among twenty,
    each rated by a single tier, and the cash went elsewhere. The buccaneer
    stood at 1-1-0 when round 95 came.

    The goal is dropped (and None returned) once the tower is gone, has gone
    another way, stands at the goal, the goal's round has passed, or the
    rest of the path cannot be paid before that round from the cash and the
    income until then (payable_by): then it holds no claim. It is also None,
    but kept, while the cash does not cover the next tier yet."""
    goal = getattr(ex, "reinforce_goal", None)
    if not goal:
        return None
    step, due = goal["step"], goal["round"]
    p = ex.g.towers.get(step["id"])
    target = _tiers(step["to"])
    family = _price_family(ex)
    why = None
    if p is None:
        why = "the tower is gone"
    elif rnd is not None and rnd > due:
        why = f"its round {due} has passed"
    elif all(c >= t for c, t in zip(p.tiers, target)):
        why = "it stands"
    elif any(c > t for c, t in zip(p.tiers, target)):
        why = "the tower went another way"
    if why is None:
        left = T.total_cost(p.kind, target, family) - T.total_cost(p.kind, tuple(p.tiers), family)
        if payable_by(ex, left, cash, due, rnd) is False:
            why = f"the rest (${left:.0f}) cannot be paid before round {due}"
    if why is not None:
        log.info("reinforce: goal %s -> %s dropped: %s", step["id"], step["to"], why)
        ex.reinforce_goal = None
        return None
    nxt = _next_tier_cost(p.kind, tuple(p.tiers), target, family)
    if nxt is None or nxt > cash:
        return None
    now = board(ex)
    after = [SimpleNamespace(**{**vars(t), "tiers": target}) if t.tid == p.tid else t for t in now]
    return Option(f"upgrade {p.tid} toward {step['to']} (the goal for round {due})", left,
                  dict(step), after, goal=dict(step))


def follow_goal(ex, goal, cash, due, rnd, start):
    """After the first tier of a goal (Option.goal) went through, buy the
    path's next tiers too while `cash` (what the goal was rated on, less
    what has been spent since `start`, the tower's tiers before the first
    one) covers them - the path was chosen as a whole. Whatever is left
    (cash ran short, a click failed) becomes ex.reinforce_goal, offered
    again at the next looks (goal_option) until round `due`."""
    p = ex.g.towers.get(goal["id"])
    if p is None or start is None:
        return
    family = _price_family(ex)
    target = _tiers(goal["to"])
    for _ in range(15):           # at most the tiers of one crosspath
        if all(c >= t for c, t in zip(p.tiers, target)):
            ex.reinforce_goal = None
            return
        left = cash - (T.total_cost(p.kind, tuple(p.tiers), family) - T.total_cost(p.kind, start, family))
        nxt = _next_tier_cost(p.kind, tuple(p.tiers), target, family)
        if nxt is None or nxt > left:
            break
        before = tuple(p.tiers)
        with _why(ex, "reinforce", f"goal {p.tid} -> {goal['to']} for round {due}"):
            r = ex.try_step(dict(goal), left, rnd)
        if r not in ("bought", "progress") or tuple(p.tiers) == before:
            break
        log.info("reinforce: %s -> %s on the way to %s (the goal for round %d)",
                 p.tid, "-".join(map(str, p.tiers)), goal["to"], due)
    if any(c > t for c, t in zip(p.tiers, target)):
        ex.reinforce_goal = None
    else:
        ex.reinforce_goal = {"step": dict(goal), "round": due}


def _new_tower_goal(ex, goal, step, standing):
    """(goal, start) for a placement rated at the crosspath it grows into:
    the goal's upgrade step aimed at the tower the placement just put down
    (the one of its kind that was not standing before), and its tiers now -
    or (None, None) when no new tower can be found.

    Water Park Impoppable (2026-11-10 13:44): reinforce chose "another dart
    (to grow to 0-3-2)" - Enhanced Eyesight for round 33's camo yellows - on
    rounds 30, 31 and 32. Each time it placed a bare $240 dart and nothing
    grew it, so the next look rated another bare dart at 0-3-2 again; round
    33 came with three 0-0-0 darts and $2,945 unspent, and its camo took
    the one life. follow_goal now grows the placed tower the way it grows
    an upgrade chosen for its whole path, from the tiers it stands at."""
    kind = step.get("kind")
    new = [tid for tid, p in ex.g.towers.items()
           if tid not in standing and (kind is None or getattr(p, "kind", None) == kind)]
    if len(new) != 1:
        return None, None
    tid = new[0]
    return dict(goal, id=tid), tuple(ex.g.towers[tid].tiers)


def _price_family(ex):
    """The price family (hard, impoppable, ...) of the executor's mode."""
    from .strategy import PRICE_FAMILY      # here: strategy imports this module
    return PRICE_FAMILY.get(getattr(ex, "mode", None), "hard")


# The crosspaths a new tower is rated at (grown): each path as the main one,
# with either other path as its side path.
CROSSPATHS = [(5, 2, 0), (5, 0, 2), (2, 5, 0), (0, 5, 2), (2, 0, 5), (0, 2, 5)]


def grown(ex, kind, cash):
    """The tiers a new tower of `kind` reaches toward each of CROSSPATHS
    with `cash` (its own price included): grown_from a bare tower."""
    return set(grown_from(ex, kind, (0, 0, 0), cash - T.tower_cost(kind, _price_family(ex))))


def grown_from(ex, kind, start, budget, tower=None):
    """{crosspath reached: the first upgrade on the way} for a tower of
    `kind` standing at `start`, growing toward each of CROSSPATHS with
    `budget`: the main path to tier 2, the side path to its target, then
    the main path on - as far as the budget goes and the account's tower
    XP has unlocked (tiers 1-2 are always open). A template the tower's
    tiers have already left (a tier on its third path, more on the side
    path than it wants) is not its way. The first upgrade is None when the
    budget buys nothing on that way (the tower stays as it is).

    tower: the standing tower (with its tid) the ladder is for, or None for
    one not placed yet. A standing tower's way skips a side path the
    executor would not buy now and ends at such a main path
    (Executor.path_blocked: capped for the game, price unreadable, tier 5
    taken, or on the game's retry hold) - a step there comes back "skip"
    without a click, and offered again and again it shut every other
    purchase out (High Finance Magic Monkeys Only, 2026-11-05, rounds
    49-54: wizard2's paths 1 and 3 were capped, and the ladder never got
    to Dragon's Breath on its open path 2)."""
    family = _price_family(ex)
    account = getattr(ex, "account", None)
    unlocked = account.upgrades(kind) if account else (5, 5, 5)
    blocked = getattr(ex, "path_blocked", None) if tower is not None else None
    reached = {}
    for target in CROSSPATHS:
        main = target.index(5)
        side = next(i for i in range(3) if i != main and target[i])
        other = 3 - main - side
        if start[other] or start[side] > target[side]:
            continue
        t, left, first = list(start), budget, None
        for path, upto in ((main, 2), (side, target[side]), (main, 5)):
            ended = False           # locked, unaffordable or blocked: the way ends here
            while t[path] < upto:
                tier = t[path] + 1
                if tier > 2 and tier > unlocked[path]:
                    ended = True
                    break
                if blocked is not None and blocked(SimpleNamespace(tid=tower.tid, kind=kind, tiers=tuple(t)), path + 1):
                    ended = path == main        # a blocked side path is left out, the main path goes on
                    break
                cost = T.upgrade_cost(kind, path + 1, tier, family)
                if cost > left:
                    ended = True
                    break
                left -= cost
                t[path] = tier
                if first is None:
                    first = tuple(t)
            if ended:
                break
        reached.setdefault(tuple(t), first)
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


def save_target(forecast, ex, cash, rnd, worst, deadline=None):
    """(Option, margin after) for the cheapest purchase the cash cannot buy
    yet that gets round `worst` to margin 1 or better - or None.

    Peninsula Medium (2026-10-27) rated round 40 at 0.06 from round 37 on,
    and reinforcing kept buying $1,000 sub upgrades that each saved a few
    lives at half strength but left that round at 0.06; the cash for an
    upgrade that would have held it never piled up. Saving makes sense only
    while the round is SAVE_LEAD or more rounds away (income needs rounds to
    arrive) and the target costs at most SAVE_REACH times the cash in hand
    (further than that it would not come in time).

    Under continuous sends (Apopalypse, rules `continuous`) a saving must
    also be paid within CONTINUOUS_SAVE_ROUNDS rounds of income. There the
    rounds come every 2-3 seconds and the blimps of several rounds share
    the track, so a board left as it is while the bank grows meets more
    than the one round the model rates. Castle Revenge Apopalypse
    (2026-11-06, case 20261106_183541) said "saving for upgrade su1 ->
    3-0-2 ($20000)" at round 49 with $7,006, bought nothing more, and lost
    all 142 lives in round 55 with $17,084 banked; Ancient Portal (r52,
    $18,040) and Spring Spring (r60, $21,494) died the same way.

    Past `deadline` (the look's, best) the search stops with None, and
    best() answers "busy": the next look goes on from where this one
    stopped."""
    if rnd is None or worst - rnd < SAVE_LEAD or cash <= 0:
        return None
    continuous = bool((getattr(ex, "rules", None) or {}).get("continuous"))
    dearer = [o for o in options(ex, cash * SAVE_REACH) if o.cost > cash]     # cheapest first
    for done, o in enumerate(dearer):
        if _over(deadline, "looking for a purchase to save for", done, len(dearer)):
            return None
        if continuous and payable_by(ex, o.cost, cash, rnd + CONTINUOUS_SAVE_ROUNDS, rnd) is False:
            continue        # too far off: the board would stand still for too many rounds
        m = forecast.margin(o.towers, worst)
        if m is not None and m >= 1.0:
            return o, m
    return None


def buy_best(ex, forecast, cash, rnd, end_round, lives=None, deadline=None):
    """Buy the best purchase (see best()). Returns 'bought', 'safe' (the
    look-ahead holds: stop), 'wait' (nothing affordable helps yet: more cash
    may), 'save' (keep the cash for a dearer purchase that does help),
    'busy' (the look ran out of time: look again at once, it goes on where
    it stopped) or 'failed' (the purchase did not go through).

    After a 'save', ex.save_goal is (cost, round) of the purchase being
    saved for - the match keeps the plan's own steps off that cash
    (Executor.tick, reinforce_hold) - and None after any other answer.

    deadline: when the look must be done (best); default LOOK_BUDGET_S from
    now. Match hands the same deadline to the surplus spending that may
    follow in the same pass of its loop, so the pass as a whole keeps to it."""
    # part of the cash the executor keeps for a far threat (Executor._hold_for)
    held = getattr(ex, "held_cash", 0) or 0
    if held and cash is not None:
        cash = max(0, cash - held)
    status, found = best(ex, forecast, cash, rnd, end_round, lives, deadline=deadline)
    if status == "busy":
        return status           # no answer yet: what the last look saved for still stands
    ex.save_goal = (found[0].cost, found[1]) if status == "save" else None
    if status != "buy":
        return status
    o, worst, before, after = found
    tower = ex.g.towers.get(o.goal["id"]) if o.goal and o.goal.get("id") else None
    start = tuple(tower.tiers) if tower is not None else None
    standing = set(ex.g.towers)          # to find a tower this purchase places
    with _why(ex, "reinforce", f"{o.what}: round {worst} {before or 0.0:.2f}->{after or 0.0:.2f}"):
        r = ex.try_step(dict(o.step), cash, rnd)
    if r in ("bought", "progress"):
        log.warning("reinforce: %s ($%d) - round %d, the weakest ahead, goes %.2f -> %.2f in the model",
                    o.what, o.cost, worst, before or 0.0, after or 0.0)
        plan_first = getattr(ex, "plan_first", None)
        if callable(plan_first) and plan_first():
            # a plan_first build lets reinforce spend only when its plan
            # yields; what it spends uses up the given-up steps' share of the
            # bank (Executor.given_up_credit)
            ex.yield_spent = (getattr(ex, "yield_spent", 0) or 0) + o.cost
        goal = o.goal
        if goal and goal.get("id") is None:
            goal, start = _new_tower_goal(ex, goal, o.step, standing)
            if goal:            # the placement itself is paid: grow it from what is left
                cash -= T.total_cost(ex.g.towers[goal["id"]].kind, start, _price_family(ex))
        if goal:
            # the path was rated whole: the rest of its tiers follow
            follow_goal(ex, goal, cash, worst, rnd, start)
        return "bought"
    log.info("reinforce: %s ($%d) did not go through (%s)", o.what, o.cost, r)
    return "failed"
