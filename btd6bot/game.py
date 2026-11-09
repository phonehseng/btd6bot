"""In-game control: placing, probing, upgrading, targeting, speed, abilities.

Every action is verified from the screen (tower held? cash dropped? panel open?)
rather than assumed, because a missed click silently ruins a run.
"""
import logging
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import journal
from . import towers as T
from .hud import Hud, parse_int, rec_text
from .templates import brightness_ratio, classify
from .vision import crop

log = logging.getLogger("game")

PLAY_BTN = (0.905, 0.835, 1.0, 0.975)
PLAY_SHAPE_MIN = 0.75     # template score for "the Play / fast-forward button is there"
# The Defeat and Victory cards dim everything behind them, the Play button
# included, but the shape match ignores brightness (0.96 on the dimmed
# button). Measured on the stills of four losses on 2026-11-04: the lit
# button is 0.99-1.0 of the template's brightness, under the end card 0.36,
# while the card fades in 0.18. Below this share the HUD counts as covered.
PLAY_LIT_MIN = 0.6


def hud_visible(frame):
    """True when the match HUD's Play button is on screen and not dimmed by
    an overlay (end card, pause menu), i.e. a click would reach the map."""
    best, scores = classify(frame, ["play_idle", "play_run", "play_fast"], PLAY_BTN)
    if scores[best] <= PLAY_SHAPE_MIN:
        return False
    return brightness_ratio(frame, best, PLAY_BTN) >= PLAY_LIT_MIN
TARGETS = ["first", "last", "close", "strong"]
CLOSED_AFTER_MISSES = 3   # blank price reads (separate attempts) before a path its tiers allow counts closed
REREAD_SETTLE_S = 0.4     # wait after moving the cursor off the panel before reading a blank price again


@dataclass
class Placed:
    tid: str                 # strategy id, e.g. "tack1"
    kind: str                # tower id from towers.TOWERS, or "hero"
    x: float
    y: float
    tiers: list = field(default_factory=lambda: [0, 0, 0])
    spent: int = 0
    # Proof that the tower stands on the map. Game.place registers a tower
    # only on proof (cash drop or a successful selection), so this starts
    # True; a failed selection makes it doubtful (False) until the next
    # successful one. Executor.defended() counts only verified towers.
    verified: bool = True
    select_fails: int = 0    # failed selections in a row (0 after a success)

    @property
    def crosspath(self):
        return "-".join(map(str, self.tiers))


