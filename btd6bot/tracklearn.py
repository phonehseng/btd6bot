"""Learn a map's track in Sandbox mode, before the first real game there.

In a real game the tracer must ignore motion around our towers (projectiles),
which is exactly where the defended track runs, and Fast Track skips the early
rounds it learned from - so models came out with whole lanes missing and with
animated scenery (seasonal props) in the corners. Sandbox has no towers,
infinite lives and costs nothing: record the scenery's own motion first, then
play rounds with nothing on the field and trace the bloons on every lane.
"""
import logging
import time

import cv2
import numpy as np

from .maplearn import GRID, MapModel, PathTracer
from .status import set_state

log = logging.getLogger("tracklearn")

LEARNED_ROUNDS = 25  # in-game tracing stops at this many traced rounds


class SandboxTracer(PathTracer):
    """Background subtraction on chromaticity instead of frame differencing.

    Cloud shadows (Monkey Meadow) and lighting changes darken the grass but keep
    its hue; a bloon changes the hue. The background is the median of frames
    taken before any bloon is on the field; scenery that animates on its own
    (seasonal props, water) is measured then too and masked out."""

    # HUD readouts that change while bloons run (lives, cash, round counter,
    # the "FAST TRACK ENABLED" banner): (x0, y0, x1, y1) fractions of the screen
    HUD_ZONES = ((0.0, 0.0, 0.34, 0.13), (0.62, 0.0, 0.86, 0.17))

    def __init__(self, model):
        super().__init__(model, region_mask=self._hud_mask(model))
        self.bg = None
        self._bg_frames = []

    @classmethod
    def _hud_mask(cls, model):
        """Grid mask: True where tracing is allowed (outside the HUD zones)."""
        w, h = GRID
        keep = np.ones((h, w), bool)
        px0, py0, px1, py1 = model.playfield
        for x0, y0, x1, y1 in cls.HUD_ZONES:
            # screen fractions -> playfield grid cells
            cx0 = int(np.clip((x0 - px0) / (px1 - px0), 0, 1) * w)
            cx1 = int(np.ceil(np.clip((x1 - px0) / (px1 - px0), 0, 1) * w))
            cy0 = int(np.clip((y0 - py0) / (py1 - py0), 0, 1) * h)
            cy1 = int(np.ceil(np.clip((y1 - py0) / (py1 - py0), 0, 1) * h))
            keep[cy0:cy1, cx0:cx1] = False
        return keep

    @staticmethod
    def _chroma(img):
        f = img.astype(np.float32) + 1.0
        return f / f.sum(axis=2, keepdims=True)

    def add_background(self, frame):
        self._bg_frames.append(self._small(frame))
        if len(self._bg_frames) > 9:
            self._bg_frames.pop(0)
        self.bg = self._chroma(np.median(np.stack(self._bg_frames), axis=0).astype(np.uint8))

    def _bloons(self, cur):
        hsv = cv2.cvtColor(cur, cv2.COLOR_BGR2HSV)
        d = np.abs(self._chroma(cur) - self.bg).sum(axis=2)
        h, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        # early-round bloons are bright red/blue/green/yellow/pink; seasonal
        # bats are dark purple (and no purple bloons come this early)
        mask = ((d > 0.12) & (sat > 90) & (val > 120) & ~((h >= 125) & (h <= 160))).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        return cv2.resize(mask.astype(np.float32), GRID, interpolation=cv2.INTER_AREA) > 0.08

    def feed_idle(self, frame):
        cur = self._small(frame)
        if self.bg is not None:
            self.ambient += self._bloons(cur)
            self.ambient_frames += 1

    def ambient_mask(self):
        if self.ambient_frames < 5:
            return np.zeros(self.m.heat.shape, bool)
        amb = (self.ambient / self.ambient_frames) > 0.05
        return cv2.dilate(amb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    def feed_count(self, frame):
        """Feed one frame; returns how many grid cells hold a bloon now."""
        small = self._bloons(self._small(frame)) & ~self._amb & self.region_mask
        if small.mean() > 0.25:
            return 1  # screen transition / popup: not 'clear'
        self.m.heat[small] += 1
        newly = small & np.isnan(self.first_seen)
        self.first_seen[newly] = time.time() - self.t0
        return int(small.sum()) if small.sum() > 2 else 0


def sandbox_difficulty(account, map_name):
    """Easiest difficulty whose standard medal this save has on the map, or None.

    A difficulty's Sandbox only unlocks after beating that difficulty on the
    map; clicking a locked one leads to a purchase offer."""
    for diff in ("easy", "medium", "hard"):
        if account.has_medal(map_name, diff):
            return diff
    return None


def needs_sandbox(model):
    """True until the map's track has been learned cleanly in Sandbox."""
    return not getattr(model, "sandbox_rounds", 0)


def learn_track(bot, map_name, rounds=(1, 2, 3, 5, 7), max_seconds=300):
    """Main menu -> map -> beaten difficulty -> Sandbox -> trace -> main menu.

    rounds: sent one after another; a mix of odd/even/prime numbers so maps
    that switch lanes by round number show every lane. True when saved."""
    from .game import Game
    from .menus import page_forbidden
    diff = sandbox_difficulty(bot.account, map_name)
    if diff is None:
        log.info("sandbox: no difficulty beaten on %s yet - Sandbox locked, skipping", map_name)
        return False
    set_state(f"first visit to {map_name}: learning its track in Sandbox")
    bot.skip_known = None
    if bot.open_map(map_name) is not True:
        return False
    for _ in range(3):
        bot.menus.read()
        if bot.menus.click_word(diff, dy=-0.09, region=(0, 0.3, 1, 0.7)) and \
                bot.menus.wait_for("mode_select", timeout=3) == "mode_select":
            break
    else:
        log.warning("sandbox: %s did not open its modes", diff)
        bot.to_main_menu()
        return False
    bot.menus.read()
    if not bot.menus.click_word("sandbox", dy=-0.08):
        log.warning("sandbox: no Sandbox button")
        bot.to_main_menu()
        return False
    g = Game(bot.s, bot.inp, bot.lay, difficulty=diff, hero=None)
    # Wait for the game: the mode screen first fades out (its text "Monkeys
    # cost ..." + "$25" rewards would look like a price offer), then a
    # "SANDBOX MODE ... OK" intro pops up over the map.
    end = time.time() + 25
    while time.time() < end:
        time.sleep(0.8)
        st = bot.menus.identify()
        if st == "mode_select":
            continue  # still fading out
        if bot.menus.has("sandboxmode"):
            bot.menus.click_word("ok")
            time.sleep(1.0)
            continue
        if page_forbidden(bot.menus.words):  # safety net: never buy anything here
            log.warning("sandbox: %s Sandbox offered for purchase - backing out", diff)
            bot.to_main_menu()
            return False
        if g.in_game():
            time.sleep(1.0)
            bot.menus.read()
            if not bot.menus.has("sandboxmode"):
                break
    if not g.in_game():
        log.warning("sandbox: game screen did not appear")
        bot.to_main_menu()
        return False

    model = MapModel.load(map_name, bot.lay["playfield"])
    model.heat[:] = 0
    model.t_sum[:] = 0
    model.t_cnt[:] = 0
    model.rounds_traced = 0
    tracer = SandboxTracer(model)
    t_start = time.time()
    try:
        for _ in range(9):  # empty field: the background
            tracer.add_background(g.fresh())
            time.sleep(0.25)
        _idle(g, tracer, 4.0)  # scenery that animates by itself
        _fast(bot, g)
        for i, rnd in enumerate(rounds):
            if time.time() - t_start > max_seconds:
                break
            set_state(f"learning the track of {map_name} in Sandbox: round {rnd} ({i + 1}/{len(rounds)})")
            _send_round(bot, rnd)
            tracer.start_round()
            t_round = time.time()
            clear_since = None
            while time.time() - t_round < 60:
                f = g.fresh()
                if not g.in_game(f):
                    bot.menus.dismiss_popup()
                    time.sleep(0.5)
                    continue
                busy = tracer.feed_count(f)
                if busy:
                    clear_since = None
                elif clear_since is None:
                    clear_since = time.time()
                if time.time() - t_round > 4 and clear_since and time.time() - clear_since > 2.0:
                    break  # every bloon has left the track
                time.sleep(0.01)
            tracer.end_round()
            _idle(g, tracer, 1.0)
        traced = model.rounds_traced
        # stray hits (leaves, bats, popups) are rare; the track is hit every round
        floor = 0.04 * float(np.percentile(model.heat[model.heat > 0], 99)) if (model.heat > 0).any() else 0
        noise = model.heat < max(floor, 2)
        model.heat[noise] = 0
        model.t_sum[noise] = 0
        model.t_cnt[noise] = 0
        cells = int((model.heat > 0).sum())
        log.info("sandbox: %s traced over %d rounds, %d track cells", map_name, traced, cells)
        frac = cells / model.heat.size
        if traced >= 3 and 150 < cells and frac < 0.45:
            model.sandbox_rounds = traced
            model.rounds_traced = max(traced, LEARNED_ROUNDS)  # no noisy in-game tracing
            model.save()
            ok = True
        else:
            log.warning("sandbox: unusable trace (%d rounds, %.0f%% of the map) - not saved", traced, frac * 100)
            ok = False
    finally:
        _leave(bot, g)
    return ok


# Sandbox side panel (calibrated live 2026-10-21, 1920x1200): rounds are sent
# from SET ROUND + its green button; the bottom-right button only toggles 2x
SET_ROUND_FIELD = (0.903, 0.098)
SEND_ROUND = (0.962, 0.085)


def _fast(bot, g):
    for _ in range(2):
        if g.button_state() == "play_fast":
            return
        bot.inp.click(*bot.lay["play_button"])
        time.sleep(0.5)


def _send_round(bot, rnd):
    bot.inp.click(*SET_ROUND_FIELD)
    time.sleep(0.4)
    for _ in range(4):
        bot.inp.press("backspace")
    bot.inp.type_text(str(rnd))
    time.sleep(0.2)
    bot.inp.click(*SEND_ROUND)
    time.sleep(0.5)


def _idle(g, tracer, seconds):
    end = time.time() + seconds
    while time.time() < end:
        tracer.feed_idle(g.fresh())
        time.sleep(0.05)


def _leave(bot, g):
    """Sandbox -> main menu (nothing to save or lose)."""
    for _ in range(4):
        if bot.menus.identify() == "main_menu":
            return
        if g.in_game():
            bot.inp.click(*bot.lay["gear"])
            time.sleep(0.8)
        bot.menus.read()
        if bot.menus.click_word("home"):
            bot.menus.wait_for("main_menu", timeout=8)
        else:
            bot.to_main_menu()


def reversed_from(base, model):
    """Reverse mode runs the same track backwards: copy heat, flip progress."""
    model.heat = base.heat.copy()
    model.t_cnt = base.t_cnt.copy()
    model.t_sum = np.where(base.t_cnt > 0, base.t_cnt - base.t_sum, 0).astype(np.float32)
    model.rounds_traced = base.rounds_traced
    model.sandbox_rounds = getattr(base, "sandbox_rounds", 0)
