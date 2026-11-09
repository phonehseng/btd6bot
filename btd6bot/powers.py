"""Use owned Powers and place owned Insta Monkeys during a normal game, for
the achievements You've Got the Power / Power User / Empowered (power uses)
and Insta Century / Instant Gratification (insta placements).

When (plan_extras decides, the match runs it once per game)
  * only while one of those achievement cards is wanted (achtasks.wanted);
  * only in a game the bot is sure of: Easy or Medium (ALLOWED_MODES), the
    planner's p >= MIN_P, never an achievement build (its constraints may
    forbid extra towers), never CHIMPS (the game forbids powers there and
    crosses out the button), Instas never in Primary/Military Only;
  * Instas: once, before the first round starts (Match.play, after setup
    and before Play): no bloon is on the track, nothing is lost by taking a
    few seconds;
  * Powers: once, IN a round (Match._in_round_powers_due: the second round
    the game plays, a few seconds after it started, lives steady, no
    crisis) - the instant Powers (Super Monkey Storm, Monkey Boost, Cash
    Drop ...) are greyed out before round 1 (see "Greyed-out Powers"). The
    run is phase="round": Powers only, the top view's un-greyed ones first,
    else the Insta tab's view (the placed Powers such as Energizing Totem,
    the old pre-round path). With powers_in_round=False the pre-round run
    uses Powers as before;
  * within the daily caps of achtasks (power uses, insta uses, clicks).

The Powers button (recordings, 1280x800, 2026-11-07)
  The square button left of Play/Fast-forward: a yellow lightning bolt in a
  normal game (rec_20261107_151000.mkv) and crossed out in CHIMPS
  (rec_20261107_173100.mkv). Centre POWERS_BUTTON. While the panel is open
  the same button shows a monkey face and brings the tower list back.

What the panel shows (first live run, Tricky Tracks Easy 2026-11-08 00:26,
logs/achievement_captures/powers_panel_20261108_002637.png and
insta_panel_20261108_002642.png, 1920x1200)
  * a "POWERS" header, three tab buttons under it (lightning = Powers,
    lightning+ = ?, monkey face = Insta Monkeys: INSTA_TAB);
  * Powers tab: a two-column grid of hexagon icons with NO names and NO
    prices. Purple hexes (the He-Man event powers) and blue hexes (Banana
    Farmer, Tech Bot, Portable Lake ...) carry no badge; the tenth, a gold
    hexagon, carries an orange round badge "22", and under it an "INSTA
    MONKEYS" jump button (see "Greyed-out Powers" below: it is drawn over
    more owned Powers, the Insta list comes further down). The shop's Powers page
    (rec_20261108_005701.mkv 0:41) lists the same icons in the same order
    and shows what the colours mean: purple and blue = not owned, gold with
    a count = owned (22, 15, 5, 12, 19, 24 ... on that account). So a Power
    counts as owned only when its hexagon is gold AND carries a count badge
    (power_badges); the first version wrongly skipped the "22" hexagon.
  * Insta list (the divider clicked, or scrolled down): blue tower tiles,
    each with an orange count badge (9, 12, 14, 20, 12, 11, 19, 6, 16, 9 on
    that account): insta_badges. Gold Power hexagons above them are not
    Instas and are left out.
  The badge: an orange ring (HSV hue 5-22) about 0.027 of the window wide
  and 0.044 high around a yellow disc with the number; the icon it belongs
  to is centred BADGE_TO_ICON below-left of it.

Greyed-out Powers (2026-11-09, rec_20261109_065800.mkv 0:30-0:40 and every
powers_panel_* capture since 2026-11-08)
  The panel is ONE scrolling two-column list: the purple event Powers, the
  blue Powers Pro (not owned), then the owned standard Powers in the shop's
  order (Super Monkey Storm 22, Monkey Boost 15, Thrive 5, Time Stop 12,
  Cash Drop 19, ...), then the Insta towers. "INSTA MONKEYS" with its down
  arrow is a sticky jump button drawn OVER the bottom row (the badges "15"
  and "5" of Monkey Boost and Thrive show faintly through it), not an
  entry: it has no badge and is never taken for a Power.
  The gold "22" is Super Monkey Storm (the shop's 22) - but before round 1
  its art is washed out (power_greyed), like every icon in the top view,
  selected or not, for the whole 10 s the panel was open. Hexagon click, map
  click and drag never moved its count (02:46, 19:55, 20:06, 05:40, 06:58).
  The Insta tab's jump shows the end of the Powers list instead: Portable
  Lake, Tech Bot and Energizing Totem ("9") in FULL colour - placed Powers
  are usable there, the instant ones are not (all captures are before round
  1 with FAST TRACK ENABLED; whether the greying comes from "between rounds"
  or from Fast Track is not told apart by them). So only a gold, badged AND
  not greyed hexagon is used (usable_powers): in the top view if any, else
  in the Insta tab's view.

Using a Power (only one with a badge; never one without - it may be a
purchase - and never a greyed one)
  Click its hexagon. If something comes onto the cursor (Game.is_holding,
  the red cancel X) it is a placed Power: dropped on the track late in the
  route (track_points), else on open ground near the track (insta_spots),
  else put back. If nothing comes onto the cursor it is an instant Power:
  used when its badge count went down (or the badge went away while the
  panel still shows its Powers tab). A click that closed the panel proves
  nothing: the panel is opened again and the count compared there
  (_check_use; live 2026-11-09 05:40 the map click only closed it). When
  the map click closed the panel and the count stayed, one drag of the
  hexagon onto the track is tried (once per Power per game); the log says
  which gesture used it ("used by drag", "used by select + map click"). Anything
  else (a question, an unknown screen) ends the routine; a question is
  answered Cancel/No, nothing is ever confirmed in a game.

Placing an Insta Monkey
  Insta tab, the tower with the most Instas (a badge), then its list of
  tiers. That list has not been seen yet: when it shows tier labels
  ("2-0-0") the lowest is placed like a tower (one tier 5 while Instant
  Gratification is wanted); otherwise it is captured, logged, and the
  routine closes the panel without placing anything.

Every step saves a capture (a few a day) under logs/achievement_captures/
and logs what was read. Never: a key press (Esc ends the operator's
session), a purchase, a click outside the panel's badged icons, its tabs,
the target points and the Cancel/No of a question.
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
POWERS_BUTTON = (0.892, 0.903)            # lightning button left of Play (monkey face while open)
POWERS_BUTTON_BOX = (0.870, 0.865, 0.915, 0.945)
SIDEBAR = (0.855, 0.09, 0.998, 0.86)      # the right-hand panel (towers / powers)
INSTA_TAB = (0.972, 0.150)                # the monkey-face tab under "POWERS"
GRID = (0.855, 0.19, 0.998, 0.83)         # the icon grid under the tabs
CAPTURE_DIR = A.CAPTURE_DIR

# The lit button: saturated yellow covering most of POWERS_BUTTON_BOX
# (measured 0.66 in a normal game, 0.00 in CHIMPS and on menus).
LIT_HUE = (18, 35)
LIT_MIN_SHARE = 0.30
# Tower tiles in the side panel are blue: their share tells whether the
# tower list is back after the panel was closed (0.20-0.22 measured).
TILE_HUE = (95, 115)
TILES_MIN_SHARE = 0.08

# Count badges (measured on the two live captures): the orange ring's
# bounding box is 0.027 x 0.043-0.044 of the window, filled 0.27-0.29.
BADGE_HUE = (5, 22)
BADGE_W = (0.020, 0.035)
BADGE_H = (0.033, 0.056)
BADGE_FILL = (0.15, 0.45)
BADGE_TO_ICON = (-0.019, 0.028)           # badge centre -> its icon's centre
ICON_HALF = (0.025, 0.035)
GOLD_HUE = (18, 34)                       # gold hexagon = an owned Power (is_gold_tile)
GOLD_MIN_SHARE = 0.30
# A greyed-out (unusable now) Power: its art is washed into the gold, so
# hardly any strongly coloured pixel outside the gold/olive hues is left in
# the middle of the hexagon. Share of such pixels in GREY_HALF around the
# icon: 0.012-0.024 for the greyed Super Monkey Storm (7 captures and the
# fixture), 0.154-0.185 for the full-colour Energizing Totem.
GREY_HALF = (0.018, 0.026)
GREY_ART_HUE = (12, 40)                   # the gold/olive tint a greyed icon is washed into
ART_MIN_SHARE = 0.06

# -- when ---------------------------------------------------------------------------
# mode -> what may be used there ("both" = powers and instas)
ALLOWED_MODES = {"easy": "both", "medium": "both", "reverse": "both",
                 "primary_only": "powers", "military_only": "powers"}
MIN_P = 0.85                              # planner.CONFIDENT_P: only sure games
POWERS_PER_GAME = 2
INSTAS_PER_GAME = 1
TARGET_TRIES = 3                          # target clicks for a held Power or Insta
SETTLE = 0.8                              # seconds for the panel to draw after a click

INSTA_TABS = ("instamonkeys", "instas")
PANEL_WORDS = ("powers", "instamonkeys")
DECLINE = ("cancel", "no", "close", "nothanks", "back")
TIER = re.compile(r"^([0-5])-([0-5])-([0-5])$")


# -- reading -----------------------------------------------------------------------
def _share(frame, region, hue, min_sat=120, min_val=0):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    patch = frame[max(0, int(y0 * h)):int(y1 * h), max(0, int(x0 * w)):int(x1 * w)]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= hue[0]) & (hsv[..., 0] <= hue[1]) & (hsv[..., 1] >= min_sat) & (hsv[..., 2] >= min_val)
    return float(m.mean())


def button_lit(frame):
    """Is the Powers button there and usable (yellow bolt, not crossed out)?"""
    return _share(frame, POWERS_BUTTON_BOX, LIT_HUE, 150, 200) >= LIT_MIN_SHARE


def tower_list_shown(frame):
    """Blue in the side panel. NOT a test for the panel being closed: the
    powers panel is blue too (0.2+ on both live captures). Kept for
    callers that only need "the side panel is drawn"."""
    return _share(frame, SIDEBAR, TILE_HUE) >= TILES_MIN_SHARE


def panel_closed(frame):
    """The tower list is back: the button shows its yellow lightning bolt
    again (while the panel is open it shows a blue monkey face; measured
    lit share 0.00 on both live captures). Only meaningful outside CHIMPS."""
    return button_lit(frame)


def on_powers_tab(frame, words=()):
    """The panel shows its Powers part (not scrolled to the Insta list): the
    INSTA MONKEYS divider is read low in the panel, or every badge seen
    sits on a gold Power hexagon (the Insta list's tiles are blue)."""
    if any(norm(w.text) == "instamonkeys" and w.y > 0.6 for w in words):
        return True
    badges = find_badges(frame)
    return bool(badges) and all(is_gold_tile(frame, icon_of(b)) for b in badges)


def find_badges(frame, region=GRID):
    """Orange count badges inside region: [(badge_x, badge_y)] in window
    fractions, top to bottom, left to right."""
    h, w = frame.shape[:2]
    x0, y0 = int(region[0] * w), int(region[1] * h)
    x1, y1 = int(region[2] * w), int(region[3] * h)
    patch = frame[y0:y1, x0:x1]
    if patch.size == 0:
        return []
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (BADGE_HUE[0], 150, 200), (BADGE_HUE[1], 255, 255))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if not (BADGE_W[0] <= bw / w <= BADGE_W[1] and BADGE_H[0] <= bh / h <= BADGE_H[1]):
            continue
        if not BADGE_FILL[0] <= area / float(bw * bh) <= BADGE_FILL[1]:
            continue
        out.append(((x0 + bx + bw / 2) / w, (y0 + by + bh / 2) / h))
    return sorted(out, key=lambda b: (round(b[1], 2), b[0]))


