"""Lookin fab ("Win 100 games using a skin of any Hero"): equip a hero skin
the account already owns, once, on a hero the bot plays with. The wins then
come from normal play. Skins are cosmetic, so the skin stays on (the
planner never needs the default look) and nothing is ever bought.

What the HEROES screen shows (the bot's recordings, 1280x800,
rec_20261107_150700.mkv 0:36 and 0:39)
  * right edge, top: a bundle banner ("STARTER HERO SKIN BUNDLE", "HERO
    BUNDLE") - a real-money offer, inside BANNER: never clicked;
  * under it, a column of round skin icons at x = SKIN_X, the first at
    SKIN_Y0 and then every SKIN_STEP;
  * a skin the account does not own has a Monkey Money price under its
    icon ("2,500" for both Quincy skins); an owned skin has none (Obyn's
    three skins show a "New" ribbon and a "!" badge instead);
  * the "+" next to the Monkey Money total (top right) opens the real-money
    shop: never clicked.

The flow (one try a day at most, while the Lookin fab card is wanted)
  1. heroes.HeroPicker shows the hero (HERO_ORDER: the hero the bot has
     equipped, then the bot's usual heroes) and equips it;
  2. for each skin slot with an icon: read under it; a price (digits) means
     not owned - skipped without a click;
  3. click an owned skin's icon, read the SELECT button (HeroPicker.button);
     "select" -> click it and wait for "selected"; "selected" already ->
     done; anything else (a price, nothing) -> next slot;
  4. a shop-like screen at any point: back arrow, log, stop.
  Success is kept in logs/achievement_tasks.json (flag "skin_equipped"),
  so it is done once per account.

UNCERTAIN - to check live: that clicking an owned skin shows SELECT under
the picture (as for heroes), and that selecting it keeps the hero selected.
"""
import logging
import time

import cv2

from . import achtasks as A
from .vision import norm

log = logging.getLogger("heroskin")

SKIN_X = 0.922                       # centre of the skin column
SKIN_Y0 = 0.269                      # centre of the first skin icon
SKIN_STEP = 0.131                    # icon to icon
SKIN_SLOTS = 4                       # icons looked at, at most
SKIN_HALF = (0.035, 0.05)            # half size of an icon
PRICE_BELOW = (0.02, 0.085)          # rows under an icon centre where a price sits
BANNER = (0.80, 0.0, 1.0, 0.20)      # bundle offer + Monkey Money "+": never clicked
ICON_MIN_SAT = 0.25                  # share of saturated pixels in an icon box (empty: dark teal)
HERO_ORDER = ("obyn", "quincy", "gwendolin", "striker_jones", "benjamin", "ezili", "adora")
FLOW = "heroskin"


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


def heroes_to_try(account):
    """Owned heroes in the order tried: the equipped one, then HERO_ORDER."""
    owned = set(getattr(account, "unlocked_heroes", ()) or ())
    first = getattr(account, "selected_hero", None)
    order = ([first] if first else []) + [h for h in HERO_ORDER if h != first]
    return [h for h in order if h in owned or h == "quincy"]


class SkinEquipper:
    def __init__(self, screen, inp, menus, account, budget, sleep=time.sleep, picker=None):
        from .heroes import HeroPicker
        self.s, self.menus, self.account, self.budget = screen, menus, account, budget
        self.inp = A.CountingInput(inp, budget)
        self.sleep = sleep
        self.picker = picker or HeroPicker(screen, self.inp, menus, account)

    def _shop(self, words):
        return any(A.real_money(w.text) for w in words) and not all(
            in_banner((w.x, w.y)) for w in words if A.real_money(w.text))

    def try_hero(self, hero):
        """On the HEROES screen with `hero` shown: equip an owned skin.
        Returns "equipped", "none_owned" or "bailed: ..."."""
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
            self.sleep(1.0)
            words = self.menus.v.read((0.3, 0.0, 1.0, 1.0))
            if self._shop(words):
                return f"bailed: a shop-like screen after skin {k + 1}: {A.screen_text(words)}"
            state = self.picker.button()
            if state == "select":
                self.inp.click(*self.picker._select_position())
                end = time.time() + 2.0
                while time.time() < end and self.picker.button() != "selected":
                    self.sleep(0.15)
                state = self.picker.button()
            if state == "selected":
                log.info("achievement: Lookin fab - %s now wears owned skin %d", hero, k + 1)
                return "equipped"
            log.info("achievement: Lookin fab - %s skin %d shows %r, not SELECT - next", hero, k + 1, state)
        return "none_owned"

    def run(self):
        tried = []
        for hero in heroes_to_try(self.account)[:2]:
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
            if res.startswith("bailed"):
                break
        return "no owned skin: " + "; ".join(tried)


def run_if_due(screen, inp, menus, account, account_key, statuses=None, budget=None, equipper=None):
    """The runner's entry point on the main menu: one try a day while Lookin
    fab is wanted and no skin was equipped yet. Returns the result or None."""
    budget = budget or A.Budget(account_key)
    statuses = A.card_statuses() if statuses is None else statuses
    if not A.wanted((A.SKIN_CARD,), statuses) or budget.flag("skin_equipped"):
        return None
    if budget.used(FLOW + "_tries") >= 1:
        return None
    budget.add(FLOW + "_tries")
    log.info("achievement: Lookin fab - equipping an owned hero skin")
    try:
        res = (equipper or SkinEquipper(screen, inp, menus, account, budget)).run()
    except A.CapReached as e:
        res = f"cap: {e}"
    log.info("achievement: Lookin fab - %s", res)
    return res
