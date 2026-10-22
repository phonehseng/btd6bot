"""Learn a map's track in Sandbox mode, before the first real game there.

Why Sandbox
-----------
In a real game the motion tracer has to ignore everything around our towers
(their projectiles move too), which is exactly where the defended track runs,
and Fast Track skips the early rounds it used to learn from. Models came out
with whole lanes missing and with animated scenery in the corners, which led to
bad placements (a spike factory in an empty corner). Sandbox has no towers,
infinite lives and costs nothing, so the bloons can be watched on their own.

How it works (roughly 1-2 minutes, once per map)
------------------------------------------------
1. Open the map in a difficulty whose Sandbox this save has unlocked.
2. Keep a per-pixel background colour that slowly follows the scene, so slow
   changes (water colour cycling, lighting, cloud shadows) are absorbed. A
   bloon is a pixel whose colour suddenly differs from that background.
3. Watch the empty field first, and again after every round: how often each
   grid cell lights up with no bloons around is its "scenery rate" (water
   ripples, swaying trees, seasonal bats and props).
4. Send a few rounds chosen from data/rounds.json (short rounds of fast,
   brightly coloured bloons; different odd/even/mod-3/mod-4/prime numbers so
   maps that switch lanes by round number show every lane). Stop early once a
   round adds almost no new track.
5. Keep only cells lit clearly more often during rounds than their scenery
   rate explains. Save heat (where bloons go) and progress (how far along the
   track each cell is); in-game tracing is then switched off for this map.

Nothing here is specific to one map, so maps added to the game later are
learned the same way.
"""
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from .maplearn import GRID, MapModel, PathTracer
from .status import set_state
from .vision import norm

log = logging.getLogger("tracklearn")

DATA = Path(__file__).resolve().parents[1] / "data"

LEARNED_ROUNDS = 25     # in-game tracing stops once a model has this many rounds
MIN_ROUNDS = 3          # always trace at least this many rounds
MAX_ROUNDS = 5
NEW_CELLS_DONE = 0.04   # then stop when a round adds less than 4% new track cells
CLEAR_SECONDS = 1.5     # field empty this long = every bloon has left
TYPICAL_RED_CROSSING = 40.0  # s for a Red Bloon to cross an average map at 1x;
                             # only used to rank rounds against each other

# Which medal unlocks each difficulty's Sandbox (seen on the mode screens,
# 2026-10-21): Easy after Easy, Medium only after Reverse, Hard after Hard.
# A locked Sandbox shows a padlock and ignores clicks.
SANDBOX_UNLOCKED_BY = (("easy", "easy"), ("hard", "hard"), ("medium", "reverse"))


# ---------------------------------------------------------------------------
# Choosing which rounds to send
# ---------------------------------------------------------------------------

def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _is_prime(n):
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


def round_properties(r):
    """What a lane-switching map might key its lanes on."""
    return {("mod2", r % 2), ("mod3", r % 3), ("mod4", r % 4), ("prime", _is_prime(r))}


def round_kinds(r):
    """Bloon types in standard round r (from data/rounds.json)."""
    groups = _load("rounds.json")["standard"].get(str(r), {}).get("groups") or []
    return sorted({g["bloon"] for g in groups})


def choose_rounds(max_rounds=MAX_ROUNDS, last_round=40, colour_share=None):
    """Rounds to send, best first: short, fast, brightly coloured, and together
    covering as many round-number patterns (parity, mod 3, mod 4, primes) as
    possible. Computed from data/rounds.json and data/bloons.json.

    colour_share: {bloon type: fraction of the map already that colour}; a
    round whose bloons blend into the map costs more (yellow on a sand map)."""
    colour_share = colour_share or {}
    rounds = _load("rounds.json")["standard"]
    bloons = _load("bloons.json")["bloons"]
    cost = {}
    for key, rd in rounds.items():
        r = int(key)
        groups = rd.get("groups") or []
        if not groups or r > last_round:
            continue
        kinds = [g["bloon"] for g in groups]
        if not all(bloons.get(k, {}).get("bright") for k in kinds):
            continue  # dark/white/lead/purple bloons are hard to see on some maps
        spawn = max(g["end_s"] for g in groups)
        slowest = min(bloons[k]["speed"] for k in kinds)
        blend = max(colour_share.get(k, 0.0) for k in kinds)
        # time until the round clears, x up to 3 when its colour is all over the map
        cost[r] = (spawn + TYPICAL_RED_CROSSING / slowest) * (1 + 20 * min(blend, 0.1))
    chosen, covered = [], set()
    while cost and len(chosen) < max_rounds:
        # the cheapest round that still shows a new pattern (any round once all are seen)
        fresh = [r for r in cost if r not in chosen and round_properties(r) - covered]
        pool = fresh or [r for r in cost if r not in chosen]
        if not pool:
            break
        best = min(pool, key=lambda r: cost[r])
        chosen.append(best)
        covered |= round_properties(best)
    return chosen


