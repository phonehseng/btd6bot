"""Spend tower XP in the Monkeys menu before a game, on what the plan needs.

In-game unlocking (via a locked upgrade button) proved unreliable, and an
upgrade still locked when its threat arrives loses the game (a Hard run died
to the round-40 MOAB with MOAB Mauler affordable but locked). So before every
game the runner calls unlock_for_strategy(): main menu -> MONKEYS -> category
tab -> tower card -> upgrade tree -> unlock each needed tier the tower's XP
pays for, verified by the XP total dropping. Layout measured at 1920x1200.
The menu is only opened when some needed tier is neither known unlocked nor
known to be too expensive (see known_short).
"""
import logging
import re
import time

from . import status
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
# With all three tier 5s unlocked, the tree ends in a purple paragon column;
# selecting it fills the side panel with the paragon and "UNLOCK FOR: N XP".
# (Measured 2026-10-22 on the Tack Shooter: Crucible of Steel and Flame,
# 500,000 XP. No confirmation box: the click unlocks it, the tree turns
# purple.) Never near: UNLOCK ALL (bottom right) and the "+" next to the XP,
# both real money.
PARAGON_COLUMN = (0.895, 0.507)
PARAGON_PRICE_TOLERANCE = 0.02   # the panel's price may differ this much from data/tower_xp.json


def _title_matches(title, kind):
    """OCR'd tree title vs tower (tolerates misreads like 'soomeRAnG MonKeY')."""
    import difflib
    t = norm(title)
    exact = T.find_tower(title)
    if exact:
        return exact == kind

    def score(k):
        name = norm(T.TOWERS[k]["name"])
        r = difflib.SequenceMatcher(None, t, name).ratio()
        if r < 0.75 and len(t) >= 6 and difflib.SequenceMatcher(None, t, name[:len(t)]).ratio() >= 0.8:
            r = 0.75
        return r

    # the best-scoring tower must be this one ('SUPeRMONKeY' is close to Mermonkey too)
    best = max(T.TOWERS, key=score)
    return best == kind and score(kind) >= 0.75


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


def strategy_towers(strat):
    """Tower kinds a strategy places (plan, threat answers, fill): the towers
    that earn XP when it is played."""
    steps = strat.get("plan", []) + [a for v in (strat.get("answers") or {}).values() for a in v] \
        + strat.get("fill", [])
    return {st["kind"] for st in steps if st.get("kind") in T.TOWERS}


# -- "can't afford yet", remembered per account (AccountState.xp_short) ------
# Log evidence (2026-10-22 02:30): "boomerang path 1 tier 5 needs 37500 XP,
# have 36108" and "bomb path 2 tier 5 needs 35000 XP, have 10885" were read
# again after every bot restart (6-25 s each time): the old cache was a
# module-level dict that each restart (29 code reloads that night) emptied.
# A tower's XP only grows when it is played, so a shortfall stays true until
# that tower plays a game (forget_short, called by the runner after each game)
# or, to be safe, for a day.
SHORT_TTL = 24 * 3600


def known_short(account, kind, path, tier, now=None):
    """True while (kind, path 1..3, tier) is known to be unaffordable: the
    menu showed tier t0 <= tier of that path costing more XP than the tower
    had (a higher tier needs t0 first, so it is out of reach too)."""
    rec = (account.xp_short or {}).get(kind)
    if not rec or (now or time.time()) - rec.get("at", 0) > SHORT_TTL:
        return False
    blocked = rec.get("paths", {}).get(str(path))
    return bool(blocked) and blocked[0] <= tier and rec.get("xp", 0) < blocked[1]


def note_short(account, kind, path, tier, cost, have):
    """Remember that the tower had `have` XP and the path's `tier` costs `cost`."""
    rec = account.xp_short.setdefault(kind, {"paths": {}})
    rec["xp"], rec["at"] = float(have), time.time()
    rec["paths"][str(path)] = [int(tier), int(cost)]


def forget_short(account, kinds):
    """These towers just played a game and earned XP: check them again."""
    for kind in kinds:
        account.xp_short.pop(kind, None)


def pending_upgrades(account, wanted):
    """{tower: [(path, tier)]} still worth a look in the Monkeys menu: not
    known unlocked and not known unaffordable. Empty -> skip the menu."""
    todo = {}
    for kind, path, tier in wanted:
        if account.upgrades(kind)[path - 1] >= tier or known_short(account, kind, path, tier):
            continue
        todo.setdefault(kind, []).append((path, tier))
    return todo


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
        # Decide before opening anything: the Monkeys menu used to be opened
        # (and closed again, ~3-4 s) before every game even when every needed
        # upgrade was already unlocked or known to be out of reach.
        by_tower = pending_upgrades(self.account, wanted)
        if not by_tower:
            return []
        if self.menus.identify() != "main_menu":
            return []
        self.inp.click(*MONKEYS_BUTTON)
        time.sleep(1.5)
        done = []
        try:
            for kind, items in by_tower.items():
                if not self.open_tower(kind):
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
                            note_short(self.account, kind, path, tier, cost, have)
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


