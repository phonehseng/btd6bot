"""Turn the rolling recording into subtitled highlight clips and daily videos.

How it works
------------
1. The bot's log (logs/bot.log) is split into games: from the planner's
   "NEXT: ..." line to the "RESULT {...}" line.
2. In each finished game the interesting moments are picked from the log:
   the opening (first tower placed), tier 4/5 upgrades, leaks (bursts of lost
   lives), milestone rounds (40 MOAB, 60, 80, 100) and the ending.
3. For each moment, the matching seconds are cut out of the 1-minute
   recording chunks (recorder.py names them rec_YYYYmmdd_HHMMSS.mkv, by
   their start time). A subtitle saying what happened is burned in at the
   bottom, and the bot build (git commit) it was playing with at the top.
4. All clips of a day are joined into one video:
   ~/Videos/BTD6 Bot/BTD6 bot highlights YYYY-MM-DD.mp4
   It tells the development story: whenever the code changed between two
   clips, a short "What changed" card lists the new commits, so early
   clumsy games and later fixes read as a progression.

Run by the recorder every few minutes; can also be run by hand:
    python -m btd6bot.highlights
"""
import json
import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "logs" / "bot.log"
CACHE = Path.home() / ".btd6bot_cache"
REC_DIR = CACHE / "recordings"
CLIP_DIR = CACHE / "highlights"
VIDEO_DIR = Path.home() / "Videos" / "BTD6 Bot"
STATE_FILE = CLIP_DIR / "done.json"
GIT = "C:/Program Files/Git/cmd/git.exe"   # used when git is not on PATH

SEGMENT_SECONDS = 60
MAX_CLIPS_PER_GAME = 6
CARD_SIZE = "1280x800"      # must match the recording (recorder.WIDTH, 16:10)
MILESTONE_ROUNDS = {40: "Round 40: the first MOAB", 60: "Round 60: a BFB arrives",
                    80: "Round 80: ZOMG", 100: "Round 100: the BAD"}
MODE_NAMES = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "chimps": "CHIMPS",
              "impoppable": "Impoppable", "abr": "ABR", "magic_only": "Magic Only",
              "double_hp": "Double HP", "half_cash": "Half Cash", "primary_only": "Primary Only",
              "military_only": "Military Only", "apopalypse": "Apopalypse", "reverse": "Reverse",
              "deflation": "Deflation"}
SUBTITLE_STYLE = ("FontName=Segoe UI,FontSize=20,Bold=1,PrimaryColour=&H00FFFFFF,"
                  "BackColour=&H80000000,BorderStyle=3,Outline=6,Shadow=0,Alignment=2,MarginV=24")
TOP = "{\\an8}"     # libass override tag: put this subtitle at the top centre
CENTRE = "{\\an5}"  # ... in the middle of the screen

log = logging.getLogger("highlights")
TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) ")


# ---------------------------------------------------------------------------
# 1-2. games and their moments, from the bot's log
# ---------------------------------------------------------------------------