def round_timeout(r):
    """Seconds to wait for a sent round at 2x before giving up on it."""
    groups = _load("rounds.json")["standard"].get(str(r), {}).get("groups") or []
    spawn = max((g["end_s"] for g in groups), default=20)
    return spawn / 2 + 30


# ---------------------------------------------------------------------------
# Seeing bloons
# ---------------------------------------------------------------------------

class SandboxTracer(PathTracer):
    """Finds the bloons that were sent by their colour.

    Each bright bloon type has a known body hue (data/bloons.json). A pixel is
    a bloon of type K when it has K's hue, is vivid, and was not like that a
    moment ago (the background follows the scene slowly, so pulsing water,
    lighting and shadows are absorbed). Scenery that flickers in K's hue with
    no bloons around is measured per colour and subtracted at the end."""

    # HUD readouts that change while bloons run (lives, cash, round counter,
    # the "FAST TRACK ENABLED" banner): (x0, y0, x1, y1) screen fractions
    HUD_ZONES = ((0.0, 0.0, 0.34, 0.13), (0.62, 0.0, 0.86, 0.17))
    BG_RATE = 0.03        # background follows the scene over ~1-2 s of frames
    COLOUR_DIFF = 0.12    # chromaticity distance that counts as "something new"
    MIN_SAT, MIN_VAL = 120, 130   # bloon bodies are vivid and well lit
    SCENERY_RATE = 0.02   # lit in >2% of empty-field frames = scenery
    STILL_SECONDS = 1.5   # nothing stops a bloon in Sandbox (no towers): a pixel
                          # "changed" this long is the scene changing, not a bloon

    def __init__(self, model, bloons):
        super().__init__(model, region_mask=self._hud_mask(model))
        # bloon type -> list of (low, high) OpenCV hue ranges
        self.hues = {k: v["hue"] for k, v in bloons.items() if v.get("bright") and v.get("hue")}
        self.bg = None                      # background chromaticity
        self._changed_since = None          # per pixel: time it started differing
        shape = model.heat.shape
        self.idle_hits = {k: np.zeros(shape, np.float32) for k in self.hues}
        self.idle_frames = 0
        self.expected = np.zeros(shape, np.float32)  # scenery hits expected in rounds
        self.kinds = list(self.hues)        # colours to look for this round
        self._round_frames = 0
        self._scenery = np.zeros(shape, bool)

    @classmethod
    def _hud_mask(cls, model):
        """Grid mask: True where tracing is allowed (outside the HUD zones)."""
        w, h = GRID
        keep = np.ones((h, w), bool)
        px0, py0, px1, py1 = model.playfield
        for x0, y0, x1, y1 in cls.HUD_ZONES:
            # screen fractions -> play-field grid cells
            cx0 = int(np.clip((x0 - px0) / (px1 - px0), 0, 1) * w)
            cx1 = int(np.ceil(np.clip((x1 - px0) / (px1 - px0), 0, 1) * w))
            cy0 = int(np.clip((y0 - py0) / (py1 - py0), 0, 1) * h)
            cy1 = int(np.ceil(np.clip((y1 - py0) / (py1 - py0), 0, 1) * h))
            keep[cy0:cy1, cx0:cx1] = False
        return keep

    @staticmethod
    def _chroma(img):
        """Per-pixel colour with brightness divided out (r, g, b sum to 1)."""
        f = img.astype(np.float32) + 1.0
        return f / f.sum(axis=2, keepdims=True)

    def _hue_mask(self, h, kind):
        m = np.zeros(h.shape, bool)
        for lo, hi in self.hues[kind]:
            m |= (h >= lo) & (h <= hi)
        return m

    def _detect(self, frame):
        """{bloon type: grid cells (bool) holding something new of that colour}.
        Also moves the background towards this frame."""
        cur = self._small(frame)
        chroma = self._chroma(cur)
        if self.bg is None:
            self.bg = chroma
            return {k: np.zeros(self.m.heat.shape, bool) for k in self.hues}
        changed = np.abs(chroma - self.bg).sum(axis=2) > self.COLOUR_DIFF
        # A pixel that keeps differing is the scene itself changing (water
        # cycling colour, a prop switching on): adopt it as background.
        now = time.time()
        if self._changed_since is None:
            self._changed_since = np.full(changed.shape, np.inf)
        self._changed_since[~changed] = np.inf
        self._changed_since[changed & np.isinf(self._changed_since)] = now
        stuck = changed & (now - self._changed_since > self.STILL_SECONDS)
        self.bg[stuck] = chroma[stuck]
        self._changed_since[stuck] = np.inf
        changed &= ~stuck
        calm = ~changed
        self.bg[calm] += self.BG_RATE * (chroma[calm] - self.bg[calm])

        hsv = cv2.cvtColor(cur, cv2.COLOR_BGR2HSV)
        vivid = changed & (hsv[..., 1] > self.MIN_SAT) & (hsv[..., 2] > self.MIN_VAL)
        out = {}
        for kind in self.hues:
            pix = (vivid & self._hue_mask(hsv[..., 0], kind)).astype(np.uint8)
            pix = cv2.morphologyEx(pix, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
            cells = cv2.resize(pix.astype(np.float32), GRID, interpolation=cv2.INTER_AREA) > 0.08
            out[kind] = cells & self.region_mask
        return out

    def colour_share(self, frame):
        """Fraction of the field already showing each bloon colour (vivid).
        Rounds whose bloons blend into the map are avoided."""
        hsv = cv2.cvtColor(self._small(frame), cv2.COLOR_BGR2HSV)
        vivid = (hsv[..., 1] > self.MIN_SAT) & (hsv[..., 2] > self.MIN_VAL)
        return {k: float((vivid & self._hue_mask(hsv[..., 0], k)).mean()) for k in self.hues}

    def warm_up(self, frames):
        """Let the background settle on the empty field."""
        for f in frames:
            self._detect(f)

    def feed_idle(self, frame):
        """A frame with no bloons on the field: anything lit is scenery."""
        for kind, cells in self._detect(frame).items():
            self.idle_hits[kind] += cells
        self.idle_frames += 1

    def _idle_rate(self, kinds):
        """Per cell: how often scenery lights up in any of these colours."""
        rate = sum(self.idle_hits[k] for k in kinds) / max(self.idle_frames, 1)
        return np.minimum(rate, 1.0)

    def start_round(self, kinds=None):
        super().start_round()
        self.kinds = [k for k in (kinds or self.hues) if k in self.hues] or list(self.hues)
        self._round_frames = 0
        if self.idle_frames >= 5:
            noisy = self._idle_rate(self.kinds) > self.SCENERY_RATE
            self._scenery = cv2.dilate(noisy.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    def feed_count(self, frame):
        """A frame while a round runs. Returns the number of non-scenery cells
        holding one of this round's colours (0 when the field looks empty)."""
        found = self._detect(frame)
        cells = np.zeros(self.m.heat.shape, bool)
        for k in self.kinds:
            cells |= found[k]
        if cells.mean() > 0.25:
            return 1  # screen transition / popup: neither track nor 'clear'
        self._round_frames += 1
        self.m.heat[cells] += 1
        newly = cells & np.isnan(self.first_seen)
        self.first_seen[newly] = time.time() - self.t0
        n = int((cells & ~self._scenery).sum())
        return n if n > 2 else 0

    def end_round(self):
        super().end_round()
        # scenery hits this round would have produced on its own
        self.expected += self._idle_rate(self.kinds) * self._round_frames

    def clean(self):
        """Keep cells lit clearly more often in rounds than scenery explains."""
        excess = self.m.heat - self.expected
        positive = excess[excess > 0]
        floor = max(3.0, 0.05 * float(np.percentile(positive, 99))) if positive.size else 3.0
        noise = excess < floor
        for arr in (self.m.heat, self.m.t_sum, self.m.t_cnt):
            arr[noise] = 0


# ---------------------------------------------------------------------------
# Driving Sandbox
# ---------------------------------------------------------------------------

def sandbox_difficulty(account, map_name):
    """A difficulty whose Sandbox this save has unlocked on the map, or None."""
    for diff, medal in SANDBOX_UNLOCKED_BY:
        if account.has_medal(map_name, medal):
            return diff
    return None


def needs_sandbox(model):
    """True until the map's track is known cleanly: read from the game's map
    files (mapgeom) or learned in Sandbox."""
    return not (getattr(model, "geometry_bundle", None) or getattr(model, "sandbox_rounds", 0))


def learn_track(bot, map_name, max_seconds=240):
    """Main menu -> map -> Sandbox -> trace -> main menu. True when saved."""
    from .game import Game
    diff = sandbox_difficulty(bot.account, map_name)
    if diff is None:
        log.info("sandbox: no Sandbox unlocked on %s yet - skipping", map_name)
        return False
    set_state(f"first visit to {map_name}: learning its track in Sandbox")
    if not _enter_sandbox(bot, map_name, diff):
        bot.to_main_menu()
        return False
    g = Game(bot.s, bot.inp, bot.lay, difficulty=diff, hero=None)
    try:
        return _trace(bot, g, map_name, max_seconds)
    finally:
        _leave(bot, g)


def _enter_sandbox(bot, map_name, diff):
    """Map select -> difficulty -> Sandbox -> dismiss the intro popup."""
    from .game import Game
    from .menus import page_forbidden
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
        return False
    bot.menus.read()
    if not bot.menus.click_word("sandbox", dy=-0.08):
        log.warning("sandbox: no Sandbox button")
        return False
    g = Game(bot.s, bot.inp, bot.lay, difficulty=diff, hero=None)
    # The mode screen first fades out (its "Monkeys cost ..." text next to
    # "$25" rewards looks like a price offer, so judge only after it is gone),
    # then a "SANDBOX MODE ... OK" intro pops up over the map.
    end = time.time() + 25
    while time.time() < end:
        time.sleep(0.8)
        if bot.menus.identify() == "mode_select":
            continue
        if bot.menus.has("sandboxmode"):
            bot.menus.click_word("ok")
            continue
        if page_forbidden(bot.menus.words):  # safety net: never buy anything
            log.warning("sandbox: %s Sandbox offered for purchase - backing out", diff)
            return False
        if g.in_game():
            return True
    log.warning("sandbox: game screen did not appear")
    return False


class SandboxPanel:
    """Where to type a round number and the button that sends it.

    Found on screen from the "SET ROUND:" label: the number box sits under it
    and the green send button to its right. The fallback positions were
    measured live (2026-10-21, 1920x1200) and are used only if OCR misses."""
    FALLBACK_FIELD = (0.903, 0.098)
    FALLBACK_SEND = (0.962, 0.085)

    def __init__(self, bot):
        self.field, self.send = self.FALLBACK_FIELD, self.FALLBACK_SEND
        words = bot.menus.read()
        label = next((w for w in words if "setround" in norm(w.text)), None)
        if label is None:
            log.info("sandbox: SET ROUND label not found - using measured positions")
            return
        below = [w for w in words if abs(w.x - label.x) < 0.04 and 0.01 < w.y - label.y < 0.06]
        self.field = (below[0].x, below[0].y) if below else (label.x, label.y + 0.031)
        self.send = self._green_button(bot.s.grab(), label) or (label.x + 0.059, label.y + 0.018)

    @staticmethod
    def _green_button(frame, label):
        """Centre of the bright green button right of the label, or None."""
        hh, ww = frame.shape[:2]
        x0, x1 = int((label.x + 0.02) * ww), int(min(1.0, label.x + 0.11) * ww)
        y0, y1 = int(max(0.0, label.y - 0.05) * hh), int((label.y + 0.07) * hh)
        hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (40, 150, 150), (80, 255, 255))
        ys, xs = np.nonzero(green)
        if xs.size < 200:
            return None
        return ((x0 + xs.mean()) / ww, (y0 + ys.mean()) / hh)

    def send_round(self, bot, rnd):
        """Type the round number into the box and send that round's bloons."""
        bot.inp.click(*self.field)
        time.sleep(0.3)
        for _ in range(4):
            bot.inp.press("backspace")
        bot.inp.type_text(str(rnd))
        time.sleep(0.2)
        bot.inp.click(*self.send)
        time.sleep(0.4)


def _trace(bot, g, map_name, max_seconds):
    """Send rounds and trace them; save the model if the result is sane."""
    model = MapModel.load(map_name, bot.lay["playfield"])
    for arr in (model.heat, model.t_sum, model.t_cnt):
        arr[:] = 0
    model.rounds_traced = 0
    tracer = SandboxTracer(model, _load("bloons.json")["bloons"])
    t_start = time.time()

    _wait_still(g)
    tracer.warm_up([g.fresh() for _ in range(10)])
    _idle(g, tracer, 3.0)
    share = tracer.colour_share(g.fresh())
    rounds = choose_rounds(colour_share=share)
    log.info("sandbox: map colours %s -> rounds %s",
             {k: round(v, 3) for k, v in share.items()}, rounds)
    panel = SandboxPanel(bot)
    _fast(bot, g)

    prev_cells = 0
    for i, rnd in enumerate(rounds):
        if time.time() - t_start > max_seconds:
            break
        set_state(f"learning the track of {map_name} in Sandbox: round {rnd}")
        panel.send_round(bot, rnd)
        tracer.start_round(round_kinds(rnd))
        cleared = _run_until_clear(bot, g, tracer, round_timeout(rnd))
        tracer.end_round()
        if cleared:
            _idle(g, tracer, 1.0)  # field empty again: sample the scenery
        cells = int((model.heat > 0).sum())
        grew = (cells - prev_cells) / max(cells, 1)
        log.info("sandbox: round %d -> %d cells (+%.0f%%)%s", rnd, cells, grew * 100,
                 "" if cleared else " (did not clear)")
        prev_cells = cells
        if i + 1 >= MIN_ROUNDS and grew < NEW_CELLS_DONE:
            break  # nothing new: every lane has been seen

    tracer.clean()
    cells = int((model.heat > 0).sum())
    frac = cells / model.heat.size
    if model.rounds_traced >= MIN_ROUNDS and cells > 150 and frac < 0.45:
        model.sandbox_rounds = model.rounds_traced
        model.rounds_traced = max(model.rounds_traced, LEARNED_ROUNDS)
        model.save()
        log.info("sandbox: %s learned in %.0f s (%d cells, %.0f%% of the map)",
                 map_name, time.time() - t_start, cells, frac * 100)
        return True
    log.warning("sandbox: unusable trace on %s (%d rounds, %.0f%% of the map) - not saved",
                map_name, model.rounds_traced, frac * 100)
    return False


def _run_until_clear(bot, g, tracer, timeout):
    """Feed frames until the field has been empty for CLEAR_SECONDS.
    True when it cleared, False on timeout."""
    t_round = time.time()
    clear_since = None
    while time.time() - t_round < timeout:
        f = g.fresh()
        if not g.in_game(f):
            bot.menus.dismiss_popup()
            time.sleep(0.5)
            continue
        if tracer.feed_count(f):
            clear_since = None
        else:
            clear_since = clear_since or time.time()
            if time.time() - t_round > 3 and time.time() - clear_since > CLEAR_SECONDS:
                return True
    return False


def _wait_still(g, timeout=8.0):
    """Wait until consecutive frames barely differ (fades/popups finished)."""
    prev = None
    still = 0
    end = time.time() + timeout
    while time.time() < end and still < 3:
        cur = cv2.resize(g.fresh(), (240, 150), interpolation=cv2.INTER_AREA).astype(np.int16)
        if prev is not None and np.abs(cur - prev).mean() < 1.5:
            still += 1
        else:
            still = 0
        prev = cur
        time.sleep(0.3)


def _fast(bot, g):
    """Turn on 2x speed (the bottom-right button is a toggle in Sandbox)."""
    for _ in range(2):
        if g.button_state() == "play_fast":
            return
        bot.inp.click(*bot.lay["play_button"])
        time.sleep(0.5)


def _idle(g, tracer, seconds):
    """Sample the empty field for `seconds` (scenery that moves by itself)."""
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
