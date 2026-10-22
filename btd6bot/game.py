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
            return None
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
        path must show something (a panel still sliding in shows nothing)."""
        if costs[path - 1] != (None, None) or all(c == (None, None) for c in costs):
            return False
        time.sleep(0.1)
        if self.path_costs(p)[path - 1] != (None, None):
            return False
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
            # click the path's upgrade button; fall back to the hotkey
            self.inp.click(*self.panel(p)["paths"][path - 1])
            time.sleep(0.3)
            after = self.cash_stable(dx=dx)
            if before is not None and after is not None and after >= before:
                self.inp.press(T.UPGRADE_HOTKEYS[path - 1])
                time.sleep(0.3)
                after = self.cash_stable(dx=dx)
            if after is None and before is not None and shown[1] is not None:
                # the cash was unreadable after the click (a flash or popup);
                # if the button now shows another price (the next tier's), it
                # was bought. An unreadable button proves nothing either way.
                again = self.path_costs(p)[path - 1]
                if again[1] is not None and again != shown:
                    after = before - shown[1]
            if before is not None and after is not None and after < before:
                p.tiers[path - 1] += 1
                p.spent += before - after
                if p.kind != "hero":
                    self.learn_price(p.kind, path, p.tiers[path - 1], before - after)
                log.info("upgraded %s -> %s", p.tid, p.crosspath)
                return True
            log.info("upgrade %s path %d not bought (panel %s, cash %s -> %s)",
                     p.tid, path, costs, before, after)
            self.fail_reason = "noeffect"
            return False
        finally:
            self.deselect(p)

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

    def ability(self, n):
        self.inp.press(str(n))


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


def _legal_cross(tiers):
    """A crosspath the game allows: tiers 0..5, at most two paths in use,
    at most one of them above tier 2."""
    return (len(tiers) == 3 and all(0 <= t <= 5 for t in tiers)
            and sum(t > 0 for t in tiers) <= 2 and sum(t > 2 for t in tiers) <= 1)
