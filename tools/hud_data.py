"""What the big HUD (tools/big_hud.py) shows, read from the files the bot writes.

Pure data - no window, no drawing - so tests/test_big_hud_offline.py runs it
on fake log folders. Every source is optional: a missing, old or
half-written file only leaves its part of the HUD empty.

    logs/state.txt         one line: what the bot is doing (btd6bot/status.py)
    logs/bot.log           the decisions in words: the latest lines, the
                           planner's NEXT line, what reinforce saves for
    logs/journal/*.jsonl   the newest game (btd6bot/journal.py): game_start,
                           every purchase with its why, round snapshots
    logs/hud.json          what only the running bot knows (btd6bot/hudstate.py):
                           margins ahead, the plan ahead, the planner's runner-ups
    logs/focus.txt, logs/level.txt     XP focus and player level (status.py)
    data/current_account.txt, data/accounts/<uid>.json    the medals
    strategies/**/*.yaml   the build's planned spots, when hud.json has no plan

Collector.poll() re-reads a file only when its modification time changed,
so polling a few times a second costs a handful of stat calls.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_TAIL_BYTES = 32_000       # enough of bot.log for the latest decisions
JOURNAL_TAIL_BYTES = 400_000  # a long CHIMPS game's journal is about this size
LOG_LINES_KEPT = 40           # bot.log lines offered to the HUD's stream of thought (it shows what fits)
DECISIONS_KEPT = 7            # journal purchases listed with their why
STALE_GAME_S = 30             # hud.json "game" older than this: the match is gone
JOURNAL_LIVE_S = 300          # a journal untouched this long is no game in progress
FOCUS_STALE_S = 3 * 3600      # a focus note older than this is from a crashed game
JOURNAL_SCAN_S = 5.0          # seconds between looks for a newer journal file
ACCOUNT_SCAN_S = 30.0         # seconds between looks at the account's medals
LEAK_MARGIN = 1.0             # the damage model's margin under which a round leaks
CONTROL_FILES = ("HOLD", "PAUSE", "STOP")

LOG_RE = re.compile(r"^\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d),\d+ ([A-Z]) (\w+): (.*)$")
NEXT_RE = re.compile(r"NEXT: \[(?P<phase>[A-Z]+)\] (?P<map>.+?) / (?P<mode>\w+) with (?P<strategy>[\w.-]+): "
                     r"(?P<rest>.*)$")
NOTE_SPLIT = re.compile(r", (?![^()]*\))")    # the NEXT line's notes: commas outside brackets


# -- small file helpers ---------------------------------------------------------------

def read_tail(path, max_bytes):
    """The last `max_bytes` of a text file as lines (the first, likely cut,
    line dropped when the file is longer); [] when it cannot be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return lines[1:] if size > max_bytes else lines


def last_line(path):
    return next((ln for ln in reversed(read_tail(path, 4096)) if ln.strip()), "")


def mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tiers(cross):
    """'2-0-4' -> (2, 0, 4); anything unreadable -> (0, 0, 0)."""
    try:
        t = tuple(int(c) for c in str(cross).split("-"))
        return t if len(t) == 3 else (0, 0, 0)
    except ValueError:
        return (0, 0, 0)


# -- bot.log ---------------------------------------------------------------------------

@dataclass
class LogLine:
    clock: str      # HH:MM:SS
    level: str      # I / W / E
    source: str     # the logger: runner, game, strategy, reinforce, ...
    text: str


def parse_log(lines):
    """bot.log lines -> LogLine records (continuation lines of a traceback
    are skipped)."""
    out = []
    for ln in lines:
        m = LOG_RE.match(ln)
        if m:
            out.append(LogLine(*m.groups()))
    return out


def parse_next(text):
    """The planner's 'NEXT: [PHASE] map / mode with strategy: score ...;
    note, note' line -> {phase, map, mode, strategy, score, notes}, or None."""
    m = NEXT_RE.search(text)
    if not m:
        return None
    head, _, tail = m.group("rest").partition("; ")
    notes = [n.strip() for n in NOTE_SPLIT.split(tail) if n.strip()] if tail else []
    return {"phase": m.group("phase"), "map": m.group("map"), "mode": m.group("mode"),
            "strategy": m.group("strategy"), "score": head.strip(), "notes": notes}


def latest_next(records):
    """The newest NEXT choice in `records` (LogLine), or None."""
    for r in reversed(records):
        if r.source == "runner" and r.text.startswith("NEXT: "):
            return parse_next(r.text)
    return None


