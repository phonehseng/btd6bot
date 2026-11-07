"""Lookin fab ("Win 100 games using a skin of any Hero"): equip a hero skin
on a hero the bot plays with - an owned one if there is one, else ONE skin
bought with Monkey Money (the owner allowed it on 2026-11-07: "doesn't
matter what it buys"). The wins then come from normal play. Skins are
cosmetic, so the skin stays on (the planner never needs the default look).

Buying (only after every hero in HERO_ORDER was checked and has no owned
skin; once ever per account)
  Quincy first (the hero the strategies name most). Click a skin icon; on
  its page the bottom button must say UNLOCK and show one whole Monkey
  Money amount (button_price: "UNLOCK FOR: 2,500"; a price with cents, or
  real-money wording anywhere outside the top banner, stops it) of at most
  MAX_SKIN_PRICE that fits today's achtasks Monkey Money cap. The Monkey
  Money total at the top right is read; the flag "skin_bought" is written
  BEFORE the click (so a crash cannot lead to a second purchase); UNLOCK is
  clicked; a confirmation is answered once (Yes/OK/Confirm/Buy) only if it
  shows no other amount; then the total must have dropped by exactly the
  price ("achievement: Lookin fab - bought ..."). Then SELECT/USE/EQUIP is
  clicked until SELECTED is read. Anything else: logged with the words read,
  back arrow, no second try. A capture is saved at every step.

What the HEROES screen shows (the bot's recordings, 1280x800,
rec_20261107_150700.mkv 0:36 and 0:39)
  * right edge, top: a bundle banner ("STARTER HERO SKIN BUNDLE", "HERO
    BUNDLE") - a real-money offer, inside BANNER: never clicked;
  * under it, a column of round skin icons at x = SKIN_X, the first at
    SKIN_Y0 and then every SKIN_STEP;
  * a Monkey Money price under an icon ("2,500") means not owned. A "New"
    ribbon can hide that price: Obyn's three skins showed "New" and no
    price, yet all three cost 2,500 (first live run, 2026-11-07 18:06).
  * the "+" next to the Monkey Money total (top right) opens the real-money
    shop: never clicked.

What clicking a skin icon opens (live run 2026-11-07 18:06,
rec_20261107_180600.mkv 0:52, 1280x800)
  A page of its own: the skin's name as the title ("MOUNTAIN GUARDIAN
  SKIN"), the skin at hero levels 3/10/20, a back arrow at the top left,
  and one big button at the bottom centre (SKIN_BUTTON). For a skin not
  owned that button reads "UNLOCK FOR: 2,500" (Monkey Money): never
  clicked. For an owned skin it is expected to read SELECT / SELECTED /
  EQUIP / USE - not seen yet, so those words are accepted only inside
  SKIN_BUTTON and anything else is logged.
  The first live run missed this page: it read the hero screen's button
  region (nothing there), then clicked the next "skin slots", which on this
  page are empty background.

The flow (one try a day, while the Lookin fab card is wanted)
  1. heroes.HeroPicker shows the hero (Obyn, then Quincy: the heroes the bot
     plays) and equips it; a capture is saved;
  2. each skin slot with an icon and no price under it is clicked; a
     capture is saved and the whole skin page is read;
  3. "UNLOCK FOR" or a price on the button: not owned - back arrow, and the
     hero screen must show the same hero again before the next slot;
     SELECT/EQUIP/USE: clicked, then SELECTED must be read; SELECTED:
     already worn; a shop-like page or an unknown one: back arrow, stop;
  4. every hero checked is remembered (flag "skins_checked"), so a hero
     whose skins are all priced is not opened again; when the bot's heroes
     have no owned skin the routine stops for good and says so: getting
     Lookin fab then needs a skin bought (2,500 MM each, an owner decision).
  Success is kept in logs/achievement_tasks.json (flag "skin_equipped").
"""
import logging
import re
import time

import cv2

from . import achtasks as A
from .vision import norm, save