def icon_of(badge):
    return badge[0] + BADGE_TO_ICON[0], badge[1] + BADGE_TO_ICON[1]


def _icon_box(icon):
    return (icon[0] - ICON_HALF[0], icon[1] - ICON_HALF[1], icon[0] + ICON_HALF[0], icon[1] + ICON_HALF[1])


def is_gold_tile(frame, icon, half=None):
    """A gold hexagon: how the game draws a Power the account OWNS.

    The shop's Powers page (rec_20261108_005701.mkv 0:41) lists the same
    icons in the same order as the in-game panel: purple (event) and blue
    hexagons without a badge - not owned - then gold hexagons with a count
    (22, 15, 5, 12, 19, 24 ...). So the in-game "22" gold hexagon above the
    INSTA MONKEYS label is an owned Power (the first version took it for an
    Insta tile and skipped it); the label is a divider before the Insta list
    further down. Insta towers are blue square tiles.

    Measured share of gold in the icon box: in game 0.57-0.58 for the gold
    hexagons, 0.04-0.16 for Insta tiles; on the shop page (bigger tiles,
    half = (0.04, 0.06)) 0.37-0.50. half: the box's half size."""
    hx, hy = half or ICON_HALF
    box = (icon[0] - hx, icon[1] - hy, icon[0] + hx, icon[1] + hy)
    return _share(frame, box, GOLD_HUE, 150, 180) >= GOLD_MIN_SHARE


