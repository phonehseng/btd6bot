"""The big HUD's picture: what to draw, as plain shapes, from a Snapshot.

No window here. Scene.layers() turns a hud_data.Snapshot into named layers
of Shape records - each one Tk canvas call, create_<kind>(*coords, **opts) -
which tools/big_hud.py draws on its canvas, tools/hud_preview.py into an
image and the tests count.

Two views, chosen by Snapshot.in_game:

  in a game   a THINKING panel down the left (round, cash, lives, the
              damage model's margins for the rounds ahead, the latest
              decision and why, what reinforce saves for, what the build
              wants next, the bot's stream of thought), and over the play
              field ghost towers - "hallucinations" of what the build still
              wants: dashed, see-through towers at their planned spots and
              rings on standing towers it will upgrade, the next one tied to
              the panel by a moving thought line
  in menus    the same panel with the planner's pick, its reasons and the
              runner-ups, and a black-border board: every map by tier with
              its 14 medals, black borders and CHIMPS wins lit, the maps the
              planner considers marked

A thin status strip stays at the top centre in both (where the old HUD
was), beside the STOP / GO / OFF buttons big_hud.py places there.

Layers are drawn bottom to top in LAYER_ORDER, each rebuilt only when its
key changes: the board when the medals or the pick change, the panel when
a file changed, the animation layer every frame (a few dozen items).
"""
from __future__ import annotations

import math
import textwrap
from collections import namedtuple

from hud_data import LEAK_MARGIN, project

Shape = namedtuple("Shape", "kind coords opts")

# -- look -------------------------------------------------------------------------------
KEY = "#010203"          # the window's see-through colour: nothing is ever drawn in it
PANEL_BG = "#0b0f17"
PANEL_EDGE = "#2b3d5c"
TEXT = "#e8e8e8"
DIM = "#8b95a7"
FAINT = "#4a5468"
GOOD = "#7cfc9a"         # the old strip's colours: active / quiet / silent
WARN = "#ffd54f"
BAD = "#ff6e6e"
INFO = "#81d4fa"
GHOST = "#c39bff"        # what the bot imagines: ghost towers, thought lines
GOLD = "#d4af37"         # a black border's frame
CHIMPS = "#ff9e40"
SOURCE_COLOURS = {"plan": INFO, "surplus": GOOD, "reinforce": WARN, "ramp": "#ffab40", "threat": "#ea80fc",
                  "panic": BAD, "fill": "#80cbc4", "deferred": DIM, "hold": BAD}
FONT = "Segoe UI"
MONO = "Consolas"
CHAR_W = 0.56            # average character width of FONT, as a share of its pixel size
BOLD_CHAR_W = 0.62       # ... in bold
MONO_CHAR_W = 0.6         # Consolas, with a little room for rounding

# -- layout (fractions of the screen, pixel sizes at BASE_HEIGHT) ----------------------
BASE_HEIGHT = 1200       # pixel sizes below are for a 1200 px tall screen and scale with it
STRIP_WIDTH = 0.42       # the status strip's share of the screen width (as the old strip)
STRIP_HEIGHT = 46
PANEL_X = (0.006, 0.262)
PANEL_TOP = 0.105        # in a game: below the game's own lives and cash
PANEL_BOTTOM = 0.988
BOARD_X = (0.278, 0.994)
PAD = 12
GAP = 10
TITLE_PX, BIG_PX, BODY_PX, SMALL_PX, TINY_PX = 26, 30, 16, 14, 12
BEAT_ROOM = 20           # room left of the strip's text for its heartbeat dot
MIN_FONT_PX = 8          # no text smaller than this, however small the screen

# -- motion -------------------------------------------------------------------------------
ORB_SPIN = 1.6           # turns per second of the thinking orb while the bot is busy
ORB_NODES = 6
TYPE_CPS = 70            # characters per second the newest log line is typed at
GROW_S = 0.8             # seconds a new margin bar takes to grow
SCAN_S = 3.0             # seconds per sweep of the margin chart's scan line
PULSE_S = 1.4            # seconds per pulse of the ghosts and the board's marks
THOUGHT_DOTS = 4
QUIET_OK_S, QUIET_WARN_S = 120, 480   # the strip turns yellow, then red, when the bot goes quiet

MARGIN_CAP = 3.0         # margins above this are drawn full height
MAX_GHOSTS = 8           # ghost towers drawn: the next ones in the plan
WANTS_LISTED = 5
DEFAULT_FOOTPRINT = 0.0193   # footprint when hud.json gives none: the bot's default (placement.DEFAULT_RADIUS,
                             # 7 world units) at its 5.3 px per unit on a 1920-wide game (Game.PX_PER_UNIT)
LAYER_ORDER = ("board", "panel", "ghosts", "anim")


# -- shape helpers -------------------------------------------------------------------------

def rect(x0, y0, x1, y1, **o):
    return Shape("rectangle", (x0, y0, x1, y1), o)


def oval(cx, cy, r, **o):
    return Shape("oval", (cx - r, cy - r, cx + r, cy + r), o)


def line(points, **o):
    return Shape("line", tuple(points), o)