class Game:
    def __init__(self, screen, inp, layout, difficulty="easy", hero="quincy"):
        self.s = screen
        self.inp = inp
        self.lay = layout
        self.hud = Hud(layout)
        self.difficulty = difficulty
        self.hero = hero
        self.towers = {}           # tid -> Placed
        self.learned_cost = {}     # (kind, path, tier) -> observed price
        self.locked_seen = None    # (kind, path, tier) last upgrade found XP-locked
        self.fail_reason = None    # why the last place()/upgrade() did nothing
        self.unlocked_now = None   # (kind, path, tier) last upgrade unlocked with XP
        self._retry_at = {}        # (tower id, path) -> (time, reason): upgrade on hold
        self.closed = set()        # (tower id, path) the panel showed closed or maxed
        self._closed_misses = {}   # (tower id, path) -> blank reads of a path its tiers allow
        self.last_price = None     # panel price of the last upgrade tried (None: unread)
        self.refused_spots = []    # (fx, fy) the last place() call found refused
        self.click_refusals = 0    # ... of which the click (not the probe) was refused
        self.last_spot = None      # (fx, fy) where the last place() released its hold
        self._frame = None
        self._frame_t = 0
        # Set by screen_ok() once the match HUD is gone; every click-making
        # action then refuses until the match loop has looked at the screen
        # and cleared it (Match.play).
        self.screen_lost = False
        # Why the purchase or sale being made now is made: {'source': ...,
        # 'reason': ..., ...}, set around each one by Executor.why and
        # written to the game journal with it (None: not known).
        self.why = None
        # Modes that forbid selling (CHIMPS): sell() refuses before any click,
        # whatever asks for it (set by Match from Executor.no_sell).
        self.no_sell = False

    # -- observation --------------------------------------------------------
    def frame(self, max_age=0.05):
        if self._frame is None or time.time() - self._frame_t > max_age:
            self._frame = self.s.grab()
            self._frame_t = time.time()
        return self._frame

    def fresh(self):
        return self.frame(max_age=0)

    def cash(self, f=None):
        return self.hud.cash(f if f is not None else self.fresh())

    def cash_stable(self, tries=3, dx=0.0):
        """Cash read twice in agreement (guards against OCR blips).

        Without agreement the latest readable value is returned (Hud.cash is
        already a median of recent reads): ending on one unreadable frame
        used to return None, and the bot never acts on None - on Tricky
        Tracks and Encrypted (2026-11-02) no tower was bought for a whole
        setup and five games were refused in a row."""
        last = readable = None
        for _ in range(tries):
            c = self.hud.cash(self.fresh(), dx)
            if c is not None and c == last:
                return c
            last = c
            readable = c if c is not None else readable
            time.sleep(0.05)
        return readable

    def lives(self):
        return self.hud.lives(self.fresh())

    def round(self):
        return self.hud.round(self.fresh())

    def button_state(self, f=None):
        return classify(f if f is not None else self.fresh(),
                        ["play_idle", "play_run", "play_fast"], PLAY_BTN)[0]

    def in_game(self, f=None):
        """The match HUD is showing and lit (see hud_visible).

        Quad Reverse (2026-11-04): the old shape-only check passed on the
        Defeat card, so screen_ok() let clicks through and one opened the
        Restart dialog, next to the Monkey-Money Continue button."""
        return hud_visible(f if f is not None else self.fresh())

    # Pause between the two looks at the Play button before the HUD counts
    # as gone (one look can catch a frame mid-redraw).
    SCREEN_RECHECK_S = 0.25

    def screen_ok(self):
        """True while the match HUD (the Play / fast-forward button) is on
        screen, so a click lands on the map and not on something above it.

        Cargo Double HP Monkeys (2026-11-03): the game was lost at round 75
        while the executor was in the middle of a long run of purchases. For
        35 s it kept clicking spots and towers on the DEFEAT screen - whose
        Continue button spends Monkey Money - until a placement click hit
        Home, and stray clicks then opened the Legends page, where the bot
        clicked for 18 minutes. Each placement and selection now looks
        first; once the HUD is gone, nothing more is clicked until the match
        loop has identified the screen (it clears screen_lost)."""
        if self.screen_lost:
            return False
        if self.in_game():
            return True
        time.sleep(self.SCREEN_RECHECK_S)
        if self.in_game():
            return True
        log.warning("the match HUD is gone (end screen or menu?) - no more clicks until the screen is identified")
        self.screen_lost = True
        return False

    # -- speed / rounds -------------------------------------------------------
    def go_fast(self, allow_start):
        """Make sure the game runs at 2x. Starts the round only if allowed."""
        st = self.button_state()
        if st == "play_idle":
            if not allow_start:
                return False
            self.inp.press("space")
            time.sleep(0.25)
            st = self.button_state()
        if st == "play_run":
            self.inp.press("space")
            time.sleep(0.2)
        return True

    # -- banana farms -----------------------------------------------------------
    # A banana farm drops bananas on the ground around it, and they only pay
    # when the cursor moves over them. Path 3 tier 3 (Marketplace) and path 2
    # tier 3 (Monkey Bank) stop the drops (cash goes straight to the player /
    # into the bank), so only farms below both make bananas.
    #
    # Bananas are found by looking: bright yellow blobs near a farm that were
    # not there when the farm was built (its first snapshot), outside the
    # farm's own sprite. The cursor then passes over each one - no clicks.
    BANANA_REACH = 0.10       # farthest drop from the farm, fraction of window width (estimate)
    BANANA_HSV = ((20, 140, 190), (36, 255, 255))   # banana yellow, OpenCV HSV
    BANANA_AREA = (0.00002, 0.0012)   # blob area, fraction of the window area
    MAX_BANANA_MOVES = 12

    @staticmethod
    def drops_bananas(p):
        return p.kind == "farm" and p.tiers[1] < 3 and p.tiers[2] < 3

    def collect_bananas(self):
        """Move the cursor over the bananas lying around this game's farms.
        Returns how many were passed over."""
        farms = [p for p in self.towers.values() if self.drops_bananas(p)]
        if not farms:
            return 0
        f = self.fresh()
        h, w = f.shape[:2]
        reach = int(self.BANANA_REACH * w)
        from .mapgeom import WORLD_PX_PER_UNIT_1920
        from .placement import footprint_radius
        own = int(1.4 * footprint_radius("farm") * WORLD_PX_PER_UNIT_1920 * w / 1920)
        moves = 0
        for p in farms:
            cx, cy = int(p.x * w), int(p.y * h)
            x0, y0, x1, y1 = max(0, cx - reach), max(0, cy - reach), min(w, cx + reach), min(h, cy + reach)
            patch = f[y0:y1, x0:x1]
            bg = getattr(p, "banana_bg", None)
            if bg is None or bg.shape != patch.shape:
                p.banana_bg = patch.copy()      # the ground before any banana fell
                continue
            for bx, by in self._banana_blobs(patch, bg, (cx - x0, cy - y0), reach, own, w * h):
                if moves >= self.MAX_BANANA_MOVES:
                    return moves
                self.inp.move((x0 + bx) / w, (y0 + by) / h, fast=True)
                moves += 1
        return moves

    def _banana_blobs(self, patch, bg, centre, reach, own, window_area):
        """Centres of new yellow blobs in `patch` (vs its snapshot `bg`),
        between the farm's own sprite (radius `own`) and `reach`."""
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, *self.BANANA_HSV)
        changed = cv2.absdiff(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY),
                              cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)) > 30
        mask = (yellow > 0) & changed
        ring = np.zeros(mask.shape, np.uint8)
        cv2.circle(ring, centre, reach, 1, -1)
        cv2.circle(ring, centre, own, 0, -1)
        mask = (mask & (ring > 0)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
        lo, hi = (a * window_area for a in self.BANANA_AREA)
        return [(int(cents[i][0]), int(cents[i][1])) for i in range(1, n)
                if lo <= stats[i, cv2.CC_STAT_AREA] <= hi]

    # -- holding / probing ----------------------------------------------------
    # Share of the cancel-button region that must be red, and share that must
    # be the button's white X, for a tower to count as held. Measured on
    # Cracked (2026-11-06, 1280x800 recording): the held button reads ~0.47
    # red and 0.20-0.48 white (0.14 while fading in); the bare ground there
    # reads 0.38-0.50 red but at most 0.015 white.
    HOLD_RED_MIN = 0.3
    HOLD_WHITE_MIN = 0.1
    # The white must also be shaped like an X: share of the pixels on the two
    # diagonals that are white, and how many times whiter the diagonals are
    # than the rest of the region. Measured on 1280x800 recordings: a held
    # tower's X reads 0.60-0.82 on the diagonals and 0.14-0.19 off them
    # (Cracked, Mesa, also with the cursor over the button); the white text
    # "ENABLED" of Fast Track's banner reads 0.18-0.25 on and ~0.30 off.
    HOLD_X_DIAG_MIN = 0.35
    HOLD_X_RATIO_MIN = 1.8

    def is_holding(self, f=None):
        """True while a tower is on the cursor: the red cancel button with its
        white X is drawn at layout 'cancel_place' (over the map's right edge).

        Red alone is not enough. Cracked's orange-red ground lies under that
        spot and passed the red test with no tower held, so every successful
        placement click read as 'refused': the bot picked the tower up again
        and placed it elsewhere, bought ~30 towers it never recorded (no
        upgrades, no answers) and lost Apopalypse at round 46 (case
        20261106_171204). The white X is what the ground does not have.

        Red and some white are not enough either: with Fast Track on, the
        "FAST TRACK ENABLED" banner is shown over the same spot until the
        first round starts, and the white "ED" of its text lies inside the
        region. On Mesa the ground there is orange-red, so with nothing held
        the test said "holding": every opener the bot placed before round
        one was logged as a refused click and never recorded, ~$5,800 of
        towers stood on the map unknown to the bot, and the match was
        abandoned with "no defence" (Mesa, 2026-11-08/09, 114 refusal runs).
        So the white must lie on the X's diagonals (_x_shaped)."""
        f = f if f is not None else self.fresh()
        x, y = self.lay["cancel_place"]
        reg = (x - 0.012, y - 0.02, x + 0.012, y + 0.02)
        c = crop(f, reg)
        hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, (0, 130, 150), (15, 255, 255)) | cv2.inRange(hsv, (172, 130, 150), (180, 255, 255))
        white = cv2.inRange(hsv, (0, 0, 200), (180, 60, 255)) > 0
        return (np.count_nonzero(red) / red.size > self.HOLD_RED_MIN
                and white.mean() > self.HOLD_WHITE_MIN
                and self._x_shaped(white))

    @classmethod
    def _x_shaped(cls, white):
        """Does this white mask (the cancel-button region) hold an X? The
        X's two strokes run corner to corner through the centre, so the
        pixels near the diagonals must be mostly white and clearly whiter
        than the pixels far from them (text or ground highlights are not
        laid out that way)."""
        h, w = white.shape
        yy, xx = np.mgrid[0:h, 0:w]
        u = np.abs((xx - (w - 1) / 2) / (w / 2))    # 0 at the centre, 1 at the edge
        v = np.abs((yy - (h - 1) / 2) / (h / 2))
        off_diag = np.abs(u - v)
        on = (off_diag < 0.25) & (u < 0.7)           # the strokes, short of the corners
        off = off_diag > 0.55                        # between the strokes
        if not on.any() or not off.any():
            return False
        on_share, off_share = white[on].mean(), white[off].mean()
        return on_share >= cls.HOLD_X_DIAG_MIN and on_share >= cls.HOLD_X_RATIO_MIN * off_share

    def hold(self, kind, tries=3):
        """Pick up a tower (or the hero) with its hotkey. True when it is on
        the cursor. `tries` hotkey presses at most (~1 s each when it fails)."""
        key = T.HERO_HOTKEY if kind == "hero" else T.TOWERS[kind]["hotkey"]
        if not key:
            raise ValueError(f"{kind} has no hotkey bound")
        if self.is_holding():
            self.cancel_hold()
        self._held_kind = kind
        for attempt in range(tries):
            if attempt:
                # an open upgrade panel, a mode's intro box over the match or
                # the cursor over the side panel can swallow the hotkey: clear
                # them and retry
                self.close_panels()
                self.close_intro_box()
                self.inp.move(0.42, 0.5, fast=True)
            self.inp.press(key)
            for _ in range(16):  # the X can fade in late when the game is busy
                time.sleep(0.06)
                if self.is_holding():
                    if kind == "hero" and not getattr(self, "_hero_checked", False):
                        self._detect_hero()
                    return True
            if self._header_shows(kind):
                # held, but the cancel X was not drawn (seen on Logs): trust the header
                self._holding_unseen = True
                return True
        if time.time() - getattr(self, "_holdfail_saved", 0) > 600:  # a capture now and then
            self._holdfail_saved = time.time()
            try:
                from .vision import save
                save(self.fresh(), "logs/holdfail.png")
            except Exception:
                pass
        return False

    # A mode's intro box ("IMPOPPABLE - Impoppable will test your Bloon popping
    # skills to the max ... OK") can come up after the match already reads as
    # in_game, so the runner's check right after loading misses it, and while
    # it is up no hotkey picks a tower up. Cargo Impoppable (2026-11-05): the
    # box stayed 45 s, the ninja's pick-up failed six times behind it, and the
    # build went without its core tower. Its green OK sits in this region
    # (screen fractions), the same one runner._close_mode_intro reads.
    INTRO_OK_REGION = (0.35, 0.6, 0.65, 0.8)

    def close_intro_box(self, f=None):
        """Click the OK of a mode's intro box if one covers the match
        (find_intro_box_ok). True when it was clicked."""
        f = f if f is not None else self.fresh()
        spot = find_intro_box_ok(f)
        if spot is None:
            return False
        log.info("mode intro box over the match: clicking its OK at %.3f,%.3f", *spot)
        self.inp.click(*spot)
        time.sleep(0.6)
        return True

    # Failed pick-ups in a row after which probe_roster() stops: the hotkeys
    # are not working (a popup has focus, or the mode restricts towers).
    PROBE_MAX_FAILS = 3

    def probe_roster(self, kinds=None):
        """Which towers does this save have? Press each hotkey before round 1:
        a tower that can be picked up is unlocked. Towers we cannot afford yet
        are left out (unknown). Returns {tower_id: True/False}.

        kinds: probe only these towers (None: every tower with a hotkey). The
        caller passes the towers it does not know yet: a full probe took ~17 s
        per session, 80 s in Primary Only (every non-primary tower failed
        three hotkey presses) and 150 s when the hotkeys did not work at all.
        For the same reason each tower gets one press (the probe only ever
        ADDS towers, so a missed one costs nothing) and the probe stops after
        PROBE_MAX_FAILS failures in a row."""
        cash = self.cash_stable()
        out = {}
        fails = 0
        self.inp.move(0.42, 0.5, fast=True)   # a cursor over the side panel swallows hotkeys
        for kind, t in T.TOWERS.items():
            if kinds is not None and kind not in kinds:
                continue
            if not t.get("hotkey"):
                continue
            if cash is None or self.price(kind) > cash:
                continue
            held = self.hold(kind, tries=1)
            out[kind] = held
            if held:
                self.cancel_hold()
                fails = 0
                continue
            fails += 1
            if fails >= self.PROBE_MAX_FAILS:
                log.warning("roster probe: %d towers in a row could not be picked up - "
                            "stopping early (hotkeys not working, or those towers are locked)", fails)
                break
        log.info("roster probe: %s", out)
        return out

    def cancel_hold(self):
        """Drop a held tower. The red X is not always drawn, so a right-click
        (which cancels placement and does nothing else on the map) backs it up."""
        if self.is_holding():
            self.inp.click(*self.lay["cancel_place"])
            time.sleep(0.15)
        elif getattr(self, "_holding_unseen", False):
            self.inp.right_click(0.42, 0.5)
            time.sleep(0.15)
        self._holding_unseen = False

    def _detect_hero(self):
        """The equipped hero is whatever the save has selected: read its name
        from the tower panel header while it is held, and adopt it."""
        self._hero_checked = True
        try:
            words = " ".join(w.text for w in self._vision().read((0.855, 0.095, 1.0, 0.175)))
            n = "".join(c for c in words.lower() if c.isalnum())
            for hid, h in T.HEROES.items():
                key = "".join(c for c in h["name"].lower() if c.isalnum())
                first = "".join(c for c in h["name"].split()[0].lower() if c.isalnum())
                if len(n) >= 4 and (key in n or (len(first) >= 4 and first in n)):
                    if hid != self.hero:
                        log.info("equipped hero is %s (assumed %s)", hid, self.hero)
                        self.hero = hid
                        self.detected_hero = hid
                        cb = getattr(self, "on_hero", None)
                        if cb:
                            cb(hid)
                    return
        except Exception:
            pass

    def _vision(self):
        if getattr(self, "_v", None) is None:
            from .vision import Vision
            self._v = Vision(self.s)
        return self._v

    def _header_shows(self, kind):
        """The tower panel header names the tower on the cursor (when the X is missing)."""
        name = T.HEROES.get(self.hero, {}).get("name") if kind == "hero" else T.TOWERS[kind]["name"]
        if not name:
            return False
        words = [w.text for w in self._vision().read((0.855, 0.095, 1.0, 0.175))]
        a = "".join(c for c in " ".join(words).lower() if c.isalnum())
        parts = ["".join(c for c in w.lower() if c.isalnum()) for w in name.split()]
        key = max(parts, key=len)  # 'boomerang' of 'Boomerang Monkey' (names wrap)
        return len(key) >= 4 and key in a

    PX_PER_UNIT = 5.3 / 1920  # range circle radius per game unit, as a width fraction
                              # (measured: held dart, range 32 -> ~170 px at 1920 wide)

    def probe(self, fx, fy, baseline=None, settle=0.06):
        """With a tower held, is (fx, fy) a legal spot? Red range circle = no.

        Only a ring of the range circle (45-85% of its radius) is sampled: the
        tower sprite in the middle can itself be red (Tack Shooter is pink).
        """
        self.inp.move(fx, fy, fast=True)
        time.sleep(settle)
        f = self.fresh()
        h, w = f.shape[:2]
        rng = self._held_range()
        R = max(45, rng * self.PX_PER_UNIT * w)
        cx, cy = int(fx * w), int(fy * h)
        x0, x1 = max(0, int(cx - R)), min(w, int(cx + R))
        y0, y1 = max(0, int(cy - R)), min(h, int(cy + R))
        yy, xx = np.ogrid[y0:y1, x0:x1]
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (d2 >= (0.45 * R) ** 2) & (d2 <= (0.85 * R) ** 2)
        if not ring.any():
            return True
        red_now = _red_mask(f[y0:y1, x0:x1])[ring].mean()
        red_base = _red_mask(baseline[y0:y1, x0:x1])[ring].mean() if baseline is not None else 0.0
        return bool(red_now - red_base < 0.2)

    def _held_range(self):
        kind = getattr(self, "_held_kind", None)
        if kind == "hero":
            return T.HEROES.get(self.hero, {}).get("range") or 40
        if kind in T.TOWERS:
            return T.TOWERS[kind].get("range") or 12  # unlimited-range towers show a small circle
        return 32

    # -- prices -----------------------------------------------------------------
    # An observed price (cash before minus cash after a purchase) is only
    # believed within this band around the price table (towers.py, at this
    # game's difficulty). The low end leaves room for discounts the tables
    # do not model (Monkey Knowledge, a nearby village); anything outside is
    # a misread or pop income landing between the two cash reads.
    PRICE_BAND = (0.7, 1.3)

    def table_price(self, kind, path=0, tier=0):
        """Price-table cost at this difficulty: the tower itself (path 0),
        or tier `tier` of upgrade path `path` (1..3)."""
        if kind == "hero":
            return T.hero_cost(self.hero, self.difficulty)
        if path:
            return T.upgrade_cost(kind, path, tier, self.difficulty)
        return T.tower_cost(kind, self.difficulty)

    def learn_price(self, kind, path, tier, seen):
        """Remember a price seen in this game. Returns True when it was kept.

        Pop income between the two cash reads can only make a drop look
        SMALLER than the price, so the highest plausible observation is the
        best estimate and is the one kept. (Ancient Portal: one income-
        shrunk drop taught a $400 ninja a $290 price; the bot then 'bought'
        ninjas it could not afford and recorded them as placed.)"""
        table = self.table_price(kind, path, tier)
        lo, hi = self.PRICE_BAND
        if not lo * table <= seen <= hi * table:
            log.info("ignoring observed price $%s for %s %d-%d (price table $%d)",
                     seen, kind, path, tier, table)
            return False
        key = (kind, path, tier)
        self.learned_cost[key] = max(seen, self.learned_cost.get(key, 0))
        return True

    def price(self, kind):
        """What placing `kind` costs now: the learned price when there is one,
        held inside PRICE_BAND of the table, else the table price."""
        table = self.table_price(kind)
        seen = self.learned_cost.get((kind, 0, 0)) if kind != "hero" else None
        if not seen:
            return table
        lo, hi = self.PRICE_BAND
        return int(min(max(seen, lo * table), hi * table))

    # -- placing ----------------------------------------------------------------
    def place(self, tid, kind, fx, fy, check_valid=True, more_spots=()):
        """Place a tower at (fx, fy); returns the Placed tower or None.

        more_spots: further (fx, fy) candidates, best first. When the probe
        refuses a spot, the tower stays on the cursor and the next spot is
        probed (~0.1 s, against ~1.4 s to cancel and pick it up again). When
        the CLICK is refused, the tower is picked up again before the next
        spot (its preview may have stuck). Every refused spot is listed in
        self.refused_spots so the caller can learn them.

        A tower is registered only on proof that it stands on the map (see
        _confirm). fail_reason: "cash", "hold", "spot" (every spot refused)
        or "unverified" (the hold was released, but neither the cash nor the
        map shows a new tower)."""
        self.fail_reason = None
        self.refused_spots = []
        self.click_refusals = 0     # spots the probe passed but the click did not take
        self.last_spot = None
        if not self.screen_ok():
            self.fail_reason = "screen"
            return None
        before = self.cash_stable()
        cost = self.price(kind)
        if before is None or before < cost:
            self.fail_reason = "cash"
            return None
        self.cancel_hold()
        baseline = self.fresh()  # the spots without a held tower, to compare against
        if not self.hold(kind):
            log.info("could not pick up %s (locked or unaffordable)", kind)
            self.fail_reason = "hold"
            return None
        for sx, sy in [(fx, fy), *more_spots]:
            if check_valid and not self.probe(sx, sy, baseline):
                log.info("spot %.3f,%.3f invalid for %s", sx, sy, kind)
                self.refused_spots.append((sx, sy))
                continue
            pre = self.cash_stable()        # the cash read closest to the click
            self.inp.click(sx, sy)
            time.sleep(0.25)
            if self.is_holding():
                # the game keeps the tower on the cursor after a click on a
                # spot it refuses (the probe missed it): try the next spot
                log.info("spot %.3f,%.3f refused the click for %s", sx, sy, kind)
                self.refused_spots.append((sx, sy))
                self.click_refusals += 1
                # After a refused click the held tower's preview can stop
                # following the cursor: it stays on the refused spot, every
                # later probe sees no red where the cursor is, and every
                # later click lands on that one bad spot (Encrypted
                # Impoppable 2026-11-04: the ace preview sat on its first
                # spot for 20 clicks over two rounds, so no blimp damage was
                # bought before the round-40 MOAB). Picking the tower up
                # again makes the preview follow once more (~1.4 s).
                if not self.hold(kind):
                    self.fail_reason = "hold"
                    return None
                continue
            self.last_spot = (sx, sy)
            return self._confirm(tid, kind, sx, sy, pre if pre is not None else before)
        self.cancel_hold()
        self.fail_reason = "spot"
        self._journal_place_failed(tid, kind)
        return None

    def _journal_place_failed(self, tid, kind):
        """Note in the game journal that the game took no tower at any spot
        tried (journal.cause_of_death counts these as placement trouble)."""
        journal.current().event("place_failed", tid=tid, kind=kind, reason=self.fail_reason,
                                refused=len(self.refused_spots), why=getattr(self, "why", None))

    def _confirm(self, tid, kind, fx, fy, before):
        """The hold was released at (fx, fy). Register the tower only on proof:
        the cash dropped by about its price, or the tower can be selected there.

        Root cause of phantom towers: a released hold used to count as a
        purchase even when the cash went UP (Ancient Portal, "cash 374 -> 407"
        for a $400 ninja). Each phantom then failed 8 selections of ~3 s, and
        a phantom as the only tower would let a round start undefended.

        A selection proves the tower only when the panel that opened can be
        a NEW tower's (_not_a_new_tower): the click may open a neighbour's."""
        p = Placed(tid, kind, fx, fy, spent=self.price(kind), verified=True)
        drop = self._cash_drop(before, kind)
        if drop is None:
            # a tower whose cancel X is never drawn (seen on Logs) may still be
            # on the cursor: drop it, or the selection click below would try
            # to place it instead of selecting
            self.cancel_hold()
        self._holding_unseen = False
        if drop is not None:
            p.spent = drop
            if kind != "hero":
                self.learn_price(kind, 0, 0, drop)
        else:
            found = self.select(p)
            foreign = self._not_a_new_tower(p) if found else None
            if found:
                self.deselect(p)
            if found and not foreign:
                log.info("placement of %s confirmed by selecting it (cash %s -> %s)",
                         kind, before, self._seen_cash)
            else:
                why = (f"the click there opened {foreign}" if foreign
                       else "nothing to select there")
                log.warning("placement of %s at %.3f,%.3f NOT confirmed (cash %s -> %s, %s) - "
                            "not recorded", kind, fx, fy, before, self._seen_cash, why)
                self.fail_reason = "unverified"
                self.unconfirmed_streak = getattr(self, "unconfirmed_streak", 0) + 1
                self._journal_place_failed(tid, kind)
                return None
        self.unconfirmed_streak = 0
        self.towers[tid] = p
        log.info("placed %s (%s) at %.3f,%.3f for $%s", tid, kind, fx, fy, p.spent)
        journal.current().event("place", tid=tid, kind=kind, x=round(fx, 4), y=round(fy, 4),
                                cost=p.spent, why=getattr(self, "why", None))
        return p

    # Seconds the cash is watched for a purchase's drop after the click.
    CASH_PROOF_S = 1.0

    def _cash_drop(self, before, kind):
        """Proof by cash: some read within CASH_PROOF_S seconds lies about one
        price below `before` (PRICE_BAND of the price table; the HUD needs a
        few frames to show the new total). Returns that drop, else None."""
        table = self.table_price(kind)
        lo, hi = self.PRICE_BAND
        self._seen_cash = None
        end = time.time() + self.CASH_PROOF_S
        while True:
            now = self.cash()
            if now is not None:
                self._seen_cash = now
                if lo * table <= before - now <= hi * table:
                    return before - now
            if time.time() >= end:
                return None
            time.sleep(0.08)

    # -- selection / upgrade panel ---------------------------------------------
    def panel(self, p):
        """Which side the upgrade panel opens on for tower p (learned on first
        selection; predicted from the tower's side of the map until then)."""
        side = getattr(p, "panel_side", None)
        if side:
            return self.lay[side]
        mid = self.lay["playfield"][2] / 2
        return self.lay["upg_right"] if p.x < mid else self.lay["upg_left"]

    def _open_side(self, f=None):
        f = f if f is not None else self.fresh()
        for side in ("upg_right", "upg_left"):
            text, _ = rec_text(crop(f, _expand(self.lay[side]["sell"], 0.04, 0.025)))
            if "sell" in text.lower():
                return side
        return None

    def panel_open(self, p, f=None):
        f = f if f is not None else self.fresh()
        text, _ = rec_text(crop(f, _expand(self.panel(p)["sell"], 0.04, 0.025)))
        return "sell" in text.lower()

    def select(self, p):
        """Click tower p and wait for its upgrade panel. True when it opened.

        Keeps score on p: a success proves the tower is there (verified, and
        the failure streak resets); a failure makes it doubtful. Callers drop
        a tower that fails twice in a row (Executor._forget_if_missing).
        Off the match screen nothing is clicked and no score is kept."""
        if not self.screen_ok():
            return False
        if self.is_holding():
            self.cancel_hold()
        for attempt in range(3):
            self.inp.click(p.x, p.y)
            for _ in range(3):  # the panel slides in over ~0.3 s
                time.sleep(0.15)
                side = self._open_side()
                if side:
                    p.panel_side = side
                    p.verified, p.select_fails = True, 0
                    self._read_pops(p)
                    return True
            # nudge: the click may have hit the edge of the sprite
            p_dx = (0.004, -0.004, 0.0)[attempt]
            p.x += p_dx
        p.verified = False
        p.select_fails = getattr(p, "select_fails", 0) + 1
        return False

    def _read_pops(self, p):
        """Pop counter shown under the tower's name (used to learn good spots).

        A count of 0 is believed only from a panel that is p's own - its
        prices fit p's kind and tiers (_panel_fits, or one purchase the bot
        did not see). A click can open a neighbour's panel, and a village's
        or a hero's shows 0 pops or none. Spring Spring CHIMPS (2026-11-07
        17:12): r1, a M.O.A.R. Glaives boomerang (4-0-2, $4,100) beside the
        village, read 0 pops three times over nine rounds while the
        boomerangs earned 161,756 XP that game; Executor._dead called it a
        tower that pops nothing, its Glaive Lord step went to a fresh 0-0-0
        boomerang, and round 95 was lost without the Glaive Lord. An
        unproven 0 now leaves the count unknown (None) instead."""
        try:
            f = self.fresh()
            img = crop(f, self.panel(p)["pops"])
            if not getattr(Game, "_pops_crop_saved", False):
                Game._pops_crop_saved = True  # one crop per session, for calibration
                from .vision import save
                save(img, "logs/pops_crop.png")
            text = rec_text(img)[0]
            v = parse_int(text)
            if v is None:
                return
            if v == 0 and p.kind != "hero":
                # every zero read leaves its crop behind, for checking the reader
                try:
                    from .vision import save
                    save(img, f"logs/pops_zero_{p.tid}.png")
                    log.info("%s (%s %s): pop counter read %r as 0", p.tid, p.kind, p.crosspath, text)
                except Exception:
                    pass
                costs = self.path_costs(p, f)
                kind_prices = all(self._tier_for_price(p.kind, i + 1, v) is not None
                                  for i, (k, v) in enumerate(costs) if k == "cash" and v)
                priced = any(k == "cash" and v for k, v in costs)
                own = priced and kind_prices and (self._panel_fits(p.kind, p.tiers, costs)
                                                  or self._one_missed_tier(p, costs))
                if not own:
                    log.info("%s: a pop count of 0 from a panel that is not provably its own "
                             "(prices %s) - not counted", p.tid, costs)
                    p.pops = None
                    return
            if v >= (getattr(p, "pops", 0) or 0):
                p.pops = v
        except Exception:
            pass

    def deselect(self, p):
        if self.panel_open(p):
            self.inp.click(*self.panel(p)["close"])
            time.sleep(0.15)

    def close_panels(self):
        """Close any upgrade panel left open (it also shifts the HUD)."""
        f = self.fresh()
        for side in ("upg_left", "upg_right"):
            pan = self.lay[side]
            text, _ = rec_text(crop(f, _expand(pan["sell"], 0.04, 0.025)))
            if "sell" in text.lower():
                self.inp.click(*pan["close"])
                time.sleep(0.2)
                return True
        return False

    def path_costs(self, p, f=None):
        """Per path: ("cash", n) | ("xp", n) for a locked tier | (None, None)
        when the button shows no price (path closed or maxed, or unreadable)."""
        f = f if f is not None else self.fresh()
        return [price_row(rec_text(crop(f, reg))[0]) for reg in self.panel(p)["cost_rows"]]

    def _path_closed(self, p, path, costs):
        """Does the panel show no price at all on this path? Then it is closed
        (two other paths in use, or another path past tier 2) or maxed, and
        stays so for the rest of the game: remember it and never click it.
        Seen: Spike Factory sp1 clicked three times on a closed path 3.

        A second read must agree (one OCR miss looks the same), and some other
        path must show something (a panel still sliding in shows nothing).

        When the tower's own tiers say the path is open (crosspath allows it,
        not maxed), a blank price is likelier a misread: the Super Monkey s1,
        just placed at 0-0-0, had its top path closed for a whole game
        (2026-10-22, Bazaar Hard). Then the path closes only after
        CLOSED_AFTER_MISSES blank reads in separate attempts; until then the
        attempt just fails ("unread") and is tried again later."""
        if costs[path - 1] != (None, None) or all(c == (None, None) for c in costs):
            return False
        if self._reread_clear(p)[path - 1] != (None, None):
            return False
        if _path_open_by_tiers(p.tiers, path):
            misses = self._closed_misses
            misses[(p.tid, path)] = misses.get((p.tid, path), 0) + 1
            if misses[(p.tid, path)] < CLOSED_AFTER_MISSES:
                if not getattr(self, "_misread_saved", False):
                    self._misread_saved = True       # one picture per game, to see what it was
                    try:
                        from .vision import save
                        save(crop(self.fresh(), self.panel(p)["box"]), "logs/closed_misread.png")
                    except Exception:
                        pass
                log.info("%s path %d shows no price although its tiers %s allow it - "
                         "trying again later (panel %s)", p.tid, path, p.crosspath, costs)
                self.fail_reason = "unread"
                return True
            # closed for good: the count was behind, on another path or this one
            if not self._closed_path_hides_a_tier(p, path, costs):
                self._closed_path_took_its_last_tier(p, path, costs)
        self.closed.add((p.tid, path))
        log.info("%s path %d is closed or maxed (panel %s) - not buying it this game",
                 p.tid, path, costs)
        self.fail_reason = "capped"
        return True

    def _closed_path_hides_a_tier(self, p, path, costs=None):
        """A path the panel shows closed while p.tiers say it is open means
        the count is behind on another path: the game closes a path only
        when the two other paths both hold tiers (or this one stands at 2
        with another past 2, which the count would show). So when exactly
        one other path is counted at 0, that path really holds a tier the
        bot never saw. Corrects p.tiers to the least that explains the
        panel (that path at 1) and returns True.

        High Finance Magic Monkeys Only (2026-11-05): wizard2's Intense
        Magic click was judged "not bought" - the next tier, Monkey Sense,
        costs the same $325, so the button could not prove it, and round
        income hid the cash drop - and the bot kept the tower at 0-2-0
        while the panel showed its path 1 as PATH CLOSED. _resync_tiers
        cannot tell from the $325 whether path 3 stands at 0 or 1; the
        closed path can.

        The path said to hold a tier must then be open, so its button must
        show something (`costs`, the panel read): when it is blank too, the
        panel is not explained by the corrected tiers and nothing changes.
        Alpine Run CHIMPS (2026-11-07 08:49): r3, counted 0-0-2, read
        [blank, blank, $1,405]; path 2 "closed" made it 1-0-2 although path 1
        was just as blank, and a plan step was set aside for it."""
        others = [i for i in range(3) if i != path - 1]
        zero = [i for i in others if p.tiers[i] == 0]
        if p.tiers[path - 1] != 0 or len(zero) != 1:
            return False
        if costs is not None and costs[zero[0]] == (None, None):
            return False
        new = list(p.tiers)
        new[zero[0]] = 1
        if not _legal_cross(new):
            return False
        log.warning("%s path %d is closed although it is counted at %s: path %d must hold a tier - "
                    "corrected to %s", p.tid, path, p.crosspath, zero[0] + 1, "-".join(map(str, new)))
        p.tiers[:] = new
        return True

    def _closed_path_took_its_last_tier(self, p, path, costs):
        """A path its tiers call open that stays blank (CLOSED_AFTER_MISSES
        reads) is explained by ONE more tier on that same path when that
        tier is the last the crosspath allows there (the button then reads
        MAX UPGRADES): the click that bought it was judged "not bought".
        Corrects p.tiers to that tier and returns True.

        Lost Crevasse CHIMPS (2026-11-07 18:19): x1, counted 1-0-4, read
        $215 on path 1 (Razor Sharp Shots), was clicked with $364 and judged
        "not bought" - the button went blank (2-0-4 closes path 1) and pop
        income mid-round hid the cash drop. Three blank reads then closed
        the path with the count still at 1-0-4 (logs/closed_misread.png shows
        Razor Sharp Shots owned and MAX UPGRADES), so the plan's 2-0-4 step
        was set aside as blocked although it stood.

        The other paths' buttons must fit the corrected tiers (blank where
        they are closed, a price where they are open), or nothing changes."""
        new = list(p.tiers)
        new[path - 1] += 1
        if not _legal_cross(new) or _path_open_by_tiers(new, path):
            return False
        for i in range(3):
            if i != path - 1 and (costs[i] != (None, None)) != _path_open_by_tiers(new, i + 1):
                return False
        log.warning("%s path %d stays blank although it is counted at %s: the tier to %s, the last "
                    "this crosspath allows there, was bought unseen - corrected", p.tid, path,
                    p.crosspath, "-".join(map(str, new)))
        p.tiers[:] = new
        return True

    def _reread_clear(self, p):
        """Read the panel's prices again with nothing in the way.

        A blank price right after a click is usually not a closed path: the
        cursor still rests on the button just clicked, so its hover tooltip
        or press animation covers the price. Peninsula Medium (2026-10-27)
        read path 1 of three towers as blank three times this way and lost
        that path for the game, although the saved picture reads $2,200 fine.
        So the cursor moves onto the map beside the panel (a hover there does
        nothing) and the button gets REREAD_SETTLE_S to settle first."""
        box = self.panel(p)["box"]
        x = box[0] - 0.05 if box[0] > 0.5 else box[2] + 0.05   # just off the panel's inner edge
        self.inp.move(x, 0.5, fast=True)
        time.sleep(REREAD_SETTLE_S)
        return self.path_costs(p)

    def _tier_for_price(self, kind, path, price):
        """The tier of `path` whose price-table cost (this difficulty) is
        `price`, give or take the game's $5 rounding; None unless exactly one
        tier matches.

        A tower near a Monkey Village shows its prices discounted (up to
        gamemodel.deepest_discount(), 17%), so when no tier matches exactly,
        a price between the discounted and the full cost of exactly one tier
        names that tier. Without this, Skates ABR (2026-11-03) read the
        opener dart's $15,390 (tier 5's $16,200 less 5%) as no tier at all:
        the bought tier was judged by cash, which the round's income hid,
        the hotkey bought a second tier, and the bot believed the dart was
        2-0-0 while it was 4-2-0."""
        from . import gamemodel
        costs = {t: T.upgrade_cost(kind, path, t, self.difficulty) for t in range(1, 6)}
        exact = [t for t, c in costs.items() if abs(c - price) <= 5]
        if exact:
            return exact[0] if len(exact) == 1 else None
        floor = 1.0 - gamemodel.deepest_discount()
        near = [t for t, c in costs.items() if floor * c - 5 <= price <= c + 5]
        return near[0] if len(near) == 1 else None

    def _resync_tiers(self, p, costs):
        """Correct p.tiers from the panel. Each button shows the price of its
        path's NEXT tier, so a price that names exactly one tier tells how far
        that path really is. A purchase whose cash check failed leaves the
        bot's count behind: Spike Factory sp1 really was 3-0-2 while the bot
        believed 2-0-2, and path 1 showed $10,260 (tier 4's price on Hard).
        Returns True when the tiers were corrected."""
        new = list(p.tiers)
        for i, (kind_, price) in enumerate(costs):
            if kind_ == "cash" and price:
                nxt = self._tier_for_price(p.kind, i + 1, price)
                if nxt is not None:
                    new[i] = nxt - 1
        if new == list(p.tiers) or not _legal_cross(new):
            return False
        log.warning("%s is really %s, not %s (panel prices %s) - corrected",
                    p.tid, "-".join(map(str, new)), p.crosspath, costs)
        p.tiers[:] = new
        return True

    # -- whose panel is it? ----------------------------------------------------
    # A click on a tower opens the upgrade panel of whatever tower the game
    # finds under the cursor, and a neighbour's footprint can reach over the
    # spot. Alpine Run CHIMPS (2026-11-07 08:42-09:00): r2 at 0.473,0.760
    # was never bought (r3's $340 came out of the same $456), but the click
    # meant to confirm it opened r1's panel (r1 at 0.505,0.700, 0.08 away;
    # logs/closed_misread.png shows r1's 3-0-2 Boomerang with its 671 pops),
    # so r2 was recorded. Every later read of "r2" was r1's panel: r2 was
    # "corrected" 0-0-0 -> 3-0-0 ($2,160 = r1's M.O.A.R. Glaives) -> 4-0-0
    # ($35,100 = r1's Glaive Lord), its paths were closed one by one, and the
    # damage model counted a 4-1-0 boomerang that did not exist. Had a plan
    # step asked for r2's path 1, the click would have bought r1's Glaive
    # Lord under r2's name. Likewise boomerang1 at 0.350,0.794 (08:58) was
    # "confirmed" by a panel with no price on any path - Quincy's, 0.06 above.
    NEIGHBOUR_RADIUS = 0.12   # screen heights: how far a misdirected click can reach
    SCREEN_ASPECT = 1.6       # width / height of the capture (1920x1200), for distances

    def _screen_dist(self, a, b):
        """Distance between two towers in screen heights."""
        return float(np.hypot((a.x - b.x) * self.SCREEN_ASPECT, a.y - b.y))

    def _panel_fits(self, kind, tiers, costs):
        """Could this panel (path_costs) be the panel of a `kind` tower at
        `tiers`? Every price must name exactly the next tier of its path,
        every blank path must be one the tiers close or max, and at least
        one price must be readable (an all-blank panel fits anything)."""
        priced = 0
        for i, (k, v) in enumerate(costs):
            if k == "cash" and v:
                if self._tier_for_price(kind, i + 1, v) != tiers[i] + 1:
                    return False
                priced += 1
            elif k is None and _path_open_by_tiers(tiers, i + 1):
                return False
        return priced > 0

    def _panel_owner(self, p, costs):
        """Another known tower whose tiers explain this panel, when p's own
        count does not: the click on p opened that neighbour's panel. Only
        towers within NEIGHBOUR_RADIUS of p count - a click cannot reach
        farther, and a same-kind tower across the map with the tiers a
        drifted count really has must not block the correction. None when
        the panel may be p's own (then _resync_tiers may correct p).

        p's own history wins a tie: a panel that one missed purchase on p
        explains (the usual drift, see _resync_tiers) stays p's even when a
        neighbour fits it too. r2's first read asked for r1's tier 4 while
        r2 was counted 0-0-0 - three tiers nobody bought."""
        if p.kind == "hero" or self._panel_fits(p.kind, p.tiers, costs):
            return None
        if self._one_missed_tier(p, costs):
            return None
        for q in self.towers.values():
            if q is p or q.tid == p.tid or q.kind == "hero":
                continue
            if self._screen_dist(p, q) <= self.NEIGHBOUR_RADIUS and self._panel_fits(q.kind, q.tiers, costs):
                return q
        return None

    def _one_missed_tier(self, p, costs):
        """Do the panel's prices put p at most one tier past its count, and
        no path below it? (A purchase the bot did not see; tiers are never
        lost, so a path below the count cannot be p's.)"""
        implied = list(p.tiers)
        for i, (k, v) in enumerate(costs):
            if k == "cash" and v:
                t = self._tier_for_price(p.kind, i + 1, v)
                if t is not None:
                    implied[i] = t - 1
        if any(a < b for a, b in zip(implied, p.tiers)):
            return False
        return sum(implied) - sum(p.tiers) <= 1

    def _not_a_new_tower(self, p):
        """p was just placed (0-0-0) and its spot selects; is the panel that
        opened someone else's? Returns what it is instead (for the log), or
        None when it may be p's own.

        A new tower's panel shows tier 1 on every path. Signs of another
        tower: a known neighbour's tiers explain it (_panel_owner); a price
        names a tier past 1 (an upgraded tower); or no path shows a price
        even when read again (a hero's panel has no paths) and the panel's
        name does not name p's kind either. Alpine Run CHIMPS 2026-11-07:
        r2 was "confirmed" by r1's 3-0-2 panel, boomerang1 by Quincy's."""
        if p.kind == "hero":
            return None
        costs = self.path_costs(p)
        owner = self._panel_owner(p, costs)
        if owner is not None:
            return f"{owner.tid}'s panel ({owner.kind} {owner.crosspath}; prices {costs})"
        for i, (k, v) in enumerate(costs):
            tier = self._tier_for_price(p.kind, i + 1, v) if k == "cash" and v else None
            if tier is not None and tier > 1:
                return f"an upgraded tower's panel (path {i + 1} asks for tier {tier}; prices {costs})"
        if all(c == (None, None) for c in costs):
            costs = self._reread_clear(p)
            if all(c == (None, None) for c in costs) and not self._panel_names(p):
                return f"a panel with no price on any path that does not name a {p.kind} (a hero's?)"
        return None

    def _panel_names(self, p):
        """Does the open panel's title name p's kind ("Boomerang Monkey")?
        Only asked when no price can be read, so an unreadable title just
        leaves the placement unproven."""
        try:
            text, _ = rec_text(crop(self.fresh(), self.panel(p)["name"]))
        except Exception:
            return False
        words = [w.lower() for w in T.TOWERS.get(p.kind, {}).get("name", p.kind).split()
                 if w.lower() != "monkey"]
        return bool(words) and all(w in text.lower() for w in words)

    def _wrong_panel(self, p, owner, costs):
        """The click on p opened `owner`'s panel. p's tiers are NOT touched
        and nothing is clicked; it counts as a failed selection, so two in a
        row make Executor._forget_if_missing drop p (and queue its place
        step again) instead of the bot rewriting p's tiers from a panel that
        is not p's. select() resets select_fails on every panel it opens, so
        the streak of wrong panels is kept apart in p.wrong_panels."""
        p.wrong_panels = getattr(p, "wrong_panels", 0) + 1
        p.verified = False
        p.select_fails = p.wrong_panels
        self.fail_reason = "select"
        log.warning("%s at %.3f,%.3f cannot be selected: the click opens %s's panel (%s %s, panel "
                    "prices %s) - %s stays %s, nothing clicked (%d in a row)", p.tid, p.x, p.y,
                    owner.tid, owner.kind, owner.crosspath, costs, p.tid, p.crosspath, p.wrong_panels)
        journal.current().event("wrong_panel", tid=p.tid, kind=p.kind, owner=owner.tid,
                                tiers=p.crosspath, owner_tiers=owner.crosspath)

    # upgrade tree (opened by clicking a locked upgrade, or the UPGRADES button)
    TREE_ICON_X = (0.306, 0.424, 0.541, 0.659, 0.777)
    TREE_ICON_Y = (0.33, 0.53, 0.73)
    TREE_UNLOCK = (0.143, 0.683)
    TREE_BACK = (0.045, 0.05)

    def unlock_in_tree(self, path, tier):
        """On the upgrade tree screen: unlock (path, tier) with tower XP if affordable."""
        self.inp.click(self.TREE_ICON_X[tier - 1], self.TREE_ICON_Y[path - 1] - 0.03)
        have = need = None
        for _ in range(3):
            time.sleep(0.8)
            f = self.fresh()
            have = parse_int(rec_text(crop(f, (0.52, 0.01, 0.70, 0.065)))[0].lower().replace("xp", ""))
            need_txt = rec_text(crop(f, (0.04, 0.685, 0.25, 0.72)))[0].lower()
            need = parse_int(need_txt.replace("xp", "")) if "xp" in need_txt else None
            if have is not None and need is not None:
                break
        log.info("tree: path %d tier %d needs %s XP, have %s", path, tier, need, have)
        if need is not None and have is not None and have >= need:
            self.inp.click(*self.TREE_UNLOCK)
            time.sleep(0.9)
            return True
        return False

    def leave_tree(self):
        self.inp.click(*self.TREE_BACK)
        time.sleep(1.2)

    # An upgrade that failed for a reason more cash will not fix is put on
    # hold: still locked behind tower XP (XP grows only slowly during a game),
    # or the click had no effect although the cash was there (path closed,
    # misread panel). The strategy asks again every few seconds and each try
    # costs clicks and screen reads; one Easy game logged 23 identical tries
    # at an XP-locked tier. The hold doubles with every failure, up to
    # RETRY_MAX seconds, and ends when the upgrade goes through.
    RETRY_AFTER = {"xp": 90.0, "noeffect": 30.0}
    RETRY_MAX = 600.0

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        """Buy the next tier on path (1..3). Returns True if it went through.

        A tier still locked behind tower XP is unlocked on the spot (when the
        tower has enough XP) through the upgrade tree, then bought.

        fail_reason when it did not: "select", "xp", "cash" (the panel price,
        self.last_price, is above the cash: nothing clicked), "capped" (the
        path is closed or maxed: never clicked again this game), "drift" (the
        panel showed the bot's tier count was wrong; corrected, nothing
        clicked, so the caller can pick the next tier again) or "noeffect".
        """
        self.fail_reason = None
        self.locked_seen = None
        self.last_price = None
        key = (p.tid, path)
        if key in self.closed:
            self.fail_reason = "capped"         # seen closed earlier: no clicks
            return False
        held = self._retry_at.get(key)
        if held and time.time() < held[0]:
            self.fail_reason = held[1]          # on hold: same answer, no clicks
            return False
        try:
            ok = self._upgrade(p, path, allow_xp_unlock)
        finally:
            if self.fail_reason in self.RETRY_AFTER:
                tries = (held[2] + 1) if held else 1
                wait = min(self.RETRY_MAX, self.RETRY_AFTER[self.fail_reason] * 2 ** (tries - 1))
                self._retry_at[key] = (time.time() + wait, self.fail_reason, tries)
            elif self.fail_reason is None:
                self._retry_at.pop(key, None)
        return ok

    def _upgrade(self, p, path, allow_xp_unlock):
        if not self.select(p):
            log.warning("could not select %s", p.tid)
            self.fail_reason = "select"
            # A tower that will not select is the same sign as a placement
            # that leaves no tower: the click landed on something over the
            # map. The Defeat screen leaves the fast-forward button in view,
            # so screen_ok() is fooled by it - Spillway and Quad (2026-11-04)
            # clicked every tower on it for up to 1 m 47 s, once opening the
            # Restart dialog, next to Continue (Monkey Money). Counting it
            # lets the match loop look at the screen after two such clicks.
            self.unconfirmed_streak = getattr(self, "unconfirmed_streak", 0) + 1
            return False
        try:
            costs = self.path_costs(p)
            if p.kind != "hero":         # hero panels have no upgrade paths
                owner = self._panel_owner(p, costs)
                if owner is not None:    # a neighbour's panel: never "correct" p from it
                    self._wrong_panel(p, owner, costs)
                    return False
                p.wrong_panels = 0
                drifted = self._resync_tiers(p, costs)
                if self._path_closed(p, path, costs):
                    return False
                if drifted:
                    self.fail_reason = "drift"
                    return False
            kind_, cost = costs[path - 1]
            if kind_ == "xp":
                self.locked_seen = (p.kind, path, p.tiers[path - 1] + 1)
                if not allow_xp_unlock or p.kind == "hero":
                    self.fail_reason = "xp"
                    return False
                self.inp.click(*self.panel(p)["paths"][path - 1])
                time.sleep(1.2)
                ok = self.unlock_in_tree(path, p.tiers[path - 1] + 1)
                self.leave_tree()
                if not ok:
                    self.fail_reason = "xp"
                    return False
                self.locked_seen = None
                self.unlocked_now = (p.kind, path, p.tiers[path - 1] + 1)
                if not self.panel_open(p) and not self.select(p):
                    return False
                kind_, cost = self.path_costs(p)[path - 1]
            shown = (kind_, cost)        # the price on the button before the click
            if cost is None:
                cost = T.upgrade_cost(p.kind, path, p.tiers[path - 1] + 1, self.difficulty) if p.kind != "hero" else None
            self.last_price = cost
            dx = self.panel(p).get("hud_shift", 0.0)  # the open panel moves the HUD
            before = self.cash_stable(dx=dx)
            if before is None or (cost is not None and before < cost):
                # the button's own price is above our cash: a click would do
                # nothing, so none is made (the caller saves up for last_price)
                self.fail_reason = "cash"
                return False
            # Click the path's button, then decide from the BUTTON whether the
            # tier was bought: it then shows the next tier's price (or the XP
            # lock). Cash alone misleads when pop income lands between the two
            # reads: with Double Cash a click that bought a tier looked like
            # nothing, the hotkey fallback then bought a SECOND tier, and the
            # bot believed neither (Lost Crevasse: spike factories went
            # 0-0-0 -> 0-0-2 in one "failed" upgrade). The hotkey is pressed
            # only while the same price is still on the button.
            self.inp.click(*self.panel(p)["paths"][path - 1])
            verdict = self._await_verdict(p, path, shown, before, cost, dx)
            if verdict == "same":
                self.inp.press(T.UPGRADE_HOTKEYS[path - 1])
                verdict = self._await_verdict(p, path, shown, before, cost, dx)
            if verdict == "bought":
                cross_before = p.crosspath
                p.tiers[path - 1] += 1
                p.spent += cost or 0
                log.info("upgraded %s -> %s for $%s", p.tid, p.crosspath, cost)
                journal.current().event("upgrade", tid=p.tid, kind=p.kind, path=path,
                                        cross_before=cross_before, cross_after=p.crosspath,
                                        cost=cost, why=getattr(self, "why", None))
                return True
            log.info("upgrade %s path %d not bought (panel %s, cash %s)", p.tid, path, costs, before)
            self.fail_reason = "noeffect"
            return False
        finally:
            self.deselect(p)

    # The price on an upgrade button can take most of a second to change after
    # a purchase. Judged 0.3 s after the click, a bought tier looked "not
    # bought", the hotkey fallback then bought the NEXT tier too, and the bot
    # believed neither (22 games: 131 "not bought" lines, most of them right
    # after another upgrade of the same tower, towers jumping 1-0-0 -> 2-0-2).
    VERDICT_WAIT = 1.2
    VERDICT_POLL = 0.15

    def _await_verdict(self, p, path, shown, before, cost, dx):
        """Poll _upgrade_verdict until it says "bought" or VERDICT_WAIT has
        passed: only a button that kept its price that long counts as "same"."""
        end = time.time() + self.VERDICT_WAIT
        while True:
            time.sleep(self.VERDICT_POLL)
            verdict = self._upgrade_verdict(p, path, shown, before, cost, dx)
            if verdict == "bought" or time.time() >= end:
                return verdict

    def _next_tier_same_price(self, p, path):
        """True when the tier being bought and the one after it cost the same
        (Ninja path 1 on Hard: $380 and $380). The button then shows the same
        price whether the click bought the tier or not, so it cannot prove
        "same" and the cash decides. Taken as "same", it made the hotkey buy
        the second tier too: Ancient Portal ABR (2026-11-04) turned both
        ninjas 0-0-1 -> 2-0-1 in one "failed" upgrade, set the plan step
        aside and spent the money meant for it elsewhere."""
        if p.kind == "hero":
            return False
        tier = p.tiers[path - 1] + 1
        if tier >= 5:
            return False
        this = T.upgrade_cost(p.kind, path, tier, self.difficulty)
        after = T.upgrade_cost(p.kind, path, tier + 1, self.difficulty)
        return abs(this - after) <= 5           # the game rounds prices to $5

    def _upgrade_verdict(self, p, path, shown, before, cost, dx):
        """After an upgrade click: 'bought', 'same' (the button still shows
        the same price: the click did not register), or 'unknown'.

        The button decides when it can be read: another price or the XP lock
        means the tier was bought. A blank button (path now maxed or closed,
        or an unreadable read) falls back to the cash, which must have
        dropped by about the price (PRICE_BAND), not merely gone down.

        Cash that did not drop says "same" only when the button agrees: if
        the button moved, or cannot move because the next tier costs the
        same, pop income may simply have covered the price. Rake Impoppable
        (2026-11-04) took such cash as "same" four times; each time the
        hotkey bought a second tier (ninjas 0-0-1 -> 2-0-1, ninja1 2-0-1 ->
        4-0-1) and the bot counted one or none. "unknown" retries later,
        after the panel's prices have corrected the count."""
        again = self.path_costs(p)[path - 1]
        same_price = self._next_tier_same_price(p, path)
        moved = shown[1] is not None and again[0] is not None and again != shown
        if shown[1] is not None and again[0] is not None:
            if again == shown and not same_price:
                return "same"
            if again[0] == "xp":
                return "bought"                  # the next tier is XP-locked
            # A price of a LATER tier - not just any other number (an OCR
            # slip). One past the next is the usual case; further on means
            # the count was already behind, which the next panel read fixes.
            if p.kind != "hero" and again[1] is not None:
                named = self._tier_for_price(p.kind, path, again[1])
                if named is not None and named >= p.tiers[path - 1] + 2:
                    return "bought"
        after = self.cash_stable(dx=dx)
        if before is not None and after is not None and cost:
            lo, hi = self.PRICE_BAND
            if lo * cost <= before - after <= hi * cost:
                return "bought"
            if after >= before:
                return "unknown" if (moved or same_price) else "same"
        return "unknown"

    def target(self, p, mode):
        """Cycle p's targeting until its button shows `mode` (a word of it is
        enough: "lock" for Lock In Place, "pursuit", "strong"...).

        The button's label can wrap onto two lines ("LOCK IN / PLACE" on a
        heli), which the one-line recogniser garbles ("Ck"), so the label is
        read with the full OCR and its words joined."""
        from .vision import norm
        want = norm(mode)
        if not self.select(p):
            return False
        try:
            pan = self.panel(p)
            x0, y0, x1, y1 = pan["target_text"]
            region = (x0, y0 - 0.012, x1, y1 + 0.012)
            for _ in range(8):
                f = self.fresh()
                words = self._vision().read(region=region, img=f)
                if want in norm(" ".join(w.text for w in words)):
                    return True
                self.inp.click(*pan["target_next"])
                time.sleep(0.2)
            return False
        finally:
            self.deselect(p)

    def sell(self, p):
        """Sell tower p; True once its Sell button was clicked. Refused, with
        no click at all, in a mode that forbids selling (CHIMPS): the game
        would take the sale and the run would no longer count."""
        why = getattr(self, "why", None)
        if getattr(self, "no_sell", False):
            log.error("refusing to sell %s: this mode forbids selling", p.tid)
            return False
        if not self.select(p):
            return False
        self.inp.click(*self.panel(p)["sell"])
        time.sleep(0.3)
        self.towers.pop(p.tid, None)
        log.info("sold %s (%s %s) - %s", p.tid, p.kind, p.crosspath,
                 (why or {}).get("reason") or (why or {}).get("source") or "no reason given")
        journal.current().event("sell", tid=p.tid, kind=p.kind, cross=p.crosspath, spent=p.spent, why=why)
        return True

    def remove_obstacle(self, fx, fy, cost, name=""):
        """Buy the removal of the obstacle at (fx, fy) with in-game cash
        (never Monkey Money - removals are paid from the round's cash).

        The price is read off the game's box (the map file's price can
        differ by difficulty), the green check is clicked only if the cash
        covers it, and the purchase counts only when the cash then drops by
        about that price. Anything unexpected cancels: nothing is bought."""
        if not self.screen_ok():
            return False
        before = self.cash_stable()
        if before is None or before < cost:
            return False
        self.inp.click(fx, fy)
        time.sleep(0.6)
        f = self.fresh()
        box = find_removal_box(f, self._vision().read(img=f))
        if box is None:
            log.info("obstacle %s: no removal box after clicking it", name)
            self.close_panels()          # the click may have opened something else
            return False
        price = box["price"] or cost
        if box["confirm"] is None or price > before:
            log.info("obstacle %s: box read %s, confirm %s, cash %s - cancelled", name, price, box["confirm"], before)
            self.inp.click(*(box["cancel"] or (0.5, 0.012)))   # the X, or anywhere outside the box
            time.sleep(0.4)
            return False
        self.inp.click(*box["confirm"])
        time.sleep(0.7)
        after = self.cash_stable()
        paid = None if after is None else before - after
        if paid is not None and paid >= 0.6 * price:
            log.info("removed obstacle %s for $%s", name, price)
            return True
        # The cash can rise instead of dropping: with BTD6's Auto Start on
        # the round keeps paying while the box is confirmed. On Cornfield
        # Magic Only (2026-11-05) ten obstacles were bought this way and
        # each "not counted", so the freed ground was never used and the
        # bot sat on $29k with "0 legal cells". The obstacle itself is the
        # proof: once it is gone, clicking its spot opens no box.
        self.inp.click(fx, fy)
        time.sleep(0.6)
        f = self.fresh()
        again = find_removal_box(f, self._vision().read(img=f))
        if again is None:
            log.info("removed obstacle %s for $%s (cash %s -> %s: the round's income hid the price)",
                     name, price, before, after)
            self.close_panels()      # the click may have selected a tower standing there now
            return True
        log.warning("obstacle %s: still there after confirming $%s (cash %s -> %s) - not counted as removed",
                    name, price, before, after)
        self.inp.click(*(again["cancel"] or (0.5, 0.012)))
        time.sleep(0.4)
        return False

    def ability(self, n):
        self.inp.press(str(n))


