"""Spend tower XP in the Monkeys menu before a game, on what the plan needs.

In-game unlocking (via a locked upgrade button) proved unreliable, and an
upgrade still locked when its threat arrives loses the game (a Hard run died
to the round-40 MOAB with MOAB Mauler affordable but locked). So before every
game the runner calls unlock_for_strategy(): main menu -> MONKEYS -> category
tab -> tower card -> upgrade tree -> unlock each needed tier the tower's XP
pays for, verified by the XP total dropping. Layout measured at 1920x1200.
"""
import logging
import re
import time

from . import towers as T
from .hud import parse_int
from .vision import norm

log = logging.getLogger("xpspend")

MONKEYS_BUTTON = (0.132, 0.88)
TABS = {"primary": (0.282, 0.979), "military": (0.427, 0.979),
        "magic": (0.573, 0.979), "support": (0.719, 0.979)}
TREE_ICON_X = (0.306, 0.424, 0.541, 0.659, 0.777)
TREE_ICON_Y = (0.33, 0.53, 0.73)       # path 1..3 icon centres
TREE_UNLOCK = (0.143, 0.683)
TREE_COST = (0.03, 0.655, 0.26, 0.725)  # "UNLOCK FOR: / 2,700XP"
TREE_XP = (0.52, 0.01, 0.70, 0.065)     # "XP: 3,373"
TREE_TITLE = (0.28, 0.005, 0.56, 0.07)
BACK = (0.044, 0.055)
SHORT = {}  # tower -> cheapest XP cost it could not pay (skip until its XP grows)


def _title_matches(title, kind):
    """OCR'd tree title vs tower (tolerates misreads like 'soomeRAnG MonKeY')."""
    import difflib
    t, name = norm(title), norm(T.TOWERS[kind]["name"])
    return T.find_tower(title) == kind or difflib.SequenceMatcher(None, t, name).ratio() >= 0.75         or (len(t) >= 6 and difflib.SequenceMatcher(None, t, name[:len(t)]).ratio() >= 0.8)


def needed_upgrades(strat):
    """[(tower, path 1..3, tier)] in the order the plan will want them."""
    order, best = [], {}
    steps = strat.get("plan", []) + [a for v in (strat.get("answers") or {}).values() for a in v] \
        + strat.get("fill", [])
    kinds_by_id = {s["id"]: s["kind"] for s in strat.get("plan", []) if s.get("do") == "place" and s.get("id")}
    for st in steps:
        if st.get("do") != "upgrade":
            continue
        kind = st.get("kind") or kinds_by_id.get(st.get("id"))
        if not kind or kind not in T.TOWERS:
            continue
        target = [int(c) for c in str(st["to"]).split("-")]
        have = best.setdefault(kind, [0, 0, 0])
        for path in range(3):
            for tier in range(have[path] + 1, target[path] + 1):
                order.append((kind, path + 1, tier))
            have[path] = max(have[path], target[path])
    return order


