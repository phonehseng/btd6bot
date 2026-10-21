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

    def hold(self, kind):
        key = T.HERO_HOTKEY if kind == "hero" else T.TOWERS[kind]["hotkey"]
        if not key:
            raise ValueError(f"{kind} has no hotkey bound")
        if self.is_holding():
            self.cancel_hold()
        self.inp.press(key)
        for _ in range(8):
            time.sleep(0.06)
            if self.is_holding():
                return True
        return False

    def probe_roster(self):
        """Which towers does this save have? Press each hotkey before round 1:
        a tower that can be picked up is unlocked. Towers we cannot afford yet
        are left out (unknown). Returns {tower_id: True/False}."""
        cash = self.cash_stable()
        out = {}
        for kind, t in T.TOWERS.items():
            if not t.get("hotkey"):
                continue
            if cash is None or self.price(kind) > cash:
                continue
            held = self.hold(kind)
            out[kind] = held
            if held:
                self.cancel_hold()
        log.info("roster probe: %s", {k: v for k, v in out.items()})
        return out

    def cancel_hold(self):
        if self.is_holding():
            self.inp.click(*self.lay["cancel_place"])
            time.sleep(0.15)

    def probe(self, fx, fy, baseline=None, settle=0.06):
        """With a tower held, is (fx, fy) a legal spot? Red range circle = no."""
        self.inp.move(fx, fy, fast=True)
        time.sleep(settle)
        f = self.fresh()
        r = 0.035
        reg = (max(0, fx - r), max(0, fy - r * 1.6), min(1, fx + r), min(1, fy + r * 1.6))
        red_now = _red_frac(crop(f, reg))
        red_base = _red_frac(crop(baseline, reg)) if baseline is not None else 0.0
        return (red_now - red_base) < 0.12

    # -- placing ----------------------------------------------------------------
    def price(self, kind):
        if kind == "hero":
            return T.hero_cost(self.hero, self.difficulty)
        return self.learned_cost.get((kind, 0, 0)) or T.tower_cost(kind, self.difficulty)

    def place(self, tid, kind, fx, fy, check_valid=True):
        """Place a tower; returns Placed or None. Verifies via cash drop."""
        self.fail_reason = None
        before = self.cash_stable()
        cost = self.price(kind)
        if before is None or before < cost:
            self.fail_reason = "cash"
            return None
        self.cancel_hold()
        baseline = self.fresh()  # the spot without a held tower, to compare against
        if not self.hold(kind):
            log.info("could not pick up %s (locked or unaffordable)", kind)
            self.fail_reason = "hold"
            return None
        if check_valid and not self.probe(fx, fy, baseline):
            self.cancel_hold()
            log.info("spot %.3f,%.3f invalid for %s", fx, fy, kind)
            self.fail_reason = "spot"
            return None
        self.inp.click(fx, fy)
        time.sleep(0.25)
        if self.is_holding():
            self.cancel_hold()
            self.fail_reason = "click"
            return None
        after = self.cash_stable()
        if before is not None and after is not None:
            if after >= before:
                log.warning("placement of %s not confirmed (cash %s -> %s)", kind, before, after)
                self.fail_reason = "noeffect"
                return None
            self.learned_cost[(kind, 0, 0)] = before - after
        p = Placed(tid, kind, fx, fy, spent=(before - after) if before and after else cost)
        self.towers[tid] = p
        log.info("placed %s (%s) at %.3f,%.3f", tid, kind, fx, fy)
        return p

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
        if self.is_holding():
            self.cancel_hold()
        for attempt in range(3):
            self.inp.click(p.x, p.y)
            for _ in range(3):  # the panel slides in over ~0.3 s
                time.sleep(0.15)
                side = self._open_side()
                if side:
                    p.panel_side = side
                    return True
            # nudge: the click may have hit the edge of the sprite
            p_dx = (0.004, -0.004, 0.0)[attempt]
            p.x += p_dx
        return False

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
        """Per path: ("cash", n) | ("xp", n) for a locked tier | (None, None)."""
        f = f if f is not None else self.fresh()
        out = []
        for reg in self.panel(p)["cost_rows"]:
            text, conf = rec_text(crop(f, reg))
            low = text.lower()
            if "xp" in low:
                out.append(("xp", parse_int(low.replace("xp", ""))))
            elif "$" in text or text[:1].isdigit():
                out.append(("cash", parse_int(text)))
            else:
                out.append((None, None))
        return out

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

    def upgrade(self, p, path, max_wait=0.0, allow_xp_unlock=True):
        """Buy the next tier on path (1..3). Returns True if it went through.

        A tier still locked behind tower XP is unlocked on the spot (when the
        tower has enough XP) through the upgrade tree, then bought.
        """
        self.fail_reason = None
        self.locked_seen = None
        if not self.select(p):
            log.warning("could not select %s", p.tid)
            self.fail_reason = "select"
            return False
        try:
            costs = self.path_costs(p)
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
            if cost is None:
                cost = T.upgrade_cost(p.kind, path, p.tiers[path - 1] + 1, self.difficulty) if p.kind != "hero" else None
            dx = self.panel(p).get("hud_shift", 0.0)  # the open panel moves the HUD
            before = self.cash_stable(dx=dx)
            if before is None or (cost is not None and before < cost):
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
            if before is not None and after is not None and after < before:
                p.tiers[path - 1] += 1
                p.spent += before - after
                self.learned_cost[(p.kind, path, p.tiers[path - 1])] = before - after
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


def _red_frac(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 90, 90), (10, 255, 255)) | cv2.inRange(hsv, (168, 90, 90), (180, 255, 255))
    return np.count_nonzero(red) / max(1, red.size)


def _expand(pt, dx, dy):
    x, y = pt
    return (x - dx, y - dy, x + dx, y + dy)
