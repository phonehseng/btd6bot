"""Dev log: a voiceover script and a video of how the bot's bugs were found and fixed.

The git history is the script. Every commit message says what went wrong and
what changed; this tool lays the commits of one day out as narration, and
pairs each with footage from the rolling recording (btd6bot/recorder.py):

  * BEFORE - the last problem the bot's log recorded before the commit (an
    error, a defeat, a leak, a refused spot, a misread) - what the bug looked like
  * AFTER  - the start of the bot's next game on the new code

Output for a day YYYY-MM-DD:
  docs/devlog/YYYY-MM-DD.md                  the voiceover script (commit it)
  ~/Videos/BTD6 Bot/BTD6 bot devlog YYYY-MM-DD.mp4
      per commit: a title card, the BEFORE clip, the AFTER clip

    python tools/devlog.py              # today
    python tools/devlog.py 2026-10-22   # another day

Moments before the recorder was running have no footage; the script still
covers them.
"""
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from btd6bot import highlights as H  # noqa: E402
from btd6bot.recorder import ffmpeg_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEVLOG_DIR = ROOT / "docs" / "devlog"
PROBLEM = re.compile(r"game loop error|defeat|lost \d+ lives|invalid for|refus|misread|"
                     r"giving up|benched|could not|not responding|back at the menus", re.I)
BEFORE_WINDOW = 30 * 60      # look this far back for the problem a commit fixed
AFTER_WINDOW = 20 * 60       # and this far ahead for the next game


def day_commits(day):
    """[(epoch, hash, subject, body)] committed on `day`, oldest first."""
    start = datetime.strptime(day, "%Y-%m-%d")
    end = start + timedelta(days=1)
    for git in ("git", H.GIT):
        try:
            out = subprocess.run([git, "-C", str(ROOT), "log", f"--since={start:%Y-%m-%d %H:%M}",
                                  f"--until={end:%Y-%m-%d %H:%M}", "--format=%ct%x1f%h%x1f%s%x1f%b%x1e"],
                                 capture_output=True, text=True, timeout=30)
        except OSError:
            continue
        if out.returncode == 0:
            rows = []
            for rec in out.stdout.split("\x1e"):
                parts = rec.strip("\n").split("\x1f")
                if len(parts) == 4:
                    rows.append((int(parts[0]), parts[1], parts[2], parts[3].strip()))
            return sorted(rows)
    return []


def log_lines():
    """[(epoch, text)] of the bot log."""
    out = []
    with open(H.LOG_FILE, encoding="utf-8", errors="ignore") as f:
        for line in f:
            t = H._time(line)
            if t is not None:
                out.append((t, line[24:].strip()))
    return out


def before_moment(lines, t):
    """The last problem logged in the half hour before time t."""
    hits = [(lt, text) for lt, text in lines if t - BEFORE_WINDOW <= lt < t and PROBLEM.search(text)]
    return hits[-1] if hits else None


def after_moment(lines, t):
    """The first tower placed (a game on the new code) after time t."""
    hits = [(lt, text) for lt, text in lines if t < lt <= t + AFTER_WINDOW and "game: placed" in text]
    return hits[0] if hits else None


def narration(subject, body):
    """Commit message -> the points to read out: the subject, then one point
    per body bullet or paragraph (wrapped lines are joined back together)."""
    points, current = [subject.rstrip(".") + "."], []
    for raw in body.splitlines() + [""]:
        line = raw.strip()
        if line.lower().startswith(("co-authored-by", "signed-off-by")):
            continue
        starts_point = not line or line.startswith(("-", "*"))
        if starts_point and current:
            points.append(" ".join(current))
            current = []
        if line:
            current.append(line.lstrip("-*").strip())
    return points


def write_script(day, items):
    DEVLOG_DIR.mkdir(parents=True, exist_ok=True)
    out = [f"# Dev log {day}: finding and fixing the bot's bugs", "",
           "Voiceover script built from the day's commits (tools/devlog.py). Each entry:",
           "what the bot did wrong (BEFORE footage), what changed, and the next game (AFTER).", ""]
    for it in items:
        when = datetime.fromtimestamp(it["t"]).strftime("%H:%M")
        out.append(f"## {when} — {it['subject']}  (`{it['hash']}`)")
        out.append("")
        if it["before"]:
            out.append(f"**Before** ({datetime.fromtimestamp(it['before'][0]):%H:%M:%S}): "
                       f"`{it['before'][1][:140]}`" + ("" if it["before_clip"] else " — no footage"))
        out.append("")
        out.append("**Voiceover:**")
        out.append("")
        out.extend(f"- {point}" for point in narration(it["subject"], it["body"]))
        out.append("")
        if it["after"]:
            out.append(f"**After** ({datetime.fromtimestamp(it['after'][0]):%H:%M:%S}): "
                       f"`{it['after'][1][:140]}`" + ("" if it["after_clip"] else " — no footage"))
            out.append("")
    path = DEVLOG_DIR / f"{day}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def build(day):
    ffmpeg = ffmpeg_path()
    lines = log_lines()
    folder = H.CLIP_DIR / f"devlog-{day}"
    folder.mkdir(parents=True, exist_ok=True)
    items, order = [], []
    for t, h, subject, body in day_commits(day):
        it = {"t": t, "hash": h, "subject": subject, "body": body,
              "before": before_moment(lines, t), "after": after_moment(lines, t),
              "before_clip": None, "after_clip": None}
        if ffmpeg:
            card = folder / f"{t}_0_card.mp4"
            if card.exists() or H.title_card(ffmpeg, f"{datetime.fromtimestamp(t):%H:%M}  build {h}\n{subject[:90]}", card):
                order.append(card)
            if it["before"]:
                bt, btext = it["before"]
                clip = folder / f"{t}_1_before.mp4"
                if clip.exists() or H.cut_clip(ffmpeg, bt - 8, bt + 4, f"BEFORE: {btext[:90]}", clip, f"build {h} (before the fix)"):
                    order.append(clip)
                    it["before_clip"] = clip
            if it["after"]:
                at, atext = it["after"]
                clip = folder / f"{t}_2_after.mp4"
                if clip.exists() or H.cut_clip(ffmpeg, at - 2, at + 10, "AFTER the fix: the next game", clip, f"build {h}"):
                    order.append(clip)
                    it["after_clip"] = clip
        items.append(it)
    script = write_script(day, items)
    video = None
    if ffmpeg and any(p.name.endswith(("before.mp4", "after.mp4")) for p in order):
        H.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        lst = folder / "all.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in order), encoding="utf-8")
        video = H.VIDEO_DIR / f"BTD6 bot devlog {day}.mp4"
        subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(video)], capture_output=True, timeout=600)
    return script, video, items


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    script, video, items = build(day)
    with_footage = sum(1 for i in items if i["before_clip"] or i["after_clip"])
    print(f"{len(items)} commits; {with_footage} with footage")
    print("script:", script)
    print("video:", video)
