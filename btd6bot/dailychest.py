"""Daily Reward chest: open it from the main menu whenever it is ready.

What the game has (from the il2cpp class dump and the English text table in
the localisation bundle, game version of 2026-11):
  * the chest is a "world item" of the main-menu island (class OpenChest,
    with isChestReady and ShowChest(isChestReady)); clicking it calls
    OpenDailyRewardUI, which shows DailyRewardsScreen: a menu with one item
    per day ("Day {0}", "Today", "Claimed"), a rewardInfo line and a back
    button (BackClicked). The game text for the countdown is
    "Return in {0}h {1}m to claim your next reward!".
  * the reward is a LootSet (Monkey Money, Insta Monkeys, Powers...);
    Insta Monkeys show the "INSTA MONKEY!" panel the bot already knows.
  * the player profile keeps nextDailyRewardDateTime: the next chest is due
    at a set time (the wikis say 00:00 UTC), not 24 h after the last one.
  * a "Would you like to be notified when your Daily Reward chest is ready to
    open again?" prompt exists (RequestDailyRewardNotif); it changes a
    setting, so the bot never answers it with yes.

What the chest looks like (recordings of 2026-11-07, both accounts):
  The chest stands left of the centre statue, at about (0.265, 0.60) of the
  window. Its art is seasonal: in the Halloween theme it is a black coffin
  with a skull (tests/fixtures/daily_chest_ready_lvl150.png from
  rec_20261107_165100.mkv, and daily_chest_ready_lvl10.png from
  docs/screens/after_home.jpg); outside events it is a treasure chest. Under
  it lies a pulsing pale-yellow glow ellipse (HSV hue 15-30, saturation
  ~100-200, value > 200) on pink sand; a patch of the same sand near the
  statue never has it. So detection measures that glow, not the chest art.

UNCERTAIN - to check live:
  * every frame found shows the glow; no frame shows a chest that was
    already opened that day (neither account has ever claimed it while being
    recorded). The glow is the game's usual "this can be clicked" cue, but it
    may also be there after claiming. So the glow is only a hint here: the
    bot also tries once after each due time, and the game's own countdown
    text ("Return in 5h 12m ...") decides when the next try is due.
  * no frame of the reward screen exists. Its screen text above comes from
    the game's text table; the button positions are not known, so the flow
    only clicks words it reads (claim / collect / ok / continue / no) and
    leaves through the top-left back arrow every other game menu uses.
  * whether opening the chest needs one click (chest -> reward screen) or
    two (chest opens, then the reward screen comes up after an animation):
    the flow waits up to OPEN_WAIT seconds for any change.

Safety rules: never Esc (it ends the operator's session); never click a
word menus.forbidden() rejects (store, unlock all, buy, prices ...); on a
purchase-looking page, an unknown screen or anything else unexpected, log
what was read and go back to the main menu with the on-screen back arrow.
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from .menus import forbidden, page_forbidden
from .vision import norm

log = logging.getLogger("dailychest")

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT_DIR / "logs" / "daily_chest.json"   # per account: due time, recent tries

# -- where things are (fractions of the game window) --------------------------
CHEST = (0.265, 0.60)                    # centre of the chest/coffin on the main menu
GLOW_REGION = (0.25, 0.655, 0.345, 0.715)  # sand below-right of the chest, where the glow lies
CONTROL_REGION = (0.40, 0.66, 0.47, 0.71)  # the same pink sand near the statue: never glows
BACK_ARROW = (0.044, 0.055)              # top-left back arrow of every game menu

# Glow pixels: pale yellow (OpenCV HSV, hue 0-180). The pink sand around it
# is hue 6-11, saturation ~75; the orange ground further left is saturation
# ~195 but outside GLOW_REGION. Measured share in GLOW_REGION on the main
# menu: 0.36-0.49 (pulsing), control region 0.00-0.04; a settings popup or a
# game over the menu: 0.00.
GLOW_HUE = (15, 30)
GLOW_MIN_SAT = 80
GLOW_MIN_VAL = 200
GLOW_MIN_SHARE = 0.20                    # the glow covers at least this share of GLOW_REGION
CONTROL_MAX_SHARE = 0.10                 # ... while the plain sand patch stays clear of it

# -- pacing -----------------------------------------------------------------------
MAX_TRIES_PER_DAY = 3                    # clicks on the chest per account per 24 h, at most
MIN_TRY_GAP = 3600                       # seconds between two tries
FAILED_RETRY = 4 * 3600                  # after a try that read nothing useful
COUNTDOWN_MARGIN = 120                   # seconds added to the game's own countdown
OPEN_WAIT = 8.0                          # seconds to wait for the chest to react to a click
MAX_STEPS = 14                           # screens handled per claim, at most (bounded loop)
MAX_UNKNOWN = 3                          # unreadable screens in a row before bailing out

# -- what the screens say (normalised: lower case, letters and digits only) ----------
REWARD_WORDS = ("dailyreward", "today", "claimed")
DAY_ITEM = re.compile(r"^day\d{1,3}$")   # "Day 12" item labels
COUNTDOWN = re.compile(r"returnin(\d{1,2})h(\d{1,2})m")
NOTIFY_WORDS = ("wouldyouliketobenotified", "benotified", "notifiedwhen")
# buttons the flow may press, in order of preference
CLAIM_BUTTONS = ("claim", "collect", "ok", "continue", "awesome", "gotit")
DECLINE_BUTTONS = ("no", "notnow", "later", "nothanks", "cancel", "close")
# Words of a shop or a paid offer: the chest never leads there, so seeing
# one means a click went wrong. (Narrower than menus.FORBIDDEN, which also
# lists "insta" and "powers" - words the main menu and reward screens show.)
SHOP_WORDS = ("store", "unlockall", "buy", "purchase", "bundle", "offer", "getnow", "dlc",
              "specialoffer", "bestvalue")
_REAL_PRICE = re.compile(r"\d[.,]\d\d\b")


# -- detection on the main menu ---------------------------------------------------
def glow_share(frame, region):
    """Share of glow-coloured pixels inside region (fractions) of a BGR frame."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    patch = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 0] >= GLOW_HUE[0]) & (hsv[..., 0] <= GLOW_HUE[1])
            & (hsv[..., 1] >= GLOW_MIN_SAT) & (hsv[..., 2] >= GLOW_MIN_VAL))
    return float(mask.mean())


