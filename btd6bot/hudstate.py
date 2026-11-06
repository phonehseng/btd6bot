"""What only the running bot knows, as data for the big HUD (tools/big_hud.py).

bot.log says in words what the bot did, and the journal (journal.py) keeps
each purchase and round as data. A few things neither keeps, and the HUD
wants them while a game runs:

    phase      "game" while a match is played, "menu" after it ended
    game       map, mode, strategy, hero and last round of the match
    round, cash, lives          as the match last read them
    margins    the damage model's margin of every look-ahead round, as
               [[round, margin], ...] (rated once per round anyway, see
               match._rate_ahead), with the thresholds `weak` (reinforce
               starts under it) and `crisis`
    plan       the next plan steps (place / upgrade, with `at` when the
               build has an exact spot), what the build still wants
    towers     the towers standing: [tid, kind, crosspath, x, y]
    sizes      {kind: [footprint, range]} as fractions of the game width,
               so ghost towers are drawn at the size the game draws them
    waiting    what the plan waits on (Executor.waiting)
    save_goal  [cost, round] of the purchase reinforce saves for
    planner    the planner's pick and its runner-ups (runner.next_plan)

They go to logs/hud.json, rewritten whole (a temporary file, then a
rename, so the HUD never reads half a file). Routine updates come every
HUD tick of the match; at most one write per MIN_GAP seconds reaches the
disk, and a caller can ask due() first to skip building the fields at all.
Like status.py the file is a convenience: a failed write is ignored and
never costs a game, and the HUD treats an old file as no file.

Only the running bot writes it: bot.py calls enable() once it holds the
one-bot lock. A test or tool that builds a Match leaves the live file
alone, since the module-level writer stays off until then.
"""
import json
import os
import time
from pathlib import Path

HUD_FILE = Path(__file__).resolve().parents[1] / "logs" / "hud.json"
MIN_GAP = 1.0        # seconds between two routine writes
PLAN_AHEAD = 12      # plan steps passed on: the HUD draws the next few as ghosts


class HudState:
    """The fields of one hud.json, and when they were last written."""

    def __init__(self, path=HUD_FILE, min_gap=MIN_GAP, clock=time.time, enabled=True):
        self.path = Path(path)
        self.enabled = enabled
        self.min_gap = min_gap
        self.clock = clock
        self.fields = {}
        self._written = 0.0      # clock time of the last write

    def due(self):
        """Would a routine update be written now?"""
        return self.enabled and self.clock() - self._written >= self.min_gap

    def update(self, force=False, **fields):
        """Merge `fields` in; write them when due() or `force` (a phase
        change, a new game, new margins: the HUD should see those at once)."""
        self.fields.update(fields)
        if force or self.due():
            self.write()

    def start_game(self, **game):
        """A new match: the old game's facts go, the new game's come."""
        self.fields = {"phase": "game", "game": game}
        self.write()

    def end_game(self):
        """The match is over: the HUD goes back to its menu view."""
        self.update(force=True, phase="menu")

    def write(self):
        if not self.enabled:
            return
        now = self.clock()
        self._written = now
        self.fields["t"] = round(now, 2)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.fields, default=str), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass     # the HUD reading the file at that moment, a locked file: the next write comes


def plan_ahead(plan, idx, n=PLAN_AHEAD):
    """The next `n` place/upgrade steps of an executor's plan from step
    `idx`, cut to what the HUD draws: do, id, kind, to, at."""
    keep = ("do", "id", "kind", "to", "at")
    steps = [s for s in plan[idx:] if s.get("do") in ("place", "upgrade")]
    return [{k: s[k] for k in keep if s.get(k) is not None} for s in steps[:n]]


def tower_sizes(kinds):
    """{kind: [footprint radius, base range]} as fractions of the game
    width, for the kinds given; a kind the game data lacks is left out.
    Uses the same scale as the bot's own placement probe (Game.PX_PER_UNIT)."""
    from . import towers as T
    from .game import Game
    from .placement import footprint_radius
    out = {}
    for kind in set(kinds):
        try:
            foot = footprint_radius(kind)
            rng = (T.TOWERS.get(kind) or {}).get("range")
        except Exception:
            continue
        if foot:
            out[kind] = [round(foot * Game.PX_PER_UNIT, 4), round((rng or 0) * Game.PX_PER_UNIT, 4)]
    return out


_default = HudState(enabled=False)


def enable():
    """Let this process write logs/hud.json (the running bot: bot.py)."""
    _default.enabled = True


def due():
    return _default.due()


def update(force=False, **fields):
    _default.update(force=force, **fields)


def start_game(**game):
    _default.start_game(**game)


def end_game():
    _default.end_game()