def latest_reinforce(records):
    """What reinforce last said in the current game - the newest 'reinforce: ...'
    line after the newest NEXT line - as {saving: bool, text}, or None."""
    for r in reversed(records):
        if r.source == "runner" and r.text.startswith("NEXT: "):
            return None
        if r.source == "reinforce" and r.text.startswith("reinforce: "):
            text = r.text[len("reinforce: "):]
            return {"saving": text.startswith("saving for "), "text": text}
    return None


# -- the journal -----------------------------------------------------------------------

@dataclass
class Decision:
    """One purchase (or hold) of the journal, said for the HUD."""
    source: str     # plan, surplus, reinforce, ramp, threat, panic, fill, deferred, hold, ...
    what: str       # "upgrade a1 2-0-1 -> 3-0-1  $1,700"
    why: str        # the reason the bot gave
    rnd: int | None = None


@dataclass
class JournalView:
    game: dict = field(default_factory=dict)          # the game_start record
    towers: dict = field(default_factory=dict)        # tid -> [kind, cross, x, y]
    decisions: list = field(default_factory=list)     # Decision, oldest first
    margins: list = field(default_factory=list)       # [(round, margin)] as each round started
    last_round: dict = field(default_factory=dict)    # the newest round snapshot
    outcome: str | None = None                        # game_end's outcome once the game ended
    end_round: int | None = None                      # ... and the round it ended in


def describe(rec):
    """A journal record -> Decision, or None for records that are not a choice."""
    ev, why = rec.get("ev"), rec.get("why")
    reason = why.get("reason", "") if isinstance(why, dict) else ""
    source = why.get("source", "?") if isinstance(why, dict) else "?"
    cost = f"  ${rec['cost']:,}" if isinstance(rec.get("cost"), (int, float)) else ""
    tid, kind = rec.get("tid", "?"), rec.get("kind", "?")
    if ev == "place":
        what = f"place {tid} ({kind}){cost}"
    elif ev == "upgrade":
        what = f"upgrade {tid} {rec.get('cross_before', '?')} -> {rec.get('cross_after', '?')}{cost}"
    elif ev == "sell":
        what = f"sell {tid} ({kind} {rec.get('cross', '')})"
    elif ev == "place_failed":
        what = f"no spot for {tid} ({kind})"
    elif ev == "hold":
        margin = rec.get("margin")
        source, reason = "hold", str(why or "")
        what = f"hold round {rec.get('rnd')}" + (f" (margin {margin:.2f})" if isinstance(margin, float) else "")
    else:
        return None
    return Decision(source, what, reason, rec.get("rnd"))


def read_journal(lines):
    """The newest game from its journal lines (JSON objects, oldest first)."""
    view = JournalView()
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue          # the line being written, or a cut first line
        if not isinstance(rec, dict):
            continue
        ev = rec.get("ev")
        if ev == "game_start":
            view = JournalView(game=rec)
            continue
        if ev == "place" and rec.get("tid"):
            view.towers[rec["tid"]] = [rec.get("kind"), "0-0-0", rec.get("x"), rec.get("y")]
        elif ev == "upgrade" and rec.get("tid") in view.towers:
            view.towers[rec["tid"]][1] = rec.get("cross_after") or view.towers[rec["tid"]][1]
        elif ev == "sell":
            view.towers.pop(rec.get("tid"), None)
        elif ev == "round":
            view.last_round = rec
            if isinstance(rec.get("margin"), (int, float)):
                view.margins.append((rec.get("rnd"), rec["margin"]))
        elif ev == "game_end":
            view.outcome = rec.get("outcome")
            view.end_round = rec.get("round", rec.get("rnd"))
        d = describe(rec)
        if d:
            view.decisions.append(d)
    view.decisions = view.decisions[-DECISIONS_KEPT:]
    return view


