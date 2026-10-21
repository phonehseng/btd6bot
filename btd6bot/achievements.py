"""Achievements screen: read every card's status and claim finished rewards.

Main menu -> ribbon badge (left column) -> a two-column grid of cards:
  yellow card + COLLECT   finished, reward (Monkey Money) not yet claimed
  "COMPLETE"              finished and claimed
  blue card + NN%         in progress
The list is scrolled with the mouse wheel (one tick ~ 3.5% of the screen,
one card row ~ 29%). Results go to data/achievements_state.json so the planner
can aim for what is missing. Collecting is a free reward, never a purchase.
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


def _is_collect(text):
    n = norm(text)
    return any(n.startswith(c) for c in COLLECT_WORDS)


def _catalog_names():
    try:
        return {norm(a["name"]): a["name"] for a in json.loads(CATALOG.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


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
    def save(cards):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        data = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cards": cards}
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)

    @staticmethod
    def load():
        try:
            return json.loads(STATE.read_text(encoding="utf-8")).get("cards", {})
        except (OSError, ValueError):
            return {}