def _divider_y(words):
    """y of the "INSTA MONKEYS" divider under the Powers, or None."""
    ys = [w.y for w in words if norm(w.text) == "instamonkeys"]
    return min(ys) if ys else None


def power_badges(frame, words=()):
    """Icons of owned Powers: gold hexagons carrying a count badge, above the
    INSTA MONKEYS jump button when it is read (the row under it shows
    through it and is not clickable). Greyed ones included. [(icon, badge)]"""
    top = _divider_y(words)
    out = []
    for b in find_badges(frame):
        icon = icon_of(b)
        if top is not None and icon[1] > top - 0.03:
            continue
        if is_gold_tile(frame, icon):
            out.append((icon, b))
    return out


def power_greyed(frame, icon):
    """Is this Power hexagon drawn washed out (not usable right now)? See
    the module notes: the greyed Super Monkey Storm keeps its gold hexagon
    and orange badge, only its art loses its colours."""
    hx, hy = GREY_HALF
    box = (icon[0] - hx, icon[1] - hy, icon[0] + hx, icon[1] + hy)
    colourful = (_share(frame, box, (0, GREY_ART_HUE[0] - 1), 130, 110)
                 + _share(frame, box, (GREY_ART_HUE[1] + 1, 180), 130, 110))
    return colourful < ART_MIN_SHARE


