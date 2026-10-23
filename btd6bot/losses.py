"""A case file for every lost game, kept for the caretaker to diagnose.

The recorder keeps only the last few hours of screen recording, so after
each defeat this module (run by the recorder, like highlights.py) saves what
is needed to find out why, in its own folder:

    ~/.btd6bot_cache/losses/<YYYYmmdd_HHMMSS>_<map>_<mode>/
        report.md        the result, what to look at, and "status: new"
        game.log         the bot's log for the game (NEXT ... RESULT)
        last_minutes.mp4 the last LAST_SECONDS before the defeat, with the
                         game's own sound when it was recorded
        frames/          stills: every FINAL_STEP s over the last FINAL_SPAN s,
                         and one every OVERVIEW_STEP s over the whole game
        diagnosis.md     written by the caretaker once it has looked (it then
                         sets "status: handled" in report.md)

Games lost before the recorder had them (older than its buffer) still get
the log and the report. Run by hand:  python -m btd6bot.losses
"""
import json
import logging
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .highlights import LOG_FILE, REC_DIR, SEGMENT_SECONDS, chunks, read_games

log = logging.getLogger("losses")

LOSS_DIR = Path.home() / ".btd6bot_cache" / "losses"
LAST_SECONDS = 180       # video kept before the defeat
FINAL_SPAN, FINAL_STEP = 90, 3          # stills, closely, at the end
OVERVIEW_STEP = 30                      # stills over the whole game
CLOSED_AFTER = 75        # seconds after the game before its last chunk is complete
BACKFILL_HOURS = 36      # older losses are not filed (their logs may be gone too)
KEEP_VIDEO_DAYS = 14     # handled cases lose their video and stills after this
LOSING = ("defeat",)     # outcomes filed as losses


def _name(game):
    stamp = datetime.fromtimestamp(game["end"]).strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9]+", "", game["map"])
    return f"{stamp}_{safe}_{game['mode']}"


def _games():
    """Finished games from the current log and the previous one."""
    out = []
    for path in (LOG_FILE.with_name(LOG_FILE.name + ".1"), LOG_FILE):
        if path.exists():
            out += read_games(path)
    return out


def _result_for(game):
    """The game's line in logs/results.jsonl (strategy, lives lost...)."""
    path = LOG_FILE.with_name("results.jsonl")
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return {}
    near = [r for r in rows if abs(r.get("t", 0) - game["end"]) < 120 and r.get("map") == game["map"]]
    return near[-1] if near else {}


def _defeat_time(game):
    """When the game was lost: the bot's "game over" line (the RESULT line
    that ends the log's game comes ~20 s later, after going home)."""
    over = [t for t, text in game["lines"] if "game over" in text]
    return over[-1] if over else game["end"]


def _concat_list(path, t0, t1, files):
    """An ffmpeg concat list covering [t0, t1] from [(start epoch, file)]."""
    with open(path, "w", encoding="utf-8") as f:
        for start, p in files:
            f.write(f"file '{p.as_posix()}'\n")
            f.write(f"inpoint {max(0.0, t0 - start):.2f}\n")
            f.write(f"outpoint {min(float(SEGMENT_SECONDS) + 1, t1 - start):.2f}\n")