def arc(cx, cy, r, start, extent, **o):
    return Shape("arc", (cx - r, cy - r, cx + r, cy + r), dict(start=start, extent=extent, style="arc", **o))


def text(x, y, s, px, colour=TEXT, anchor="nw", bold=False, mono=False):
    size = max(MIN_FONT_PX, round(px))
    return Shape("text", (x, y), dict(text=s, fill=colour, anchor=anchor,
                                      font=(MONO if mono else FONT, -size, "bold" if bold else "normal")))


def wrap(s, px, width, mono=False, max_lines=None, bold=False):
    """Lines of `s` that fit `width` pixels at font size `px`."""
    chars = max(8, int(width / (px * (MONO_CHAR_W if mono else (BOLD_CHAR_W if bold else CHAR_W)))))
    lines = textwrap.wrap(str(s), chars) or [""]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, chars - 1)].rstrip() + "…"
    return lines


def fit(s, px, width, mono=False, bold=False):
    """`s` cut to one line of `width` pixels."""
    return wrap(s, px, width, mono, max_lines=1, bold=bold)[0]


def margin_colour(m, weak):
    if m < LEAK_MARGIN:
        return BAD
    return WARN if weak is not None and m < weak else GOOD


def pulse(now, period=PULSE_S):
    """0..1..0 once per period."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * (now % period) / period)


def blend(c1, c2, t):
    """Colour between c1 and c2 (#rrggbb), t = 0..1: a fade without alpha."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class Layout:
    """Pixel geometry for a screen of w x h."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.u = h / BASE_HEIGHT

    def px(self, n):
        """A size given at BASE_HEIGHT, in pixels on this screen."""
        return n * self.u

    @property
    def strip(self):
        """(x0, y0, x1, y1) of the status strip, as the old HUD placed it."""
        w = int(self.w * STRIP_WIDTH)
        x0 = (self.w - w) // 2
        return x0, 0, x0 + w, self.px(STRIP_HEIGHT)

    def panel(self, in_game):
        top = self.h * PANEL_TOP if in_game else self.strip[3] + self.px(GAP)
        return self.w * PANEL_X[0], top, self.w * PANEL_X[1], self.h * PANEL_BOTTOM

    @property
    def board(self):
        return self.w * BOARD_X[0], self.strip[3] + self.px(GAP), self.w * BOARD_X[1], self.h * PANEL_BOTTOM


class Scene:
    """Builds the layers; remembers what the animation needs between frames
    (where the margin chart and the newest log line are, when they changed)."""

    def __init__(self, w, h):
        self.lay = Layout(w, h)
        self._margins_key = None
        self._margins_since = -1e9
        self._typed_key = None
        self._typed_since = -1e9
        self._spark = None          # (box, bars) of the margin chart: bars = [(x0, x1, margin, ahead)]
        self._typed = None          # (x, y, text, px) of the newest log line
        self._wants = None          # (x, y) where the thought line leaves the panel
        self._board_marks = {}      # map -> (box, rank) of the maps the planner considers
        self._orb = None            # (cx, cy, r)
        self._strip_line = None     # (x, y, room, text) of the strip's first line

    # -- the layers ------------------------------------------------------------------
    def layers(self, snap, now, game_rect=None):
        """[(name, key, build)] in LAYER_ORDER; build() -> [Shape]. A layer
        whose key did not change since the last frame need not be rebuilt."""
        in_game = snap.in_game
        margins = tuple(snap.margins_ahead)
        if margins != self._margins_key:
            self._margins_key, self._margins_since = margins, now
        newest = (snap.log[-1].clock, snap.log[-1].text) if snap.log else None
        if newest != self._typed_key:
            self._typed_key, self._typed_since = newest, now
        board_key = (None if in_game else (id(snap.board), self._considered(snap)))
        ghosts_key = (tuple(snap.ghosts), game_rect, tuple(sorted(snap.sizes))) if in_game else None
        return [("board", board_key, lambda: [] if in_game else self.board(snap)),
                ("panel", (snap.version, in_game, snap.flags), lambda: self.panel(snap)),
                ("ghosts", ghosts_key, lambda: self.ghosts(snap, game_rect) if in_game and game_rect else []),
                ("anim", now, lambda: self.anim(snap, now, game_rect))]

    def build_all(self, snap, now, game_rect=None):
        """Every layer's shapes, bottom first (previews and tests)."""
        return [s for _name, _key, build in self.layers(snap, now, game_rect) for s in build()]

    # -- the panel -------------------------------------------------------------------
    def panel(self, snap):
        L = self.lay
        x0, y0, x1, y1 = L.panel(snap.in_game)
        out = [rect(x0, y0, x1, y1, fill=PANEL_BG, outline=PANEL_EDGE, width=2)]
        out += self.strip(snap)
        pad = L.px(PAD)
        cx0, cx1 = x0 + pad, x1 - pad
        width = cx1 - cx0
        y = y0 + pad
        # header: the orb (drawn by anim) and what the bot is doing
        orb_r = L.px(BIG_PX) * 0.8
        self._orb = (cx0 + orb_r, y + orb_r, orb_r)
        tx = cx0 + 2 * orb_r + pad
        out.append(text(tx, y, "THINKING", L.px(TITLE_PX), GHOST, bold=True))
        y_state = y + L.px(TITLE_PX) * 1.25
        for ln in wrap(snap.state or "the bot has not said anything yet", L.px(SMALL_PX), cx1 - tx, max_lines=2):
            out.append(text(tx, y_state, ln, L.px(SMALL_PX), DIM))
            y_state += L.px(SMALL_PX) * 1.3
        y = max(y + 2 * orb_r, y_state) + L.px(GAP)
        if snap.in_game:
            y = self._game_section(out, snap, cx0, cx1, y)
        else:
            y = self._menu_section(out, snap, cx0, cx1, y)
        self._thought_stream(out, snap, cx0, cx1, y, y1 - pad)
        return out

    def _heading(self, out, x, y, label, colour=DIM):
        px = self.lay.px(TINY_PX)
        out.append(text(x, y, label.upper(), px, colour, bold=True))
        return y + px * 1.5

    def _game_section(self, out, snap, x0, x1, y):
        L = self.lay
        g = snap.game or {}
        # round / cash / lives, big
        cols = [("ROUND", f"{snap.round if snap.round is not None else '?'}"
                 + (f"/{g['end_round']}" if g.get("end_round") else ""), TEXT),
                ("CASH", f"${snap.cash:,}" if isinstance(snap.cash, int) else "?", GOOD),
                ("LIVES", f"{snap.lives}" if snap.lives is not None else "?",
                 BAD if snap.lives is not None and snap.lives <= 1 else TEXT)]
        cw = (x1 - x0) / len(cols)
        for i, (label, value, colour) in enumerate(cols):
            out.append(text(x0 + i * cw, y, label, L.px(TINY_PX), DIM, bold=True))
            out.append(text(x0 + i * cw, y + L.px(TINY_PX) * 1.3, value, L.px(BIG_PX), colour, bold=True))
        y += L.px(TINY_PX) * 1.3 + L.px(BIG_PX) * 1.35
        where = " / ".join(str(v) for v in (g.get("map"), g.get("mode")) if v)
        out.append(text(x0, y, fit(where or "a game", L.px(BODY_PX), x1 - x0), L.px(BODY_PX), TEXT, bold=True))
        y += L.px(BODY_PX) * 1.35
        build = ", ".join(str(v) for v in (g.get("strategy"), g.get("hero")) if v)
        if build:
            out.append(text(x0, y, fit(build, L.px(SMALL_PX), x1 - x0), L.px(SMALL_PX), DIM))
            y += L.px(SMALL_PX) * 1.4
        y += L.px(GAP) * 0.5
        y = self._margin_chart(out, snap, x0, x1, y)
        y = self._decisions(out, snap, x0, x1, y)
        if snap.reinforce:
            y = self._heading(out, x0, y, "reinforce - saving for" if snap.reinforce["saving"] else "reinforce", WARN)
            said = snap.reinforce["text"]
            if snap.reinforce["saving"]:
                said = said[len("saving for "):]
            for ln in wrap(said, L.px(SMALL_PX), x1 - x0, max_lines=2):
                out.append(text(x0, y, ln, L.px(SMALL_PX), WARN))
                y += L.px(SMALL_PX) * 1.3
            y += L.px(GAP) * 0.5
        y = self._wants_list(out, snap, x0, x1, y)
        return y

    def _margin_chart(self, out, snap, x0, x1, y):
        """The damage model's margins: past rounds (as each started, dim) and
        the rounds ahead (bright); bars are drawn by anim so they can grow."""
        L = self.lay
        y = self._heading(out, x0, y, "damage model - margin per round")
        past = [(r, m, False) for r, m in snap.margins_past if r is not None]
        ahead_rounds = {r for r, _m in snap.margins_ahead}
        past = [p for p in past if p[0] not in ahead_rounds][-max(0, 18 - len(snap.margins_ahead)):]
        bars = past + [(r, m, True) for r, m in snap.margins_ahead]
        h = L.px(BIG_PX) * 3
        box = (x0, y, x1, y + h)
        out.append(rect(*box, fill="#070a10", outline=FAINT))
        if not bars:
            out.append(text((x0 + x1) / 2, y + h / 2, "no margins yet", L.px(SMALL_PX), FAINT, anchor="center"))
            self._spark = None
            return y + h + L.px(GAP)
        lines = [(LEAK_MARGIN, BAD, "1.0")]
        if snap.weak:
            lines.append((snap.weak, WARN, f"{snap.weak:g}"))
        for m, colour, label in lines:
            ly = box[3] - h * min(m, MARGIN_CAP) / MARGIN_CAP
            out.append(line((x0, ly, x1, ly), fill=colour, dash=(3, 4)))
            out.append(text(x1 - 2, ly - 1, label, L.px(TINY_PX), colour, anchor="se"))
        slot = (x1 - x0) / len(bars)
        drawn = []
        label_every = max(1, math.ceil(len(bars) * L.px(TINY_PX) * 1.6 / (x1 - x0)))
        for i, (r, m, ahead) in enumerate(bars):
            bx0, bx1 = x0 + i * slot + slot * 0.18, x0 + (i + 1) * slot - slot * 0.18
            drawn.append((bx0, bx1, m, ahead))
            if i % label_every == 0:
                out.append(text((bx0 + bx1) / 2, box[3] + 2, str(r), L.px(TINY_PX), TEXT if ahead else FAINT,
                                anchor="n"))
        self._spark = (box, drawn, snap.weak)
        worst = min(snap.margins_ahead, key=lambda p: p[1]) if snap.margins_ahead else None
        y = box[3] + L.px(TINY_PX) * 1.5
        if worst:
            out.append(text(x0, y, f"weakest ahead: round {worst[0]} at {worst[1]:.2f}", L.px(SMALL_PX),
                            margin_colour(worst[1], snap.weak), bold=True))
            y += L.px(SMALL_PX) * 1.4
        return y + L.px(GAP) * 0.5

    def _decisions(self, out, snap, x0, x1, y):
        L = self.lay
        decisions = list(snap.journal.decisions) if snap.journal else []
        if not decisions:
            return y
        y = self._heading(out, x0, y, "latest decision")
        d = decisions[-1]
        colour = SOURCE_COLOURS.get(d.source, TEXT)
        chip = d.source.upper()
        cw = len(chip) * L.px(TINY_PX) * CHAR_W * 1.15 + L.px(PAD)
        out.append(rect(x0, y, x0 + cw, y + L.px(BODY_PX) * 1.3, fill=colour, outline=""))
        out.append(text(x0 + cw / 2, y + L.px(BODY_PX) * 0.65, chip, L.px(TINY_PX), PANEL_BG, "center", bold=True))
        out.append(text(x0 + cw + L.px(GAP), y, fit(d.what, L.px(BODY_PX), x1 - x0 - cw - L.px(GAP)),
                        L.px(BODY_PX), TEXT, bold=True))
        y += L.px(BODY_PX) * 1.5
        for ln in wrap("why: " + (d.why or "-"), L.px(SMALL_PX), x1 - x0, max_lines=2):
            out.append(text(x0, y, ln, L.px(SMALL_PX), colour))
            y += L.px(SMALL_PX) * 1.3
        y += L.px(GAP) * 0.4
        for d in reversed(decisions[:-1][-4:]):
            colour = SOURCE_COLOURS.get(d.source, DIM)
            out.append(oval(x0 + L.px(4), y + L.px(SMALL_PX) * 0.65, L.px(4), fill=colour, outline=""))
            out.append(text(x0 + L.px(14), y, fit(f"{d.what} - {d.source}", L.px(SMALL_PX), x1 - x0 - L.px(14)),
                            L.px(SMALL_PX), DIM))
            y += L.px(SMALL_PX) * 1.35
        return y + L.px(GAP) * 0.6

    def _wants_list(self, out, snap, x0, x1, y):
        """What the build wants next; the first entry is where the thought
        line to its ghost starts."""
        L = self.lay
        self._wants = None
        if not snap.wishes:
            if snap.hud.get("waiting"):
                y = self._heading(out, x0, y, "plan")
                out.append(text(x0, y, fit(snap.hud["waiting"], L.px(SMALL_PX), x1 - x0), L.px(SMALL_PX), DIM))
                y += L.px(SMALL_PX) * 1.4
            return y
        y = self._heading(out, x0, y, "wants next (ghosts on the field)", GHOST)
        numbered = {g.tid: i + 1 for i, g in enumerate(snap.ghosts[:MAX_GHOSTS])}
        for i, w in enumerate(snap.wishes[:WANTS_LISTED]):
            n = numbered.get(w.tid)
            mark = f"{n}" if n else "·"
            colour = GHOST if i == 0 else (TEXT if n else DIM)
            out.append(text(x0, y, mark, L.px(SMALL_PX), GHOST, bold=True))
            out.append(text(x0 + L.px(18), y, fit(w.text(), L.px(SMALL_PX), x1 - x0 - L.px(18)),
                            L.px(SMALL_PX), colour, bold=(i == 0)))
            if i == 0 and n:
                self._wants = (x1, y + L.px(SMALL_PX) * 0.65, w.tid)
            y += L.px(SMALL_PX) * 1.35
        return y + L.px(GAP) * 0.5

    def _menu_section(self, out, snap, x0, x1, y):
        L = self.lay
        planner = snap.planner or {}
        pick = planner.get("pick") or snap.next
        if not pick:
            y = self._heading(out, x0, y, "next game")
            out.append(text(x0, y, "the planner has not chosen yet", L.px(SMALL_PX), FAINT))
            return y + L.px(SMALL_PX) * 1.5
        y = self._heading(out, x0, y, f"next game [{planner.get('phase') or pick.get('phase') or '?'}]", GHOST)
        out.append(text(x0, y, fit(pick.get("map", "?"), L.px(BIG_PX), x1 - x0), L.px(BIG_PX), TEXT, bold=True))
        y += L.px(BIG_PX) * 1.3
        out.append(text(x0, y, fit(f"{pick.get('mode', '?')}  with  {pick.get('strategy', '?')}", L.px(BODY_PX),
                                   x1 - x0), L.px(BODY_PX), INFO, bold=True))
        y += L.px(BODY_PX) * 1.5
        p = pick.get("p")
        if p is None:     # the log line's notes carry p as "p=0.48 (n=0)"
            p = next((float(n[2:6]) for n in pick.get("notes", ()) if n.startswith("p=")), None)
        if p is not None:
            y = self._p_bar(out, x0, x1, y, p, "chance to win")
        notes = [n for n in pick.get("notes", ()) if not n.startswith("p=")]
        for n in notes[:6]:
            for ln in wrap(n, L.px(SMALL_PX), x1 - x0 - L.px(14), max_lines=1):
                out.append(text(x0, y, "›", L.px(SMALL_PX), GHOST, bold=True))
                out.append(text(x0 + L.px(14), y, ln, L.px(SMALL_PX), DIM))
                y += L.px(SMALL_PX) * 1.3
        y += L.px(GAP)
        runner_ups = planner.get("runner_ups") or []
        if runner_ups:
            y = self._heading(out, x0, y, "also considered")
            for i, c in enumerate(runner_ups):
                label = fit(f"{i + 2}. {c.get('map')} / {c.get('mode')}", L.px(SMALL_PX), (x1 - x0) * 0.68)
                out.append(text(x0, y, label, L.px(SMALL_PX), TEXT))
                if c.get("p") is not None:
                    self._mini_bar(out, x0 + (x1 - x0) * 0.7, x1, y + L.px(SMALL_PX) * 0.25, c["p"])
                y += L.px(SMALL_PX) * 1.4
            y += L.px(GAP) * 0.5
        last = snap.journal
        if last and last.game and last.outcome:
            g = last.game
            colour = GOOD if last.outcome == "victory" else BAD
            y = self._heading(out, x0, y, "last game")
            out.append(text(x0, y, fit(f"{g.get('map')} / {g.get('mode')}: {last.outcome} at round "
                                       f"{last.end_round or '?'}", L.px(SMALL_PX), x1 - x0),
                            L.px(SMALL_PX), colour, bold=True))
            y += L.px(SMALL_PX) * 1.5
        return y

    def _p_bar(self, out, x0, x1, y, p, label):
        L = self.lay
        h = L.px(SMALL_PX)
        colour = GOOD if p >= 0.8 else (WARN if p >= 0.6 else BAD)
        out.append(rect(x0, y, x1, y + h, fill="#070a10", outline=FAINT))
        out.append(rect(x0, y, x0 + (x1 - x0) * max(0.0, min(1.0, p)), y + h, fill=colour, outline=""))
        out.append(text(x0 + L.px(4), y + h / 2, f"{label} {p:.0%}", L.px(TINY_PX), PANEL_BG, "w", bold=True))
        return y + h + L.px(GAP)

    def _mini_bar(self, out, x0, x1, y, p):
        h = self.lay.px(SMALL_PX) * 0.7
        colour = GOOD if p >= 0.8 else (WARN if p >= 0.6 else BAD)
        out.append(rect(x0, y, x1, y + h, fill="#070a10", outline=FAINT))
        out.append(rect(x0, y, x0 + (x1 - x0) * max(0.0, min(1.0, p)), y + h, fill=colour, outline=""))

    def _thought_stream(self, out, snap, x0, x1, y, y_end):
        """The newest bot.log lines, oldest faded; the newest is typed by anim."""
        L = self.lay
        px = L.px(TINY_PX)
        step = px * 1.35
        y = self._heading(out, x0, y + L.px(GAP) * 0.5, "stream of thought")
        room = int((y_end - y) // step)
        self._typed = None
        if room <= 0 or not snap.log:
            return
        lines = []
        for rec in snap.log:
            body = f"{rec.clock} {rec.source}: {rec.text}"
            lines.append((wrap(body, px, x1 - x0, mono=True, max_lines=2), rec))
        # the newest lines that fit, oldest first
        shown, used = [], 0
        for wrapped, rec in reversed(lines):
            if used + len(wrapped) > room:
                break
            shown.insert(0, (wrapped, rec))
            used += len(wrapped)
        for i, (wrapped, rec) in enumerate(shown):
            newest = i == len(shown) - 1
            age = (len(shown) - 1 - i) / max(1, len(shown) - 1)
            colour = BAD if rec.level == "E" else (WARN if rec.level == "W" else TEXT)
            colour = blend(colour, PANEL_BG, 0.65 * age)
            if newest:
                self._typed = (x0, y, wrapped, px, colour, step)
                break
            for ln in wrapped:
                out.append(text(x0, y, ln, px, colour, mono=True))
                y += step

    # -- the status strip ---------------------------------------------------------------
    def strip(self, snap):
        L = self.lay
        x0, y0, x1, y1 = L.strip
        out = [rect(x0, y0, x1, y1, fill=PANEL_BG, outline=PANEL_EDGE)]
        pad = L.px(PAD)
        flags = "".join({"HOLD": " | STOPPED - press GO", "PAUSE": " | PAUSED", "STOP": " | OFF"}[f]
                        for f in snap.flags)
        right = fit(f"XP: {snap.focus}", L.px(SMALL_PX), (x1 - x0) * 0.4) if snap.focus else ""
        out.append(text(x1 - pad, y0 + L.px(4), right, L.px(SMALL_PX), WARN, "ne", bold=True))
        # line 1 - the state and how long ago the bot last did anything - ticks, so anim draws it
        lx = x0 + pad + L.px(BEAT_ROOM)
        room = x1 - pad - lx - len(right) * L.px(SMALL_PX) * CHAR_W - L.px(GAP)
        self._strip_line = (lx, y0 + L.px(4), room, f"BTD6 bot: {snap.state}{flags}")
        out.append(text(x1 - pad, y1 - L.px(4), snap.level, L.px(TINY_PX), INFO, "se", bold=True))
        msg = snap.log[-1].text if snap.log else ""
        room = (x1 - x0) - 2 * pad - len(snap.level) * L.px(TINY_PX) * CHAR_W - L.px(GAP)
        out.append(text(x0 + pad, y1 - L.px(4), fit(msg, L.px(TINY_PX), room), L.px(TINY_PX), TEXT, "sw"))
        return out

    @staticmethod
    def _strip_colour(snap):
        if "HOLD" in snap.flags or (snap.quiet is not None and snap.quiet >= QUIET_WARN_S):
            return BAD
        return GOOD if snap.quiet is None or snap.quiet < QUIET_OK_S else WARN

    # -- ghosts over the play field ------------------------------------------------------
    def _ghost_geometry(self, snap, game_rect):
        """[(ghost, cx, cy, footprint px, range px, number)] for the next MAX_GHOSTS."""
        out = []
        width = game_rect[2]
        for i, g in enumerate(snap.ghosts[:MAX_GHOSTS]):
            cx, cy = project(g.x, g.y, game_rect)
            size = snap.sizes.get(g.kind) or [DEFAULT_FOOTPRINT, 0]
            out.append((g, cx, cy, max(self.lay.px(8), size[0] * width), size[1] * width, i + 1))
        return out

    def ghosts(self, snap, game_rect):
        """The still parts of the ghosts: see-through bodies and labels."""
        L = self.lay
        out = []
        for g, cx, cy, foot, _rng, n in self._ghost_geometry(snap, game_rect):
            label = f"{n} {g.kind}" + (f" -> {g.target}" if g.target else "")
            if g.placed:
                out.append(oval(cx, cy, foot * 1.25, outline=INFO, width=2, dash=(6, 4)))
                colour = INFO
            else:
                out.append(oval(cx, cy, foot, fill=GHOST, outline=GHOST, width=2, stipple="gray25"))
                out.append(oval(cx, cy, foot * 0.45, fill=GHOST, outline="", stipple="gray50"))
                colour = GHOST
            px = L.px(SMALL_PX)
            tw = len(label) * px * CHAR_W + L.px(8)
            ty = cy + foot * 1.3
            out.append(rect(cx - tw / 2, ty, cx + tw / 2, ty + px * 1.35, fill=PANEL_BG, outline=colour))
            out.append(text(cx, ty + px * 0.68, label, px, colour, "center", bold=True))
        return out

    # -- the board ----------------------------------------------------------------------
    def _considered(self, snap):
        """{map: rank} of the planner's pick (1) and runner-ups (2, 3, ...)."""
        planner = snap.planner or {}
        pick = planner.get("pick") or snap.next or {}
        maps = [pick.get("map")] + [c.get("map") for c in planner.get("runner_ups") or ()]
        out = {}
        for i, m in enumerate(maps):
            if m and m not in out:
                out[m] = i + 1
        return tuple(sorted(out.items(), key=lambda kv: kv[1]))

    def board(self, snap):
        L = self.lay
        x0, y0, x1, y1 = L.board
        out = [rect(x0, y0, x1, y1, fill=PANEL_BG, outline=PANEL_EDGE, width=2)]
        pad = L.px(PAD)
        tiers = snap.board
        self._board_marks = {}
        if not tiers:
            out.append(text((x0 + x1) / 2, (y0 + y1) / 2, "no medals read yet", L.px(BODY_PX), FAINT, "center"))
            return out
        maps = [m for t in tiers for m in t.maps]
        blacks, chimps = sum(t.black for t in tiers), sum(m.chimps for m in maps)
        out.append(text(x0 + pad, y0 + pad, "BLACK BORDERS", L.px(TITLE_PX), TEXT, bold=True))
        out.append(text(x0 + pad + L.px(TITLE_PX) * 8.2, y0 + pad + L.px(TITLE_PX) * 0.1,
                        f"{blacks} / {len(maps)} maps    CHIMPS {chimps} / {len(maps)}    "
                        f"medals {sum(m.count for m in maps)} / {len(maps) * len(snap.board_modes or ())}",
                        L.px(BODY_PX), DIM, bold=True))
        considered = dict(self._considered(snap))
        top = y0 + pad + L.px(TITLE_PX) * 1.6
        col_w = (x1 - x0 - pad) / len(tiers)
        rows_max = max(len(t.maps) for t in tiers)
        legend_h = L.px(TINY_PX) * 1.8
        row_h = (y1 - pad - legend_h - top - L.px(BODY_PX) * 1.8) / max(1, rows_max)
        modes = snap.board_modes or tuple((f"m{i}", "") for i in range(len(maps[0].won)))
        groups = sum(1 for i in range(1, len(modes)) if modes[i][1] != modes[i - 1][1])
        name_px = max(L.px(9), min(L.px(SMALL_PX), int(row_h * 0.55)))
        for ti, tb in enumerate(tiers):
            cx0 = x0 + pad + ti * col_w
            cx1 = cx0 + col_w - pad
            out.append(text(cx0, top, f"{tb.tier.title()}", L.px(BODY_PX), TEXT, bold=True))
            out.append(text(cx1, top + L.px(BODY_PX) * 0.15, f"{tb.black}/{len(tb.maps)} black", L.px(SMALL_PX),
                            GOLD if tb.black else DIM, "ne", bold=True))
            y = top + L.px(BODY_PX) * 1.8
            badge = row_h * 0.6            # room at the row's start for the planner's rank (anim)
            name_x = cx0 + badge
            name_w = (cx1 - cx0) * 0.47 - badge
            pip_x0 = name_x + name_w
            gap = row_h * 0.25
            pip = min(row_h * 0.62, (cx1 - pip_x0 - gap * groups) / len(modes))
            for m in tb.maps:
                ry0, ry1 = y + row_h * 0.08, y + row_h * 0.92
                if m.black:
                    out.append(rect(cx0, ry0, cx1, ry1, fill="#000000", outline=GOLD, width=1))
                rank = considered.get(m.name)
                if rank:
                    self._board_marks[m.name] = ((cx0, ry0, cx1, ry1), rank)
                colour = TEXT if m.black else (INFO if m.count else DIM)
                out.append(text(name_x, (ry0 + ry1) / 2, fit(m.name, name_px, name_w - L.px(6), bold=m.black), name_px,
                                colour, "w", bold=m.black))
                px_ = pip_x0
                for i, (won, (key, _diff)) in enumerate(zip(m.won, modes)):
                    if i and modes[i][1] != modes[i - 1][1]:
                        px_ += gap
                    py0 = (ry0 + ry1) / 2 - pip / 2
                    is_chimps = key == "chimps"
                    fill = (CHIMPS if is_chimps else (GOLD if m.black else GOOD)) if won else "#1a2130"
                    out.append(rect(px_, py0, px_ + pip * 0.82, py0 + pip, fill=fill,
                                    outline=CHIMPS if is_chimps else "", width=1))
                    px_ += pip
                y += row_h
        legend_y = y1 - pad
        out.append(text(x0 + pad, legend_y, "each square a medal, grouped Easy | Medium | Hard (CHIMPS last, framed "
                                            "orange);  gold row = black border;  numbered = the maps the planner "
                                            "considers",
                        L.px(TINY_PX), DIM, "sw"))
        return out

    # -- motion -------------------------------------------------------------------------
    def anim(self, snap, now, game_rect):
        out = []
        out += self._strip_anim(snap, now)
        out += self._orb_anim(snap, now)
        out += self._margin_anim(now)
        out += self._typed_anim(now)
        if snap.in_game and game_rect:
            out += self._ghost_anim(snap, now, game_rect)
        elif not snap.in_game:
            out += self._board_anim(now)
        return out

    def _strip_anim(self, snap, now):
        L = self.lay
        x0, y0, _x1, _y1 = L.strip
        colour = self._strip_colour(snap)
        beat = pulse(now, 1.0 if colour == GOOD else 2.5)
        cx, cy = x0 + L.px(PAD) + L.px(BEAT_ROOM) / 3, y0 + L.px(4) + L.px(SMALL_PX) * 0.65
        out = [oval(cx, cy, L.px(3) + L.px(3) * beat, fill=colour, outline="")]
        if self._strip_line:
            lx, ly, room, said = self._strip_line
            q = snap.quiet
            ago = "" if q is None else (f"   ({int(q)}s ago)" if q < QUIET_OK_S else f"   ({int(q // 60)} min ago)")
            room -= len(ago) * L.px(SMALL_PX) * CHAR_W
            out.append(text(lx, ly, fit(said, L.px(SMALL_PX), room) + ago, L.px(SMALL_PX), colour, bold=True))
        return out

    def _orb_anim(self, snap, now):
        """The thinking orb: nodes circling a core, spinning while the bot is
        busy, slow and red while it is stopped."""
        if not self._orb:
            return []
        cx, cy, r = self._orb
        held = "HOLD" in snap.flags or "STOP" in snap.flags
        busy = snap.quiet is not None and snap.quiet < QUIET_OK_S and not held
        colour = BAD if held else (GHOST if busy else WARN)
        spin = ORB_SPIN if busy else ORB_SPIN / 6
        p = pulse(now)
        out = [oval(cx, cy, r * (0.95 + 0.05 * p), outline=blend(colour, PANEL_BG, 0.6), width=1),
               oval(cx, cy, r * (0.32 + 0.08 * p), fill=colour, outline="")]
        angle0 = 2 * math.pi * ((now * spin) % 1.0)
        nodes = []
        for i in range(ORB_NODES):
            a = angle0 + 2 * math.pi * i / ORB_NODES
            wob = 0.72 + 0.12 * math.sin(now * 3 + i)
            nodes.append((cx + r * wob * math.cos(a), cy + r * wob * math.sin(a)))
        lit = int(now * spin * ORB_NODES) % ORB_NODES      # the synapse firing now
        for i, (nx, ny) in enumerate(nodes):
            tone = colour if i == lit else blend(colour, PANEL_BG, 0.55)
            out.append(line((cx, cy, nx, ny), fill=tone, width=2 if i == lit else 1))
            out.append(oval(nx, ny, r * (0.14 if i == lit else 0.09), fill=tone, outline=""))
        out.append(arc(cx, cy, r * 1.08, math.degrees(-angle0 * 0.5) % 360, 70, outline=colour, width=2))
        return out

    def _margin_anim(self, now):
        if not self._spark:
            return []
        (bx0, by0, bx1, by1), bars, weak = self._spark
        h = by1 - by0
        grow = min(1.0, (now - self._margins_since) / GROW_S)
        grow = 1 - (1 - grow) ** 3        # ease out
        out = []
        for x0, x1, m, ahead in bars:
            height = h * min(m, MARGIN_CAP) / MARGIN_CAP * (grow if ahead else 1.0)
            colour = margin_colour(m, weak)
            out.append(rect(x0, by1 - height, x1, by1, fill=colour if ahead else blend(colour, PANEL_BG, 0.6),
                            outline=""))
        scan = bx0 + (bx1 - bx0) * ((now % SCAN_S) / SCAN_S)
        out.append(line((scan, by0, scan, by1), fill=GHOST, width=1))
        return out

    def _typed_anim(self, now):
        """The newest log line, typed out, with a blinking cursor."""
        if not self._typed:
            return []
        x, y, wrapped, px, colour, step = self._typed
        shown = int((now - self._typed_since) * TYPE_CPS)
        out = []
        left = shown
        for ln in wrapped:
            part = ln[:max(0, left)]
            out.append(text(x, y, part, px, colour, mono=True))
            if left < len(ln):
                if int(now * 2) % 2 == 0:
                    cx = x + len(part) * px * MONO_CHAR_W
                    out.append(rect(cx, y, cx + px * 0.5, y + px * 1.1, fill=GHOST, outline=""))
                break
            left -= len(ln)
            y += step
        return out

    def _ghost_anim(self, snap, now, game_rect):
        """Range rings breathing round the ghosts; a thought line, with dots
        running along it, from the panel's first wish to its ghost."""
        out = []
        p = pulse(now)
        geo = self._ghost_geometry(snap, game_rect)
        for g, cx, cy, foot, rng, n in geo:
            if g.placed:
                out.append(oval(cx, cy, foot * (1.45 + 0.25 * p), outline=blend(INFO, PANEL_BG, 0.5 * p), width=2))
            elif rng:
                out.append(oval(cx, cy, rng * (0.97 + 0.03 * p), outline=blend(GHOST, PANEL_BG, 0.25 + 0.4 * p),
                                width=2, dash=(8, 6)))
            else:
                out.append(oval(cx, cy, foot * (1.4 + 0.3 * p), outline=blend(GHOST, PANEL_BG, 0.3 + 0.4 * p),
                                width=2))
        if self._wants and geo:
            target = next(((cx, cy, foot) for g, cx, cy, foot, _r, _n in geo if g.tid == self._wants[2]), None)
            if target:
                sx, sy = self._wants[0], self._wants[1]
                tx, ty, foot = target
                out.append(line((sx, sy, tx, ty), fill=blend(GHOST, PANEL_BG, 0.45), dash=(4, 6), width=1))
                for i in range(THOUGHT_DOTS):
                    t = ((now / PULSE_S) + i / THOUGHT_DOTS) % 1.0
                    out.append(oval(sx + (tx - sx) * t, sy + (ty - sy) * t, self.lay.px(3), fill=GHOST, outline=""))
                out.append(oval(tx, ty, foot * (1.1 + 0.6 * p), outline=GHOST, width=3))
        return out

    def _board_anim(self, now):
        """A breathing frame round each map the planner considers, its rank beside it."""
        out = []
        p = pulse(now)
        L = self.lay
        for _name, ((x0, y0, x1, y1), rank) in self._board_marks.items():
            colour = GHOST if rank == 1 else blend(GHOST, PANEL_BG, 0.45)
            grow = L.px(2) * p
            out.append(rect(x0 - grow, y0 - grow, x1 + grow, y1 + grow, outline=colour, width=2 if rank == 1 else 1))
            r = (y1 - y0) * 0.3
            out.append(oval(x0 + r * 1.2, (y0 + y1) / 2, r, fill=colour, outline=""))
            out.append(text(x0 + r * 1.2, (y0 + y1) / 2, str(rank), r * 1.5, PANEL_BG, "center", bold=True))
        return out