def chest_glows(frame):
    """Does the main menu show the glow under the daily chest?

    Returns (glowing, share, control_share). Only meaningful on the main
    menu (the caller checks that). The control patch guards against a
    screen tinted yellow all over (an event backdrop): there both patches
    would be "glowing", and that is not the chest's glow."""
    share = glow_share(frame, GLOW_REGION)
    control = glow_share(frame, CONTROL_REGION)
    return share >= GLOW_MIN_SHARE and control <= CONTROL_MAX_SHARE, share, control


# -- reading the screens after the click ----------------------------------------------
def countdown_seconds(words):
    """Seconds until the next chest from "Return in 5h 12m to claim your next
    reward!", or None. OCR glues the words together, so the normalised text
    of all words joined is searched."""
    joined = "".join(norm(w.text) for w in words)
    m = COUNTDOWN.search(joined)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60


def shop_like(words):
    """A store page or a purchase confirmation: words of a shop, a real-money
    price, or menus.page_forbidden (spending wording next to a price)."""
    if page_forbidden(words):
        return True
    for w in words:
        n = norm(w.text)
        if any(s in n for s in SHOP_WORDS) or _REAL_PRICE.search(w.text or ""):
            return True
    return False


def classify(words, screen_name="unknown"):
    """Name what is showing after the chest was clicked.

    words: OCR words of the whole screen; screen_name: menus.identify()'s
    answer for the same read. Returns one of
      "shop"          store / purchase page: leave at once
      "notify_prompt" the "be notified when your chest is ready" question
      "rewards"       the Daily Reward screen (days, Today, Claimed)
      "countdown"     the countdown text on any other screen
      "main_menu", "insta_reward", "reward_cards", "collection_event", a
      popup with a button ("popup"), or "unknown".
    The main menu wins over everything: its own numbers (XP "1,830/4,250",
    Monkey Money) must never make it look like a shop, and a countdown
    bubble over it needs no back-arrow click (there the arrow's place holds
    the profile button)."""
    if screen_name == "main_menu":
        return "main_menu"
    if shop_like(words):
        return "shop"
    norms = [norm(w.text) for w in words]
    joined = "".join(norms)
    if any(k in joined for k in NOTIFY_WORDS):
        return "notify_prompt"
    days = sum(1 for n in norms if DAY_ITEM.match(n))
    if "dailyreward" in joined or days >= 2 or (days and any(k in joined for k in REWARD_WORDS)):
        return "rewards"
    if countdown_seconds(words) is not None:
        return "countdown"
    if screen_name in ("insta_reward", "reward_cards", "collection_event"):
        return screen_name
    if any(n in CLAIM_BUTTONS for n in norms):
        return "popup"
    return "unknown"


