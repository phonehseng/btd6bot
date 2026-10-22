"""Sped-up recordings of whole games ("full runs").

Highlight clips (highlights.py) show a few seconds per moment. A full run is
the opposite: one game from the first tower to the end screen, sped up so a
45-minute CHIMPS game plays in a few minutes, with captions for what the bot
did and the round counter in the corner.

Which games get one
-------------------
* every CHIMPS game (win or loss) - the hardest mode, the one worth watching
* the first game of each other Hard-family mode per day (Hard, Magic Only,
  Double HP, Half Cash, ABR, Impoppable) - so there is something to watch
  while CHIMPS is still locked, and day-by-day progress is visible
* any game whose start time is listed in logs/fullrun_requests.txt (one
  "YYYY-MM-DD HH:MM" per line) - to ask for a particular game by hand

Output: ~/Videos/BTD6 Bot/Full runs/<date> <time> <map> <mode> (<outcome>) xN.mp4
a short title card followed by the sped-up game.

The recording chunks are kept for recorder.KEEP_HOURS (4 h); games are capped
at a little over an hour (match.Match.play), and this pass runs every few
minutes, so a finished game is always still on disk when it is processed.

Run by the recorder after the highlight pass; can also be run by hand:
    python -m btd6bot.timelapse
"""
import json
import logging
import math
import re
import subprocess
import time
from datetime import datetime

from . import highlights as H

OUT_DIR = H.VIDEO_DIR / "Full runs"
WORK_DIR = H.CLIP_DIR / "fullruns"
STATE_FILE = WORK_DIR / "done.json"
REQUESTS_FILE = H.ROOT / "logs" / "fullrun_requests.txt"

ALWAYS_MODES = {"chimps"}
DAILY_MODES = {"hard", "magic_only", "double_hp", "half_cash", "abr", "impoppable"}
TARGET_SECONDS = 6 * 60       # aim for about this long a video ...
MIN_SPEED, MAX_SPEED = 4, 24  # ... within these speed-ups
CAPTION_SECONDS = 2.0         # how long an event caption stays up (video time)
MIN_COVERAGE = 0.8            # skip games the recorder mostly missed
FFMPEG_TIMEOUT = 3600
# ffmpeg keeps only the {\anN} position tag of an SRT's override tags; the
# size goes in an HTML-style <font> tag, which it converts.
CORNER = '{\\an1}<font size="12">%s</font>'   # bottom-left, smaller text

log = logging.getLogger("timelapse")


# ---------------------------------------------------------------------------
# which games
# ---------------------------------------------------------------------------

def _requested_starts():
    """Start minutes ("YYYY-MM-DD HH:MM") asked for in logs/fullrun_requests.txt."""
    try:
        lines = REQUESTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def wanted(games, done):
    """The finished games that should get a full run, oldest first.
    done: {game key: video path, or "" when it could not be made}."""
    requested = _requested_starts()
    seen_today = set()  # (day, mode) pairs that already have a full-run video
    for game in games:
        day = datetime.fromtimestamp(game["start"]).strftime("%Y-%m-%d")
        if done.get(f"{game['start']:.0f}"):
            seen_today.add((day, game["mode"]))
    out = []
    for game in games:
        day = datetime.fromtimestamp(game["start"]).strftime("%Y-%m-%d")
        minute = datetime.fromtimestamp(game["start"]).strftime("%Y-%m-%d %H:%M")
        if f"{game['start']:.0f}" in done:
            continue
        if game["mode"] in ALWAYS_MODES or minute in requested:
            out.append(game)
        elif game["mode"] in DAILY_MODES and (day, game["mode"]) not in seen_today:
            seen_today.add((day, game["mode"]))
            out.append(game)
    return out


# ---------------------------------------------------------------------------
# the game's footage: which chunks, and where a log time lands in the video
# ---------------------------------------------------------------------------

def footage(t0, t1):
    """The recorded pieces of [t0, t1]: [(chunk path, in s, out s, real start)].
    Gaps (the recorder was restarted) are simply left out."""
    pieces = []
    for start, path in H.chunks():
        a, b = max(t0, start), min(t1, start + H.SEGMENT_SECONDS)
        if b - a > 0.5:
            pieces.append((path, a - start, b - start, a))
    return pieces


def video_time(t, pieces):
    """Seconds into the joined (not yet sped-up) footage at log time t, or
    None if t falls in a gap."""
    offset = 0.0
    for _, a, b, real in pieces:
        if real <= t <= real + (b - a):
            return offset + (t - real)
        offset += b - a
    return None


def pick_speed(seconds):
    """A round speed-up that brings the game close to TARGET_SECONDS."""
    speed = math.ceil(seconds / TARGET_SECONDS)
    speed = max(MIN_SPEED, min(MAX_SPEED, speed))
    return speed if speed <= 8 else int(math.ceil(speed / 4) * 4)   # 4..8, then 12, 16, 20, 24


# ---------------------------------------------------------------------------
# captions from the bot's log
# ---------------------------------------------------------------------------

