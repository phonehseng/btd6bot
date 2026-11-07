"""Use owned Powers and place owned Insta Monkeys during a normal game, for
the achievements You've Got the Power / Power User / Empowered (power uses)
and Insta Century / Instant Gratification (insta placements).

When (plan_extras decides, the match runs it once per game)
  * only while one of those achievement cards is wanted (achtasks.wanted);
  * only in a game the bot is sure of: Easy or Medium (ALLOWED_MODES), the
    planner's p >= MIN_P, never an achievement build (its constraints may
    forbid extra towers), never CHIMPS (the game forbids powers there and
    crosses out the button), Instas never in Primary/Military Only;
  * once, before the first round starts (Match.play, after setup and before
    Play): the game is waiting, no bloon is on the track, nothing is lost by
    taking a few seconds;
  * within the daily caps of achtasks (power uses, insta uses, clicks).

What the game shows (from the bot's own recordings, 1280x800, 2026-11-07)
  The Powers button is the square button left of Play/Fast-forward at the
  bottom of the right-hand tower panel: a yellow lightning bolt in a normal
  game (rec_20261107_151000.mkv, Downstream Half Cash) and a brown button
  crossed out in red in CHIMPS (rec_20261107_173100.mkv). Its centre is
  POWERS_BUTTON. NO recording shows the panel it opens: neither the bot nor
  the owner opened it while recording (all 242 recordings of the day were
  scanned). So everything after the click is read, not assumed:
  * the panel is taken as open when OCR of the side panel reads a known
    Power name or the Insta Monkeys tab; a power counts as owned only when a
    count ("x3" or "3") is read next to its name;
  * an unknown screen, a shop-like page (achtasks.real_money, menus.page_
    forbidden) or a purchase question ends the routine: the question is
    declined with its Cancel/No/Close, nothing is confirmed in a game;
  * every opening of the panel saves a screenshot (up to LOOKS_PER_DAY a
    day) under logs/achievement_captures/ and logs the words read, so the
    first live runs calibrate this module.

Using a Power
  Click its name. A track Power (Road Spikes, Glue Trap, Camo Trap, MOAB
  Mine) is then held on the cursor like a tower (Game.is_holding sees the
  red cancel X): it is dropped on a point of the track late in the route
  (track_points); an instant Power (Monkey Boost, Thrive) works at once.
  Cash Drop is placed on open ground. A Power still held after
  TARGET_TRIES clicks is put back with Game.cancel_hold.

Placing an Insta Monkey
  Click the Insta Monkeys tab, then a tower name (if the tab lists towers),
  then a tier "a-b-c": the Insta is held like a tower and dropped on a free
  spot near the track (insta_spots). The tier is the lowest one on offer,
  except one tier-5 Insta while Instant Gratification is wanted.

Never: a key press (Esc ends the operator's session), a purchase, a click
on a word outside this module's allow-lists.
"""
import logging
import re
import time
from pathlib import Path

import cv2
import numpy as np

from . import achtasks as A
from .menus import page_forbidden
from .vision import norm, save

log = logging.getLogger("powers")

# -- where things are (fractions of the game window) ----------------------------
POWERS_BUTTON = (0.892, 0.903)            # the lightning button left of Play
POWERS_BUTTON_BOX = (0.870, 0.865, 0.915, 0.945)
SIDEBAR = (0.855, 0.09, 0.998, 0.86)      # the right-hand panel (towers / powers)
CAPTURE_DIR = A.CAPTURE_DIR

# The lit button: saturated yellow covering most of POWERS_BUTTON_BOX
# (measured 0.66 in a normal game, 0.00 in CHIMPS and on menus).
LIT_HUE = (18, 35)
LIT_MIN_SHARE = 0.30
# Tower tiles in the side panel are blue: their share tells whether the
# tower list is back after the panel was closed (0.20-0.22 measured).
TILE_HUE = (95, 115)
TILES_MIN_SHARE = 0.08

# -- when ---------------------------------------------------------------------------
# mode -> what may be used there ("both" = powers and instas)
ALLOWED_MODES = {"easy": "both", "medium": "both", "reverse": "both",
                 "primary_only": "powers", "military_only": "powers"}