def _time(line):
    m = TS.match(line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() + int(m.group(2)) / 1000


def read_games(path=LOG_FILE):
    """Finished games: {start, end, map, mode, outcome, round, lines[(t, text)]}."""
    games, cur = [], None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            t = _time(line)
            if t is None:
                continue
            nxt = re.search(r"NEXT: \[\w+\] (.+?) / (\w+) with", line)
            if nxt:
                cur = {"start": t, "map": nxt.group(1), "mode": nxt.group(2), "lines": []}
                continue
            if cur is None:
                continue
            if "RESULT {" in line:
                out = re.search(r"'outcome': '(\w+)'", line)
                rnd = re.search(r"'round': (\d+)", line)
                cur.update(end=t, outcome=out.group(1) if out else "?", round=int(rnd.group(1)) if rnd else None)
                games.append(cur)
                cur = None
            else:
                cur["lines"].append((t, line[24:].strip()))
    return games


def moments(game):
    """[(t0, t1, text)] worth showing, in time order."""
    mode = MODE_NAMES.get(game["mode"], game["mode"])
    title = f"{game['map']} · {mode}"
    kinds, out = {}, []
    leak_t, leak_n, leak_round, rnd = None, 0, None, None
    for t, text in game["lines"]:
        m = re.search(r"round (\d+)\s+cash", text)
        if m:
            rnd = int(m.group(1))
            if rnd in MILESTONE_ROUNDS:
                out.append((t - 1, t + 10, f"{title} — {MILESTONE_ROUNDS[rnd]}"))
        m = re.search(r"game: placed (\S+) \((\w+)\)", text)
        if m:
            kinds[m.group(1)] = m.group(2)
            if not any("first towers" in o[2] for o in out):
                out.append((t - 2, t + 8, f"{title} — placing the first towers"))
        m = re.search(r"^I game: upgraded (\S+) -> (\d)-(\d)-(\d)", text)
        if m and max(map(int, m.group(2, 3, 4))) >= 4:
            kind = kinds.get(m.group(1), "tower").replace("_", " ")
            out.append((t - 3, t + 5, f"{title} — {kind} upgraded to {m.group(2)}-{m.group(3)}-{m.group(4)}"))
        m = re.search(r"lost (\d+) lives", text)
        if m:
            if leak_t is None or t - leak_t > 6:   # a new burst of leaks
                if leak_n >= 5:
                    out.append((leak_t - 8, leak_t + 3, f"{title} — leak! {leak_n} lives lost on round {leak_round}"))
                leak_t, leak_n, leak_round = t, 0, rnd or 1
            leak_n += int(m.group(1))
    if leak_n >= 5:
        out.append((leak_t - 8, leak_t + 3, f"{title} — leak! {leak_n} lives lost on round {leak_round}"))
    if game["outcome"] == "victory":
        ending = f"{title} — victory, round {game['round']} beaten!"
    else:
        ending = f"{title} — {game['outcome']} on round {game['round']}"
    out.append((game["end"] - 16, game["end"] - 2, ending))
    # keep the opening and the ending, then the rest in time order, capped
    out.sort()
    keep = [out[0], out[-1]] + out[1:-1][: MAX_CLIPS_PER_GAME - 2]
    merged = []
    for a, b, text in sorted(set(keep)):
        if merged and a < merged[-1][1]:     # overlapping: one clip, both texts
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]), merged[-1][2] + "\n" + text.split(" — ")[-1])
        else:
            merged.append((a, b, text))
    return merged


# ---------------------------------------------------------------------------
# the bot's own history: which build was running when
# ---------------------------------------------------------------------------