# -- when to try ------------------------------------------------------------------
def next_utc_midnight(now):
    """Unix time of the next 00:00 UTC after now (the wikis' reset time)."""
    d = datetime.fromtimestamp(now, timezone.utc)
    nxt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)
    return nxt.timestamp()


def load_state(path=STATE_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state, path=STATE_FILE):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.warning("daily chest: could not save %s", path)


def is_due(rec, now, glowing):
    """Should the bot click the chest now? rec: this account's saved record.

    Never more than MAX_TRIES_PER_DAY tries in 24 h, nor two within
    MIN_TRY_GAP. Otherwise due once next_at has passed. A glow seen before
    then counts too, unless next_at came from the game's own countdown text
    (which is exact; the glow may well show all the time - module notes).
    Returns (due, why) for the log."""
    tries = [t for t in rec.get("tries", []) if now - t < 24 * 3600]
    if len(tries) >= MAX_TRIES_PER_DAY:
        return False, f"{len(tries)} tries in the last 24 h"
    if tries and now - max(tries) < MIN_TRY_GAP:
        return False, "tried less than an hour ago"
    next_at = rec.get("next_at", 0.0)
    if now >= next_at:
        return True, "due" if next_at else "never tried"
    if glowing and not rec.get("next_from_game"):
        return True, "chest glows before the guessed due time"
    return False, f"next chest in {(next_at - now) / 3600:.1f} h"


def record_result(rec, now, result, wait=None):
    """Update an account's record after a try. wait: seconds from the game's
    countdown, when it was read. Returns the record."""
    rec = dict(rec)
    rec["tries"] = [t for t in rec.get("tries", []) if now - t < 24 * 3600] + [now]
    rec["last_result"] = result
    if wait is not None:
        rec["next_at"] = now + wait + COUNTDOWN_MARGIN
        rec["next_from_game"] = True
    elif result == "opened":
        rec["next_at"] = next_utc_midnight(now)
        rec["next_from_game"] = False
    else:
        rec["next_at"] = now + FAILED_RETRY
        rec["next_from_game"] = False
    if result == "opened":
        rec["last_opened"] = now
    return rec