log = logging.getLogger("heroskin")

SKIN_X = 0.922                       # centre of the skin column
SKIN_Y0 = 0.269                      # centre of the first skin icon
SKIN_STEP = 0.131                    # icon to icon
SKIN_SLOTS = 4                       # icons looked at, at most
SKIN_HALF = (0.035, 0.05)            # half size of an icon
PRICE_BELOW = (0.02, 0.085)          # rows under an icon centre where a price sits
BANNER = (0.80, 0.0, 1.0, 0.20)      # bundle offer + Monkey Money "+": never clicked
ICON_MIN_SAT = 0.25                  # share of saturated pixels in an icon box (empty: dark teal)
BACK_ARROW = (0.044, 0.055)          # top-left back arrow (hero screen and skin page)
# the skin page's big button ("UNLOCK FOR: 2,500" at 0.50, 0.875 on 1280x800)
SKIN_BUTTON = (0.36, 0.78, 0.64, 0.97)
SKIN_TITLE = (0.20, 0.0, 0.80, 0.11)
SELECT_WORDS = ("select", "selegt", "equip", "use", "wear")
SELECTED_WORDS = ("selected", "selegted", "equipped", "inuse", "wearing")
UNOWNED_WORDS = ("unlockfor", "unlock", "buy", "purchase")
# The heroes the bot plays, most used first: strategies/ name Quincy 162
# times and Obyn 40 (2026-11-07); a skin elsewhere earns nothing.
HERO_ORDER = ("quincy", "obyn")
FLOW = "heroskin"
_DIGITS = re.compile(r"\d")

# -- buying one skin -----------------------------------------------------------------
# The owner (2026-11-07 ~18:37): the bot may buy ONE hero skin with Monkey
# Money for Lookin fab. Once ever per account (flag "skin_bought", written
# before the click), only when no owned skin exists on the bot's heroes.
BUY_ONE_SKIN = True
MAX_SKIN_PRICE = 3000                # Monkey Money; also within achtasks.MM_PER_DAY left today
MM_REGION = (0.82, 0.0, 0.98, 0.10)  # the Monkey Money total, top right ("$213.833")
CONFIRM_WORDS = ("yes", "ok", "confirm", "buy", "unlock")
# A Monkey Money amount as OCR reads it: "2,500", "2.500", "@2.500" (the
# coin icon read as @), "$213.833" (the total). Whole numbers only.
_MM = re.compile(r"^\d{1,3}([.,]\d{3})*$")


def parse_mm(text):
    """A whole Monkey Money amount from OCR text, or None (a price with
    cents - real money - is None too)."""
    t = (text or "").strip().lstrip("@$£€ ").replace(" ", "")
    if not _MM.match(t):
        return None
    return int(re.sub(r"[.,]", "", t))


def mm_total(words):
    """The Monkey Money total at the top right, or None."""
    for w in words:
        if _inside(w, MM_REGION):
            v = parse_mm(w.text)
            if v is not None:
                return v
    return None


def button_price(words):
    """(UNLOCK word, price) of a skin page's button: the button must say
    UNLOCK and show one whole Monkey Money amount. (None, None) otherwise."""
    button = [w for w in words if _inside(w, SKIN_BUTTON)]
    unlock = next((w for w in button if norm(w.text).startswith("unlock")), None)
    prices = [p for p in (parse_mm(w.text) for w in button) if p is not None]
    if unlock is None or len(prices) != 1 or any(A.real_money(w.text) for w in button):
        return None, None
    return unlock, prices[0]


def slot_centres(n=SKIN_SLOTS):
    return [(SKIN_X, SKIN_Y0 + k * SKIN_STEP) for k in range(n)]


