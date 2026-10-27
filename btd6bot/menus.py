"""Menu screens: recognising where we are and getting where we want to be.

Screens are recognised from OCR keywords (robust to art/event changes) and
buttons are clicked by their text where possible. Hard rules:
  * never click a Continue that costs Monkey Money (defeat screen)
  * never press Esc (other programs treat a global Esc as "stop")
"""
import logging
import re
import time

from .vision import Vision, norm

log = logging.getLogger("menus")

# screen -> list of keyword groups; all groups must match (any word within a group)
SCREENS = [
    # the game's own crash dialog: "ERROR - We've encountered an unexpected
    # error ... EXIT" (2026-10-23, Another Brick: an ArgumentNullException in
    # the map's OnClickHandler). Over a match the HUD still shows, so it must
    # come before everything else, or the bot thinks it is playing.
    ("game_error", [["unexpectederror", "encounteredan", "contactsupport"], ["exit"]]),
    # a mode's intro box whose only button is a green Play arrow with no text
    # (Apopalypse: "Ever increasing Bloon waves, no breaks at the end of each
    # round. How far can you get?"); it comes before the map loads, so the
    # game never starts until the arrow is pressed (runner._press_intro_play)
    ("mode_intro_play", [["everincreasing", "nobreaksattheend", "howfarcanyouget"]]),
    # after a win during a collection event (title "COLLECTION EVENT"; the
    # font's C reads as G): a crate fills up, and a full one shows COLLECT
    ("collection_event", [["collectionevent", "collegtionevent"]]),
    # opening an event crate: "INSTA MONKEY! New <tower> 0-2-2" over a card
    ("insta_reward", [["instamonkey"]]),
    # the word alone is not enough: the Legends screen says "defeat the Bloons"
    ("defeat", [["defeat", "gameover", "bloonsleaked", "youlost"], ["restart", "home", "tryagain", "continue"]]),
    # HEROES screen: SELECT/SELECTED (OCR often reads the C as a G) and the
    # hero's "Ingame cost:", which the upgrade tree shows too - so it goes first
    ("hero_select", [["select", "selegt"], ["ingamecost"]]),
    ("upgrade_tree", [["unlockall", "ingamecost", "appliestothismonkey"]]),
    ("profile", [["overallstats", "topmonkeys", "topheroes", "publicstats"]]),
    ("account", [["yourninjakiwiaccount", "signin", "resetpassword"]]),
    ("victory", [["victory", "vigtory", "congratulations", "completedthistrack", "monkeystar"]]),
    # "CHOOSE A MONKEY TO UNLOCK" - not just "to unlock" (map cards say "click to unlock")
    ("tower_choice", [["chooseamonkey", "choosea"], ["unlock"]]),
    ("level_up", [["levelup"]]),
    ("hero_unlock", [["tryme", "nextgame"]]),
    ("pause", [["pause"], ["restart"], ["home"]]),
    ("restart_confirm", [["restart?", "sureyouwish"]]),
    # NB the difficulty screen can show a "Continue saved game?" banner; that is
    # not this prompt (which appears after picking a mode over an existing save)
    ("overwrite", [["overwrite", "existingsave"]]),
    # difficulty first: its "continue saved game" banner can say "Standard"
    ("difficulty", [["easy"], ["medium"], ["hard"]]),
    ("mode_select", [["standard"], ["rewards", "sandbox"]]),
    ("map_select", [["beginner"], ["intermediate"], ["expert"]]),
    ("hero_select", [["select"], ["heroes", "hero"]]),
    ("monkeys_menu", [["primary"], ["military"], ["magic"], ["support"]]),
    # title screen after the game reloads / reconnects: "WELCOME TO BLOONS ... START"
    ("title", [["welcometo", "anepicadventure", "anepigadventureof"], ["start"]]),
    ("main_menu", [["play"], ["monkeys"], ["heroes"]]),
]

POPUP_BUTTONS = ["ok", "collect", "claim", "continue", "next", "close", "gotit", "awesome", "yes"]
# After a win, "Review Map" hides the Victory screen; it comes back through a
# blue CONTINUE button in the bottom-right corner (caption at 0.93, 0.93 of
# the window) whose magnifier icon, not its caption, takes the click.
REVIEW_MAP_CORNER = (0.85, 0.85)
REVIEW_MAP_ICON_ABOVE = 0.065
# How OCR misreads some button words in the game's font (its C looks like a
# G or an I): find() accepts these spellings for the key on the left.
OCR_VARIANTS = {"collect": ("collegt", "colleci"), "select": ("selegt",), "selected": ("selegted",)}
# never click anything containing these (real-money or Monkey Money purchases)
FORBIDDEN = ["unlockall", "buy", "purchase", "store", "bundle", "offer", "usd", "insta", "powers",
             "trophystore", "continuefor", "signin", "signup", "resetpassword", "password", "logout",
             "deleteaccount",
             # the Legends screen sells DLC: "GET NOW $9.99" (reached by stray
             # clicks on 2026-10-22 - never clicked, but never clickable)
             "getnow", "dlc"]
