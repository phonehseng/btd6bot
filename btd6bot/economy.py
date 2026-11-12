"""Cash a board earns besides pops, and what Monkey Villages take off prices.

The bot's cash projections - the build optimizer's economy, the executor's
threat lead times and reinforce.payable_by - counted only the round's own
cash (pops plus the end-of-round bonus, threats.round_cash). That makes an
income hero or tower look like dead money: Benjamin pays $90 a round at
level 1 and $5,000 from level 17, which the optimizer never saw, so it never
had a reason to pick him (docs/model_fix_plan.md item 15,
docs/model_audit_support_heroes.md F1, V5 and G8).

Everything here is pure arithmetic on the game model's export
(data/game_model/attacks.json, read through gamemodel) and the mode rules
(strategy.MODE_RULES). No screen, no game.

What is counted, per round:
  * Benjamin's Cyber Cash: the export's per-level "income" ($90 at level 1,
    $140 from 2, $250 from 8, $1,000 from 11, $2,500 from 15, $5,000 from 17).
  * Banana Farms: the export's bananas per round. Farms that drop bananas on
    the ground pay only what the cursor collects (Game.collect_bananas), so
    they count at BANANA_COLLECTED. Marketplace (x-x-3) pays straight to the
    player. A Monkey Bank (x-3-x) keeps its cash until it is withdrawn,
    which the bot never does, so a bank counts nothing (BOT_WITHDRAWS_BANKS);
    Benjamin's Bank Hack only raises a bank's interest, so it counts nothing
    either while that is off. Monkey Wall Street's +$4,000 a round counts.
  * Other towers' flat per-round cash in the export (Merchantman, Favored
    Trades: buccaneer x-x-3/4).
Not counted: Benjamin's Skimming ($1-2 per bloon spawned), Bloon Trap and
Supply Drop cash (the export has no cash figure for them), and Monkey
Town/City's pop-cash bonus.

Mode rules: nothing in a mode without income (Deflation: `income` False) or
with income towers banned (CHIMPS: `no_income_towers`; the game pays
Benjamin nothing there either). Half Cash halves it [UNVERIFIED for
Benjamin and farms; the cautious reading]. Double Cash is NOT applied: whether it
doubles Benjamin's and the farms' pay was never checked, and counting
money that may not come is the risky direction.
"""
from __future__ import annotations

import math

# Share of a dropping farm's bananas the cursor passes collect (an estimate:
# Game.collect_bananas passes over at most MAX_BANANA_MOVES blobs every
# BANANA_EVERY seconds, and bananas expire on the ground).
BANANA_COLLECTED = 0.8

# The bot never opens a Monkey Bank to take its cash out, so a bank pays the
# bot nothing. If that changes, banks count their bananas plus interest
# (with Benjamin's Bank Hack, BANK_HACK) - see tower_income.
BOT_WITHDRAWS_BANKS = False

# Benjamin's Bank Hack: + this share of a bank's interest from the level
# (fandom:Benjamin_(BTD6): +5% at level 5, +12% at level 9).
BANK_HACK = ((9, 0.12), (5, 0.05))


def _attacks():
    from . import gamemodel
    return gamemodel._table("attacks") or {}


def _code(tiers):
    return "".join(str(int(t or 0)) for t in (tiers or (0, 0, 0)))


def hero_income(hero, level):
    """Cash hero `hero` pays at the end of every round at `level` (the
    export's per-level income: Benjamin's Cyber Cash); 0 for heroes without
    one or an unknown level."""
    if not hero or not level:
        return 0.0
    levels = ((_attacks().get("heroes") or {}).get(hero) or {}).get("levels") or {}
    level = max(1, min(int(level), max((int(k) for k in levels), default=1)))
    income = (levels.get(str(level)) or {}).get("income") or {}
    return float(income.get("per_round") or 0.0)


def bank_hack(hero, level):
    """Benjamin's Bank Hack bonus on bank interest at `level` (0 below 5)."""
    if hero != "benjamin" or not level:
        return 0.0
    return next((v for lvl, v in BANK_HACK if level >= lvl), 0.0)