def scan_owned(inp, menus):
    """Monkeys menu: towers whose card shows an 'XP:' total are owned (locked
    cards show a price instead). Leaves the menu on the last tab."""
    owned = set()
    for cat, pos in TABS.items():
        inp.click(*pos)
        time.sleep(0.8)
        words = menus.read()
        xps = [w for w in words if "xp" in norm(w.text) or re.search(r"\d[\d,.]{3,}", w.text)]
        for w in words:
            kind = T.find_tower(w.text)
            if not kind or T.TOWERS[kind]["category"] != cat:
                continue
            if any(abs(x.x - w.x) < 0.08 and 0.15 < x.y - w.y < 0.35 for x in xps):
                owned.add(kind)
    log.info("owned towers: %d (%s)", len(owned), ", ".join(sorted(owned)))
    return owned


def unlock_paragons(screen, inp, menus, account, towers):
    """Unlock the paragon of each tower in `towers` (all tier 5s unlocked,
    paragon not yet) whose tower XP pays for it - the point of the paragon
    focus. Starts and ends at the main menu. Each unlock is checked three
    ways before the click: the panel shows "UNLOCK FOR: N XP" (an XP price,
    never money), N is the paragon's price from data/tower_xp.json, and the
    tower's XP covers it; after it, the tree must turn purple. The XP read on
    screen also corrects the counted XP (towerxp.py). Returns the towers
    whose paragon was unlocked."""
    from .meta import paragon_tree
    from .planner import DEFAULT_CONFIG, load_tower_xp_prices
    prices = load_tower_xp_prices(DEFAULT_CONFIG.tower_xp_path)
    sp = XpSpender(screen, inp, menus, account)
    done = []
    if not towers or menus.identify() != "main_menu":
        return done
    inp.click(*MONKEYS_BUTTON)
    time.sleep(1.5)
    try:
        for kind in towers:
            price = getattr(prices.get(kind), "paragon_xp", 0)
            if not price or not sp.open_tower(kind):
                continue
            inp.click(0.5, 0.94)            # close a tooltip the opening click may have raised
            inp.move(0.97, 0.97)
            time.sleep(0.5)
            if paragon_tree(screen.grab()):
                account.paragons[kind] = True   # unlocked already
            else:
                inp.click(*PARAGON_COLUMN)
                time.sleep(0.8)
                cost, have = sp._cost(), sp._xp()
                if have is not None:
                    account.tower_xp[kind] = float(have)
                if cost is None or abs(cost - price) > PARAGON_PRICE_TOLERANCE * price:
                    log.info("%s: no paragon price on the panel (read %s, expected %s) - not clicking",
                             kind, cost, f"{price:,}")
                elif have is None or have < cost:
                    log.info("%s: paragon needs %s XP, the tower has %s", kind, f"{cost:,}", have)
                else:
                    inp.click(*TREE_UNLOCK)
                    time.sleep(1.5)
                    if paragon_tree(screen.grab()):
                        account.paragons[kind] = True
                        after = sp._xp()
                        account.tower_xp[kind] = float(after if after is not None else have - cost)
                        log.warning("PARAGON unlocked: %s (%s XP)", T.TOWERS[kind]["name"], f"{cost:,}")
                        done.append(kind)
                    else:
                        log.warning("%s: clicked UNLOCK for the paragon but the tree did not turn purple", kind)
            inp.click(*BACK)
            time.sleep(0.8)
    finally:
        for _ in range(3):
            if menus.identify() == "main_menu":
                break
            inp.click(*BACK)
            time.sleep(0.8)
    return done


def sync_all(screen, inp, menus, account, towers=None):
    """Read every owned tower's upgrade tree and store the true unlocked tiers.
    Used when an account is first seen (e.g. a higher-level save) and daily."""
    from .meta import paragon_tree, tiers_from_states, tree_states
    sp = XpSpender(screen, inp, menus, account)
    if menus.identify() != "main_menu":
        return {}
    inp.click(*MONKEYS_BUTTON)
    time.sleep(1.5)
    seen = {}
    try:
        if not towers:
            owned = scan_owned(inp, menus)
            if owned:
                account.unlocked_towers |= owned
        kinds = towers or [k for k in T.TOWERS if k in account.unlocked_towers]
        for i, kind in enumerate(kinds):
            status.set_state(f"reading upgrade trees: {T.TOWERS[kind]['name']} ({i + 1}/{len(kinds)})")
            if not sp.open_tower(kind):
                continue
            # the click that opened the tree may land on a node, whose tooltip
            # then hides part of the tree: click empty background to close it
            inp.click(0.5, 0.94)
            inp.move(0.97, 0.97)
            time.sleep(0.5)
            frame = screen.grab()
            # remembered for the planner's paragon focus (towers still short
            # of their paragon get XP-heavy games first)
            has_paragon = paragon_tree(frame)
            account.paragons[kind] = has_paragon
            if has_paragon:
                tiers = [5, 5, 5]
            else:
                tiers = tiers_from_states(tree_states(frame))
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
                counted = account.tower_xp.get(kind)
                if counted is not None and abs(counted - xp) > max(1000.0, 0.02 * xp):
                    # the games' counted XP (towerxp.py) against the game's own figure
                    log.info("%s tower XP: counted %s, the game shows %s", kind, f"{counted:,.0f}", f"{xp:,}")
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
