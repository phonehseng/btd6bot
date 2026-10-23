"""In-game control: placing, probing, upgrading, targeting, speed, abilities.

Every action is verified from the screen (tower held? cash dropped? panel open?)
rather than assumed, because a missed click silently ruins a run.
"""
import logging
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import towers as T
from .hud import Hud, parse_int, rec_text
from .templates import classify
from .vision import crop

log = logging.getLogger("game")

PLAY_BTN = (0.905, 0.835, 1.0, 0.975)
TARGETS = ["first", "last", "close", "strong"]
CLOSED_AFTER_MISSES = 3   # blank price reads (separate attempts) before a path its tiers allow counts closed


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
        self.last_spot = None      # (fx, fy) where the last place() released its hold
        self._frame = None
        self._frame_t = 0

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
        """Cash read twice in agreement (guards against OCR blips)."""
        last = None
        for _ in range(tries):
            c = self.hud.cash(self.fresh(), dx)
            if c is not None and c == last:
                return c
            last = c
            time.sleep(0.05)
        return last

    def lives(self):
        return self.hud.lives(self.fresh())

    def round(self):
        return self.hud.round(self.fresh())

    def button_state(self, f=None):
        return classify(f if f is not None else self.fresh(),
                        ["play_idle", "play_run", "play_fast"], PLAY_BTN)[0]

    def in_game(self, f=None):
        f = f if f is not None else self.fresh()
        best, scores = classify(f, ["play_idle", "play_run", "play_fast"], PLAY_BTN)
        return scores[best] > 0.75

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
    def is_holding(self, f=None):
        f = f if f is not None else self.fresh()
        x, y = self.lay["cancel_place"]
        reg = (x - 0.012, y - 0.02, x + 0.012, y + 0.02)
        c = crop(f, reg)
        hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
        # the cancel button is orange-red with a white X
        red = cv2.inRange(hsv, (0, 130, 150), (15, 255, 255)) | cv2.inRange(hsv, (172, 130, 150), (180, 255, 255))
        return np.count_nonzero(red) / red.size > 0.3

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
                # an open upgrade panel or the cursor over the side panel can
                # swallow the hotkey: clear both and retry
                self.close_panels()
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

        more_spots: further (fx, fy) candidates, best first. When a spot is
        refused, the tower stays on the cursor and the next spot is probed:
        a probe takes ~0.1 s, while cancelling and picking the tower up again
        took ~1.4 s per refused spot. Every refused spot is listed in
        self.refused_spots so the caller can learn them.

        A tower is registered only on proof that it stands on the map (see
        _confirm). fail_reason: "cash", "hold", "spot" (every spot refused)
        or "unverified" (the hold was released, but neither the cash nor the
        map shows a new tower)."""
        self.fail_reason = None
        self.refused_spots = []
        self.last_spot = None
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
                continue
            self.last_spot = (sx, sy)
            return self._confirm(tid, kind, sx, sy, pre if pre is not None else before)
        self.cancel_hold()
        self.fail_reason = "spot"
        return None

    def _confirm(self, tid, kind, fx, fy, before):
        """The hold was released at (fx, fy). Register the tower only on proof:
        the cash dropped by about its price, or the tower can be selected there.

        Root cause of phantom towers: a released hold used to count as a
        purchase even when the cash went UP (Ancient Portal, "cash 374 -> 407"
        for a $400 ninja). Each phantom then failed 8 selections of ~3 s, and
        a phantom as the only tower would let a round start undefended."""
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
        elif self.select(p):
            self.deselect(p)
            log.info("placement of %s confirmed by selecting it (cash %s -> %s)",
                     kind, before, self._seen_cash)
        else:
            log.warning("placement of %s at %.3f,%.3f NOT confirmed (cash %s -> %s, nothing "
                        "to select there) - not recorded", kind, fx, fy, before, self._seen_cash)
            self.fail_reason = "unverified"
            self.unconfirmed_streak = getattr(self, "unconfirmed_streak", 0) + 1
            return None
        self.unconfirmed_streak = 0
        self.towers[tid] = p
        log.info("placed %s (%s) at %.3f,%.3f", tid, kind, fx, fy)
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
        a tower that fails twice in a row (Executor._forget_if_missing)."""
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
        """Pop counter shown under the tower's name (used to learn good spots)."""
        try:
            img = crop(self.fresh(), self.panel(p)["pops"])
            if not getattr(Game, "_pops_crop_saved", False):
                Game._pops_crop_saved = True  # one crop per session, for calibration
                from .vision import save
                save(img, "logs/pops_crop.png")
            v = parse_int(rec_text(img)[0])
            if v is not None and v >= getattr(p, "pops", 0):
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
        out = []
        for reg in self.panel(p)["cost_rows"]:
            text, conf = rec_text(crop(f, reg))
            low = text.lower()
            if "xp" in low:
                out.append(("xp", parse_int(low.replace("xp", ""))))
            elif "$" in text or text[:1].isdigit() or (low[:1] == "s" and low[1:2].isdigit()):
                out.append(("cash", parse_int(text)))   # OCR reads '$' as 'S' at times
            else:
                out.append((None, None))
        return out

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
        time.sleep(0.1)
        if self.path_costs(p)[path - 1] != (None, None):
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
        self.closed.add((p.tid, path))
        log.info("%s path %d is closed or maxed (panel %s) - not buying it this game",
                 p.tid, path, costs)
        self.fail_reason = "capped"
        return True

    def _tier_for_price(self, kind, path, price):
        """The tier of `path` whose price-table cost (this difficulty) is
        `price`, give or take the game's $5 rounding; None unless exactly one
        tier matches (a discounted price matches none and is left alone)."""
        tiers = [t for t in range(1, 6)
                 if abs(T.upgrade_cost(kind, path, t, self.difficulty) - price) <= 5]
        return tiers[0] if len(tiers) == 1 else None

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
            return False
        try:
            costs = self.path_costs(p)
            if p.kind != "hero":         # hero panels have no upgrade paths
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
                p.tiers[path - 1] += 1
                p.spent += cost or 0
                log.info("upgraded %s -> %s", p.tid, p.crosspath)
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

    def _upgrade_verdict(self, p, path, shown, before, cost, dx):
        """After an upgrade click: 'bought', 'same' (the button still shows
        the same price: the click did not register), or 'unknown'.

        The button decides when it can be read: another price or the XP lock
        means the tier was bought. A blank button (path now maxed or closed,
        or an unreadable read) falls back to the cash, which must have
        dropped by about the price (PRICE_BAND), not merely gone down."""
        again = self.path_costs(p)[path - 1]
        if shown[1] is not None and again[0] is not None:
            if again == shown:
                return "same"
            if again[0] == "xp":
                return "bought"                  # the next tier is XP-locked
            # the next tier's price - not just any other number (an OCR slip)
            if (p.kind != "hero" and again[1] is not None
                    and self._tier_for_price(p.kind, path, again[1]) == p.tiers[path - 1] + 2):
                return "bought"
        after = self.cash_stable(dx=dx)
        if before is not None and after is not None and cost:
            lo, hi = self.PRICE_BAND
            if lo * cost <= before - after <= hi * cost:
                return "bought"
            if after >= before:
                return "same"
        return "unknown"

    def target(self, p, mode):
        mode = mode.lower()
        if not self.select(p):
            return False
        try:
            pan = self.panel(p)
            for _ in range(8):
                text, _ = rec_text(crop(self.fresh(), pan["target_text"]))
                if mode in text.lower():
                    return True
                self.inp.click(*pan["target_next"])
                time.sleep(0.2)
            return False
        finally:
            self.deselect(p)

    def sell(self, p):
        if not self.select(p):
            return False
        self.inp.click(*self.panel(p)["sell"])
        time.sleep(0.3)
        self.towers.pop(p.tid, None)
        return True

    def remove_obstacle(self, fx, fy, cost, name=""):
        """Buy the removal of the obstacle at (fx, fy) with in-game cash
        (never Monkey Money - removals are paid from the round's cash).

        The price is read off the game's box (the map file's price can
        differ by difficulty), the green check is clicked only if the cash
        covers it, and the purchase counts only when the cash then drops by
        about that price. Anything unexpected cancels: nothing is bought."""
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
        log.warning("obstacle %s: cash %s -> %s after confirming $%s - not counted as removed", name, before, after, price)
        return False

    def ability(self, n):
        self.inp.press(str(n))


# -- removable obstacles ------------------------------------------------------
# Clicking a removable obstacle (Peninsula's kelp, Dark Castle's trees...)
# opens a box "Remove FOR $500" with a red X and a green check under the text;
# the box pauses the game. Clicking outside it cancels.
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


def find_removal_box(img, words):
    """The "Remove FOR $N" box in a frame: {"price", "confirm", "cancel"}
    (button centres as screen fractions; a button may be None), or None when
    no such box is showing."""
    import re
    from .vision import norm
    text = next((w for w in words if "remove" in norm(w.text)), None)
    if text is None:
        return None
    digits = re.findall(r"\d[\d,]*", text.text.split("$")[-1]) or re.findall(r"\d[\d,]*", text.text)
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