MIN_P = 0.85                              # planner.CONFIDENT_P: only sure games
POWERS_PER_GAME = 2
INSTAS_PER_GAME = 2
TARGET_TRIES = 3                          # target clicks for a held Power or Insta
SETTLE = 0.8                              # seconds for the panel to draw after a click

# -- what may be clicked -------------------------------------------------------------
# Powers in the order they are used: cheap track powers first, then the
# instant ones; Time Stop (slows the game), Super Monkey Storm and the
# placeable towers (Banana Farmer, Tech Bot, Totem, Pontoon, Lake) are left out.
POWER_USE = {"roadspikes": "track", "gluetrap": "track", "camotrap": "track", "moabmine": "track",
             "monkeyboost": "instant", "thrive": "instant", "cashdrop": "ground"}
POWER_ORDER = tuple(POWER_USE)
INSTA_TABS = ("instamonkeys", "instas", "insta")
DECLINE = ("cancel", "no", "close", "nothanks", "back")
COUNT = re.compile(r"^[xÃ—]?(\d{1,3})$")
TIER = re.compile(r"^([0-5])-([0-5])-([0-5])$")


# -- reading -----------------------------------------------------------------------
def _share(frame, region, hue, min_sat=120, min_val=0):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    patch = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= hue[0]) & (hsv[..., 0] <= hue[1]) & (hsv[..., 1] >= min_sat) & (hsv[..., 2] >= min_val)
    return float(m.mean())


def button_lit(frame):
    """Is the Powers button there and usable (yellow bolt, not crossed out)?"""
    return _share(frame, POWERS_BUTTON_BOX, LIT_HUE, 150, 200) >= LIT_MIN_SHARE


def tower_list_shown(frame):
    """Are the blue tower tiles in the side panel (the panel is closed)?"""
    return _share(frame, SIDEBAR, TILE_HUE) >= TILES_MIN_SHARE


def _near(a, b, dx=0.06, dy=0.08):
    return abs(a.x - b.x) <= dx and abs(a.y - b.y) <= dy


def owned_powers(words):
    """{power: (name word, count)} for every allowed Power whose name and a
    count next to it were read. A name with no count is not owned (or its
    count is unreadable): it is never clicked. Each count belongs to the
    nearest name read (any name, not only allowed Powers), so a count is
    never credited to a neighbouring tile."""
    out = {}
    names = [w for w in words if sum(c.isalpha() for c in norm(w.text)) >= 4]
    for cw in words:
        m = COUNT.match(norm(cw.text))
        if not m or int(m.group(1)) <= 0:
            continue
        close = [w for w in names if _near(w, cw)]
        if not close:
            continue
        w = min(close, key=lambda w: abs(w.x - cw.x) + abs(w.y - cw.y))
        n = norm(w.text)
        if n in POWER_USE and n not in out and not A.real_money(w.text):
            out[n] = (w, int(m.group(1)))
    return out


def classify_panel(words):
    """'shop' (store / purchase wording), 'powers' (a Power name or the
    Insta Monkeys tab read), 'tiers' (Insta tiers "a-b-c" read) or 'unknown'."""
    if page_forbidden(words) or any(A.real_money(w.text) for w in words):
        return "shop"
    norms = [norm(w.text) for w in words]
    if any(TIER.match(w.text.strip()) for w in words):
        return "tiers"
    if any(n in POWER_USE or n in INSTA_TABS for n in norms):
        return "powers"
    return "unknown"


def tier_words(words):
    """[(word, (a, b, c))] for every Insta tier read."""
    out = []
    for w in words:
        m = TIER.match(w.text.strip())
        if m:
            out.append((w, tuple(int(g) for g in m.groups())))
    return out


def pick_tier(tiers, want_t5):
    """The tier to place: a tier-5 one when Instant Gratification is wanted
    and one is offered, otherwise the lowest total (spares the good ones)."""
    if not tiers:
        return None
    if want_t5:
        t5 = [t for t in tiers if 5 in t[1]]
        if t5:
            return t5[0]
    return min(tiers, key=lambda t: (sum(t[1]), max(t[1])))