def journal_lines(path):
    """The game_start line (the file's first) plus the file's tail."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return []
    tail = read_tail(path, JOURNAL_TAIL_BYTES)
    return tail if tail and tail[0] == first.rstrip("\n") else [first] + tail


# -- what the build still wants: ghost towers -------------------------------------------

@dataclass
class Ghost:
    """A tower the build wants: one still to place at a planned spot
    (placed False), or a standing tower with upgrades to come."""
    tid: str
    kind: str
    x: float          # screen fractions of the game's client area
    y: float
    target: str | None = None    # the crosspath the plan takes it to
    placed: bool = False
    order: int = 0               # its first step's place in the plan: 0 = next


def remaining_plan(steps, towers):
    """The steps of a strategy's plan that `towers` (tid -> [kind, cross, ...])
    have not done yet - for a bot that writes no hud.json plan."""
    out = []
    for st in steps or ():
        if not isinstance(st, dict):
            continue
        tid = st.get("id")
        if st.get("do") == "place" and not (tid and tid in towers):
            out.append(st)
        elif st.get("do") == "upgrade":
            have = tiers(towers[tid][1]) if tid in towers else (0, 0, 0)
            if not all(h >= w for h, w in zip(have, tiers(st.get("to")))):
                out.append(st)
    return out


def wishes(plan, towers):
    """(ghosts, unplaced) from the plan ahead: a Ghost for every planned
    spot (`at`) and every standing tower the plan still upgrades; unplaced
    are the place steps the bot will find a spot for itself (no `at`)."""
    ghosts, unplaced = {}, []
    for i, st in enumerate(plan or ()):
        tid, do = st.get("id"), st.get("do")
        if do == "place":
            at = st.get("at")
            if at and len(at) == 2 and tid not in ghosts:
                ghosts[tid or f"step{i}"] = Ghost(tid or st.get("kind", "?"), st.get("kind", "?"),
                                                  float(at[0]), float(at[1]), order=i)
            elif not at:
                unplaced.append(st)
        elif do == "upgrade" and tid:
            if tid in ghosts:
                ghosts[tid].target = st.get("to")
            elif tid in towers and towers[tid][2] is not None and towers[tid][3] is not None:
                kind, _cross, x, y = towers[tid][:4]
                ghosts[tid] = Ghost(tid, kind, float(x), float(y), target=st.get("to"), placed=True, order=i)
    return sorted(ghosts.values(), key=lambda g: g.order), unplaced


@dataclass
class Wish:
    """Consecutive plan steps on one tower, said as one wish."""
    tid: str | None
    kind: str | None
    place: bool              # the tower is still to be placed
    to: str | None = None    # the crosspath these steps take it to
    steps: int = 1
    spot: bool = False       # placed at the build's own spot (`at`)

    def text(self):
        """'place v1 (village) -> 0-2-0', 'upgrade sp1 -> 4-2-0 (6 steps)'."""
        kind = f" ({self.kind})" if self.kind else ""
        head = f"place {self.tid or ''}{kind}" if self.place else f"upgrade {self.tid}{kind}"
        tail = f" -> {self.to}" if self.to else ""
        more = f" ({self.steps} steps)" if self.steps > 1 else ""
        return f"{head}{tail}{more}".replace("  ", " ")


def wish_list(plan, towers):
    """The plan ahead as wishes: a run of steps on the same tower becomes
    one ('upgrade sp1' five times -> 'upgrade sp1 -> 4-2-0 (5 steps)')."""
    out = []
    for st in plan or ():
        tid, do = st.get("id"), st.get("do")
        if out and tid and out[-1].tid == tid:
            w = out[-1]
            w.to = st.get("to") or w.to
            w.steps += 1
            continue
        kind = st.get("kind") or (towers.get(tid) or [None])[0]
        out.append(Wish(tid, kind, do == "place", st.get("to"), spot=bool(st.get("at"))))
    return out


def project(fx, fy, rect):
    """Screen fractions of the game's client area -> overlay pixels.
    rect = (left, top, width, height) of that area on the overlay."""
    left, top, width, height = rect
    return left + fx * width, top + fy * height


def find_strategy(root, sid, cache={}):
    """The plan steps of strategy `sid` from strategies/**/*.yaml (a file
    named after it, else one whose text says `id: sid`), or []."""
    if not sid:
        return []
    if sid in cache:
        return cache[sid]
    import yaml
    files = sorted(Path(root, "strategies").rglob("*.yaml"))
    named = [f for f in files if f.stem == sid]
    plan = []
    for f in named + [f for f in files if f not in named]:
        try:
            text = f.read_text(encoding="utf-8")
            if f.stem != sid and not re.search(rf"^id:\s*['\"]?{re.escape(sid)}['\"]?\s*$", text, re.M):
                continue
            doc = yaml.safe_load(text)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        if isinstance(doc, dict) and doc.get("id", f.stem) == sid:
            plan = doc.get("plan") or []
            break
    cache[sid] = plan
    return plan


# -- the black-border board -------------------------------------------------------------

@dataclass
class MapMedals:
    name: str
    won: tuple          # one bool per medal mode, in the game's mode order
    count: int          # modes won, of len(mode_keys)
    black: bool         # every mode won: the map's black border
    chimps: bool        # CHIMPS won


@dataclass
class TierBoard:
    tier: str
    maps: list
    black: int          # maps with their black border


def game_maps():
    """({map: tier}, tier order, mode keys) from the bot's account module:
    the game's own map list where it was extracted, the tiers in the game's
    order (Beginner first) and the 14 medal modes in the game's order."""
    from btd6bot import account as A
    maps = {m: c for m, c in A.MAPS.items() if m not in A.EXCLUDED_MAPS}
    return maps, tuple(A.CATEGORY_XP_MULT), tuple(A.MODE_KEYS)