# -- removable obstacles ------------------------------------------------------
# Clicking a removable obstacle (Peninsula's kelp, Dark Castle's trees...)
# opens a box "Remove FOR $500" with a red X and a green check under the text;
# the box pauses the game. Clicking outside it cancels.
# High Finance's empty lots open the same box worded "BUILD FOR $1,500" (a
# platform that becomes tower ground). Only "remove" was read, so on High
# Finance Deflation (2026-11-04) the box was left open, taken for a purchase
# screen, and the game ran on with $12,120 unspent until it was lost.
REMOVE_BOX_BELOW = 0.16     # how far below the text (screen height) the buttons sit
REMOVE_BOX_SIDE = 0.16      # and how far left/right of the text's centre


def _colour_blob(img, region, lo, hi):
    """Centre (screen fractions) of the largest blob within HSV [lo, hi]
    inside region (fx0, fy0, fx1, fy1) of img, or None."""
    h, w = img.shape[:2]
    x0, y0 = max(0, int(region[0] * w)), max(0, int(region[1] * h))
    x1, y1 = min(w, int(region[2] * w)), min(h, int(region[3] * h))
    if x1 <= x0 or y1 <= y0:
        return None
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lo, hi)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[best, cv2.CC_STAT_AREA] < 0.0004 * w * h:      # a button, not a stray pixel
        return None
    cx, cy = cents[best]
    return (x0 + cx) / w, (y0 + cy) / h


