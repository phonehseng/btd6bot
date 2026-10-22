"""Achievements screen: read every card's status and claim finished rewards.

Main menu -> ribbon badge (left column) -> a two-column grid of cards:
  yellow card + COLLECT   finished, reward (Monkey Money) not yet claimed
  "COMPLETE"              finished and claimed
  blue card + NN%         in progress
The list is scrolled with the mouse wheel (one tick ~ 3.5% of the screen,
one card row ~ 29%). Results go to data/achievements_state.json so the planner
can aim for what is missing. Collecting is a free reward, never a purchase.

The game sorts the list by completion: in-progress cards by percentage, highest
first, and claimed ("COMPLETE") cards at the bottom (both saved scans show it:
VXORVHFCB 80, 77, 55, 40, 25 ... 0 %; SFYOSHHYV 96, 92, 90 ... 0 %, then 55
COMPLETE cards). A finished card waiting for its COLLECT click is at 100 %, so
it sits at the top - which is what claim() relies on.
"""
import json
import logging
import re
import time
from pathlib import Path

from .vision import norm

log = logging.getLogger("achievements")

STATE = Path(__file__).resolve().parents[1] / "data" / "achievements_state.json"
CATALOG = Path(__file__).resolve().parents[1] / "data" / "achievements.json"

BADGE = (0.044, 0.32)      # achievements ribbon on the main menu (left column)
LIST_POINT = (0.5, 0.6)    # where to hover while scrolling
SCROLL_TICKS = 15          # ~1.8 card rows per page, so cards overlap between pages
ROW_PITCH = 0.288          # vertical distance between card rows
COLLECT_WORDS = ("collect", "collegt", "colleci")
CLAIM_PAGES = 4            # claim(): pages it may scroll through at most


def _is_collect(text):
    """The COLLECT button: one word. A description that starts with
    "Collect" is not one - "Our Powers Combined" ("Collect at least 12
    different Powers") was read as claimable in every scan and its text
    clicked as if it were the button."""
    n = norm(text)
    return " " not in text.strip() and any(n.startswith(c) for c in COLLECT_WORDS)