def mode_difficulties():
    """{mode key: its difficulty button (easy / medium / hard / chimps)},
    so the board can group a map's medals the way the game does."""
    from btd6bot import account as A
    return {k: m.difficulty for k, m in A.MODES.items()}


def border_board(medals, maps, tier_order, mode_keys):
    """Medals ({map: {mode: True}}) -> one TierBoard per tier, maps in the
    game's order. A map has its black border when every mode is won."""
    medals = medals or {}
    out = []
    for tier in tier_order:
        rows = []
        for name, cat in maps.items():
            if cat != tier:
                continue
            won = {k for k, v in (medals.get(name) or {}).items() if v and k in mode_keys}
            rows.append(MapMedals(name, tuple(k in won for k in mode_keys), len(won),
                                  len(won) == len(mode_keys), "chimps" in won))
        out.append(TierBoard(tier, rows, sum(r.black for r in rows)))
    return out


# -- everything together -----------------------------------------------------------------

@dataclass
class Snapshot:
    now: float = 0.0
    state: str = ""                  # state.txt without its time stamp
    quiet: float | None = None       # seconds since bot.log or state.txt last changed
    flags: tuple = ()                # control files present: HOLD, PAUSE, STOP
    level: str = ""
    focus: str = ""
    log: list = field(default_factory=list)          # LogLine, newest last
    next: dict | None = None
    reinforce: dict | None = None
    journal: JournalView | None = None
    hud: dict = field(default_factory=dict)          # a fresh hud.json, else {}
    in_game: bool = False
    game: dict = field(default_factory=dict)         # map, mode, strategy, hero, end_round
    round: int | None = None
    pane_round: int | None = None   # the round Covered Garden's open pane belongs to, as the bot saw it on screen
    now_round: int | None = None    # the round the bot's placement judges ground by (Executor._ground_round)
    pose_round: int | None = None   # Sanctuary: the round whose layout the platforms stand in
    ground_horizon: int | None = None   # Erosion: the last round new ground must last (the phase's end)
    cash: int | None = None
    lives: int | None = None
    margins_ahead: list = field(default_factory=list)  # [(round, margin)] from hud.json
    margins_past: list = field(default_factory=list)   # [(round, margin)] from the journal
    weak: float | None = None
    crisis: float | None = None
    ghosts: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)
    plan: list = field(default_factory=list)         # the plan ahead, as steps
    wishes: list = field(default_factory=list)       # the plan ahead, as Wish
    sizes: dict = field(default_factory=dict)        # kind -> [footprint, range] (game-width fractions)
    planner: dict | None = None
    board: list = field(default_factory=list)        # TierBoard
    board_modes: tuple = ()                          # (mode key, difficulty) in the board's pip order
    version: int = 0                                 # changes whenever a source changed