def _audio_parts(t0, t1):
    """[(start epoch, file)] of the game-audio minutes (gameaudio.py) over [t0, t1]."""
    out = []
    for f in [*REC_DIR.glob("aud_*.opus"), *REC_DIR.glob("aud_*.wav")]:
        m = re.match(r"aud_(\d{8})_(\d{6})_(\d{3})\.", f.name)
        if m:
            start = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp() + int(m.group(3)) / 1000
            if start < t1 and start + SEGMENT_SECONDS + 2 > t0:
                out.append((start, f))
    return sorted(out)


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=600,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def _cut(ffmpeg, folder, game):
    """last_minutes.mp4 and frames/ from the recording; what was saved."""
    lost = _defeat_time(game)
    t1 = lost + 5                    # a few seconds of the defeat screen
    t0 = max(game["start"], lost - LAST_SECONDS)
    video = [(s, p) for s, p in chunks() if s < t1 and s + SEGMENT_SECONDS > game["start"]]
    if not video:
        return []
    saved = []
    lst = folder / "video.txt"
    _concat_list(lst, t0, t1, [(s, p) for s, p in video if s + SEGMENT_SECONDS > t0])
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst.name]
    audio = _audio_parts(t0, t1)
    if audio:
        _concat_list(folder / "audio.txt", t0, t1, audio)
        cmd += ["-f", "concat", "-safe", "0", "-i", "audio.txt", "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-shortest", "last_minutes.mp4"]
    if _run(cmd, folder).returncode == 0:
        saved.append("last_minutes.mp4" + (" (with game sound)" if audio else ""))
    frames = folder / "frames"
    frames.mkdir(exist_ok=True)
    # close-ups of the end, then an overview of the whole game
    f0 = max(game["start"], lost - FINAL_SPAN)
    _concat_list(folder / "end.txt", f0, t1, [(s, p) for s, p in video if s + SEGMENT_SECONDS > f0])
    _run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "end.txt",
          "-vf", f"fps=1/{FINAL_STEP},scale=960:-2", "-q:v", "4", "frames/end_%03d.jpg"], folder)
    _concat_list(folder / "all.txt", game["start"], t1, video)
    _run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "all.txt",
          "-vf", f"fps=1/{OVERVIEW_STEP},scale=960:-2", "-q:v", "4", "frames/game_%03d.jpg"], folder)
    for tmp in ("video.txt", "audio.txt", "end.txt", "all.txt"):
        (folder / tmp).unlink(missing_ok=True)
    n_end, n_all = len(list(frames.glob("end_*.jpg"))), len(list(frames.glob("game_*.jpg")))
    if n_end or n_all:
        saved.append(f"frames/: {n_end} stills every {FINAL_STEP} s over the last {FINAL_SPAN} s (end_*.jpg), "
                     f"{n_all} every {OVERVIEW_STEP} s over the game (game_*.jpg)")
    return saved


def file_loss(ffmpeg, game):
    """Write the case folder for one lost game; returns its path."""
    folder = LOSS_DIR / _name(game)
    folder.mkdir(parents=True, exist_ok=True)
    res = _result_for(game)
    with open(folder / "game.log", "w", encoding="utf-8") as f:
        for t, text in game["lines"]:
            f.write(datetime.fromtimestamp(t).strftime("%H:%M:%S ") + text + "\n")
    saved = _cut(ffmpeg, folder, game) if ffmpeg else []
    started = datetime.fromtimestamp(game["start"]).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Lost: {game['map']} {game['mode']}, round {game.get('round')}",
        "",
        "status: new",
        "",
        f"- played {started}, {round((game['end'] - game['start']) / 60, 1)} min, outcome {game.get('outcome')}",
        f"- strategy: {res.get('strategy', '?')}; lives lost: {res.get('lives_lost', '?')}",
        "- game.log: the bot's log for the game (placements, upgrades, threats, leaks, the model's ratings)",
        *[f"- {s}" for s in saved],
        *([] if saved else ["- no recording: the game is older than the recorder's buffer"]),
        "",
        "For the caretaker: find the root cause (game.log first, then the stills),",
        "fix it in code or strategies with an offline test, write diagnosis.md here",
        "(cause, evidence, fix and commit) and change the status above to handled.",
    ]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("loss filed: %s (%s)", folder.name, "; ".join(saved) or "log only")
    return folder


def prune(now=None):
    """Handled cases keep their report, log and diagnosis; their video and
    stills go after KEEP_VIDEO_DAYS."""
    now = now or time.time()
    for folder in LOSS_DIR.glob("*_*"):
        report = folder / "report.md"
        try:
            if "status: handled" not in report.read_text(encoding="utf-8"):
                continue
            if now - report.stat().st_mtime < KEEP_VIDEO_DAYS * 86400:
                continue
        except OSError:
            continue
        (folder / "last_minutes.mp4").unlink(missing_ok=True)
        shutil.rmtree(folder / "frames", ignore_errors=True)


def update(ffmpeg, now=None):
    """File every loss not filed yet whose recording is complete. Returns
    the folders written."""
    now = now or time.time()
    LOSS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for game in _games():
        if game.get("outcome") not in LOSING or "end" not in game:
            continue
        if now - game["end"] > BACKFILL_HOURS * 3600 or now - game["end"] < CLOSED_AFTER:
            continue
        if (LOSS_DIR / _name(game) / "report.md").exists():
            continue
        try:
            out.append(file_loss(ffmpeg, game))
        except Exception:
            log.exception("filing the loss of %s %s failed", game.get("map"), game.get("mode"))
    prune(now)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s")
    from .recorder import ffmpeg_path
    for f in update(ffmpeg_path()):
        print(f)
