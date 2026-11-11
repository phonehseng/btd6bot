"""The game journal: what one game bought, sold and leaked, and why it ended.

bot.log says what happened in words and rotates within a day; a lost game's
case folder (losses.py) keeps a cut of it, a won game keeps nothing. The
journal is the same game as data, one JSON object per line, kept for
KEEP_DAYS days in

    logs/journal/<YYYYmmdd_HHMMSS>_<map>_<mode>.jsonl

Every line has t (unix time), ev (the event) and rnd (the round the bot was
tracking when it was written). The events:

    game_start  map, mode, strategy, hero, the mode's rules, account boosts
    place       tid, kind, x, y, cost, why     (why: who bought it and for what,
    upgrade     tid, kind, path, cross_before, cross_after, cost, why
    sell        tid, kind, cross, spent, why    set by Executor.why; None when unknown)
    place_failed kind, tid, reason              (the game refused every spot)
    round       a snapshot as each round starts: cash, lives, lives lost in the
                round just played, the damage model's margin, the towers
    leak        lives lost, the round's bloon groups with their share of its
                RBE, the properties nothing on the map pops, the blimp check
    hold        Play held back between rounds, and why
    game_end    outcome, round, stats, cause (cause_of_death)
    result      the Monkey Money the game paid, an outside cause if any

tools/journal_report.py sums the journals up (causes of death, leaks by
bloon type, the model's calibration, when each crosspath arrived).

The journal only observes: any failure to write switches it off for the
rest of the game (like forecast.py), it never costs a game.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("journal")

ROOT = Path(__file__).resolve().parents[1]
JOURNAL_DIR = ROOT / "logs" / "journal"
KEEP_DAYS = 14          # journals older than this are pruned
LOOKBACK_ROUNDS = 5     # rounds before a death that cause_of_death looks back over
STAMP = "%Y%m%d_%H%M%S"  # the file name's time stamp, as losses._name writes it


def _plain(value):
    """json.dumps fallback: sets and tuples as lists, anything else as text."""
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(value, key=str) if isinstance(value, (set, frozenset)) else list(value)
    return str(value)


class Journal:
    """One game's journal file. Every write is appended and flushed at once,
    so a crash or a killed bot loses nothing written before it; the events
    are also kept in memory for cause_of_death."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self.events = []
        self.rnd = None        # the round events are filed under (set by round())
        self.off = False       # switched off after the first failed write

    @property
    def active(self):
        return self.path is not None and not self.off

    def _write(self, ev, fields):
        """Append one event; returns it, or None when the journal is off."""
        if not self.active:
            return None
        try:
            rec = {"t": round(time.time(), 2), "ev": ev, "rnd": fields.pop("rnd", self.rnd)}
            rec.update(fields)
            line = json.dumps(rec, default=_plain)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
            self.events.append(json.loads(line))   # the same plain values as on disk
            return rec
        except Exception:   # an observer must never cost a game
            log.exception("game journal failed - off for the rest of this game")
            self.off = True
            return None

    def start(self, header):
        """The game_start line (header: what start_game collected)."""
        if header.get("start_round") is not None:
            self.rnd = header["start_round"]
        return self._write("game_start", dict(header))

    def event(self, ev, **fields):
        """Any event: place, upgrade, sell, place_failed, result ..."""
        return self._write(ev, fields)

    def round(self, **fields):
        """A round snapshot; later events are filed under its round."""
        if fields.get("rnd") is not None:
            self.rnd = fields["rnd"]
        return self._write("round", fields)

    def leak(self, **fields):
        return self._write("leak", fields)

    def end(self, **fields):
        return self._write("game_end", fields)

    def close(self):
        """No more writes to this file (the events stay readable)."""
        self.path = None


# The journal used when no game is running: every call does nothing, so
# offline tests and tools that drive Game or Match need no changes.
NULL = Journal(None)

_current = NULL


def current():
    """The running game's journal, or NULL."""
    return _current


def close():
    """End the running game's journal (after its result is written)."""
    global _current
    _current.close()
    _current = NULL


