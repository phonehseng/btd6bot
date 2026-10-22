"""Tower XP a game earns, counted round by round as the game pays it.

The account's tower XP (unspent XP per tower type, what paragons are bought
with) is read from the Monkeys menu once a day (xpspend.sync_all). Between
those reads nothing counted the XP the games earned, so the planner's
paragon focus worked from numbers up to a day old: Tack still "95k short"
after a day of Tack games. This counts it from the game's own rules
(docs/tower_xp.md):

  * XP is paid at the end of every completed round: base(round) from
    account.round_xp, x the map's difficulty (CATEGORY_XP_MULT: x1.0 to
    x1.3), x1.08 with the Monkey Education knowledge;
  * it is split between tower types by the cash invested in them at that
    moment (price plus upgrades); heroes are left out.

The daily sync still overwrites the counts with what the game shows.
"""
from __future__ import annotations

from . import towers as T
from .account import CATEGORY_XP_MULT, MAPS, round_xp

EDUCATION_MULT = 1.08          # Monkey Education: +8% tower and hero XP
REVERSE_SUFFIX = " reverse"    # map models of Reverse games are keyed "<map> reverse"


def invested(towers, family="medium"):
    """{kind: dollars} in the non-hero towers standing (price + upgrades)."""
    out = {}
    for p in towers:
        if p.kind == "hero" or p.kind not in T.TOWERS:
            continue
        cash = T.tower_cost(p.kind, family)
        for path, tier in enumerate(p.tiers or (0, 0, 0), start=1):
            cash += sum(T.upgrade_cost(p.kind, path, t, family) for t in range(1, int(tier) + 1))
        out[p.kind] = out.get(p.kind, 0) + cash
    return out


class TowerXpCounter:
    def __init__(self, map_key, mk_unlocked=(), family="medium"):
        name = map_key[:-len(REVERSE_SUFFIX)] if map_key and map_key.endswith(REVERSE_SUFFIX) else map_key
        self.mult = CATEGORY_XP_MULT.get(MAPS.get(name), 1.0)
        if "Monkey Education" in (mk_unlocked or ()):
            self.mult *= EDUCATION_MULT
        self.family = family
        self.totals = {}           # kind -> XP earned this game
        self.paid = set()          # rounds already counted

    def round_end(self, rnd, towers):
        """Round `rnd` was completed with these towers standing."""
        if rnd is None or rnd in self.paid:
            return
        self.paid.add(rnd)
        cash = invested(towers, self.family)
        total = sum(cash.values())
        if total <= 0:
            return
        xp = round_xp(rnd) * self.mult
        for kind, c in cash.items():
            self.totals[kind] = self.totals.get(kind, 0.0) + xp * c / total

    def rounded(self):
        return {k: round(v) for k, v in self.totals.items() if v >= 1}
