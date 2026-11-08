"""Buy a cheap Power with Monkey Money when the account has none left to use,
for Power User / Empowered (the owner allowed Monkey Money for achievements
on 2026-11-07; in-game currency only).

When (run_if_needed decides, between games on the main menu)
  * a power card is wanted (achtasks.POWER_CARDS);
  * the last in-game look at the powers panel (powers.InGameExtras saves the
    flag "powers_seen") found NO owned Power, within SEEN_FRESH seconds - so
    the bot never buys while it still owns some;
  * today's Monkey Money (achtasks.MM_PER_DAY) and purchase caps allow it;
  * the flow has not failed FAILURES_PER_DAY times today.

The flow (only words of the allow-lists below are clicked)
  1. main menu -> the "INSTAS + POWERS" button (bottom row; its place
     INSTAS_POWERS_BUTTON is measured on the level-150 main menu,
     rec_20261107_165100.mkv 0:18);
  2. the POWERS tab, by its word, only inside TAB_ROW: the screen opens on
     FEATURED (live 2026-11-08 00:39), whose banners read "INSTA STORE" and
     "MAP CHALLENGE" - that page is neither judged nor clicked. From the
     Powers page on, store / real-money words are judged on the page's own
     words (page_words: tab row and Monkey Money corner left out);
  3. the name of a cheap Power (BUY_ORDER);
  4. its price: a whole number (no cents, no currency sign) between
     MIN_PRICE and MAX_PRICE that fits today's cap, read next to or under
     the name. A price with cents, a store/offer/bundle word anywhere on the
     screen, or no price read: bail out;
  5. a confirmation question: confirmed with Yes/OK/Buy/Confirm only when
     it shows the same price and no real-money wording;
  6. the Monkey Money total is read before and after (runner.read_mm): the
     spend logged is the real difference, and a difference above the price
     read stops all buying for the day.
  Then back to the main menu with the on-screen back arrow (never Esc).

No recording shows this screen (the bot never opened it), so the first
runs are the calibration: every screen is saved under
logs/achievement_captures/ (a few a day) with the words read.
"""
import logging
import re
import time

from . import achtasks as A
from .vision import norm, save

log = logging.getLogger("powershop")

INSTAS_POWERS_BUTTON = (0.748, 0.885)     # the bolt icon above its "INSTAS + POWERS" caption
BACK_ARROW = (0.044, 0.055)
SEEN_FRESH = 3 * 86400                    # how recent the "no owned Power" look must be
MIN_PRICE, MAX_PRICE = 10, 500            # a single cheap Power, in Monkey Money
BUY_ORDER = ("roadspikes", "gluetrap", "camotrap", "monkeyboost", "moabmine", "thrive")
TABS = ("powers",)
# The screen's tab row and Monkey Money corner (live capture 2026-11-08
# 00:39, shop_opened_20261108_003930.png, 1920x1200): FEATURED (0.32, 0.055),
# POWERS (0.50, 0.055), INSTA MONKEYS (0.68, 0.055); total "$215,150" and
# its "+" at the top right.
TAB_ROW = (0.20, 0.0, 0.79, 0.11)
MM_CORNER = (0.79, 0.0, 1.0, 0.11)
CONFIRM = ("yes", "ok", "buy", "confirm", "purchase")
DECLINE = ("cancel", "no", "close", "nothanks")
SETTLE = 1.0
PRICE = re.compile(r"^\d{1,3}(,\d{3})?$")
SHOP_WORDS = ("store", "bundle", "offer", "getnow", "dlc", "bestvalue", "specialoffer", "usd")


