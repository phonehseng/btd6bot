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
    ("profile", [["overallstats", "topmonkeys", "topheroes", "publicstats"]]),
    ("victory", [["victory", "vigtory", "congratulations", "completedthistrack", "monkeystar"]]),
    ("tower_choice", [["choosea", "tounlock"], ["unlock"]]),
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
        if self.in_game():
            return "in_game"
        return "unknown"

    def in_game(self):
        from .templates import classify
        best, scores = classify(self.s.grab(), ["play_idle", "play_run", "play_fast"],
                                (0.905, 0.835, 1.0, 0.975))
        return scores[best] > 0.75

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
        # a screen offering Restart + Home is an end-of-game screen: its
        # Continue/Yes may be a paid revive, so never use those here
        endgame = self.has("restart") and self.has("home") and not self.has("pause")
        for b in POPUP_BUTTONS:
            if endgame and b in ("continue", "yes", "ok"):
                continue
            w = self.find(b)
            if w and w.conf > 0.6 and len(norm(w.text)) <= len(b) + 3 and not forbidden(w.text):
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
                time.sleep(1.4)
            else:
                # never reached the target: pick again knowing everything offered
                target = choose(title, offered) if offered else None
                log.warning("carousel: target not reached; offered %s -> retry for %r", offered, target)
                continue
            break
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
            # buttons are icons above their labels; the label is not clickable
            if self.click_word("home", dy=-0.08):
                time.sleep(2.0)
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
            if self.click_word("home", dy=-0.08):
                time.sleep(2.0)
                continue
            time.sleep(1.0)
        return False