class XpSpender:
    def __init__(self, screen, inp, menus, account):
        self.s, self.inp, self.menus, self.account = screen, inp, menus, account

    def _read(self, region):
        from .hud import rec_text
        from .vision import crop
        return rec_text(crop(self.s.grab(), region))[0]

    def _xp(self):
        return parse_int(self._read(TREE_XP).lower().replace("xp", ""))

    def _cost(self):
        """XP cost shown for the selected upgrade, or None if it is not purchasable."""
        words = self.menus.v.read(TREE_COST)
        text = " ".join(w.text for w in sorted(words, key=lambda w: w.y))
        if "unlock" not in norm(text):
            return None
        m = re.search(r"([\d,.]+)\s*xp", text.lower().replace(" ", ""))
        return parse_int(m.group(1)) if m else None

    def open_tower(self, kind):
        """Monkeys menu -> tower's tree. True when the tree title shows the tower."""
        cat = T.TOWERS[kind]["category"]
        self.inp.click(*TABS[cat])
        time.sleep(0.6)
        words = self.menus.read()
        for w in words:
            if w.y < 0.08 or w.y > 0.9:
                continue
            n = norm(w.text)
            if n in ("monkey", "monkeys") or len(n) < 3:
                continue  # second line of a two-line name, matches everything
            if T.find_tower(w.text) == kind or _title_matches(w.text, kind) or                     (len(n) >= 4 and norm(T.TOWERS[kind]["name"]).startswith(n)):
                self.inp.click(w.x, min(0.85, w.y + 0.12))  # portrait sits under the name
                time.sleep(1.2)
                title = self._read(TREE_TITLE)
                if _title_matches(title, kind):
                    return True
                log.info("opened %r, wanted %s", title, kind)
                self.inp.click(*BACK)
                time.sleep(0.8)
                return False
        log.info("tower %s not found on the %s tab", kind, cat)
        return False

    def unlock(self, wanted):
        """wanted: [(tower, path, tier)]. Returns the list actually unlocked."""
        if not wanted:
            return []
        if self.menus.identify() != "main_menu":
            return []
        self.inp.click(*MONKEYS_BUTTON)
        time.sleep(1.5)
        done = []
        try:
            by_tower = {}
            for kind, path, tier in wanted:
                by_tower.setdefault(kind, []).append((path, tier))
            for kind, items in by_tower.items():
                known = self.account.upgrades(kind)
                items = [(p, t) for p, t in items if known[p - 1] < t]
                # skip the trip when we already know this tower's XP is short
                short = SHORT.get(kind)
                if items and short is not None and                         float((self.account.tower_xp or {}).get(kind, 0) or 0) < short:
                    continue
                if not items or not self.open_tower(kind):
                    continue
                blocked = set()
                for path, tier in items:
                    if path in blocked:
                        continue
                    self.inp.click(TREE_ICON_X[tier - 1], TREE_ICON_Y[path - 1])
                    time.sleep(0.7)
                    cost, have = self._cost(), self._xp()
                    if cost is None:
                        # no "UNLOCK FOR": already unlocked (we go in tier order)
                        self.account.unlock_upgrade(kind, path - 1, tier)
                        continue
                    if have is None or have < cost:
                        log.info("%s path %d tier %d needs %s XP, have %s", kind, path, tier, cost, have)
                        blocked.add(path)
                        if have is not None:
                            self.account.tower_xp[kind] = float(have)
                            SHORT[kind] = min(SHORT.get(kind, cost), cost)
                        continue
                    self.inp.click(*TREE_UNLOCK)
                    time.sleep(0.9)
                    after = self._xp()
                    if after is not None and after < have:
                        self.account.unlock_upgrade(kind, path - 1, tier, cost=cost)
                        done.append((kind, path, tier))
                        log.info("unlocked %s path %d tier %d for %d XP", kind, path, tier, cost)
                    else:
                        blocked.add(path)
                self.inp.click(*BACK)  # tree -> monkeys grid
                time.sleep(0.8)
        finally:
            for _ in range(3):  # back to the main menu
                if self.menus.identify() == "main_menu":
                    break
                self.inp.click(*BACK)
                time.sleep(0.8)
            self.account.save()
        return done


def unlock_for_strategy(screen, inp, menus, account, strat):
    return XpSpender(screen, inp, menus, account).unlock(needed_upgrades(strat))


def sync_all(screen, inp, menus, account, towers=None):
    """Read every owned tower's upgrade tree and store the true unlocked tiers.
    Used when an account is first seen (e.g. a higher-level save) and daily."""
    from .meta import tiers_from_states, tree_states
    sp = XpSpender(screen, inp, menus, account)
    if menus.identify() != "main_menu":
        return {}
    kinds = towers or [k for k in T.TOWERS if k in account.unlocked_towers]
    inp.click(*MONKEYS_BUTTON)
    time.sleep(1.5)
    seen = {}
    try:
        for kind in kinds:
            if not sp.open_tower(kind):
                continue
            time.sleep(0.4)
            tiers = tiers_from_states(tree_states(screen.grab()))
            # colour alone is unsure for tiers 4-5 (a locked tier 5 that is next
            # in line is drawn as a gold face): confirm by the side panel, which
            # shows "UNLOCK FOR: N XP" only for upgrades not yet unlocked
            for path in range(3):
                while tiers[path] >= 4:
                    inp.click(TREE_ICON_X[tiers[path] - 1], TREE_ICON_Y[path])
                    time.sleep(0.6)
                    if sp._cost() is None:
                        break  # "UNLOCKED" (no XP price shown): really unlocked
                    tiers[path] -= 1  # "UNLOCK FOR: N XP": still locked
            xp = sp._xp()
            account.unlocked_upgrades[kind] = list(tiers)
            if xp is not None:
                account.tower_xp[kind] = float(xp)
            seen[kind] = tiers
            inp.click(*BACK)
            time.sleep(0.8)
    finally:
        for _ in range(3):
            if menus.identify() == "main_menu":
                break
            inp.click(*BACK)
            time.sleep(0.8)
        account.save()
    log.info("upgrade sync: %s", seen)
    return seen
