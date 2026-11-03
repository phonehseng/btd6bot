"""Loss circuit breaker: when games keep being lost, play only safe medals.

The owner's rule for unattended running: "if all is going wrong with a bunch
of losses, just beat every single easy map with every single medal".

    normal --(TRIP_LOSSES defeats among the last TRIP_WINDOW games)--> safe
    safe   --(exit_wins wins in a row)--------------------------------> normal

In safe mode the bot plays Easy-family medals only (Easy, Primary Only,
Deflation); when every one of those is earned, Medium-family medals. Each
time the breaker trips again, the wins needed to leave safe mode double
(8, 16, 32, ...), so a bot that keeps failing at hard modes spends ever
longer earning safe medals before it tries again; every clean day (no trip,
no defeat) forgives one trip, even while safe mode is on.

State lives in logs/safe_mode.json; logs/results.jsonl (progress.py) is the
game history. Only "defeat" counts as a loss: games ended by something
outside the bot (another sign-in, a closed game) are not its fault.
"""
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("safety")

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "logs" / "safe_mode.json"
RESULTS_FILE = ROOT / "logs" / "results.jsonl"

TRIP_WINDOW = 6          # recent games looked at
TRIP_LOSSES = 3          # defeats among them that trip the breaker
BASE_EXIT_WINS = 8       # wins in a row that end safe mode (doubles per trip)
FORGIVE_AFTER = 24 * 3600  # a trip older than this no longer doubles the next exit


def _load():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"on": False, "since": 0, "streak": 0, "trips": 0, "last_trip": 0}


def _save(state):
    try:
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass


def _recent(n):
    try:
        lines = RESULTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-200:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows[-n:]


def _last_defeat_time():
    """Unix time of the newest defeat in results.jsonl (0 if none is dated)."""
    return max((g.get("t") or 0 for g in _recent(200) if g.get("outcome") == "defeat"), default=0)


def effective_trips(state, now=None):
    """The trip count that sets the wins needed, after forgiveness: every full
    FORGIVE_AFTER without a trip or a defeat forgives one trip (never below 1).

    Before 2026-11-03 a clean day was forgiven only when the breaker tripped
    again, so four trips from 2026-10-24 still asked for 64 wins in a row ten
    days later - with safe mode playing only p >= 0.85 games, almost none of
    which were left, the bot idled instead of earning its way out."""
    trips = state.get("trips", 1)
    quiet_since = max(state.get("last_trip", 0), _last_defeat_time())
    forgiven = int(max(0.0, (now or time.time()) - quiet_since) // FORGIVE_AFTER)
    return max(1, trips - forgiven)


def exit_wins(state, now=None):
    """Wins in a row that end safe mode: BASE_EXIT_WINS doubled per trip."""
    return BASE_EXIT_WINS * 2 ** (effective_trips(state, now) - 1)


def active():
    """Is the bot in safe mode (Easy-family medals first)?"""
    return bool(_load().get("on"))


def status():
    """One line for the log and the status pane."""
    s = _load()
    if not s.get("on"):
        return "normal"
    return f"SAFE MODE ({s.get('streak', 0)}/{exit_wins(s)} wins to leave)"


def after_game(outcome):
    """Update the breaker after a finished game (results.jsonl already has it).
    Returns the new status line."""
    s = _load()
    now = time.time()
    if s.get("on"):
        s["streak"] = s.get("streak", 0) + 1 if outcome == "victory" else 0
        if s["streak"] >= exit_wins(s):
            log.warning("safe mode over after %d wins in a row - trying harder modes again", s["streak"])
            s.update(on=False, streak=0)
    else:
        games = _recent(TRIP_WINDOW)
        losses = sum(1 for g in games if g.get("outcome") == "defeat")
        if outcome == "defeat" and losses >= TRIP_LOSSES:
            if now - s.get("last_trip", 0) > FORGIVE_AFTER:
                s["trips"] = 0
            s.update(on=True, since=now, streak=0, trips=s.get("trips", 0) + 1, last_trip=now)
            log.warning("%d of the last %d games lost - SAFE MODE: Easy-family medals until "
                        "%d wins in a row", losses, len(games), exit_wins(s))
    _save(s)
    return status()