def file_name(map_name, mode, t=None):
    """<YYYYmmdd_HHMMSS>_<Map>_<mode>.jsonl, the stamp style of losses._name."""
    stamp = datetime.fromtimestamp(t or time.time()).strftime(STAMP)
    safe = re.sub(r"[^A-Za-z0-9]+", "", map_name or "unknown")
    return f"{stamp}_{safe}_{mode}.jsonl"


def start_game(map_name, mode, strategy_id, hero, rules, account=None, executor=None):
    """Open a new journal for the game starting now, make it current and
    write its game_start line. A journal left open by a game that broke
    off (no result recorded) is closed first."""
    global _current
    close()
    rules = dict(rules or {})
    try:
        from . import threats as TH
        round_set = TH.set_for_mode(mode)
    except Exception:
        round_set = None
    boosts = dict(getattr(account, "boosts", None) or {})
    header = {
        "map": map_name, "mode": mode, "strategy": strategy_id, "hero": hero,
        "start_round": rules.get("start_round"), "end_round": rules.get("end_round"),
        "round_set": round_set,
        "no_sell": bool(getattr(executor, "no_sell", rules.get("no_sell"))),
        "one_life": bool(rules.get("one_life")),
        "income": rules.get("income", True), "half_cash": bool(rules.get("half_cash")),
        "no_mk": bool(rules.get("no_mk")),
        "account_level": getattr(account, "player_level", None),
        "double_cash": boosts.get("double_cash"),
        "fast_track": bool(boosts.get("fast_track")) and _fast_track_on_for(
            mode, getattr(executor, "strat", None)),
        "rules": rules,
    }
    path = JOURNAL_DIR / file_name(map_name, mode)
    n = 1
    while path.exists():           # two games in one second: keep both
        n += 1
        path = JOURNAL_DIR / file_name(map_name, mode).replace(".jsonl", f"_{n}.jsonl")
    _current = Journal(path)
    _current.start(header)
    return _current


def prune(days=KEEP_DAYS, now=None):
    """Remove journals older than `days`; returns how many went."""
    now = now or time.time()
    gone = 0
    for f in JOURNAL_DIR.glob("*.jsonl"):
        try:
            if now - f.stat().st_mtime > days * 86400:
                f.unlink()
                gone += 1
        except OSError:
            continue
    return gone


def read(path):
    """The events of one journal file (unreadable lines are skipped)."""
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _span(path):
    """(first t, last t) of a journal file, or None."""
    events = read(path)
    times = [e["t"] for e in events if isinstance(e.get("t"), (int, float))]
    return (min(times), max(times)) if times else None


def find_for(t_start, t_end):
    """The journal file whose time span overlaps [t_start, t_end] the most,
    or None (losses.file_loss copies it into the case folder)."""
    best, best_overlap = None, None
    for f in JOURNAL_DIR.glob("*.jsonl"):
        span = _span(f)
        if span is None:
            continue
        # 0 for a journal of one instant inside the game (a single line)
        overlap = min(span[1], t_end) - max(span[0], t_start)
        if overlap >= 0 and (best_overlap is None or overlap > best_overlap):
            best, best_overlap = f, overlap
    return best


# ---------------------------------------------------------------------------
# cause of death: a pure function over the journal's events
# ---------------------------------------------------------------------------

PURCHASES = ("place", "upgrade")


def _cheapest_recent(purchases, n=LOOKBACK_ROUNDS):
    """The lowest price among the last `n` purchases (the cash that would
    have bought something), or None."""
    costs = [e.get("cost") for e in purchases[-n:] if (e.get("cost") or 0) > 0]
    return min(costs) if costs else None


def _death_detail(death_leak, purchases, snapshots):
    """What a reader wants next to the category: the death round's biggest
    bloon groups, the last purchases with their reasons, what the plan was
    waiting on."""
    groups = sorted((death_leak or {}).get("groups") or (), key=lambda g: -(g.get("share") or 0))[:3]
    last = [{k: e.get(k) for k in ("ev", "rnd", "tid", "kind", "cross_after", "cost", "why") if k in e}
            for e in purchases[-3:]]
    return {"top_groups": groups, "last_purchases": last,
            "waiting": snapshots[-1].get("waiting") if snapshots else None}