class Collector:
    """Polls the bot's files under `root` (the repo) and builds Snapshots."""

    def __init__(self, root=ROOT, clock=time.time):
        self.root = Path(root)
        self.logs = self.root / "logs"
        self.clock = clock
        self._seen = {}                 # key -> (mtime, value)
        self._journal_path = None
        self._t_journal_scan = -1e9
        self._t_account_scan = -1e9
        self._board = []
        self._maps = None
        self._modes = ()
        self._acc_seen = None           # the account record the board was built from
        self.version = 0

    def _cached(self, key, path, load):
        """load(path) again only when the file's mtime changed."""
        t = mtime(path)
        old = self._seen.get(key)
        if old is not None and old[0] == t:
            return old[1]
        value = load(path) if t is not None else None
        self._seen[key] = (t, value)
        self.version += 1
        return value

    def _newest_journal(self, now):
        if now - self._t_journal_scan >= JOURNAL_SCAN_S:
            self._t_journal_scan = now
            files = sorted((self.logs / "journal").glob("*.jsonl"))
            self._journal_path = files[-1] if files else None
        return self._journal_path

    def _account_board(self, now):
        if now - self._t_account_scan < ACCOUNT_SCAN_S:
            return self._board
        self._t_account_scan = now
        uid = last_line(self.root / "data" / "current_account.txt").strip()
        if not uid:
            return self._board
        acc = self._cached("account", self.root / "data" / "accounts" / f"{uid}.json", read_json)
        if isinstance(acc, dict) and acc is not self._acc_seen:     # re-read: the medals may have changed
            self._acc_seen = acc
            try:
                if self._maps is None:
                    self._maps = game_maps()
                    diff = mode_difficulties()
                    self._modes = tuple((k, diff.get(k, "")) for k in self._maps[2])
                self._board = border_board(acc.get("medals"), *self._maps)
            except Exception:
                pass        # no account module or an odd file: the board stays as it was
        return self._board

    def poll(self):
        now = self.clock()
        snap = Snapshot(now=now)
        state = self._cached("state", self.logs / "state.txt", last_line) or ""
        snap.state = state.split(" ", 2)[2] if state.count(" ") >= 2 else state
        ages = [now - t for t in (mtime(self.logs / "bot.log"), mtime(self.logs / "state.txt")) if t is not None]
        snap.quiet = max(0.0, min(ages)) if ages else None
        snap.flags = tuple(n for n in CONTROL_FILES if (self.root / n).exists())
        snap.level = self._cached("level", self.logs / "level.txt", last_line) or ""
        focus_t = mtime(self.logs / "focus.txt")
        if focus_t is not None and now - focus_t < FOCUS_STALE_S:
            snap.focus = self._cached("focus", self.logs / "focus.txt", last_line) or ""

        records = self._cached("log", self.logs / "bot.log",
                               lambda p: parse_log(read_tail(p, LOG_TAIL_BYTES))) or []
        snap.log = records[-LOG_LINES_KEPT:]
        snap.next = latest_next(records)
        snap.reinforce = latest_reinforce(records)

        jpath = self._newest_journal(now)
        view = self._cached(f"journal:{jpath}", jpath, lambda p: read_journal(journal_lines(p))) if jpath else None
        snap.journal = view
        hud = self._cached("hud", self.logs / "hud.json", read_json)
        hud = hud if isinstance(hud, dict) else {}
        hud_age = now - hud.get("t", 0) if isinstance(hud.get("t"), (int, float)) else None
        snap.planner = hud.get("planner")
        live_hud = hud.get("phase") == "game" and hud_age is not None and hud_age < STALE_GAME_S
        jt = mtime(jpath) if jpath else None
        live_journal = bool(view and view.game and view.outcome is None and jt and now - jt < JOURNAL_LIVE_S)
        if hud.get("phase") == "menu" and hud_age is not None and hud_age < STALE_GAME_S:
            live_journal = False     # the bot says the match is over
        snap.in_game = live_hud or live_journal
        if live_hud:
            snap.hud = hud
        self._fill_game(snap, view if live_journal or live_hud else None)
        snap.board = self._account_board(now)
        snap.board_modes = self._modes
        snap.version = self.version
        return snap

    def _fill_game(self, snap, view):
        """The match's facts: hud.json first, the journal where it has none."""
        hud = snap.hud
        last = view.last_round if view else {}
        snap.game = dict(hud.get("game") or (view.game if view else {}) or {})
        snap.round = hud.get("round", last.get("rnd"))
        snap.pane_round = hud.get("pane_round")
        snap.now_round = hud.get("now_round")
        snap.pose_round = hud.get("pose_round")
        snap.ground_horizon = hud.get("ground_horizon")
        snap.cash = hud.get("cash", last.get("cash"))
        snap.lives = hud.get("lives", last.get("lives"))
        snap.margins_past = list(view.margins) if view else []
        snap.margins_ahead = [tuple(p) for p in hud.get("margins") or () if len(p) == 2]
        snap.weak, snap.crisis = hud.get("weak"), hud.get("crisis")
        snap.sizes = hud.get("sizes") or {}
        if not snap.in_game:
            return
        if "towers" in hud:
            towers = {t[0]: list(t[1:5]) for t in hud["towers"] if len(t) >= 5}
            plan = hud.get("plan") or []
        else:
            towers = view.towers if view else {}
            plan = remaining_plan(find_strategy(self.root, snap.game.get("strategy")), towers)
        snap.plan = plan
        snap.wishes = wish_list(plan, towers)
        snap.ghosts, snap.unplaced = wishes(plan, towers)