def events(game):
    """[(t, text)] worth a caption: towers placed, tier 3+ upgrades, leaks and
    milestone rounds. (Round, cash and lives are on the game's own HUD.)"""
    out, kinds = [], {}
    for t, text in game["lines"]:
        m = re.search(r"round (\d+)\s+cash", text)
        if m and int(m.group(1)) in H.MILESTONE_ROUNDS:
            out.append((t, H.MILESTONE_ROUNDS[int(m.group(1))]))
            continue
        m = re.search(r"game: placed (\S+) \((\w+)\)", text)
        if m:
            kinds[m.group(1)] = m.group(2)
            out.append((t, f"placed a {m.group(2).replace('_', ' ')}"))
            continue
        m = re.search(r"^I game: upgraded (\S+) -> (\d)-(\d)-(\d)", text)
        if m and max(map(int, m.group(2, 3, 4))) >= 3:
            kind = kinds.get(m.group(1), "tower").replace("_", " ")
            out.append((t, f"{kind} -> {m.group(2)}-{m.group(3)}-{m.group(4)}"))
            continue
        m = re.search(r"lost (\d+) lives", text)
        if m:
            out.append((t, f"leak: -{m.group(1)} lives"))
    return out


MERGE_SECONDS = 0.8   # captions closer than this (video time) share one cue
MAX_LINES = 3


def captions(game, pieces, speed):
    """Subtitle cues [(start, end, text)] in sped-up video time. Events that
    land almost together share a cue; otherwise a new caption replaces the
    previous one early rather than stacking on top of it."""
    cues = []
    for t, text in events(game):
        vt = video_time(t, pieces)
        if vt is None:
            continue   # happened while the recorder was not running
        start = vt / speed
        if cues and start - cues[-1][0] < MERGE_SECONDS and cues[-1][2].count("\n") < MAX_LINES - 1:
            a, _, old = cues[-1]
            cues[-1] = (a, start + CAPTION_SECONDS, old + "\n" + text)
            continue
        if cues and start < cues[-1][1]:
            cues[-1] = (cues[-1][0], start, cues[-1][2])
        cues.append((start, start + CAPTION_SECONDS, text))
    return cues


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(ffmpeg, game, history):
    """Build the full-run video of one game. Returns its path, or None."""
    # from just before the first tower to a few seconds of the end screen
    # ("game over" is logged on the victory/defeat screen; RESULT only after
    # the bot is back at the menus)
    t0 = next((t for t, text in game["lines"] if "game: placed" in text), game["start"]) - 5
    over = next((t for t, text in game["lines"] if "match: game over" in text), game["end"])
    t1 = min(over + 6, game["end"] + 3)
    pieces = footage(t0, t1)
    recorded = sum(b - a for _, a, b, _ in pieces)
    if recorded < MIN_COVERAGE * (t1 - t0):
        log.info("full run skipped: only %.0f of %.0f s recorded (%s %s)",
                 recorded, t1 - t0, game["map"], game["mode"])
        return None
    speed = pick_speed(recorded)
    mode = H.MODE_NAMES.get(game["mode"], game["mode"])
    build = H.build_at(t0, history)
    when = datetime.fromtimestamp(game["start"])
    name = f"{when:%Y-%m-%d %H%M} {game['map']} {mode} ({game['outcome']} r{game['round']}) x{speed}"
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    work = WORK_DIR / f"{game['start']:.0f}"
    work.mkdir(parents=True, exist_ok=True)

    # the game, sped up, with captions
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\ninpoint {a:.2f}\noutpoint {b:.2f}\n"
                           for p, a, b, _ in pieces), encoding="utf-8")
    # a small label in the bottom-left corner: the game's HUD (lives, cash,
    # round) along the top stays visible
    label = f"{game['map']} · {mode} · x{speed}" + (f" · build {build[1]}" if build else "")
    cues = captions(game, pieces, speed) + [(0, recorded / speed, CORNER % label)]
    H._write_srt(work / "subs.srt", sorted(cues))
    body = work / "body.mp4"
    vf = (f"setpts=(PTS-STARTPTS)/{speed},fps=30,scale={H.CARD_SIZE.replace('x', ':')},"
          f"subtitles=subs.srt:force_style='{H.SUBTITLE_STYLE}'")
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
           "-i", lst.name, "-vf", vf, *H._encoder_args(ffmpeg), "-an", body.name]
    # below-normal priority: the bot's screen reading comes first
    done = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
                          creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    if done.returncode != 0:
        log.warning("full run failed: %s", done.stderr[-300:])
        return None

    # a title card in front, then join (same encoding: no re-encode)
    card = work / "card.mp4"
    result = "victory!" if game["outcome"] == "victory" else f"{game['outcome']} on round {game['round']}"
    H.title_card(ffmpeg, f"Full run · {when:%b %d %H:%M}\n{game['map']} · {mode}\n{result}\n"
                         f"{recorded / 60:.0f} minutes at x{speed}", card)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.mp4"
    joined = work / "all.txt"
    joined.write_text("".join(f"file '{p.as_posix()}'\n" for p in (card, body) if p.exists()), encoding="utf-8")
    subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(joined), "-c", "copy", str(out)], capture_output=True, timeout=600)
    for f in work.iterdir():      # the pieces are not needed once joined
        f.unlink(missing_ok=True)
    work.rmdir()
    return out if out.exists() else None


def update(ffmpeg):
    """Make full runs of newly finished games that qualify. Returns the paths."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        done = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        done = {}
    made, now, history = [], time.time(), H.commits()
    for game in wanted(H.read_games(), done):
        if now - game["end"] < H.SEGMENT_SECONDS + 15:
            continue  # its last chunk is still being written
        out = render(ffmpeg, game, history)
        done[f"{game['start']:.0f}"] = str(out) if out else ""
        STATE_FILE.write_text(json.dumps(done, indent=1), encoding="utf-8")
        if out:
            log.info("full run saved: %s", out)
            made.append(out)
    return made


if __name__ == "__main__":
    from .recorder import ffmpeg_path
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for path in update(ffmpeg_path()):
        print(path)