# A mode's intro box is a flat blue panel (HSV about 107, 150, 212 on Cargo
# and Luminous Cove, 2026-11-05) with a green OK low in its middle. The HUD's
# digit reader cannot read the word "OK" (it gave "1" and "K"), so the box is
# known by its panel: these strips left of, right of and above the button
# (screen fractions) must be all panel. On a match without the box they hold
# map, water, track and bloons, and read 0.0-0.001 of panel.
INTRO_PANEL_HSV = ((100, 60, 120), (125, 200, 255))
INTRO_PANEL_STRIPS = ((0.36, 0.66, 0.42, 0.75), (0.58, 0.66, 0.64, 0.75), (0.40, 0.62, 0.60, 0.66))
INTRO_PANEL_MIN = 0.9        # share of a strip that must be panel
INTRO_OK_HSV = ((40, 120, 120), (85, 255, 255))     # the green OK button


def _panel_share(img, region, lo, hi):
    """Share of the pixels in region (screen fractions) within HSV [lo, hi]."""
    h, w = img.shape[:2]
    c = img[int(region[1] * h):int(region[3] * h), int(region[0] * w):int(region[2] * w)]
    if c.size == 0:
        return 0.0
    return float(cv2.inRange(cv2.cvtColor(c, cv2.COLOR_BGR2HSV), *INTRO_PANEL_HSV).mean()) / 255.0


