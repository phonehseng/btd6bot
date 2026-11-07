"""First Steps ("Complete the First Time Tutorial quest"): a look at the
Quests menu, nothing more.

Why only a look
  The quest is a guided tutorial game: it tells the player where to put a
  Dart Monkey, when to upgrade and when to press Play, and waits for exactly
  those clicks. The bot's match code places towers by its own plan with
  hotkeys and has no reader for tutorial instructions, so it cannot be
  trusted to finish it. What a playing routine would need is listed in
  docs/achievements.md (First Steps).

Where the Quests menu is
  The main menu's monkey holding a scroll, left of the centre statue (a
  pumpkin-headed monkey in the Halloween theme): QUEST_GIVER, measured on
  rec_20261107_165100.mkv 0:18. Confirmed by the first live run
  (2026-11-07 18:07): it opens QUESTS.

What the Quests menu shows (that run's capture,
logs/achievement_captures/quests_20261107_180710.png, 1920x1200)
  Title QUESTS, a search box, five tabs in a row at y = 0.167 - ALL (0.15),
  TALES (0.30), CHALLENGES (0.47), TUTORIALS (0.64), EXPERIMENTS (0.81) -
  and under them one card per quest: title and description on the left
  (x 0.23-0.6), a reward strip ("x3", "500"), a green GO! button at
  x = 0.80 with the progress ("0/1") under it. The ALL tab showed event
  quests (He-Man, Rogue Legends preview); First Time Tutorial was not on
  its first page, so it is presumably under TUTORIALS.

The look (once a day at most, while the First Steps card is wanted)
  Click the quest giver, then the TUTORIALS tab (the only word clicked on
  the Quests screen, and only inside TAB_ROW); read, save a capture, log
  every card read (title, description, progress, whether it has a GO!
  button) and whether "First Time Tutorial" is among them - then leave
  with the on-screen back arrow. GO! is never clicked: the quest is a
  guided game (see "Why only a look"). A shop-like screen or an unreadable
  one is logged the same way.
"""
import logging
import time

from . import achtasks as A
from .vision import norm, save

log = logging.getLogger("quests")

QUEST_GIVER = (0.405, 0.555)
BACK_ARROW = (0.044, 0.055)
TAB_ROW = (0.10, 0.12, 0.92, 0.22)       # ALL / TALES / CHALLENGES / TUTORIALS / EXPERIMENTS
TUTORIALS_TAB = ("tutorials", "tutorial")
GO_COLUMN = (0.70, 0.90)                 # x range of the GO! buttons and the progress
QUEST_WORDS = ("quests", "quest", "questline")
TUTORIAL = "firsttimetutorial"
# New names: the first version's daily counter and its "quests_seen" flag
# (set by the 18:07 run) must not stop the TUTORIALS look.
FLOW = "quests_tutorials_look"
SEEN_FLAG = "quests_tutorials_seen"


def describe(words):
    """('quests' | 'shop' | 'unknown', tutorial_listed)."""
    joined = "".join(norm(w.text) for w in words)
    if any(A.real_money(w.text) for w in words):
        return "shop", False
    tut = TUTORIAL in joined or ("firsttime" in joined and "tutorial" in joined)
    if tut or any(q in joined for q in QUEST_WORDS):
        return "quests", tut
    return "unknown", False


CARD_ABOVE = 0.135                      # a card's title sits this far above its progress
CARD_BELOW = 0.02


def cards(words):
    """The quest cards read: [{title, desc, progress, go}] top to bottom.
    Each card is anchored on its progress ("0/1", in GO_COLUMN at the
    card's bottom; on the capture the cards' progress lines are 0.19 apart
    and the title 0.12 above it): the text left of GO_COLUMN from
    CARD_ABOVE above to CARD_BELOW below the progress is the card's, and
    so is a GO! word in that band. A GO! with no progress read anchors a
    card too (its progress is about 0.06 below it)."""
    below = [w for w in words if w.y > TAB_ROW[3]]
    left = sorted((w for w in below if w.x < GO_COLUMN[0]), key=lambda w: w.y)
    right = [w for w in below if GO_COLUMN[0] <= w.x <= GO_COLUMN[1]]
    anchors = sorted(w.y for w in right if "/" in w.text)
    for w in right:
        if norm(w.text) == "go" and not any(abs(a - (w.y + 0.06)) < 0.04 for a in anchors):
            anchors.append(w.y + 0.06)
    out = []
    for a in sorted(anchors):
        y0, y1 = a - CARD_ABOVE, a + CARD_BELOW
        row = [w for w in left if y0 <= w.y <= y1]
        side = [w for w in right if y0 <= w.y <= y1]
        # reward counts ("x3") and the "New" ribbon are not text of the quest
        texts = [w.text for w in row
                 if not (norm(w.text)[:1] == "x" and norm(w.text)[1:].isdigit())
                 and norm(w.text) not in ("new", "") and not norm(w.text).isdigit()]
        out.append({"title": texts[0] if texts else "", "desc": " ".join(texts[1:3]),
                    "progress": next((w.text for w in side if "/" in w.text), None),
                    "go": any(norm(w.text) == "go" for w in side)})
    return out


