"""Equip a hero from the main menu's HEROES screen.

What the screen looks like (calibrated live, v57.3, 1920x1200):
  * left: a scrolling grid of hero portraits in gold frames, three per row,
    with NO names on them; a hero the account does not own shows a Monkey
    Money price on its portrait
  * clicking a portrait shows that hero on the right: its name in big letters
    at the top and, under the picture, SELECT (owned) or SELECTED (equipped)
  * the column of skins at the far right has purchase buttons: never touched

So the picker finds the portraits by their gold frames, clicks them one by
one and reads the name at the top until it shows the wanted hero, then
clicks SELECT. Along the way it learns which heroes the account owns.

Where a hero was found (how far the grid was scrolled, which tile) is kept
in data/hero_grid.json, so the next switch goes straight there. A stale
entry (a game update adds heroes and shifts the grid) is noticed because the
name does not match, and the hero is simply searched for again.
"""
import json
import logging
import time
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

from . import towers as T
from .meta import Meta, match_hero, safe_text
from .vision import norm

log = logging.getLogger("heroes")

CACHE_FILE = Path(__file__).resolve().parents[1] / "data" / "hero_grid.json"

GRID = (0.015, 0.12, 0.285, 1.0)        # the portrait grid (fractions of the window)
NAME = (0.30, 0.02, 0.62, 0.10)         # the shown hero's name, top centre
BUTTON = (0.48, 0.53, 0.70, 0.61)       # SELECT / SELECTED under the picture
SCROLL_AT = (0.147, 0.55)               # where the mouse wheel scrolls the grid
SCROLL_STEP = 4                         # wheel ticks per page while searching
MAX_PAGES = 12
# The gold frame of a portrait: orange-yellow, saturated and bright (HSV).
FRAME_LO, FRAME_HI = (15, 170, 190), (35, 255, 255)
SETTLE = 0.15                           # seconds between reads while waiting