# A price in real money: "$9.99", "4,99 EUR". Monkey Money and in-game cash
# never have cents, so two decimals mark real money.
_REAL_PRICE = re.compile(r"\d[.,]\d\d\b")


def forbidden(text):
    n = norm(text)
    return any(f in n for f in FORBIDDEN) or bool(_REAL_PRICE.search(text or ""))


CONFIRM_WORDS = ("yes", "ok", "confirm", "continue", "buy", "purchase", "unlock")
SPEND_WORDS = ("areyousure", "purchase", "buy", "spend", "cost", "for$")
PRICE_WORDS = ("monkeymoney", "$")


def page_forbidden(words):
    """A purchase confirmation: spending wording next to a price. On such a page
    no confirming button may be clicked (Monkey Money or real money)."""
    joined = " ".join(norm(w.text) for w in words)
    return any(sw in joined for sw in SPEND_WORDS) and any(pw in joined for pw in PRICE_WORDS)


class Menus:
    def __init__(self, screen, inp, game=None):
        self.s = screen
        self.inp = inp
        self.v = Vision(screen)
        self.g = game
        self.words = []

    def has_badge(self, cx, cy, dx=0.05, up=0.11, frame=None):
        """True when the game's red '!' notification badge sits at the
        top-right of the button centred at (cx, cy) (fractions). The game
        shows it on Monkey Knowledge when points can be spent and on the
        achievements ribbon when a reward can be claimed. Measured on
        docs/screens/after_home.jpg: badge windows hold ~3-4% bright red,
        plain buttons 0%."""
        import cv2
        import numpy as np
        f = frame if frame is not None else self.s.grab()
        h, w = f.shape[:2]
        x0, x1 = int(cx * w), int(min(1.0, cx + dx) * w)
        y0, y1 = int(max(0.0, cy - up) * h), int(cy * h)
        if x1 <= x0 or y1 <= y0:
            return False
        hsv = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        red = ((hsv[..., 0] < 8) | (hsv[..., 0] > 172)) & (hsv[..., 1] > 150) & (hsv[..., 2] > 170)
        white = (hsv[..., 1] < 40) & (hsv[..., 2] > 220)
        return bool(red.mean() > 0.012 and white.mean() > 0.003)

    def read(self, scale=0.5):
        """OCR the whole screen (downscaled for speed)."""
        import cv2
        f = self.s.grab()
        small = cv2.resize(f, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        self.words = self.v.read((0, 0, 1, 1), img=small)
        return self.words

    def has(self, *keys, words=None):
        words = self.words if words is None else words
        ks = [norm(k) for k in keys]
        return any(k in norm(w.text) for w in words for k in ks)

    def find(self, *keys, words=None, region=None, exact=False):
        """First word matching a key. A word that IS a key beats one that only
        contains it: the Collection Event screen's title "COLLECTION EVENT"
        contains "collect", and the bot clicked the title four times instead
        of the COLLECT button below it."""
        words = self.words if words is None else words
        if region:
            words = [w for w in words if region[0] <= w.x <= region[2] and region[1] <= w.y <= region[3]]
        ks = []
        for k in map(norm, keys):
            ks += [k, *OCR_VARIANTS.get(k, ())]
        for k in ks:                       # 1. whole-word matches, keys in order
            for w in words:
                if k == norm(w.text):
                    return w
        if exact:
            return None
        for k in ks:                       # 2. then words containing a key
            for w in words:
                if len(k) > 3 and k in norm(w.text):
                    return w
        return None

    def identify(self, read=True):
        if read:
            self.read()
        for name, groups in SCREENS:
            if all(self.has(*g) for g in groups):
                return name
        if self.in_game():
            return "in_game"
        if self.reward_cards():
            return "reward_cards"     # opening an event crate: cards on black
        return "unknown"

    def wait_for(self, targets, timeout=6.0, cheap_in_game=True):
        """Poll until one of `targets` (screen names) shows; return it, or the
        last screen seen on timeout. Replaces fixed sleeps after clicks."""
        targets = {targets} if isinstance(targets, str) else set(targets)
        end = time.time() + timeout
        st = "unknown"
        while True:
            if cheap_in_game and "in_game" in targets and self.in_game():
                return "in_game"
            st = self.identify()
            if st in targets or time.time() >= end:
                return st
            time.sleep(0.15)

    def in_game(self):
        from .templates import classify
        best, scores = classify(self.s.grab(), ["play_idle", "play_run", "play_fast"],
                                (0.905, 0.835, 1.0, 0.975))
        return scores[best] > 0.75

    def click_word(self, *keys, region=None, dy=0.0):
        w = self.find(*keys, region=region)
        if not w or forbidden(w.text):
            return False
        if page_forbidden(self.words) and any(norm(w.text).startswith(c) for c in CONFIRM_WORDS):
            log.warning("refusing to click %r on a purchase screen", w.text)
            return False
        log.info("click %r", w.text)
        self.inp.click(w.x, w.y + dy)
        time.sleep(0.25)
        return True

    # -- popups ---------------------------------------------------------------
    def dismiss_popup(self):
        """Close whatever simple popup is up. Never on a defeat screen."""
        if self.has("defeat", "gameover", "bloonsleaked"):
            return False
        # a screen offering Restart + Home is an end-of-game screen: its
        # Continue/Yes may be a paid revive, so never use those here
        endgame = self.has("restart") and self.has("home") and not self.has("pause")
        if page_forbidden(self.words):
            # never confirm a purchase: back out with cancel / no / close instead
            for b in ("cancel", "no", "close", "back"):
                w = self.find(b)
                if w and not forbidden(w.text):
                    log.warning("purchase screen - backing out via %r", w.text)
                    self.inp.click(w.x, w.y)
                    time.sleep(0.6)
                    return True
            log.warning("purchase screen with no way out found - not clicking")
            return False
        for b in POPUP_BUTTONS:
            if endgame and b in ("continue", "yes", "ok"):
                continue
            w = self.find(b)
            if w and w.conf > 0.6 and len(norm(w.text)) <= len(b) + 3 and not forbidden(w.text):
                x, y = w.x, w.y
                if b == "continue" and x > REVIEW_MAP_CORNER[0] and y > REVIEW_MAP_CORNER[1]:
                    # "Review Map" after a win: only the magnifier icon above
                    # the caption takes the click (Rake Easy: 20 minutes of
                    # clicks on the caption did nothing)
                    y -= REVIEW_MAP_ICON_ABOVE
                log.info("dismiss popup via %r", w.text)
                self.inp.click(x, y)
                time.sleep(0.7)
                return True
        return False

    # -- level up / tower choice -------------------------------------------------
    def handle_level_up(self):
        self.inp.click(0.5, 0.5)
        time.sleep(1.2)

    def handle_tower_choice(self, choose):
        """Carousel: centre item is selected; side items rotate in when clicked.

        choose(category, offered_names) -> preferred display name.
        """
        title = ""
        for w in self.words:
            n = norm(w.text)
            if n.endswith("monkeys") and w.y < 0.12:
                title = n.replace("monkeys", "")
        offered = []
        target = None
        name = ""
        # Step one item at a time (click the right-hand neighbour) and read the
        # centred name each time. Lap 1 aims for the first-seen preference but
        # records every tower offered; if the lap ends without landing on it,
        # re-choose from the full list and go round once more.
        for lap in range(2):
            for attempt in range(8):
                self.read(scale=0.6)
                name_w = self.find_center_name()
                name = name_w.text if name_w else ""
                if name and norm(name) not in map(norm, offered):
                    offered.append(name)
                if target is None and offered:
                    target = choose(title, offered)
                if not self.has("choosea", "chooseamonkey"):
                    log.warning("carousel: no longer on the tower-choice screen - aborting")
                    return ""
                log.info("carousel lap %d step %d: centre=%r target=%r", lap, attempt, name, target)
                if target and norm(target) == norm(name):
                    break
                if lap == 0 and attempt == 0:
                    try:  # what the carousel looks like, for calibration
                        from .vision import save
                        save(self.s.grab(), "logs/carousel.png")
                    except Exception:
                        pass
                self.inp.click(0.745, 0.45)
                time.sleep(0.9)
            else:
                if len(offered) == 1:
                    # a whole lap showed one tower: it is the only one left to unlock
                    log.info("carousel: only %r offered", offered[0])
                    name = offered[0]
                    break
                # never reached the target: pick again knowing everything offered
                target = choose(title, offered) if offered else None
                if target is None:
                    break  # nothing we prefer is offered: take the centred one
                log.warning("carousel: target not reached; offered %s -> retry for %r", offered, target)
                continue
            break
        self.last_offered = list(offered)
        log.info("unlocking %s (%s)", name, title)
        self.inp.click(0.5, 0.938)
        time.sleep(2.0)
        return name

    def find_center_name(self):
        cands = [w for w in self.words if 0.75 < w.y < 0.83 and 0.3 < w.x < 0.7]
        return max(cands, key=lambda w: w.conf) if cands else None

    # -- end of game ----------------------------------------------------------------
    def leave_victory(self):
        """From the victory screen back to the main menu."""
        for _ in range(6):
            st = self.identify()
            if st == "main_menu":
                return True
            if st in ("collection_event", "reward_cards", "insta_reward"):
                self.handle_collection_event()
                continue
            # buttons are icons above their labels; the label is not clickable
            if self.click_word("home", dy=-0.08):
                if self.wait_for("main_menu", timeout=8) == "main_menu":
                    return True
                continue
            if self.click_word("next", "continue", "collect"):
                self.wait_for({"victory", "main_menu"}, timeout=3)
                continue
            self.inp.click(0.5, 0.85)
            time.sleep(0.5)
        return False

    # -- collection events ---------------------------------------------------------
    # Calibrated live (v57.3, 2026-10-22): COLLECT opens the crate; a screen
    # with NO text shows face-down cards (blue tiles with a "?"); clicking one
    # shows "INSTA MONKEY! New ..." and a click anywhere closes that; when
    # every card is turned the event screen returns (crate at 0/N) with a
    # PLAY button. Free rewards: nothing here costs anything.
    CARD_BLUE = ((100, 150, 90), (118, 255, 230))   # face-down card, OpenCV HSV
    COLLECT_REGION = (0.35, 0.56, 0.65, 0.72)       # the COLLECT button under the crate
    BACK_ARROW = (0.044, 0.055)                     # top-left back arrow of menu screens

    def reward_cards(self, frame=None):
        """Centres (fx, fy) of the cards on a crate-opening screen, left to
        right: blue tiles about a sixth of the screen high."""
        import cv2
        import numpy as np
        if frame is None and getattr(self, "s", None) is None:
            return []                  # no screen (offline tests)
        f = frame if frame is not None else self.s.grab()
        h, w = f.shape[:2]
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        if np.median(hsv[:, :, 2]) > 40:
            return []                  # the cards screen is almost black around the cards
        mask = cv2.inRange(hsv, *self.CARD_BLUE)
        n, _, stats, cen = cv2.connectedComponentsWithStats(mask)
        return sorted((cen[i][0] / w, cen[i][1] / h) for i in range(1, n)
                      if stats[i, cv2.CC_STAT_AREA] > 0.004 * w * h)

    def handle_collection_event(self, max_steps=20):
        """From the collection-event screen, the cards screen or an "INSTA
        MONKEY!" popup: collect a full crate, turn every card, and leave the
        event screen. Returns True when none of these screens is up."""
        turned = set()
        self._event_backs = 0
        for _ in range(max_steps):
            st = self.identify()
            if st == "insta_reward":
                self.inp.click(0.5, 0.5)            # close the popup
                time.sleep(1.2)
            elif st == "reward_cards":
                cards = [c for c in self.reward_cards() if (round(c[0], 2), round(c[1], 2)) not in turned]
                if not cards:
                    self.inp.click(0.5, 0.5)
                    time.sleep(1.0)
                    continue
                turned.add((round(cards[0][0], 2), round(cards[0][1], 2)))
                self.inp.click(*cards[0])
                time.sleep(1.5)
            elif st == "collection_event":
                # COLLECT shows only under a full crate, and only as the whole
                # word: the title "COLLECTION EVENT" contains "collect", and a
                # partial match clicked it 5,576 times over 4.7 hours while
                # the crate sat at 0/20 (2026-10-22 07:41-12:25)
                w = self.find("collect", region=self.COLLECT_REGION, exact=True)
                if w is not None and not forbidden(w.text):
                    log.info("collection event: crate full - collecting")
                    self.inp.click(w.x, w.y)
                    time.sleep(2.0)
                    continue
                # Nothing to collect: the back arrow (top left, shown while
                # the crate is not full) returns to the main menu. PLAY is
                # only a last resort: it opens map select, whose back arrow
                # leads straight back here (seen looping on 2026-10-22).
                left_by_back = getattr(self, "_event_backs", 0) < 2
                if left_by_back:
                    self._event_backs = getattr(self, "_event_backs", 0) + 1
                    self.inp.click(*self.BACK_ARROW)
                elif not self.click_word("play"):
                    self.inp.click(0.94, 0.97)
                time.sleep(1.5)
            else:
                if turned:
                    log.info("collection event: %d reward cards turned", len(turned))
                return True
        return False

    def leave_defeat(self):
        """Defeat: go home. NEVER the paid continue."""
        for _ in range(4):
            st = self.identify()
            if st == "main_menu":
                return True
            if self.click_word("home", dy=-0.08):
                if self.wait_for("main_menu", timeout=8) == "main_menu":
                    return True
                continue
            time.sleep(0.5)
        return False