# -- targets ------------------------------------------------------------------------
def track_points(model, n=TARGET_TRIES, lo=0.55, hi=0.9):
    """Screen points on the track late in the route (where a track Power
    catches what got through). Falls back to any track cell."""
    try:
        mask = model.track_mask()
        cells = np.argwhere(mask)
        if len(cells) and model.known():
            prog = model.progress_full()
            late = [(cy, cx) for cy, cx in cells if lo <= prog[cy, cx] <= hi]
            late.sort(key=lambda c: prog[c[0], c[1]])
            cells = late or [tuple(c) for c in cells]
        else:
            weight = model.track_weight()
            cells = [tuple(c) for c in np.argwhere(weight > 0.5)]
        if not len(cells):
            return []
        step = max(1, len(cells) // (n + 1))
        picks = [cells[i] for i in range(step, len(cells), step)][:n]
        return [model.cell_to_frac(int(cx), int(cy)) for cy, cx in picks]
    except Exception:
        log.exception("achievement: no track points")
        return []


def insta_spots(model, avoid, n=TARGET_TRIES):
    """Free land spots near the track for an Insta (best coverage first)."""
    try:
        cover = model.score_spots(6, avoid=avoid)
        return [model.cell_to_frac(cx, cy) for cx, cy, _ in model.best_spots(cover, n=n)]
    except Exception:
        log.exception("achievement: no insta spots")
        return []


# -- the routine ---------------------------------------------------------------------
class InGameExtras:
    """Use up to POWERS_PER_GAME Powers and place up to INSTAS_PER_GAME
    Instas once, before round 1 of a game (see the module notes).

    budget: achtasks.Budget of the signed-in account. want_*: which cards
    are wanted. allow_instas: False in modes with a tower restriction."""

    def __init__(self, budget, want_powers, want_instas, want_t5=False, allow_instas=True,
                 sleep=time.sleep, capture_dir=CAPTURE_DIR):
        self.budget = budget
        self.want_powers = want_powers
        self.want_instas = want_instas and allow_instas
        self.want_t5 = want_t5 and self.want_instas
        self.sleep = sleep
        self.capture_dir = Path(capture_dir)
        self.summary = {"powers": [], "instas": [], "result": None}

    # -- helpers ---------------------------------------------------------------------
    def _read(self):
        self.sleep(SETTLE)
        return list(self.menus.v.read(SIDEBAR))

    def _capture(self, frame, what, words):
        """Calibration: keep the screen and say what was read."""
        log.info("achievement: %s read: %s", what, A.screen_text(words))
        if self.budget.used("looks_" + what) >= A.LOOKS_PER_DAY:
            return
        self.budget.add("looks_" + what)
        try:
            save(frame, self.capture_dir / f"{what}_{time.strftime('%Y%m%d_%H%M%S')}.png")
        except Exception:
            pass

    def _decline(self, words):
        """A purchase question in the game: answer it with Cancel/No/Close."""
        w = A.find_allowed(words, DECLINE)
        if w is not None:
            log.warning("achievement: purchase question in the game - declining via %r", w.text)
            self.inp.click(w.x, w.y)
            self.sleep(SETTLE)
            return True
        return False

    def _close(self):
        """Close the panel with its own button and check the tower list is back."""
        f = self.g.fresh()
        if self.g.is_holding(f):
            self.g.cancel_hold()
        if not tower_list_shown(self.g.fresh()):
            self.inp.click(*POWERS_BUTTON)
            self.sleep(SETTLE)
        if not tower_list_shown(self.g.fresh()):
            log.warning("achievement: the tower list did not come back after the powers panel - closing panels")
            self.g.close_panels()

    def _drop(self, points, what):
        """Something (a Power or an Insta) is on the cursor: click target
        points until it is gone. True when it was placed."""
        for pt in points[:TARGET_TRIES]:
            self.inp.click(*pt)
            self.sleep(0.4)
            if not self.g.is_holding():
                log.info("achievement: %s placed at %.3f,%.3f", what, *pt)
                return True
        log.warning("achievement: %s could not be placed - putting it back", what)
        self.g.cancel_hold()
        return False

    def _bail(self, why, words):
        log.warning("achievement: powers panel - bailing out (%s); screen read: %s", why, A.screen_text(words))
        self.budget.add("powers_failures")
        self.summary["result"] = f"bailed: {why}"
        return self.summary

    # -- one power ----------------------------------------------------------------------
    def _use_power(self, name, word, count, model):
        kind = POWER_USE[name]
        if not self.budget.allow("power_uses"):
            return False
        self.inp.click(word.x, word.y)
        self.sleep(0.5)
        words = self._read()
        if classify_panel(words) == "shop":
            self._decline(words)
            raise _Bail("a purchase question after clicking " + name, words)
        held = self.g.is_holding()
        if kind == "instant" and not held:
            used = True
        elif held:
            pts = track_points(model) if kind == "track" else insta_spots(model, self.avoid)
            used = self._drop(pts, name)
        else:
            used = False
        # the count next to the name tells whether it really went
        after = owned_powers(self._read()).get(name)
        verified = after is not None and after[1] == count - 1
        if used:
            self.budget.add("power_uses")
            self.summary["powers"].append(name)
            log.info("achievement: Power used: %s (count %d -> %s, %s)", name, count,
                     after[1] if after else "?", "verified" if verified else "unverified")
        else:
            log.warning("achievement: clicked Power %s but it was not used", name)
        return used

    def _use_powers(self, owned, model):
        n = 0
        for name in POWER_ORDER:
            if n >= POWERS_PER_GAME or not self.budget.allow("power_uses"):
                break
            if name not in owned:
                continue
            words = self._read()
            cur = owned_powers(words).get(name)
            if cur is None:
                # the panel closed after the last use: open it again
                if not self._open():
                    break
                cur = owned_powers(self._read()).get(name)
                if cur is None:
                    continue
            if self._use_power(name, cur[0], cur[1], model):
                n += 1
        return n

    # -- one insta ------------------------------------------------------------------------
    def _place_insta(self, model):
        words = self._read()
        if classify_panel(words) not in ("powers", "tiers") and not self._open():
            return False
        words = self._read()
        if classify_panel(words) != "tiers":
            tab = A.find_allowed(words, INSTA_TABS)
            if tab is None:
                log.info("achievement: no Insta Monkeys tab read in the powers panel")
                return False
            self.inp.click(tab.x, tab.y)
            words = self._read()
            self._capture(self.g.fresh(), "insta_panel", words)
            if classify_panel(words) == "shop":
                self._decline(words)
                raise _Bail("a shop page after the Insta tab", words)
            if not tier_words(words):
                tower = self._insta_tower(words)
                if tower is None:
                    log.info("achievement: no owned Insta tower read")
                    return False
                self.inp.click(tower.x, tower.y)
                words = self._read()
        pick = pick_tier(tier_words(words), self.want_t5)
        if pick is None:
            log.info("achievement: no Insta tier read")
            return False
        word, tier = pick
        self.inp.click(word.x, word.y)
        self.sleep(0.5)
        if classify_panel(self._read()) == "shop":
            raise _Bail("a purchase question after an Insta tier", self.menus.v.read(SIDEBAR))
        if not self.g.is_holding():
            log.warning("achievement: Insta %s did not come onto the cursor", word.text)
            return False
        placed = self._drop(insta_spots(model, self.avoid), "Insta " + word.text)
        if placed:
            self.budget.add("insta_uses")
            self.summary["instas"].append("-".join(map(str, tier)))
            if 5 in tier:
                self.want_t5 = False
                log.info("achievement: Instant Gratification - a tier-5 Insta (%s) placed", word.text)
        return placed

    @staticmethod
    def _insta_tower(words):
        """A tower name with a count next to it on the Insta tab."""
        from . import towers as T
        names = {norm(t["name"]): k for k, t in T.TOWERS.items() if t.get("name")}
        counts = [w for w in words if COUNT.match(norm(w.text))]
        for w in words:
            if norm(w.text) in names and any(_near(w, c) for c in counts) and not A.real_money(w.text):
                return w
        return None

    # -- open --------------------------------------------------------------------------------
    def _open(self):
        """Click the Powers button and read the panel. True when it shows."""
        f = self.g.fresh()
        if not button_lit(f):
            log.info("achievement: the Powers button is not lit - nothing to do")
            return False
        self.inp.click(*POWERS_BUTTON)
        words = self._read()
        kind = classify_panel(words)
        self._capture(self.g.fresh(), "powers_panel", words)
        if kind == "shop":
            self._decline(words)
            raise _Bail("a shop page behind the Powers button", words)
        if kind == "unknown":
            raise _Bail("the panel could not be read", words)
        return True

    def run(self, game, menus, model, avoid=()):
        """Open the panel, use Powers, place Instas, close it. Returns a
        summary dict; never raises (a failure closes the panel and is logged)."""
        self.g, self.menus, self.avoid = game, menus, list(avoid)
        self.inp = A.CountingInput(game.inp, self.budget)
        if self.budget.resting("powers"):
            log.info("achievement: powers panel resting until tomorrow (failed %d times today)",
                     A.FAILURES_PER_DAY)
            self.summary["result"] = "resting"
            return self.summary
        opened = False
        try:
            if not self._open():
                self.summary["result"] = "button not lit"
                return self.summary
            opened = True
            words = self._read()
            owned = owned_powers(words)
            self.budget.set_flag("powers_seen", {"at": time.time(), "owned": sorted(owned)})
            if self.want_powers:
                if owned:
                    self._use_powers(owned, model)
                else:
                    log.info("achievement: no owned Power read in the panel (Power names read: %s)",
                             [norm(w.text) for w in words if norm(w.text) in POWER_USE] or "none")
            for _ in range(INSTAS_PER_GAME if self.want_instas else 0):
                if not self.budget.allow("insta_uses") or not self._place_insta(model):
                    break
            self.summary["result"] = "done"
            log.info("achievement: powers panel done - powers %s, instas %s",
                     self.summary["powers"] or "none", self.summary["instas"] or "none")
            return self.summary
        except _Bail as b:
            return self._bail(b.why, b.words)
        except A.CapReached as e:
            log.warning("achievement: %s - stopping", e)
            self.summary["result"] = "cap"
            return self.summary
        except Exception:
            log.exception("achievement: powers panel failed")
            self.budget.add("powers_failures")
            self.summary["result"] = "error"
            return self.summary
        finally:
            if opened or not tower_list_shown(game.fresh()):
                try:
                    self._close()
                except Exception:
                    log.exception("achievement: closing the powers panel failed")


class _Bail(Exception):
    def __init__(self, why, words):
        super().__init__(why)
        self.why, self.words = why, list(words or [])


# -- the runner's entry point --------------------------------------------------------------
def plan_extras(plan, strat, account_key, statuses=None, budget=None):
    """An InGameExtras for this game, or None (and the reason is logged once).

    plan: planner.GamePlan (mode_key, p_win); strat: the strategy dict."""
    allowed = ALLOWED_MODES.get(plan.mode_key)
    if allowed is None:
        return None
    if (strat or {}).get("achievement"):
        return None                       # its constraints come first
    if (plan.p_win or 0) < MIN_P:
        return None
    statuses = A.card_statuses() if statuses is None else statuses
    powers = A.wanted(A.POWER_CARDS, statuses)
    instas = A.wanted(A.INSTA_CARDS, statuses)
    if not powers and not instas:
        return None
    budget = budget or A.Budget(account_key)
    if not budget.allow("power_uses") and not budget.allow("insta_uses"):
        return None
    log.info("achievement: this game uses the powers panel (%s; mode %s, p=%.2f)",
             ", ".join(powers + instas), plan.mode_key, plan.p_win)
    return InGameExtras(budget, bool(powers), bool(instas), A.T5_INSTA_CARD in instas,
                        allow_instas=allowed == "both")