def drops_bananas(kind, tiers):
    """Does this farm drop bananas the cursor must collect? Not from Monkey
    Bank (x-3-x) or Marketplace (x-x-3) on (as Game.drops_bananas)."""
    return kind == "farm" and tiers[1] < 3 and tiers[2] < 3


def tower_income(kind, tiers, hero=None, hero_level=None):
    """Cash one tower pays the bot per round (see the module docstring)."""
    tiers = tuple(tiers or (0, 0, 0))
    entry = ((_attacks().get("towers") or {}).get(kind) or {}).get("crosspaths", {}).get(_code(tiers)) or {}
    income = entry.get("income") or {}
    flat = float(income.get("per_round") or 0.0)
    bananas = float(income.get("bananas_per_round") or 0.0)
    bank = income.get("bank")
    if bank:
        if not BOT_WITHDRAWS_BANKS:
            return flat
        interest = float(bank.get("interest") or 0.0) * (1.0 + bank_hack(hero, hero_level))
        return flat + bananas * (1.0 + interest)
    if drops_bananas(kind, tiers):
        bananas *= BANANA_COLLECTED
    return flat + bananas


def income_factor(rules):
    """What the mode does to board income: 0 without income or with income
    towers banned (Deflation, CHIMPS), 0.5 in Half Cash, else 1. Double
    Cash is left out on purpose (module docstring)."""
    rules = rules or {}
    if rules.get("income") is False or rules.get("no_income_towers"):
        return 0.0
    return 0.5 if rules.get("half_cash") else 1.0


def board_income(towers, rules, hero=None, hero_level=None):
    """Cash the board pays per round besides pops: every tower's
    tower_income plus the hero's hero_income, times income_factor(rules).

    towers: objects with .kind ("hero" for the hero, skipped: its pay comes
    from `hero` and `hero_level`) and .tiers."""
    factor = income_factor(rules)
    if not factor:
        return 0.0
    total = hero_income(hero, hero_level) if hero else 0.0
    for t in towers or ():
        if getattr(t, "kind", None) in (None, "hero"):
            continue
        total += tower_income(t.kind, getattr(t, "tiers", None), hero, hero_level)
    return total * factor


# -- Monkey Village discounts --------------------------------------------------------

DISCOUNT_MAX_TIER = 3     # Monkey Business / Commerce take off the base price and tiers 1-3


def village_discount(tiers):
    """Share a village with these tiers takes off prices in its radius: the
    export's "discount" buffs (Monkey Business 0-0-1 10%, Monkey Commerce
    0-0-2 +5%)."""
    entry = ((_attacks().get("towers") or {}).get("village") or {}).get("crosspaths", {}).get(_code(tiers)) or {}
    return sum(float(b.get("value") or 0.0) for b in entry.get("buffs") or () if b.get("kind") == "discount")


def village_range(tiers):
    entry = ((_attacks().get("towers") or {}).get("village") or {}).get("crosspaths", {}).get(_code(tiers)) or {}
    return float(entry.get("range") or 0.0)


def discount_at(x, z, villages):
    """The best discount of any village whose radius holds the point (x, z)
    (world units, as the build optimizer's spots). villages: objects with
    .tiers and .spot (.x, .z). Only the best one counts: whether two
    villages' discounts add up was not checked (Monkey Commerce's text says
    it stacks with up to two others), and taking one is the cautious
    reading."""
    best = 0.0
    for v in villages or ():
        d = village_discount(v.tiers)
        if d <= best:
            continue
        r = village_range(v.tiers)
        if math.hypot(v.spot.x - x, v.spot.z - z) <= r:
            best = d
    return best


def discounted(price, tier, discount):
    """`price` of the base tower (tier 0) or one upgrade tier with
    `discount` off, when the tier is one the discount covers."""
    if discount and tier <= DISCOUNT_MAX_TIER:
        return price * (1.0 - discount)
    return price