def has_icon(frame, centre):
    """Something colourful (a skin icon) at this slot."""
    h, w = frame.shape[:2]
    x0 = int((centre[0] - SKIN_HALF[0]) * w)
    x1 = int((centre[0] + SKIN_HALF[0]) * w)
    y0 = int((centre[1] - SKIN_HALF[1]) * h)
    y1 = int((centre[1] + SKIN_HALF[1]) * h)
    patch = frame[max(0, y0):y1, max(0, x0):x1]
    if patch.size == 0:
        return False
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 1] > 120) & (hsv[..., 2] > 150)).mean()) >= ICON_MIN_SAT


def price_region(centre):
    return (centre[0] - 0.06, centre[1] + PRICE_BELOW[0], centre[0] + 0.06, centre[1] + PRICE_BELOW[1])


def priced(words):
    """A Monkey Money price among the words under an icon ("2,500")."""
    return any(sum(c.isdigit() for c in norm(w.text)) >= 2 for w in words)


def in_banner(pt):
    return BANNER[0] <= pt[0] <= BANNER[2] and BANNER[1] <= pt[1] <= BANNER[3]


def _inside(w, region):
    return region[0] <= w.x <= region[2] and region[1] <= w.y <= region[3]


def skin_page(words):
    """Read a skin's own page. Returns (state, button word or None):
      "unowned"   the button says UNLOCK FOR / a price: never clicked
      "select"    SELECT / EQUIP / USE in the button region
      "selected"  SELECTED / EQUIPPED in the button region
      "shop"      real-money wording anywhere outside the banner
      "unknown"   none of these (logged with the words)"""
    if any(A.real_money(w.text) and not in_banner((w.x, w.y)) for w in words):
        return "shop", None
    button = [w for w in words if _inside(w, SKIN_BUTTON)]
    joined = "".join(norm(w.text) for w in button)
    if any(u in joined for u in UNOWNED_WORDS) or any(_DIGITS.search(w.text) for w in button):
        return "unowned", None
    for w in button:
        if norm(w.text) in SELECTED_WORDS:
            return "selected", w
    for w in button:
        if norm(w.text) in SELECT_WORDS:
            return "select", w
    return "unknown", None