def is_due(budget, statuses, now=None):
    """(due, why) for the log."""
    now = time.time() if now is None else now
    if not A.wanted(A.POWER_CARDS, statuses):
        return False, "no power card wanted"
    seen = budget.flag("powers_seen")
    if not seen or now - seen.get("at", 0) > SEEN_FRESH:
        return False, "the powers panel was not read lately"
    owned = seen.get("owned")
    if owned:
        # a count of badged Power icons (powers.power_badges); older flags held names
        return False, "the account still owns %s Power(s)" % (
            owned if isinstance(owned, int) else ", ".join(owned))
    if budget.resting("powershop"):
        return False, "failed too often today"
    if not budget.allow("purchases") or budget.left("mm") < MIN_PRICE:
        return False, "daily Monkey Money cap reached"
    return True, "no owned Power left"


def mm_amount(text):
    """A whole Monkey Money amount ("35", "1,000", "@35" - OCR reads the
    coin icon as @), or None. Real-money prices have cents and never match."""
    t = (text or "").strip().replace(" ", "").lstrip("@")
    return int(t.replace(",", "")) if PRICE.match(t) else None


def page_words(words):
    """The words of the page itself: the tab row (FEATURED / POWERS /
    INSTA MONKEYS) and the Monkey Money corner (the total and its "+",
    which opens the real-money shop and is never clicked) left out."""
    def inside(w, r):
        return r[0] <= w.x <= r[2] and r[1] <= w.y <= r[3]
    return [w for w in words if not inside(w, TAB_ROW) and not inside(w, MM_CORNER)]


def read_price(words, near, limit):
    """The Monkey Money price shown for the Power named by word `near`: a
    whole number in MIN_PRICE..min(MAX_PRICE, limit), to the right of or
    under the name. None if none is read."""
    best = None
    for w in words:
        v = mm_amount(w.text)
        if v is None:
            continue
        if not (MIN_PRICE <= v <= min(MAX_PRICE, limit)):
            continue
        if abs(w.x - near.x) <= 0.12 and -0.02 <= w.y - near.y <= 0.2:
            d = abs(w.x - near.x) + abs(w.y - near.y)
            if best is None or d < best[0]:
                best = (d, w, v)
    return (best[1], best[2]) if best else (None, None)


def shop_page(words):
    """Real money or a store anywhere on the screen."""
    for w in words:
        n = norm(w.text)
        if A.real_money(w.text) or any(s in n for s in SHOP_WORDS):
            return True
    return False