# -- the claim flow ----------------------------------------------------------------
class DailyChest:
    """Open the daily chest from the main menu and come back to it.

    screen: has grab(); inp: has click(fx, fy); menus: btd6bot.menus.Menus
    (read, identify, find, dismiss_popup). sleep and clock can be replaced
    for offline tests."""

    def __init__(self, screen, inp, menus, sleep=time.sleep, clock=time.time):
        self.s = screen
        self.inp = inp
        self.menus = menus
        self.sleep = sleep
        self.clock = clock
        self.wait = None          # seconds until the next chest, when the game said so

    # one look at the screen: (what classify() calls it, the words read)
    def _look(self):
        name = self.menus.identify()
        words = list(self.menus.words)
        return classify(words, name), words

    def _click_word(self, keys, words):
        """Click the first button whose whole text is one of keys and that
        menus.forbidden() allows. Returns the word clicked or None."""
        for k in keys:
            for w in words:
                if norm(w.text) == k and not forbidden(w.text):
                    self.inp.click(w.x, w.y)
                    return w.text
        return None

    def _note_countdown(self, words):
        secs = countdown_seconds(words)
        if secs is not None:
            self.wait = secs

    def claim(self):
        """Click the chest and walk through whatever follows.

        Returns one of "opened" (the reward screen or a reward popup came up:
        today's chest was claimed - unless the game also shows that screen
        for a chest claimed earlier, which is not known yet), "not_ready" (the
        game showed its countdown
        and no reward screen), "no_response" (nothing changed after the
        click), "not_on_main_menu", or "bailed: <why>". Always tries to end
        on the main menu."""
        kind, _ = self._look()
        if kind != "main_menu":
            log.info("daily chest: not on the main menu (%s) - not clicking", kind)
            return "not_on_main_menu"
        log.info("daily chest: clicking the chest at %.3f,%.3f", *CHEST)
        self.inp.click(*CHEST)
        clicked_at = self.clock()
        seen_rewards = False
        unknown = 0
        for _ in range(MAX_STEPS):
            self.sleep(0.8)
            kind, words = self._look()
            self._note_countdown(words)
            if kind == "shop":
                return self._bail("a store or purchase page", words)
            if kind == "main_menu":
                if seen_rewards:
                    log.info("daily chest: opened (reward screen seen), back on the main menu")
                    return "opened"
                if self.clock() - clicked_at < OPEN_WAIT:
                    continue      # the chest may still be playing its opening animation
                if self.wait is not None:
                    log.info("daily chest: not ready - the game says %.1f h", self.wait / 3600)
                    return "not_ready"
                log.info("daily chest: the click changed nothing")
                return "no_response"
            unknown = unknown + 1 if kind == "unknown" else 0
            if kind == "notify_prompt":
                # turning notifications on is a setting: always decline
                hit = self._click_word(DECLINE_BUTTONS, words)
                if not hit:
                    return self._bail("a notification question without a No button", words)
                log.info("daily chest: declined the notification question via %r", hit)
            elif kind == "rewards":
                seen_rewards = True
                hit = self._click_word(("claim", "collect"), words)
                if hit:
                    log.info("daily chest: pressed %r on the reward screen", hit)
                    self.sleep(1.5)
                    continue
                log.info("daily chest: reward screen shown (%s) - leaving by the back arrow",
                         "next in %.1f h" % (self.wait / 3600) if self.wait is not None else "no countdown read")
                self.inp.click(*BACK_ARROW)
            elif kind == "insta_reward":
                seen_rewards = True
                log.info("daily chest: Insta Monkey reward - closing its panel")
                self.inp.click(0.5, 0.5)
            elif kind in ("reward_cards", "collection_event"):
                seen_rewards = True
                self.menus.handle_collection_event()
            elif kind == "popup":
                seen_rewards = True   # a reward panel ("+100 Monkey Money ... OK")
                hit = self._click_word(CLAIM_BUTTONS, words)
                if hit:
                    log.info("daily chest: closed a reward popup via %r", hit)
                elif not self.menus.dismiss_popup():
                    return self._bail("a popup it could not close", words)
            elif kind == "countdown":
                # countdown over some other screen (a speech bubble or the
                # reward screen read badly): leave it the usual way
                self.inp.click(*BACK_ARROW)
            elif unknown >= MAX_UNKNOWN:
                return self._bail("an unknown screen", words)
        return self._bail("too many steps", self.menus.words)

    def _bail(self, why, words):
        """Something unexpected: log what was on screen and return to the main
        menu with the back arrow (never Esc)."""
        text = " | ".join(w.text for w in list(words)[:25])
        log.warning("daily chest: bailing out - %s; screen read: %s", why, text)
        for _ in range(3):
            if self.menus.identify() == "main_menu":
                break
            self.inp.click(*BACK_ARROW)
            self.sleep(1.0)
        return f"bailed: {why}"


def run_if_due(screen, inp, menus, account_key, state_path=STATE_FILE, now=None, chest=None):
    """The runner's entry point between games (on the main menu): try the
    chest when is_due() says so, save the outcome. Returns the result, or
    None when nothing was tried."""
    now = time.time() if now is None else now
    frame = screen.grab()
    glowing, share, control = chest_glows(frame)
    state = load_state(state_path)
    rec = state.get(account_key, {})
    due, why = is_due(rec, now, glowing)
    if not due:
        log.debug("daily chest: not due (%s; glow %.2f, control %.2f)", why, share, control)
        return None
    log.info("daily chest: trying (%s; glow %.2f, control %.2f, glowing=%s)", why, share, control, glowing)
    chest = chest or DailyChest(screen, inp, menus)
    result = chest.claim()
    if result == "not_on_main_menu":
        return result         # nothing was clicked: does not count as a try
    state[account_key] = record_result(rec, now, result, chest.wait)
    save_state(state, state_path)
    nxt = state[account_key]["next_at"]
    log.info("daily chest: %s; next try after %s", result,
             time.strftime("%Y-%m-%d %H:%M", time.localtime(nxt)))
    return result