def find_intro_box_ok(img):
    """Centre (screen fractions) of the OK button of a mode's intro box over
    the match, or None when no box is showing: the panel strips around the
    button must be panel-blue and a green button must sit between them."""
    if any(_panel_share(img, s, *INTRO_PANEL_HSV) < INTRO_PANEL_MIN for s in INTRO_PANEL_STRIPS):
        return None
    return _colour_blob(img, Game.INTRO_OK_REGION, *INTRO_OK_HSV)


def find_removal_box(img, words):
    """The "Remove FOR $N" (or "Build FOR $N") box in a frame:
    {"price", "confirm", "cancel"} (button centres as screen fractions; a
    button may be None), or None when no such box is showing.

    "build" alone is a common word, so it counts only followed by "for"."""
    import re
    from .vision import norm

    def is_box_text(t):
        t = norm(t)
        return "remove" in t or ("build" in t and "for" in t)
    text = next((w for w in words if is_box_text(w.text)), None)
    if text is None:
        return None
    # OCR reads the price's zeros as letter O and its comma as a dot
    # ("$1.5OO"), so both are mended before the digits are taken
    tail = text.text.split("$")[-1].replace("O", "0").replace("o", "0").replace(".", ",")
    digits = re.findall(r"\d[\d,]*", tail) or re.findall(r"\d[\d,]*", text.text)
    price = parse_int(digits[-1]) if digits else None
    below = (text.y, text.y + REMOVE_BOX_BELOW)
    # the green check sits right of the text's centre, the red X left of it
    confirm = _colour_blob(img, (text.x, below[0], text.x + REMOVE_BOX_SIDE, below[1]), (40, 120, 120), (85, 255, 255))
    cancel = _colour_blob(img, (text.x - REMOVE_BOX_SIDE, below[0], text.x, below[1]), (0, 120, 140), (12, 255, 255))
    return {"price": price, "confirm": confirm, "cancel": cancel}