def commits():
    """[(epoch, short hash, subject)] of the bot's git history, oldest first."""
    for git in ("git", GIT):
        try:
            out = subprocess.run([git, "-C", str(ROOT), "log", "--format=%ct|%h|%s"],
                                 capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            continue
        if out.returncode == 0:
            rows = [line.split("|", 2) for line in out.stdout.splitlines() if line.count("|") >= 2]
            return sorted((int(t), h, subj) for t, h, subj in rows)
    return []


def build_at(t, history):
    """The commit the bot was running at time t (the newest one before it)."""
    older = [c for c in history if c[0] <= t]
    return older[-1] if older else None


# ---------------------------------------------------------------------------
# 3. cutting clips out of the recording chunks
# ---------------------------------------------------------------------------

def chunks():
    """[(start epoch, path)] of recording chunks, oldest first."""
    out = []
    for f in REC_DIR.glob("rec_*.mkv"):
        m = re.match(r"rec_(\d{8})_(\d{6})\.mkv$", f.name)
        if m:
            out.append((datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp(), f))
    return sorted(out)


def _encoder_args(ffmpeg):
    out = subprocess.run([str(ffmpeg), "-hide_banner", "-encoders"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    if " h264_nvenc " in out:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "26", "-r", "30", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", "30", "-pix_fmt", "yuv420p"]


def _srt_time(seconds):
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _write_srt(path, cues):
    """cues: [(start s, end s, text)] -> an .srt file."""
    body = "".join(f"{i}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(cues, 1))
    path.write_text(body, encoding="utf-8")


def cut_clip(ffmpeg, t0, t1, text, out_path, label=""):
    """Cut [t0, t1] from the chunks with `text` burned in at the bottom and
    `label` (the bot build) at the top. False if that time was not recorded."""
    parts = [(s, p) for s, p in chunks() if s < t1 and s + SEGMENT_SECONDS > t0]
    if not parts or parts[0][0] > t0 + 1 or parts[-1][0] + SEGMENT_SECONDS < t1 - 1:
        return False  # the recorder was not running for (all of) this moment
    work = out_path.parent
    work.mkdir(parents=True, exist_ok=True)
    lst = work / (out_path.stem + ".txt")
    with open(lst, "w", encoding="utf-8") as f:
        for start, path in parts:
            f.write(f"file '{path.as_posix()}'\n")
            f.write(f"inpoint {max(0.0, t0 - start):.2f}\n")
            f.write(f"outpoint {min(float(SEGMENT_SECONDS), t1 - start):.2f}\n")
    srt = work / (out_path.stem + ".srt")
    dur = t1 - t0
    cues = [(0, dur, text)] + ([(0, dur, TOP + label)] if label else [])
    _write_srt(srt, cues)
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
           "-i", lst.name, "-vf", f"scale={CARD_SIZE.replace('x', ':')},subtitles={srt.name}:force_style='{SUBTITLE_STYLE}'",
           *_encoder_args(ffmpeg), "-an", out_path.name]
    done = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
    for tmp in (lst, srt):
        tmp.unlink(missing_ok=True)
    if done.returncode != 0:
        log.warning("clip failed: %s", done.stderr[-300:])
        return False
    return True


def title_card(ffmpeg, text, out_path, seconds=4.0):
    """A plain card with centred text, encoded like the clips (joinable)."""
    srt = out_path.with_suffix(".srt")
    _write_srt(srt, [(0, seconds, CENTRE + text)])
    style = SUBTITLE_STYLE.replace("FontSize=20", "FontSize=17")
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"color=c=0x101418:s={CARD_SIZE}:r=30:d={seconds}",
           "-vf", f"subtitles={srt.name}:force_style='{style}'",
           *_encoder_args(ffmpeg), "-an", out_path.name]
    done = subprocess.run(cmd, cwd=str(out_path.parent), capture_output=True, text=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    srt.unlink(missing_ok=True)
    if done.returncode != 0:
        log.warning("title card failed: %s", done.stderr[-300:])
    return done.returncode == 0


# ---------------------------------------------------------------------------
# 4. the daily video
# ---------------------------------------------------------------------------

def build_day_video(ffmpeg, day):
    """Join every clip of `day` (YYYY-MM-DD) into one video, in time order,
    with a "What changed" card wherever the bot's code changed in between."""
    folder = CLIP_DIR / day
    clips = sorted(folder.glob("clip_*.mp4"), key=lambda c: int(c.name.split("_")[1]))
    if not clips:
        return None
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    history = commits()
    order, prev_t = [], None
    for clip in clips:
        t = int(clip.name.split("_")[1])
        new = [c for c in history if prev_t is not None and prev_t < c[0] <= t]
        if new:   # the code changed since the previous clip
            card = folder / f"card_{t}.mp4"
            if not card.exists():
                lines = [subj[:80] for _, _, subj in new[-4:]]
                more = f"\n(+{len(new) - 4} more)" if len(new) > 4 else ""
                title_card(ffmpeg, "What changed:\n" + "\n".join(lines) + more, card)
            if card.exists():
                order.append(card)
        order.append(clip)
        prev_t = t
    lst = folder / "all.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in order), encoding="utf-8")
    out = VIDEO_DIR / f"BTD6 bot highlights {day}.mp4"
    subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(out)], capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    return out


def update(ffmpeg):
    """Clip every newly finished game whose recording is complete; rebuild
    the day videos that got new clips. Returns the days updated."""
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        done = set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        done = set()
    days, now = set(), time.time()
    history = commits()
    for game in read_games():
        key = f"{game['start']:.0f}"
        if key in done or now - game["end"] < SEGMENT_SECONDS + 15:
            continue  # done already, or its last chunk is still being written
        day = datetime.fromtimestamp(game["start"]).strftime("%Y-%m-%d")
        made = 0
        for i, (t0, t1, text) in enumerate(moments(game)):
            build = build_at(t0, history)
            label = f"bot build {build[1]} · {datetime.fromtimestamp(t0):%b %d %H:%M}" if build else ""
            if cut_clip(ffmpeg, t0, t1, text, CLIP_DIR / day / f"clip_{int(t0)}_{i}.mp4", label):
                made += 1
        done.add(key)
        if made:
            days.add(day)
            log.info("%d highlight clips from %s %s", made, game["map"], game["mode"])
    STATE_FILE.write_text(json.dumps(sorted(done)), encoding="utf-8")
    for day in days:
        log.info("daily highlights updated: %s", build_day_video(ffmpeg, day))
    return days


if __name__ == "__main__":
    from .recorder import ffmpeg_path
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(update(ffmpeg_path()))