def cause_of_death(events, rnd, stats=None):
    """Why a lost game was lost, from its journal events: {category, round,
    detail, evidence}. Categories, the first that applies:

    property_gap          the death round brought a property (camo, lead,
                          purple ...) nothing on the map could pop
    auto_start            the game's Auto Start was on: no round could be held
    placement             plan steps were given up, or the game refused spots
                          in the last LOOKBACK_ROUNDS rounds
    model_warned_unfunded the damage model rated a round before the death
                          under forecast.CRISIS_MARGIN while cash would have
                          bought something
    idle_cash             the death round started with more cash than the
                          cheapest recent purchase
    model_overrated       the model rated the death round at 1 or more, and
                          it leaked anyway
    unknown               none of these
    """
    from .forecast import CRISIS_MARGIN
    stats = stats or {}
    leaks = [e for e in events if e.get("ev") == "leak"]
    death_leak = next((e for e in reversed(leaks) if e.get("rnd") == rnd), None)
    if death_leak is None and rnd is None and leaks:
        death_leak = leaks[-1]
    purchases = [e for e in events if e.get("ev") in PURCHASES]
    snapshots = [e for e in events if e.get("ev") == "round"]
    recent = (lambda e: rnd is None or e.get("rnd") is None
              or rnd - LOOKBACK_ROUNDS <= e["rnd"] <= rnd)
    death_snap = next((e for e in reversed(snapshots) if e.get("rnd") == rnd), None)
    cheapest = _cheapest_recent(purchases)
    out = {"round": rnd, "detail": _death_detail(death_leak, purchases, snapshots)}

    def verdict(category, evidence):
        return dict(out, category=category, evidence=evidence)

    if death_leak and death_leak.get("uncovered"):
        return verdict("property_gap", f"round {rnd} brought {', '.join(death_leak['uncovered'])} "
                                       f"that nothing on the map pops")
    if stats.get("auto_start"):
        return verdict("auto_start", "the Play button was never idle: Auto Start is on, no round could be held")
    failed = [e for e in events if e.get("ev") == "place_failed" and recent(e)]
    if (stats.get("steps_given_up") or 0) > 0 or failed:
        return verdict("placement", f"{stats.get('steps_given_up') or 0} plan steps given up, "
                                    f"{len(failed)} placements refused in the last {LOOKBACK_ROUNDS} rounds")
    if cheapest is not None:
        warned = [e for e in snapshots
                  if e.get("margin") is not None and e["margin"] < CRISIS_MARGIN
                  and (e.get("cash") or 0) > cheapest and recent(e) and (rnd is None or e.get("rnd") != rnd)]
        if warned:
            w = warned[-1]
            return verdict("model_warned_unfunded",
                           f"round {w.get('rnd')} was rated {w['margin']:.2f} with ${w.get('cash')} "
                           f"in hand (cheapest recent purchase ${cheapest})")
        if death_snap and (death_snap.get("cash") or 0) > cheapest:
            return verdict("idle_cash", f"round {rnd} started with ${death_snap.get('cash')} "
                                        f"(cheapest recent purchase ${cheapest})")
    if death_snap and death_leak and (death_snap.get("margin") or 0) >= 1:
        return verdict("model_overrated", f"the model rated round {rnd} at {death_snap['margin']:.2f} "
                                          f"and it leaked")
    return verdict("unknown", "no journal evidence points at one cause")


def _fast_track_on_for(mode, strategy=None):
    """Was the Fast Track toggle on for a game in `mode` with `strategy`
    (boosts.fast_track_wanted)?"""
    try:
        from .boosts import fast_track_wanted
        return fast_track_wanted(mode, strategy if isinstance(strategy, dict) else None)
    except Exception:
        return True