def _catalog_names():
    try:
        return {norm(a["name"]): a["name"] for a in json.loads(CATALOG.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _past_finished(cards, claimed):
    """Does this page reach below the finished cards? True when it shows an
    in-progress card, or a COMPLETE one this claim pass did not just claim
    (claimed cards may keep their place until the list is reopened)."""
    return any(c["status"] == "progress" or (c["status"] == "complete" and c["name"] not in claimed)
               for c in cards)


def _same_card(card, seen, catalog):
    """Key of an already-seen card that is this one under another OCR spelling."""
    import difflib
    n = norm(card["name"])
    if catalog:
        hit = difflib.get_close_matches(n, list(catalog), n=1, cutoff=0.8)
        if hit:
            return catalog[hit[0]]
    d = norm(card["desc"])
    for key, rec in seen.items():
        if difflib.SequenceMatcher(None, n, norm(key)).ratio() > 0.8 or (
                len(d) > 12 and difflib.SequenceMatcher(None, d, norm(rec["desc"])).ratio() > 0.85):
            return key
    return None


def parse_cards(words, catalog=None):
    """Group OCR words into cards: [{name, desc, status, progress, collect_xy}]."""
    catalog = catalog if catalog is not None else {}
    cards = []
    # card titles: single tokens (OCR glues bold title words together) that are
    # immediately followed by a sentence-like description just below them
    for w in words:
        n = norm(w.text)
        if " " in w.text.strip() or len(n) < 4 or _is_collect(w.text) or n in ("complete", "search"):
            continue
        if re.fullmatch(r"[0-9$%/]+", n):
            continue
        col = 0 if w.x < 0.5 else 1
        desc = [d for d in words if " " in d.text.strip() and (d.x < 0.5) == (col == 0)
                and 0.015 < d.y - w.y < 0.09]
        if not desc:
            continue
        name = catalog.get(n, w.text)
        below = [d for d in words if (d.x < 0.5) == (col == 0) and 0.0 < d.y - w.y < ROW_PITCH - 0.04]
        status, progress, collect_xy = "unknown", None, None
        for d in below:
            dn = norm(d.text)
            if _is_collect(d.text):
                status, collect_xy = "collect", (d.x, d.y)
            elif dn == "complete" and " " not in d.text.strip():
                status = "complete"  # the status label, not "Complete a race..." text
            elif d.text.strip().endswith("%"):
                m = re.search(r"(\d+)\s*%", d.text)
                if m and status == "unknown":
                    status, progress = "progress", int(m.group(1))
        cards.append({"name": name, "desc": " ".join(d.text for d in sorted(desc, key=lambda d: d.y)),
                      "status": status, "progress": progress, "collect_xy": collect_xy, "y": w.y})
    return cards


class Achievements:
    def __init__(self, screen, inp, menus):
        self.s = screen
        self.inp = inp
        self.menus = menus

    def open(self):
        """From the main menu. Returns True when the achievements list shows."""
        if self.menus.identify() != "main_menu":
            return False
        self.inp.click(*BADGE)
        end = time.time() + 6
        while time.time() < end:
            self.menus.read()
            if self.menus.has("achievements", "achlevements", "achievement"):
                return True
            time.sleep(0.3)
        return False

    def close(self):
        self.inp.click(0.044, 0.055)  # back arrow
        self.menus.wait_for("main_menu", timeout=5)

    def _focus_list(self):
        """The list only takes mouse-wheel input after a press inside it: a
        tiny drag on description text (no buttons there) does that."""
        self.inp.drag(0.25, 0.86, 0.25, 0.85, steps=2)
        time.sleep(0.2)

    def _claim(self, xy):
        self.inp.click(*xy)
        time.sleep(1.0)
        # reward popups: "20 / Monkey Money" (any click) or "CLAIMED" with an OK
        # button (bigger rewards, e.g. Monkey Money + an Insta Monkey)
        for _ in range(5):
            self.menus.read()
            if self.menus.has("achievements", "achlevements") and not self.menus.has("claimed"):
                return
            ok = self.menus.find("ok")
            if ok and ok.y > 0.8:
                self.inp.click(ok.x, ok.y)
            else:
                self.inp.click(0.5, 0.6)
            time.sleep(0.9)

    def claim(self, max_pages=CLAIM_PAGES):
        """Claim finished rewards without reading the whole list - for when
        the ribbon shows its "!" badge. Ends on the main menu; returns the
        names claimed.

        Log evidence (2026-10-22): the badge used to start the full scan,
        204 s (01:58:40-02:02:04, 97 cards read for 4 rewards) and 192 s
        (02:26:52-02:30:04, 92 cards for 1) only 28 minutes apart. As the
        list is sorted by completion (module notes), the COLLECT buttons are
        on the first page; the walk stops at the first page that also shows
        an unfinished or claimed card, since everything below is the same."""
        if not self.open():
            log.warning("could not open achievements")
            return []
        catalog = _catalog_names()
        claimed = []
        try:
            for _ in range(max_pages):
                cards = self._claim_visible(catalog, claimed)
                if not cards or _past_finished(cards, claimed):
                    break  # below the finished cards (or nothing readable at all)
                self._focus_list()  # every card on this page was finished: look further
                self.inp.scroll(-SCROLL_TICKS, *LIST_POINT)
                time.sleep(0.5)
        finally:
            self.close()
        log.info("achievements: %d rewards claimed %s", len(claimed), claimed)
        self._mark_claimed(claimed, catalog)
        return claimed

    def _claim_visible(self, catalog, claimed, most=8):
        """Claim every COLLECT button on the current page, one at a time with
        a fresh read before each: a claimed card may move to the bottom of
        the list, shifting the others, so positions from an older read could
        miss. Returns the page's cards as last read; `claimed` collects the
        names."""
        cards = []
        for _ in range(most):  # bounded, like everything that clicks in a loop
            cards = parse_cards(self.menus.read(), catalog)
            todo = [c for c in cards if c["status"] == "collect"]
            if not todo or todo[0]["name"] in claimed:
                break  # nothing (more) to claim, or a button that did not take
            self._claim(todo[0]["collect_xy"])
            claimed.append(todo[0]["name"])
        return cards

    @classmethod
    def _mark_claimed(cls, names, catalog):
        """Mark claimed cards COMPLETE in the saved progress, so the planner
        stops aiming at them before the next full scan."""
        if not names:
            return
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # no full scan saved yet: the next one records everything
        cards = data.get("cards", {})
        for name in names:
            key = _same_card({"name": name, "desc": ""}, cards, catalog) or name
            cards.setdefault(key, {"desc": "", "progress": None}).update(status="complete", progress=None)
        cls.save(cards, scanned_at=data.get("scanned_at"))

    def scan(self, collect=True, max_pages=40):
        """Walk the whole list; claim rewards; return {name: card}. Ends on main menu."""
        if not self.open():
            log.warning("could not open achievements")
            return {}
        catalog = _catalog_names()
        seen, stale, claimed = {}, 0, 0
        self._focus_list()
        try:
            for page in range(max_pages):
                cards = parse_cards(self.menus.read(), catalog)
                if collect:
                    for c in [c for c in cards if c["status"] == "collect"]:
                        self._claim(c["collect_xy"])
                        c["status"] = "complete"
                        claimed += 1
                    if claimed:
                        cards = parse_cards(self.menus.read(), catalog) or cards
                new = 0
                for c in cards:
                    key = _same_card(c, seen, catalog) or c["name"]
                    if key not in seen:
                        new += 1
                    prev = seen.get(key, {})
                    rec = {k: c[k] for k in ("desc", "status", "progress")}
                    if prev.get("status") in ("complete", "collect") and rec["status"] == "unknown":
                        rec["status"] = prev["status"]  # keep the better reading
                    if len(prev.get("desc", "")) > len(rec["desc"]):
                        rec["desc"] = prev["desc"]
                    seen[key] = rec
                stale = stale + 1 if new == 0 else 0
                if stale >= 2:
                    break
                if claimed:
                    self._focus_list()  # popups take the list's focus away
                self.inp.scroll(-SCROLL_TICKS, *LIST_POINT)
                time.sleep(0.5)
        finally:
            self.close()
        total = self._total_text()
        log.info("achievements: %d cards read, %d rewards claimed %s", len(seen), claimed, total)
        self.save(seen)
        return seen

    def _total_text(self):
        for w in self.menus.words:
            if re.fullmatch(r"\d+/\d+", w.text.strip()):
                return f"({w.text.strip()})"
        return ""

    @staticmethod
    def save(cards, scanned_at=None):
        """scanned_at: when the cards were last all read (default: now)."""
        STATE.parent.mkdir(parents=True, exist_ok=True)
        data = {"scanned_at": scanned_at or time.strftime("%Y-%m-%d %H:%M:%S"), "cards": cards}
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)

    @staticmethod
    def load():
        try:
            return json.loads(STATE.read_text(encoding="utf-8")).get("cards", {})
        except (OSError, ValueError):
            return {}
