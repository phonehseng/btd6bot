"""Menu screens: recognising where we are and getting where we want to be.

Screens are recognised from OCR keywords (robust to art/event changes) and
buttons are clicked by their text where possible. Hard rules:
  * never click a Continue that costs Monkey Money (defeat screen)
  * never press Esc (it would stop a supervising Claude session)
"""
import logging
import time

from .vision import Vision, norm

log = logging.getLogger("menus")

# screen -> list of keyword groups; all groups must match (any word within a group)
SCREENS = [
    ("defeat", [["defeat", "gameover", "bloonsleaked", "youlost"]]),
    ("upgrade_tree", [["unlockall", "ingamecost", "appliestothismonkey"]]),
    ("victory", [["victory"]]),
    ("tower_choice", [["choosea", "tounlock"], ["unlock"]]),
    ("level_up", [["levelup"]]),
    ("pause", [["pause"], ["restart"], ["home"]]),
    ("restart_confirm", [["restart?", "sureyouwish"]]),
    ("overwrite", [["overwrite", "existingsave", "savedgame"]]),
    ("mode_select", [["standard"], ["rewards", "sandbox"]]),
    ("difficulty", [["easy"], ["medium"], ["hard"]]),
    ("map_select", [["beginner"], ["intermediate"], ["expert"]]),
    ("hero_select", [["select"], ["heroes", "hero"]]),
    ("main_menu", [["play"], ["monkeys"], ["heroes"]]),
]

POPUP_BUTTONS = ["ok", "collect", "claim", "continue", "next", "close", "gotit", "awesome", "yes"]
# never click anything containing these (real-money or Monkey Money purchases)
FORBIDDEN = ["unlockall", "buy", "purchase", "store", "bundle", "offer", "usd", "insta", "powers",
             "trophystore", "continuefor"]


def forbidden(text):
    n = norm(text)
    return any(f in n for f in FORBIDDEN)


class Menus:
    def __init__(self, screen, inp, game=None):
        self.s = screen
        self.inp = inp
        self.v = Vision(screen)
        self.g = game
        self.words = []

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

    def find(self, *keys, words=None, region=None):
        words = self.words if words is None else words
        ks = [norm(k) for k in keys]
        for k in ks:
            for w in words:
                if region and not (region[0] <= w.x <= region[2] and region[1] <= w.y <= region[3]):
                    continue
                if k == norm(w.text) or (len(k) > 3 and k in norm(w.text)):
                    return w
        return None

    def identify(self, read=True):
        if read:
            self.read()
        for name, groups in SCREENS:
            if all(self.has(*g) for g in groups):
                return name
        if self.g is not None and self.g.in_game():
            return "in_game"
        return "unknown"

    def click_word(self, *keys, region=None, dy=0.0):
        w = self.find(*keys, region=region)
        if not w or forbidden(w.text):
            return False
        log.info("click %r", w.text)
        self.inp.click(w.x, w.y + dy)
        time.sleep(0.6)
        return True

    # -- popups ---------------------------------------------------------------
    def dismiss_popup(self):
        """Close whatever simple popup is up. Never on a defeat screen."""
        if self.has("defeat", "gameover", "bloonsleaked"):
            return False
        for b in POPUP_BUTTONS:
            w = self.find(b)
            if w and w.conf > 0.6 and len(norm(w.text)) <= len(b) + 3 and not forbidden(w.text):
                # a 'continue' next to a monkey-money price is a paid revive
                if b == "continue" and self.has("$", "monkeymoney") and self.has("defeat", "lost"):
                    continue
                log.info("dismiss popup via %r", w.text)
                self.inp.click(w.x, w.y)
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
        for attempt in range(7):
            self.read(scale=0.6)
            name_w = self.find_center_name()
            name = name_w.text if name_w else ""
            if name and name not in offered:
                offered.append(name)
            if target is None:
                target = choose(title, offered) if len(offered) >= 1 else None
            if target and norm(target) == norm(name):
                break
            # rotate: click the item left of centre
            self.inp.click(0.255, 0.45)
            time.sleep(1.0)
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
            if self.click_word("home"):
                continue
            if self.click_word("next", "continue", "collect"):
                continue
            self.inp.click(0.5, 0.85)
            time.sleep(1.0)
        return False

    def leave_defeat(self):
        """Defeat: go home. NEVER the paid continue."""
        for _ in range(4):
            st = self.identify()
            if st == "main_menu":
                return True
            if self.click_word("home"):
                continue
            time.sleep(1.0)
        return False