def _red_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return (cv2.inRange(hsv, (0, 90, 90), (10, 255, 255)) |
            cv2.inRange(hsv, (168, 90, 90), (180, 255, 255))) > 0


def _red_frac(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 90, 90), (10, 255, 255)) | cv2.inRange(hsv, (168, 90, 90), (180, 255, 255))
    return np.count_nonzero(red) / max(1, red.size)


def _expand(pt, dx, dy):
    x, y = pt
    return (x - dx, y - dy, x + dx, y + dy)


def price_row(text):
    """What one upgrade button's price row says, from its OCR text: ("xp", n)
    for a tier still locked behind tower XP, ("cash", n) for a price, and
    (None, None) when there is no price - the path is closed or maxed, or
    the read is unreadable.

    A price of $0 is no price: no tier costs nothing. High Finance Magic
    Monkeys Only (2026-11-05) read a wizard's "PATH CLOSED" box as $0
    twice; each read let Game.upgrade click the closed button, the click
    counted as a purchase with no effect, four of them capped the path for
    the game, and reinforce kept asking for it (reinforce.grown_from). Read
    as no price, the box goes the closed-path way (_path_closed)."""
    low = text.lower()
    if "xp" in low:
        return "xp", parse_int(low.replace("xp", ""))
    if looks_like_price(text):
        value = parse_int(text)
        if value != 0:
            return "cash", value
    return None, None