class PowerShop:
    def __init__(self, screen, inp, menus, budget, read_mm, sleep=time.sleep):
        self.s, self.menus, self.budget = screen, menus, budget
        self.inp = A.CountingInput(inp, budget)
        self.read_mm = read_mm
        self.sleep = sleep

    def _look(self, what):
        self.sleep(SETTLE)
        self.menus.identify()
        words = list(self.menus.words)
        log.info("achievement: power shop, %s: %s", what, A.screen_text(words))
        if self.budget.used("looks_shop") < A.LOOKS_PER_DAY:
            self.budget.add("looks_shop")
            try:
                save(self.s.grab(), A.CAPTURE_DIR / f"shop_{what}_{time.strftime('%Y%m%d_%H%M%S')}.png")
            except Exception:
                pass
        return words

    def _home(self):
        for _ in range(4):
            if self.menus.identify() == "main_menu":
                return True
            self.inp.click(*BACK_ARROW)
            self.sleep(SETTLE)
        return False

    def _bail(self, why, words):
        log.warning("achievement: power shop - bailing out (%s); screen read: %s", why, A.screen_text(words))
        self.budget.add("powershop_failures")
        w = A.find_allowed(words, DECLINE)
        if w is not None:
            self.inp.click(w.x, w.y)
            self.sleep(SETTLE)
        self._home()
        return f"bailed: {why}"

    def buy_one(self):
        """Buy one cheap Power. Returns "bought <power> <mm>", or a reason."""
        if self.menus.identify() != "main_menu":
            return "not_on_main_menu"
        mm_before = self.read_mm()
        if mm_before is None:
            return "Monkey Money not readable"
        self.inp.click(*INSTAS_POWERS_BUTTON)
        words = self._look("opened")
        # The screen opens on FEATURED, whose own banners say "INSTA STORE"
        # and "MAP CHALLENGE" (live 2026-11-08 00:39): nothing on it is judged
        # or clicked except the POWERS tab, by its word, inside the tab row.
        tab = A.find_allowed(words, TABS, region=TAB_ROW)
        if tab is None:
            return self._bail("no POWERS tab read in the tab row", words)
        self.inp.click(tab.x, tab.y)
        words = self._look("powers_tab")
        if shop_page(page_words(words)):
            return self._bail("a store or real-money page", words)
        name = A.find_allowed(page_words(words), BUY_ORDER)
        if name is None:
            return self._bail("no cheap Power name read", words)
        limit = self.budget.left("mm")
        self.inp.click(name.x, name.y)
        words = self._look("power")
        if shop_page(page_words(words)):
            return self._bail("a store or real-money page", words)
        name2 = A.find_allowed(page_words(words), (norm(name.text),)) or name
        price_w, price = read_price(page_words(words), name2, limit)
        if price_w is None:
            return self._bail("no Monkey Money price within the cap", words)
        log.info("achievement: power shop - %s costs %d MM (today %d of %d MM spent)",
                 name.text, price, self.budget.used("mm"), A.MM_PER_DAY)
        self.inp.click(price_w.x, price_w.y)
        # At most one confirmation, then at most one plain OK (a "purchased"
        # notice). A loop over "buy" words could buy again and again.
        words = page_words(self._look("confirm"))
        if shop_page(words):
            return self._bail("a store or real-money page", words)
        ok = A.find_allowed(words, CONFIRM)
        if ok is not None:
            prices = {v for v in (mm_amount(w.text) for w in words) if v is not None}
            if prices and price not in prices:
                return self._bail(f"the question shows another price {sorted(prices)}", words)
            log.info("achievement: power shop - confirming %d MM via %r", price, ok.text)
            self.inp.click(ok.x, ok.y)
            words = page_words(self._look("after_confirm"))
            notice = A.find_allowed(words, ("ok", "close", "continue"))
            if notice is not None and not shop_page(words):
                self.inp.click(notice.x, notice.y)
                self.sleep(SETTLE)
        self._home()
        mm_after = self.read_mm()
        spent = None if mm_after is None else mm_before - mm_after
        if spent is None:
            # not readable: count the price read, to stay under the cap
            spent = price
            log.warning("achievement: power shop - Monkey Money unreadable afterwards; counting %d", price)
        if spent > price:
            log.error("achievement: power shop spent %d MM, more than the %d read - no more buying today",
                      spent, price)
            self.budget.add("powershop_failures", A.FAILURES_PER_DAY)
        if spent <= 0:
            log.warning("achievement: power shop - Monkey Money unchanged, nothing was bought")
            self.budget.add("powershop_failures")
            return "nothing bought"
        self.budget.add("mm", spent)
        self.budget.add("purchases")
        self.budget.set_flag("powers_seen", None)    # look in a game again before buying more
        log.info("achievement: bought %s for %d MM (today %d of %d MM)", name.text, spent,
                 self.budget.used("mm"), A.MM_PER_DAY)
        return f"bought {norm(name.text)} {spent}"


def run_if_needed(screen, inp, menus, account_key, read_mm, statuses=None, budget=None):
    """The runner's entry point on the main menu. Returns the result, or None
    when nothing was tried."""
    budget = budget or A.Budget(account_key)
    statuses = A.card_statuses() if statuses is None else statuses
    due, why = is_due(budget, statuses)
    if not due:
        log.debug("achievement: power shop not due (%s)", why)
        return None
    log.info("achievement: buying a Power with Monkey Money (%s)", why)
    try:
        return PowerShop(screen, inp, menus, budget, read_mm).buy_one()
    except A.CapReached as e:
        log.warning("achievement: power shop - %s", e)
        return "cap"