def usable_powers(frame, words=()):
    """Owned Powers that can be used now: gold, badged, not greyed.
    [(icon, badge)]"""
    return [(icon, b) for icon, b in power_badges(frame, words) if not power_greyed(frame, icon)]


def insta_badges(frame):
    """Icons of Insta towers: badged tiles that are not gold Power hexagons.
    [(icon, badge)]"""
    return [(icon_of(b), b) for b in find_badges(frame) if not is_gold_tile(frame, icon_of(b))]


def badge_region(badge):
    return (badge[0] - 0.016, badge[1] - 0.025, badge[0] + 0.016, badge[1] + 0.025)


def read_count(words):
    """The number OCR read on a badge, or None."""
    digits = "".join(c for w in words for c in w.text if c.isdigit())
    return int(digits) if digits and len(digits) <= 3 else None


def badge_near(badges, badge, tol=0.012):
    """The badge in `badges` at the same place as `badge`, or None."""
    for b in badges:
        if abs(b[0] - badge[0]) <= tol and abs(b[1] - badge[1]) <= tol:
            return b
    return None


def classify_panel(words, frame=None):
    """'shop' (store / purchase wording), 'tiers' (Insta tiers "a-b-c"
    read), 'powers' (the panel's header or Insta tile/tab words, or count
    badges seen) or 'unknown'."""
    if page_forbidden(words) or any(A.real_money(w.text) for w in words):
        return "shop"
    if any(TIER.match(w.text.strip()) for w in words):
        return "tiers"
    norms = [norm(w.text) for w in words]
    if any(n in PANEL_WORDS for n in norms) or (frame is not None and find_badges(frame)):
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
    """Use up to POWERS_PER_GAME owned Powers and place up to
    INSTAS_PER_GAME Instas once, before round 1 (see the module notes).

    budget: achtasks.Budget of the signed-in account. want_*: which cards
    are wanted. allow_instas: False in modes with a tower restriction."""

    def __init__(self, budget, want_powers, want_instas, want_t5=False, allow_instas=True,
                 sleep=time.sleep, capture_dir=CAPTURE_DIR, powers_in_round=True):
        self.budget = budget
        self.want_powers = want_powers
        # Powers wait for a running round (Match calls run(phase="round"))
        self.powers_in_round = powers_in_round
        self.phase = "pre"
        self.want_instas = want_instas and allow_instas
        self.want_t5 = want_t5 and self.want_instas
        self.sleep = sleep
        self.capture_dir = Path(capture_dir)
        self.summary = {"powers": [], "instas": [], "result": None}
        self._dragged = set()             # Power hexagons already dragged this game (one try each)
        self._failure_counted = False     # powers_failures grows at most once per game
        self._view = "powers"             # which view of the list the Power in use sits in
        self.seen = None                  # {"owned", "usable"} for the "powers_seen" flag

    # -- helpers ---------------------------------------------------------------------
    def _look(self, what):
        """Wait, grab, read the side panel, keep a capture. (frame, words)"""
        self.sleep(SETTLE)
        frame = self.g.fresh()
        words = list(self.menus.v.read(SIDEBAR))
        log.info("achievement: %s read: %s", what, A.screen_text(words) or "no words")
        if self.budget.used("looks_powers") < 12:
            self.budget.add("looks_powers")
            try:
                save(frame, self.capture_dir / f"{what}_{time.strftime('%Y%m%d_%H%M%S')}.png")
            except Exception:
                pass
        return frame, words

    def _count(self, badge):
        return read_count(self.menus.v.read(badge_region(badge)))

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
        """Back to the tower list with the panel's own button."""
        if self.g.is_holding(self.g.fresh()):
            self.g.cancel_hold()
        if not panel_closed(self.g.fresh()):
            self.inp.click(*POWERS_BUTTON)
            self.sleep(SETTLE)
        if not panel_closed(self.g.fresh()):
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
        return False

    def _count_failure(self):
        """One powers_failures per game at most, whatever gestures failed."""
        if not self._failure_counted:
            self._failure_counted = True
            self.budget.add("powers_failures")

    def _bail(self, why, words):
        log.warning("achievement: powers panel - bailing out (%s); screen read: %s", why, A.screen_text(words))
        self._count_failure()
        self.summary["result"] = f"bailed: {why}"
        return self.summary

    # -- powers --------------------------------------------------------------------------
    def _use_power(self, slot, icon, badge, model):
        """Click a badged Power hexagon and use it. True when used."""
        before = self._count(badge)
        log.info("achievement: using the owned Power in slot %d at %.3f,%.3f (badge count %s)",
                 slot, icon[0], icon[1], before if before is not None else "unread")
        self.inp.click(*icon)
        self.sleep(0.6)
        if self.g.is_holding():
            placed = (self._drop(track_points(model), f"Power {slot} (track)")
                      or self._drop(insta_spots(model, self.avoid), f"Power {slot} (ground)"))
            if not placed:
                log.warning("achievement: Power %d could not be placed - putting it back", slot)
                self.g.cancel_hold()
                return False
            return self._placed_counts(slot, badge, before)
        frame, words = self._look(f"power{slot}_after")
        self._refuse_shop(frame, words, slot)
        used, reopened = self._check_use(frame, words, badge, before, slot, "the hexagon click")
        if used:
            log.info("achievement: Power %d used by the hexagon click", slot)
            return True
        if reopened:
            raise _Bail(f"Power slot {slot}: the panel closed after the hexagon click and the count "
                        f"stayed {before}", words)
        # Live 02:46 (Super Monkey Storm, the gold "22"): the click only
        # SELECTED the hexagon (a glowing outline, rec_20261108_024601.mkv
        # 0:16), nothing came onto the cursor and the count stayed 22. A
        # second click on the map was meant to fire it: a point late on the
        # track first, then open ground. Each click is checked by the count.
        # Live 2026-11-09 05:40 (rec_20261109_054000.mkv 0:05-0:12) showed
        # what that map click really does: the hexagon glows (selected) for
        # ~2 s, the map click comes, and the next frame shows the tower list
        # ("UPGRADES", the lit bolt button) - no Storm effect, cash and the
        # count unchanged. The map click only closed the panel, so a closed
        # panel is reopened and its count compared (_check_use) before
        # anything counts as used.
        # 2026-11-09: in all of those runs the Storm was GREYED OUT (module
        # notes) - no gesture could have used it, and greyed Powers are no
        # longer clicked. These steps stay for a usable instant Power.
        targets = track_points(model)[:1] + insta_spots(model, self.avoid)[:1]
        for pt in targets:
            log.info("achievement: Power %d selected, not used - clicking the map at %.3f,%.3f", slot, *pt)
            self.inp.click(*pt)
            self.sleep(0.8)
            if self.g.is_holding():
                if self._drop(targets, f"Power {slot}"):
                    return self._placed_counts(slot, badge, before)
                self.g.cancel_hold()
                return False
            frame, words = self._look(f"power{slot}_after_map")
            self._refuse_shop(frame, words, slot)
            used, reopened = self._check_use(frame, words, badge, before, slot, "the map click")
            if used:
                log.info("achievement: Power %d used by select + map click", slot)
                return True
            if reopened:
                # the reopened panel has nothing selected: no hexagon click to let go
                if self._drag_power(slot, icon, badge, before, pt):
                    return True
                raise _Bail(f"Power slot {slot}: the panel closed after the map click and the count "
                            f"stayed {before} - neither the map click nor a drag fired the Power", words)
        # still selected and unused: click the hexagon again to let it go
        self.inp.click(*icon)
        self.sleep(0.4)
        raise _Bail(f"Power slot {slot} clicked but nothing changed (badge {before}, map clicked too)", words)

    def _drag_power(self, slot, icon, badge, before, target):
        """The next gesture after select + map click (which only closed the
        panel, live 2026-11-09 05:40): drag the hexagon onto the map at
        `target` in one press-move-release. At most one drag per Power per
        game, so a gesture that does not work costs one click. True when the
        count went down (checked as _check_use does)."""
        key = (round(icon[0], 3), round(icon[1], 3))
        if key in self._dragged:
            log.info("achievement: Power %d was already dragged once this game - no second drag", slot)
            return False
        self._dragged.add(key)
        frame = self._panel[0]                      # the reopened panel: nothing selected
        now = badge_near(find_badges(frame), badge)
        src = icon_of(now) if now is not None else icon
        log.info("achievement: Power %d - trying a drag from %.3f,%.3f to %.3f,%.3f", slot, *src, *target)
        self.inp.drag(*src, *target)
        self.sleep(0.8)
        if self.g.is_holding():
            log.warning("achievement: Power %d is on the cursor after the drag - putting it back", slot)
            self.g.cancel_hold()
            return False
        frame, words = self._look(f"power{slot}_after_drag")
        self._refuse_shop(frame, words, slot)
        used, _ = self._check_use(frame, words, badge, before, slot, "the drag")
        if used:
            log.info("achievement: Power %d used by drag", slot)
            return True
        log.info("achievement: Power %d not used by the drag either", slot)
        return False

    def _refuse_shop(self, frame, words, slot):
        if classify_panel(words, frame) == "shop":
            self._decline(words)
            raise _Bail(f"a purchase question after Power slot {slot}", words)

    def _placed_counts(self, slot, badge, before):
        """A Power went from the cursor onto the map: check the count. Live
        2026-11-08 20:06 a "placed" Power left the count at 22. A count that
        cannot be read keeps the old answer (the cursor emptied = used)."""
        frame, words = self._look(f"power{slot}_after_drop")
        self._refuse_shop(frame, words, slot)
        used, _ = self._check_use(frame, words, badge, before, slot, "the drop")
        if used is False:
            raise _Bail(f"Power slot {slot} left the cursor but the count stayed {before}", words)
        if used is None:
            log.info("achievement: Power %d left the cursor; its count could not be compared - "
                     "counting it as used", slot)
        return True

    def _check_use(self, frame, words, badge, before, slot, what):
        """Did the click (`what`) use the Power? -> (used, reopened).

        used: True when the count went down, or the badge is gone while the
        frame is on the Powers tab; False when the count was read before and
        after and did not go down; None when it cannot be told.

        "Badge not found" alone is no use: live 2026-11-09 05:40 the map click
        closed the panel, the frame showed the tower list (OCR "$330 | $310
        ..."), the badge was simply not on screen and two false uses were
        counted - the reopened panel still read 22. So a closed panel is
        opened again (as run() does for the Instas) and read there."""
        reopened = False
        if panel_closed(frame):
            log.info("achievement: the powers panel closed after %s - opening it again to read "
                     "Power %d's count", what, slot)
            if not self._reopen():
                return None, True
            frame, words = self._panel
            reopened = True
        if not self._in_view(frame, words):
            log.info("achievement: after %s the panel is not on the view of Power %d (%s) - its count "
                     "not compared", what, slot, self._view)
            return None, reopened
        now = badge_near(find_badges(frame), badge)
        if now is None:
            if self._view != "powers":
                # the Insta view's place may differ by a scroll: a missing badge proves nothing
                return None, reopened
            log.info("achievement: Power %d used (badge %s -> gone on the Powers tab)", slot, before)
            return True, reopened
        after = self._count(now)
        if before is not None and after is not None:
            if after < before:
                log.info("achievement: Power %d used (badge %s -> %s)", slot, before, after)
                return True, reopened
            log.info("achievement: Power %d not used by %s: %sthe count stayed %s", slot, what,
                     "the panel closed and " if reopened else "", after)
            return False, reopened
        return None, reopened

    # -- the two views of the list ---------------------------------------------------------
    def _jump_to_instas(self):
        """The Insta tab: the list jumps to its Insta part, whose top rows are
        the last (placed) Powers. Sets self._panel."""
        self.inp.click(*INSTA_TAB)
        frame, words = self._look("powers_insta_view")
        if classify_panel(words, frame) == "shop":
            self._decline(words)
            raise _Bail("a shop page on the Insta tab", words)
        self._panel = (frame, words)
        return frame, words

    def _reopen(self):
        """Open the closed panel again on the view in use. True when shown."""
        if not self._open():
            return False
        if self._view == "instas":
            self._jump_to_instas()
        return True

    def _in_view(self, frame, words):
        """The frame shows the view the Power in use was found in."""
        if self._view == "powers":
            return on_powers_tab(frame, words)
        return not panel_closed(frame) and not on_powers_tab(frame, words) and bool(find_badges(frame))

    def _usable_here(self, frame, words):
        if self._view == "powers":
            return usable_powers(frame, words) if on_powers_tab(frame, words) else []
        return usable_powers(frame) if self._in_view(frame, words) else []

    def _find_usable(self, frame, words):
        """Usable Powers: the top view's first, else the Insta view's.
        Returns [(icon, badge)] and leaves self._view on the view used.
        Records what was seen in self.seen (for the "powers_seen" flag)."""
        self._view = "powers"
        owned = power_badges(frame, words)
        usable = usable_powers(frame, words)
        self.seen["owned"] = len(owned)
        self.seen["usable"] = len(usable)
        if owned:
            log.info("achievement: owned Powers in the top view: %d (slots at %s), %d of them usable, "
                     "the rest greyed out", len(owned), ", ".join("%.3f,%.3f" % i for i, _ in owned), len(usable))
            if self.phase == "round" and not usable:
                # expected to un-grey once bloons are out: worth a look at the capture
                log.warning("achievement: the top view's owned Powers are STILL GREYED during a round "
                            "(see the powers_panel capture) - trying the Insta tab's view")
        if usable:
            return usable
        frame, words = self._jump_to_instas()
        self._view = "instas"
        owned_low = power_badges(frame)
        usable = usable_powers(frame)
        self.seen["owned"] += len(owned_low)
        self.seen["usable"] = len(usable)
        log.info("achievement: owned Powers in the Insta tab's view: %d, %d usable (slots at %s)",
                 len(owned_low), len(usable), ", ".join("%.3f,%.3f" % i for i, _ in usable) or "none")
        return usable

    def _use_powers(self, frame, model, words=()):
        if not on_powers_tab(frame, words):
            log.info("achievement: the panel is not on its Powers tab (it shows the Insta list) "
                     "- no Power used")
            return 0
        owned = self._find_usable(frame, words)
        if not owned:
            log.info("achievement: no usable owned Power in either view (none badged, or all greyed out) "
                     "- nothing clicked")
            return 0
        n = 0
        while owned and n < POWERS_PER_GAME and self.budget.allow("power_uses"):
            icon, badge = owned[0]          # the first usable hexagon, read afresh each time
            if not self._use_power(n + 1, icon, badge, model):
                break
            n += 1
            self.budget.add("power_uses")
            self.summary["powers"].append("%.3f,%.3f" % icon)
            if n >= POWERS_PER_GAME:
                break
            # the panel may have closed after a use: open it again, re-read
            frame, words = self._look("powers_panel_again")
            if panel_closed(frame):
                if not self._reopen():
                    break
                frame, words = self._panel
            owned = self._usable_here(frame, words)
        return n

    # -- instas ----------------------------------------------------------------------------
    def _place_insta(self, model, words):
        tab = A.find_allowed(words, INSTA_TABS)
        self.inp.click(*((tab.x, tab.y) if tab is not None else INSTA_TAB))
        frame, words = self._look("insta_panel")
        if classify_panel(words, frame) == "shop":
            self._decline(words)
            raise _Bail("a shop page on the Insta tab", words)
        towers = insta_badges(frame)
        if not towers:
            log.info("achievement: no Insta tower with a count badge")
            return False
        counts = [(self._count(b), icon, b) for icon, b in towers]
        log.info("achievement: Insta towers by badge: %s", [c for c, _, _ in counts])
        count, icon, _ = max(counts, key=lambda c: c[0] or 0)
        self.inp.click(*icon)
        frame, words = self._look("insta_tower")
        if classify_panel(words, frame) == "shop":
            self._decline(words)
            raise _Bail("a shop page after an Insta tower", words)
        pick = pick_tier(tier_words(words), self.want_t5)
        if pick is None:
            log.info("achievement: the Insta tower's list shows no tier labels - not placing anything "
                     "(see the insta_tower capture)")
            return False
        word, tier = pick
        self.inp.click(word.x, word.y)
        self.sleep(0.6)
        if not self.g.is_holding():
            frame, words = self._look("insta_tier_after")
            if classify_panel(words, frame) == "shop":
                self._decline(words)
                raise _Bail("a purchase question after an Insta tier", words)
            log.warning("achievement: Insta %s did not come onto the cursor", word.text)
            return False
        if not self._drop(insta_spots(model, self.avoid), "Insta " + word.text):
            log.warning("achievement: Insta %s could not be placed - putting it back", word.text)
            self.g.cancel_hold()
            return False
        self.budget.add("insta_uses")
        self.summary["instas"].append("-".join(map(str, tier)))
        if 5 in tier:
            self.want_t5 = False
            log.info("achievement: Instant Gratification - a tier-5 Insta (%s) placed", word.text)
        return True

    # -- open --------------------------------------------------------------------------------
    def _open(self):
        """Click the Powers button and read the panel. True when it shows."""
        if not button_lit(self.g.fresh()):
            log.info("achievement: the Powers button is not lit - nothing to do")
            return False
        self.inp.click(*POWERS_BUTTON)
        self._clicked = True
        frame, words = self._look("powers_panel")
        kind = classify_panel(words, frame)
        if kind == "shop":
            self._decline(words)
            raise _Bail("a shop page behind the Powers button", words)
        if kind == "unknown":
            raise _Bail("the panel could not be read", words)
        self._panel = (frame, words)
        return True

    def wants_pre_round(self):
        """Anything to do before round 1: Instas, or Powers when they do not wait for a round."""
        return self.want_instas or (self.want_powers and not self.powers_in_round)

    def wants_in_round(self):
        """Powers wait for a running round and that run has not happened yet."""
        return self.want_powers and self.powers_in_round and not getattr(self, "_round_run", False)

    def run(self, game, menus, model, avoid=(), phase="pre"):
        """Open the panel, use Powers, place Instas, close it. Returns a
        summary dict; never raises (a failure closes the panel and is logged).

        phase "pre": before round 1 - Instas, and Powers only when
        powers_in_round is False. phase "round": during a round - Powers
        only, once per game."""
        self.phase = phase
        if phase == "round":
            self._round_run = True
        self.summary = {"powers": [], "instas": [], "result": None, "phase": phase}
        self.seen = None
        return self._run(game, menus, model, avoid)

    def _powers_now(self):
        return self.want_powers and (self.phase == "round" or not self.powers_in_round)

    def _instas_now(self):
        return self.want_instas and self.phase == "pre"

    def _run(self, game, menus, model, avoid=()):
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
            frame, words = self._panel
            if on_powers_tab(frame, words):
                # written in `finally`: the power shop buys only after a look that found none owned
                self.seen = {"owned": len(power_badges(frame, words)), "usable": len(usable_powers(frame, words))}
            if self._powers_now() and self.budget.allow("power_uses"):
                self._use_powers(frame, model, words)
            if self._powers_now() and self._instas_now():
                frame, words = self._look("powers_panel_before_instas")
                if panel_closed(frame):
                    if not self._open():
                        raise _Bail("the panel did not open again for the Instas", words)
                    frame, words = self._panel
            for _ in range(INSTAS_PER_GAME if self._instas_now() else 0):
                if not self.budget.allow("insta_uses") or not self._place_insta(model, words):
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
            self._count_failure()
            self.summary["result"] = "error"
            return self.summary
        finally:
            if self.seen is not None:
                # owned: gold badged hexagons seen (greyed ones too); usable: of those, not greyed
                self.budget.set_flag("powers_seen", {"at": time.time(), "method": "gold_badge", **self.seen})
            if opened or getattr(self, "_clicked", False):
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
    """An InGameExtras for this game, or None.

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
