"""Shared pieces of the small achievement routines (powers, instas, hero
skin, quests): which achievement cards are still wanted, a per-account daily
budget kept on disk, and the narrow click allow-list those routines use.

Which cards are wanted
  The planner's own reading of the account's achievement scan
  (planner.account_scan_path, planner.match_achievement_state). A card is
  wanted while the scan read it "progress" (any percentage) or "unknown" (a
  card read without a percentage, e.g. Lookin fab). A card the scan did not
  read at all is NOT wanted: almost all of those are finished cards at the
  bottom of the list (docs/achievements.md), and no routine should run for
  them on a guess.

Daily budget (logs/achievement_tasks.json)
  Per account (User ID) and per UTC day: clicks made by these routines,
  Monkey Money spent, purchases, power and insta uses, look-only captures.
  Each routine asks allow() before acting and calls add() afterwards, so a
  routine that misbehaves stops at the cap instead of running all day. The
  caps are the constants below; MM_PER_DAY is the owner's hard cap on
  Monkey Money (in-game currency only; real money is never touched).

Click allow-list
  menus.FORBIDDEN blocks every word containing "powers", "insta" or "buy",
  deliberately, and stays as it is. These routines click only words whose
  whole normalised text is in their own small allow-list (allowed_word),
  and never anything that looks like real money or a shop offer, whatever
  the allow-list says (REAL_MONEY_WORDS, a price with cents).
"""
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .vision import norm

log = logging.getLogger("achtasks")

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT_DIR / "logs" / "achievement_tasks.json"
# calibration screenshots of screens no recording shows yet (a few a day)
CAPTURE_DIR = ROOT_DIR / "logs" / "achievement_captures"

# -- hard daily caps (per account, per UTC day) -------------------------------
MM_PER_DAY = 3000          # Monkey Money these routines may spend in a day
PURCHASES_PER_DAY = 10     # Monkey Money purchases in a day
CLICKS_PER_DAY = 400       # clicks by these routines in a day (all flows together)
POWER_USES_PER_DAY = 40    # powers used in games in a day
INSTA_USES_PER_DAY = 30    # Insta Monkeys placed in a day
LOOKS_PER_DAY = 3          # look-only captures (calibration screenshots) per flow
FAILURES_PER_DAY = 4       # failed tries of one flow before it rests until tomorrow

CAPS = {"mm": MM_PER_DAY, "purchases": PURCHASES_PER_DAY, "clicks": CLICKS_PER_DAY,
        "power_uses": POWER_USES_PER_DAY, "insta_uses": INSTA_USES_PER_DAY}

# Card names, as in data/achievements.json
POWER_CARDS = ("You've Got the Power", "Power User", "Empowered")
INSTA_CARDS = ("Insta Century", "Instant Gratification")
T5_INSTA_CARD = "Instant Gratification"
SKIN_CARD = "Lookin fab"
FIRST_STEPS_CARD = "First Steps"

WANTED_STATUSES = ("progress", "unknown")

# Words of real-money offers and shops: never clicked, even when an
# allow-list names them (the allow-lists never do).
REAL_MONEY_WORDS = ("store", "unlockall", "bundle", "offer", "usd", "eur", "getnow", "dlc",
                    "trophystore", "trophies", "continuefor", "bestvalue", "specialoffer",
                    "pack", "starter", "signin", "password")
_REAL_PRICE = re.compile(r"\d[.,]\d\d\b")


# -- wanted cards ------------------------------------------------------------------
def card_statuses(catalog=None, state=None):
    """Catalog name -> scanned status ("progress", "unknown", "complete",
    "collect") for every card the current account's scan read. catalog and
    state default to the planner's files (planner.load_achievements)."""
    from . import planner
    if catalog is None or state is None:
        cat, st = planner.load_achievements()
        catalog = cat if catalog is None else catalog
        state = st if state is None else state
    if not catalog:
        return {}
    cards = planner.match_achievement_state(catalog, state)
    return {name: str(card.get("status") or "unknown") for name, card in cards.items()}


def wanted(names, statuses=None):
    """The names among `names` whose card is wanted (read, not finished)."""
    statuses = card_statuses() if statuses is None else statuses
    return [n for n in names if statuses.get(n) in WANTED_STATUSES]


