"""Purchases cost time as well as cash: what to buy when the clicking is the limit.

Mesa Apopalypse (2026-11-09, lost at round 59): the 0-2-4 snipers were bought
this time, yet from round 44 the bank piled up - $7.7k, $12.4k, $14.0k,
$17.4k - while the bot bought $300-$450 single tiers, one a round. Under
continuous sends (Apopalypse) a round passes every 3-4 seconds, and one
purchase takes about 2.4 s (an upgrade: select the tower, read the panel,
click, wait for the verdict, close) or 4 s (a placement), so about one
purchase fits in a round. Ranked per dollar, the cheapest tiers always win,
and the bank is never spent: the scarce resource is seconds, not dollars.

This module prices a purchase in both:

  * seconds(): the clicking a purchase takes - a placement, plus one
    upgrade per tier; tiers bought one after another on the same tower,
    with its panel left open (Game.hold_panel), take less each;
  * time_left(): the seconds until the round being judged arrives (its
    rounds times the round length measured in this game);
  * effort(): a purchase's share of the cash in hand plus its share of
    the seconds left. Gain per effort ranks purchases per dollar when cash
    is short (the seconds share is small), per second when the bank is
    large (the cash share is small), and in between by both - the bank
    and the clock are both budgets, and each purchase spends some of each.

Only modes whose rounds do not wait for the bot are time-limited
(time_limited: rules `continuous`, Apopalypse). Elsewhere the bot buys
between rounds or while a slow round plays, and nothing here changes.

The seconds a click takes are measured in each game (note(): the executor
times each placement and upgrade it makes); the defaults are the ones read
from Mesa Apopalypse's log (2026-11-09 07:46-07:53): from a tower's pop
count (its panel just opened) to "upgraded" about 1.1 s, a whole upgrade
with the select before and the close after about 1.8 s, a placement about
3.5 s; and between two purchases on separate ticks the match loop spends
about 0.8 s more of its own (HUD reads, the threat checks, the round
change), which a tier bought from a panel still open does not.
"""
from __future__ import annotations

# Measured on Mesa Apopalypse (see the module docstring); replaced in each
# game by the executor's own measurements (note()).
PLACE_S = 3.5          # one placement: pick up, drop, confirm
UPGRADE_S = 1.8        # one upgrade tier: select, read, click, verdict, close
CHAINED_S = 1.1        # a further tier of the tower whose panel is still open
                       # (no select, no pop count, no close)
LOOP_S = 0.8           # the match loop's own time between two separate purchases
ROUND_S = 4.0          # one Apopalypse round, until the game's own pace is known
LEARN = 0.3            # weight of each new measurement in the running mean
# Tiers bought from one open panel in a row. The match loop waits while
# they are bought - no HUD read, no ability - so a long path is cut into
# runs of this many (about 5 s); the next tick goes on with the rest.
CHAIN_MAX_TIERS = 4
# Plan steps looked at by Executor._quicker_step: the current one and the
# next few, as far as the first step that is not a placement or an upgrade
# of a named tower.
PLAN_WINDOW = 5


# False: nothing here applies anywhere (the behaviour before this module) -
# for comparing the two offline (tools/apopalypse_check.py --old-clicks)
ENABLED = True


def time_limited(ex):
    """Are purchases limited by the clicking time rather than by cash? True
    under continuous sends (Apopalypse), where the rounds never wait."""
    return ENABLED and bool((getattr(ex, "rules", None) or {}).get("continuous"))


def _measured(ex):
    """The executor's measured seconds per kind of action (note()), on the
    module's defaults until it has measured its own."""
    m = getattr(ex, "click_seconds", None)
    if not isinstance(m, dict):
        m = {"place": PLACE_S, "upgrade": UPGRADE_S, "chained": CHAINED_S}
        try:
            ex.click_seconds = m
        except AttributeError:      # a read-only stand-in: use the defaults
            pass
    return m


def note(ex, action, seconds):
    """Record that one `action` ("place", "upgrade" or "chained") took
    `seconds`: a running mean, so one slow click (a popup, a retry) moves
    it only a little. Times outside 0.2-20 s are not purchases (a failed
    click, a frozen screen) and are left out."""
    if seconds is None or not 0.2 <= seconds <= 20.0:
        return
    m = _measured(ex)
    m[action] = (1 - LEARN) * m.get(action, seconds) + LEARN * seconds


def tiers_between(before, after):
    """Upgrade tiers that turn `before` into `after` (each a tiers tuple)."""
    return sum(max(0, b - a) for a, b in zip(before, after))


def seconds(ex, placements, tiers_by_tower):
    """Seconds of clicking for `placements` new towers and the upgrade tiers
    listed per tower (`tiers_by_tower`: one count per tower): the first
    tier of each run of CHAIN_MAX_TIERS costs a full upgrade and a pass of
    the match loop, each further one a chained tier (its panel stays open
    between them)."""
    m = _measured(ex)
    total = placements * (m["place"] + LOOP_S)
    for n in tiers_by_tower:
        if n > 0:
            runs = -(-n // CHAIN_MAX_TIERS)           # each run opens the panel anew
            total += runs * (m["upgrade"] + LOOP_S) + (n - runs) * m["chained"]
    return total


def board_seconds(ex, now, after):
    """Seconds of clicking that turn the board `now` into `after` (lists of
    tower records with tid and tiers): a tower in `after` that is not in
    `now` is a placement plus its tiers, a standing one its added tiers."""
    standing = {t.tid: tuple(t.tiers) for t in now}
    placements, tiers = 0, []
    for t in after:
        if t.tid in standing:
            tiers.append(tiers_between(standing[t.tid], tuple(t.tiers)))
        else:
            placements += 1
            tiers.append(sum(t.tiers))
    return seconds(ex, placements, tiers)


def round_seconds(ex):
    """The length of a round in this game: measured by the match
    (ex.round_seconds), else ROUND_S."""
    s = getattr(ex, "round_seconds", None)
    return s if isinstance(s, (int, float)) and s > 0 else ROUND_S


def time_left(ex, rnd, due_round):
    """Seconds until the bloons of `due_round` are past, seen from round
    `rnd`: the rounds from this one to that one, the round being played
    counted whole. None when not time-limited or unknown."""
    if not time_limited(ex) or rnd is None or due_round is None:
        return None
    return max(1, due_round - rnd + 1) * round_seconds(ex)


def effort(cost, secs, cash, budget_s):
    """A purchase's share of the two budgets it spends: its cost over the
    cash in hand plus its seconds over the seconds left. Never zero."""
    share = (cost / cash if cash and cash > 0 else 1.0)
    if budget_s:
        share += secs / budget_s
    return max(share, 1e-6)