def looks_like_price(text):
    """Is this OCR text of an upgrade button a cash price ('$2,200')?

    The '$' is the shakiest character: OCR has read it as 'S', 's' and '#'.
    '#2,200' was not accepted, so Deadly Precision ($2,200) read as a blank
    button on every sniper, the path was closed for the game, and Peninsula
    Reverse (2026-11-03) was lost at round 50 with $51,030 unspent. So up to
    two leading symbols or an 'S' may stand before the first digit; words
    ('PATH CLOSED', upgrade names) still do not count.

    At the full 1920x1200 capture the '$' is also read as a CJK character
    ('$500' -> '学500', Cargo Medium 2026-11-03, about 80 blank reads an
    hour). Python's isalnum() is True for such characters, so "symbol" here
    means anything that is not an ASCII letter or digit."""
    t = text.strip()
    if "$" in t:
        return True
    i = 0
    while i < min(2, len(t)) and not _ascii_alnum(t[i]):
        i += 1
    if t[i:i + 1] in ("s", "S"):
        i += 1
    return t[i:i + 1] in _ASCII_DIGITS


_ASCII_DIGITS = frozenset("0123456789")


def _ascii_alnum(ch):
    """An ASCII letter or digit (str.isalnum also accepts e.g. '学')."""
    return ch.isascii() and ch.isalnum()


def _path_open_by_tiers(tiers, path):
    """Can a tower with these tiers take the next tier of `path` (1-3)?
    Not maxed, and the crosspath stays legal: two paths at most, only one
    past tier 2."""
    t = list(tiers)
    if t[path - 1] >= 5:
        return False
    t[path - 1] += 1
    return sum(x > 0 for x in t) <= 2 and sum(x > 2 for x in t) <= 1


def _legal_cross(tiers):
    """A crosspath the game allows: tiers 0..5, at most two paths in use,
    at most one of them above tier 2."""
    return (len(tiers) == 3 and all(0 <= t <= 5 for t in tiers)
            and sum(t > 0 for t in tiers) <= 2 and sum(t > 2 for t in tiers) <= 1)