# -- click allow-list ----------------------------------------------------------------
def real_money(text):
    """True for text of a real-money offer: a shop word or a price with cents."""
    n = norm(text)
    return any(w in n for w in REAL_MONEY_WORDS) or bool(_REAL_PRICE.search(text or ""))


def allowed_word(word, allow):
    """May this OCR word be clicked by a routine whose allow-list is `allow`
    (normalised whole texts)? Only an exact match, and never real money."""
    return norm(word.text) in allow and not real_money(word.text)


def find_allowed(words, allow, region=None):
    """First word (in allow-list order) that allowed_word() accepts, inside
    region (fractions) when given."""
    if region:
        words = [w for w in words if region[0] <= w.x <= region[2] and region[1] <= w.y <= region[3]]
    for a in allow:
        for w in words:
            if norm(w.text) == a and allowed_word(w, allow):
                return w
    return None


def screen_text(words, limit=30):
    """The words read, for an "achievement: ... bailing out" log line."""
    return " | ".join(w.text for w in list(words)[:limit])


# -- daily budget ----------------------------------------------------------------------
def today(now=None):
    now = time.time() if now is None else now
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")


class Budget:
    """One account's counters for today, saved to STATE_FILE after each add().

    The file keeps, per account: "days": {date: {counter: n}} (the last 7
    days), and "flags": lasting facts such as {"skin_equipped": {...}}."""

    def __init__(self, account_key, path=STATE_FILE, clock=time.time):
        self.key = account_key or "default"
        self.path = Path(path)
        self.clock = clock

    # -- file ---------------------------------------------------------------
    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("achievement tasks: could not save %s", self.path)

    def _account(self, data):
        acc = data.setdefault(self.key, {})
        acc.setdefault("days", {})
        acc.setdefault("flags", {})
        return acc

    # -- counters -------------------------------------------------------------
    def counts(self):
        """Today's counters (a copy)."""
        acc = self._account(self._load())
        return dict(acc["days"].get(today(self.clock()), {}))

    def used(self, counter):
        return self.counts().get(counter, 0)

    def left(self, counter):
        cap = CAPS.get(counter)
        return None if cap is None else max(0, cap - self.used(counter))

    def allow(self, counter, amount=1):
        """Would adding `amount` to `counter` stay within today's cap?"""
        cap = CAPS.get(counter)
        return cap is None or self.used(counter) + amount <= cap

    def add(self, counter, amount=1):
        data = self._load()
        acc = self._account(data)
        day = today(self.clock())
        rec = acc["days"].setdefault(day, {})
        rec[counter] = rec.get(counter, 0) + amount
        # keep a week of days
        for d in sorted(acc["days"])[:-7]:
            del acc["days"][d]
        self._save(data)
        return rec[counter]

    def resting(self, flow):
        """True when `flow` failed FAILURES_PER_DAY times today."""
        return self.used(f"{flow}_failures") >= FAILURES_PER_DAY

    # -- lasting flags -----------------------------------------------------------
    def flag(self, name):
        return self._account(self._load())["flags"].get(name)

    def set_flag(self, name, value):
        data = self._load()
        self._account(data)["flags"][name] = value
        self._save(data)


class CountingInput:
    """Wraps the bot's input so every click counts against the daily click
    cap. Once the cap is reached, click() raises CapReached and the routine
    bails out. It has no press(): these routines never press a key (Esc
    ends the operator's session)."""

    def __init__(self, inp, budget):
        self._inp = inp
        self.budget = budget

    def click(self, fx, fy, *a, **kw):
        if not self.budget.allow("clicks"):
            raise CapReached("daily click cap reached")
        self.budget.add("clicks")
        return self._inp.click(fx, fy, *a, **kw)

    def move(self, fx, fy, *a, **kw):
        if hasattr(self._inp, "move"):
            return self._inp.move(fx, fy, *a, **kw)
        return None

    def scroll(self, *a, **kw):
        return self._inp.scroll(*a, **kw)


class CapReached(Exception):
    """A daily cap stopped a routine."""