def tutorial_card(found):
    """The First Time Tutorial card among cards(), or None."""
    for c in found:
        n = norm(c["title"] + c["desc"])
        if TUTORIAL in n or ("firsttime" in n and "tutorial" in n):
            return c
    return None


def _capture(screen, what):
    try:
        save(screen.grab(), A.CAPTURE_DIR / f"{what}_{time.strftime('%Y%m%d_%H%M%S')}.png")
    except Exception:
        pass


def _tutorials_tab(screen, cinp, menus, words, sleep):
    """On the Quests screen: open TUTORIALS, log its cards. Returns the
    First Time Tutorial card or None."""
    tab = A.find_allowed(words, TUTORIALS_TAB, region=TAB_ROW)
    if tab is None:
        log.info("achievement: First Steps - no TUTORIALS tab read in the tab row")
        return None
    cinp.click(tab.x, tab.y)
    sleep(1.5)
    menus.identify()
    words = list(menus.words)
    _capture(screen, "quests_tutorials")
    if any(A.real_money(w.text) for w in words):
        log.warning("achievement: First Steps - real-money wording on the TUTORIALS tab; screen read: %s",
                    A.screen_text(words, 40))
        return None
    found = cards(words)
    for c in found:
        log.info("achievement: First Steps - tutorials card: %r / %r, progress %s, GO button %s",
                 c["title"], c["desc"], c["progress"], "yes" if c["go"] else "no")
    card = tutorial_card(found)
    if card:
        verdict = "listed (%s; progress %s) - not started: a guided game" % (
            card["desc"] or "no description", card["progress"])
    else:
        verdict = "not read"
    log.info("achievement: First Steps - TUTORIALS tab: %d cards, First Time Tutorial %s; read: %s",
             len(found), verdict, A.screen_text(words, 40))
    return card


def look(screen, inp, menus, budget, sleep=time.sleep):
    """Open the Quests menu and its TUTORIALS tab, record what they show,
    come back. Returns a short result for the log."""
    cinp = A.CountingInput(inp, budget)
    if menus.identify() != "main_menu":
        return "not_on_main_menu"
    cinp.click(*QUEST_GIVER)
    sleep(2.0)
    st = menus.identify()
    words = list(menus.words)
    kind, tut = ("unchanged", False) if st == "main_menu" else describe(words)
    log.info("achievement: First Steps - quest giver clicked: %s, First Time Tutorial %s; read: %s",
             kind, "listed" if tut else "not read", A.screen_text(words, 40))
    _capture(screen, "quests")
    card = _tutorials_tab(screen, cinp, menus, words, sleep) if kind == "quests" else None
    tut = tut or card is not None
    for _ in range(4):
        if menus.identify() == "main_menu":
            break
        cinp.click(*BACK_ARROW)
        sleep(1.2)
    if kind == "quests":
        budget.set_flag(SEEN_FLAG, {"at": time.time(), "tutorial_listed": tut, "card": card})
    return f"{kind}, tutorial {'listed' if tut else 'not read'}"


def run_if_due(screen, inp, menus, account_key, statuses=None, budget=None):
    """The runner's entry point on the main menu. Once a day while First
    Steps is wanted, and only until the TUTORIALS tab was looked at once."""
    budget = budget or A.Budget(account_key)
    statuses = A.card_statuses() if statuses is None else statuses
    if not A.wanted((A.FIRST_STEPS_CARD,), statuses) or budget.flag(SEEN_FLAG):
        return None
    if budget.used(FLOW) >= 1:
        return None
    budget.add(FLOW)
    try:
        return look(screen, inp, menus, budget)
    except A.CapReached as e:
        return f"cap: {e}"