class SkinEquipper:
    def __init__(self, screen, inp, menus, account, budget, sleep=time.sleep, picker=None,
                 capture_dir=None):
        from .heroes import HeroPicker
        self.s, self.menus, self.account, self.budget = screen, menus, account, budget
        self.inp = A.CountingInput(inp, budget)
        self.sleep = sleep
        self.picker = picker or HeroPicker(screen, self.inp, menus, account)
        self.capture_dir = capture_dir

    def _capture(self, what):
        """Evidence for the next look at this flow (a few a day)."""
        if self.budget.used("looks_skin") >= 20:
            return
        self.budget.add("looks_skin")
        try:
            folder = self.capture_dir or A.CAPTURE_DIR
            save(self.s.grab(), folder / f"skin_{what}_{time.strftime('%Y%m%d_%H%M%S')}.png")
        except Exception:
            pass

    def _back_to_hero(self, hero):
        """Leave a skin page with its back arrow; True once the hero screen
        shows `hero` again (else the next slot click could land anywhere)."""
        for _ in range(2):
            self.inp.click(*BACK_ARROW)
            self.sleep(1.2)
            if self.picker.shown_hero() == hero:
                return True
        return False

    def try_hero(self, hero):
        """On the HEROES screen with `hero` shown: equip an owned skin.
        Returns "equipped", "none_owned" or "bailed: ..."."""
        self._capture(f"{hero}_hero")
        frame = self.s.grab()
        for k, centre in enumerate(slot_centres()):
            if in_banner(centre) or not has_icon(frame, centre):
                continue
            below = self.menus.v.read(price_region(centre))
            if priced(below):
                log.info("achievement: Lookin fab - %s skin %d has a price (%s): not owned, not clicked",
                         hero, k + 1, A.screen_text(below))
                continue
            self.inp.click(*centre)
            self.sleep(1.5)
            self._capture(f"{hero}_skin{k + 1}")
            words = self.menus.v.read((0.0, 0.0, 1.0, 1.0))
            title = " ".join(w.text for w in words if _inside(w, SKIN_TITLE))
            state, button = skin_page(words)
            log.info("achievement: Lookin fab - %s skin %d page %r: %s; button area read: %s", hero, k + 1,
                     title, state, A.screen_text([w for w in words if _inside(w, SKIN_BUTTON)]) or "nothing")
            if state == "select":
                self.inp.click(button.x, button.y)
                self.sleep(1.5)
                self._capture(f"{hero}_skin{k + 1}_after_select")
                words = self.menus.v.read((0.0, 0.0, 1.0, 1.0))
                state, _ = skin_page(words)
                log.info("achievement: Lookin fab - after %r the button reads: %s", button.text,
                         A.screen_text([w for w in words if _inside(w, SKIN_BUTTON)]) or "nothing")
            if state == "selected":
                log.info("achievement: Lookin fab - %s now wears skin %d (%s)", hero, k + 1, title)
                self._back_to_hero(hero)
                return "equipped"
            if state in ("shop", "unknown"):
                log.warning("achievement: Lookin fab - %s skin %d: %s page, stopping; screen read: %s",
                            hero, k + 1, state, A.screen_text(words, 40))
                self._back_to_hero(hero)
                return f"bailed: {state} page after skin {k + 1}"
            # unowned, or SELECT that did not take: back to the hero for the next one
            if not self._back_to_hero(hero):
                return f"bailed: the {hero} screen did not come back after skin {k + 1}"
            frame = self.s.grab()
        return "none_owned"

    # -- buying one skin (owner's permission, 2026-11-07) -------------------------
    def _read_page(self):
        return list(self.menus.v.read((0.0, 0.0, 1.0, 1.0)))

    def _buy_on_page(self, hero, k, words):
        """On an unowned skin's page: buy it with Monkey Money if the price
        passes every check. Returns "bought", "not_bought" or "bailed: ..."."""
        title = " ".join(w.text for w in words if _inside(w, SKIN_TITLE)) or f"{hero} skin {k + 1}"
        unlock, price = button_price(words)
        if unlock is None or price is None:
            return f"bailed: no UNLOCK FOR button with a Monkey Money price ({A.screen_text(words)})"
        if price > MAX_SKIN_PRICE or not self.budget.allow("mm", price) or not self.budget.allow("purchases"):
            return f"bailed: {price} MM is over the cap (max {MAX_SKIN_PRICE}, {self.budget.left('mm')} left today)"
        before = mm_total(words)
        if before is None or before < price:
            return f"bailed: Monkey Money total not readable or too low ({before})"
        # once ever, even if the bot stops halfway: the flag goes first
        self.budget.set_flag("skin_bought", {"state": "clicking", "hero": hero, "skin": title,
                                             "price": price, "mm_before": before, "at": time.time()})
        log.info("achievement: Lookin fab - buying %r for %d MM (Monkey Money %d)", title, price, before)
        self.inp.click(unlock.x, unlock.y)
        self.sleep(2.0)
        self._capture(f"{hero}_skin{k + 1}_after_unlock")
        words = self._read_page()
        if any(A.real_money(w.text) and not in_banner((w.x, w.y)) for w in words):
            return self._bought_result(hero, title, price, before, words, "real-money wording after UNLOCK")
        if skin_page(words)[0] not in ("select", "selected"):
            # a confirmation question: confirmed once, only if it shows no other price
            ok = A.find_allowed(words, CONFIRM_WORDS)
            prices = {p for p in (parse_mm(w.text) for w in words if not _inside(w, MM_REGION)) if p}
            if ok is not None and prices <= {price}:
                log.info("achievement: Lookin fab - confirming %d MM via %r", price, ok.text)
                self.inp.click(ok.x, ok.y)
                self.sleep(2.0)
                self._capture(f"{hero}_skin{k + 1}_after_confirm")
                words = self._read_page()
        return self._bought_result(hero, title, price, before, words)

    def _bought_result(self, hero, title, price, before, words, why=None):
        """Settle a purchase by the Monkey Money total: it must drop by
        exactly the price."""
        after = mm_total(words)
        spent = None if after is None else before - after
        state = "bought" if spent == price else "not_bought" if spent == 0 else "unexpected"
        self.budget.set_flag("skin_bought", {"state": state, "hero": hero, "skin": title, "price": price,
                                             "mm_before": before, "mm_after": after, "at": time.time()})
        if state == "bought":
            self.budget.add("mm", price)
            self.budget.add("purchases")
            log.info("achievement: Lookin fab - bought %r for %d MM (Monkey Money %d -> %d)",
                     title, price, before, after)
            return "bought"
        log.warning("achievement: Lookin fab - purchase of %r for %d MM: %s (Monkey Money %s -> %s)%s; "
                    "no further buying; screen read: %s", title, price, state, before, after,
                    f" - {why}" if why else "", A.screen_text(words, 40))
        if spent:
            self.budget.add("mm", max(spent, 0))
        return f"bailed: {state}"

    def _equip_after_buy(self, hero, k):
        words = self._read_page()
        state, button = skin_page(words)
        if state == "select":
            self.inp.click(button.x, button.y)
            self.sleep(1.5)
            self._capture(f"{hero}_skin{k + 1}_after_select")
            words = self._read_page()
            state, _ = skin_page(words)
        log.info("achievement: Lookin fab - after buying, the button reads: %s",
                 A.screen_text([w for w in words if _inside(w, SKIN_BUTTON)]) or "nothing")
        return state == "selected"

    def buy_for(self, hero):
        """On the HEROES screen with `hero` shown: buy the first skin whose
        page passes the checks, then equip it. Returns "equipped",
        "bought" (not confirmed SELECTED), "none_for_sale" or "bailed: ..."."""
        self._capture(f"{hero}_hero_buy")
        frame = self.s.grab()
        for k, centre in enumerate(slot_centres()):
            if in_banner(centre) or not has_icon(frame, centre):
                continue
            self.inp.click(*centre)
            self.sleep(1.5)
            self._capture(f"{hero}_skin{k + 1}_buy")
            words = self._read_page()
            state, _ = skin_page(words)
            log.info("achievement: Lookin fab - %s skin %d page: %s; button area read: %s", hero, k + 1, state,
                     A.screen_text([w for w in words if _inside(w, SKIN_BUTTON)]) or "nothing")
            if state != "unowned":
                self._back_to_hero(hero)
                if state in ("shop", "unknown"):
                    return f"bailed: {state} page after skin {k + 1}"
                return "bailed: an owned skin turned up - equip it on the next run"
            res = self._buy_on_page(hero, k, words)
            if res == "bought":
                ok = self._equip_after_buy(hero, k)
                self._back_to_hero(hero)
                return "equipped" if ok else "bought"
            self._back_to_hero(hero)
            return res
        return "none_for_sale"

    def _buy(self):
        """No owned skin on the bot's heroes: buy one (once ever)."""
        for hero in heroes_to_try(self.account)[:1]:
            ok, origin = self.picker.meta._open_hero_picker()
            if not ok:
                return f"bailed: HEROES did not open (from {origin})"
            try:
                if not self.picker._find_and_equip(hero):
                    return f"bailed: {hero} not found"
                res = self.buy_for(hero)
            finally:
                self.picker.meta.to_main_menu()
            if res == "equipped":
                self.budget.set_flag("skin_equipped", {"hero": hero, "at": time.time(), "bought": True})
                return "bought and equipped a skin for " + hero
            return f"buy {hero}: {res}"
        return "no hero to buy a skin for"

    def _equip_bought(self, bought):
        """A skin was bought on an earlier run but SELECTED was not read: it is
        owned now, so the usual owned-skin pass equips it."""
        hero = bought.get("hero")
        ok, origin = self.picker.meta._open_hero_picker()
        if not ok:
            return f"bailed: HEROES did not open (from {origin})"
        try:
            res = self.try_hero(hero) if self.picker._find_and_equip(hero) else "not found"
        finally:
            self.picker.meta.to_main_menu()
        if res == "equipped":
            self.budget.set_flag("skin_equipped", {"hero": hero, "at": time.time(), "bought": True})
            return "equipped the bought skin on " + hero
        return f"bought skin on {hero} not equipped: {res}"

    def run(self):
        bought = self.budget.flag("skin_bought")
        if bought and bought.get("state") == "bought":
            return self._equip_bought(bought)
        checked = dict(self.budget.flag("skins_checked") or {})
        todo = [h for h in heroes_to_try(self.account) if h not in checked]
        if not todo:
            if bought or not BUY_ONE_SKIN:
                return "no owned skin on " + ", ".join(sorted(checked))
            return self._buy()
        tried = []
        for hero in todo[:2]:
            ok, origin = self.picker.meta._open_hero_picker()
            if not ok:
                return f"bailed: HEROES did not open (from {origin})"
            try:
                if not self.picker._find_and_equip(hero):
                    tried.append(f"{hero}: not found")
                    continue
                res = self.try_hero(hero)
            finally:
                self.picker.meta.to_main_menu()
            if res == "equipped":
                self.budget.set_flag("skin_equipped", {"hero": hero, "at": time.time()})
                return "equipped " + hero
            tried.append(f"{hero}: {res}")
            if res == "none_owned":
                checked[hero] = time.time()
                self.budget.set_flag("skins_checked", checked)
            else:
                break
        out = "no owned skin: " + "; ".join(tried)
        if BUY_ONE_SKIN and not [h for h in heroes_to_try(self.account) if h not in checked]:
            out += "; " + self._buy()
        return out


