"""First Steps ("Complete the First Time Tutorial quest"): a look at the
Quests menu, nothing more.

Why only a look
  The quest is a guided tutorial game: it tells the player where to put a
  Dart Monkey, when to upgrade and when to press Play, and waits for exactly
  those clicks. The bot's match code places towers by its own plan with
  hotkeys and has no reader for tutorial instructions, so it cannot be
  trusted to finish it; and no recording shows the Quests menu or the
  tutorial (the bot never opened them). What a playing routine would need
  is listed in docs/achievements.md (First Steps).

Where the Quests menu is (UNCERTAIN - to check live)
  The main menu has a monkey holding a scroll left of the centre statue (a
  pumpkin-headed monkey in the Halloween theme; on the level-10 account a
  green arrow points at it: docs/screens/after_home.jpg). It is the game's
  quest giver: QUEST_GIVER, measured on rec_20261107_165100.mkv 0:18
  (level 150) and after_home.jpg (level 10).

The look (once a day at most, while the First Steps card is wanted)
  Click the quest giver, wait, read the screen, save it under
  logs/achievement_captures/, log every word read and whether the
  "First Time Tutorial" quest is listed - then leave with the on-screen
  back arrow. Nothing on the Quests screen is clicked. A shop-like screen
  or a screen that never became readable is logged the same way.
"""
import logging
import time

from . import achtasks as A
from .vision import norm, save

log = logging.getLogger("quests")

QUEST_GIVER = (0.405, 0.555)
BACK_ARROW = (0.044, 0.055)
QUEST_WORDS = ("quests", "quest", "questline", "daily", "rewards")
TUTORIAL = "firsttimetutorial"
FLOW = "quests_look"


def describe(words):
    """('quests' | 'shop' | 'unchanged' | 'unknown', tutorial_listed)."""
    joined = "".join(norm(w.text) for w in words)
    if any(A.real_money(w.text) for w in words):
        return "shop", False
    tut = TUTORIAL in joined or ("firsttime" in joined and "tutorial" in joined)
    if tut or any(q in joined for q in QUEST_WORDS[:3]):
        return "quests", tut
    return "unknown", False


def look(screen, inp, menus, budget, sleep=time.sleep):
    """Open the Quests menu, record what it shows, come back. Returns a
    short result for the log."""
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
    try:
        save(screen.grab(), A.CAPTURE_DIR / f"quests_{time.strftime('%Y%m%d_%H%M%S')}.png")
    except Exception:
        pass
    for _ in range(4):
        if menus.identify() == "main_menu":
            break
        cinp.click(*BACK_ARROW)
        sleep(1.2)
    if kind == "quests":
        budget.set_flag("quests_seen", {"at": time.time(), "tutorial_listed": tut})
    return f"{kind}, tutorial {'listed' if tut else 'not read'}"


def run_if_due(screen, inp, menus, account_key, statuses=None, budget=None):
    """The runner's entry point on the main menu. Once a day while First
    Steps is wanted, and only until the Quests menu was seen once."""
    budget = budget or A.Budget(account_key)
    statuses = A.card_statuses() if statuses is None else statuses
    if not A.wanted((A.FIRST_STEPS_CARD,), statuses) or budget.flag("quests_seen"):
        return None
    if budget.used(FLOW) >= 1:
        return None
    budget.add(FLOW)
    try:
        return look(screen, inp, menus, budget)
    except A.CapReached as e:
        return f"cap: {e}"
