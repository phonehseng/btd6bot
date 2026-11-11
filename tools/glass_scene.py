"""The glass HUD's pictures: a few small see-through widgets, each drawn as
an RGBA image with Pillow.

No window here. GlassScene.widgets() turns a hud_data.Snapshot into named
widgets, each with a key and a build(); build() returns a Picture (the
widget's image, its soft shadow included, and where its top-left corner
goes on the screen) or None when the widget is hidden. tools/glass_hud.py
pushes each Picture into its own per-pixel-alpha window (only when the key
changed), tools/hud_preview.py composites them over a game frame, and the
tests check where they sit.

The look is "liquid glass": a dark tint at roughly 35-50 % alpha with a soft
vertical gradient, a gloss over the top, a 1 px light rim brightest along
the top edge, rounded corners and a faint shadow around it. Text is crisp,
anti-aliased and carries a faint shadow so it reads over bright maps. The
game behind is not blurred (capturing the screen would cost too much on a
laptop that also runs the bot and BTD6).

What shows where (fractions of a 16:10 screen, BTD6's own UI avoided):

  always      a slim status PILL at the top centre (map, mode, round, what
              the bot is doing, a heartbeat dot and how long ago it last did
              anything), the STOP / GO / OFF buttons right of it, and under
              it a faint THOUGHTS card with the newest bot.log lines
              (switched off with a HUD_NO_THOUGHTS file in the repo root or
              BTD6BOT_HUD_THOUGHTS=off)
  in a game   two cards along the bottom edge, between the ability buttons
              (bottom left) and the tower shop: NEXT ROUNDS (the damage
              model's margin per coming round, coloured by danger, and what
              is at risk) and DECISION (the latest purchase and why, what
              reinforce saves for or what the build wants next); over the
              field thin, faint GHOSTS where the build still wants towers,
              and under them the FIELD layer (tools/glass_field.py): the
              ground the bot may place on, its learned refusals and the
              bloon paths with their direction (switched off with a
              HUD_NO_FIELD file in the repo root or BTD6BOT_HUD_FIELD=off)
  in menus    a PICK card (the planner's choice, its chance, its reasons and
              two runner-ups) and a PROGRESS card (black borders, CHIMPS
              wins and medals) at the right edge

Cheap on purpose: the glass backgrounds are cached per size, a widget is
rebuilt only when its key changes, and only the pill animates (its heartbeat
at PILL_FPS frames a second).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import hud_scene as S                   # the big HUD's colours and meanings, shared
from hud_data import LEAK_MARGIN, project
from btd6bot.layout import LAYOUTS      # importable once hud_data has put the repo on sys.path

# -- colours (the big HUD's meaning colours, as RGB) ----------------------------------------


def rgb(colour):
    """'#rrggbb' -> (r, g, b)."""
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def ink(colour, alpha=1.0):
    """'#rrggbb' (or an (r, g, b) tuple) and an opacity 0..1 -> an RGBA fill."""
    c = rgb(colour) if isinstance(colour, str) else tuple(colour)
    return c + (round(255 * max(0.0, min(1.0, alpha))),)


TEXT, DIM, FAINT = S.TEXT, "#a4adbd", "#6b7588"   # DIM and FAINT a little lighter than the big HUD's: thinner glass
GOOD, WARN, BAD, INFO, GHOST, GOLD, CHIMPS = S.GOOD, S.WARN, S.BAD, S.INFO, S.GHOST, S.GOLD, S.CHIMPS
SOURCE_COLOURS = S.SOURCE_COLOURS

# -- the glass ---------------------------------------------------------------------------
TINT = (10, 14, 24)          # the glass's dark blue-black
TINT_TOP_ALPHA = 0.52        # the tint's opacity at the top of a panel ...
TINT_BOTTOM_ALPHA = 0.40     # ... and at the bottom: a soft vertical gradient
HELD_TINT = (48, 10, 14)     # the pill's tint while the bot is stopped (HOLD)
SHEEN_ALPHA = 0.10           # a white gloss fading out over the top ...
SHEEN_DEPTH = 0.45           # ... share of the panel's height
RIM_ALPHA = 0.16             # the 1 px light rim round the panel ...
HIGHLIGHT_ALPHA = 0.55       # ... brightest along the top edge
SHADOW_ALPHA = 0.32          # the soft shadow round a panel
TEXT_HALO_ALPHA = 0.85       # a soft dark halo round text: it reads over bright maps
TEXT_HALO_PX = 1.6           # ... its blur radius at BASE_HEIGHT
SUPERSAMPLE = 3              # rounded corners are drawn this much larger and scaled down: smooth edges

# -- sizes in pixels on a BASE_HEIGHT tall screen (they scale with the screen) --------------
BASE_HEIGHT = S.BASE_HEIGHT  # 1200
# Every size below is drawn this much bigger (owner, 2026-11-11: "make everything
# a little bigger"): fonts, padding, corners and heights all follow Layout.u.
UI_SCALE = 1.2
RADIUS = 14                  # corner radius of a card
PILL_RADIUS = 18             # the pill is fully round at its ends
SHADOW = 10                  # room round a panel for its shadow
EDGE = 6                     # gap between a widget and the screen's edge
GAP = 12                     # gap between two widgets
PAD = 12                     # inner padding of a card
PILL_TOP, PILL_H = 4, 38
PILL_PX = 16                 # the pill's text
THOUGHT_PX, THOUGHT_LINES = 13, 3
# (the bottom cards in a game have no fixed height: they fill the room under an open
# upgrade panel, about 110 px at 1200 - Layout._bottom)
TITLE_PX, BODY_PX, SMALL_PX, TINY_PX = 12, 17, 14, 12
PICK_H, PROGRESS_H = 222, 146     # the PICK card at most (it shrinks to what it says)
MIN_PX = 8                   # no text smaller than this, however small the screen

# -- placement (fractions of the screen) -----------------------------------------------------
PILL_WIDTH = 0.25            # the pill's share of the screen width
ROUNDS_WIDTH = 0.20          # the NEXT ROUNDS card
DECISION_WIDTH = 0.30        # the DECISION card
MENU_X0 = 0.86               # the menu cards' left edge: right of the map-select cards (which end at 0.846)
MENU_TOP = 0.14              # ... below the menus' top-right buttons (cash, friends)
BUTTON_PANEL_WIDTH = 270     # hud_controls.ButtonPanel's width (not scaled, as there)
BUTTON_GAP = 6               # hud_controls.BUTTON_GAP

# BTD6's own UI in a game (16:10), from the bot's calibrated layout
# (btd6bot/layout.py) where it has the element; the ability row has no
# entry there and was measured on a 1920x1200 frame: activated abilities
# and the power button start at the bottom left and grow to the right.
ABILITY_ROW = (0.0, 0.86, 0.33, 0.96)
MIDDLE_OF_FIELD = (0.15, 0.2, 0.7, 0.8)   # where no widget may ever sit (ghosts and the field layer aside)

# -- motion ----------------------------------------------------------------------------------
PILL_FPS = 4                 # heartbeat frames a second (the only animation)
BEAT_ACTIVE_S, BEAT_QUIET_S = 1.0, 2.5    # heartbeat period while the bot is busy / quiet

# -- content ------------------------------------------------------------------------------------
ROUND_BARS = 8               # coming rounds in the NEXT ROUNDS card
MARGIN_CAP = S.MARGIN_CAP    # margins above this are drawn full height
MAX_GHOSTS = S.MAX_GHOSTS
RUNNER_UPS = 2
PICK_NOTES = 2
PICK_MAP_PX = 19             # the picked map's name
GHOST_FILL_ALPHA = 0.14      # an unplaced ghost's body
GHOST_EDGE_ALPHA = 0.55      # ... its outline
GHOST_RANGE_ALPHA = 0.22     # ... its range ring (dotted)
GHOST_RING_ALPHA = 0.45      # a standing tower the plan still upgrades
GHOST_LABEL_ALPHA = 0.85

FONT_DIR = Path(r"C:\Windows\Fonts")
FONT_FILES = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf", "mono": "consola.ttf"}


def game_ui_zones():
    """{name: (x0, y0, x1, y1)} in screen fractions: where BTD6 draws its
    own UI during a game (16:10). The glass widgets stay out of these."""
    lay = LAYOUTS["16:10"]
    pf = lay["playfield"]
    return {"lives and cash": (0.0, 0.0, lay["cash"][2], lay["cash"][3]),
            "round and settings": (lay["round"][0], 0.0, pf[2], lay["round"][3]),
            "tower shop": (pf[2], 0.0, 1.0, 1.0),       # upgrades button, towers, play / fast forward
            "abilities": ABILITY_ROW}


def upgrade_panel_box():
    """The upgrade panel (opened by selecting a tower) as screen fractions;
    the bottom cards stay below it."""
    return LAYOUTS["16:10"]["upg_right"]["box"]


# -- drawing helpers -----------------------------------------------------------------------------

@lru_cache(maxsize=64)
def font(style, px):
    """A Segoe UI / Consolas font at `px` pixels (Pillow's own font where
    Windows' fonts are missing)."""
    px = max(MIN_PX, int(round(px)))
    try:
        return ImageFont.truetype(str(FONT_DIR / FONT_FILES[style]), px)
    except OSError:
        return ImageFont.load_default(px)


def fit(s, f, width):
    """`s` cut (with an ellipsis) to fit `width` pixels in font `f`."""
    s = str(s)
    if f.getlength(s) <= width:
        return s
    lo, hi = 0, len(s)
    while lo < hi:                               # the longest prefix that fits with the ellipsis
        mid = (lo + hi + 1) // 2
        if f.getlength(s[:mid].rstrip() + "…") <= width:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip() + "…" if lo else ""


def wrap(s, f, width, max_lines):
    """`s` broken into at most `max_lines` lines of `width` pixels in font `f`
    (the last one cut with an ellipsis when the text runs on)."""
    words, lines, cur = str(s).split(), [], ""
    for i, word in enumerate(words):
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
            continue
        lines.append(cur)
        cur = word
        if len(lines) == max_lines:
            lines[-1] = fit(lines[-1] + " " + " ".join(words[i:]), f, width)
            return lines
    if cur:
        lines.append(fit(cur, f, width))
    return lines[:max_lines] or [""]


def rounded_mask(w, h, radius, inset=0):
    """An anti-aliased rounded-rectangle mask ("L") of w x h, `inset` pixels in."""
    k = SUPERSAMPLE
    m = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((inset * k, inset * k, w * k - 1 - inset * k, h * k - 1 - inset * k),
                                        max(0, radius - inset) * k, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def vertical(h, w, top, bottom, depth=1.0):
    """An "L" image w x h whose value runs from `top` to `bottom` (0..255)
    over the top `depth` share of the height, then stays at `bottom`."""
    end = max(1, int(h * depth))
    col = Image.new("L", (1, h), 0)
    col.putdata([round(top + (bottom - top) * min(1.0, y / max(1, end - 1))) for y in range(h)])
    return col.resize((w, h))


@lru_cache(maxsize=48)
def glass(w, h, radius, shadow, tint=TINT, opacity=1.0, accent=None):
    """A glass panel w x h (body) inside a transparent margin of `shadow`
    pixels for its shadow: RGBA of (w + 2 shadow) x (h + 2 shadow).
    `opacity` scales the whole panel (the faint thoughts card); `accent`
    (an RGB tuple) adds a thin coloured bar inside the left edge."""
    W, H = w + 2 * shadow, h + 2 * shadow
    body_mask = rounded_mask(w, h, radius)
    # the shadow: the panel's shape a little lower, blurred, kept outside the body
    sh = Image.new("L", (W, H), 0)
    drop = max(1, shadow // 4)                   # the shadow falls a little below the panel
    sh.paste(round(255 * SHADOW_ALPHA * opacity), (shadow, shadow + drop, shadow + w, shadow + drop + h), body_mask)
    if shadow:
        sh = sh.filter(ImageFilter.GaussianBlur(shadow / 2))
    cut = Image.new("L", (W, H), 0)
    cut.paste(body_mask, (shadow, shadow))
    sh = ImageChops.subtract(sh, cut)
    out = Image.merge("RGBA", (Image.new("L", (W, H), 0),) * 3 + (sh,))
    # the body: the tint with its vertical gradient
    alpha = vertical(h, w, 255 * TINT_TOP_ALPHA * opacity, 255 * TINT_BOTTOM_ALPHA * opacity)
    body = Image.new("RGBA", (w, h), tint + (0,))
    body.putalpha(ImageChops.multiply(alpha, body_mask))
    # the gloss over the top
    sheen = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    sheen.putalpha(ImageChops.multiply(vertical(h, w, 255 * SHEEN_ALPHA * opacity, 0, SHEEN_DEPTH), body_mask))
    body.alpha_composite(sheen)
    # the rim: a 1 px ring, brightest along the top
    ring = ImageChops.subtract(body_mask, rounded_mask(w, h, radius, inset=1))
    rim_alpha = vertical(h, w, 255 * HIGHLIGHT_ALPHA * opacity, 255 * RIM_ALPHA * opacity, 0.5)
    rim = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    rim.putalpha(ImageChops.multiply(rim_alpha, ring))
    body.alpha_composite(rim)
    if accent:
        bar_w = max(2, round(radius / 4.5))
        bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle((bar_w, radius * 0.7, 2 * bar_w, h - radius * 0.7), bar_w,
                                              fill=tuple(accent) + (round(230 * opacity),))
        body.alpha_composite(bar)
    out.alpha_composite(body, (shadow, shadow))
    return out


@dataclass
class Picture:
    """A widget ready for the screen: its RGBA image (shadow margin
    included) and where the image's top-left corner goes."""
    image: Image.Image
    x: int
    y: int

    @property
    def rect(self):
        return self.x, self.y, self.x + self.image.width, self.y + self.image.height


class Card:
    """Drawing on one glass panel. Marks (bars, chips, dots) and text go on
    two transparent layers of their own, composited over the glass in that
    order, so text always sits on top with clean anti-aliased edges.
    Coordinates are relative to the body's top-left corner."""

    def __init__(self, lay, rect, radius=RADIUS, tint=TINT, opacity=1.0, accent=None):
        self.lay = lay
        self.rect = tuple(int(round(v)) for v in rect)
        x0, y0, x1, y1 = self.rect
        self.w, self.h = x1 - x0, y1 - y0
        self.m = lay.px(SHADOW)
        self.base = glass(self.w, self.h, lay.px(radius), self.m, tint, opacity, accent)   # cached: never drawn on
        self.opacity = opacity
        self._marks = self._text = None

    @property
    def marks(self):
        """An ImageDraw on the marks layer (created on first use)."""
        if self._marks is None:
            self._marks = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
            self._marks_draw = ImageDraw.Draw(self._marks)
        return self._marks_draw

    def at(self, x, y):
        """Body coordinates -> image coordinates."""
        return x + self.m, y + self.m

    def box(self, x0, y0, x1, y1):
        return (*self.at(x0, y0), *self.at(x1, y1))

    def text(self, x, y, s, f, colour=TEXT, alpha=1.0, anchor="la"):
        """Text (Pillow anchors: 'la', 'lm', 'mm', 'rm', ...), its halo
        added in picture(); returns its width in pixels."""
        if not s:
            return 0
        if self._text is None:
            self._text = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
            self._text_draw = ImageDraw.Draw(self._text)
        # Text is always fully opaque (owner, 2026-11-11): a dimmer line is the
        # colour mixed toward the glass's tint instead of made see-through, so
        # the hierarchy stays while the map never shows through the letters.
        a = max(0.0, min(1.0, alpha * self.opacity))
        base = rgb(colour) if isinstance(colour, str) else tuple(colour)[:3]
        mixed = tuple(round(c * a + t * (1 - a)) for c, t in zip(base, TINT))
        self._text_draw.text(self.at(x, y), s, font=f, fill=mixed + (255,), anchor=anchor)
        return f.getlength(s)

    def picture(self):
        """The glass with its marks and text, placed so the body lands on its rect."""
        img = self.base.copy()
        if self._marks is not None:
            img.alpha_composite(self._marks)
        if self._text is not None:
            # the halo: the text's own shape, blurred, in black - under the text
            halo = self._text.getchannel("A").filter(ImageFilter.GaussianBlur(self.lay.fpx(TEXT_HALO_PX)))
            halo = halo.point(lambda a: min(255, round(a * 2 * TEXT_HALO_ALPHA * self.opacity)))
            img.alpha_composite(Image.merge("RGBA", (Image.new("L", img.size, 0),) * 3 + (halo,)))
            img.alpha_composite(self._text)
        x0, y0 = self.rect[:2]
        return Picture(img, x0 - self.m, y0 - self.m)


class Layout:
    """Where each widget's glass body sits on a w x h screen, as (x0, y0, x1, y1) pixels."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.u = h / BASE_HEIGHT * UI_SCALE

    def px(self, n):
        """A size given at BASE_HEIGHT, in whole pixels on this screen."""
        return max(1, int(round(n * self.u)))

    def fpx(self, n):
        """The same, unrounded (font sizes)."""
        return n * self.u

    # -- always ----------------------------------------------------------------------------
    @property
    def pill(self):
        """Top centre: the pill and the buttons right of it, centred in the
        gap between the game's cash and its round counter. The buttons do
        not scale, so on a small screen the pill gives up width to them."""
        lay = LAYOUTS["16:10"]
        room = self.w * (lay["round"][0] - lay["cash"][2]) - 2 * self.px(GAP)
        width = min(round(self.w * PILL_WIDTH), int(room) - BUTTON_GAP - BUTTON_PANEL_WIDTH)
        group = width + BUTTON_GAP + BUTTON_PANEL_WIDTH
        centre = self.w * (lay["cash"][2] + lay["round"][0]) / 2
        x0 = round(centre - group / 2)
        return x0, self.px(PILL_TOP), x0 + width, self.px(PILL_TOP) + self.px(PILL_H)

    @property
    def buttons(self):
        """The STOP / GO / OFF panel (hud_controls.ButtonPanel): right of the
        pill, from the screen's top to the pill's bottom."""
        x0, _y0, x1, y1 = self.pill
        return x1 + BUTTON_GAP, 0, x1 + BUTTON_GAP + BUTTON_PANEL_WIDTH, y1 + self.px(PILL_TOP)

    @property
    def thoughts(self):
        x0, _y0, x1, y1 = self.pill
        top = y1 + self.px(GAP) // 2
        return x0, top, x1, top + 2 * self.px(PAD) // 2 + THOUGHT_LINES * self.px(THOUGHT_PX * 1.35)

    # -- in a game ----------------------------------------------------------------------------
    def _bottom(self, width_share, right):
        """A bottom card `width_share` of the screen wide ending at `right`:
        from just below an open upgrade panel down to the screen's edge."""
        y0 = math.ceil(self.h * upgrade_panel_box()[3]) + self.px(EDGE) // 2
        return round(right - self.w * width_share), y0, right, self.h - self.px(EDGE)

    @property
    def decision(self):
        """Bottom edge, against the tower shop: right of the ability row."""
        right = round(self.w * LAYOUTS["16:10"]["playfield"][2]) - self.px(GAP)
        return self._bottom(DECISION_WIDTH, right)

    @property
    def rounds(self):
        return self._bottom(ROUNDS_WIDTH, self.decision[0] - self.px(GAP))

    # -- in menus --------------------------------------------------------------------------------
    def pick_rect(self, height=None):
        """The PICK card at the right edge, `height` tall (at most PICK_H)."""
        x0, x1 = round(self.w * MENU_X0), self.w - self.px(EDGE)
        y0 = round(self.h * MENU_TOP)
        return x0, y0, x1, y0 + min(self.px(PICK_H), height or self.px(PICK_H))

    def progress_rect(self, pick_height=None):
        """The PROGRESS card, right under a PICK card `pick_height` tall."""
        x0, _y0, x1, y1 = self.pick_rect(pick_height)
        return x0, y1 + self.px(GAP), x1, y1 + self.px(GAP) + self.px(PROGRESS_H)

    @property
    def pick(self):
        """The PICK card at its tallest."""
        return self.pick_rect()

    @property
    def progress(self):
        """The PROGRESS card at its lowest (under the tallest PICK card)."""
        return self.progress_rect()

    def rects(self, in_game, thoughts=True):
        """{widget: body rect} of the glass widgets shown in a game or in menus (ghosts aside)."""
        names = ["pill"] + (["thoughts"] if thoughts else []) + (["rounds", "decision"] if in_game
                                                                  else ["pick", "progress"])
        return {n: getattr(self, n) for n in names}


# -- what a widget says, as plain values (so a key is cheap and the picture follows it) ----------

def status_colour(snap):
    """The heartbeat's colour: green while the bot is busy, yellow when it
    has gone quiet, red when it is stopped or silent (as the old strip)."""
    if "HOLD" in snap.flags or (snap.quiet is not None and snap.quiet >= S.QUIET_WARN_S):
        return BAD
    return GOOD if snap.quiet is None or snap.quiet < S.QUIET_OK_S else WARN


def quiet_text(q):
    if q is None:
        return ""
    return f"{int(q)}s" if q < S.QUIET_OK_S else f"{int(q // 60)} min"


def mode_name(mode):
    """'half_cash' -> 'half cash'."""
    return str(mode or "").replace("_", " ")


def margin_colour(m, weak):
    return S.margin_colour(m, weak)


def worst_ahead(snap):
    """(round, margin) of the weakest coming round, or None."""
    return min(snap.margins_ahead, key=lambda p: p[1]) if snap.margins_ahead else None


def pick_of(snap):
    planner = snap.planner or {}
    return planner.get("pick") or snap.next


def chance(pick):
    """The planner's chance to win, from the pick (or the NEXT line's 'p=0.48' note)."""
    p = pick.get("p")
    if p is None:
        p = next((float(n[2:6]) for n in pick.get("notes", ()) if n.startswith("p=")), None)
    return p


def p_colour(p):
    return GOOD if p >= 0.8 else (WARN if p >= 0.6 else BAD)


class GlassScene:
    """Builds the widgets for a w x h screen. `field` is the FIELD layer
    (glass_field.FieldLayer: what the bot sees of the map, under the
    ghosts); None makes one reading this repo's learned models.
    show_field=False hides it (the owner's HUD_NO_FIELD switch)."""

    def __init__(self, w, h, thoughts=True, field=None, show_field=True):
        self.lay = Layout(w, h)
        self.show_thoughts = thoughts
        self.show_field = show_field
        self._field = field

    @property
    def field(self):
        """The field layer, made on first use (it imports numpy and OpenCV,
        which only a game needs)."""
        if self._field is None:
            import glass_field
            self._field = glass_field.FieldLayer()
        return self._field

    # -- the widgets ---------------------------------------------------------------------------
    def widgets(self, snap, now, game_rect=None):
        """[(name, key, build)]; build() -> Picture or None (hidden). A
        widget whose key did not change since it was last shown need not be
        built again."""
        g = snap.in_game
        newest = [(r.clock, r.level, r.source, r.text) for r in snap.log[-THOUGHT_LINES:]]
        decisions = snap.journal.decisions if snap.journal else []
        last = decisions[-1] if decisions else None
        pill_key = (g, snap.state, snap.flags, quiet_text(snap.quiet), status_colour(snap), snap.focus,
                    tuple((snap.game or {}).get(k) for k in ("map", "mode", "end_round")), snap.round,
                    int(now * PILL_FPS) % (PILL_FPS * 10))
        rounds_key = (tuple(snap.margins_ahead), tuple(snap.margins_past[-ROUND_BARS:]), snap.weak, snap.lives)
        decision_key = ((last.source, last.what, last.why, last.rnd) if last else None,
                        (snap.reinforce or {}).get("text"), snap.wishes[0].text() if snap.wishes else None,
                        len(snap.wishes), snap.hud.get("waiting"))
        planner = snap.planner or {}
        pick_key = (repr(pick_of(snap)), repr(planner.get("runner_ups")), planner.get("phase"))
        progress_key = (id(snap.board), snap.level, self._last_game(snap), pick_key)
        ghosts_key = (tuple((x.tid, x.kind, x.x, x.y, x.target, x.placed) for x in snap.ghosts[:MAX_GHOSTS]),
                      game_rect, tuple(sorted((k, tuple(v)) for k, v in snap.sizes.items())))
        hidden = ("hidden",)
        field_key = self.field.key(snap, game_rect) if g and game_rect and self.show_field else None
        return [
            # first, so a preview composites it under everything else (the HUD keeps its window lowest)
            ("field", ("field", field_key) if field_key is not None else hidden,
             lambda: self.field.picture(snap, game_rect) if field_key is not None else None),
            ("pill", pill_key, lambda: self.pill(snap, now)),
            ("thoughts", (tuple(newest), self.show_thoughts) if self.show_thoughts and newest else hidden,
             lambda: self.thoughts(snap) if self.show_thoughts else None),
            ("rounds", rounds_key if g else hidden, lambda: self.rounds(snap) if g else None),
            ("decision", decision_key if g else hidden, lambda: self.decision(snap) if g else None),
            ("pick", pick_key if not g else hidden, lambda: None if g else self.pick(snap)),
            ("progress", progress_key if not g else hidden, lambda: None if g else self.progress(snap)),
            ("ghosts", ghosts_key if g and game_rect and snap.ghosts else hidden,
             lambda: self.ghosts(snap, game_rect) if g and game_rect else None),
        ]

    def build_all(self, snap, now, game_rect=None):
        """{name: Picture} of every widget shown (previews and tests)."""
        out = {}
        for name, _key, build in self.widgets(snap, now, game_rect):
            pic = build()
            if pic is not None:
                out[name] = pic
        return out

    # -- the pill ---------------------------------------------------------------------------------
    def pill(self, snap, now):
        L = self.lay
        held = "HOLD" in snap.flags
        c = Card(L, L.pill, PILL_RADIUS, HELD_TINT if held else TINT)
        colour = status_colour(snap)
        # the heartbeat: a dot with a breathing glow
        beat = S.pulse(now, BEAT_ACTIVE_S if colour == GOOD else BEAT_QUIET_S)
        cx, cy = L.px(PILL_H) / 2 + L.px(2), c.h / 2
        r = L.fpx(3.5)
        glow = r * (1.8 + 1.2 * beat)
        c.marks.ellipse(c.box(cx - glow, cy - glow, cx + glow, cy + glow), fill=ink(colour, 0.18 + 0.2 * beat))
        c.marks.ellipse(c.box(cx - r, cy - r, cx + r, cy + r), fill=ink(colour))
        f = font("semibold", L.fpx(PILL_PX))
        small = font("regular", L.fpx(PILL_PX - 2))
        x = cx + glow + L.px(6)
        right_edge = c.w - L.px(PILL_H) / 2
        ago = quiet_text(snap.quiet)
        if ago:
            right_edge -= c.text(right_edge, cy, ago, small, colour, 0.9, "rm") + L.px(8)
        g = snap.game or {}
        if held:
            head = "STOPPED  -  press GO"
        elif snap.in_game:
            rnd = f"R{snap.round if snap.round is not None else '?'}" + (f"/{g['end_round']}" if g.get("end_round")
                                                                        else "")
            head = "  ·  ".join(str(v) for v in (g.get("map"), mode_name(g.get("mode")), rnd) if v)
        else:
            head = snap.state or "the bot has not said anything yet"
        flags = [{"PAUSE": "PAUSED", "STOP": "OFF"}[fl] for fl in snap.flags if fl != "HOLD"]
        head = "  ·  ".join([head] + flags)
        x += c.text(x, cy, fit(head, f, right_edge - x), f, BAD if held else TEXT, 1.0, "lm") + L.px(10)
        # what else fits: the XP focus in a game (in menus the head already is the bot's state)
        extra = (f"XP: {snap.focus}" if snap.focus else "") if snap.in_game else ""
        if extra and right_edge - x > L.px(40):
            c.text(x, cy, fit(extra, small, right_edge - x), small, WARN, 0.9, "lm")
        return c.picture()

    # -- the thoughts ---------------------------------------------------------------------------
    def thoughts(self, snap):
        if not snap.log:
            return None
        L = self.lay
        c = Card(L, L.thoughts, RADIUS, opacity=0.75)
        f = font("mono", L.fpx(THOUGHT_PX))
        step = L.px(THOUGHT_PX * 1.35)
        x, y = L.px(PAD), L.px(PAD) // 2 + step / 2
        recs = snap.log[-THOUGHT_LINES:]
        for i, rec in enumerate(recs):
            age = len(recs) - 1 - i                      # 0 = the newest
            colour = BAD if rec.level == "E" else (WARN if rec.level == "W" else TEXT)
            c.text(x, y, fit(f"{rec.clock[:5]} {rec.source}: {rec.text}", f, c.w - 2 * x), f, colour,
                   (0.95, 0.62, 0.42)[min(age, 2)], "lm")
            y += step
        return c.picture()

    # -- in a game: NEXT ROUNDS -----------------------------------------------------------------
    def rounds(self, snap):
        L = self.lay
        worst = worst_ahead(snap)
        risk = BAD if worst and worst[1] < LEAK_MARGIN else (WARN if worst and snap.weak and worst[1] < snap.weak
                                                            else None)
        c = Card(L, L.rounds, accent=rgb(risk) if risk else None)
        pad = L.px(PAD)
        title, tiny, small = font("semibold", L.fpx(TITLE_PX)), font("regular", L.fpx(TINY_PX)), \
            font("semibold", L.fpx(SMALL_PX))
        x0, x1 = pad + L.px(4), c.w - pad
        ahead = list(snap.margins_ahead[:ROUND_BARS])
        bars = ahead or [p for p in snap.margins_past if p[0] is not None][-ROUND_BARS:]
        c.text(x0, pad, "NEXT ROUNDS" if ahead or not bars else "LAST ROUNDS", title, DIM)
        if snap.lives is not None:
            lives_colour = BAD if risk == BAD else (WARN if snap.lives <= 1 else TEXT)
            c.text(x1, pad, f"♥ {snap.lives}", font("semibold", L.fpx(TITLE_PX + 1)), lives_colour, 1.0, "ra")
        top = pad + L.px(TITLE_PX * 1.6)
        foot_y = c.h - pad
        label_h = L.px(TINY_PX * 1.3)
        base = foot_y - L.px(SMALL_PX * 1.45) - label_h          # the bars' baseline
        h = base - top
        if not bars:
            c.text((x0 + x1) / 2, (top + base) / 2, "no forecast yet", small, FAINT, 1.0, "mm")
            return c.picture()
        for m, colour in ((LEAK_MARGIN, BAD), (snap.weak, WARN)):
            if m:
                y = base - h * min(m, MARGIN_CAP) / MARGIN_CAP
                for dx in range(int(x0), int(x1), L.px(6)):            # a dotted line
                    c.marks.line((*c.at(dx, y), *c.at(min(x1, dx + L.px(3)), y)), fill=ink(colour, 0.5), width=1)
        slot = (x1 - x0) / len(bars)
        for i, (r, m) in enumerate(bars):
            colour = margin_colour(m, snap.weak)
            bw = slot * 0.56
            bx = x0 + i * slot + (slot - bw) / 2
            bh = max(L.px(2), h * min(m, MARGIN_CAP) / MARGIN_CAP)
            c.marks.rounded_rectangle(c.box(bx, base - bh, bx + bw, base), radius=min(L.px(3), bw / 2),
                                      fill=ink(colour, 0.85 if ahead else 0.4))
            is_worst = ahead and worst and r == worst[0]
            c.text(bx + bw / 2, base + L.px(2), str(r), font("semibold" if is_worst else "regular", L.fpx(TINY_PX)),
                   colour if is_worst else DIM, 1.0, "ma")
        if worst:
            r, m = worst
            verdict = "may leak" if m < LEAK_MARGIN else ("thin" if snap.weak and m < snap.weak else "holds")
            c.text(x0, foot_y, fit(f"weakest R{r}  {m:.2f}  ·  {verdict}", small, x1 - x0), small,
                   margin_colour(m, snap.weak), 1.0, "ld")
        else:
            c.text(x0, foot_y, "margins as each round started", tiny, FAINT, 1.0, "ld")
        return c.picture()

    # -- in a game: DECISION ----------------------------------------------------------------------
    def decision(self, snap):
        L = self.lay
        decisions = snap.journal.decisions if snap.journal else []
        d = decisions[-1] if decisions else None
        colour = SOURCE_COLOURS.get(d.source, TEXT) if d else DIM
        c = Card(L, L.decision, accent=rgb(colour))
        pad = L.px(PAD)
        x0, x1 = pad + L.px(6), c.w - pad
        body, small, tiny = font("semibold", L.fpx(BODY_PX)), font("regular", L.fpx(SMALL_PX)), \
            font("semibold", L.fpx(TINY_PX))
        step = L.px(SMALL_PX * 1.4)
        y = pad
        lines = []          # (text, colour, alpha) under the headline
        if d:
            chip = d.source.upper()
            cw = tiny.getlength(chip) + L.px(12)
            ch = L.px(BODY_PX * 1.25)
            c.marks.rounded_rectangle(c.box(x0, y, x0 + cw, y + ch), radius=ch / 2, fill=ink(colour, 0.9))
            c.text(x0 + cw / 2, y + ch / 2, chip, tiny, "#0b0f17", 1.0, "mm")
            rnd = f"R{d.rnd}" if d.rnd is not None else ""
            right = x1 - (tiny.getlength(rnd) + L.px(8) if rnd else 0)
            c.text(x1, y + ch / 2, rnd, tiny, DIM, 1.0, "rm")
            hx = x0 + cw + L.px(8)
            c.text(hx, y + ch / 2, fit(d.what, body, right - hx), body, TEXT, 1.0, "lm")
            y += ch + L.px(6)
            why = wrap(d.why or "-", small, x1 - x0 - small.getlength("why  "), 2)
            lines += [(("why  " if i == 0 else "") + ln, TEXT, 0.82) for i, ln in enumerate(why)]
        else:
            c.text(x0, y, "no decision yet this game", body, DIM)
            y += L.px(BODY_PX * 1.25) + L.px(6)
        plan = []
        if snap.reinforce and snap.reinforce["saving"]:
            plan.append(("saving for " + snap.reinforce["text"][len("saving for "):], WARN, 0.95))
        if snap.wishes:
            more = f"  (+{len(snap.wishes) - 1} more)" if len(snap.wishes) > 1 else ""
            plan.append((f"next → {snap.wishes[0].text()}{more}", GHOST, 0.95))
        elif snap.hud.get("waiting"):
            plan.append((f"waiting: {snap.hud['waiting']}", DIM, 0.95))
        room = max(0, int((c.h - pad - y) // step))
        # the plan lines matter more than a second line of why
        while len(lines) + len(plan) > room and len(lines) > 1:
            lines.pop()
        for s, col, a in (lines + plan)[:room]:
            c.text(x0, y + step / 2, fit(s, small, x1 - x0), small, col, a, "lm")
            y += step
        return c.picture()

    # -- in menus: PICK -------------------------------------------------------------------------
    def pick_content(self, snap):
        """What the PICK card says - (pick, phase, chance, notes, runner-ups),
        pick None when the planner has not chosen - and the card's height
        for it (the PROGRESS card sits right under it)."""
        L = self.lay
        planner = snap.planner or {}
        pick = pick_of(snap)
        h = 2 * L.px(PAD) + L.px(TITLE_PX * 1.6)
        if not pick:
            return (None, None, None, [], []), h + L.px(SMALL_PX * 1.4)
        p = chance(pick)
        notes = [n for n in pick.get("notes", ()) if not n.startswith("p=")][:PICK_NOTES]
        runner_ups = (planner.get("runner_ups") or [])[:RUNNER_UPS]
        h += L.px(PICK_MAP_PX * 1.35) + L.px(SMALL_PX * 1.5) + len(notes) * L.px(SMALL_PX * 1.35)
        if p is not None:
            h += L.px(15) + L.px(8)
        if runner_ups:
            h += L.px(4) + L.px(TITLE_PX * 1.5) + len(runner_ups) * L.px(SMALL_PX * 1.4)
        phase = planner.get("phase") or pick.get("phase")
        return (pick, phase, p, notes, runner_ups), min(h, L.px(PICK_H))

    def pick(self, snap):
        L = self.lay
        (pick, phase, p, notes, runner_ups), height = self.pick_content(snap)
        c = Card(L, L.pick_rect(height), accent=rgb(GHOST))
        pad = L.px(PAD)
        x0, x1 = pad + L.px(6), c.w - pad
        title, big, small, tiny = (font("semibold", L.fpx(TITLE_PX)), font("bold", L.fpx(PICK_MAP_PX)),
                                   font("regular", L.fpx(SMALL_PX - 1)), font("semibold", L.fpx(TINY_PX)))
        y = pad
        if not pick:
            c.text(x0, y, "NEXT GAME", title, DIM)
            c.text(x0, y + L.px(TITLE_PX * 1.6), "the planner has not chosen yet", small, FAINT)
            return c.picture()
        c.text(x0, y, "NEXT GAME" + (f"  ·  {phase}" if phase else ""), title, GHOST)
        y += L.px(TITLE_PX * 1.6)
        c.text(x0, y, fit(pick.get("map", "?"), big, x1 - x0), big, TEXT)
        y += L.px(PICK_MAP_PX * 1.35)
        c.text(x0, y, fit(f"{mode_name(pick.get('mode', '?'))}  ·  {pick.get('strategy', '?')}", small, x1 - x0),
               small, INFO)
        y += L.px(SMALL_PX * 1.5)
        if p is not None:
            y = self._bar(c, x0, x1, y, p, f"chance {p:.0%}", tiny)
        for n in notes:
            c.text(x0, y, "›", small, GHOST)
            c.text(x0 + L.px(10), y, fit(n, small, x1 - x0 - L.px(10)), small, DIM)
            y += L.px(SMALL_PX * 1.35)
        if runner_ups:
            y += L.px(4)
            c.text(x0, y, "ALSO", title, FAINT)
            y += L.px(TITLE_PX * 1.5)
            for i, cand in enumerate(runner_ups):
                label = fit(f"{i + 2}. {cand.get('map')} · {mode_name(cand.get('mode'))}", small, (x1 - x0) * 0.68)
                c.text(x0, y, label, small, TEXT, 0.85)
                if cand.get("p") is not None:
                    bx = x0 + (x1 - x0) * 0.72
                    by = y + L.px(SMALL_PX) * 0.45
                    self._mini(c, bx, x1, by, cand["p"])
                y += L.px(SMALL_PX * 1.4)
        return c.picture()

    def _bar(self, c, x0, x1, y, p, label, f):
        """A chance bar with its label in it; returns the y below it."""
        L = self.lay
        h = L.px(15)
        c.marks.rounded_rectangle(c.box(x0, y, x1, y + h), radius=h / 2, fill=ink("#ffffff", 0.08))
        c.marks.rounded_rectangle(c.box(x0, y, x0 + max(h, (x1 - x0) * max(0.0, min(1.0, p))), y + h),
                                  radius=h / 2, fill=ink(p_colour(p), 0.8))
        c.text(x0 + L.px(8), y + h / 2, label, f, "#0b0f17", 1.0, "lm")
        return y + h + L.px(8)

    def _mini(self, c, x0, x1, y, p):
        h = self.lay.px(6)
        c.marks.rounded_rectangle(c.box(x0, y, x1, y + h), radius=h / 2, fill=ink("#ffffff", 0.1))
        c.marks.rounded_rectangle(c.box(x0, y, x0 + max(h, (x1 - x0) * max(0.0, min(1.0, p))), y + h),
                                  radius=h / 2, fill=ink(p_colour(p), 0.85))

    # -- in menus: PROGRESS ---------------------------------------------------------------------
    @staticmethod
    def _last_game(snap):
        last = snap.journal
        if last and last.game and last.outcome:
            return (last.game.get("map"), last.game.get("mode"), last.outcome, last.end_round)
        return None

    def progress(self, snap):
        L = self.lay
        c = Card(L, L.progress_rect(self.pick_content(snap)[1]), accent=rgb(GOLD))
        pad = L.px(PAD)
        x0, x1 = pad + L.px(6), c.w - pad
        title, small, value = (font("semibold", L.fpx(TITLE_PX)), font("regular", L.fpx(SMALL_PX - 1)),
                               font("semibold", L.fpx(SMALL_PX - 1)))
        y = pad
        c.text(x0, y, "PROGRESS", title, DIM)
        if snap.level:
            c.text(x1, y, fit(snap.level.split("|")[0].strip(), title, (x1 - x0) / 2), title, INFO, 1.0, "ra")
        y += L.px(TITLE_PX * 1.7)
        tiers = snap.board
        if not tiers:
            c.text(x0, y, "no medals read yet", small, FAINT)
            return c.picture()
        maps = [m for t in tiers for m in t.maps]
        modes = len(snap.board_modes) or (len(maps[0].won) if maps else 0)
        # the tier the black-border push is on: the first one not finished
        current = next((t for t in tiers if t.black < len(t.maps)), tiers[-1])
        rows = [("black borders", sum(t.black for t in tiers), len(maps), GOLD),
                (f"  {current.tier}", current.black, len(current.maps), GOLD),
                ("CHIMPS", sum(m.chimps for m in maps), len(maps), CHIMPS),
                ("medals", sum(m.count for m in maps), len(maps) * modes, GOOD)]
        for label, have, total, colour in rows:
            c.text(x0, y, label, small, TEXT if not label.startswith(" ") else DIM, 0.9)
            c.text(x1, y, f"{have} / {total}", value, colour, 1.0, "ra")
            by = y + L.px(SMALL_PX * 1.25)
            c.marks.rounded_rectangle(c.box(x0, by, x1, by + L.px(3)), radius=1, fill=ink("#ffffff", 0.08))
            if total:
                c.marks.rounded_rectangle(c.box(x0, by, x0 + (x1 - x0) * have / total, by + L.px(3)), radius=1,
                                          fill=ink(colour, 0.85))
            y += L.px(SMALL_PX * 1.75)
        last = self._last_game(snap)
        if last and y + L.px(SMALL_PX) <= c.h - pad / 2:
            mp, mode, outcome, rnd = last
            col = GOOD if outcome == "victory" else BAD
            c.text(x0, y, fit(f"last: {mp} · {mode_name(mode)} · {outcome} R{rnd or '?'}", small, x1 - x0), small,
                   col, 0.9)
        return c.picture()

    # -- ghosts over the field ------------------------------------------------------------------
    def _ghost_geometry(self, snap, game_rect):
        """[(ghost, cx, cy, footprint px, range px, number)] for the next MAX_GHOSTS."""
        out = []
        width = game_rect[2]
        for i, gh in enumerate(snap.ghosts[:MAX_GHOSTS]):
            cx, cy = project(gh.x, gh.y, game_rect)
            size = snap.sizes.get(gh.kind) or [S.DEFAULT_FOOTPRINT, 0]
            out.append((gh, cx, cy, max(self.lay.px(8), size[0] * width), size[1] * width, i + 1))
        return out

    def ghosts(self, snap, game_rect):
        """Thin, faint marks where the build still wants towers: a see-through
        body for a tower still to place (with its range dotted), a thin ring
        round a standing tower it will upgrade, and a small label. One
        picture just big enough for them all."""
        geo = self._ghost_geometry(snap, game_rect)
        if not geo:
            return None
        L = self.lay
        f = font("semibold", L.fpx(TINY_PX + 1))
        labels = []
        x0 = y0 = math.inf
        x1 = y1 = -math.inf
        for gh, cx, cy, foot, rng, n in geo:
            reach = max(foot * 1.35, rng)
            label = f"{n} {gh.kind}" + (f" → {gh.target}" if gh.target else "")
            lw = f.getlength(label)
            ly = cy + foot * 1.35 + L.px(3)
            labels.append((label, cx, ly, gh.placed))
            x0, y0 = min(x0, cx - reach, cx - lw / 2), min(y0, cy - reach)
            x1, y1 = max(x1, cx + reach, cx + lw / 2), max(y1, cy + reach, ly + L.px(TINY_PX * 1.6))
        m = L.px(4)
        x0, y0 = max(0, int(x0) - m), max(0, int(y0) - m)
        x1, y1 = min(self.lay.w, int(x1) + m + 1), min(self.lay.h, int(y1) + m + 1)
        if x1 <= x0 or y1 <= y0:
            return None
        img = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        line_w = max(1, L.px(1.5))
        for gh, cx, cy, foot, rng, n in geo:
            cx, cy = cx - x0, cy - y0
            if gh.placed:
                r = foot * 1.3
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=ink(INFO, GHOST_RING_ALPHA), width=line_w)
                continue
            if rng:
                steps = max(12, int(2 * math.pi * rng / L.px(9)))        # a dotted range ring
                for k in range(0, steps, 2):
                    d.arc((cx - rng, cy - rng, cx + rng, cy + rng), 360 * k / steps, 360 * (k + 1) / steps,
                          fill=ink(GHOST, GHOST_RANGE_ALPHA), width=1)
            d.ellipse((cx - foot, cy - foot, cx + foot, cy + foot), fill=ink(GHOST, GHOST_FILL_ALPHA),
                      outline=ink(GHOST, GHOST_EDGE_ALPHA), width=line_w)
        for label, cx, ly, placed in labels:
            colour = INFO if placed else GHOST
            p = (cx - x0, ly - y0)
            d.text((p[0] + 1, p[1] + 1), label, font=f, fill=(0, 0, 0, 170), anchor="ma")
            d.text(p, label, font=f, fill=ink(colour, GHOST_LABEL_ALPHA), anchor="ma")
        return Picture(img, x0, y0)