def find_tiles(img):
    """Centres (fx, fy) of the portraits that are fully visible, top-left
    first. Tiles are found by their gold frames; partly scrolled-out tiles
    (shorter than the others) are left out."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(GRID[0] * w), int(GRID[1] * h), int(GRID[2] * w), int(GRID[3] * h)
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, FRAME_LO, FRAME_HI)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours]
    # a portrait is a tall-ish rectangle about a quarter of the grid wide
    boxes = [b for b in boxes if 0.18 < b[2] / (x1 - x0) < 0.4 and 0.9 < b[3] / b[2] < 1.6]
    if not boxes:
        return []
    # the usual portrait height (the median: the equipped hero's glowing frame
    # is a little bigger, scrolled-out ones are shorter)
    full_h = float(np.median([b[3] for b in boxes]))
    tiles = [((x0 + bx + bw / 2) / w, (y0 + by + bh / 2) / h)
             for bx, by, bw, bh in boxes if bh >= 0.92 * full_h]
    return sorted(tiles, key=lambda t: (round(t[1], 2), t[0]))


def grid_shift(before, after):
    """How many pixels the grid content moved up between two frames (found by
    locating a band of the new frame in the old one)."""
    h, w = before.shape[:2]
    x0, x1 = int(GRID[0] * w), int(GRID[2] * w)
    old = cv2.cvtColor(before[int(0.12 * h):h, x0:x1], cv2.COLOR_BGR2GRAY)
    band_top = int(0.35 * h)
    band = cv2.cvtColor(after[band_top:band_top + int(0.2 * h), x0:x1], cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(old, band, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if score < 0.6:
        return None
    return (loc[1] + int(0.12 * h)) - band_top


class HeroPicker:
    def __init__(self, screen, inp, menus, account):
        self.s, self.inp, self.menus, self.account = screen, inp, menus, account
        self.meta = Meta(screen, inp, menus, account)   # main-menu navigation

    # -- reading the right-hand side -------------------------------------------
    def _text(self, region):
        return " ".join(w.text for w in self.menus.v.read(region))

    def shown_hero(self):
        """Hero id whose name is shown at the top, or None. The game's font
        makes OCR read C as G ("quINGY" for Quincy), so a failed match is
        tried again with G read as C."""
        text = self._text(NAME)
        return match_hero(text) or match_hero(text.replace("G", "C").replace("g", "c"))

    def button(self):
        """'selected', 'select', 'locked' (a price or unlock text: not owned),
        or None (nothing readable yet). The game's font makes OCR read the C
        as a G ("SeLeGTeD"), so the words are compared loosely."""
        words = [norm(w.text) for w in self.menus.v.read(BUTTON)]
        # "select" is most of "selected", so the length decides between them
        for t in words:
            if len(t) >= 7 and SequenceMatcher(None, t, "selected").ratio() >= 0.8:
                return "selected"
        for t in words:
            if len(t) <= 7 and SequenceMatcher(None, t, "select").ratio() >= 0.75:
                return "select"
        if any(t.isdigit() or t.startswith(("unlock", "buy", "level")) for t in words):
            return "locked"
        return None

    def _wait_for_change(self, before, timeout=1.5):
        """After clicking a portrait: wait until the name at the top changes."""
        end = time.time() + timeout
        while time.time() < end:
            now = self.shown_hero()
            if now is not None and now != before:
                return now
            time.sleep(SETTLE)
        return self.shown_hero()

    def _note_owned(self, hero, state):
        """Keep the account's list of owned heroes true to the screen."""
        if state in ("select", "selected"):
            self.account.unlocked_heroes.add(hero)
        elif state == "locked" and hero in self.account.unlocked_heroes and hero != "quincy":
            log.info("%s is not owned (no SELECT button)", hero)
            self.account.unlocked_heroes.discard(hero)

    # -- scrolling ---------------------------------------------------------------
    def _settle(self):
        """Wait until the grid stops moving (it scrolls smoothly); returns the frame."""
        prev = self.s.grab()
        for _ in range(10):
            time.sleep(SETTLE)
            cur = self.s.grab()
            if np.mean(cv2.absdiff(prev, cur)) < 1.0:
                return cur
            prev = cur
        return prev

    def _to_top(self):
        self.inp.scroll(15, *SCROLL_AT)
        return self._settle()

    # -- the cache ---------------------------------------------------------------
    # data/hero_grid.json: {"tiles": {hero: {"ticks", "tile"}},
    #                        "owned_scan": {account file: time of the last full scan}}
    @staticmethod
    def _load_cache():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        cache.setdefault("tiles", {})
        cache.setdefault("owned_scan", {})
        return cache

    @staticmethod
    def _save_cache(cache):
        try:
            CACHE_FILE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    # -- choosing ----------------------------------------------------------------
    def _try_tile(self, tile, current):
        """Click a portrait; returns the hero id it shows."""
        self.inp.click(*tile)
        return self._wait_for_change(current)

    def _equip_shown(self, hero):
        """The wanted hero is shown: SELECT it. True when equipped."""
        state = self.button()
        self._note_owned(hero, state)
        if state == "select":
            self.inp.click(*self._select_position())
            end = time.time() + 2.0
            while time.time() < end and self.button() != "selected":
                time.sleep(SETTLE)
            state = self.button()
        if state == "selected":
            self.account.selected_hero = hero
            log.info("hero %s equipped", hero)
            return True
        log.warning("hero %s cannot be selected (button: %s)", hero, state)
        return False

    def _select_position(self):
        """Centre of the SELECT word (read, not assumed)."""
        for w in self.menus.v.read(BUTTON):
            if norm(w.text).startswith("sele") and safe_text(w.text):
                return w.x, w.y
        return (BUTTON[0] + BUTTON[2]) / 2, (BUTTON[1] + BUTTON[3]) / 2

    def select(self, hero):
        """Open HEROES, equip `hero`, return to the main menu. True when equipped."""
        if hero not in T.HEROES:
            log.warning("unknown hero %r", hero)
            return False
        ok, origin = self.meta._open_hero_picker()
        if not ok:
            log.warning("HEROES screen did not open (from %s)", origin)
            self.meta.to_main_menu()
            return False
        try:
            return self._find_and_equip(hero)
        finally:
            self.meta.to_main_menu()
            self.account.save()

    def _walk(self, current, cache):
        """Click every portrait from the top of the grid, page by page.
        Yields the hero each one shows (None if unreadable); records where it
        was and whether the account owns it."""
        frame = self._to_top()
        ticks, offset, visited = 0, 0, []
        for _ in range(MAX_PAGES):
            h = frame.shape[0]
            for tile in find_tiles(frame):
                content_y = tile[1] * h + offset          # position in the whole grid
                if any(abs(tile[0] - vx) < 0.03 and abs(content_y - vy) < 0.05 * h for vx, vy in visited):
                    continue                              # seen before this scroll
                visited.append((tile[0], content_y))
                current = self._try_tile(tile, current)
                if current:
                    cache["tiles"][current] = {"ticks": ticks, "tile": [round(tile[0], 4), round(tile[1], 4)]}
                    self._note_owned(current, self.button())
                yield current
            self.inp.scroll(-SCROLL_STEP, *SCROLL_AT)
            after = self._settle()
            shift = grid_shift(frame, after)
            if shift is None or shift < 5:
                return                                    # the end of the grid
            ticks += SCROLL_STEP
            offset += shift
            frame = after

    def _find_and_equip(self, hero):
        current = self.shown_hero()        # the equipped hero is shown first
        if current == hero:
            return self._equip_shown(hero)
        cache = self._load_cache()
        # 1. straight to where it was last time
        spot = cache["tiles"].get(hero)
        if spot:
            self._to_top()
            if spot["ticks"]:
                self.inp.scroll(-spot["ticks"], *SCROLL_AT)
                self._settle()
            current = self._try_tile(tuple(spot["tile"]), current)
            if current == hero:
                return self._equip_shown(hero)
            log.info("hero grid changed (%s found where %s was) - searching", current, hero)
        # 2. search every portrait
        try:
            for shown in self._walk(current, cache):
                if shown == hero:
                    return self._equip_shown(hero)
        finally:
            self._save_cache(cache)
        log.warning("hero %s not found in the HEROES grid", hero)
        return False

    def scan_owned_if_due(self, every_days=7):
        """Once a week per account: click through the whole grid to learn which
        heroes the account owns (heroes can be bought or won at any time; the
        bot itself never buys one). Returns the owned set, or None if not due."""
        cache = self._load_cache()
        key = Path(self.account.path or "account").stem
        if time.time() - cache["owned_scan"].get(key, 0) < every_days * 86400:
            return None
        ok, origin = self.meta._open_hero_picker()
        if not ok:
            log.warning("HEROES screen did not open (from %s)", origin)
            self.meta.to_main_menu()
            return None
        try:
            seen = [h for h in self._walk(self.shown_hero(), cache) if h]
            cache["owned_scan"][key] = time.time()
            log.info("hero scan: %d heroes seen, owned: %s", len(set(seen)), sorted(self.account.unlocked_heroes))
        finally:
            self._save_cache(cache)
            self.meta.to_main_menu()
            self.account.save()
        return set(self.account.unlocked_heroes)