def heroes_to_try(account):
    """The bot's heroes the account owns, the equipped one first."""
    owned = set(getattr(account, "unlocked_heroes", ()) or ()) | {"quincy"}
    first = getattr(account, "selected_hero", None)
    order = ([first] if first in HERO_ORDER else []) + [h for h in HERO_ORDER if h != first]
    return [h for h in order if h in owned]


def run_if_due(screen, inp, menus, account, account_key, statuses=None, budget=None, equipper=None):
    """The runner's entry point on the main menu: one try a day while Lookin
    fab is wanted, no skin is equipped yet and a hero is left to check.
    Returns the result or None."""
    budget = budget or A.Budget(account_key)
    statuses = A.card_statuses() if statuses is None else statuses
    if not A.wanted((A.SKIN_CARD,), statuses) or budget.flag("skin_equipped"):
        return None
    checked = budget.flag("skins_checked") or {}
    bought = budget.flag("skin_bought")
    left = account is not None and [h for h in heroes_to_try(account) if h not in checked]
    if account is not None and not left and bought and bought.get("state") != "bought":
        return None                       # every hero checked, the one purchase is used up
    if account is not None and not left and not bought and not BUY_ONE_SKIN:
        return None                       # said once: the bot's heroes have no owned skin
    if budget.used(FLOW + "_tries") >= 1:
        return None
    budget.add(FLOW + "_tries")
    log.info("achievement: Lookin fab - equipping an owned hero skin")
    try:
        res = (equipper or SkinEquipper(screen, inp, menus, account, budget)).run()
    except A.CapReached as e:
        res = f"cap: {e}"
    log.info("achievement: Lookin fab - %s", res)
    if res.startswith("no owned skin") and not BUY_ONE_SKIN and account is not None and \
            not [h for h in heroes_to_try(account) if h not in (budget.flag("skins_checked") or {})]:
        log.warning("achievement: Lookin fab - none of the bot's heroes (%s) has an owned skin; "
                    "it needs a skin bought (2,500 MM each) - left to the owner", ", ".join(HERO_ORDER))
    return res
